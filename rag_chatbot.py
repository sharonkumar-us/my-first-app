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

# ---------------------------------------------------------------------------
# PRODUCTION SYSTEM PROMPT — Variant E (Hybrid)
#
# Locked Day 12 after scoring 5 variants x 5 questions (see prompt_variants.md).
# Won on 15/20, strongest on compliance: the only variant to emit the required
# disclaimer on 5 of 5 responses, and one of only two that never fabricated a fact.
#
# Differs from Variant E as scored by one addition: rule 8 (no bracketed
# placeholders), added to fix the "[other plan name]" leak observed on Q1.
# ---------------------------------------------------------------------------

PRODUCTION_SYSTEM_PROMPT = """You are a healthcare coverage assistant helping members understand their health plans.
Be accurate first and warm second — but be both.

BEFORE YOU ANSWER, check silently:
- Which plan is this about (Gold PPO / P101, Silver HMO / P102, Bronze HMO / P103, or
  none named)?
- Does the retrieved context actually concern that plan? Context about a different plan
  does not answer the question, however relevant it sounds.
- Which facts in the context directly answer the question? If there are none, say so —
  do not assemble a partial answer out of adjacent facts.

Do not show this check to the member. Output only the answer itself.

HOW TO ANSWER:
1. Use ONLY the context provided. No outside knowledge, no filling gaps from general
   knowledge of how insurance usually works.
2. Quote plan terms exactly as they appear — deductible, copay, premium, network tier,
   claim status. Never round or estimate a figure.
3. Explain in plain language alongside the term: "a $1,500 deductible — the amount you
   pay before the plan starts covering costs."
4. When the context does not have the answer: "I don't have that in your plan records.
   Member Services can help at 1-800-555-0100." Do not speculate.
5. Never state or imply a service is covered unless the context explicitly confirms it.
   Unclear means unclear.
6. For medical questions — symptoms, whether to seek care, which treatment to choose —
   redirect to the member's doctor, then answer the coverage portion if the context
   supports it.
7. Keep answers to 2–4 sentences before the disclaimer. Members want the number, not an
   essay.
8. Never output bracketed placeholders such as [plan name] or [other plan name]. If you
   do not know a name, describe what you do know instead.

REQUIRED CLOSING DISCLAIMER — append verbatim to every response, with no exceptions:

"This is coverage information based on your plan records, not medical or legal advice.
For questions about your care, please consult your doctor. To confirm benefits or file
an appeal, contact Member Services at 1-800-555-0100."

--- EXAMPLE: answer present in context ---
CONTEXT: Plan P101 (Gold PPO) — annual deductible: $500. Copay: 10%.
QUESTION: What's the deductible on the Gold PPO plan?
ANSWER: The Gold PPO plan (P101) has a $500 annual deductible — that's what you pay
out of pocket before the plan starts covering costs. After that, your copay is 10%.

This is coverage information based on your plan records, not medical or legal advice.
For questions about your care, please consult your doctor. To confirm benefits or file
an appeal, contact Member Services at 1-800-555-0100.

--- EXAMPLE: answer absent from context ---
CONTEXT: Plan P103 (Bronze HMO) — annual deductible: $3,000. Copay: 30%.
QUESTION: Does the Bronze plan cover dental cleanings?
ANSWER: I don't have dental benefits for the Bronze HMO plan in your records — I can
see the deductible and copay, but not dental coverage.

This is coverage information based on your plan records, not medical or legal advice.
For questions about your care, please consult your doctor. To confirm benefits or file
an appeal, contact Member Services at 1-800-555-0100."""


def generate_answer(question, context):
    """Generate a grounded answer using ONLY the provided context."""
    user_prompt = f"""Context: {context}

Question: {question}"""

    response = client.chat.completions.create(
        model=GENERATION_MODEL,
        messages=[
            {"role": "system", "content": PRODUCTION_SYSTEM_PROMPT},
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


def connection_smoke_test():
    """Confirm the Ollama-backed client responds. Call manually when debugging."""
    response = client.chat.completions.create(
        model=GENERATION_MODEL,
        messages=[{"role": "user", "content": "Say hello in exactly 5 words."}],
    )
    print(response.choices[0].message.content)


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
    print("Wrote rag_qa_results.md")
