import re, os, json, base64, subprocess, shutil, uuid
import anthropic
from anthropic.types import TextBlock
import fitz, cv2, numpy as np, qrcode
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from dotenv import load_dotenv

load_dotenv()
_client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
SUBJECT_TEMPLATE  = open("template_subject.tex",  encoding="utf-8").read()
SOLUTION_TEMPLATE = open("template_solution.tex", encoding="utf-8").read()

# ── Prompts ───────────────────────────────────────────────────────────────────

SYSTEM_PROMPT_UNIFIED = """
You are an expert at reading scanned Arabic exam papers and transcribing them into clean LaTeX.

OUTPUT FORMAT — return ONLY this raw JSON, no markdown fences, no explanation:
{
  "subject":  "subject name in Arabic exactly as written",
  "year":     "4-digit year only",
  "duration": "exam duration in Arabic exactly as written",
  "exam":     "<LaTeX body — questions only>",
  "solution": "<LaTeX body — solution only, or NO_SOLUTION>"
}

RULES FOR exam AND solution FIELDS:
- LaTeX body only — no \\documentclass, no preamble, no \\begin{document}.
- No markdown fences. Arabic UTF-8 directly. Math in $...$ or \\[...\\].
- English/French: \\begin{english}...\\end{english} or \\begin{french}...\\end{french}.
- \\section*{} for titles, \\begin{enumerate}...\\end{enumerate} for lists.
- Simple geometry: TikZ. Complex figures (circuits, biology diagrams): named placeholder:
    \\begin{center}
    \\fbox{\\parbox{7cm}{\\centering\\textbf{[FIGURE:name:pageN]}\\\\[4pt]{\\small أرفق الصورة هنا}}}
    \\end{center}
  where N = 1-based page number in the input PDF where the figure appears.
- exam: questions section only. No header table. Start with first \\section*.
- solution: solution/correction section only. If absent: return string NO_SOLUTION.
"""

# ── Helpers ───────────────────────────────────────────────────────────────────

def clean_json_response(raw: str) -> str:
    """Strip markdown fences if Claude wrapped the JSON."""
    raw = raw.strip()
    raw = re.sub(r'^```[a-zA-Z]*\n?', '', raw)
    raw = re.sub(r'\n?```$', '', raw)
    return raw.strip()


def clean_latex(raw: str) -> str:
    """Strip markdown fences AND \\begin{document}/\\end{document} wrappers."""
    raw = raw.strip()
    raw = re.sub(r'^```[a-zA-Z]*\n?', '', raw)
    raw = re.sub(r'\n?```$', '', raw)
    raw = re.sub(r'\\begin\{document\}', '', raw)
    raw = re.sub(r'\\end\{document\}', '', raw)
    return raw.strip()


def compress_pdf_bytes(pdf_bytes: bytes, dpi: int = 150) -> bytes:
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


def extract_all_from_pdf(pdf_b64: str) -> dict:
    """One Claude call. Returns {subject, year, duration, exam, solution}."""
    msg = _client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=20000,
        system=SYSTEM_PROMPT_UNIFIED,
        messages=[{"role": "user", "content": [
            {"type": "document", "source": {"type": "base64",
             "media_type": "application/pdf", "data": pdf_b64}},
            {"type": "text", "text": "Extract all content from this exam PDF and return the unified JSON."}
        ]}]
    )
    block = msg.content[0]
    if not isinstance(block, TextBlock):
        raise ValueError(f"Unexpected response block type: {type(block)}")
    return json.loads(clean_json_response(block.text))
