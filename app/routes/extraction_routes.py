import uuid, os, json, math
from flask import Blueprint, request, jsonify, render_template, Response, current_app
from app.models import db, Job, Extraction

bp = Blueprint("api", __name__, template_folder="../templates")

def _safe_json(obj):
    """Sérialise en JSON en remplaçant NaN/Inf par null (valide en JSON)."""
    def sanitize(o):
        if isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
            return None
        if isinstance(o, dict):
            return {k: sanitize(v) for k, v in o.items()}
        if isinstance(o, list):
            return [sanitize(v) for v in o]
        return o
    return Response(
        json.dumps(sanitize(obj), ensure_ascii=False),
        mimetype="application/json"
    )


@bp.route("/")
def index():
    return jsonify({"status": "ok", "message": "API en ligne"})

@bp.route("/ui")
def ui():
    return render_template("index.html")


import threading

def process_job(app, job_id, path, model):
    with app.app_context():
        try:
            from app.services.extraction_service import ExtractionPipeline
            result = ExtractionPipeline().run(path, model)
            
            job = db.session.get(Job, job_id)
            if job:
                job.status = "done"
                job.nb_tableaux = result.get("nb_tableaux", 0)
                text = result.get("text", "")
                job.nb_mots = len(text.split()) if text else 0
                job.duration_seconds = result.get("duration_seconds", 0.0)
                job.output_file = result.get("output_file")
                
                # Optional: create Extraction records if possible
                tables = result.get("tables", [])
                for i, table in enumerate(tables):
                    ext = Extraction(
                        job_id=job_id,
                        table_index=i,
                        row_count=len(list(table.values())[0]) if isinstance(table, dict) and table else 0,
                        col_count=len(table) if isinstance(table, dict) else 0
                    )
                    db.session.add(ext)
                
                db.session.commit()
        except Exception as e:
            job = db.session.get(Job, job_id)
            if job:
                job.status = "error"
                job.error_message = str(e)
                db.session.commit()

@bp.route("/upload", methods=["POST"])
def upload():
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "Aucun fichier envoyé"}), 400
    model = request.form.get("model", "docling")
    job_id = str(uuid.uuid4())
    path = os.path.join("uploads", f"{job_id}_{file.filename}")
    file.save(path)
    
    job = Job(job_id=job_id, filename=file.filename, model=model, status="processing")
    db.session.add(job)
    db.session.commit()
    
    # Lancement de l'extraction en arrière-plan pour ne pas bloquer l'UI
    app = current_app._get_current_object()
    thread = threading.Thread(target=process_job, args=(app, job_id, path, model))
    thread.start()
    
    return jsonify({"job_id": job_id})

@bp.route("/status/<job_id>")
def status(job_id):
    job = db.session.get(Job, job_id)
    if not job:
        return jsonify({"error": "job introuvable"}), 404
    return jsonify({"status": job.status})

@bp.route("/result/<job_id>")
def result(job_id):
    job = db.session.get(Job, job_id)
    if not job:
        return jsonify({"error": "job introuvable"}), 404
        
    if job.status == "processing":
        return jsonify({"status": "processing"})
        
    if job.status == "error":
        return jsonify({"status": "error", "message": job.error_message})
        
    if job.status == "done":
        if job.output_file and os.path.exists(job.output_file):
            with open(job.output_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return _safe_json({"status": "done", "result": data})
        else:
            return jsonify({"status": "error", "message": "Fichier de résultat introuvable"})
            
    return jsonify({"status": "unknown"})

@bp.route("/history")
def history():
    jobs = Job.query.order_by(Job.created_at.desc()).limit(50).all()
    results = []
    for j in jobs:
        results.append({
            "job_id": j.job_id,
            "filename": j.filename,
            "model": j.model,
            "status": j.status,
            "nb_tableaux": j.nb_tableaux,
            "nb_mots": j.nb_mots,
            "duration_seconds": j.duration_seconds,
            "created_at": j.created_at.isoformat() if j.created_at else None
        })
    return jsonify({"history": results})
