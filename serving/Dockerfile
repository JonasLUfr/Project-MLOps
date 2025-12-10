FROM python:3.10-slim

WORKDIR /app

# copie le fichier des dépendances
COPY requirements.txt .

# installe les dépendances (pandas, scikit-learn, FastAPI...)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# copie le code de l'API
COPY api.py .

# lance le serveur
CMD uvicorn api:app --host 0.0.0.0 --port 8080