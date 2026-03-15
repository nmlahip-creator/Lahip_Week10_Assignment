import requests
import streamlit as st

st.set_page_config(page_title="My AI Chat", layout="wide")

st.title("My AI Chat")

hf_token = st.secrets.get("HF_TOKEN", "").strip()
if not hf_token:
    st.error(
        "Missing Hugging Face token. Add HF_TOKEN to .streamlit/secrets.toml and restart the app."
    )
    st.stop()

if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

prompt = st.chat_input("Type your message")
if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    headers = {"Authorization": f"Bearer {hf_token}"}
    payload = {
        "model": "meta-llama/Llama-3.2-1B-Instruct",
        "messages": st.session_state.messages,
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
        st.session_state.messages.append({"role": "assistant", "content": reply})
        with st.chat_message("assistant"):
            st.markdown(reply)
    except requests.exceptions.RequestException as exc:
        st.error("Network error while contacting the Hugging Face API.")
        st.caption(str(exc))
    except (KeyError, IndexError, ValueError) as exc:
        st.error("Unexpected API response format.")
        st.caption(str(exc))
