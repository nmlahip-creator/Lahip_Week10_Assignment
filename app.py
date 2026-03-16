from datetime import datetime
import json
from pathlib import Path
import requests
import streamlit as st

st.set_page_config(page_title="My AI Chat", layout="wide")

st.title("My AI Chat")

BASE_DIR = Path(__file__).resolve().parent
CHATS_DIR = BASE_DIR / "chats"
CHATS_DIR.mkdir(exist_ok=True)

hf_token = st.secrets.get("HF_TOKEN", "").strip()
if not hf_token:
    st.error(
        "Missing Hugging Face token. Add HF_TOKEN to .streamlit/secrets.toml and restart the app."
    )
    st.stop()

if "chats" not in st.session_state:
    st.session_state.chats = {}
if "active_chat_id" not in st.session_state:
    st.session_state.active_chat_id = None


def _chat_path(chat_id: str) -> Path:
    return CHATS_DIR / f"{chat_id}.json"


def _save_chat(chat_id: str) -> None:
    chat = st.session_state.chats.get(chat_id)
    if not chat:
        return
    data = {
        "id": chat_id,
        "title": chat["title"],
        "created_at": chat["created_at"],
        "messages": chat["messages"],
    }
    _chat_path(chat_id).write_text(json.dumps(data, indent=2), encoding="utf-8")


def _load_chats() -> None:
    if st.session_state.chats:
        return
    for path in sorted(CHATS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            chat_id = data.get("id") or path.stem
            st.session_state.chats[chat_id] = {
                "title": data.get("title", "Chat"),
                "created_at": data.get("created_at", ""),
                "messages": data.get("messages", []),
            }
        except (OSError, json.JSONDecodeError):
            continue

    if st.session_state.chats and not st.session_state.active_chat_id:
        st.session_state.active_chat_id = next(iter(st.session_state.chats.keys()))


def _delete_chat(chat_id: str) -> None:
    try:
        _chat_path(chat_id).unlink(missing_ok=True)
    except OSError:
        pass


def _new_chat():
    chat_id = f"chat-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    created_at = datetime.now().isoformat()
    st.session_state.chats[chat_id] = {
        "title": "New Chat",
        "created_at": created_at,
        "messages": [],
    }
    st.session_state.active_chat_id = chat_id
    _save_chat(chat_id)


_load_chats()

with st.sidebar:
    st.header("Chats")
    if st.button("New Chat", type="primary"):
        _new_chat()

    if not st.session_state.chats:
        st.caption("No chats yet.")
    else:
        for chat_id, chat in list(st.session_state.chats.items()):
            is_active = chat_id == st.session_state.active_chat_id
            left, right = st.columns([0.85, 0.15])
            with left:
                if st.button(
                    chat["title"],
                    type="primary" if is_active else "secondary",
                    key=f"select-{chat_id}",
                ):
                    st.session_state.active_chat_id = chat_id
                created_at = chat.get("created_at", "")
                try:
                    display_time = datetime.fromisoformat(created_at).strftime(
                        "%b %d, %Y %I:%M %p"
                    )
                except ValueError:
                    display_time = created_at or "Unknown time"
                st.caption(display_time)
            with right:
                if st.button("✕", key=f"delete-{chat_id}"):
                    del st.session_state.chats[chat_id]
                    _delete_chat(chat_id)
                    if st.session_state.active_chat_id == chat_id:
                        remaining = list(st.session_state.chats.keys())
                        st.session_state.active_chat_id = (
                            remaining[0] if remaining else None
                        )
                    st.rerun()

active_chat_id = st.session_state.active_chat_id
active_chat = (
    st.session_state.chats.get(active_chat_id) if active_chat_id else None
)

if not active_chat:
    st.info("No chat selected. Start a new chat from the sidebar.")
    st.stop()

for message in active_chat["messages"]:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

prompt = st.chat_input("Type your message")
if prompt:
    active_chat["messages"].append({"role": "user", "content": prompt})
    if active_chat["title"] == "New Chat":
        active_chat["title"] = prompt.strip()[:40] or "New Chat"
    _save_chat(active_chat_id)
    with st.chat_message("user"):
        st.markdown(prompt)

    headers = {"Authorization": f"Bearer {hf_token}"}
    payload = {
        "model": "meta-llama/Llama-3.2-1B-Instruct",
        "messages": active_chat["messages"],
        "max_tokens": 512,
    }

    try:
        response = requests.post(
            "https://router.huggingface.co/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=30,
        )
        if response.status_code != 200:
            st.error(
                f"API request failed ({response.status_code}). "
                "Check your token and try again."
            )
            st.caption(response.text)
            st.stop()

        data = response.json()
        reply = data["choices"][0]["message"]["content"]
        active_chat["messages"].append({"role": "assistant", "content": reply})
        _save_chat(active_chat_id)
        with st.chat_message("assistant"):
            st.markdown(reply)
    except requests.exceptions.RequestException as exc:
        st.error("Network error while contacting the Hugging Face API.")
        st.caption(str(exc))
    except (KeyError, IndexError, ValueError) as exc:
        st.error("Unexpected API response format.")
        st.caption(str(exc))
