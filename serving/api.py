import pandas as pd
import joblib
import os
import csv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

# path
ARTIFACTS_DIR = "/artifacts"
DATA_DIR = "/data"
PROD_DATA_PATH = os.path.join(DATA_DIR, "prod_data.csv")
MODEL_PATH = os.path.join(ARTIFACTS_DIR, "phishing_tfidf_logreg.joblib")

# variable globale pour le modèle
model = None

class EmailInput(BaseModel):
    email_text: str

class FeedbackInput(BaseModel):
    email_text: str
    model_prediction: str
    user_correction: str


# fonction utilitaire pour nettoyer le texte
def clean_text(text: str) -> str:
    # rm les espaces au début et à la fin
    text = text.strip()
    # remplace les retours à la ligne par des espaces
    text = text.replace("\n", " ").replace("\r", " ")
    # enleve les doubles espaces créés
    import re
    text = re.sub(' +', ' ', text)
    return text

@app.on_event("startup")
def load_model():
    global model
    try:
        model = joblib.load(MODEL_PATH)
        print(f"Modèle chargé depuis {MODEL_PATH}")
    except Exception as e:
        print(f"Erreur chargement modèle: {e}")
        model = None

@app.get("/")
def read_root():
    return {"status": "Active", "model_loaded": model is not None}

@app.post("/predict")
def predict(data: EmailInput):
    global model
    
    if model is None:
        return {"prediction": "MOCK", "probability": 0.5, "status": "MOCK"}

    try:

        cleaned_email = clean_text(data.email_text)

        # prédiction brute (attention erreur format -> numpy.int32)
        raw_pred = model.predict([cleaned_email])[0]
        raw_proba = model.predict_proba([cleaned_email]).max()

        # pour debug type -> affichage dans les logs
        print(f"🔍 DEBUG TYPE: Pred={type(raw_pred)} Val={raw_pred} | Proba={type(raw_proba)}")

        # conversion -> on force la proba en float python standard pour eviter une erreur
        final_proba = float(raw_proba)

        # gestion prédiction (Int ou Str)
        final_pred = ""
        
        # si le modèle renvoie 0 ou 1 (entier)
        if hasattr(raw_pred, "item"): # détection type NumPy
            valeur = raw_pred.item() # convertit numpy.int32 en int python
            if isinstance(valeur, int):
                # mappig du 1 en Phishing et 0 en Safe
                # (à inverser si on considere l'inverse dans les datas)
                final_pred = "Phishing Email" if valeur == 1 else "Safe Email"
            else:
                final_pred = str(valeur)
        else:
            # c'est déjà une string ou un int standard
            final_pred = str(raw_pred)

        # sécurité si le modèle a renvoyé "1" en string
        if final_pred == "1": final_pred = "Phishing Email"
        if final_pred == "0": final_pred = "Safe Email"

        return {
            "prediction": final_pred,
            "probability": final_proba,
            "email_excerpt": cleaned_email[:50] + "..."
        }

    except Exception as e:
        print(f"ERREUR CRITIQUE: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/feedback")
def save_feedback(feedback: FeedbackInput):
    try:
        file_exists = os.path.isfile(PROD_DATA_PATH)
        
        cleaned_email = clean_text(feedback.email_text)

        with open(PROD_DATA_PATH, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
            if not file_exists:
                writer.writerow(["email_text", "prediction", "target"])
            
            # on save la version clean du texte
            writer.writerow([
                cleaned_email, 
                feedback.model_prediction, 
                feedback.user_correction
            ])
            
        return {"status": "Feedback Saved"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur: {e}")

@app.post("/reload-model")
def reload_model():
    """Recharge le modèle depuis le disque"""
    global model
    try:
        model = joblib.load(MODEL_PATH)
        print(f"✅ Modèle rechargé depuis {MODEL_PATH}")
        return {"status": "success", "message": "Model reloaded successfully"}
    except Exception as e:
        print(f"❌ Erreur rechargement modèle: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to reload model: {e}")