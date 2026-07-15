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
        Orchestre le traitement d'un fichier par un modele donne.

        Optimisation : split adaptatif avec chevauchement d'1 page entre les chunks,
        suivi d'une déduplication des tableaux extraits.
        """
        if model_name not in self.models:
            raise ValueError(f"Modele '{model_name}' non supporte. Choisissez parmi : {list(self.models.keys())}")

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Le fichier {file_path} n'existe pas.")

        extract_fn = self.models[model_name]

        import time as _time
        t0 = _time.time()

        # ── Étape 1 : Split adaptatif du PDF en chunks avec chevauchement ────
        from app.utils.pdf_utils import split_pdf_adaptive, deduplicate_tables
        chunk_paths = split_pdf_adaptive(file_path)

        # ── Étape 2 : Extraction de chaque chunk et fusion des résultats ─────
        all_texte_par_page: list[dict] = []
        all_tableaux_par_page: list[dict] = []
        all_tables_flat: list = []
        all_text_parts: list[str] = []
        total_nb_pages = 0

        # Track pages already seen to avoid duplicates from overlap
        seen_pages: set[int] = set()
        # We also collect page-level seen sets for tableaux to avoid overlap dupes
        seen_text_pages: set[int] = set()
        seen_table_pages: set[int] = set()

        for chunk_path in chunk_paths:
            try:
                chunk_result = extract_fn(chunk_path)
            except Exception as chunk_err:
                # Log chunk error but continue processing remaining chunks
                print(f"[WARNING] Échec extraction chunk {chunk_path}: {chunk_err}")
                continue

            # Merge texte_par_page (skip pages already collected from a previous chunk)
            for page_entry in chunk_result.get("texte_par_page", []):
                page_num = page_entry.get("page")
                if page_num not in seen_text_pages:
                    all_texte_par_page.append(page_entry)
                    seen_text_pages.add(page_num)
                    # Rebuild full text from individual pages
                    all_text_parts.append(f"[Page {page_num}]\n{page_entry.get('contenu', '')}")

            # Merge tableaux_par_page (skip pages already collected)
            for tab_entry in chunk_result.get("tableaux_par_page", []):
                page_num = tab_entry.get("page")
                if page_num not in seen_table_pages:
                    all_tableaux_par_page.append(tab_entry)
                    seen_table_pages.add(page_num)
                    # Collect raw tables for global deduplication
                    all_tables_flat.extend(tab_entry.get("tableaux", []))

            # Track max page number seen
            chunk_nb_pages = chunk_result.get("nb_pages", 0)
            if chunk_nb_pages > total_nb_pages:
                total_nb_pages = chunk_nb_pages

        # Sort merged page data by page number for consistent ordering
        all_texte_par_page.sort(key=lambda x: x.get("page", 0))
        all_tableaux_par_page.sort(key=lambda x: x.get("page", 0))

        # Rebuild combined full text from sorted pages
        combined_text = "\n\n".join(all_text_parts)
        # Re-sort text parts by page number
        text_parts_sorted = sorted(
            [p for p in all_texte_par_page],
            key=lambda x: x.get("page", 0)
        )
        combined_text = "\n\n".join(
            f"[Page {p['page']}]\n{p.get('contenu', '')}"
            for p in text_parts_sorted
        )

        # ── Étape 3 : Déduplication globale des tableaux ──────────────────────
        all_tables_flat = deduplicate_tables(all_tables_flat)

        duration = round(_time.time() - t0, 2)

        # ── Étape 4 : Nettoyage du texte ──────────────────────────────────────
        from app.utils.text_utils import clean_extracted_text
        combined_text = clean_extracted_text(combined_text)

        # ── Étape 5 : Suppression des fichiers chunks temporaires ─────────────
        for chunk_path in chunk_paths:
            # Ne pas supprimer le fichier original (si aucun split n'a eu lieu)
            if chunk_path != file_path and os.path.exists(chunk_path):
                try:
                    os.remove(chunk_path)
                except Exception:
                    pass  # Non-bloquant : la suppression est best-effort

        # ── Étape 6 : Sauvegarde du résultat ─────────────────────────────────
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

        nb_tableaux_total = sum(
            len(tab_entry.get("tableaux", []))
            for tab_entry in all_tableaux_par_page
        )

        serializable_result = {
            "text": combined_text,
            "tables": [df_to_serializable(t) for t in all_tables_flat],
            "model": model_name,
            # Structured page-level fields
            "texte_par_page": all_texte_par_page,
            "tableaux_par_page": all_tableaux_par_page,
            "nb_tableaux": nb_tableaux_total,
            "nb_pages": total_nb_pages,
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
