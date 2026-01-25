FROM python:3.10-slim

WORKDIR /app

# Install des outils de base
RUN apt-get update && apt-get install -y build-essential --no-install-recommends && rm -rf /var/lib/apt/lists/*

# Opti PyTorch CPU avant le reste -> évite de télécharger drivers Nvidia inutiles (5Go)
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu

# Copie et installation du reste des dépendances
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copie du code
COPY app_optimized.py .

# Commande de lancement
CMD ["python", "app_optimized.py"]