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

from pathlib import Path
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

    # 2. Call the backend. The retrieval + generation loop takes tens of
    #    seconds, so we show a spinner inside the assistant bubble to make
    #    the wait feel intentional rather than broken.
    with st.chat_message("assistant"):
        with st.spinner("Looking it up in your plan records..."):
            try:
                assistant_reply = post_to_backend(user_message)
            except requests.exceptions.Timeout:
                assistant_reply = (
                    "The backend took too long to respond. Please try again — "
                    "if this keeps happening, contact Member Services at 1-800-555-0100."
                )
            except requests.exceptions.ConnectionError:
                assistant_reply = (
                    "I can't reach the coverage service right now. Please make "
                    "sure the backend is running, then try again."
                )
            except Exception as e:
                # Catch-all for HTTP 4xx/5xx and anything else. The specific
                # error text isn't safe to show a member, so we log-and-generic.
                assistant_reply = (
                    "Something went wrong on my end. Please try again."
                )
                st.error(f"Backend error: {e}", icon="⚠️")
        st.markdown(assistant_reply)

    # 3. Append to history so the reply persists on the next rerun.
    st.session_state.messages.append({"role": "assistant", "content": assistant_reply})
