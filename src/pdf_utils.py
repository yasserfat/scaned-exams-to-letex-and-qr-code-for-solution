import re
import os
import unicodedata
import fitz


def make_exam_stem(subject: str, year: str) -> str:
    """Build a stable filename stem from subject + year only (no date).
    Same exam + year always produces the same stem. Example: 'رياضيات_2025'.
    """
    try:
        slug = unicodedata.normalize("NFKD", subject).encode("ascii", "ignore").decode()
    except Exception:
        slug = ""
    slug = re.sub(r"[^\w]+", "_", slug).strip("_")
    if not slug:
        slug = re.sub(r"\s+", "_", subject.strip())
    year_clean = re.sub(r"[^\w-]", "", year) or "unknown"
    return f"{slug}_{year_clean}" if slug else f"exam_{year_clean}"


_OCR_AVAILABLE: bool | None = None


def compress_pdf_bytes(pdf_bytes: bytes, dpi: int = 100) -> bytes:
    """Re-render each PDF page at lower DPI using PyMuPDF to reduce file size.

    Uses Tesseract (via PyMuPDF's pdfocr_tobytes) to produce searchable PDFs
    when available. If Tesseract isn't installed, falls back to a plain
    image-only PDF so the pipeline still works.
    """
    global _OCR_AVAILABLE
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    out = fitz.open()
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    for page in doc:
        pix = page.get_pixmap(matrix=mat, alpha=False)
        if _OCR_AVAILABLE is False:
            imgpdf = fitz.open("pdf", pix.tobytes("pdf"))
        else:
            try:
                imgpdf = fitz.open("pdf", pix.pdfocr_tobytes())
                _OCR_AVAILABLE = True
            except Exception:
                _OCR_AVAILABLE = False
                imgpdf = fitz.open("pdf", pix.tobytes("pdf"))
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
