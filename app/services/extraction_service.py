import os
import json
import math
import pandas as pd

from app.config import OUTPUT_FOLDER

os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# Import des fonctions extract() de chaque service
from app.services import docling_service, mineru_service

_MODELS = {
    "mineru": mineru_service.extract,
    "docling": docling_service.extract,
}

# PaddleOCR n'est pas disponible sur Windows/Python 3.13 - on l'exclut silencieusement
try:
    from app.services import paddle_service
    _MODELS["paddle"] = paddle_service.extract
except Exception:
    pass


class ExtractionPipeline:
    def __init__(self):
        self.models = _MODELS

    def run(self, file_path: str, model_name: str) -> dict:
        """
        Orchestre le traitement d'un fichier par un modele donne
        """
        if model_name not in self.models:
            raise ValueError(f"Modele '{model_name}' non supporte. Choisissez parmi : {list(self.models.keys())}")
            
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Le fichier {file_path} n'existe pas.")

        extract_fn = self.models[model_name]
        
        import time as _time
        t0 = _time.time()

        # Execution de la logique d'extraction
        result = extract_fn(file_path)

        duration = round(_time.time() - t0, 2)

        # Nettoyage du texte et conversion des tableaux HTML en Markdown
        from app.utils.text_utils import clean_extracted_text
        if "text" in result:
            result["text"] = clean_extracted_text(result["text"])

        # Sauvegarde du resultat dans le dossier outputs
        filename = os.path.basename(file_path)
        output_filename = f"{os.path.splitext(filename)[0]}_{model_name}_output.json"
        output_path = os.path.join(OUTPUT_FOLDER, output_filename)

        # Les DataFrames ne sont pas JSON-serialisables directement
        # On remplace NaN/Inf par None pour produire du JSON valide
        def df_to_serializable(t):
            if hasattr(t, 'to_dict'):
                # Remplacer NaN par None (JSON: null) pour chaque cellule
                return t.where(pd.notna(t), other=None).to_dict()
            return t

        serializable_result = {
            "text": result.get("text", ""),
            "tables": [df_to_serializable(t) for t in result.get("tables", [])],
            "model": result.get("model", model_name),
            # Structured page-level fields forwarded from model output
            "texte_par_page": result.get("texte_par_page", []),
            "tableaux_par_page": result.get("tableaux_par_page", []),
            "nb_tableaux": result.get("nb_tableaux", 0),
            "nb_pages": result.get("nb_pages", 0),
            "duration_seconds": duration,
        }
        
        # Encodeur de securite : convertit NaN/Inf residuels en None
        class SafeEncoder(json.JSONEncoder):
            def iterencode(self, o, _one_shot=False):
                return super().iterencode(self._sanitize(o), _one_shot)
            def _sanitize(self, obj):
                if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
                    return None
                if isinstance(obj, dict):
                    return {k: self._sanitize(v) for k, v in obj.items()}
                if isinstance(obj, list):
                    return [self._sanitize(v) for v in obj]
                return obj

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(serializable_result, f, ensure_ascii=False, indent=4, cls=SafeEncoder)
            
        # Sauvegarde du texte extrait dans un fichier .txt bien structuré
        txt_output_filename = f"{os.path.splitext(filename)[0]}_{model_name}_output.txt"
        txt_output_path = os.path.join(OUTPUT_FOLDER, txt_output_filename)
        with open(txt_output_path, 'w', encoding='utf-8') as f:
            f.write(serializable_result.get("text", ""))
            
        serializable_result["output_file"] = output_path
        serializable_result["txt_output_file"] = txt_output_path
        
        return serializable_result
