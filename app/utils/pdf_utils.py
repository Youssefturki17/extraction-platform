"""
pdf_utils.py — PDF-specific utility functions.

Provides adaptive PDF chunking with overlap and table deduplication
to optimize extraction time for large documents.
"""

import os
import hashlib


def get_chunk_config(total_pages: int) -> tuple[int, int]:
    """
    Returns (chunk_size, overlap) based on total page count.

    Strategy:
    - 1–5 pages   → no split (chunk_size = total_pages, overlap = 0)
    - 6–15 pages  → chunk_size = 5,  overlap = 1
    - 16–30 pages → chunk_size = 8,  overlap = 1
    - 31–60 pages → chunk_size = 10, overlap = 1
    - 60+ pages   → chunk_size = 12, overlap = 1
    """
    if total_pages <= 5:
        return total_pages, 0
    elif total_pages <= 15:
        return 5, 1
    elif total_pages <= 30:
        return 8, 1
    elif total_pages <= 60:
        return 10, 1
    else:
        return 12, 1


def split_pdf_adaptive(file_path: str) -> list[str]:
    """
    Splits a PDF into overlapping chunks based on adaptive config.

    - Reads total page count using pypdf.
    - Calls get_chunk_config() to determine chunk_size and overlap.
    - If no split needed (total_pages <= 5), returns [file_path] directly.
    - Otherwise, saves temp chunk files as uploads/{basename}_chunk_{i}.pdf
      with exactly 1 page of overlap between consecutive chunks.
    - Returns list of chunk file paths.
    """
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(file_path)
    total_pages = len(reader.pages)

    chunk_size, overlap = get_chunk_config(total_pages)

    # No split needed
    if total_pages <= 5:
        return [file_path]

    basename = os.path.splitext(os.path.basename(file_path))[0]
    uploads_dir = os.path.join(os.path.dirname(file_path))
    # Ensure we write chunks next to the original file (in uploads/)
    chunk_paths = []
    chunk_index = 0
    start = 0

    while start < total_pages:
        end = min(start + chunk_size, total_pages)

        writer = PdfWriter()
        for page_num in range(start, end):
            writer.add_page(reader.pages[page_num])

        chunk_filename = f"{basename}_chunk_{chunk_index}.pdf"
        chunk_path = os.path.join(uploads_dir, chunk_filename)

        with open(chunk_path, "wb") as f:
            writer.write(f)

        chunk_paths.append(chunk_path)
        chunk_index += 1

        # Advance by chunk_size - overlap (step forward, keeping 1 page overlap)
        step = chunk_size - overlap
        start += step

        # If the remaining pages are fewer than or equal to overlap, stop
        # to avoid an empty or already-covered chunk
        if start >= total_pages:
            break

    return chunk_paths


def deduplicate_tables(tables: list) -> list:
    """
    Deduplicates a list of table strings (CSV/Markdown) produced across chunks.

    Strategy:
    - For each table, compute a hash from the content of its first non-empty row.
    - When duplicates are found (same first-row hash), keep only the table
      with the most rows (most complete version).
    - Returns a deduplicated list preserving original order of first occurrence.
    """
    if not tables:
        return tables

    def _first_row_hash(table_content: str) -> str:
        """Extract the first non-empty row and hash it."""
        if not isinstance(table_content, str):
            # Non-string tables (e.g. dicts from older pipeline): hash repr
            content_str = repr(table_content)
            return hashlib.md5(content_str.encode("utf-8", errors="ignore")).hexdigest()
        lines = [line.strip() for line in table_content.splitlines() if line.strip()]
        first_row = lines[0] if lines else ""
        return hashlib.md5(first_row.encode("utf-8", errors="ignore")).hexdigest()

    def _row_count(table_content) -> int:
        """Count non-empty rows in a table string."""
        if not isinstance(table_content, str):
            return 0
        return sum(1 for line in table_content.splitlines() if line.strip())

    # Map: first_row_hash → (best_table, best_row_count)
    seen: dict[str, tuple] = {}
    order: list[str] = []  # preserve insertion order of hashes

    for table in tables:
        h = _first_row_hash(table)
        rows = _row_count(table)

        if h not in seen:
            seen[h] = (table, rows)
            order.append(h)
        else:
            # Keep the more complete version (most rows)
            _, best_rows = seen[h]
            if rows > best_rows:
                seen[h] = (table, rows)

    return [seen[h][0] for h in order]
