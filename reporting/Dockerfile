FROM python:3.10-slim

WORKDIR /app

# copie le fichier des dépendances
COPY requirements.txt .

# installe les dépendances (scikit-learn, sniffio, evidently...)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY project.py .

# création du dossier workspace pour la BDD Evidently
RUN mkdir workspace

# on génère le rapport PUIS on lance l'UI
CMD python project.py && evidently ui --workspace workspace --host 0.0.0.0 --port 8082