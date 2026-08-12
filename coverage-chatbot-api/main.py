"""
Coverage Chatbot API — backend service.

Day 3: FastAPI skeleton + /health.
Day 16 Step 1: POST /chat endpoint. Later steps wire in retrieval, orchestration,
               session history, and error handling.
Day 20 Step 1: SQLite-backed conversations table (persisted history), alongside
               the existing in-memory SESSIONS dict from Day 16.
Day 20 Step 2: Every /chat call now persists both the user message and the
               assistant reply to the conversations table.
Day 20 Step 3: /chat AND /chat/stream both load history for the session_id and
               infer the plan_id under discussion, threading both into the RAG
               pipeline so multi-turn conversations remember which plan is
               being asked about. /chat/stream now also persists its turns to
               the conversations table (previously only the in-memory
               SESSIONS dict).
Day 20 Step 4: History loading now counts tokens (tiktoken) and summarizes the
               oldest half of the conversation with one LLM call once the
               total exceeds ~2000 tokens, replacing those turns with the
               summary. This supersedes Step 3's flat "last 10 turns" cap —
               the full history is loaded and token-budgeted instead. Plan
               inference (_infer_plan_id) runs on the FULL raw history before
               summarization, so a plan mention folded into a summary can't
               silently break plan memory.

Run from the project root (NOT from backend/), so the Day 10-13 modules resolve:

    uvicorn backend.main:app --reload
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import time
from datetime import datetime, timezone
from typing import Iterator, Literal
from uuid import uuid4

import tiktoken
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from openai import OpenAI
from pydantic import BaseModel, Field

from rag_chatbot import PRODUCTION_SYSTEM_PROMPT, retrieve_and_answer
from retrieval_engine import retrieve
from tool_calling_chatbot import get_claim_status, get_plan_details, build_card_from_tool
from redact_pii import redact_pii
from token_utils import count_tokens

load_dotenv()

stream_client = OpenAI(
    base_url=os.environ["OLLAMA_BASE_URL"],
    api_key=os.environ["OLLAMA_API_KEY"],
)
GENERATION_MODEL = "qwen2.5-coder:7b"

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
# Day 20 — persisted conversation history (SQLite) + token-budgeted memory
#
# Shares coverage.db with the plans/claims tables (same DB connection pattern
# as tool_calling_chatbot.py's _plan_row()/get_claim_status()) rather than a
# separate file. Table is created at import time so it always exists once the
# backend starts, with no separate setup script to remember or forget.
# ---------------------------------------------------------------------------

from pathlib import Path

DB_PATH = str(Path(__file__).resolve().parent.parent / "coverage.db")
TOKEN_BUDGET = 2000  # summarize oldest half once history exceeds this
TOKEN_ENCODING = tiktoken.get_encoding("cl100k_base")


def _init_conversations_table() -> None:
    """Create the conversations table if it doesn't already exist.

    Columns match the portal's Day 20 Step 1 spec exactly: session_id, role,
    content, timestamp. An auto-incrementing id is added as the primary key
    purely for row identity — it is not part of the portal's required schema
    and downstream code should not rely on it.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


_init_conversations_table()


def _init_token_usage_table() -> None:
    """Create the token_usage table if it doesn't already exist.

    Day 26 Step 2: one row per /chat request, logging token counts and an
    ILLUSTRATIVE estimated cost. This project's LLM calls run through local
    Ollama (see OLLAMA_BASE_URL) and cost $0 in reality -- there is no real
    "provider rate" to log. estimated_cost here uses OpenAI's published
    gpt-4o-mini pricing ($0.15/1M input tokens, $0.60/1M output tokens, late
    2025 rates) purely to demonstrate the cost-logging mechanism a
    cloud-hosted deployment would need.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS token_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            input_tokens INTEGER NOT NULL,
            output_tokens INTEGER NOT NULL,
            estimated_cost REAL NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


_init_token_usage_table()

# Illustrative only -- see _init_token_usage_table() docstring. Actual
# inference cost for this project is $0 (local Ollama).
ILLUSTRATIVE_INPUT_RATE_PER_TOKEN = 0.15 / 1_000_000
ILLUSTRATIVE_OUTPUT_RATE_PER_TOKEN = 0.60 / 1_000_000


def _log_token_usage(session_id: str, input_tokens: int, output_tokens: int) -> float:
    """Log one request's token usage and return the illustrative estimated
    cost (also stored in the row) so callers can log it alongside other
    per-request metrics without a second DB read."""
    estimated_cost = (
        input_tokens * ILLUSTRATIVE_INPUT_RATE_PER_TOKEN
        + output_tokens * ILLUSTRATIVE_OUTPUT_RATE_PER_TOKEN
    )
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO token_usage (session_id, timestamp, input_tokens, output_tokens, estimated_cost) "
        "VALUES (?, ?, ?, ?, ?)",
        (session_id, _now(), input_tokens, output_tokens, estimated_cost),
    )
    conn.commit()
    conn.close()
    return estimated_cost


def _save_turn(session_id: str, role: str, content: str, timestamp: str) -> None:
    """Persist one turn (user or assistant) to the conversations table.

    Day 20 Step 2: called once per user message and once per assistant reply
    on every /chat call. Day 20 Step 3: also called by /chat/stream, so both
    response paths share the same persisted memory. The Day 16 in-memory
    SESSIONS dict is still kept alongside this for now since
    /history/{session_id} reads from it.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO conversations (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
        (session_id, role, content, timestamp),
    )
    conn.commit()
    conn.close()


def _load_raw_history(session_id: str) -> list[dict]:
    """Load the FULL turn history for a session, oldest first, as plain
    {"role": ..., "content": ...} dicts.

    Called BEFORE the current turn's user message is saved, so it never
    includes the message currently being answered — only genuinely prior
    turns.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        "SELECT role, content FROM conversations WHERE session_id = ? ORDER BY id ASC",
        (session_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return [{"role": row["role"], "content": row["content"]} for row in rows]


def _count_tokens(history: list[dict]) -> int:
    """Count total tokens across a history list's content, via tiktoken.

    Approximate — does not account for message-boundary overhead the way the
    OpenAI cookbook's per-model formula does, but is more than accurate enough
    for a budget threshold check like this one.
    """
    return sum(len(TOKEN_ENCODING.encode(turn["content"])) for turn in history)


def _summarize_history(turns_to_summarize: list[dict]) -> dict:
    """Summarize a list of turns into a single condensed turn via one LLM call.

    Returns a single {"role": "user", "content": ...} turn — kept as a "user"
    role (rather than "system") so it reads naturally as background context
    rather than confusing the model about whose turn comes next. Prefixed
    clearly as a summary so the model doesn't mistake it for something the
    member just said.
    """
    transcript = "\n".join(f"{t['role']}: {t['content']}" for t in turns_to_summarize)
    prompt = f"""Summarize the following conversation between a healthcare coverage
chatbot and a member, in 2-4 sentences. Preserve any plan names, claim IDs, or
specific facts (deductibles, copays, claim status) that were discussed —
these matter for later turns. Do not add information that wasn't in the
conversation.

Conversation:
{transcript}

Summary:"""
    response = stream_client.chat.completions.create(
        model=GENERATION_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    summary_text = response.choices[0].message.content.strip()
    return {"role": "user", "content": f"[Earlier conversation summary]: {summary_text}"}


def _load_history(session_id: str) -> tuple[list[dict], list[dict], int, int]:
    """Load history for a session, summarizing the oldest half if the total
    exceeds TOKEN_BUDGET tokens.

    Returns a 4-tuple:
        - raw_history:        the FULL unsummarized history, for plan inference
        - prompt_history:      the (possibly summarized) history to inject into
                                the chat prompt
        - tokens_before:       token count of raw_history
        - tokens_after:        token count of prompt_history (== tokens_before
                                if no summarization occurred)

    Plan inference (_infer_plan_id) must run on raw_history, not
    prompt_history — a plan mention could land in the summarized (dropped)
    half, and we don't want plan memory to depend on the summary happening
    to preserve it.
    """
    raw_history = _load_raw_history(session_id)
    tokens_before = _count_tokens(raw_history)

    if tokens_before <= TOKEN_BUDGET or len(raw_history) < 2:
        return raw_history, raw_history, tokens_before, tokens_before

    midpoint = len(raw_history) // 2
    oldest_half = raw_history[:midpoint]
    newest_half = raw_history[midpoint:]

    summary_turn = _summarize_history(oldest_half)
    prompt_history = [summary_turn] + newest_half
    tokens_after = _count_tokens(prompt_history)

    return raw_history, prompt_history, tokens_before, tokens_after


# Plan-name keywords shared between plan inference (Step 3) and card building
# (Day 19's _try_build_cards). Kept as one constant so both stay in sync.
PLAN_KEYWORDS = {
    "gold": ("P101", "Gold PPO"),
    "silver": ("P102", "Silver HMO"),
    "bronze": ("P103", "Bronze HMO"),
    "p101": ("P101", "Gold PPO"),
    "p102": ("P102", "Silver HMO"),
    "p103": ("P103", "Bronze HMO"),
}


def _infer_plan_id(message: str, history: list[dict]) -> tuple[str, str] | tuple[None, None]:
    """Infer which plan is under discussion: (plan_id, plan_name) or (None, None).

    Checks the CURRENT message first — if the member names a plan right now,
    that takes priority over anything said earlier. Otherwise scans history
    newest-first, so the most RECENTLY mentioned plan wins if the member
    talked about more than one plan earlier in the conversation.

    Day 20 Step 4: callers pass the FULL raw history here, never the
    summarized prompt_history — see _load_history()'s docstring.
    """
    msg_lower = message.lower()
    for keyword, (plan_id, plan_name) in PLAN_KEYWORDS.items():
        if keyword in msg_lower:
            return plan_id, plan_name

    for turn in reversed(history):
        turn_lower = turn["content"].lower()
        for keyword, (plan_id, plan_name) in PLAN_KEYWORDS.items():
            if keyword in turn_lower:
                return plan_id, plan_name

    return None, None


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    timestamp: str


SESSIONS: dict[str, list[ChatTurn]] = {}

# ---------------------------------------------------------------------------
# Day 26 Step 3 -- rate limiting per member
#
# Manual dict-based counter rather than the slowapi library: this project
# consistently prefers hand-rolled deterministic logic over adding external
# dependencies for something this simple (see Day 19's _try_build_cards,
# Day 20's _infer_plan_id) -- a sliding-window counter is a few lines and
# keeps the dependency surface smaller.
# ---------------------------------------------------------------------------

RATE_LIMIT_PER_MINUTE = 10
RATE_LIMIT_WINDOW_SECONDS = 60

# member_id -> list of request timestamps (epoch seconds) within the
# current window. Pruned lazily on each check rather than with a
# background task, since this project's traffic volume doesn't warrant one.
_rate_limit_state: dict[str, list[float]] = {}


def check_rate_limit(member_id: str) -> bool:
    """Return True if member_id is under the rate limit and the request
    should proceed (and is recorded); False if the limit is exceeded (and
    nothing is recorded, so a rejected request doesn't itself count against
    the member).
    """
    now = time.time()
    timestamps = _rate_limit_state.setdefault(member_id, [])

    # Prune timestamps outside the current sliding window.
    cutoff = now - RATE_LIMIT_WINDOW_SECONDS
    timestamps[:] = [t for t in timestamps if t > cutoff]

    if len(timestamps) >= RATE_LIMIT_PER_MINUTE:
        return False

    timestamps.append(now)
    return True


# ---------------------------------------------------------------------------
# Day 26 Step 4 -- exact-match cache for general (non-member-specific)
# questions
#
# Member-specific questions must NEVER be cached -- serving one member's
# claim status to a different member asking a similarly-phrased question
# would be a real data leak, not just a correctness bug. This project
# already has a claim-ID pattern (see _try_build_cards above) used to
# detect claim questions; reused here rather than duplicated, so both
# checks stay in sync if the ID format ever changes.
# ---------------------------------------------------------------------------

_CLAIM_ID_IN_MESSAGE = re.compile(r"\b(C\d{4})\b", re.IGNORECASE)
_MEMBER_ID_IN_MESSAGE = re.compile(r"\bM\d{4}\b", re.IGNORECASE)

_general_question_cache: dict[str, str] = {}


def _normalize_question(message: str) -> str:
    """Lowercase and collapse whitespace, so trivial formatting differences
    ("What'"'"'s the premium?" vs "what's the premium?  ") still hit the same
    cache entry. Deliberately simple exact-match normalization, not fuzzy
    matching -- the portal specifically asks for exact-match caching."""
    return " ".join(message.lower().split())


def is_cacheable(message: str) -> bool:
    """A question is cacheable ONLY if it contains no claim ID and no
    member ID -- i.e. it cannot be about a specific person'"'"'s specific data.
    A plan-terms question ("what'"'"'s the deductible on Gold PPO?") is
    cacheable since the answer is the same for anyone asking. A claim
    question is never cacheable, even if phrased generically, since the
    cache key would be shared across members who happen to ask the same
    way about DIFFERENT claims."""
    if _CLAIM_ID_IN_MESSAGE.search(message):
        return False
    if _MEMBER_ID_IN_MESSAGE.search(message):
        return False
    return True


def get_cached_answer(message: str) -> str | None:
    """Return the cached answer for this exact (normalized) question, or
    None on a cache miss. Does not check is_cacheable() itself -- callers
    must check before writing to the cache; a read against a
    never-written key is always a safe miss regardless."""
    return _general_question_cache.get(_normalize_question(message))


def set_cached_answer(message: str, answer: str) -> None:
    """Store an answer in the cache. Callers MUST check is_cacheable(message)
    before calling this -- this function does not re-check, to keep the
    caching decision made in exactly one place (the /chat endpoint) rather
    than duplicated here."""
    _general_question_cache[_normalize_question(message)] = answer


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ChatRequest(BaseModel):
    session_id: str | None = Field(default=None)
    member_id: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)


class ChatResponse(BaseModel):
    session_id: str
    member_id: str
    answer: str
    chunk_ids: list[str] = []
    cards: list[dict] = []


def _try_build_cards(message: str, plan_id: str | None = None) -> list[dict]:
    """Build response cards from direct DB lookups based on keywords in the
    message, or the inferred plan_id from earlier in the conversation. No
    LLM call — just pattern matching + direct queries.

    Day 20 Step 3: falls back to the inferred plan_id (from conversation
    memory) when the current message doesn't name a plan itself, so a
    follow-up like "what's the copay?" still surfaces a plan card if a plan
    was named earlier.
    """
    cards = []

    claim_match = re.search(r"\b(C\d{4})\b", message, re.IGNORECASE)
    if claim_match:
        raw = get_claim_status(claim_match.group(1).upper())
        card = build_card_from_tool("get_claim_status", raw)
        if card:
            cards.append(card.model_dump())

    msg_lower = message.lower()
    matched_plan_id = None
    for keyword, (kw_plan_id, _name) in PLAN_KEYWORDS.items():
        if keyword in msg_lower:
            matched_plan_id = kw_plan_id
            break
    if matched_plan_id is None:
        matched_plan_id = plan_id  # fall back to conversation memory

    if matched_plan_id:
        raw = get_plan_details(matched_plan_id)
        card = build_card_from_tool("get_plan_details", raw)
        if card:
            cards.append(card.model_dump())

    return cards


def orchestrate(session_id: str, member_id: str, message: str) -> dict:
    """Run the full pipeline: load memory (with token-budgeted summarization),
    infer plan context, retrieve + generate a grounded answer, build any
    structured cards.

    Day 20 Step 4: history loading now returns both raw and (possibly
    summarized) prompt history, plus token counts logged for Step 6.
    """
    raw_history, prompt_history, tokens_before, tokens_after = _load_history(session_id)
    plan_id, plan_name = _infer_plan_id(message, raw_history)

    if tokens_after < tokens_before:
        log.info(
            "history summarized session=%s tokens_before=%d tokens_after=%d",
            session_id, tokens_before, tokens_after,
        )
    else:
        log.info(
            "history loaded session=%s tokens=%d (no summarization)",
            session_id, tokens_before,
        )

    result = retrieve_and_answer(message, history=prompt_history, plan_hint=plan_name)
    cards = _try_build_cards(message, plan_id=plan_id)

    # Day 26 Step 1-2: count tokens on the actual prompt sent to the LLM
    # (retrieved context + the question) and the completion received, so
    # the logged input/output counts reflect what was really sent, not
    # just the member's raw message.
    input_tokens = count_tokens(result.get("context", "")) + count_tokens(message)
    output_tokens = count_tokens(result["answer"])

    return {
        "answer": result["answer"],
        "chunk_ids": result.get("chunk_ids", []),
        "cards": cards,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    if not check_rate_limit(req.member_id):
        raise HTTPException(
            status_code=429,
            detail=(
                f"Rate limit exceeded: max {RATE_LIMIT_PER_MINUTE} requests "
                f"per {RATE_LIMIT_WINDOW_SECONDS}s per member. Please try again shortly."
            ),
        )

    session_id = req.session_id or str(uuid4())
    turns = SESSIONS.setdefault(session_id, [])

    # Day 26 Step 4: exact-match cache check, before any retrieval/LLM work.
    # Cache hits skip orchestrate() entirely -- no tokens spent, no cost,
    # near-instant response. Only questions confirmed cacheable (no claim
    # or member ID present) are ever looked up here.
    cacheable = is_cacheable(req.message)
    if cacheable:
        cached = get_cached_answer(req.message)
        if cached is not None:
            log.info("chat cache HIT session=%s", session_id)
            user_timestamp = _now()
            turns.append(ChatTurn(role="user", content=req.message, timestamp=user_timestamp))
            _save_turn(session_id, "user", req.message, user_timestamp)
            assistant_timestamp = _now()
            turns.append(ChatTurn(role="assistant", content=cached, timestamp=assistant_timestamp))
            _save_turn(session_id, "assistant", cached, assistant_timestamp)
            return ChatResponse(
                session_id=session_id,
                member_id=req.member_id,
                answer=cached,
                chunk_ids=[],
                cards=[],
            )

    start = time.perf_counter()
    try:
        result = orchestrate(session_id, req.member_id, req.message)
        answer = result["answer"]
        chunk_ids = result["chunk_ids"]
        cards = result.get("cards", [])
        input_tokens = result.get("input_tokens", 0)
        output_tokens = result.get("output_tokens", 0)
    except Exception as e:
        elapsed_ms = (time.perf_counter() - start) * 1000
        log.exception(
            "chat orchestration failed after %.0fms — session=%s member=%s: %s",
            elapsed_ms, session_id, redact_pii(req.member_id), e,
        )
        raise HTTPException(
            status_code=500,
            detail="Internal error generating reply. Please try again.",
        ) from e
    elapsed_ms = (time.perf_counter() - start) * 1000
    estimated_cost = _log_token_usage(session_id, input_tokens, output_tokens)
    log.info(
        "chat ok session=%s member=%s elapsed_ms=%.0f chunks=%d cards=%d "
        "input_tokens=%d output_tokens=%d estimated_cost=$%.6f",
        session_id, redact_pii(req.member_id), elapsed_ms, len(chunk_ids), len(cards),
        input_tokens, output_tokens, estimated_cost,
    )

    # Save AFTER orchestrate() so history loaded inside it only ever sees
    # genuinely prior turns, never the message currently being answered.
    user_timestamp = _now()
    turns.append(ChatTurn(role="user", content=req.message, timestamp=user_timestamp))
    _save_turn(session_id, "user", req.message, user_timestamp)

    assistant_timestamp = _now()
    turns.append(ChatTurn(role="assistant", content=answer, timestamp=assistant_timestamp))
    _save_turn(session_id, "assistant", answer, assistant_timestamp)
    if cacheable:
        set_cached_answer(req.message, answer)


    return ChatResponse(
        session_id=session_id,
        member_id=req.member_id,
        answer=answer,
        chunk_ids=chunk_ids,
        cards=cards,
    )


class HistoryResponse(BaseModel):
    session_id: str
    turns: list[ChatTurn]


@app.get("/history/{session_id}", response_model=HistoryResponse)
def history(session_id: str) -> HistoryResponse:
    turns = SESSIONS.get(session_id)
    if turns is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return HistoryResponse(session_id=session_id, turns=turns)


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _generate_stream(
    session_id: str,
    member_id: str,
    message: str,
    turns: list[ChatTurn],
) -> Iterator[str]:
    """Do retrieval synchronously, then stream generation tokens as SSE events.

    Day 20 Step 3: loads conversation history and infers the plan under
    discussion, same as /chat's orchestrate(). Day 20 Step 4: history loading
    now applies the same token-budgeted summarization as /chat.
    """
    start = time.perf_counter()
    accumulated = []

    try:
        raw_history, prompt_history, tokens_before, tokens_after = _load_history(session_id)
        plan_id, plan_name = _infer_plan_id(message, raw_history)

        if tokens_after < tokens_before:
            log.info(
                "history summarized session=%s tokens_before=%d tokens_after=%d",
                session_id, tokens_before, tokens_after,
            )
        else:
            log.info(
                "history loaded session=%s tokens=%d (no summarization)",
                session_id, tokens_before,
            )

        retrieval_question = message
        if plan_name and plan_name.lower() not in message.lower():
            retrieval_question = f"{message} (regarding the {plan_name} plan)"

        retrieval_result = retrieve(retrieval_question)
        context = retrieval_result["merged_context"]

        plan_note = (
            f"(The member has been discussing the {plan_name} plan earlier in this "
            f"conversation — assume this plan unless the question names a different one.)\n"
            if plan_name else ""
        )
        user_content = f"Context: {context}\n\n{plan_note}Question: {message}"

        messages = [{"role": "system", "content": PRODUCTION_SYSTEM_PROMPT}]
        messages.extend(prompt_history)
        messages.append({"role": "user", "content": user_content})

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

        full_answer = "".join(accumulated)

        # Save AFTER generation, same discipline as /chat: history loaded
        # above reflects only genuinely prior turns.
        user_timestamp = _now()
        turns.append(ChatTurn(role="user", content=message, timestamp=user_timestamp))
        _save_turn(session_id, "user", message, user_timestamp)

        assistant_timestamp = _now()
        turns.append(ChatTurn(role="assistant", content=full_answer, timestamp=assistant_timestamp))
        _save_turn(session_id, "assistant", full_answer, assistant_timestamp)

        elapsed_ms = (time.perf_counter() - start) * 1000
        log.info(
            "chat/stream ok session=%s member=%s elapsed_ms=%.0f tokens=%d",
            session_id, redact_pii(member_id), elapsed_ms, len(accumulated),
        )
        yield _sse({"type": "done", "session_id": session_id})

    except Exception as e:
        elapsed_ms = (time.perf_counter() - start) * 1000
        log.exception(
            "chat/stream failed after %.0fms — session=%s member=%s: %s",
            elapsed_ms, session_id, redact_pii(member_id), e,
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

    Day 20 Step 3: the user turn is no longer saved here up front — it's
    saved inside _generate_stream() AFTER generation completes, same
    discipline as /chat, so history loaded during generation never includes
    the message currently being answered.
    """
    session_id = req.session_id or str(uuid4())
    turns = SESSIONS.setdefault(session_id, [])

    return StreamingResponse(
        _generate_stream(session_id, req.member_id, req.message, turns),
        media_type="text/event-stream",
    )
