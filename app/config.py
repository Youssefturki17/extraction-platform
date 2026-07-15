"""
config.py — Centralized configuration constants for the extraction platform.
All environment-wide settings live here; import from this module instead of
hard-coding values in service or route files.
"""

import os

# ---------------------------------------------------------------------------
# Base directories
# ---------------------------------------------------------------------------
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
OUTPUT_FOLDER = os.path.join(BASE_DIR, "outputs")

# ---------------------------------------------------------------------------
# Flask / upload constraints
# ---------------------------------------------------------------------------
MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100 MB

# ---------------------------------------------------------------------------
# Text-chunking parameters (reserved for future use)
# ---------------------------------------------------------------------------
CHUNK_SIZE = 1000   # number of characters per chunk
OVERLAP    = 200    # overlap between consecutive chunks

# ---------------------------------------------------------------------------
# Supported extraction models
# ---------------------------------------------------------------------------
SUPPORTED_MODELS = ["docling", "mineru", "paddle"]

# ---------------------------------------------------------------------------
# Database — PostgreSQL uniquement (SQLite supprimé)
# ---------------------------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise EnvironmentError(
        "La variable d'environnement DATABASE_URL n'est pas définie.\n"
        "Exemple : postgresql+psycopg://postgres:postgres@localhost:5433/fininfo_db\n"
        "Définissez-la avant de lancer l'application."
    )
