import pandas as pd
import pickle
import os
import csv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional

app = FastAPI()

# path (accessibles via le volume Docker)
ARTIFACTS_DIR = "/artifacts"
DATA_DIR = "/data"
PROD_DATA_PATH = os.path.join(DATA_DIR, "prod_data.csv")

# var globales
pipeline = None
model = None

# input des données (issue de customer_churn_train.csv)
class CustomerData(BaseModel):
    CustomerID: int = 0
    Age: int
    Gender: str
    Tenure: int
    Usage_Frequency: int
    Support_Calls: int
    Payment_Delay: int
    Subscription_Type: str
    Contract_Length: str
    Total_Spend: float
    Last_Interaction: int

# modèle de données (pour le feedback -> enregistré dans prod_data.csv)
class FeedbackData(BaseModel):
    customer_data: CustomerData
    correct_prediction: bool # true si on valide la prédiction, false sinon    -> verif la logique 
    model_prediction: bool # ce que le modèle avait prédit

@app.on_event("startup")
def load_artifacts():
    global pipeline, model
    # chargement du Pipeline (PCA)
    try:
        with open(f"{ARTIFACTS_DIR}/embedding_pipeline.pickle", "rb") as f:
            pipeline = pickle.load(f)
        print("✅ Pipeline (PCA) chargé avec succès.")
    except Exception as e:
        print(f"⚠️ Pipeline non chargé ({e}). L'API utilisera des valeurs simulées.")
        pipeline = None

    # chargement du Modèle (classification) -> à décommenter quand dispo
    # try:
    #     with open(f"{ARTIFACTS_DIR}/model.pickle", "rb") as f:
    #         model = pickle.load(f)
    # except:
    #     model = None

@app.get("/")
def read_root():
    return {"status": "API Serving Churn (Active)", "pipeline_loaded": pipeline is not None}

@app.post("/predict")
def predict(data: CustomerData):
    global pipeline
    
    # DEBUG LOGS (pour voir ce qui se passe dans la console Docker)
    print(f"📥 Donnée reçue : {data.dict()}")

    # MODE MOCK (si pipeline cassé ou absent) 
    if pipeline is None:
        import random
        return {
            "prediction": bool(random.choice([True, False])),
            "churn_probability": round(random.random(), 2),
            "status": "MOCK_MODE (Pipeline non chargé)"
        }
    
    # MODE REEL 
    try:
        input_df = pd.DataFrame([data.dict()])
        
        # nettoyage et renommage (important car colonne avec un espace dedans)
        # on supprime l'ID
        if 'CustomerID' in input_df.columns:
            input_df = input_df.drop(columns=['CustomerID'])
            
        # ⚠️ on remet les espaces que python avait remplacés par des _
        # verif si d'autres colonnes ont des espaces
        input_df = input_df.rename(columns={
            "Usage_Frequency": "Usage Frequency", 
            "Support_Calls": "Support Calls",
            "Payment_Delay": "Payment Delay",
            "Subscription_Type": "Subscription Type",
            "Contract_Length": "Contract Length",
            "Total_Spend": "Total Spend",
            "Last_Interaction": "Last Interaction"
        })

        print(f"📊 Colonnes envoyées au Pipeline : {input_df.columns.tolist()}")
            
        # transfo (PCA)
        data_pca = pipeline.transform(input_df)
        
        # prédiction (mock ici car pas encore model.pickle)
        import random
        proba = random.random()
        
        return {
            "prediction": proba > 0.5,
            "churn_probability": proba,
            "pca_vector": data_pca.tolist()
        }
    except Exception as e:
        # on imprime l'erreur exacte dans les logs docker
        import traceback
        traceback.print_exc()
        print(f"❌ ERREUR PREDICT : {e}")
        raise HTTPException(status_code=500, detail=f"Erreur interne: {e}")

@app.post("/feedback")
def save_feedback(feedback: FeedbackData):
    global pipeline
    
    # on a besoin du pipeline pour transfo les données brutes en PCA avant la sauvegarde dans prod_data.csv
    if pipeline is None:
        return {"status": "Erreur: Impossible de sauvegarder le feedback sans le pipeline (Format PCA requis)"}

    try:
        # transfo
        input_df = pd.DataFrame([feedback.customer_data.dict()])
        if 'CustomerID' in input_df.columns:
            input_df = input_df.drop(columns=['CustomerID'])
            
        # ⚠️ on remet les espaces que python avait remplacés par des _
        input_df = input_df.rename(columns={
            "Usage_Frequency": "Usage Frequency", 
            "Support_Calls": "Support Calls",
            "Payment_Delay": "Payment Delay",
            "Subscription_Type": "Subscription Type",
            "Contract_Length": "Contract Length",
            "Total_Spend": "Total Spend",
            "Last_Interaction": "Last Interaction"
        })
        
        data_pca = pipeline.transform(input_df) # renvoie un numpy array
        
        # prépa de la ligne (PCA_1...PCA_10 + prediction + target)
        # data_pca[0] est le vecteur de 10 chiffres
        row = list(data_pca[0])

        # on ajoute la prédiction originale (1 ou 0)
        row.append(1 if feedback.model_prediction else 0)
        
        # on ajoute la target (la valeur reel verifier par l'humain dans le front)
        # si l'utilisateur dit "Prédiction correcte", alors target = prediction    -> verif la logique car pas sur opti
        # sinon, target = l'inverse de la prediction
        if feedback.correct_prediction:
            target_value = 1 if feedback.model_prediction else 0
        else:
            target_value = 0 if feedback.model_prediction else 1
        row.append(target_value)

        # ecriture dans le CSV
        file_exists = os.path.isfile(PROD_DATA_PATH)
        
        with open(PROD_DATA_PATH, 'a', newline='') as f:
            writer = csv.writer(f)
            # si fichier nouveau, on écrit l'entête PCA_1...PCA_10,prediction,target
            if not file_exists:
                header = [f"PCA_{i+1}" for i in range(len(row)-1)] + ["prediction", "target"]
                writer.writerow(header)
            
            writer.writerow(row)
            
        return {"status": "Feedback enregistré", "rows_count": sum(1 for line in open(PROD_DATA_PATH))}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur sauvegarde: {e}")