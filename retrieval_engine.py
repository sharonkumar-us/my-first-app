import ollama
import sqlite3
import re

import chromadb
from sentence_transformers import SentenceTransformer

CLASSIFIER_MODEL = "qwen2.5-coder:7b"


def classify_question(question):
    """Classify a member question as 'structured', 'unstructured', or 'both'."""
    prompt = f"""You are a query router for a healthcare coverage chatbot. Classify the following member question into exactly one category:

- "structured": questions answerable from a database of plans and claims (e.g. deductible amounts, premium costs, claim status, claim amounts)
- "unstructured": questions answerable from policy documents (e.g. whether a specific procedure or service is covered, claims process steps, enrollment details)
- "both": questions that need both a specific plan/claim lookup AND policy wording (e.g. "is X covered under MY plan" - needs the plan's tier AND the policy's coverage rules)

Respond with ONLY one word: structured, unstructured, or both.

Question: "{question}"

Classification:"""

    response = ollama.chat(
        model=CLASSIFIER_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    label = response["message"]["content"].strip().lower()

    # Normalize in case the model adds extra words
    if "both" in label:
        return "both"
    elif "unstructured" in label:
        return "unstructured"
    elif "structured" in label:
        return "structured"
    else:
        return "unstructured"  # safe fallback


DB_SCHEMA = """
Table: plans
Columns: plan_id (TEXT), plan_name (TEXT), monthly_premium (INTEGER), annual_deductible (INTEGER), copay_pct (INTEGER), coverage_type (TEXT), network_tier (TEXT)

Table: claims
Columns: claim_id (TEXT), member_id (TEXT), plan_id (TEXT), procedure (TEXT), claim_amount (INTEGER), status (TEXT), date_filed (TEXT)
"""


def generate_sql(question):
    """Ask the LLM to write a SQL query for the given question, using our known schema."""
    prompt = f"""You are a SQL generator for a SQLite database with this schema:

{DB_SCHEMA}

Write a single SQL SELECT query that answers this question. Respond with ONLY the SQL query, no explanation, no markdown formatting, no backticks.

Question: "{question}"

SQL:"""

    response = ollama.chat(
        model=CLASSIFIER_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    sql = response["message"]["content"].strip()
    # Strip markdown code fences if the model adds them anyway
    sql = re.sub(r"^```sql\s*|^```\s*|```$", "", sql, flags=re.MULTILINE).strip()
    return sql


def sql_lookup(question):
    """Generate SQL for a structured question, run it against coverage.db, return results."""
    sql = generate_sql(question)

    # Safety guard: only allow SELECT statements
    if not sql.strip().upper().startswith("SELECT"):
        return {"sql": sql, "error": "Refused: generated query was not a SELECT statement", "rows": []}

    try:
        conn = sqlite3.connect("coverage.db")
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        cols = [desc[0] for desc in cur.description]
        conn.close()
        return {"sql": sql, "error": None, "rows": [dict(zip(cols, row)) for row in rows]}
    except Exception as e:
        return {"sql": sql, "error": str(e), "rows": []}


embed_model = SentenceTransformer("all-MiniLM-L6-v2")
chroma_client = chromadb.PersistentClient(path="./chroma_data")
collection = chroma_client.get_collection("coverage_kb")


def vector_lookup(question, n_results=5, plan_type_filter=None):
    """Embed the question and query the vector DB for the top-N relevant chunks.
    Optionally scope results to a specific plan_type (learned from Day 9's finding)."""
    query_embedding = embed_model.encode(question).tolist()

    query_kwargs = {
        "query_embeddings": [query_embedding],
        "n_results": n_results,
    }
    if plan_type_filter:
        query_kwargs["where"] = {"plan_type": plan_type_filter}

    results = collection.query(**query_kwargs)

    chunks = []
    for i in range(len(results["ids"][0])):
        chunks.append({
            "id": results["ids"][0][i],
            "distance": results["distances"][0][i],
            "text": results["documents"][0][i],
            "metadata": results["metadatas"][0][i],
        })
    return chunks


def retrieve(question):
    """Route the question to sql_lookup, vector_lookup, or both, then merge into one context block."""
    classification = classify_question(question)

    context_parts = []
    sql_result = None
    vector_chunks = None

    if classification in ("structured", "both"):
        sql_result = sql_lookup(question)
        if sql_result["error"] is None and sql_result["rows"]:
            context_parts.append(f"[Structured data from database]\n{sql_result['rows']}")

    if classification in ("unstructured", "both"):
        vector_chunks = vector_lookup(question)
        # De-duplicate: skip chunks whose text is already substantially present elsewhere
        seen_texts = set()
        for c in vector_chunks:
            if c["text"] not in seen_texts:
                seen_texts.add(c["text"])
                context_parts.append(f"[Policy text, section: {c['metadata']['section']}]\n{c['text']}")

    merged_context = "\n\n---\n\n".join(context_parts)

    return {
        "question": question,
        "classification": classification,
        "sql_result": sql_result,
        "vector_chunks": vector_chunks,
        "merged_context": merged_context,
    }


if __name__ == "__main__":
    # --- Quick test ---
    result = retrieve("What's my deductible on the Gold PPO plan?")
    print(f"Classification: {result['classification']}")
    print(f"\nMerged context:\n{result['merged_context']}")

    TEST_QUESTIONS = [
        "What's my copay under the Bronze HMO plan?",
        "Is maternity care covered on the Bronze plan?",
        "What's the status of claim C1001?",
        "Is physical therapy covered under my Silver plan?",
        "What's the monthly premium for Gold PPO?",
        "What is the claims submission process?",
        "How much was billed for claim C1003?",
        "What information is needed to enroll in a plan?",
        "Is my X-ray procedure covered and what's my deductible under Silver HMO?",
        "What's the status of claim C-2031?",
    ]

    print("\n\n=== TEST HARNESS: 10 questions ===")
    test_results = []
    for i, q in enumerate(TEST_QUESTIONS):
        print(f"\n{'='*60}\nQ{i+1}: {q}")
        result = retrieve(q)
        print(f"Classification: {result['classification']}")
        if result["sql_result"]:
            print(f"Generated SQL: {result['sql_result']['sql']}")
            print(f"SQL Error: {result['sql_result']['error']}")
            print(f"SQL Rows: {result['sql_result']['rows']}")
        print(f"Full context:\n{result['merged_context']}")
        test_results.append(result)
