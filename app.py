from datetime import datetime
import json
from pathlib import Path
import time
import requests
import streamlit as st

st.set_page_config(page_title="My AI Chat", layout="wide")

st.title("My AI Chat")

BASE_DIR = Path(__file__).resolve().parent
CHATS_DIR = BASE_DIR / "chats"
CHATS_DIR.mkdir(exist_ok=True)
MEMORY_PATH = BASE_DIR / "memory.json"

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
if "user_memory" not in st.session_state:
    st.session_state.user_memory = {}


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


def _load_memory() -> None:
    if st.session_state.user_memory:
        return
    if MEMORY_PATH.exists():
        try:
            st.session_state.user_memory = json.loads(
                MEMORY_PATH.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            st.session_state.user_memory = {}
    else:
        st.session_state.user_memory = {}


def _save_memory() -> None:
    try:
        MEMORY_PATH.write_text(
            json.dumps(st.session_state.user_memory, indent=2), encoding="utf-8"
        )
    except OSError:
        pass


def _parse_json_object(text: str) -> dict:
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        data = None
    if isinstance(data, dict):
        return data

    if not text:
        return {}

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {}
    try:
        data = json.loads(text[start : end + 1])
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _reset_memory() -> None:
    st.session_state.user_memory = {}
    try:
        MEMORY_PATH.write_text("{}", encoding="utf-8")
    except OSError:
        pass


_load_memory()

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

    with st.expander("User Memory", expanded=False):
        if st.session_state.user_memory:
            st.json(st.session_state.user_memory)
        else:
            st.caption("No memory saved yet.")
        if st.button("Clear Memory"):
            _reset_memory()
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
    memory_context = (
        "Use this user memory to personalize responses:\n"
        + json.dumps(st.session_state.user_memory)
        if st.session_state.user_memory
        else ""
    )
    messages_for_api = (
        [{"role": "system", "content": memory_context}]
        if memory_context
        else []
    ) + active_chat["messages"]

    payload = {
        "model": "meta-llama/Llama-3.2-1B-Instruct",
        "messages": messages_for_api,
        "max_tokens": 512,
        "stream": True,
    }

    try:
        response = requests.post(
            "https://router.huggingface.co/v1/chat/completions",
            headers=headers,
            json=payload,
            stream=True,
            timeout=30,
        )
        if response.status_code != 200:
            st.error(
                f"API request failed ({response.status_code}). "
                "Check your token and try again."
            )
            st.caption(response.text)
            st.stop()

        with st.chat_message("assistant"):
            placeholder = st.empty()
            reply_chunks = []

            for raw_line in response.iter_lines(decode_unicode=True):
                if not raw_line:
                    continue
                if raw_line.startswith("data: "):
                    data_str = raw_line[len("data: ") :]
                else:
                    data_str = raw_line

                if data_str.strip() == "[DONE]":
                    break

                try:
                    data = json.loads(data_str)
                    delta = data["choices"][0]["delta"].get("content", "")
                except (KeyError, IndexError, ValueError):
                    delta = ""

                if delta:
                    reply_chunks.append(delta)
                    placeholder.markdown("".join(reply_chunks))
                    time.sleep(0.02)

            reply = "".join(reply_chunks).strip()
            if not reply:
                st.error("No response received from the model.")
                st.stop()

        active_chat["messages"].append({"role": "assistant", "content": reply})
        _save_chat(active_chat_id)
        _extract_payload = {
            "model": "meta-llama/Llama-3.2-1B-Instruct",
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Given this user message, extract any personal facts or "
                        "preferences as a JSON object. If none, return {}. "
                        "Respond with only JSON."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 128,
            "temperature": 0,
        }
        try:
            extract_response = requests.post(
                "https://router.huggingface.co/v1/chat/completions",
                headers=headers,
                json=_extract_payload,
                timeout=30,
            )
            if extract_response.status_code == 200:
                extract_data = extract_response.json()
                content = extract_data["choices"][0]["message"]["content"]
                new_memory = _parse_json_object(content)
                if isinstance(new_memory, dict) and new_memory:
                    st.session_state.user_memory.update(new_memory)
                    _save_memory()
        except (requests.exceptions.RequestException, KeyError, IndexError, ValueError):
            pass
    except requests.exceptions.RequestException as exc:
        st.error("Network error while contacting the Hugging Face API.")
        st.caption(str(exc))
    except (KeyError, IndexError, ValueError) as exc:
        st.error("Unexpected API response format.")
        st.caption(str(exc))
