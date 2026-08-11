# GOVERNANCE.md — AI Governance, PHI Handling & Guardrails

This document covers data sensitivity, PHI/PII exposure, bias risks, and
accountability for the coverage chatbot project, based on a direct audit of
this project's actual data sources (not generic boilerplate) as of Day 25.

All data in this project is synthetic training data (see Day 3 preflight
checklist: "keep it obviously fake — Jane Test, fictional plan numbers").
Nothing below refers to a real member or real insurance product. This
document treats the data AS IF it were real, since the governance practices
being exercised are the point of the mission — not the fictional stakes.

---

## Data sources used and their sensitivity

### coverage.db (SQLite)

- **plans table** — plan_id, plan_name, monthly_premium, annual_deductible,
  copay_pct, coverage_type, network_tier. NOT PHI/PII — this is product
  data, not tied to any individual.
- **claims table** — claim_id, member_id, plan_id, procedure, claim_amount,
  status, date_filed. **PHI-adjacent**: member_id ties a specific
  individual to specific medical procedures and dollar amounts. If this
  project ever ingested real data, this table alone would be enough to
  identify what medical services a specific person received and what they
  cost — squarely within HIPAA's definition of PHI.
- **conversations table** (Day 20) — session_id, role, content, timestamp.
  **Sensitivity is user-determined and unbounded**: content is raw member
  chat text. A member could type anything into it, including their own
  name, symptoms, or other identifying details never asked for. This table
  has no schema-level way to know in advance what sensitive data it might
  contain — redaction has to happen on the text itself, not on a known
  column.

### knowledge_base.jsonl (Day 6 chunking output, feeds the vector store)

Audited directly for this document. Two categories found:

- **Synthetic plan/policy text** — no PHI, describes plan terms and general
  processes.
- **A synthetic PHI example EMBEDDED IN RETRIEVABLE TEXT** — chunk
  `raw_text/claims_process.txt::chunk10` reads: "Member Jane Test (Member ID
  M1001) submitted a claim for an X-ray procedure billed at \$250 under the
  Gold PPO plan." This is fictional, but it demonstrates a real production
  risk: **if a real claims-process document were ingested for RAG the same
  way**, any PHI it contained (a real example claim, a real member's data
  used as a training example) would be embedded verbatim in the vector
  store and could be retrieved and surfaced in an answer or citation to ANY
  member asking a similar question — not just the member the data belonged
  to. This is a structural risk of RAG over unstructured documents, not a
  one-off content mistake, and needs a policy: source documents for
  ingestion must be scrubbed of real PHI before chunking, not after.

### Application logs (coverage-chatbot-api/main.py)

Audited directly. Current `log.info()` calls on every `/chat` request
already log **member_id in plaintext** (e.g. `chat ok session=... member=M1001
...`), alongside session_id, elapsed_ms, and result counts. Message and
answer TEXT are not currently logged — only the identifier. This is Day
25's actual redaction target (Step 3): member_id in logs is real, present,
unredacted PHI-adjacent data today, not a hypothetical risk.


---

## PHI/PII fields present

Direct inventory from the audit above:

| Field | Location | Type |
|---|---|---|
| member_id | claims table, /chat request body, application logs | Direct identifier |
| claim_id | claims table | Indirect identifier (links to member_id) |
| procedure | claims table, chunk10 in knowledge_base.jsonl | Medical information (PHI when tied to member_id) |
| claim_amount | claims table, chunk10 | Financial + medical information |
| Member name ("Jane Test") | chunk10 in knowledge_base.jsonl | Direct identifier — found embedded in unstructured retrievable text, not just structured data |
| session_id | conversations table, /chat request/response | Pseudonymous identifier — not PHI alone, but re-identifying if correlated with member_id (which it is, via the /chat request) |
| Free-text chat content | conversations table | Unbounded — could contain anything the member types, no schema constraint |

**Fields NOT present in this system:** SSN, date of birth, address, phone
number, email. If any of these were added in a future iteration (e.g. a
real enrollment flow), this table would need to be revisited before launch.

## Bias risks

- **Plan-tier assumptions in generated language.** Reviewing outputs from
  Days 21-24, the chatbot's phrasing sometimes implies a value judgment
  about plan tiers (e.g. describing Bronze HMO as offering "basic" coverage
  "at a lower cost" — Day 23's own test notes show this exact phrasing from
  Claude Desktop's response). This isn't factually wrong, but repeated
  framing of lower-cost tiers as categorically "basic" or lesser could
  read as steering members away from plans that are, for their actual
  needs, perfectly adequate — especially if a member on a lower-tier plan
  asks a coverage question and receives subtly more hedged or cautious
  language than a member on Gold PPO would for the equivalent question.
  Not tested directly in this exercise; worth a structured A/B review of
  tone across plan tiers if this were headed to production.
- **Underlying data sparsity bias.** Per Day 6/9's documented findings
  (`knowledge_base_notes.md`), the knowledge base has zero exclusions-tagged
  chunks and Gold PPO content dominates the vector store relative to Silver
  and Bronze. This means retrieval-grounded answers are structurally more
  complete and confident for Gold PPO questions than for other plans — a
  data coverage gap that could look like a product bias even though it's
  actually a training-data sampling gap. Documented in this project since
  Day 9; repeated here because it is a governance-relevant risk, not just
  an accuracy one.
- **No fairness testing was performed in this project.** This is a gap:
  a production system should run comparable questions across plan tiers,
  demographics implied by claim data, and member phrasing styles, and check
  for disparities in answer helpfulness, hedging, or refusal rate. Not done
  here; noted as a required step before any production consideration (see
  Step 7 note below).

## Who's accountable for reviewing chatbot outputs

For this project (a solo training exercise), Sharon Kumar is the sole
author and reviewer of all chatbot outputs, prompts, and guardrail logic.

**For a real production deployment, this project's current setup would be
insufficient governance on its own.** A real system would need:

- A named accountable owner for the chatbot's clinical/coverage accuracy
  (not just its engineering) — likely a clinical or compliance
  stakeholder, not the engineering team alone.
- A defined escalation path for when the guardrails (Day 25) miss something
  — who gets notified, how fast, and what the rollback process is.
  This project has adversarial test logging (`adversarial_tests.md`) but no
  live monitoring or alerting; that gap is intentional for a training
  exercise but would be a blocker for production.
- Periodic re-review of the knowledge base for embedded PHI (per the
  chunk10 finding above) — not a one-time check.

---

## Production readiness note (Step 7)

**This project's governance, redaction, and guardrail work is a training
exercise and explicitly does NOT constitute a formal compliance review.**
Before any production use handling real PHI, this system would require, at
minimum:

- Legal/compliance sign-off on the redaction approach. `redact_pii.py`'s
  regex-based approach was a deliberate choice for this exercise's small,
  well-known PHI surface — a real system would need to evaluate whether
  regex alone (vs. a proper NER-based tool like Presidio) meets its actual
  compliance bar, especially for identifying information the system
  doesn't already know to look for (this project's fix for the "Jane Test"
  leak, documented in `adversarial_tests.md`, only worked because that
  name was already known from a direct audit — a real system would
  encounter unknown real names it has no hardcoded pattern for).
- A far larger adversarial test suite. This exercise ran 6 prompts across
  5 categories; a real red-team exercise would run hundreds of phrasing
  variations per category, and should be run by someone other than the
  system's own developer.
- Live monitoring and alerting for guardrail misses in production, not
  just point-in-time testing. `adversarial_tests.md` documents that this
  project's own guardrails had two genuine, fixable bugs found only through
  active testing (one over-blocking legitimate output, one under-catching
  a real leak) — a production system needs an ongoing detection mechanism
  for this class of drift, not a one-time test log.
- A defined accountable owner (see "Who's accountable" above) with
  authority to pause or roll back the chatbot if a guardrail failure is
  discovered live, separate from the engineering team that built it.
- Review of PHI embedded in source documents BEFORE ingestion into the
  knowledge base, not just redaction after the fact — see the
  `knowledge_base.jsonl` chunk10 finding above, which is a structural risk
  of RAG over unstructured documents, not something output-side guardrails
  alone can fully close.

This document and the accompanying `redact_pii.py`, `guardrails_config.py`,
and `adversarial_tests.md` represent a solid foundation for these
practices, not a substitute for them.
