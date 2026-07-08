"""
document.py — Data models for the extraction platform.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExtractionResult:
    """Represents the structured output of an extraction pipeline run."""

    model: str
    text: str = ""
    tables: list[Any] = field(default_factory=list)
    texte_par_page: list[dict] = field(default_factory=list)
    tableaux_par_page: list[dict] = field(default_factory=list)
    nb_tableaux: int = 0
    nb_pages: int = 0
    duration_seconds: float = 0.0
    output_file: str = ""
    txt_output_file: str = ""

from datetime import datetime
from app.models import db

class Job(db.Model):
    __tablename__ = 'jobs'
    
    job_id = db.Column(db.String, primary_key=True)
    filename = db.Column(db.String, nullable=True)
    model = db.Column(db.String, nullable=True)
    status = db.Column(db.String, nullable=True) # processing, done, error
    nb_tableaux = db.Column(db.Integer, default=0)
    nb_mots = db.Column(db.Integer, default=0)
    duration_seconds = db.Column(db.Float, default=0.0)
    output_file = db.Column(db.Text, nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    extractions = db.relationship('Extraction', backref='job', lazy=True)

class Extraction(db.Model):
    __tablename__ = 'extractions'
    
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.String, db.ForeignKey('jobs.job_id'), nullable=False)
    page_number = db.Column(db.Integer, nullable=True)
    table_index = db.Column(db.Integer, nullable=True)
    row_count = db.Column(db.Integer, nullable=True)
    col_count = db.Column(db.Integer, nullable=True)
