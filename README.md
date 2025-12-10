# 🐳 Lancement du Projet avec Docker
### 1. Prérequis

    Avoir Docker Desktop installé et lancé.

    S'assurer que les fichiers de données sont présents :

        data/ref_data.csv (Données de référence)

        artifacts/embedding_pipeline.pickle (Pipeline PCA)

### 2. Commandes de démarrage

Exécutez ces commandes depuis la racine du projet :

```
# 1. Lancer l'API Backend (Port 8080)
docker compose -f serving/docker-compose.yml up -d --build

# 2. Lancer l'Interface Utilisateur (Port 8081)
docker compose -f webapp/docker-compose.yml up -d --build

# 3. Lancer le Dashboard de Monitoring (Port 8082)
docker compose -f reporting/docker-compose.yml up -d --build
```

### 3. Accès aux Services

Service	URL	Description
Webapp (Streamlit)	http://localhost:8081	Interface pour prédire et envoyer du feedback.

(PAS ENCORE IMPLEMENTER) API Docs (Swagger)	http://localhost:8080/docs	Documentation technique de l'API.

Reporting (Evidently)	http://localhost:8082	Dashboard de surveillance du Data Drift.

### 4. Commandes utiles

Voir les logs (en cas d'erreur) :

```
docker logs -f serving-api
docker logs -f reporting
```

Arrêter tous les conteneurs :

```
docker stop $(docker ps -q)
```