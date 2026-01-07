import streamlit as st
import requests

st.set_page_config(page_title="Phishing Detector", page_icon="🎣")

st.title("Détecteur de Phishing")
st.markdown("Copiez le contenu d'un email suspect pour l'analyser.")

API_URL = "http://serving-api:8080"
RAG_API_URL = "http://rag-api:8083/ask"

# init Session State
if 'pred_result' not in st.session_state:
    st.session_state['pred_result'] = None
if 'email_input' not in st.session_state:
    st.session_state['email_input'] = ""

# zone de saisie
email_text = st.text_area("Contenu de l'email :", height=200, placeholder="Dear customer, your bank account...")

if st.button("Analyser l'email"):
    if email_text:
        try:
            # appel API classification
            response = requests.post(f"{API_URL}/predict", json={"email_text": email_text})
            
            if response.status_code == 200:
                res_json = response.json()
                st.session_state['pred_result'] = res_json
                st.session_state['email_input'] = email_text # on garde le texte pour le feedback
                


                # partie RAG -> si c'est du Phishing, on interroge le RAG
                if res_json['prediction'] == "Phishing Email":
                    with st.spinner("L'IA génère des conseils de sécurité..."):
                        try:
                            # pas de code pour l'instant donc on suppose que comme ca pour l'instant
                            # rag_res = requests.post(RAG_API_URL, json={"context": email_text})
                            # advice = rag_res.json()['answer']
                            
                            # MOCK (temporaire, en attente de code)
                            import time
                            time.sleep(1) # simule temps de calcul
                            advice = """
                            🛡️ **Conseils de Sécurité** :
                            1. Ne cliquez pas sur les liens.
                            2. Vérifiez l'adresse de l'expéditeur.
                            3. Contactez votre banque directement.
                            """
                            st.session_state['rag_advice'] = advice
                        except:
                            st.session_state['rag_advice'] = "Impossible de contacter l'assistant de sécurité."
                else:
                    st.session_state['rag_advice'] = None


            else:
                st.error(f"Erreur API: {response.text}")
        except Exception as e:
            st.error(f"Erreur Connexion: {e}")
    else:
        st.warning("Veuillez entrer du texte.")

# zone resultat + feedback
if st.session_state['pred_result']:
    result = st.session_state['pred_result']
    pred_label = result['prediction']
    proba = result['probability']
    
    st.divider()
    
    # affichage
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Résultat", pred_label)
    with col2:
        st.metric("Confiance", f"{proba*100:.1f}%")
        
    if pred_label == "Phishing Email":
        st.error("ALERTE : Ceci ressemble à une tentative de Phishing !")
    else:
        st.success("Cet email semble légitime (Safe).")

    # Affichage du RAG (si disponible)
    if st.session_state.get('rag_advice'):
        st.info(st.session_state['rag_advice'])

    # boucle feedback
    st.write("---")
    st.subheader("L'IA a-t-elle raison ?")
    
    with st.form("feedback_form"):
        # le user choisit la vraie catégorie
        user_choice = st.radio("Classification réelle :", ["Phishing Email", "Safe Email"], horizontal=True)
        
        submit_feedback = st.form_submit_button("Envoyer la correction")
        
        if submit_feedback:
            payload = {
                "email_text": st.session_state['email_input'],
                "model_prediction": pred_label,
                "user_correction": user_choice
            }
            
            try:
                res = requests.post(f"{API_URL}/feedback", json=payload)
                if res.status_code == 200:
                    st.success("Merci ! Feedback enregistré pour le ré-entraînement.")
                else:
                    st.error("Erreur sauvegarde feedback.")
            except Exception as e:
                st.error(f"Erreur: {e}")