"""
Day 26 Step 1 — Token counting.

Reuses the same tiktoken encoding already installed and used by
coverage-chatbot-api/main.py's Day 20 summarization logic (TOKEN_ENCODING =
tiktoken.get_encoding("cl100k_base")), so token counts here are directly
comparable to Day 20's counts rather than using a different encoding that
would produce different numbers for the same text.
"""

import tiktoken

_ENCODING = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """Count tokens in a string using the cl100k_base encoding.

    Returns 0 for empty or None input rather than raising, since callers
    (Day 26 Step 2's per-request logging) should never crash on an empty
    prompt or completion.
    """
    if not text:
        return 0
    return len(_ENCODING.encode(text))


if __name__ == "__main__":
    samples = [
        "",
        "What's the status of claim C1001?",
        "The Gold PPO plan has a $500 monthly premium — that's what you pay "
        "out of pocket before the plan starts covering costs.",
    ]
    for s in samples:
        print(f"{count_tokens(s):>4} tokens: {s!r}")
