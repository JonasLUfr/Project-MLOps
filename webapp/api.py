import streamlit as st
import requests

st.set_page_config(page_title="Phishing Detector", page_icon="🎣")

st.title("Détecteur de Phishing")
st.markdown("Copiez le contenu d'un email suspect pour l'analyser.")

API_URL = "http://n8n:5678/webhook"  # now pointing to n8n

# init session
if 'pred_result' not in st.session_state:
    st.session_state['pred_result'] = None
if 'email_input' not in st.session_state:
    st.session_state['email_input'] = ""

email_text = st.text_area("Contenu de l'email :", height=200, placeholder="Dear customer...")

if st.button("Analyser l'email"):
    if email_text:
        try:
            response = requests.post(
                f"{API_URL}/analyze",
                json={"email_text": email_text}
            )
            
            if response.status_code == 200:
                res_json = response.json()
                st.session_state['pred_result'] = res_json
                st.session_state['email_input'] = email_text
            else:
                st.error(f"Erreur API: {response.text}")
        except Exception as e:
            st.error(f"Erreur Connexion: {e}")
    else:
        st.warning("Veuillez entrer du texte.")

if st.session_state['pred_result']:
    result = st.session_state['pred_result']
    pred_label = result.get('prediction')
    proba_raw = result.get('probability')
    proba = float(proba_raw) if proba_raw is not None else None


    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Résultat", pred_label)
    with col2:
        st.metric("Confiance", f"{proba * 100:.1f}%" if proba is not None else "N/A")

    # show rag advice if returned by n8n
    if result.get('rag_advice'):
        st.info(result['rag_advice'])

    st.write("---")
    st.subheader("L'IA a-t-elle raison ?")
    
    with st.form("feedback_form"):
        user_choice = st.radio(
            "Classification réelle :",
            ["Phishing Email", "Safe Email"],
            horizontal=True
        )
        
        submit_feedback = st.form_submit_button("Envoyer la correction")
        
        if submit_feedback:
            payload = {
                "email_text": st.session_state['email_input'],
                "model_prediction": pred_label,
                "user_correction": user_choice
            }
            
            try:
                res = requests.post(
                    f"{API_URL}/feedback",
                    json=payload
                )
                if res.status_code == 200:
                    st.success("Merci ! Feedback enregistré.")
                else:
                    st.error("Erreur sauvegarde feedback.")
            except Exception as e:
                st.error(f"Erreur: {e}")
