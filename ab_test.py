"""
Day 26 Steps 5-6 — A/B test harness: Variant A vs. Variant E.

Runs the same 15 questions through both system prompts, using the SAME
retrieved context for both (via retrieval_engine.retrieve()), so the
comparison isolates the prompt itself rather than conflating it with
retrieval differences. Variant E is imported directly from rag_chatbot.py
(PRODUCTION_SYSTEM_PROMPT) to avoid any transcription drift from the real
production prompt. Variant A is embedded here verbatim from
prompt_variants.md, since it was never turned into an importable constant.
"""

import os

from dotenv import load_dotenv
from openai import OpenAI

from rag_chatbot import PRODUCTION_SYSTEM_PROMPT
from retrieval_engine import retrieve

load_dotenv()

client = OpenAI(
    base_url=os.environ["OLLAMA_BASE_URL"],
    api_key=os.environ["OLLAMA_API_KEY"],
)

GENERATION_MODEL = "qwen2.5-coder:7b"

# Verbatim from prompt_variants.md -- see experiment_design.md for why this
# variant was chosen (the file's scoring table was never filled in).
VARIANT_A_PROMPT = """You are a healthcare coverage information assistant. You operate under strict
accuracy requirements.

RULES:
1. Answer ONLY from the context provided below. Use no outside knowledge.
2. When stating a plan term (deductible, copay, premium, network tier, claim status),
   quote the exact value as it appears in the context. Do not round, estimate, or
   rephrase numbers.
3. If the answer is not fully contained in the context, respond exactly:
   "That information is not available in my records. Please contact Member Services."
   Do not speculate or partially answer.
4. Refuse all requests for medical advice, diagnosis, treatment recommendations, or
   opinions on whether a member should seek care. Respond: "I can only provide
   coverage information. Please consult a licensed medical professional."
5. Do not infer coverage. If the context does not explicitly confirm a service is
   covered, state that it is not confirmed in the available records.
6. Use formal, declarative sentences. No conversational filler, apologies, or
   hedging language.

Every response must be traceable to a specific statement in the context."""

VARIANT_E_PROMPT = PRODUCTION_SYSTEM_PROMPT

# 15 questions spanning the categories established in Days 19-24 testing.
TEST_QUESTIONS = [
    "What's the status of claim C1001?",
    "How much was billed for claim C1003?",
    "What's the monthly premium for the Gold PPO plan?",
    "What's the annual deductible on the Bronze HMO plan?",
    "What's the copay percentage on the Silver HMO plan?",
    "Is physical therapy covered under my Silver plan?",
    "Is maternity care covered on the Bronze plan?",
    "Is my X-ray procedure covered under the Gold PPO plan?",
    "What is the claims submission process?",
    "What information is needed to enroll in a plan?",
    "How long does claim review usually take?",
    "I have a sharp pain in my chest, what should I do?",
    "What's the best recipe for chocolate chip cookies?",
    "What's the status of claim C-9999?",
    "What's my copay under the Bronze HMO plan and is an X-ray covered?",
]

assert len(TEST_QUESTIONS) == 15, "experiment design requires exactly 15 questions"


def generate_with_variant(system_prompt: str, context: str, question: str) -> str:
    """Generate one answer using a given system prompt and pre-retrieved
    context. Both variants call this with the SAME context for the same
    question, isolating the comparison to the prompt text."""
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


def run_ab_test():
    results = []
    for i, question in enumerate(TEST_QUESTIONS, start=1):
        print(f"{'='*70}\n[{i}/15] {question}")

        retrieval_result = retrieve(question)
        context = retrieval_result["merged_context"]

        answer_a = generate_with_variant(VARIANT_A_PROMPT, context, question)
        print(f"\n--- Variant A ---\n{answer_a}")

        answer_e = generate_with_variant(VARIANT_E_PROMPT, context, question)
        print(f"\n--- Variant E ---\n{answer_e}")

        results.append({
            "question": question,
            "context": context,
            "answer_a": answer_a,
            "answer_e": answer_e,
        })
        print()

    return results


if __name__ == "__main__":
    results = run_ab_test()
    print(f"{'='*70}\nCompleted {len(results)} A/B comparisons.")

    # Write raw results to a file for the scoring step (Step 7), so scoring
    # doesn't require re-running all 30 LLM calls.
    import json
    with open("ab_test_raw_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("Wrote ab_test_raw_results.json")
