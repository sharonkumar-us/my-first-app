# Streaming Notes — Day 18

Design notes for the SSE-based streaming chat pipeline: how it works, what
decisions were made and why, and how the frontend and backend handle failure
modes.

## Architecture at a glance

```
User types → Streamlit frontend (app.py)
              │
              │  POST /chat/stream    (requests, stream=True)
              ▼
        FastAPI backend (coverage-chatbot-api/main.py)
              │
              │  1. retrieve() — classify + SQL/vector lookup   (~10-20s, blocking)
              │  2. build messages with PRODUCTION_SYSTEM_PROMPT
              │  3. stream_client.chat.completions.create(stream=True)
              │
              │  yields SSE events:
              │     data: {"type": "token", "text": "..."}\n\n
              │     data: {"type": "done", "session_id": "..."}\n\n
              │     data: {"type": "error", "detail": "..."}\n\n
              ▼
     Ollama running qwen2.5-coder:7b (localhost:11434)
```

Retrieval is synchronous and blocking. Only the LLM generation streams. This
means the client sees ~15 seconds of silence, then a fast token stream.

## Wire format: JSON-in-SSE

Plain SSE would emit `data: The\n\n` per token. Instead, every event carries a
JSON envelope with a `type` field so the client can distinguish token events
from stream end from an error mid-flight. Three event types:

| Type | Payload | Meaning |
|---|---|---|
| `token` | `{"type": "token", "text": "..."}` | One chunk of assistant text, append to the visible reply |
| `done` | `{"type": "done", "session_id": "..."}` | Stream ended cleanly; client can finalize UI |
| `error` | `{"type": "error", "detail": "..."}` | Backend hit a mid-stream failure; stream will close after |

The `session_id` echoed in `done` lets a first-turn client capture its id
without a separate `/history` roundtrip.

The JSON envelope also means the string "done" arriving as a legitimate token
(e.g. "The claim is done processing") does not get confused with a stream-end
signal. Without envelopes, either the client would need a sentinel token or
the backend would need to escape strings — both worse than adding structure.

## Two-terminal test

The endpoint was verified end-to-end with `curl -N`. The `-N` flag disables
curl's output buffering so tokens visibly appear one at a time rather than
after the whole response arrives.

```bash
curl -N -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"member_id":"M1001","message":"What is the status of claim C1001?"}'
```

Observed shape:

```
data: {"type":"token","text":"The"}

data: {"type":"token","text":" status"}

data: {"type":"token","text":" of"}

...

data: {"type":"done","session_id":"c0e7a09b-..."}
```

Retrieval + prompt build ran for ~15s of silence, then a steady stream of
tokens, then a clean `done`. The `POST /chat` endpoint (non-streaming, single
JSON blob) continues to work unchanged, so Day 16's verification still passes.

## Frontend UX — pre-first-token gap

The 15-second retrieval gap is the biggest UX risk: without a signal that
work is happening, the user assumes the tab froze and refreshes (which starts
a new session and cancels the request).

The Streamlit client covers this with `st.spinner("Looking it up in your plan
records...")` around the FIRST-token fetch. Design detail worth calling out:
the first token is pulled *inside* the spinner. This keeps the spinner
animating through the whole retrieval phase, and exits it as soon as any real
content arrives. Subsequent tokens update an `st.empty()` placeholder that
holds the accumulating reply, with a "▌" cursor appended until the stream
ends. When `done` arrives, the cursor is stripped and the message is added to
`st.session_state.messages` for the next rerun.

Sequence:

1. User submits — `st.chat_input` returns
2. User turn appended to history and rendered
3. `st.chat_message("assistant")` container opens
4. `st.empty()` placeholder created
5. `st.spinner` starts
6. `stream_from_backend(message)` opens the SSE connection
7. First token pulled → spinner exits, placeholder now holds first token + ▌
8. Rest of tokens loop → placeholder updates on each one
9. `done` event → cursor stripped, final text rendered
10. Full reply appended to `st.session_state.messages`

## Failure modes and handling

Each failure mode has a distinct user-facing message because remediation
differs. The client catches four exception classes in the streaming loop:

### `requests.exceptions.Timeout`

Timeout is set to 120 seconds (`CHAT_TIMEOUT_SECONDS`). If the backend takes
longer, the client shows:

> The backend took too long to respond. Please try again — if this keeps happening, contact Member Services at 1-800-555-0100.

Remediation is user-actionable (retry) with a fallback to a human.

### `requests.exceptions.ConnectionError`

Backend unreachable (uvicorn died, wrong port, etc.). The message points at
the operator problem:

> I can't reach the coverage service right now. Please make sure the backend is running, then try again.

### Backend-emitted `error` SSE event

The backend caught an exception mid-stream (Ollama choked, prompt too long,
etc.) and sent `{"type": "error", "detail": "..."}` before closing. Client
raises `RuntimeError` from the SSE parser and the exception handler:

- If partial tokens had already arrived, the placeholder shows them plus an
  italicized error note in parentheses — the visible partial reply is worth
  preserving because it may be what the user actually needed.
- If nothing had arrived yet, just shows the error text.

Backend side: whatever tokens accumulated before the failure are still
appended to the session transcript as an assistant turn, tagged
`[stream interrupted]`. Partial replies remain visible in `/history` for
diagnosis rather than vanishing.

### Catch-all `Exception`

Anything else (malformed SSE, unparseable JSON, unexpected HTTP status). The
client shows a generic message and surfaces the underlying error text in an
`st.error` box above the reply so it's visible during development without
leaking implementation detail into the chat bubble itself.

> Something went wrong on my end. Please try again.

## What was deliberately not built

**True cancellation.** If the user closes the tab mid-stream, the backend
keeps generating until it finishes. This is a client-side reload behavior
rather than an API-level cancellation. FastAPI can detect a closed
connection via `await request.is_disconnected()` but the current endpoint is
synchronous, and rewriting it as async for a rare edge case did not seem
worth the complexity today.

**Retry on failure.** The client shows an error and stops. No exponential
backoff, no automatic retry. A user pressing "try again" is cheap; a
backend hitting the same error on retry is worth surfacing rather than
hiding.

**Backend timeout inside the LLM call.** Ollama has no first-class request
timeout for streaming, so a stuck model would freeze the endpoint until
uvicorn's worker timeout (default 60s in workers, unlimited in dev). Manual
mitigation for now: reload uvicorn, kill the Ollama process. Production
would want a wall-clock guard around the streaming loop.

**Streamed retrieval progress.** Even during the 15-second retrieval phase,
the backend could send SSE events reporting "classifying...", "querying
SQL...", "matching policy chunks...". Nice to have, not built. The spinner
copy is a static placeholder for now.
