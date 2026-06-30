import os
import json
import subprocess
import glob
import pandas as pd
from io import StringIO


def _extract_html_from_table_block(block: dict) -> str:
    """
    A top-level table block contains sub-blocks (table_caption, table_body, table_footnote).
    The actual HTML lives in table_body -> lines[0] -> spans[0]['html'].
    """
    for sub in block.get("blocks", []):
        if not isinstance(sub, dict):
            continue
        if sub.get("type") == "table_body":
            lines = sub.get("lines", [])
            if lines and isinstance(lines[0], dict):
                spans = lines[0].get("spans", [])
                if spans and isinstance(spans[0], dict):
                    html = spans[0].get("html", "")
                    if html:
                        return html
    return ""


def _extract_text_from_block(block: dict) -> list[str]:
    """
    Text/title/paragraph blocks: block.lines[] -> line.spans[] -> span['content'].
    """
    texts = []
    for line in block.get("lines", []):
        if not isinstance(line, dict):
            continue
        for span in line.get("spans", []):
            if not isinstance(span, dict):
                continue
            content = span.get("content", "")
            if content and isinstance(content, str):
                texts.append(content.strip())
    return texts


def extract(file_path: str) -> dict:
    """
    Extrait le texte et les tableaux d'un PDF via MinerU CLI, par page.
    Compatible avec la nouvelle structure de sortie MinerU (sous-dossier auto/).
    """
    output_dir = os.path.abspath("outputs/mineru_tmp")
    os.makedirs(output_dir, exist_ok=True)

    file_path_abs = os.path.abspath(file_path)
    base_name = os.path.splitext(os.path.basename(file_path_abs))[0]

    env = os.environ.copy()
    env["HF_HUB_DISABLE_SYMLINKS"] = "1"
    env["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
    env["PYTHONWARNINGS"] = "ignore"

    proc = subprocess.run(
        [
            "mineru",
            "-p", file_path_abs,
            "-o", output_dir,
            "-m", "auto",
            "-b", "pipeline",
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=300,
    )

    # MinerU now outputs under: output_dir / base_name / auto / base_name_middle.json
    # Fallback: search recursively for *_middle.json or *.json
    candidates = [
        os.path.join(output_dir, base_name, "auto", f"{base_name}_middle.json"),
        os.path.join(output_dir, base_name, f"{base_name}_middle.json"),
        os.path.join(output_dir, base_name, f"{base_name}.json"),
    ]
    json_path = None
    for c in candidates:
        if os.path.exists(c):
            json_path = c
            break

    if json_path is None:
        # Last resort: glob for any *_middle.json, then any *.json
        for pattern in [
            os.path.join(output_dir, "**", "*_middle.json"),
            os.path.join(output_dir, "**", "*.json"),
        ]:
            matches = glob.glob(pattern, recursive=True)
            # Exclude content_list files
            matches = [m for m in matches if "content_list" not in m and "model" not in m]
            if matches:
                json_path = max(matches, key=os.path.getmtime)
                break

    if json_path is None:
        stderr_tail = (proc.stderr or "")[-3000:]
        raise RuntimeError(
            f"MinerU n'a produit aucun fichier JSON (exit code {proc.returncode}).\n"
            f"STDERR: {stderr_tail}"
        )

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # data may be a dict with 'pdf_info' key, or directly a list
    if isinstance(data, dict):
        pages = data.get("pdf_info", [])
    elif isinstance(data, list):
        pages = data
    else:
        pages = []

    pages_text: dict[int, list[str]] = {}
    pages_tables: dict[int, list] = {}

    TEXT_TYPES = {"text", "title", "plain_text", "figure_caption",
                  "interline_equation", "footnote", "abandon"}

    for page in pages:
        if not isinstance(page, dict):
            continue
        page_num = page.get("page_idx", 0) + 1

        for block in page.get("preproc_blocks", []):
            if not isinstance(block, dict):
                continue
            btype = block.get("type", "")

            if btype == "table":
                # --- Extract HTML from nested table_body sub-block ---
                html_str = _extract_html_from_table_block(block)
                tbl = html_str  # default: keep raw HTML
                if html_str:
                    try:
                        df_list = pd.read_html(StringIO(html_str))
                        if df_list:
                            tbl = df_list[0].to_csv(index=False)
                    except Exception:
                        tbl = html_str
                if page_num not in pages_tables:
                    pages_tables[page_num] = []
                pages_tables[page_num].append(tbl)

            else:
                # --- Extract text from lines/spans ---
                lines_text = _extract_text_from_block(block)
                if lines_text:
                    if page_num not in pages_text:
                        pages_text[page_num] = []
                    pages_text[page_num].extend(lines_text)

    texte_par_page = [
        {"page": p, "contenu": "\n".join(lignes)}
        for p, lignes in sorted(pages_text.items())
    ]

    tableaux_par_page = [
        {"page": p, "tableaux": tbls}
        for p, tbls in sorted(pages_tables.items())
    ]

    all_text = "\n\n".join(
        f"[Page {p}]\n" + "\n".join(lignes)
        for p, lignes in sorted(pages_text.items())
    )

    nb_pages = max(
        max(pages_text.keys(), default=0),
        max(pages_tables.keys(), default=0),
    )

    return {
        "text": all_text,
        "texte_par_page": texte_par_page,
        "tableaux_par_page": tableaux_par_page,
        "nb_tableaux": sum(len(t["tableaux"]) for t in tableaux_par_page),
        "nb_pages": nb_pages,
        "model": "mineru",
    }
