import os
from dotenv import load_dotenv
from openai import OpenAI
from retrieval_engine import retrieve

load_dotenv()

client = OpenAI(
    base_url=os.environ["OLLAMA_BASE_URL"],
    api_key=os.environ["OLLAMA_API_KEY"],
)

GENERATION_MODEL = "qwen2.5-coder:7b"

# --- Quick smoke test ---
response = client.chat.completions.create(
    model=GENERATION_MODEL,
    messages=[{"role": "user", "content": "Say hello in exactly 5 words."}],
)
print(response.choices[0].message.content)
def generate_answer(question, context):
    """Generate a grounded answer using ONLY the provided context."""
    system_prompt = """Answer using ONLY the context below.
If the answer isn't in the context, say you don't know and suggest the member contact support.
This is not medical advice."""

    user_prompt = f"""Context: {context}

Question: {question}"""

    response = client.chat.completions.create(
        model=GENERATION_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return response.choices[0].message.content
def retrieve_and_answer(question):
    """Full RAG pipeline: retrieve context, then generate a grounded answer."""
    retrieval_result = retrieve(question)
    answer = generate_answer(question, retrieval_result["merged_context"])
    return {
        "question": question,
        "classification": retrieval_result["classification"],
        "context": retrieval_result["merged_context"],
        "answer": answer,
    }
if __name__ == "__main__":
    questions = [
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
    lines = ["# Day 11 — Full RAG Pipeline Q&A Results\n"]
    for i, q in enumerate(questions, 1):
        result = retrieve_and_answer(q)
        lines.append(
            f"## Q{i}: {q}\n\n"
            f"**Classification:** {result['classification']}\n\n"
            f"**Answer:** {result['answer']}\n"
        )
        print(f"[{i}/10] done")
    with open("rag_qa_results.md", "w") as f:
        f.write("\n".join(lines))
    print(f"Wrote rag_qa_results.md")