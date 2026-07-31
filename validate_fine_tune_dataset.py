"""
Day 14 Step 4 — Validator for fine_tune_dataset.jsonl

Runs a series of checks against every line of the training file:

1.  Each line is well-formed JSON.
2.  Each object has a top-level `messages` key holding a list.
3.  The messages list has three entries in the order: system, user, assistant.
4.  Each message has string `role` and non-empty string `content`.
5.  The system content is not empty (the Day 12 prompt must be present).
6.  The user content includes both CONTEXT and QUESTION markers — this catches
    pairs that lost their context field during editing.
7.  The assistant content includes the required Day 12 closing disclaimer
    substring — this catches examples that would train the model to skip it.

The script prints a per-check summary and exits with status 1 if any check
fails, so it doubles as a pre-commit or CI check.
"""

import json
import sys
from pathlib import Path

DATASET_PATH = Path("fine_tune_dataset.jsonl")

# A distinctive fragment of the Day 12 closing disclaimer. We look for the
# fragment rather than the full string because line-wrapping differences would
# create false negatives, but no legitimate answer contains this phrase without
# also containing the rest of the disclaimer.
DISCLAIMER_FRAGMENT = "not medical or legal advice"


def check(condition, msg):
    """Return a (ok, msg) tuple used to accumulate per-line issues."""
    return (bool(condition), msg)


def validate_line(line_number, raw_line):
    """Return a list of failure messages for this line — empty list = fully valid."""
    failures = []

    # 1. JSON parseable
    try:
        obj = json.loads(raw_line)
    except json.JSONDecodeError as e:
        return [f"invalid JSON: {e}"]

    # 2. top-level shape
    if not isinstance(obj, dict) or "messages" not in obj:
        failures.append("missing top-level 'messages' key")
        return failures  # nothing else is checkable without it

    messages = obj["messages"]
    if not isinstance(messages, list):
        return ["'messages' is not a list"]

    # 3. exactly system/user/assistant in order
    expected_roles = ["system", "user", "assistant"]
    actual_roles = [m.get("role") for m in messages]
    if actual_roles != expected_roles:
        failures.append(f"roles were {actual_roles}, expected {expected_roles}")

    # 4. every message shape
    for i, m in enumerate(messages):
        if not isinstance(m.get("role"), str):
            failures.append(f"message[{i}] role is not a string")
        content = m.get("content")
        if not isinstance(content, str) or not content.strip():
            failures.append(f"message[{i}] content is empty or not a string")

    # If any structural failure so far, stop — later checks assume valid shape.
    if failures:
        return failures

    system_content = messages[0]["content"]
    user_content = messages[1]["content"]
    assistant_content = messages[2]["content"]

    # 5. system prompt not empty (already covered by step 4, but explicit for clarity)
    if len(system_content) < 100:
        failures.append(
            f"system content is only {len(system_content)} chars — "
            f"the Day 12 production prompt should be present"
        )

    # 6. user message actually has context + question markers
    if "CONTEXT:" not in user_content:
        failures.append("user content missing 'CONTEXT:' marker")
    if "QUESTION:" not in user_content:
        failures.append("user content missing 'QUESTION:' marker")

    # 7. assistant answer ends with the required disclaimer
    if DISCLAIMER_FRAGMENT not in assistant_content:
        failures.append(
            "assistant content missing the required closing disclaimer "
            f"(looked for '{DISCLAIMER_FRAGMENT}')"
        )

    return failures


def main():
    if not DATASET_PATH.exists():
        print(f"ERROR: {DATASET_PATH} not found in current directory.")
        sys.exit(1)

    total = 0
    valid = 0
    all_failures = []

    with DATASET_PATH.open() as f:
        for line_number, raw_line in enumerate(f, 1):
            raw_line = raw_line.rstrip("\n")
            if not raw_line.strip():
                # A truly blank line in JSONL is a bug — flag it, don't silently skip.
                all_failures.append((line_number, ["blank line"]))
                total += 1
                continue
            total += 1
            failures = validate_line(line_number, raw_line)
            if failures:
                all_failures.append((line_number, failures))
            else:
                valid += 1

    print(f"Validated {DATASET_PATH.name}")
    print(f"  Lines total:   {total}")
    print(f"  Lines valid:   {valid}")
    print(f"  Lines failed:  {total - valid}")

    if all_failures:
        print("\nFailures:")
        for line_number, failures in all_failures:
            print(f"  line {line_number}:")
            for f in failures:
                print(f"    - {f}")
        sys.exit(1)

    print("\nAll lines valid.")
    sys.exit(0)


if __name__ == "__main__":
    main()
