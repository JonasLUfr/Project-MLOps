### 1. Objectif du projet

Ce projet met en place une **pipeline MLOps** pour la détection d’emails de phishing, en séparant clairement :

- l’interface utilisateur (Webapp),
- l’inférence du modèle ML (Serving),
- l’orchestration et la logique métier (n8n).

L’architecture est conçue pour supporter :
- l’inférence temps réel,
- la collecte de feedback utilisateur,
- le ré-entraînement périodique,
- l’intégration future d’un module RAG (LLM).



### 2. Architecture générale pour le moment
[ Webapp (Streamlit) ]
        |
        v
[ n8n Webhook ]
        |
        v
[ Serving API (ML model) ]
        |
        v
[ n8n logic (Merge / If / Normalize) ]
        |
        v
[ Response JSON → Webapp ]

Rôle de **n8n** :
- centraliser la logique métier,
- éviter de dupliquer les règles dans le frontend,
- préparer la phase MLOps (BDD, retrain, RAG).



### 3. Modifications apportées

#### Fichiers modifiés
- **serving/api.py** - Ajout des endpoints `/feedback` et `/reload-model`
- **webapp/api.py** - Existant (appelle n8n webhook)
- **webapp/docker-compose.yml** - Existant
- **n8n/docker-compose.yml** - Ajout du service `python-retrain-worker` et montage des volumes
- **scripts/DataModeling.ipynb** - Lecture et concaténation de prod_data.csv avec Phishing_validation_emails.csv

#### Nouveaux fichiers
- **n8n/retrain-model.json** - Workflow n8n pour le réentraînement automatique
- **n8n/retrain_service.py** - Service FastAPI pour exécuter le notebook
- **n8n/RETRAIN_README.md** - Documentation détaillée du réentraînement



### 4. Réseau Docker

Tous les services communiquent via un réseau Docker partagé :

```yaml
networks:
  serving_prod_net:
    external: true
``` 
Les containers sont accessibles par leur container_name :
serving-api
n8n
webapp



### 5. Lancer le projet
5.1 Serving (API ML)

cd serving
docker compose up -d

Endpoint :
http://serving-api:8080/predict

5.2 n8n

cd n8n
docker compose up -d

UI :

http://localhost:5678

Importer le workflow :

--n8n/workflows/analyze-email.json

--activer le workflow (toggle en haut à droite)

Webhook actif :

POST /webhook/analyze


5.3 Webapp

cd webapp
docker compose up -d

UI :
http://localhost:8081


### 6. Webapp → n8n → Serving

Dans webapp/api.py :

API_URL = "http://n8n:5678/webhook/analyze"

Flux :

1.L’utilisateur soumet un email

2.La webapp appelle n8n

3.n8n appelle le modèle ML

4.n8n renvoie la réponse à la webapp

### 7. Workflow n8n – Analyse
Étapes du workflow analyze-email

1.Receive Email Text (Webhook)
Input :

{ "email_text": "..." }

2.HTTP Request
Appel du modèle ML :

POST http://serving-api:8080/predict

3.Merge (avant If)
Fusion :
-texte de l’email
-prédiction ML

➜ Prépare l’insertion future en base de données.

4.Normalize
Mise en forme uniforme des champs.

5.If
Condition :
prediction == "Phishing Email"


6.Edit Fields (True / False)
Ajout de champs métier (rag_advice mocké actuellement).


7.Respond to Webhook
Retour JSON vers la webapp.

### 9. Feedback utilisateur (prévu)

La webapp permet de :
- corriger la prédiction du modèle,
- envoyer un feedback structuré à l'API.

**Flux :**

1. Utilisateur voit la prédiction (Phishing / Safe)
2. Clique sur "Envoyer la correction" s'il désaccord
3. La webapp appelle `POST /feedback` sur l'API serving
4. L'API sauvegarde dans `data/prod_data.csv`

**Données collectées :**
```csv
email_text,model_prediction,user_correction
"Texte de l'email","Phishing Email","Safe Email"
```

Ces feedbacks sont automatiquement intégrés au réentraînement quotidien.

### 10. Ré-entraînement automatique

Un nouveau workflow automatisé a été implémenté pour le ré-entraînement du modèle.

#### Architecture du Retrain Workflow

**Deux déclencheurs :**
1. **Manual Trigger** - Lancer le réentraînement à la demande depuis n8n
2. **Schedule Daily Trigger** - Réentraîner automatiquement tous les jours (toutes les 24h)

**Flux du workflow :**

```
[Manual Trigger / Schedule Trigger]
            ↓
[Execute Notebook Training] (HTTP POST)
            ↓
[Check Success] (vérifier status == "success")
       ↙         ↘
   TRUE         FALSE
     ↓             ↓
[Reload Model]  [Error Response]
     ↓
[Success Response]
```

#### Étapes détaillées

1. **Execute Notebook Training**
   - Appel HTTP POST au service Python : `http://python-retrain-worker:9000/retrain`
   - Lance l'exécution du notebook [scripts/DataModeling.ipynb](../scripts/DataModeling.ipynb)

2. **Script de réentraînement (DataModeling.ipynb)**
   - Lit `data/prod_data.csv` (feedbacks utilisateurs)
   - Lit `data/Phishing_validation_emails.csv` (données de référence)
   - Concatène les deux sources de données
   - Entraîne un modèle TF-IDF + LogisticRegression
   - Sauvegarde dans `artifacts/phishing_tfidf_logreg.joblib`
   - Génère les métriques dans `artifacts/metrics.json`

3. **Check Success**
   - Vérifie que le réentraînement s'est bien déroulé (status == "success")

4. **Reload Model in API** (si succès)
   - Appel HTTP POST à `http://serving-api:8080/reload-model`
   - L'API serving recharge le nouveau modèle en mémoire sans redémarrer

5. **Response**
   - En cas de succès : message de confirmation avec timestamp
   - En cas d'erreur : détails de l'erreur

#### Service de réentraînement

Un service FastAPI dédié au réentraînement tourne dans le conteneur `python-retrain-worker` :

```
Port: 9000
Endpoint: POST /retrain
Dépendances: pandas, scikit-learn, joblib, jupyter, nbconvert
```

#### Feedback utilisateur

L'endpoint `/feedback` de l'API serving collecte les corrections utilisateurs :

```
POST /feedback
{
  "email_text": "...",
  "model_prediction": "Phishing Email",
  "user_correction": "Safe Email"
}
```

Les feedbacks sont sauvegardés dans `data/prod_data.csv` et utilisés au prochain réentraînement.

#### Configuration Docker

Trois conteneurs travaillent ensemble :

**1. n8n** (5678)
- Orchestration et déclenchement

**2. python-retrain-worker** (9000)
- Exécution du notebook
- Service FastAPI pour le réentraînement

**3. serving-api** (8080)
- Inférence du modèle
- Rechargement du modèle

Tous sont sur le réseau `serving_prod_net`.

#### Lancer les services

```bash
# Redémarrer n8n (avec volumes des données)
docker compose -f n8n/docker-compose.yml up -d

# Redémarrer l'API serving (avec endpoint /reload-model)
docker compose -f serving/docker-compose.yml up -d --build

# Importer le workflow dans n8n
# Menu → Import from File → n8n/retrain-model.json
# Activer le workflow (toggle en haut à droite)
```

#### Tester manuellement

```bash
# Lancer le réentraînement via l'API
curl -X POST http://localhost:9000/retrain

# Recharger le modèle dans l'API serving
curl -X POST http://localhost:8080/reload-model

# Vérifier les métriques
cat artifacts/metrics.json
```

#### Logs

- **Logs du workflow n8n** : Interface n8n → Executions
- **Logs du service Python** : `docker logs python-retrain-worker`
- **Logs de l'API serving** : `docker logs serving-api`


### 11. RAG (à implémenter)

Si l’email est détecté comme phishing :
-appel à un service LLM,
-génération de conseils contextualisés.

n8n permettra d’orchestrer ce module sans modifier la webapp.