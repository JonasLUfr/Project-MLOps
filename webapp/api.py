# version de test, destinée à etre detruite
import streamlit as st
import requests


# session state car streamlit reset à chaque clic d'un bouton
if 'prediction_result' not in st.session_state:
    st.session_state['prediction_result'] = None
if 'payload_data' not in st.session_state:
    st.session_state['payload_data'] = None

# titre
st.title("🔮 Prédiction de Churn Client")

# url de l'API (nom du service docker def dans le docker-compose)
API_URL = "http://serving-api:8080/predict"


# formulaire de saisie (col gauche / col droite)
col1, col2 = st.columns(2)

with col1:
    customer_id = st.number_input("CustomerID", value=1001)
    age = st.number_input("Age", value=30)
    gender = st.selectbox("Gender", ["Male", "Female"])
    tenure = st.number_input("Tenure (Mois)", value=12)
    usage_freq = st.number_input("Usage Frequency", value=10)
    support_calls = st.number_input("Support Calls", value=0)

with col2:
    payment_delay = st.number_input("Payment Delay", value=0)
    sub_type = st.selectbox("Subscription Type", ["Basic", "Standard", "Premium"])
    contract_len = st.selectbox("Contract Length", ["Monthly", "Quarterly", "Annual"])
    total_spend = st.number_input("Total Spend", value=500.0)
    last_inter = st.number_input("Last Interaction", value=5)

# bouton prédire
if st.button("Prédire le risque"):
    # construction du JSON
    payload = {
        "CustomerID": customer_id,
        "Age": age,
        "Gender": gender,
        "Tenure": tenure,
        "Usage_Frequency": usage_freq,
        "Support_Calls": support_calls,
        "Payment_Delay": payment_delay,
        "Subscription_Type": sub_type,
        "Contract_Length": contract_len,
        "Total_Spend": total_spend,
        "Last_Interaction": last_inter
    }

    # appel de l'API
    try:
        response = requests.post(API_URL, json=payload)
        if response.status_code == 200:
            # on save dans la session
            st.session_state['prediction_result'] = response.json()
            st.session_state['payload_data'] = payload  # on garde les données pour le feedback
        else:
            st.error("Erreur API")
    except Exception as e:
        st.error(f"Erreur connexion : {e}")



# on verif la session
if st.session_state['prediction_result']:
    result = st.session_state['prediction_result']
    payload = st.session_state['payload_data']
    
    # on affiche le résultat
    st.success(f"Probabilité de Churn : {result['churn_probability']*100:.1f}%")
    
    st.divider()
    st.write("📝 **Feedback Utilisateur**")
    
    # formulaire de feedback
    with st.form("feedback_form"):
        feedback_val = st.radio("Le client est-il vraiment parti ?", ["Oui (Churn)", "Non (Reste)"])
        submitted = st.form_submit_button("Envoyer le Feedback")
        
        if submitted:

            # on recup le résultat stocké en session pour l'envoyer au back
            original_pred = st.session_state['prediction_result']['prediction']

            feedback_payload = {
                "customer_data": payload,
                "correct_prediction": feedback_val == "Oui (Churn)",
                "model_prediction": original_pred
            }
            try:
                res = requests.post("http://serving-api:8080/feedback", json=feedback_payload)
                if res.status_code == 200:
                    st.success("Feedback enregistré ! ✅")
                else:
                    st.error(f"Erreur Back: {res.text}")
            except Exception as e:
                st.error(f"Erreur Call: {e}")