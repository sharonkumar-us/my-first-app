"""
Day 14 Step 5 — Stratified 25/5 split of fine_tune_dataset.jsonl.

Writes fine_tune_train.jsonl (25 lines) and fine_tune_test.jsonl (5 lines).

Design choices:

  1. SEEDED SHUFFLE — random enough that the split is not trivially "the first
     25 lines," reproducible so re-runs give the same split.

  2. STRATIFIED across the six categories from Step 2:
        A. Faithful lookups + jargon defined     (10)
        B. Honest refusal when context missing   (7)
        C. 'unknown' stays 'unknown'             (5)  <- the Day 13 fix
        D. Cost estimation without inventing     (4)
        E. General process questions             (2)
        F. Wrong-plan-in-context trap            (2)

     One test example is drawn from each of A, B, C, D, F. Group E is not held
     out — it exercises the least novel behavior (procedural answers without any
     tool or retrieval mechanic), so its 2 examples both stay in training. This
     gives Day 15 a test set that measures the five behaviors most likely to
     regress under fine-tuning.

  3. The Day 15 mission text says "you will NOT train on the held-out set — Day
     15 uses it for comparison" — so train and test are strictly disjoint. The
     script asserts this before writing.
"""

import json
import random
from pathlib import Path

SRC = Path("fine_tune_dataset.jsonl")
TRAIN = Path("fine_tune_train.jsonl")
TEST = Path("fine_tune_test.jsonl")

# Category boundaries in the source file, mirroring the order produced by
# Step 2. These are the ORIGINAL indices in fine_tune_dataset.jsonl.
GROUPS = {
    "A": list(range(0, 10)),   # 10 pairs
    "B": list(range(10, 17)),  # 7 pairs
    "C": list(range(17, 22)),  # 5 pairs
    "D": list(range(22, 26)),  # 4 pairs
    "E": list(range(26, 28)),  # 2 pairs — not held out
    "F": list(range(28, 30)),  # 2 pairs
}
HELD_OUT_GROUPS = ["A", "B", "C", "D", "F"]  # E is deliberately excluded

SEED = 20260731  # today's date; changing gives a different but reproducible split


def main():
    if not SRC.exists():
        raise SystemExit(f"ERROR: {SRC} not found in current directory.")

    with SRC.open() as f:
        lines = [line for line in f if line.strip()]

    if len(lines) != 30:
        raise SystemExit(f"ERROR: expected 30 lines, found {len(lines)}.")

    rng = random.Random(SEED)

    # Pick one held-out index from each of the five chosen groups.
    test_indices = []
    for g in HELD_OUT_GROUPS:
        pool = list(GROUPS[g])
        rng.shuffle(pool)
        test_indices.append(pool[0])

    test_set = set(test_indices)
    train_indices = [i for i in range(30) if i not in test_set]

    assert len(test_indices) == 5, f"test size {len(test_indices)} != 5"
    assert len(train_indices) == 25, f"train size {len(train_indices)} != 25"
    assert set(train_indices).isdisjoint(test_set), "train and test overlap!"

    with TRAIN.open("w") as f:
        for i in train_indices:
            f.write(lines[i])

    with TEST.open("w") as f:
        for i in test_indices:
            f.write(lines[i])

    print(f"Wrote {TRAIN} ({len(train_indices)} lines)")
    print(f"Wrote {TEST}  ({len(test_indices)} lines)")
    print()
    print("Held-out test set — one example per group:")
    for g, i in zip(HELD_OUT_GROUPS, test_indices):
        # Peek at the user question of the held-out example for a readable summary.
        example = json.loads(lines[i])
        user_content = example["messages"][1]["content"]
        # The user content is "CONTEXT:\n...\n\nQUESTION: ..." — grab the question tail.
        question = user_content.split("QUESTION:", 1)[-1].strip()
        print(f"  group {g}, source index {i}: {question}")


if __name__ == "__main__":
    main()
