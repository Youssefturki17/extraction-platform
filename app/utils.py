"""
utils.py — Utilitaires de post-traitement du texte extrait.

Fonctions principales :
    html_tables_to_markdown(text) : Remplace les blocs <table>…</table>
                                    par des tableaux en syntaxe Markdown.
"""

import re
import html


# ---------------------------------------------------------------------------
# Convertisseur HTML → Markdown
# ---------------------------------------------------------------------------

def html_tables_to_markdown(text: str) -> str:
    """
    Parcourt le texte et remplace chaque bloc HTML <table>…</table>
    par un tableau en syntaxe Markdown (| col | col | / |---|---|).

    Gère colspan basique : le contenu est répété dans les colonnes fusionnées.
    Ignore les attributs non pertinents (rowspan, class, style…).
    """
    def convert_table(match: re.Match) -> str:
        table_html = match.group(0)
        try:
            return _html_table_to_md(table_html)
        except Exception:
            # En cas d'échec, on laisse le HTML original intact
            return table_html

    # Remplace toutes les occurrences de <table>…</table> (insensible à la casse)
    result = re.sub(
        r"<table\b[^>]*>.*?</table>",
        convert_table,
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    return result


def _html_table_to_md(table_html: str) -> str:
    """
    Convertit un tableau HTML en tableau Markdown.
    Retourne une chaîne commençant et terminant par une ligne vide.
    """
    rows = _parse_html_rows(table_html)
    if not rows:
        return table_html

    # Normaliser toutes les lignes à la même largeur
    max_cols = max(len(r) for r in rows)
    rows = [r + [""] * (max_cols - len(r)) for r in rows]

    # Calculer la largeur maximale de chaque colonne
    col_widths = [
        max(len(str(rows[r][c])) for r in range(len(rows)))
        for c in range(max_cols)
    ]
    col_widths = [max(w, 3) for w in col_widths]  # minimum 3 pour ---

    def fmt_row(cells):
        return "| " + " | ".join(
            str(cells[c]).ljust(col_widths[c]) for c in range(max_cols)
        ) + " |"

    separator = "| " + " | ".join("-" * col_widths[c] for c in range(max_cols)) + " |"

    lines = []
    for i, row in enumerate(rows):
        lines.append(fmt_row(row))
        if i == 0:
            lines.append(separator)

    return "\n\n" + "\n".join(lines) + "\n\n"


def _parse_html_rows(table_html: str) -> list[list[str]]:
    """
    Extrait les lignes (<tr>) et cellules (<td>/<th>) d'un tableau HTML.
    Gère l'attribut colspan en dupliquant le contenu.
    """
    rows = []

    # Trouver toutes les lignes <tr>
    tr_pattern = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.DOTALL | re.IGNORECASE)
    td_pattern = re.compile(
        r"<(td|th)\b([^>]*)>(.*?)</(td|th)>", re.DOTALL | re.IGNORECASE
    )
    colspan_pattern = re.compile(r'colspan\s*=\s*["\']?(\d+)["\']?', re.IGNORECASE)

    for tr_match in tr_pattern.finditer(table_html):
        row_html = tr_match.group(1)
        cells = []
        for td_match in td_pattern.finditer(row_html):
            attrs = td_match.group(2)
            inner = td_match.group(3)

            # Nettoyer le contenu : supprimer les balises imbriquées et décoder HTML
            cell_text = re.sub(r"<[^>]+>", " ", inner)
            cell_text = html.unescape(cell_text)
            cell_text = " ".join(cell_text.split())  # normaliser les espaces

            # Gérer colspan
            colspan_match = colspan_pattern.search(attrs)
            span = int(colspan_match.group(1)) if colspan_match else 1
            for _ in range(span):
                cells.append(cell_text)

        if cells:
            rows.append(cells)

    return rows


# ---------------------------------------------------------------------------
# Nettoyage général du texte (optionnel)
# ---------------------------------------------------------------------------

def clean_extracted_text(text: str) -> str:
    """
    Applique un pipeline de nettoyage minimal :
      1. Conversion HTML → Markdown pour les tableaux
      2. Suppression des balises HTML résiduelles (images, commentaires…)
      3. Normalisation des sauts de ligne multiples
    """
    # 1. Convertir les tableaux HTML en Markdown
    text = html_tables_to_markdown(text)

    # 2. Supprimer les balises HTML résiduelles (<br>, <p>, commentaires HTML)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)  # commentaires HTML
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)  # toutes les balises restantes

    # 3. Normaliser les sauts de ligne excessifs (max 2 consécutifs)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()
