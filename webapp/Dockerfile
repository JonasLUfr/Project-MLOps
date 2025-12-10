# webapp/Dockerfile
FROM python:3.10-slim

WORKDIR /app

# copie le fichier des dépendances
COPY requirements.txt .

# installe les dépendances (streamlit, requests, pandas...)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY api.py .

# Streamlit tourne par défaut sur le port 8501, mais le tp demande 8081
# donc on force le port au lancement
CMD ["streamlit", "run", "api.py", "--server.port=8081", "--server.address=0.0.0.0"]