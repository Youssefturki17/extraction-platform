import uuid, os, json, math
from flask import Blueprint, request, jsonify, send_from_directory, Response

bp = Blueprint("api", __name__)
JOBS = {}


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
    return send_from_directory("static", "index.html")


import threading

def process_job(job_id, path, model):
    try:
        from app.pipeline import ExtractionPipeline
        result = ExtractionPipeline().run(path, model)
        JOBS[job_id] = {"status": "done", "result": result}
    except Exception as e:
        JOBS[job_id] = {"status": "error", "message": str(e)}

@bp.route("/upload", methods=["POST"])
def upload():
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "Aucun fichier envoyé"}), 400
    model = request.form.get("model", "docling")
    job_id = str(uuid.uuid4())
    path = os.path.join("uploads", f"{job_id}_{file.filename}")
    file.save(path)
    
    JOBS[job_id] = {"status": "processing"}
    
    # Lancement de l'extraction en arrière-plan pour ne pas bloquer l'UI
    thread = threading.Thread(target=process_job, args=(job_id, path, model))
    thread.start()
    
    return jsonify({"job_id": job_id})

@bp.route("/status/<job_id>")
def status(job_id):
    job = JOBS.get(job_id)
    if not job:
        return jsonify({"error": "job introuvable"}), 404
    return jsonify({"status": job["status"]})

@bp.route("/result/<job_id>")
def result(job_id):
    job = JOBS.get(job_id)
    if not job:
        return jsonify({"error": "job introuvable"}), 404
    return _safe_json(job)