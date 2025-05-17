# Utilise une image Python officielle
FROM python:3.11-slim

# Répertoire de travail
WORKDIR /app

# Copier les fichiers du script
COPY requirements.txt ./
COPY strava-sync.py ./

# Installer les dépendances
RUN pip install --no-cache-dir -r requirements.txt

# Point d'entrée par défaut
CMD ["python", "strava-sync.py"]
