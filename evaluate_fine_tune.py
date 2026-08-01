"""
Day 15 Step 3 — Evaluate base vs fine-tuned model on the 5 held-out examples.

RUN FROM ft_env. Loads the base Qwen2.5-0.5B model twice — once as-is (baseline)
and once with the LoRA adapter from ./adapters/ applied (fine-tuned) — generates
an answer for each held-out question from both, and scores them on:

  - disclaimer_present  — did the model emit the required closing disclaimer?
  - defines_jargon      — did it define plan terms (deductible/copay/premium)
                          on first use, per Day 12 rule 3?
  - refuses_honestly    — did it say "I don't have that" instead of fabricating,
                          when the context did not support an answer?
  - length_ok           — answer body under ~150 words before the disclaimer?
                          (catches the Day 12 Variant B "wall of text" failure)

Scoring is heuristic, not model-graded — small enough to review every answer by
eye. The write-up is what matters; the numbers frame the comparison.
"""

import json
import re
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

BASE_MODEL = "Qwen/Qwen2.5-0.5B-Instruct"
ADAPTER_DIR = "adapters"
TEST_FILE = "fine_tune_test.jsonl"
OUT_FILE = "fine_tune_comparison.md"

# Force CPU for inference. MPS generation on Qwen 0.5B hits a matmul shape bug
# (LLVM ERROR: Failed to infer result type on mps.matmul) — CPU code paths avoid
# it. Slower (~2-3 min/answer vs ~30-90s on MPS) but functional.
DEVICE = "cpu"

DISCLAIMER_FRAGMENT = "not medical or legal advice"
JARGON_TERMS = ("deductible", "copay", "premium", "coinsurance", "network tier")
JARGON_EXPLAINERS = (
    "before your plan starts",
    "before the plan starts",
    "share of each covered",
    "amount you pay",
    "share you pay",
    "each month",
    "monthly",
    "in-network",
)
REFUSAL_MARKERS = (
    "i don't have",
    "not in your plan records",
    "member services",
    "cannot confirm",
    "not clearly",
    "does not clearly",
    "unknown",
)


def load_test():
    with open(TEST_FILE) as f:
        return [json.loads(line) for line in f if line.strip()]


def load_base(tokenizer):
    print(f"Loading base model...")
    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        torch_dtype=torch.float32,     # float32 on CPU — float16 CPU is slow/unstable
        device_map={"": DEVICE},
    )
    model.eval()
    return model


def load_finetuned(tokenizer):
    print(f"Loading fine-tuned model (base + adapter)...")
    base = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        torch_dtype=torch.float32,     # match the base above
        device_map={"": DEVICE},
    )
    model = PeftModel.from_pretrained(base, ADAPTER_DIR)
    model.eval()
    return model


def generate(model, tokenizer, messages_up_to_user):
    """Take a messages list ending with the user turn, generate the assistant reply."""
    prompt = tokenizer.apply_chat_template(
        messages_up_to_user,
        tokenize=False,
        add_generation_prompt=True,
    )
    inputs = tokenizer(prompt, return_tensors="pt").to(DEVICE)
    with torch.no_grad():
        output = model.generate(
            **inputs,
            max_new_tokens=350,
            do_sample=False,               # deterministic — greedy decoding
            pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id,
            repetition_penalty=1.05,
        )
    generated_ids = output[0][inputs["input_ids"].shape[1]:]
    return tokenizer.decode(generated_ids, skip_special_tokens=True).strip()


# --- Heuristic scoring ------------------------------------------------------

def score_answer(text, expected_answer):
    """Return a small dict of pass/fail heuristics for one answer."""
    lower = text.lower()

    disclaimer_present = DISCLAIMER_FRAGMENT in lower

    # Jargon-defined = if a jargon term appears, at least one plain-language
    # explainer phrase appears nearby.
    uses_jargon = any(term in lower for term in JARGON_TERMS)
    if uses_jargon:
        defines_jargon = any(exp in lower for exp in JARGON_EXPLAINERS)
    else:
        defines_jargon = True  # if no jargon used, nothing to define

    # Refuses_honestly is only relevant when the ideal answer was a refusal.
    ideal_was_refusal = any(marker in expected_answer.lower() for marker in REFUSAL_MARKERS)
    if ideal_was_refusal:
        refuses_honestly = any(marker in lower for marker in REFUSAL_MARKERS)
    else:
        refuses_honestly = True  # not applicable — mark as pass

    # Length check: answer body (before disclaimer) under 150 words.
    body = re.split(re.escape("This is coverage information"), text, maxsplit=1)[0]
    body_word_count = len(body.split())
    length_ok = body_word_count <= 150

    return {
        "disclaimer_present": disclaimer_present,
        "defines_jargon": defines_jargon,
        "refuses_honestly": refuses_honestly,
        "length_ok": length_ok,
        "body_words": body_word_count,
    }


def totals(scores):
    """Aggregate scores across the 5 test cases."""
    keys = ["disclaimer_present", "defines_jargon", "refuses_honestly", "length_ok"]
    out = {k: sum(1 for s in scores if s[k]) for k in keys}
    out["overall_pass"] = sum(1 for s in scores if all(s[k] for k in keys))
    return out


# --- Main -------------------------------------------------------------------

def main():
    print(f"Device: {DEVICE}")
    tests = load_test()
    print(f"Loaded {len(tests)} held-out test cases\n")

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # Generate base answers first, free the model, then generate fine-tuned.
    # Loading both simultaneously would push us back to swap-thrashing.
    print("=== Base model generation ===")
    base = load_base(tokenizer)
    base_answers = []
    for i, t in enumerate(tests, 1):
        prompt_msgs = t["messages"][:2]
        expected = t["messages"][2]["content"]
        print(f"  [{i}/{len(tests)}] generating...")
        ans = generate(base, tokenizer, prompt_msgs)
        base_answers.append({"question_msgs": prompt_msgs, "expected": expected, "answer": ans})
    del base

    print("\n=== Fine-tuned model generation ===")
    ft = load_finetuned(tokenizer)
    ft_answers = []
    for i, t in enumerate(tests, 1):
        prompt_msgs = t["messages"][:2]
        expected = t["messages"][2]["content"]
        print(f"  [{i}/{len(tests)}] generating...")
        ans = generate(ft, tokenizer, prompt_msgs)
        ft_answers.append({"question_msgs": prompt_msgs, "expected": expected, "answer": ans})
    del ft

    # Score both sides.
    base_scores = [score_answer(a["answer"], a["expected"]) for a in base_answers]
    ft_scores = [score_answer(a["answer"], a["expected"]) for a in ft_answers]
    base_totals = totals(base_scores)
    ft_totals = totals(ft_scores)

    # --- Write the comparison report ---
    lines = [
        "# Day 15 — Fine-Tune Comparison",
        "",
        f"**Base model:** `{BASE_MODEL}` (unmodified)",
        f"**Fine-tuned:** `{BASE_MODEL}` + LoRA adapter trained on `fine_tune_train.jsonl` (25 examples, 3 epochs).",
        "",
        "Held-out test set: 5 examples from `fine_tune_test.jsonl` — one per behavior category (faithful lookup, honest refusal, unknown-stays-unknown, cost without invention, wrong-plan trap). See `fine_tune_prep_notes.md` for what fine-tuning was and was not expected to fix.",
        "",
        "## Aggregate scores",
        "",
        "| Criterion | Base | Fine-Tuned | Δ |",
        "|---|---|---|---|",
    ]
    for k in ["disclaimer_present", "defines_jargon", "refuses_honestly", "length_ok", "overall_pass"]:
        b = base_totals[k]
        f = ft_totals[k]
        delta = f - b
        sign = "+" if delta > 0 else ("" if delta == 0 else "")
        lines.append(f"| {k.replace('_', ' ')} | {b}/5 | {f}/5 | {sign}{delta} |")

    lines.extend([
        "",
        "## Per-question comparison",
        "",
    ])

    for i, (t, ba, fa, bs, fs) in enumerate(zip(tests, base_answers, ft_answers, base_scores, ft_scores), 1):
        user_content = t["messages"][1]["content"]
        question = user_content.split("QUESTION:", 1)[-1].strip()
        lines.extend([
            f"### Q{i}: {question}",
            "",
            f"**Expected answer:**\n\n> {ba['expected'][:400]}",
            "",
            "**Base output:**",
            "",
            f"> {ba['answer'][:400]}",
            "",
            f"_scores: disclaimer={bs['disclaimer_present']}, jargon_defined={bs['defines_jargon']}, refuses_honestly={bs['refuses_honestly']}, length_ok={bs['length_ok']} ({bs['body_words']} words)_",
            "",
            "**Fine-tuned output:**",
            "",
            f"> {fa['answer'][:400]}",
            "",
            f"_scores: disclaimer={fs['disclaimer_present']}, jargon_defined={fs['defines_jargon']}, refuses_honestly={fs['refuses_honestly']}, length_ok={fs['length_ok']} ({fs['body_words']} words)_",
            "",
            "---",
            "",
        ])

    Path(OUT_FILE).write_text("\n".join(lines))
    print(f"\nWrote {OUT_FILE}")
    print(f"\nBase totals:       {base_totals}")
    print(f"Fine-tuned totals: {ft_totals}")


if __name__ == "__main__":
    main()
