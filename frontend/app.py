"""Streamlit chat client for the OmniCare assistant."""

from __future__ import annotations

import os
import uuid

import requests
import streamlit as st

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/")
CHAT_ENDPOINT = f"{BACKEND_URL}/api/v1/chat"
HEALTH_ENDPOINT = f"{BACKEND_URL}/api/v1/health"
REQUEST_TIMEOUT = 90

st.set_page_config(page_title="OmniCare Assistant", page_icon="🛡️", layout="centered")

STARTERS = [
    "Is water damage from a burst pipe covered?",
    "What's the status of claim CLM-8821?",
    "I need to file a claim for a burst pipe.",
]


def backend_is_up() -> bool:
    try:
        return requests.get(HEALTH_ENDPOINT, timeout=5).json().get("status") == "healthy"
    except requests.RequestException:
        return False


def ask(user_id: str, message: str) -> dict:
    response = requests.post(
        CHAT_ENDPOINT,
        json={"user_id": user_id, "message": message},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def render_turn(turn: dict) -> None:
    with st.chat_message(turn["role"]):
        st.markdown(turn["content"])

        if turn.get("sources"):
            st.caption("Policy sections cited: " + " · ".join(turn["sources"]))

        calls = turn.get("tool_calls") or []
        if calls:
            label = f"{len(calls)} tool call{'s' if len(calls) > 1 else ''}"
            with st.expander(label):
                for call in calls:
                    marker = "✅" if call.get("ok") else "⚠️"
                    st.markdown(f"{marker} **{call['tool']}**")
                    st.json({"args": call.get("args", {}), "result": call.get("result")})


# --- session -----------------------------------------------------------------

if "user_id" not in st.session_state:
    st.session_state.user_id = f"usr_{uuid.uuid4().hex[:6]}"
if "history" not in st.session_state:
    st.session_state.history = []
if "pending" not in st.session_state:
    st.session_state.pending = None

with st.sidebar:
    st.subheader("Session")
    st.session_state.user_id = st.text_input("User ID", st.session_state.user_id)
    st.caption("Conversation history is keyed on this id.")

    st.divider()
    st.subheader("Backend")
    if backend_is_up():
        st.success("Healthy")
    else:
        st.error("Unreachable")
        st.caption(f"Expected at {BACKEND_URL}")

    st.divider()
    if st.button("Clear conversation", use_container_width=True):
        st.session_state.history = []
        st.session_state.user_id = f"usr_{uuid.uuid4().hex[:6]}"
        st.rerun()

st.title("OmniCare Financial")
st.caption("Check your coverage, track a claim, or file a new one.")

if not st.session_state.history:
    st.markdown("Try one of these:")
    columns = st.columns(len(STARTERS))
    for column, starter in zip(columns, STARTERS):
        if column.button(starter, use_container_width=True):
            st.session_state.pending = starter
            st.rerun()

for turn in st.session_state.history:
    render_turn(turn)

typed = st.chat_input("Ask about your policy or a claim")
prompt = typed or st.session_state.pending
st.session_state.pending = None

if prompt:
    user_turn = {"role": "user", "content": prompt}
    st.session_state.history.append(user_turn)
    render_turn(user_turn)

    with st.chat_message("assistant"):
        with st.spinner("Checking your policy…"):
            try:
                payload = ask(st.session_state.user_id, prompt)
            except requests.HTTPError as exc:
                payload = None
                st.error(
                    f"The assistant returned {exc.response.status_code}. "
                    "Check the backend logs for details."
                )
            except requests.RequestException:
                payload = None
                st.error(
                    f"Could not reach the assistant at {BACKEND_URL}. "
                    "Start the backend and try again."
                )

    if payload:
        assistant_turn = {
            "role": "assistant",
            "content": payload.get("response", ""),
            "sources": payload.get("sources", []),
            "tool_calls": payload.get("tool_calls", []),
        }
        st.session_state.history.append(assistant_turn)
        st.rerun()
