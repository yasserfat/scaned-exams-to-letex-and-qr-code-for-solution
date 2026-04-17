import re
import os
import unicodedata
from datetime import datetime
import fitz


def make_exam_stem(subject: str, year: str) -> str:
    """Build a clean ASCII filename stem from subject + year + date.
    Example: 'رياضيات_2025_2026-04-13'
    """
    # Transliterate Arabic to ASCII where possible, else keep as-is then strip non-alphanum
    try:
        slug = unicodedata.normalize("NFKD", subject).encode("ascii", "ignore").decode()
    except Exception:
        slug = ""
    slug = re.sub(r"[^\w]+", "_", slug).strip("_")
    if not slug:
        # Fall back to raw Arabic stripped of spaces — still meaningful in filenames
        slug = re.sub(r"\s+", "_", subject.strip())
    year_clean = re.sub(r"[^\w-]", "", year) or "unknown"
    date_str = datetime.now().strftime("%Y-%m-%d")
    return f"{slug}_{year_clean}_{date_str}" if slug else f"exam_{year_clean}_{date_str}"


def compress_pdf_bytes(pdf_bytes: bytes, dpi: int = 100) -> bytes:
    """Re-render each PDF page at lower DPI using PyMuPDF to reduce file size."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    out = fitz.open()
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    for page in doc:
        pix    = page.get_pixmap(matrix=mat, alpha=False)
        imgpdf = fitz.open("pdf", pix.pdfocr_tobytes())
        out.insert_pdf(imgpdf)
    result = out.tobytes(deflate=True, garbage=4, clean=True)
    doc.close()
    out.close()
    return result


def render_page_images(pdf_path: str, work_dir: str, dpi: int = 150) -> list[str]:
    """Render each PDF page as PNG for display in the crop UI. Returns file paths."""
    doc = fitz.open(pdf_path)
    paths = []
    for i in range(len(doc)):
        page = doc[i]
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        out = os.path.join(work_dir, f"page_{i + 1}.png")
        pix.save(out)
        paths.append(out)
    doc.close()
    return paths
