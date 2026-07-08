# Models package
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

from app.models.document import ExtractionResult, Job, Extraction

__all__ = ["ExtractionResult", "Job", "Extraction", "db"]
