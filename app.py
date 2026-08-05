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

# The Day 16 backend. Local dev only — no auth, plain HTTP. Change here (not
# in-line at call sites) if the backend moves.
BACKEND_URL = "http://localhost:8000"
CHAT_TIMEOUT_SECONDS = 120  # LLM turns run ~30-50s; give some headroom.

# Placeholder member id for now. Day 18 will add a real login / member picker;
# for Day 17 the objectives don't require it, so we hardcode a valid one.
DEFAULT_MEMBER_ID = "M1001"

PLANS_CSV = Path("data/plans.csv")


@st.cache_data
def load_plans() -> pd.DataFrame:
    """Load the plan list once per session. If the file is missing, return an
    empty dataframe so the app still renders — a broken plan selector should
    not take down the chat."""
    if not PLANS_CSV.exists():
        return pd.DataFrame(columns=["plan_id", "plan_name"])
    return pd.read_csv(PLANS_CSV)


def reset_conversation() -> None:
    """Wipe the message thread AND generate a fresh session_id.

    Clearing only messages would leave the backend still keyed to the old
    session under the old UUID, so new turns would land in a transcript the
    user thinks was reset. Both have to go together.
    """
    st.session_state.messages = []
    st.session_state.session_id = str(uuid4())

st.set_page_config(page_title="Coverage Chatbot", page_icon="💬")

st.title("Coverage Chatbot")
st.caption("Ask about your plan coverage, claims, or costs.")

# ---------------------------------------------------------------------------
# Sidebar — plan selector + New conversation
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("Session")

    plans_df = load_plans()
    if plans_df.empty:
        st.warning("No plans loaded — check `data/plans.csv`.")
        selected_plan = None
    else:
        # Show plan_name in the dropdown but store the plan_id — the id is
        # what the backend cares about, the name is what the human reads.
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

    # Debug context — small enough to keep visible, useful when a session
    # feels weird ("wait, am I on a new session_id or the old one?").
    st.caption(f"Session id: `{st.session_state.get('session_id', '(pending)')[:8]}...`")
    st.caption(f"Messages so far: {len(st.session_state.get('messages', []))}")


# ---------------------------------------------------------------------------
# Session state (main pane) — message history and session_id
#
# Streamlit reruns the whole script on every interaction, so anything that
# should persist across turns lives in st.session_state. session_id is
# generated once per browser tab; New Conversation in the sidebar rotates it.
# ---------------------------------------------------------------------------

if "messages" not in st.session_state:
    st.session_state.messages = []

# Generate the session_id ONCE per browser tab. Streamlit reruns the script
# top-to-bottom on every interaction, so uuid4() outside session_state would
# assign a fresh id on every keystroke — thus the guard. The backend uses
# this id to key the transcript store, so keeping it stable is what makes
# multi-turn sessions actually work.
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid4())


def post_to_backend(message: str) -> str:
    """Send one user message to the backend /chat endpoint and return the
    assistant reply. Raises on network / server error so the caller can
    surface it to the user."""
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
    """Yield tokens one at a time as they arrive from /chat/stream.

    Each SSE event from the backend is one of three shapes:
        {"type": "token", "text": "..."}   -> yield the text
        {"type": "done", "session_id": ""} -> stream ended cleanly
        {"type": "error", "detail": "..."} -> raise so the caller can surface it

    We use requests with stream=True so the connection stays open and iter_lines
    delivers lines as they arrive rather than after the whole response is done.
    """
    response = requests.post(
        f"{BACKEND_URL}/chat/stream",
        json={
            "session_id": st.session_state.session_id,
            "member_id": DEFAULT_MEMBER_ID,
            "message": message,
        },
        timeout=CHAT_TIMEOUT_SECONDS,
        stream=True,  # do not buffer the whole response
    )
    response.raise_for_status()

    for line in response.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data: "):
            # SSE blank lines are event separators; ignore. Also skip any
            # comment or malformed line to be safe.
            continue
        payload = json.loads(line[len("data: "):])
        event_type = payload.get("type")

        if event_type == "token":
            yield payload.get("text", "")
        elif event_type == "done":
            return
        elif event_type == "error":
            raise RuntimeError(payload.get("detail", "Unknown stream error"))


# ---------------------------------------------------------------------------
# Render the existing conversation thread
#
# Every rerun, replay all past turns. st.chat_message is a container that
# renders differently based on role ("user" vs "assistant"), giving each
# side an avatar and alignment for free.
# ---------------------------------------------------------------------------

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])


# ---------------------------------------------------------------------------
# Handle new input
#
# st.chat_input renders a bottom-anchored input box and returns the submitted
# string. Returns None when the user hasn't submitted anything on this rerun.
# ---------------------------------------------------------------------------

if user_message := st.chat_input("Type your question..."):
    # 1. Append the user turn to history and render it immediately.
    st.session_state.messages.append({"role": "user", "content": user_message})
    with st.chat_message("user"):
        st.markdown(user_message)

    # 2. Stream the assistant reply into a single placeholder that we update
    #    on every token. The spinner covers the ~15s pre-first-token gap
    #    while retrieval + prompt build happens; once tokens start arriving,
    #    we swap the spinner out for the accumulating text.
    with st.chat_message("assistant"):
        placeholder = st.empty()
        accumulated = ""
        try:
            with st.spinner("Looking it up in your plan records..."):
                token_iter = stream_from_backend(user_message)
                # Pull the FIRST token inside the spinner so the spinner
                # animates through retrieval. As soon as we get one token,
                # exit the spinner and switch to placeholder updates.
                first_token = next(token_iter, "")
                accumulated += first_token
                placeholder.markdown(accumulated + " ▌")

            # Now stream the rest of the tokens, updating the placeholder
            # each time. The "▌" cursor indicates streaming is in progress
            # and is stripped once the stream ends.
            for token in token_iter:
                accumulated += token
                placeholder.markdown(accumulated + " ▌")

            # Final render without the cursor.
            placeholder.markdown(accumulated)
            assistant_reply = accumulated

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
            # Backend-emitted stream error — safe to surface a short version.
            assistant_reply = f"The reply was interrupted: {e}"
            if accumulated:
                # Show whatever we got, then the error note.
                placeholder.markdown(accumulated + f"\n\n_({assistant_reply})_")
                assistant_reply = accumulated + f"\n\n[{assistant_reply}]"
            else:
                placeholder.markdown(assistant_reply)
        except Exception as e:
            assistant_reply = "Something went wrong on my end. Please try again."
            placeholder.markdown(assistant_reply)
            st.error(f"Backend error: {e}", icon="⚠️")

    # 3. Append to history so the reply persists on the next rerun.
    st.session_state.messages.append({"role": "assistant", "content": assistant_reply})
