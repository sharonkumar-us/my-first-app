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
import re
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

from rag_chatbot import PRODUCTION_SYSTEM_PROMPT, retrieve_and_answer
from retrieval_engine import retrieve
from tool_calling_chatbot import get_claim_status, get_plan_details, build_card_from_tool

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


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    timestamp: str


SESSIONS: dict[str, list[ChatTurn]] = {}


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


def _try_build_cards(message: str) -> list[dict]:
    """Build response cards from direct DB lookups based on keywords in the
    message. No LLM call — just pattern matching + direct queries."""
    cards = []

    claim_match = re.search(r"\b(C\d{4})\b", message, re.IGNORECASE)
    if claim_match:
        raw = get_claim_status(claim_match.group(1).upper())
        card = build_card_from_tool("get_claim_status", raw)
        if card:
            cards.append(card.model_dump())

    plan_map = {
        "gold": "P101", "silver": "P102", "bronze": "P103",
        "p101": "P101", "p102": "P102", "p103": "P103",
    }
    msg_lower = message.lower()
    for keyword, plan_id in plan_map.items():
        if keyword in msg_lower:
            raw = get_plan_details(plan_id)
            card = build_card_from_tool("get_plan_details", raw)
            if card:
                cards.append(card.model_dump())
            break

    return cards


def orchestrate(session_id: str, member_id: str, message: str) -> dict:
    result = retrieve_and_answer(message)
    cards = _try_build_cards(message)
    return {
        "answer": result["answer"],
        "chunk_ids": result.get("chunk_ids", []),
        "cards": cards,
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    session_id = req.session_id or str(uuid4())
    turns = SESSIONS.setdefault(session_id, [])
    turns.append(ChatTurn(role="user", content=req.message, timestamp=_now()))

    start = time.perf_counter()
    try:
        result = orchestrate(session_id, req.member_id, req.message)
        answer = result["answer"]
        chunk_ids = result["chunk_ids"]
        cards = result.get("cards", [])
    except Exception as e:
        elapsed_ms = (time.perf_counter() - start) * 1000
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
        "chat ok session=%s member=%s elapsed_ms=%.0f chunks=%d cards=%d",
        session_id, req.member_id, elapsed_ms, len(chunk_ids), len(cards),
    )

    turns.append(ChatTurn(role="assistant", content=answer, timestamp=_now()))

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
    start = time.perf_counter()
    accumulated = []

    try:
        retrieval_result = retrieve(message)
        context = retrieval_result["merged_context"]

        user_content = f"Context: {context}\n\nQuestion: {message}"
        messages = [
            {"role": "system", "content": PRODUCTION_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

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
        turns.append(ChatTurn(role="assistant", content=full_answer, timestamp=_now()))
        elapsed_ms = (time.perf_counter() - start) * 1000
        log.info(
            "chat/stream ok session=%s member=%s elapsed_ms=%.0f tokens=%d",
            session_id, member_id, elapsed_ms, len(accumulated),
        )
        yield _sse({"type": "done", "session_id": session_id})

    except Exception as e:
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
    session_id = req.session_id or str(uuid4())
    turns = SESSIONS.setdefault(session_id, [])
    turns.append(ChatTurn(role="user", content=req.message, timestamp=_now()))

    return StreamingResponse(
        _generate_stream(session_id, req.member_id, req.message, turns),
        media_type="text/event-stream",
    )
