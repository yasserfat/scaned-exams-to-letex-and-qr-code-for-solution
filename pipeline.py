import re, os, json, base64, subprocess, shutil, uuid
import anthropic
from anthropic.types import TextBlock
import fitz, cv2, numpy as np
import qrcode
import qrcode.constants
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


# ── LaTeX builders ────────────────────────────────────────────────────────────

def build_subject_latex(subject: str, year: str, duration: str,
                        exam_content: str,
                        qr_image_path: str | None = None) -> str:
    qr_block = (
        r"\vspace{1cm}" "\n"
        r"\begin{center}" "\n"
        r"  {\small رمز الاستجابة السريعة للوصول إلى التصحيح النموذجي}\\[0.4em]" "\n"
        rf"  \includegraphics[width=3cm]{{{qr_image_path}}}" "\n"
        r"\end{center}"
    ) if qr_image_path else ""
    latex = SUBJECT_TEMPLATE
    latex = latex.replace("%%SUBJECT%%",      subject.strip()  or "الرياضيات")
    latex = latex.replace("%%YEAR%%",         year.strip()     or "----")
    latex = latex.replace("%%DURATION%%",     duration.strip() or "----")
    latex = latex.replace("%%EXAM_CONTENT%%", clean_latex(exam_content))
    latex = latex.replace("%%QR_CODE%%",      qr_block)
    return latex


def build_solution_latex(subject: str, year: str, duration: str,
                         solution_content: str) -> str:
    latex = SOLUTION_TEMPLATE
    latex = latex.replace("%%SUBJECT%%",          subject.strip()  or "الرياضيات")
    latex = latex.replace("%%YEAR%%",             year.strip()     or "----")
    latex = latex.replace("%%DURATION%%",         duration.strip() or "----")
    latex = latex.replace("%%SOLUTION_CONTENT%%", clean_latex(solution_content))
    return latex


def compile_latex(latex_code: str, work_dir: str,
                  out_stem: str = "exam") -> tuple[bool, str]:
    """Write {out_stem}.tex, run xelatex twice, return (success, error_log)."""
    os.makedirs(work_dir, exist_ok=True)
    if os.path.exists("logo.png"):
        shutil.copy("logo.png", os.path.join(work_dir, "logo.png"))
    tex_path = os.path.join(work_dir, f"{out_stem}.tex")
    with open(tex_path, "w", encoding="utf-8") as f:
        f.write(latex_code)
    for _ in range(2):
        subprocess.run(
            ["xelatex", "-interaction=nonstopmode", f"{out_stem}.tex"],
            cwd=work_dir, capture_output=True, timeout=120
        )
    pdf_path = os.path.join(work_dir, f"{out_stem}.pdf")
    if not os.path.exists(pdf_path):
        log_path = os.path.join(work_dir, f"{out_stem}.log")
        if os.path.exists(log_path):
            log_text = open(log_path, encoding="utf-8", errors="ignore").read()
            error_lines = [l for l in log_text.splitlines()
                           if l.startswith("!") or "Error" in l]
            return False, "\n".join(error_lines)
        return False, "PDF not created and no log found"
    return True, ""


# ── Figure extraction ─────────────────────────────────────────────────────────

def parse_figure_placeholders(latex: str) -> list[dict]:
    """Returns [{"name": str, "page": int}, ...]  page defaults to 1."""
    pattern = r'\[FIGURE:([\w_-]+)(?::page(\d+))?\]'
    results = []
    for m in re.finditer(pattern, latex):
        results.append({"name": m.group(1), "page": int(m.group(2) or 1)})
    return results


def extract_figures_from_pdf(pdf_path: str, figure_specs: list[dict],
                              work_dir: str, dpi: int = 200) -> dict[str, str]:
    """
    Returns {name: png_path} for successfully extracted figures.
    Specs without a detected contour are omitted (placeholder stays).
    """
    doc = fitz.open(pdf_path)
    figure_map = {}

    for spec in figure_specs:
        name = spec["name"]
        page_idx = spec["page"] - 1
        if page_idx >= len(doc):
            continue

        # Render page at dpi
        page = doc[page_idx]
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)

        # Threshold + morphological close to join figure marks into blobs
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (20, 20))
        closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

        # Find contours
        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Filter: min 100pt × 100pt, max 95% page width, max 60% page height, aspect 0.2–5.0
        MIN_PX = int(100 * dpi / 72)
        candidates = []
        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            if (MIN_PX <= w <= int(pix.width * 0.95) and
                MIN_PX <= h <= int(pix.height * 0.6) and
                0.2 <= w / h <= 5.0):
                candidates.append((w * h, x, y, w, h))

        if not candidates:
            continue  # no figure found — keep placeholder

        # Largest candidate + 5% padding
        _, x, y, w, h = sorted(candidates, reverse=True)[0]
        pad_x, pad_y = int(w * 0.05), int(h * 0.05)
        x1 = max(0, x - pad_x); y1 = max(0, y - pad_y)
        x2 = min(pix.width, x + w + pad_x); y2 = min(pix.height, y + h + pad_y)

        cropped = img[y1:y2, x1:x2]
        out_path = os.path.join(work_dir, f"figure_{name}.png")
        cv2.imwrite(out_path, cv2.cvtColor(cropped, cv2.COLOR_RGB2BGR))
        figure_map[name] = out_path

    doc.close()
    return figure_map


def replace_figure_placeholders(latex: str, figure_map: dict[str, str]) -> str:
    """
    Replace [FIGURE:name:pageN] fbox blocks with \\includegraphics for resolved figures.
    Unresolved placeholders left as-is.
    """
    pattern = r'\\begin\{center\}\s*\\fbox\{.*?\[FIGURE:([\w_-]+)(?::page\d+)?\].*?\}\s*\\end\{center\}'
    def replacer(m: re.Match) -> str:
        name = m.group(1)
        if name in figure_map:
            fname = os.path.basename(figure_map[name])
            return rf"\begin{{center}}\includegraphics[width=0.8\textwidth]{{{fname}}}\end{{center}}"
        return m.group(0)  # keep placeholder
    return re.sub(pattern, replacer, latex, flags=re.DOTALL)


# ── Drive & QR ────────────────────────────────────────────────────────────────

def upload_to_drive(local_pdf_path: str, filename: str,
                    folder_id: str | None = None) -> str:
    """Upload to Drive via service account. Returns shareable URL."""
    creds_path = os.environ.get("GOOGLE_DRIVE_CREDENTIALS")
    if not creds_path or not os.path.exists(creds_path):
        raise RuntimeError("GOOGLE_DRIVE_CREDENTIALS not set or file not found")
    creds = service_account.Credentials.from_service_account_file(
        creds_path, scopes=["https://www.googleapis.com/auth/drive"])
    service = build("drive", "v3", credentials=creds)

    folder_id = folder_id or os.environ.get("GOOGLE_DRIVE_FOLDER_ID")
    metadata: dict = {"name": filename}
    if folder_id:
        metadata["parents"] = [folder_id]

    media = MediaFileUpload(local_pdf_path, mimetype="application/pdf", resumable=True)
    file_obj = service.files().create(body=metadata, media_body=media, fields="id").execute()
    file_id = file_obj["id"]

    if os.environ.get("GOOGLE_DRIVE_PUBLIC", "true").lower() == "true":
        service.permissions().create(
            fileId=file_id, body={"role": "reader", "type": "anyone"}
        ).execute()

    return f"https://drive.google.com/file/d/{file_id}/view?usp=sharing"


def generate_qr_code(url: str, output_path: str) -> str:
    """Generate QR PNG at output_path. Returns output_path."""
    qr = qrcode.QRCode(
        version=1, error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=6, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img.get_image().save(output_path)
    return output_path


# ── Orchestrator ──────────────────────────────────────────────────────────────

def process_exam_pdf(pdf_bytes: bytes, work_dir: str,
                     original_filename: str = "exam",
                     compress: bool = True) -> dict:
    os.makedirs(work_dir, exist_ok=True)

    # 1. Compress + encode
    data = compress_pdf_bytes(pdf_bytes) if compress else pdf_bytes
    pdf_b64 = base64.b64encode(data).decode()

    # 2. Single Claude call (Fix 3)
    extracted = extract_all_from_pdf(pdf_b64)
    subject  = extracted.get("subject", "")
    year     = extracted.get("year", "----")
    duration = extracted.get("duration", "----")
    exam     = extracted.get("exam", "")
    solution = extracted.get("solution", "")
    if solution.strip() == "NO_SOLUTION":
        solution = ""

    # 3. Figure extraction (Fix 4)
    figures_total = 0
    figures_extracted = 0
    if exam or solution:
        specs = parse_figure_placeholders(exam + "\n" + solution)
        figures_total = len(specs)
        if specs:
            # Save PDF to disk for fitz.open()
            input_pdf_path = os.path.join(work_dir, "input.pdf")
            with open(input_pdf_path, "wb") as f:
                f.write(data)
            figure_map = extract_figures_from_pdf(input_pdf_path, specs, work_dir)
            figures_extracted = len(figure_map)
            exam     = replace_figure_placeholders(exam,     figure_map)
            solution = replace_figure_placeholders(solution, figure_map)

    # 4. Compile solution.pdf (Fix 1)
    drive_url = None
    qr_png    = None
    if solution.strip():
        sol_latex = build_solution_latex(subject, year, duration, solution)
        ok, err = compile_latex(sol_latex, work_dir, out_stem="solution")
        if not ok:
            print(f"  WARNING: solution.pdf compilation failed: {err}")

        # 5. Upload to Drive (Fix 2)
        sol_pdf = os.path.join(work_dir, "solution.pdf")
        if os.path.exists(sol_pdf):
            try:
                stem = os.path.splitext(original_filename)[0]
                drive_url = upload_to_drive(sol_pdf, f"{stem}_solution.pdf")
                qr_png    = generate_qr_code(drive_url, os.path.join(work_dir, "qr_code.png"))
            except Exception as e:
                print(f"  WARNING: Drive upload failed: {e}")

    # 6. Compile subject.pdf with QR (Fix 1 + Fix 2)
    qr_rel = "qr_code.png" if (qr_png and os.path.exists(qr_png)) else None
    subj_latex = build_subject_latex(subject, year, duration, exam, qr_rel)
    ok, err = compile_latex(subj_latex, work_dir, out_stem="subject")
    if not ok and qr_rel:
        # Retry without QR if QR causes compile failure
        subj_latex = build_subject_latex(subject, year, duration, exam, None)
        ok, err = compile_latex(subj_latex, work_dir, out_stem="subject")
    if not ok:
        raise RuntimeError(f"subject.pdf compilation failed: {err}")

    return {
        "subject":           subject,
        "year":              year,
        "duration":          duration,
        "subject_pdf":       os.path.join(work_dir, "subject.pdf"),
        "solution_pdf":      os.path.join(work_dir, "solution.pdf") if solution.strip() else None,
        "drive_url":         drive_url,
        "qr_png":            qr_png,
        "figures_extracted": figures_extracted,
        "figures_total":     figures_total,
    }
