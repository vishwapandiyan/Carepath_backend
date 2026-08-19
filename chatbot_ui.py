"""
CTS Emergency Triage — Streamlit Test Client
=============================================
Quick UI to exercise the full chatbot flow end-to-end:
  Phase 1 — Intake  : 4-question conversational intake
  Phase 2 — Safety  : 10-field emergency red-flag checklist
  Phase 3 — Verdict : YES → Emergency Room | NO → ML Pathway

Run from the CTS-MAIN root:
    streamlit run chatbot_ui.py

Make sure the FastAPI server is running first:
    uvicorn app.main:app --reload
"""

import requests
import streamlit as st

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────
BASE_URL = "http://127.0.0.1:8000/api/v1/patient"
DEFAULT_API_KEY = "5e16700718fb2954a5378108763c96342f44d86dab0f17d1df62f861c79e8676"

st.set_page_config(
    page_title="CTS Emergency Triage",
    page_icon="🏥",
    layout="centered",
)

# ─────────────────────────────────────────────────────────────────────────────
# Sidebar — connection settings
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("⚙️ Settings")
    api_key = st.text_input("API Key", value=DEFAULT_API_KEY, type="password")
    base_url = st.text_input("Backend URL", value=BASE_URL)
    st.divider()
    if st.button("🔄 Reset Session", use_container_width=True):
        st.session_state.clear()
        st.rerun()
    st.caption("Make sure `uvicorn app.main:app --reload` is running.")

HEADERS = {"X-API-Key": api_key, "Content-Type": "application/json"}


# ─────────────────────────────────────────────────────────────────────────────
# Session state defaults
# ─────────────────────────────────────────────────────────────────────────────
def _init():
    defaults = {
        "phase": "start",          # start → intake → safety → verdict
        "session_id": None,
        "patient_id": None,
        "chat_messages": [],       # [{role, content}]
        "next_question": None,
        "intake_features": None,
        "red_flags": {},           # accumulated checklist values
        "safety_result": None,
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)

_init()


# ─────────────────────────────────────────────────────────────────────────────
# Helper — API calls
# ─────────────────────────────────────────────────────────────────────────────
def api_post(path: str, body: dict) -> dict | None:
    try:
        r = requests.post(f"{base_url}{path}", json=body, headers=HEADERS, timeout=30)
        r.raise_for_status()
        return r.json()
    except requests.HTTPError as e:
        st.error(f"API error {e.response.status_code}: {e.response.text}")
    except Exception as e:
        st.error(f"Connection error: {e}")
    return None


def api_get(path: str) -> dict | None:
    try:
        r = requests.get(f"{base_url}{path}", headers=HEADERS, timeout=30)
        r.raise_for_status()
        return r.json()
    except requests.HTTPError as e:
        st.error(f"API error {e.response.status_code}: {e.response.text}")
    except Exception as e:
        st.error(f"Connection error: {e}")
    return None


def add_message(role: str, content: str):
    st.session_state.chat_messages.append({"role": role, "content": content})


# ─────────────────────────────────────────────────────────────────────────────
# Phase helpers
# ─────────────────────────────────────────────────────────────────────────────
def start_session(patient_id: str):
    data = api_post("/intake/sessions", {"patient_id": patient_id})
    if data:
        st.session_state.session_id = data["session_id"]
        st.session_state.patient_id = patient_id
        st.session_state.phase = "intake"
        first_q = data.get("next_question", "Tell me your main symptom.")
        st.session_state.next_question = first_q
        add_message("assistant", f"👋 Hello! I'm your emergency triage assistant.\n\n{first_q}")


def send_intake_message(user_text: str):
    sid = st.session_state.session_id
    add_message("user", user_text)
    data = api_post(f"/intake/sessions/{sid}/messages", {"content": user_text})
    if not data:
        return
    if data.get("status") == "ERROR":
        add_message("assistant", f"⚠️ Error: {data.get('error_detail', 'Unknown error')}")
        return

    st.session_state.intake_features = data.get("extracted")

    if data.get("status") == "COMPLETE":
        st.session_state.phase = "safety"
        add_message(
            "assistant",
            "✅ Thank you — I have all the information I need.\n\n"
            "Now I need to ask you 10 quick YES/NO questions about severe symptoms. "
            "**Please answer honestly — this determines if you need immediate emergency care.**",
        )
    else:
        next_q = data.get("next_question", "")
        st.session_state.next_question = next_q
        if next_q:
            add_message("assistant", next_q)


def submit_red_flags_and_evaluate():
    sid = st.session_state.session_id
    flags = st.session_state.red_flags

    # POST /red-flags
    data = api_post(f"/safety/sessions/{sid}/red-flags", flags)
    if not data:
        return

    # POST /evaluate
    result = api_post(f"/safety/sessions/{sid}/evaluate", {})
    if not result:
        return

    st.session_state.safety_result = result
    st.session_state.phase = "verdict"


# ─────────────────────────────────────────────────────────────────────────────
# UI — PHASE: START
# ─────────────────────────────────────────────────────────────────────────────
if st.session_state.phase == "start":
    st.title("🏥 CTS Emergency Triage")
    st.markdown(
        "This system collects your symptoms and determines whether you need "
        "**immediate emergency care** or can be routed to further assessment."
    )
    st.divider()
    patient_id = st.text_input("Enter your Patient ID to begin", placeholder="e.g. PAT-001")
    if st.button("Start Triage →", type="primary", use_container_width=True):
        if patient_id.strip():
            start_session(patient_id.strip())
            st.rerun()
        else:
            st.warning("Please enter a patient ID.")


# ─────────────────────────────────────────────────────────────────────────────
# UI — PHASE: INTAKE (conversational chat)
# ─────────────────────────────────────────────────────────────────────────────
elif st.session_state.phase == "intake":
    st.title("🏥 CTS Emergency Triage")
    st.caption(f"Session: `{st.session_state.session_id}` | Patient: `{st.session_state.patient_id}`")
    st.progress(0.25, text="Step 1 of 3 — Collecting symptoms")

    # Render chat history
    for msg in st.session_state.chat_messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    # Chat input
    user_input = st.chat_input("Type your response here…")
    if user_input:
        send_intake_message(user_input)
        st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# UI — PHASE: SAFETY CHECKLIST
# ─────────────────────────────────────────────────────────────────────────────
elif st.session_state.phase == "safety":
    st.title("🚨 Emergency Red-Flag Checklist")
    st.caption(f"Session: `{st.session_state.session_id}`")
    st.progress(0.65, text="Step 2 of 3 — Emergency screening")

    # Show chat so far (collapsed for space)
    with st.expander("📋 View intake summary", expanded=False):
        for msg in st.session_state.chat_messages:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])
        if st.session_state.intake_features:
            st.subheader("Extracted Information")
            f = st.session_state.intake_features
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Chief Complaint", f.get("chief_complaint") or "—")
                st.metric("Onset", f.get("symptom_onset") or "—")
            with col2:
                st.metric("Pain Scale", f.get("pain_scale") if f.get("pain_scale") is not None else "—")
                st.metric("Location", f.get("location") or "—")

    st.divider()
    st.markdown(
        "**Answer YES or NO to each question below.**  \n"
        "These questions describe severe, emergency-level presentations."
    )

    # Red-flag questions — labels match the JSON rule descriptions
    RED_FLAG_QUESTIONS = {
        "chest_pain":           "Are you having chest pain or pressure — squeezing, tightness, or pressure in the chest?",
        "difficulty_breathing": "Are you having SEVERE difficulty breathing — unable to speak in full sentences, or gasping for air?",
        "altered_consciousness":"Have you lost consciousness, fainted, or are you acutely confused / unresponsive?",
        "severe_bleeding":      "Are you bleeding severely and unable to stop it despite direct pressure?",
        "stroke_symptoms":      "Do you have facial drooping, sudden arm/leg weakness, or inability to speak — happening RIGHT NOW?",
        "suicidal_ideation":    "Are you having thoughts of hurting yourself or ending your life?",
        "anaphylaxis":          "Are you having a severe allergic reaction — throat swelling, widespread hives, or feeling faint?",
        "high_fever":           "Do you have a dangerously high fever — 103°F (39.4°C) or higher?",
        "unable_to_walk":       "Are you completely unable to walk, stand, or bear any weight?",
        "severe_abdominal_pain":"Are you having severe, sharp, or crushing abdominal (belly) pain?",
    }

    with st.form("red_flags_form"):
        responses = {}
        for field, question in RED_FLAG_QUESTIONS.items():
            col_q, col_a = st.columns([3, 1])
            with col_q:
                st.markdown(f"**{question}**")
            with col_a:
                val = st.radio(
                    label=field,
                    options=["No", "Yes"],
                    horizontal=True,
                    label_visibility="collapsed",
                    key=f"rf_{field}",
                )
                responses[field] = val == "Yes"
            st.divider()

        submitted = st.form_submit_button(
            "🔍 Run Emergency Screening →",
            type="primary",
            use_container_width=True,
        )

    if submitted:
        st.session_state.red_flags = responses
        with st.spinner("Evaluating safety..."):
            submit_red_flags_and_evaluate()
        st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# UI — PHASE: VERDICT
# ─────────────────────────────────────────────────────────────────────────────
elif st.session_state.phase == "verdict":
    result = st.session_state.safety_result or {}
    outcome = result.get("result", "ERROR")
    next_action = result.get("next_action", "ERROR")
    triggered = result.get("triggered_rules", [])

    st.progress(1.0, text="Step 3 of 3 — Complete")

    if outcome == "YES":
        st.markdown(
            """
            <div style="background:#FF4444;border-radius:16px;padding:32px;text-align:center;color:white;">
                <h1 style="margin:0;font-size:3rem;">🚨 EMERGENCY</h1>
                <p style="font-size:1.4rem;margin-top:8px;">Please go to the Emergency Room immediately.</p>
                <p style="font-size:1rem;opacity:0.85;">Do not wait. Call 911 if you cannot travel safely.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.divider()
        if triggered:
            st.subheader("⚠️ Triggered Red Flags")
            for rule_id in triggered:
                st.error(f"Rule **{rule_id}** was triggered")

    elif outcome == "NO":
        st.markdown(
            """
            <div style="background:#1a7a4a;border-radius:16px;padding:32px;text-align:center;color:white;">
                <h1 style="margin:0;font-size:3rem;">✅ No Emergency Detected</h1>
                <p style="font-size:1.4rem;margin-top:8px;">Routing to clinical assessment pathway.</p>
                <p style="font-size:1rem;opacity:0.85;">Next: ML-based clinical decision support (CMS/ML Pathway)</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    else:  # ERROR
        st.error(f"⚠️ Safety engine error: {result.get('error_detail', 'Unknown')}")
        st.info("Please retry or contact support.")

    st.divider()

    # Summary card
    with st.expander("📊 Full Session Summary", expanded=True):
        col1, col2, col3 = st.columns(3)
        col1.metric("Result", outcome)
        col2.metric("Next Action", next_action)
        col3.metric("Rules Triggered", len(triggered))

        if st.session_state.intake_features:
            st.subheader("Intake Data")
            f = st.session_state.intake_features
            st.table({
                "Field": ["Chief Complaint", "Onset", "Pain Scale", "Location"],
                "Value": [
                    f.get("chief_complaint") or "—",
                    f.get("symptom_onset") or "—",
                    str(f.get("pain_scale")) if f.get("pain_scale") is not None else "—",
                    f.get("location") or "—",
                ],
            })

        st.subheader("Red Flag Answers")
        flag_data = {"Symptom": [], "Answer": []}
        labels = {
            "chest_pain": "Chest Pain/Pressure",
            "difficulty_breathing": "Severe Difficulty Breathing",
            "altered_consciousness": "Loss of Consciousness",
            "severe_bleeding": "Severe Bleeding",
            "stroke_symptoms": "Stroke Symptoms",
            "suicidal_ideation": "Suicidal Ideation",
            "anaphylaxis": "Anaphylaxis",
            "high_fever": "High Fever ≥103°F",
            "unable_to_walk": "Unable to Walk",
            "severe_abdominal_pain": "Severe Abdominal Pain",
        }
        for field, label in labels.items():
            flag_data["Symptom"].append(label)
            val = st.session_state.red_flags.get(field, False)
            flag_data["Answer"].append("🔴 YES" if val else "🟢 No")
        st.table(flag_data)

        st.caption(
            f"Session ID: `{st.session_state.session_id}` | "
            f"Evaluated at: `{result.get('evaluated_at', '—')}`"
        )

    st.divider()
    if st.button("🔄 Start New Triage", type="primary", use_container_width=True):
        st.session_state.clear()
        st.rerun()
