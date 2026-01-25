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

## Fichiers modifiés
serving/docker-compose.yml
webapp/api.py
webapp/docker-compose.yml
## Nouveaux fichiers
n8n/
├── docker-compose.yml
├── workflows/
│ └── analyze-email.json



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

La webapp permet déjà de :

-corriger la prédiction,

-envoyer un feedback structuré.

Étape suivante :

-endpoint n8n /feedback,

-insertion en base,

-enrichissement du dataset.

### 10. Ré-entraînement automatique (à implémenter)

Objectif :

Lancer quotidiennement un entraînement à partir des ajouts en base.

Implémentation prévue avec n8n :
-Cron Trigger
-Lecture des nouveaux exemples
-Ré-entraînement
-Versioning du modèle
-Redéploiement du serving


### 11. RAG (à implémenter)

Si l’email est détecté comme phishing :
-appel à un service LLM,
-génération de conseils contextualisés.

n8n permettra d’orchestrer ce module sans modifier la webapp.