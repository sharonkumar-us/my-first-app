"""
Coverage Chatbot — grounded RAG pipeline.

Day 11: retrieve_and_answer() chains classify -> retrieve -> generate.
Day 12: PRODUCTION_SYSTEM_PROMPT locked as Variant E (hybrid).
Day 19 Step 1: generate_answer / retrieve_and_answer now return chunk_ids
               (the list of vector-store chunk IDs that made it into context),
               so the frontend can render "Policy sources" citations.
Day 20 Step 3: generate_answer / retrieve_and_answer now accept optional
               conversation history (last N turns) and a plan_hint (the plan
               the member has been discussing), so multi-turn conversations
               don't lose track of which plan is under discussion.

Key design point for citations: we DO NOT ask the model to cite. On a 7B model
that has trouble following the disclaimer rule reliably (see Day 12 scoring),
asking it to also inline citation markers would produce more hallucinated
citations than real ones. Instead we track WHICH chunks were passed to it and
attribute the whole answer to "sources consulted." This can't fabricate a
citation the retrieval layer never produced.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from retrieval_engine import retrieve

load_dotenv(Path(__file__).resolve().parent / ".env")

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
- Which facts in the context directly answer the question? If there are none, sayso —
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
For questions about your care, please consult your doctor. To confirm benefits orfile
an appeal, contact Member Services at 1-800-555-0100."

--- EXAMPLE: answer present in context ---
CONTEXT: Plan P101 (Gold PPO) — annual deductible: $500. Copay: 10%.
QUESTION: What's the deductible on the Gold PPO plan?
ANSWER: The Gold PPO plan (P101) has a $500 annual deductible — that's what you pay
out of pocket before the plan starts covering costs. After that, your copay is 10%.

This is coverage information based on your plan records, not medical or legal advice.
For questions about your care, please consult your doctor. To confirm benefits orfile
an appeal, contact Member Services at 1-800-555-0100.

--- EXAMPLE: answer absent from context ---
CONTEXT: Plan P103 (Bronze HMO) — annual deductible: $3,000. Copay: 30%.
QUESTION: Does the Bronze plan cover dental cleanings?
ANSWER: I don't have dental benefits for the Bronze HMO plan in your records — I can
see the deductible and copay, but not dental coverage.

This is coverage information based on your plan records, not medical or legal advice.
For questions about your care, please consult your doctor. To confirm benefits orfile
an appeal, contact Member Services at 1-800-555-0100."""


def generate_answer(question, context, chunk_ids=None, history=None, plan_hint=None):
    """Generate a grounded answer using ONLY the provided context.

    Day 19: accepts and returns chunk_ids (the retrieval-layer identifiers of
    the chunks that made it into `context`). We do not modify the prompt to
    ask the model to cite — the tracking happens at the pipeline level, so a
    7B model can't hallucinate citations we never had.

    Day 20 Step 3: accepts optional `history` (a list of prior
    {"role": ..., "content": ...} messages, oldest first) inserted between the
    system prompt and the current question, and an optional `plan_hint` (a
    plan name like "Gold PPO") noted in the prompt when the member has been
    discussing that plan earlier in the conversation but the current question
    doesn't repeat the plan name.

    Returns a dict with two keys:
        - answer:    the model's natural-language response
        - chunk_ids: the chunk IDs passed in (for downstream citation rendering)
    """
    plan_note = (
        f"(The member has been discussing the {plan_hint} plan earlier in this "
        f"conversation — assume this plan unless the question names a different one.)\n"
        if plan_hint else ""
    )
    user_prompt = f"""Context: {context}

{plan_note}Question: {question}"""

    messages = [{"role": "system", "content": PRODUCTION_SYSTEM_PROMPT}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_prompt})

    response = client.chat.completions.create(
        model=GENERATION_MODEL,
        messages=messages,
    )
    return {
        "answer": response.choices[0].message.content,
        "chunk_ids": chunk_ids or [],
    }


def retrieve_and_answer(question, history=None, plan_hint=None):
    """Full RAG pipeline: retrieve context, then generate a grounded answer.

    Day 19: threads chunk_ids from retrieval through to the response dict, so
    /chat callers can hand them to the frontend for citation display.

    Day 20 Step 3: accepts optional `history` and `plan_hint`, passed straight
    through to generate_answer(). Also nudges the RETRIEVAL question itself
    with the plan name when the member's current question doesn't name one —
    so SQL/vector lookups benefit from the same memory, not just the final
    answer generation.
    """
    retrieval_question = question
    if plan_hint and plan_hint.lower() not in question.lower():
        retrieval_question = f"{question} (regarding the {plan_hint} plan)"

    retrieval_result = retrieve(retrieval_question)

    # Extract chunk IDs from vector_chunks if any were retrieved. Structured-only
    # queries (pure SQL) will have vector_chunks=None; treat that as no citations.
    vector_chunks = retrieval_result.get("vector_chunks") or []
    chunk_ids = [chunk["id"] for chunk in vector_chunks]

    generation = generate_answer(
        question,
        retrieval_result["merged_context"],
        chunk_ids=chunk_ids,
        history=history,
        plan_hint=plan_hint,
    )

    return {
        "question": question,
        "classification": retrieval_result["classification"],
        "context": retrieval_result["merged_context"],
        "answer": generation["answer"],
        "chunk_ids": generation["chunk_ids"],
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
            f"**Answer:** {result['answer']}\n\n"
            f"**Chunk IDs consulted:** {result['chunk_ids']}\n"
        )
        print(f"[{i}/10] done")
    with open("rag_qa_results.md", "w") as f:
        f.write("\n".join(lines))
    print("Wrote rag_qa_results.md")
