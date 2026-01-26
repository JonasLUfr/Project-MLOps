FROM python:3.10-slim

WORKDIR /app

# Install que le nécessaire + nettoie le cache APT directement
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Install de PyTorch CPU avant le reste -> évite de télécharger drivers Nvidia inutiles (5Go)
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu

# Install des dépendances (version fixes pour éviter les tests infinis)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Téléchargement du modèle dans code .py pendant la construction de l'image (opti temps)
RUN python -c "from llama_index.embeddings.huggingface import HuggingFaceEmbedding; HuggingFaceEmbedding(model_name='BAAI/bge-small-en-v1.5')._model"

# Copie du code
COPY app_optimized.py .

CMD ["python", "app_optimized.py"]