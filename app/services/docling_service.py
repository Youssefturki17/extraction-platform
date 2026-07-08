import os
import json
import tempfile
import subprocess
import uuid

def extract(file_path: str) -> dict:
    # On cree un script temporaire pour lancer Docling dans un processus separe
    # afin de proteger le serveur Flask contre les crashs memoire (OOM)
    script_content = f"""
import sys
import json
from docling.datamodel.base_models import InputFormat
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling_core.types.doc import TableItem, TextItem

def run():
    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = False
    converter = DocumentConverter(
        format_options={{
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
        }}
    )
    result = converter.convert(r"{file_path}")
    pages_text = {{}}
    pages_tables = {{}}

    for element, level in result.document.iterate_items():
        page_num = element.prov[0].page_no if element.prov else None
        if page_num is None:
            continue

        if isinstance(element, TextItem):
            if page_num not in pages_text:
                pages_text[page_num] = []
            pages_text[page_num].append(element.text)

        elif isinstance(element, TableItem):
            try:
                df = element.export_to_dataframe(doc=result.document)
                tbl = df.to_csv(index=False)
            except Exception:
                tbl = element.export_to_markdown(doc=result.document)
            if page_num not in pages_tables:
                pages_tables[page_num] = []
            pages_tables[page_num].append(tbl)

    texte_par_page = [
        {{"page": p, "contenu": "\\n".join(lignes)}}
        for p, lignes in sorted(pages_text.items())
    ]

    tableaux_par_page = [
        {{"page": p, "tableaux": tbls}}
        for p, tbls in sorted(pages_tables.items())
    ]

    all_text = "\\n\\n".join(
        f"[Page {{p}}]\\n" + "\\n".join(lignes)
        for p, lignes in sorted(pages_text.items())
    )

    out = {{
        "text": all_text,
        "texte_par_page": texte_par_page,
        "tableaux_par_page": tableaux_par_page,
        "nb_tableaux": sum(len(t["tableaux"]) for t in tableaux_par_page),
        "nb_pages": max(
            max(pages_text.keys(), default=0),
            max(pages_tables.keys(), default=0)
        ),
        "model": "docling"
    }}

    with open(r"{{output_json}}", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)

if __name__ == "__main__":
    run()
"""
    output_json = os.path.join(tempfile.gettempdir(), f"docling_out_{uuid.uuid4().hex}.json")
    script_path = os.path.join(tempfile.gettempdir(), f"docling_run_{uuid.uuid4().hex}.py")

    with open(script_path, "w", encoding="utf-8") as f:
        f.write(script_content.replace("{output_json}", output_json.replace("\\", "\\\\")))

    try:
        # Run in a separate process with a 5-minute hard timeout
        subprocess.run(
            ["python", script_path],
            check=True,
            capture_output=True,
            text=True,
            timeout=300,
        )
        with open(output_json, "r", encoding="utf-8") as f:
            result = json.load(f)
        return result
    except subprocess.TimeoutExpired:
        raise Exception("Docling a dépassé le délai de 5 minutes (timeout).")
    except subprocess.CalledProcessError as e:
        # Expose full stderr so errors are never hidden
        raise Exception(
            f"Docling a crashé (code {e.returncode}).\n\nSTDERR:\n{e.stderr}\n\nSTDOUT:\n{e.stdout}"
        )
    finally:
        if os.path.exists(script_path):
            os.remove(script_path)
        if os.path.exists(output_json):
            os.remove(output_json)
