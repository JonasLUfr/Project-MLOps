import streamlit as st
import requests
import hashlib

# ---------------------------
# Page config
# ---------------------------
st.set_page_config(page_title="Phishing Detector", page_icon="🎣", layout="centered")

# ---------------------------
# API endpoints (UNCHANGED)
# ---------------------------
API_URL = "http://n8n:5678/webhook"
ANALYZE_ENDPOINT = f"{API_URL}/analyze"
FEEDBACK_ENDPOINT = "http://serving-api:8080/feedback"

# ---------------------------
# CSS (ChatGPT-like centered cover)
# ---------------------------
st.markdown(
    """
    <style>
      /* Hide Streamlit default UI */
      #MainMenu {visibility: hidden;}
      footer {visibility: hidden;}
      header {visibility: hidden;}

      /* Container width + top padding */
      .block-container {max-width: 900px; padding-top: 1.5rem;}

      /* Center cover area */
      .cover {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        min-height: 30vh;
        gap: 18px;
      }

      /* Centered title */
      .cover-title {
        font-size: 2.1rem;
        font-weight: 750;
        letter-spacing: -0.02em;
        text-align: center;
        margin: 0;
      }

      /* Make the textarea look like a single rounded input */
      div[data-testid="stTextArea"] textarea {
        border-radius: 999px !important;
        padding: 14px 16px !important;
        height: 54px !important;            /* single-line feel */
        min-height: 54px !important;
        resize: none !important;
      }
      div[data-testid="stTextArea"] label {display:none;}

      /* Reduce spacing around widgets */
      .stButton button {
        border-radius: 999px !important;
        height: 54px !important;
        font-weight: 600 !important;
      }

      /* Chat area spacing */
      .chat-wrap {margin-top: 1rem;}
    </style>
    """,
    unsafe_allow_html=True
)

# ---------------------------
# Session state
# ---------------------------
if "messages" not in st.session_state:
    st.session_state["messages"] = []   # [{"role": "user"/"assistant", "content": str, "meta": dict}]
if "last_pred" not in st.session_state:
    st.session_state["last_pred"] = None
if "last_email_text" not in st.session_state:
    st.session_state["last_email_text"] = ""
if "busy" not in st.session_state:
    st.session_state["busy"] = False


def format_assistant_answer(pred_label, proba, rag_advice):
    lines = []
    if pred_label is not None:
        lines.append(f"**Decision:** `{pred_label}`")
    if proba is not None:
        try:
            lines.append(f"**Confidence:** `{float(proba) * 100:.1f}%`")
        except Exception:
            lines.append(f"**Confidence:** `{proba}`")

    lines.append("\n**Explanation (LLM/RAG)**\n")
    lines.append(rag_advice if rag_advice else "_No explanation returned by n8n._")
    return "\n\n".join(lines)


# ---------------------------
# If no messages yet: centered "cover" UI
# ---------------------------
if len(st.session_state["messages"]) == 0:
    st.markdown(
        """
        <div class="cover">
          <div class="cover-title">🎣 Phishing Email Detector</div> 
        </div>
        """,
        unsafe_allow_html=True
    )

    # Put the input right under the cover, centered with columns
    left, mid, right = st.columns([1, 8, 1])
    with mid:
        c1, c2 = st.columns([8, 2])
        with c1:
            email_text = st.text_area(
                "Email content:",
                placeholder="Paste the email text here (links, signatures, etc.)",
                height=54,
                key="draft_email_cover"
            )
        with c2:
            send_clicked = st.button("Send ➜", use_container_width=True, disabled=st.session_state["busy"])

    if send_clicked:
        if not (email_text and email_text.strip()):
            st.warning("Please paste some text.")
        else:
            st.session_state["busy"] = True

            # Add user bubble
            st.session_state["messages"].append({"role": "user", "content": email_text.strip()})
            st.session_state["last_email_text"] = email_text.strip()

            # Call backend
            with st.spinner("Analyzing…"):
                try:
                    resp = requests.post(
                        ANALYZE_ENDPOINT,
                        json={"email_text": email_text.strip()},
                        timeout=60
                    )
                    if resp.status_code != 200:
                        st.session_state["messages"].append(
                            {"role": "assistant", "content": f"❌ **API Error:** {resp.text}"}
                        )
                        st.session_state["last_pred"] = None
                    else:
                        res_json = resp.json() if resp.content else {}
                        pred_label = res_json.get("prediction")
                        proba = res_json.get("probability")
                        rag_advice = res_json.get("rag_advice")

                        st.session_state["messages"].append(
                            {
                                "role": "assistant",
                                "content": format_assistant_answer(pred_label, proba, rag_advice),
                                "meta": {"prediction": pred_label, "probability": proba}
                            }
                        )
                        st.session_state["last_pred"] = res_json

                except Exception as e:
                    st.session_state["messages"].append(
                        {"role": "assistant", "content": f"❌ **Connection Error:** {e}"}
                    )
                    st.session_state["last_pred"] = None

            st.session_state["busy"] = False
            st.rerun()

else:
    # ---------------------------
    # Chat mode (after first message)
    # ---------------------------
    st.markdown('<div class="chat-wrap"></div>', unsafe_allow_html=True)

    for msg in st.session_state["messages"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            meta = msg.get("meta") or {}
            if msg["role"] == "assistant" and meta.get("prediction") is not None:
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Decision", meta.get("prediction", "N/A"))
                with col2:
                    proba = meta.get("probability")
                    if proba is None:
                        st.metric("Confidence", "N/A")
                    else:
                        try:
                            st.metric("Confidence", f"{float(proba) * 100:.1f}%")
                        except Exception:
                            st.metric("Confidence", str(proba))

    st.divider()

    # A clean "input + send" row (still centered)
    left, mid, right = st.columns([1, 8, 1])
    with mid:
        c1, c2 = st.columns([8, 2])
        with c1:
            email_text = st.text_area(
                "Email content:",
                placeholder="Paste another email…",
                height=54,
                key="draft_email_chat"
            )
        with c2:
            send_clicked = st.button("Send ➜", use_container_width=True, disabled=st.session_state["busy"])

    if send_clicked:
        if not (email_text and email_text.strip()):
            st.warning("Please paste some text.")
        else:
            st.session_state["busy"] = True

            st.session_state["messages"].append({"role": "user", "content": email_text.strip()})
            st.session_state["last_email_text"] = email_text.strip()

            with st.spinner("Analyzing…"):
                try:
                    resp = requests.post(
                        ANALYZE_ENDPOINT,
                        json={"email_text": email_text.strip()},
                        timeout=60
                    )
                    if resp.status_code != 200:
                        st.session_state["messages"].append(
                            {"role": "assistant", "content": f"❌ **API Error:** {resp.text}"}
                        )
                        st.session_state["last_pred"] = None
                    else:
                        res_json = resp.json() if resp.content else {}
                        pred_label = res_json.get("prediction")
                        proba = res_json.get("probability")
                        rag_advice = res_json.get("rag_advice")

                        st.session_state["messages"].append(
                            {
                                "role": "assistant",
                                "content": format_assistant_answer(pred_label, proba, rag_advice),
                                "meta": {"prediction": pred_label, "probability": proba}
                            }
                        )
                        st.session_state["last_pred"] = res_json

                except Exception as e:
                    st.session_state["messages"].append(
                        {"role": "assistant", "content": f"❌ **Connection Error:** {e}"}
                    )
                    st.session_state["last_pred"] = None

            st.session_state["busy"] = False
            st.rerun()

# ---------------------------
# Feedback (UNCHANGED endpoint)
# ---------------------------
if st.session_state.get("last_pred") and st.session_state.get("last_email_text"):
    last = st.session_state["last_pred"]
    pred_label = last.get("prediction")

    h = hashlib.md5(st.session_state["last_email_text"].encode("utf-8")).hexdigest()[:8]
    form_key = f"feedback_form_{h}"

    with st.expander("Is this email a phishing email? (Human-in-the-Loop)", expanded=False):
        st.write("Help us improve the system by submitting the real label.")

        with st.form(form_key):
            user_choice = st.radio(
                "Real label:",
                ["Phishing Email", "Safe Email"],
                horizontal=True
            )
            submitted = st.form_submit_button("Submit correction")

            if submitted:
                payload = {
                    "email_text": st.session_state["last_email_text"],
                    "model_prediction": pred_label,
                    "user_correction": user_choice
                }

                try:
                    fb = requests.post(FEEDBACK_ENDPOINT, json=payload, timeout=30)
                    if fb.status_code == 200:
                        st.success("Thanks! Feedback saved.")
                    else:
                        st.error(f"❌ Feedback save error: {fb.text}")
                except Exception as e:
                    st.error(f"❌ Error: {e}")
