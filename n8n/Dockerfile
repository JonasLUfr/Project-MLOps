FROM n8nio/n8n:latest

USER root

# Installer Python et pip
RUN apt-get update && \
    apt-get install -y python3 python3-pip && \
    rm -rf /var/lib/apt/lists/*

# Installer les dépendances Python pour le réentraînement
RUN pip3 install --no-cache-dir --break-system-packages \
    pandas \
    scikit-learn \
    joblib \
    jupyter \
    nbconvert

USER node
