import os
import re
import time
import json
import argparse
from datetime import datetime

# Importer de maniere relative ou modifier le PYTHONPATH
# Pour executer : python -m benchmark.run_benchmark
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.extraction_service import ExtractionPipeline


def count_words(text: str) -> int:
    """Compte le nombre de mots dans un texte."""
    if not text:
        return 0
    # Supprime le HTML/Markdown résiduel avant de compter
    text_clean = re.sub(r'<[^>]+>', ' ', text)          # balises HTML
    text_clean = re.sub(r'[#*_`|~>\-]+', ' ', text_clean) # symboles Markdown
    text_clean = re.sub(r'\s+', ' ', text_clean).strip()
    return len(text_clean.split())


def count_unique_words(text: str) -> int:
    """Compte le nombre de mots uniques (vocabulaire distinct)."""
    if not text:
        return 0
    text_clean = re.sub(r'<[^>]+>', ' ', text)
    text_clean = re.sub(r'[#*_`|~>\-]+', ' ', text_clean)
    words = re.findall(r'\b[a-zA-ZÀ-ÿ]{3,}\b', text_clean.lower())
    return len(set(words))


def count_tables(res: dict) -> int:
    """Compte le nombre de tableaux détectés dans le résultat."""
    tables = res.get("tables", [])
    return len(tables)


def text_quality_score(text: str) -> dict:
    """
    Calcule des métriques de qualité du texte extrait :
    - nb_mots         : nombre total de mots
    - nb_mots_uniques : vocabulaire distinct
    - ratio_chiffres  : proportion de tokens numériques (utile pour les données INSEE)
    - lignes_vides    : nombre de lignes vides consécutives (indice de fragmentation)
    - score_100       : score synthétique /100
    """
    if not text:
        return {"nb_mots": 0, "nb_mots_uniques": 0, "ratio_chiffres": 0.0,
                "lignes_vides": 0, "score_100": 0}

    nb_mots = count_words(text)
    nb_mots_uniques = count_unique_words(text)

    # Ratio de nombres dans le texte brut (données tabulaires = beaucoup de chiffres)
    tokens = text.split()
    nb_nombres = sum(1 for t in tokens if re.match(r'^\d[\d\s]*$', t.strip()))
    ratio_chiffres = round(nb_nombres / max(len(tokens), 1), 3)

    # Lignes vides consécutives (fragmentation du texte)
    lignes = text.split('\n')
    lignes_vides = sum(1 for l in lignes if l.strip() == '')

    # Score synthétique /100 :
    # + 40 pts si > 5000 mots (document complet)
    # + 30 pts si > 500 mots uniques (diversité lexicale)
    # + 20 pts si ratio chiffres > 0.05 (données numériques bien captées)
    # + 10 pts si pas trop de lignes vides (< 30% des lignes)
    score = 0
    score += min(40, int(nb_mots / 5000 * 40))
    score += min(30, int(nb_mots_uniques / 500 * 30))
    score += 20 if ratio_chiffres > 0.05 else int(ratio_chiffres / 0.05 * 20)
    ratio_vides = lignes_vides / max(len(lignes), 1)
    score += 10 if ratio_vides < 0.30 else 0

    return {
        "nb_mots": nb_mots,
        "nb_mots_uniques": nb_mots_uniques,
        "ratio_chiffres": ratio_chiffres,
        "lignes_vides": lignes_vides,
        "score_100": min(score, 100)
    }


def print_summary(results: list):
    """Affiche un tableau de comparaison dans le terminal."""
    print("\n" + "="*80)
    print(f"{'MODELE':<12} {'FICHIER':<20} {'DUREE':>8} {'TABLEAUX':>10} {'MOTS':>8} "
          f"{'VOCAB':>7} {'SCORE/100':>10} {'STATUT':>8}")
    print("-"*80)
    for r in results:
        if r["status"] == "success":
            q = r.get("qualite_texte", {})
            print(f"{r['model']:<12} {r['filename']:<20} "
                  f"{r['duration_seconds']:>7.1f}s "
                  f"{r.get('nb_tableaux', 0):>10} "
                  f"{q.get('nb_mots', 0):>8} "
                  f"{q.get('nb_mots_uniques', 0):>7} "
                  f"{q.get('score_100', 0):>10} "
                  f"{'OK':>8}")
        else:
            print(f"{r['model']:<12} {r['filename']:<20} {'N/A':>8} {'N/A':>10} "
                  f"{'N/A':>8} {'N/A':>7} {'N/A':>10} {'ERREUR':>8}")
    print("="*80)


def run_benchmark(dataset_dir, models_to_test):
    print(f"=== Benchmark d'Extraction PDF ===")
    print(f"Dossier source : {dataset_dir}")
    print(f"Modeles : {models_to_test}\n")
    
    pipeline = ExtractionPipeline()
    results = []
    
    if not os.path.exists(dataset_dir):
        print(f"Dossier {dataset_dir} introuvable.")
        return
        
    files = [
        os.path.join(dataset_dir, f)
        for f in os.listdir(dataset_dir)
        if os.path.isfile(os.path.join(dataset_dir, f))
    ]
    
    if not files:
        print("Aucun fichier a traiter pour le benchmark.")
        return

    for model_name in models_to_test:
        print(f"\nEvaluation du modele : {model_name}")
        for file_path in files:
            filename = os.path.basename(file_path)
            print(f"  Traitement de {filename}...", end=" ", flush=True)
            try:
                start_time = time.time()
                res = pipeline.run(file_path, model_name)
                duration = round(time.time() - start_time, 2)

                nb_tableaux = count_tables(res)
                qualite = text_quality_score(res.get("text", ""))

                print(f"OK ({duration:.1f}s | {nb_tableaux} tableaux | {qualite['nb_mots']} mots | score={qualite['score_100']}/100)")

                results.append({
                    "timestamp": datetime.now().isoformat(),
                    "model": model_name,
                    "filename": filename,
                    "duration_seconds": duration,
                    "nb_tableaux": nb_tableaux,
                    "qualite_texte": qualite,
                    "status": "success"
                })
            except Exception as e:
                print(f"ERREUR: {str(e)[:60]}")
                results.append({
                    "timestamp": datetime.now().isoformat(),
                    "model": model_name,
                    "filename": filename,
                    "error": str(e),
                    "status": "failed"
                })

    print_summary(results)
                
    # Sauvegarde des resultats du benchmark
    output_dir = os.path.join(os.path.dirname(__file__), 'results')
    os.makedirs(output_dir, exist_ok=True)
    
    output_file = os.path.join(output_dir, f"benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=4)
        
    print(f"\nResultats enregistres dans : {output_file}")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Lancer le benchmark d'extraction.")
    parser.add_argument("--dataset", type=str, default="benchmark/pdfs",
                        help="Dossier contenant les fichiers de test")
    parser.add_argument("--models", nargs="+", default=["docling", "mineru"],
                        help="Liste des modeles a tester")
    
    args = parser.parse_args()
    os.makedirs(args.dataset, exist_ok=True)
    run_benchmark(args.dataset, args.models)
