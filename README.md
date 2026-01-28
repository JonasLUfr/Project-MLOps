# Phishing Detector - MLOps

Ce projet déploie une architecture complète de détection de Phishing incluant une Webapp, une API d'inférence, un module RAG (LLM) et un orchestrateur n8n.

# Demo
<img width="1355" height="625" alt="image" src="https://github.com/user-attachments/assets/eea6f99f-793f-4770-80c6-f6ac7c6b93db" />  
<img width="833" height="791" alt="image" src="https://github.com/user-attachments/assets/c1a67358-6894-4415-8e4a-1d200520d552" />  

# Lancement du Projet avec Docker
### 1. Prérequis

    Avoir Docker Desktop installé et lancé.

    S'assurer que les fichiers de données sont présents :

        data/ref_data.csv (Données de référence)

        artifacts/embedding_pipeline.pickle (Pipeline PCA)

    Créer/Mettre le fichier rag/.env contenant les clés API (MongoDB, Groq) pour le service RAG.

### 2. Commandes de démarrage

Exécutez ces commandes depuis la racine du projet :

```
# 1. Lancer l'API Backend (Port 8080)
docker compose -f serving/docker-compose.yml up -d --build

# 2. Lancer le service RAG (LLM + Vector DB) (Port 8083) (vérifier pour le fichier rag/.env avant)
docker compose -f rag/docker-compose.yml up -d --build

# 3. Lancer l'Orchestrateur n8n (Port 5678)
docker compose -f n8n/docker-compose.yml up -d --build

# 4. Lancer l'Interface Utilisateur Streamlit (Port 8081)
docker compose -f webapp/docker-compose.yml up -d --build

# 5. Lancer le Dashboard de Monitoring Evidently (Port 8082)
docker compose -f reporting/docker-compose.yml up -d --build
```

### 3. Configuration N8N (Obligatoire au premier lancement)

Pour que l'application fonctionne, vous devez charger le workflow dans n8n :

    Accédez à http://localhost:5678

    Créez un compte administrateur local (email/pass quelconque)

    Allez dans le menu Workflows > Import from File (les 3 petit point en haut à droite)

    Sélectionnez le fichier analyze-email.json (situé dans le folder n8n/)

    Cliquez sur le bouton "Publish" (ou activez le toggle "Inactive" → "Active") en haut à droite

        Si ce bouton n'est pas activé, la Webapp recevra une erreur 404

### 4. Accès aux Services

Service                 URL                     Description

Webapp (Streamlit)   	http://localhost:8081	Interface pour prédire et envoyer du feedback

(PAS ENCORE IMPLEMENTER) API Docs (Swagger)	http://localhost:8080/docs	Documentation Swagger de l'API de prédiction

RAG API                	http://localhost:8083	API interne du Chatbot/Explication (LLM)

Reporting (Evidently)	http://localhost:8082	Dashboard surveillance du Data Drift

### 5. Commandes utiles

Voir les logs (en cas d'erreur) :

```
# Pour voir ce qui se passe dans le RAG
docker logs -f rag-api

# Pour voir les erreurs de n8n
docker logs -f xyf-n8n-2

# Pour l'API de prédiction
docker logs -f serving-api
```

Arrêter tous les conteneurs :

```
docker stop $(docker ps -q)
```


Voir tous les conteneurs actifs :

```
docker ps
```
