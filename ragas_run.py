"""
Day 27 — RAGAS-equivalent evaluation.
RAGAS 0.1.21 is incompatible with Python 3.14's asyncio (Timeout outside task).
Scores are computed manually using the same definitions as RAGAS:
  faithfulness     - LLM judge: are all answer claims grounded in context?
  answer_relevancy - embedding cosine similarity: answer vs question
  context_precision - embedding cosine similarity: context vs question
  context_recall   - LLM judge: does context contain enough to answer ground truth?
LLM: qwen2.5-coder:7b via Ollama. Embeddings: all-MiniLM-L6-v2.
"""
import json, re
from pathlib import Path
from openai import OpenAI
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from retrieval_engine import retrieve
from rag_chatbot import retrieve_and_answer

EVAL_SET_PATH = Path(__file__).resolve().parent / "ragas_eval_set.jsonl"
OLLAMA_MODEL = "qwen2.5-coder:7b"

client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
embedder = SentenceTransformer("all-MiniLM-L6-v2")


def load_eval_set():
    rows = []
    with open(EVAL_SET_PATH) as f:
        for line in f:
            rows.append(json.loads(line.strip()))
    return rows


def extract_contexts(retrieval_result):
    contexts = []
    sql = retrieval_result.get("sql_result")
    if sql and sql.get("rows"):
        contexts.append(f"SQL result: {json.dumps(sql['rows'])}")
    chunks = retrieval_result.get("vector_chunks")
    if chunks and isinstance(chunks, list):
        for chunk in chunks:
            if isinstance(chunk, dict):
                text = chunk.get("text", "").strip()
                if text:
                    contexts.append(text)
            elif isinstance(chunk, str) and chunk.strip():
                contexts.append(chunk.strip())
    if not contexts:
        contexts = ["No relevant context found."]
    return contexts


def llm_judge(prompt):
    """Call Ollama and parse a 0.0-1.0 score from the response."""
    try:
        resp = client.chat.completions.create(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        text = resp.choices[0].message.content.strip()
        numbers = re.findall(r"0?\.\d+|1\.0|0|1", text)
        if numbers:
            return min(1.0, max(0.0, float(numbers[0])))
        return 0.5
    except Exception as e:
        print(f"    LLM judge error: {e}")
        return float("nan")


def score_faithfulness(answer, contexts):
    context_str = "\n".join(contexts)
    prompt = (
        f"Context:\n{context_str}\n\n"
        f"Answer:\n{answer}\n\n"
        "Does the answer contain ONLY information that is directly supported by the context above? "
        "Reply with a single decimal score between 0.0 (not faithful) and 1.0 (fully faithful). "
        "Reply with the number only."
    )
    return llm_judge(prompt)


def score_answer_relevancy(answer, question):
    if not answer.strip():
        return 0.0
    q_emb = embedder.encode([question])
    a_emb = embedder.encode([answer])
    return float(cosine_similarity(q_emb, a_emb)[0][0])


def score_context_precision(contexts, question):
    if not contexts or contexts == ["No relevant context found."]:
        return 0.0
    q_emb = embedder.encode([question])
    c_embs = embedder.encode(contexts)
    sims = cosine_similarity(q_emb, c_embs)[0]
    return float(sims.mean())


def score_context_recall(contexts, ground_truth):
    context_str = "\n".join(contexts)
    prompt = (
        f"Context:\n{context_str}\n\n"
        f"Ground truth answer:\n{ground_truth}\n\n"
        "Does the context contain enough information to produce the ground truth answer? "
        "Reply with a single decimal score between 0.0 (context missing key info) and 1.0 (context fully supports the answer). "
        "Reply with the number only."
    )
    return llm_judge(prompt)


def run_pipeline_on_eval_set(rows):
    results = []
    for i, row in enumerate(rows):
        question = row["question"]
        print(f"[{i+1}/{len(rows)}] Running: {question[:60]}...")
        try:
            result = retrieve_and_answer(question)
            answer = result.get("answer", "")
            retrieval = retrieve(question)
            contexts = extract_contexts(retrieval)
        except Exception as e:
            print(f"  ERROR: {e}")
            answer = ""
            contexts = ["No relevant context found."]
        results.append({
            "question": question,
            "answer": answer,
            "contexts": contexts,
            "ground_truth": row["ground_truth"],
        })
    return results


def score_all(results):
    scores = {
        "faithfulness": [],
        "answer_relevancy": [],
        "context_precision": [],
        "context_recall": [],
    }
    for i, r in enumerate(results):
        print(f"  Scoring [{i+1}/{len(results)}]: {r['question'][:50]}...")
        scores["faithfulness"].append(
            score_faithfulness(r["answer"], r["contexts"]))
        scores["answer_relevancy"].append(
            score_answer_relevancy(r["answer"], r["question"]))
        scores["context_precision"].append(
            score_context_precision(r["contexts"], r["question"]))
        scores["context_recall"].append(
            score_context_recall(r["contexts"], r["ground_truth"]))

    import math
    def safe_mean(lst):
        valid = [x for x in lst if not math.isnan(x)]
        return round(sum(valid) / len(valid), 4) if valid else float("nan")

    return {k: safe_mean(v) for k, v in scores.items()}, scores


if __name__ == "__main__":
    print("Loading eval set...")
    rows = load_eval_set()
    print(f"Running {len(rows)} questions through RAG pipeline...")
    results = run_pipeline_on_eval_set(rows)
    print("\nScoring with RAGAS-equivalent metrics...")
    summary, per_question = score_all(results)
    print("\n=== RAGAS SCORECARD ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")
