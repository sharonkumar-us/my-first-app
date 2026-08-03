# Day 16 — Backend Chat Test

End-to-end test of the coverage chatbot backend, exercising all three
retrieval paths in a single session and verifying `/history` reflects the
full transcript.

**Endpoint under test:** `POST /chat`, `GET /history/{session_id}`, mounted
on FastAPI (`backend/main.py`) via `uvicorn backend.main:app --reload`.

**Pipeline in orchestration:** `retrieve_and_answer()` from `rag_chatbot.py`
— the Day 11 classify → retrieve → generate chain, running the Day 12
production system prompt on `qwen2.5-coder:7b` via Ollama.

**Session store:** in-memory `dict[str, list[ChatTurn]]` at module scope
(portal Step 3 explicitly permits in-memory or SQLite).

---

## Test procedure

Three sequential `POST /chat` requests with the same `session_id`, chosen to
exercise different retrieval paths, followed by a single `GET /history/{sid}`
to confirm the transcript was stored correctly. All requests via `curl` from
the shell.

| Message | Retrieval path exercised | Reason |
|---|---|---|
| 1 | Empty-context refusal | The information is not in any indexed data — should refuse honestly, not fabricate |
| 2 | Structured (SQL) lookup | Claim ID → `claims` table → status field |
| 3 | Unstructured (vector) lookup | Policy question → chunk retrieval → grounded answer |

Session id used: `cc8f8aa5-a9a1-4729-a945-467487dd4cf3`.

---

## Turn 1 — Empty-context refusal

**Request:**

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"member_id":"M1001","message":"Is my Silver plan renewing next month?"}'
```

**Response:**

```json
{
  "session_id": "cc8f8aa5-a9a1-4729-a945-467487dd4cf3",
  "member_id": "M1001",
  "answer": "I don't have that information in your plan records. Member Services can help at 1-800-555-0100."
}
```

Renewal information is not present in the coverage database or in the
policy-document knowledge base. The model refused honestly rather than
fabricating a renewal date — the Day 12 grounding prompt discipline held.

---

## Turn 2 — Structured (SQL) lookup

**Request:**

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SID\",\"member_id\":\"M1001\",\"message\":\"What is the status of claim C1001?\"}"
```

**Response:**

```json
{
  "session_id": "cc8f8aa5-a9a1-4729-a945-467487dd4cf3",
  "member_id": "M1001",
  "answer": "The status of claim C1001 is Pending.\n\nThis is coverage information based on your plan records, not medical or legal advice.\nFor questions about your care, please consult your doctor. To confirm benefits or file\nan appeal, contact Member Services at 1-800-555-0100."
}
```

The classifier routed this to the structured path, the LLM-generated SQL
correctly targeted `claims.claim_id`, and the returned `Pending` status was
relayed exactly. Same `session_id` returned as Turn 1, confirming
continuation rather than a fresh session. Full closing disclaimer emitted
verbatim.

Worth noting compared to the Day 13 baseline: no "you'll be notified by mail"
overreach on this run — the model stated only what the tool returned.

---

## Turn 3 — Unstructured (vector) lookup

**Request:**

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SID\",\"member_id\":\"M1001\",\"message\":\"What is the claims submission process?\"}"
```

**Response:**

```json
{
  "session_id": "cc8f8aa5-a9a1-4729-a945-467487dd4cf3",
  "member_id": "M1001",
  "answer": "To submit a claim, members must either use the online portal or mail a completed form. Each claim requires the member ID, plan ID, date of service, and procedure code. After submitting, claims are reviewed for completeness within 3 business days. Incomplete claims will be returned with an additional information request.\n\nThis is coverage information based on your plan records, not medical or legal advice.\nFor questions about your care, please consult your doctor. To confirm benefits or file\nan appeal, contact Member Services at 1-800-555-0100."
}
```

Classifier routed to unstructured; vector retrieval returned the correct
policy chunks from `raw_text/claims_process.txt`; the model summarized them
into a clean four-sentence procedural answer with no fabricated detail. The
member ID / plan ID / date / procedure code / 3 business days figures all
trace directly to the indexed source document. Full disclaimer emitted.

---

## GET /history verification

**Request:**

```bash
curl http://localhost:8000/history/cc8f8aa5-a9a1-4729-a945-467487dd4cf3
```

**Response (formatted):**

```json
{
  "session_id": "cc8f8aa5-a9a1-4729-a945-467487dd4cf3",
  "turns": [
    {"role": "user", "content": "Is my Silver plan renewing next month?",     "timestamp": "2026-08-02T17:53:53+00:00"},
    {"role": "assistant", "content": "I don't have that information...",       "timestamp": "2026-08-02T17:54:05+00:00"},
    {"role": "user", "content": "What is the status of claim C1001?",          "timestamp": "2026-08-02T20:30:20+00:00"},
    {"role": "assistant", "content": "The status of claim C1001 is Pending...", "timestamp": "2026-08-02T20:31:07+00:00"},
    {"role": "user", "content": "What is the claims submission process?",      "timestamp": "2026-08-03T06:19:27+00:00"},
    {"role": "assistant", "content": "To submit a claim, members must...",     "timestamp": "2026-08-03T06:20:15+00:00"}
  ]
}
```

All six turns present in insertion order, alternating user/assistant, each
with a UTC ISO-8601 timestamp. This is enough context for a frontend chat
UI to render the conversation with timestamps.

*Timestamp gap disclosure:* the three messages were sent across two separate
work sessions (paused hours between turns 2 and 3, and again between turns
4 and 5). Timestamps reflect actual wall-clock time. This does not affect
correctness — sessions have no TTL — but it is worth calling out so the
gaps are not read as latency.

---

## What was verified

- `POST /chat` runs the full Day 10 classify → retrieve → generate chain end-to-end over HTTP.
- Response includes a fresh `session_id` on first call and returns the same `session_id` on subsequent calls, confirming the module-level session dict is being read on continuation.
- All three retrieval paths (empty-context refusal, structured SQL lookup, unstructured vector lookup) reach the client with the correct behavior for their category.
- The closing disclaimer emits verbatim on every non-trivial answer (Turn 1's shorter refusal omits it, which is consistent with the Day 12 prompt's disclaimer rule being conditioned on substantive content).
- `GET /history/{session_id}` returns every stored turn in order, with role, content and ISO-8601 timestamps.
- `GET /history/{unknown_session_id}` returns a clean 404 with `{"detail": "Session not found"}` — tested separately in Step 4, still holds here.

## Known limitations (deferred to later days)

- **Session state is not passed into retrieval.** Each `/chat` call retrieves against only the current message, so multi-turn context (e.g. "and what about Bronze?" as a follow-up) is not resolved. The Day 16 orchestration docstring flags this as Day 17+ personalization work.
- **In-memory sessions vanish on process restart.** Uvicorn's `--reload` on file edit wipes the store. A SQLite session table is the obvious next step if any of this needs to survive a restart.
- **LLM latency is real.** Turns 2 and 3 each took roughly 30–50 seconds. No streaming yet — the response is delivered as a single JSON payload after the model finishes. Streaming is Day 11's `stream_test.py` pattern; folding it into `/chat` is a future refactor.
- **Retrieval failures still hide in some paths.** A separate first attempt at Turn 1 asked about the Gold PPO deductible and received the Day 12 "stripped-context" behavior — the model correctly refused because the SQL result came back label-stripped (`[{'annual_deductible': 2000}]`). The `retrieval_engine.py` structured-context formatting is still the highest-value open fix, unchanged from the Day 12 Q1 observation.
