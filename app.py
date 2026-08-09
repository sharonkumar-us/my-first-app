"""
Coverage Chatbot — Streamlit frontend.

Day 17 Step 2: minimal chat UI.
Day 17 Step 3: POST each turn to the Day 16 backend, keep the same session_id
               for the duration of the browser tab.

Run from the project root, with the FastAPI backend already running:

    # terminal 1:
    PYTHONPATH=. uvicorn main:app --reload --app-dir coverage-chatbot-api
    # terminal 2:
    streamlit run app.py
"""

import json
from pathlib import Path
from typing import Iterator
from uuid import uuid4

import pandas as pd
import requests
import streamlit as st

BACKEND_URL = "http://localhost:8000"
CHAT_TIMEOUT_SECONDS = 120

DEFAULT_MEMBER_ID = "M1001"

PLANS_CSV = Path("data/plans.csv")


@st.cache_data
def load_plans() -> pd.DataFrame:
    if not PLANS_CSV.exists():
        return pd.DataFrame(columns=["plan_id", "plan_name"])
    return pd.read_csv(PLANS_CSV)


def reset_conversation() -> None:
    st.session_state.messages = []
    st.session_state.session_id = str(uuid4())

st.set_page_config(page_title="Coverage Chatbot", page_icon="💬")

st.title("Coverage Chatbot")
st.caption("Ask about your plan coverage, claims, or costs.")

with st.sidebar:
    st.header("Session")

    plans_df = load_plans()
    if plans_df.empty:
        st.warning("No plans loaded — check `data/plans.csv`.")
        selected_plan = None
    else:
        plan_options = plans_df["plan_id"].tolist()
        selected_plan = st.selectbox(
            "Plan context",
            options=plan_options,
            format_func=lambda pid: plans_df.loc[plans_df["plan_id"] == pid, "plan_name"].iat[0],
            index=0,
            help="Selection is stored for future use. Not currently passed to the backend.",
        )
        st.session_state.selected_plan = selected_plan

    st.divider()

    if st.button("New conversation", use_container_width=True):
        reset_conversation()
        st.rerun()

    st.caption(f"Session id: `{st.session_state.get('session_id', '(pending)')[:8]}...`")
    st.caption(f"Messages so far: {len(st.session_state.get('messages', []))}")


if "messages" not in st.session_state:
    st.session_state.messages = []

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid4())


def post_to_backend(message: str) -> str:
    response = requests.post(
        f"{BACKEND_URL}/chat",
        json={
            "session_id": st.session_state.session_id,
            "member_id": DEFAULT_MEMBER_ID,
            "message": message,
        },
        timeout=CHAT_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()["answer"]


def stream_from_backend(message: str) -> Iterator[str]:
    response = requests.post(
        f"{BACKEND_URL}/chat/stream",
        json={
            "session_id": st.session_state.session_id,
            "member_id": DEFAULT_MEMBER_ID,
            "message": message,
        },
        timeout=CHAT_TIMEOUT_SECONDS,
        stream=True,
    )
    response.raise_for_status()

    for line in response.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data: "):
            continue
        payload = json.loads(line[len("data: "):])
        event_type = payload.get("type")

        if event_type == "token":
            yield payload.get("text", "")
        elif event_type == "done":
            return
        elif event_type == "error":
            raise RuntimeError(payload.get("detail", "Unknown stream error"))


def fetch_extras(message: str) -> dict:
    try:
        response = requests.post(
            f"{BACKEND_URL}/chat",
            json={
                "session_id": st.session_state.session_id,
                "member_id": DEFAULT_MEMBER_ID,
                "message": message,
            },
            timeout=CHAT_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
        return {
            "chunk_ids": data.get("chunk_ids", []),
            "cards": data.get("cards", []),
        }
    except Exception:
        return {"chunk_ids": [], "cards": []}


def render_citations(chunk_ids: list[str]) -> None:
    if not chunk_ids:
        return
    with st.expander(f"Policy sources ({len(chunk_ids)})", expanded=False):
        for i, chunk_id in enumerate(chunk_ids, 1):
            if "::" in chunk_id:
                source, position = chunk_id.split("::", 1)
                st.markdown(f"{i}. `{source}` — {position}")
            else:
                st.markdown(f"{i}. `{chunk_id}`")


def render_cards(cards: list[dict]) -> None:
    for card in cards:
        with st.container(border=True):
            if "claim_id" in card:
                st.markdown(f"**Claim {card['claim_id']}**")
                cols = st.columns(2)
                cols[0].metric("Status", card.get("status", "—"))
                if card.get("amount") is not None:
                    cols[1].metric("Amount", f"${card['amount']:,.0f}")
            elif "plan_name" in card:
                st.markdown(f"**{card['plan_name']}**")
                cols = st.columns(3)
                if card.get("deductible") is not None:
                    cols[0].metric("Deductible", f"${card['deductible']:,.0f}")
                if card.get("copay") is not None:
                    cols[1].metric("Copay", f"{card['copay']}%")
                if card.get("covered") is not None:
                    cols[2].metric("Covered", "Yes" if card["covered"] else "Unknown")


for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant":
            if msg.get("cards"):
                render_cards(msg["cards"])
            if msg.get("chunk_ids"):
                render_citations(msg["chunk_ids"])


if user_message := st.chat_input("Type your question..."):
    st.session_state.messages.append({"role": "user", "content": user_message})
    with st.chat_message("user"):
        st.markdown(user_message)

    with st.chat_message("assistant"):
        placeholder = st.empty()
        accumulated = ""
        try:
            with st.spinner("Looking it up in your plan records..."):
                token_iter = stream_from_backend(user_message)
                first_token = next(token_iter, "")
                accumulated += first_token
                placeholder.markdown(accumulated + " ▌")

            for token in token_iter:
                accumulated += token
                placeholder.markdown(accumulated + " ▌")

            placeholder.markdown(accumulated)
            assistant_reply = accumulated

            extras = fetch_extras(user_message)
            chunk_ids = extras["chunk_ids"]
            cards = extras["cards"]
            render_cards(cards)
            render_citations(chunk_ids)

        except requests.exceptions.Timeout:
            assistant_reply = (
                "The backend took too long to respond. Please try again — "
                "if this keeps happening, contact Member Services at 1-800-555-0100."
            )
            placeholder.markdown(assistant_reply)
        except requests.exceptions.ConnectionError:
            assistant_reply = (
                "I can't reach the coverage service right now. Please make "
                "sure the backend is running, then try again."
            )
            placeholder.markdown(assistant_reply)
        except RuntimeError as e:
            assistant_reply = f"The reply was interrupted: {e}"
            if accumulated:
                placeholder.markdown(accumulated + f"\n\n_({assistant_reply})_")
                assistant_reply = accumulated + f"\n\n[{assistant_reply}]"
            else:
                placeholder.markdown(assistant_reply)
        except Exception as e:
            assistant_reply = "Something went wrong on my end. Please try again."
            placeholder.markdown(assistant_reply)
            st.error(f"Backend error: {e}", icon="⚠️")

    st.session_state.messages.append({
        "role": "assistant",
        "content": assistant_reply,
        "chunk_ids": chunk_ids if "chunk_ids" in dir() else [],
        "cards": cards if "cards" in dir() else [],
    })
