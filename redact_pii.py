"""
Day 25 Step 2-3 — PHI/PII redaction, with unit tests.

Built from a direct audit of this project's actual data (see GOVERNANCE.md
"PHI/PII fields present" section) rather than generic patterns. Covers:
  - member_id (format M#### per data/plans.csv and coverage.db, e.g. M1001)
  - claim_id (format C#### per coverage.db, e.g. C1001)
  - Names following "Member" (the exact pattern found embedded in
    knowledge_base.jsonl chunk10: "Member Jane Test (Member ID M1001)")
  - Dollar amounts (claim_amount is flagged PHI-adjacent in GOVERNANCE.md
    when tied to a member/claim context)

Regex-based rather than Presidio: this project's PHI surface is small and
well-understood (a handful of known ID formats from Days 4/6), so a
lightweight approach is more maintainable and auditable than pulling in a
heavier NLP-based dependency for this exercise's scope.

KNOWN LIMITATION (documented, not fixed): the dollar-amount pattern cannot
distinguish a PHI-adjacent amount (a specific claim's billed cost) from
non-PHI product data (a plan's stated deductible or premium). It redacts
both uniformly, erring toward over-redaction as the safer default. Test 3
below documents this behavior explicitly rather than treating it as a bug.
"""

import re

MEMBER_ID_PATTERN = re.compile(r"\bM\d{4}\b")
CLAIM_ID_PATTERN = re.compile(r"\bC\d{4}\b")
MEMBER_NAME_PATTERN = re.compile(r"\bMember\s+[A-Z][a-z]+\s+[A-Z][a-z]+\b")
# The one synthetic name found in this project's data (knowledge_base.jsonl
# chunk10: "Member Jane Test"). Catches it in ANY phrasing (e.g. "Jane Test's
# full name"), not just the exact "Member Jane Test" shape MEMBER_NAME_PATTERN
# requires -- added after Day 25 adversarial testing found the model can
# rephrase a leaked name without the literal word "Member" preceding it.
KNOWN_NAMES_PATTERN = re.compile(r"\bJane\s+Test\b")
DOLLAR_AMOUNT_PATTERN = re.compile(r"\$[\d,]+(?:\.\d{2})?")


def redact_pii(text: str) -> str:
    """Redact known PHI/PII patterns from a string, returning the redacted
    text. Order: member IDs and claim IDs first (specific, unambiguous),
    then member names, then dollar amounts (broadest pattern, run last so
    it never accidentally consumes part of an ID like "M1001").

    Never raises on empty or non-PHI text — returns it unchanged.
    """
    if not text:
        return text

    redacted = text
    redacted = MEMBER_ID_PATTERN.sub("[MEMBER_ID_REDACTED]", redacted)
    redacted = CLAIM_ID_PATTERN.sub("[CLAIM_ID_REDACTED]", redacted)
    redacted = MEMBER_NAME_PATTERN.sub("Member [NAME_REDACTED]", redacted)
    redacted = KNOWN_NAMES_PATTERN.sub("[NAME_REDACTED]", redacted)
    redacted = DOLLAR_AMOUNT_PATTERN.sub("[AMOUNT_REDACTED]", redacted)
    return redacted


# ---------------------------------------------------------------------------
# Unit tests — Day 25 Step 3. Plain assert statements, matching this
# project's existing test pattern (retrieval_engine.py, tool_calling_chatbot.py
# both use assert-based __main__ harnesses rather than pytest/unittest).
# ---------------------------------------------------------------------------

def test_redacts_full_phi_sentence():
    """The exact PHI shape found embedded in knowledge_base.jsonl chunk10 —
    the real finding that motivated this whole step (see GOVERNANCE.md)."""
    text = (
        "Member Jane Test (Member ID M1001) submitted a claim for an X-ray "
        "procedure billed at $250 under the Gold PPO plan."
    )
    result = redact_pii(text)
    assert "Jane Test" not in result, "member name was not redacted"
    assert "M1001" not in result, "member ID was not redacted"
    assert "$250" not in result, "dollar amount was not redacted"
    assert "[NAME_REDACTED]" in result
    assert "[MEMBER_ID_REDACTED]" in result
    assert "[AMOUNT_REDACTED]" in result
    # Non-PHI content must survive untouched.
    assert "X-ray" in result
    assert "Gold PPO" in result
    print("PASS: test_redacts_full_phi_sentence")


def test_redacts_claim_id_in_question():
    """A member asking about their own claim by ID — a realistic /chat
    message this project's own users actually send (per Day 19-24 test
    questions)."""
    text = "What's the status of claim C1001? My member ID is M2002."
    result = redact_pii(text)
    assert "C1001" not in result
    assert "M2002" not in result
    assert "[CLAIM_ID_REDACTED]" in result
    assert "[MEMBER_ID_REDACTED]" in result
    print("PASS: test_redacts_claim_id_in_question")


def test_known_limitation_overredacts_non_phi_dollar_amounts():
    """Documents the known limitation explicitly: a plan's deductible
    (product data, NOT PHI) gets redacted the same as a claim amount would,
    because redact_pii cannot distinguish context from pattern alone. This
    test asserts the CURRENT (over-redacting) behavior so a future change
    to the pattern is a deliberate decision, not an accidental regression."""
    text = "Your deductible is $2,000 for the Gold PPO plan."
    result = redact_pii(text)
    assert "$2,000" not in result, (
        "expected the current over-redaction behavior; if this now fails, "
        "the pattern was changed to be context-aware — update GOVERNANCE.md's "
        "documented limitation accordingly rather than just fixing this test"
    )
    assert "[AMOUNT_REDACTED]" in result
    print("PASS: test_known_limitation_overredacts_non_phi_dollar_amounts (documents over-redaction, not a bug)")


def test_empty_and_no_phi_text_unchanged():
    """Edge cases: empty string and text with no PHI at all should pass
    through unchanged, not error or over-redact."""
    assert redact_pii("") == ""
    no_phi = "The Gold PPO plan covers preventive care visits at no cost."
    assert redact_pii(no_phi) == no_phi
    print("PASS: test_empty_and_no_phi_text_unchanged")


if __name__ == "__main__":
    test_redacts_full_phi_sentence()
    test_redacts_claim_id_in_question()
    test_known_limitation_overredacts_non_phi_dollar_amounts()
    test_empty_and_no_phi_text_unchanged()
    print("\nAll redact_pii unit tests passed.")


def contains_identifying_pii(text: str) -> bool:
    """Day 25 Step 5 fix: narrower than redact_pii() — checks ONLY for
    identifying information (member IDs, claim IDs, member names), not
    dollar amounts. A dollar amount alone (e.g. a plan's premium) is not
    identifying information and should not trip a leakage check; only an
    identifier ties data to a specific individual. Used by
    guardrails_config.py's output guardrail, which needs to distinguish
    "this answer leaked who someone is" from "this answer mentions money" —
    a distinction the full redact_pii() (correctly conservative for log
    redaction) does not make.
    """
    if not text:
        return False
    return bool(
        MEMBER_ID_PATTERN.search(text)
        or CLAIM_ID_PATTERN.search(text)
        or MEMBER_NAME_PATTERN.search(text)
        or KNOWN_NAMES_PATTERN.search(text)
    )
