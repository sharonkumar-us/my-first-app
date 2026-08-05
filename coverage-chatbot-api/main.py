"""
Coverage Chatbot API — backend service.

Day 3: FastAPI skeleton + /health.
Day 16 Step 1: POST /chat endpoint. Later steps wire in retrieval, orchestration,
               session history, and error handling.

Run from the project root (NOT from backend/), so the Day 10-13 modules resolve:

    uvicorn backend.main:app --reload
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Iterator, Literal
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from openai import OpenAI
from pydantic import BaseModel, Field

# Day 10-11 pipeline: retrieve context + generate grounded answer.
# Imports at module load-time cost ~seconds (embedding model, chroma client)
# but avoid per-request warmup latency. Uvicorn's --reload will retrigger this
# whenever we edit; fine for dev, we'll suppress it later if needed.
from rag_chatbot import PRODUCTION_SYSTEM_PROMPT, retrieve_and_answer
from retrieval_engine import retrieve

load_dotenv()

# Local Ollama client, same config as the rest of the project. We need our
# own client here (rather than reusing rag_chatbot's) because the streaming
# code path needs to call chat.completions.create with stream=True and iterate
# the SSE-shaped chunks — the Day 11 generate_answer() collects the full
# reply before returning.
stream_client = OpenAI(
    base_url=os.environ["OLLAMA_BASE_URL"],
    api_key=os.environ["OLLAMA_API_KEY"],
)
GENERATION_MODEL = "qwen2.5-coder:7b"

# Log to stderr at INFO level. Uvicorn's default log config picks this up
# and interleaves our lines with its own access log, so timing and errors
# appear right next to the corresponding HTTP request line.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
log = logging.getLogger("chatbot")

app = FastAPI(title="Coverage Chatbot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Session store
#
# In-memory dict, keyed by session_id. Sessions disappear on process restart —
# fine for the exercise and for the objectives' "test a 3-message session"
# scope. Persistence (e.g. SQLite) would be a future upgrade.
# ---------------------------------------------------------------------------

class ChatTurn(BaseModel):
    """One message in a session's transcript. Kept minimal for now."""
    role: Literal["user", "assistant"]
    content: str
    timestamp: str  # ISO-8601


# session_id -> list of ChatTurn (oldest first)
SESSIONS: dict[str, list[ChatTurn]] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    """POST /chat body. session_id is optional — the server generates one if
    the client did not supply it, so a first-turn client does not have to."""
    session_id: str | None = Field(
        default=None,
        description="Provide to continue an existing session; omit to start a new one.",
    )
    member_id: str = Field(
        ...,
        description="The member this chat is on behalf of. Used later for scoping.",
        min_length=1,
    )
    message: str = Field(..., min_length=1, description="The member's message.")


class ChatResponse(BaseModel):
    session_id: str
    member_id: str
    answer: str
    # Room to grow in Step 2 — retrieval classification, tool calls, etc.


# ---------------------------------------------------------------------------
# Orchestration stub — Step 2 wires this to the real retrieve + generate flow
# ---------------------------------------------------------------------------

def orchestrate(session_id: str, member_id: str, message: str) -> str:
    """Return the assistant reply from the Day 11 grounded pipeline.

    retrieve_and_answer() runs classify -> retrieve -> generate with the Day 12
    production system prompt. Returns a dict with question/classification/answer;
    we hand the answer back to the client. session_id and member_id are not yet
    threaded into retrieval — that's Day 17+ personalization work.
    """
    result = retrieve_and_answer(message)
    return result["answer"]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    # Resolve or create the session.
    session_id = req.session_id or str(uuid4())
    turns = SESSIONS.setdefault(session_id, [])

    # Record the user turn before generating, so a failure downstream still
    # leaves the transcript honest about what came in.
    turns.append(ChatTurn(role="user", content=req.message, timestamp=_now()))

    # Time the orchestration call so slow retrieval / slow LLM calls surface
    # in the log rather than hiding as "the server feels laggy today."
    start = time.perf_counter()
    try:
        answer = orchestrate(session_id, req.member_id, req.message)
    except Exception as e:
        elapsed_ms = (time.perf_counter() - start) * 1000
        # Log the full traceback for diagnosis, but do NOT include the
        # internal error text in the client-facing 500.
        log.exception(
            "chat orchestration failed after %.0fms — session=%s member=%s: %s",
            elapsed_ms, session_id, req.member_id, e,
        )
        raise HTTPException(
            status_code=500,
            detail="Internal error generating reply. Please try again.",
        ) from e
    elapsed_ms = (time.perf_counter() - start) * 1000
    log.info(
        "chat ok session=%s member=%s elapsed_ms=%.0f",
        session_id, req.member_id, elapsed_ms,
    )

    turns.append(ChatTurn(role="assistant", content=answer, timestamp=_now()))

    return ChatResponse(session_id=session_id, member_id=req.member_id, answer=answer)


class HistoryResponse(BaseModel):
    session_id: str
    turns: list[ChatTurn]


@app.get("/history/{session_id}", response_model=HistoryResponse)
def history(session_id: str) -> HistoryResponse:
    """Return the stored transcript for a session, oldest turn first.

    404 when the session is unknown — an empty list would be ambiguous (was
    the session real but empty? or was the id wrong?), so we prefer the
    explicit not-found response.
    """
    turns = SESSIONS.get(session_id)
    if turns is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return HistoryResponse(session_id=session_id, turns=turns)


# ---------------------------------------------------------------------------
# Streaming chat endpoint (Day 18)
#
# Wire-format is Server-Sent Events (SSE): each server-emitted event is a
# newline-terminated block starting with "data: ". Clients parse this by
# reading line-by-line, ignoring blank lines, and stripping the "data: "
# prefix. Every event we emit has this shape:
#
#   data: {"type": "token" | "done" | "error", ...}\n\n
#
# The JSON envelope means the client can distinguish text tokens from a
# clean stream-end from a mid-stream error without reinventing framing.
# Token events carry {"type": "token", "text": "..."}; end-of-stream is
# {"type": "done", "session_id": "..."}; a failure is {"type": "error",
# "detail": "..."} and we then close the stream.
# ---------------------------------------------------------------------------

def _sse(payload: dict) -> str:
    """Format a Python dict as a single SSE event string."""
    return f"data: {json.dumps(payload)}\n\n"


def _generate_stream(
    session_id: str,
    member_id: str,
    message: str,
    turns: list[ChatTurn],
) -> Iterator[str]:
    """Do retrieval synchronously, then stream generation tokens as SSE events.

    Retrieval + prompt-build happens once, up front, before any tokens are
    sent — so the client sees ~10-20s of silence, then a fast stream. Only
    the LLM generation step actually streams. This matches how the Day 11
    pipeline is shaped and keeps this endpoint's semantics identical to the
    non-streaming /chat, minus the wait-for-full-reply latency.
    """
    start = time.perf_counter()
    accumulated = []  # tokens collected here so we can persist the full reply at end

    try:
        # Step A: retrieval. Same code path as /chat, no streaming yet.
        retrieval_result = retrieve(message)
        context = retrieval_result["merged_context"]

        # Step B: build the same messages shape Day 11's generate_answer uses.
        user_content = f"Context: {context}\n\nQuestion: {message}"
        messages = [
            {"role": "system", "content": PRODUCTION_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

        # Step C: streaming completion. stream=True flips OpenAI SDK into
        # incremental-chunks mode; each chunk delta may contain a text token
        # (or nothing, if it's a metadata chunk).
        completion = stream_client.chat.completions.create(
            model=GENERATION_MODEL,
            messages=messages,
            stream=True,
        )

        for chunk in completion:
            token = chunk.choices[0].delta.content
            if not token:
                continue
            accumulated.append(token)
            yield _sse({"type": "token", "text": token})

        # Step D: clean end. Client sees "done" and can finalize its UI.
        full_answer = "".join(accumulated)
        turns.append(ChatTurn(role="assistant", content=full_answer, timestamp=_now()))
        elapsed_ms = (time.perf_counter() - start) * 1000
        log.info(
            "chat/stream ok session=%s member=%s elapsed_ms=%.0f tokens=%d",
            session_id, member_id, elapsed_ms, len(accumulated),
        )
        yield _sse({"type": "done", "session_id": session_id})

    except Exception as e:
        # Persist whatever we got before the failure — a partial reply is
        # still evidence of what happened, and losing it makes debugging
        # harder. Same "log full traceback, tell the client something
        # generic" pattern as /chat.
        elapsed_ms = (time.perf_counter() - start) * 1000
        log.exception(
            "chat/stream failed after %.0fms — session=%s member=%s: %s",
            elapsed_ms, session_id, member_id, e,
        )
        if accumulated:
            partial = "".join(accumulated) + "\n\n[stream interrupted]"
            turns.append(ChatTurn(role="assistant", content=partial, timestamp=_now()))
        yield _sse({
            "type": "error",
            "detail": "Stream interrupted. Please try again.",
        })


@app.post("/chat/stream")
def chat_stream(req: ChatRequest) -> StreamingResponse:
    """Streaming counterpart to /chat.

    Same request body as /chat. Response is text/event-stream — a sequence of
    SSE events. The client should append token events to the visible reply
    and treat a done event as end-of-turn. session_id is echoed in the done
    event so a first-turn client can capture it without a separate request.
    """
    session_id = req.session_id or str(uuid4())
    turns = SESSIONS.setdefault(session_id, [])

    # Record the user turn before generating, same discipline as /chat: if
    # the stream fails mid-flight, the transcript still shows what came in.
    turns.append(ChatTurn(role="user", content=req.message, timestamp=_now()))

    return StreamingResponse(
        _generate_stream(session_id, req.member_id, req.message, turns),
        media_type="text/event-stream",
    )
