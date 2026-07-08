"""
paddle_service.py — PaddleOCR extraction service.

NOTE: PaddleOCR is not available on Windows / Python 3.13.
      This module is imported conditionally in extraction_service.py
      and excluded silently if unavailable.
"""

import os


def extract(file_path: str) -> dict:
    """
    Extrait le texte d'un PDF via PaddleOCR.
    """
    from paddleocr import PaddleOCR

    ocr = PaddleOCR(use_angle_cls=True, lang="fr", show_log=False)
    result = ocr.ocr(file_path, cls=True)

    pages_text: dict[int, list[str]] = {}

    for page_idx, page in enumerate(result or [], start=1):
        if not page:
            continue
        texts = []
        for line in page:
            if line and len(line) >= 2:
                text_info = line[1]
                if isinstance(text_info, (list, tuple)) and text_info:
                    texts.append(str(text_info[0]))
                elif isinstance(text_info, str):
                    texts.append(text_info)
        if texts:
            pages_text[page_idx] = texts

    texte_par_page = [
        {"page": p, "contenu": "\n".join(lignes)}
        for p, lignes in sorted(pages_text.items())
    ]

    all_text = "\n\n".join(
        f"[Page {p}]\n" + "\n".join(lignes)
        for p, lignes in sorted(pages_text.items())
    )

    nb_pages = max(pages_text.keys(), default=0)

    return {
        "text": all_text,
        "texte_par_page": texte_par_page,
        "tableaux_par_page": [],
        "nb_tableaux": 0,
        "nb_pages": nb_pages,
        "model": "paddle",
    }
