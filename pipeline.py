import re, os, json, base64, subprocess, shutil, unicodedata
from datetime import datetime
import anthropic
from anthropic.types import TextBlock
import fitz
import qrcode
import qrcode.constants
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
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
- NEVER use Unicode circled/enclosed numbers (①②③④⑤ etc.). Use \\textcircled{\\small 1} instead.
- NEVER use Unicode special symbols that may not render in Arabic fonts. Use LaTeX equivalents.
- Complex figures (circuits, diagrams, drawings, photos, tables-with-images): use this placeholder:
    \\begin{center}
    \\fbox{\\parbox{7cm}{\\centering\\textbf{[FIGURE:name:label:pageN:top:left:bottom:right]}\\\\[4pt]{\\small أرفق الصورة هنا}}}
    \\end{center}
  where:
    - name = short snake_case identifier (e.g. circuit_1, bottles, inclined_plane)
    - label = short Arabic human-readable description of the figure (e.g. دارة كهربائية, مستوى مائل, قنينة)
    - N = 1-based page number in the input PDF where the figure appears
    - top, left, bottom, right = bounding box as decimal fractions 0.0–1.0 of the PAGE dimensions
      (0,0 = top-left corner of the page; 1,1 = bottom-right corner)
      Be precise — only include the figure/diagram region, NOT surrounding text or labels.
  Example: [FIGURE:circuit_1:دارة كهربائية:page1:0.10:0.00:0.45:0.60]
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


def extract_all_from_pdf(pdf_b64: str) -> dict:
    """One Claude call. Returns {subject, year, duration, exam, solution}."""
    msg = _client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=20000,
        system=[{
            "type": "text",
            "text": SYSTEM_PROMPT_UNIFIED,
            "cache_control": {"type": "ephemeral"},  # cached at $0.30/M instead of $3/M
        }],
        messages=[{"role": "user", "content": [
            {"type": "document", "source": {"type": "base64",
             "media_type": "application/pdf", "data": pdf_b64}},
            {"type": "text", "text": "Extract all content from this exam PDF and return the unified JSON."}
        ]}]
    )
    block = msg.content[0]
    if not isinstance(block, TextBlock):
        raise ValueError(f"Unexpected response block type: {type(block)}")

    u = msg.usage
    # Sonnet 4.6 pricing (per million tokens)
    # Input: $3.00, cache write: $3.75, cache read: $0.30, output: $15.00
    cost_usd = (
        getattr(u, "input_tokens", 0)               * 3.00  / 1_000_000
        + getattr(u, "cache_creation_input_tokens", 0) * 3.75  / 1_000_000
        + getattr(u, "cache_read_input_tokens", 0)    * 0.30  / 1_000_000
        + getattr(u, "output_tokens", 0)              * 15.00 / 1_000_000
    )
    print(
        f"  Claude usage — in:{getattr(u,'input_tokens',0)} "
        f"cache_write:{getattr(u,'cache_creation_input_tokens',0)} "
        f"cache_read:{getattr(u,'cache_read_input_tokens',0)} "
        f"out:{getattr(u,'output_tokens',0)} "
        f"| cost: ${cost_usd:.4f}"
    )

    result = json.loads(clean_json_response(block.text))
    result["_cost_usd"] = cost_usd
    return result


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
    """
    Returns [{"name": str, "label": str, "page": int, "top": float, "left": float,
              "bottom": float, "right": float}, ...]
    label is the Arabic human-readable display name (may be absent in old format).
    All bbox fields default to full-page (0.0/1.0) when absent.
    """
    # New format: [FIGURE:name:label:pageN:top:left:bottom:right]
    # Old format: [FIGURE:name:pageN:top:left:bottom:right]  (no label)
    pattern = r'\[FIGURE:([\w_-]+):((?:[^:\]]*?):)?page(\d+)(?::([0-9.]+):([0-9.]+):([0-9.]+):([0-9.]+))?\]'
    results = []
    for m in re.finditer(pattern, latex):
        label_raw = m.group(2) or ""
        label = label_raw.rstrip(":").strip()
        results.append({
            "name":   m.group(1),
            "label":  label,
            "page":   int(m.group(3)),
            "top":    float(m.group(4) or 0.0),
            "left":   float(m.group(5) or 0.0),
            "bottom": float(m.group(6) or 1.0),
            "right":  float(m.group(7) or 1.0),
        })
    return results


def extract_figures_from_pdf(pdf_path: str, figure_specs: list[dict],
                              work_dir: str, dpi: int = 200) -> dict[str, str]:
    """
    Crop figures from PDF using Claude-provided fractional bounding boxes.
    Returns {name: png_path} for each successfully cropped figure.
    """
    doc = fitz.open(pdf_path)
    figure_map: dict[str, str] = {}

    for spec in figure_specs:
        name = spec["name"]
        page_idx = spec["page"] - 1
        if page_idx >= len(doc):
            continue

        page = doc[page_idx]
        rect = page.rect  # full page rect in points

        # Convert fractional bbox to absolute points
        x0 = rect.x0 + spec["left"]   * rect.width
        y0 = rect.y0 + spec["top"]    * rect.height
        x1 = rect.x0 + spec["right"]  * rect.width
        y1 = rect.y0 + spec["bottom"] * rect.height
        clip = fitz.Rect(x0, y0, x1, y1)

        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat, clip=clip, alpha=False)
        out_path = os.path.join(work_dir, f"figure_{name}.png")
        pix.save(out_path)
        figure_map[name] = out_path

    doc.close()
    return figure_map


def replace_figure_placeholders(latex: str, figure_map: dict[str, str]) -> str:
    """
    Replace [FIGURE:name:pageN] fbox blocks with \\includegraphics for resolved figures.
    Unresolved placeholders left as-is.
    """
    pattern = r'\\begin\{center\}\s*\\fbox\{.*?\[FIGURE:([\w_-]+):[^\]]*\].*?\}\s*\\end\{center\}'
    def replacer(m: re.Match) -> str:
        name = m.group(1)
        if name in figure_map:
            fname = os.path.basename(figure_map[name])
            return rf"\begin{{center}}\includegraphics[width=0.5\textwidth]{{{fname}}}\end{{center}}"
        return m.group(0)  # keep placeholder
    return re.sub(pattern, replacer, latex, flags=re.DOTALL)


# ── Drive & QR ────────────────────────────────────────────────────────────────

_SCOPES      = ["https://www.googleapis.com/auth/drive.file"]
_BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
_OAUTH_CLIENT = os.path.join(_BASE_DIR, "oauth_client.json")
_TOKEN_FILE   = os.path.join(_BASE_DIR, "token.json")


def _get_drive_service():
    """Return an authenticated Drive service using OAuth2 (user account)."""
    creds = None
    if os.path.exists(_TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(_TOKEN_FILE, _SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(_OAUTH_CLIENT):
                raise RuntimeError("oauth_client.json not found — add OAuth credentials to the project folder")
            flow = InstalledAppFlow.from_client_secrets_file(_OAUTH_CLIENT, _SCOPES)
            creds = flow.run_local_server(port=0)
        with open(_TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return build("drive", "v3", credentials=creds)


def upload_to_drive(local_pdf_path: str, filename: str,
                    folder_id: str | None = None) -> str:
    """Upload to Drive via OAuth user account. Returns shareable URL."""
    service = _get_drive_service()

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


def generate_placeholder_qr(output_path: str) -> str:
    """Generate a placeholder QR code for when Drive isn't configured yet."""
    return generate_qr_code("https://example.com/solution-coming-soon", output_path)


# ── Page rendering ────────────────────────────────────────────────────────────

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


def compile_pdfs(work_dir: str, subject: str, year: str, duration: str,
                 exam: str, solution: str,
                 original_filename: str = "exam") -> dict:
    """
    Compile subject.pdf (+ solution.pdf if present) from already-processed LaTeX.
    Drive upload + QR are attempted if credentials are configured.
    Returns same dict shape as process_exam_pdf minus figure fields.
    """
    drive_url = None
    qr_png = None

    if solution.strip():
        sol_latex = build_solution_latex(subject, year, duration, solution)
        ok, err = compile_latex(sol_latex, work_dir, out_stem="solution")
        if not ok:
            print(f"  WARNING: solution.pdf compilation failed: {err}")

        sol_pdf = os.path.join(work_dir, "solution.pdf")
        if os.path.exists(sol_pdf):
            try:
                stem = make_exam_stem(subject, year)
                drive_url = upload_to_drive(sol_pdf, f"{stem}_solution.pdf")
                qr_png = generate_qr_code(drive_url, os.path.join(work_dir, "qr_code.png"))
            except Exception as e:
                print(f"  WARNING: Drive upload failed: {e}")
                # Still generate a placeholder QR so the layout is visible
                try:
                    qr_png = generate_placeholder_qr(os.path.join(work_dir, "qr_code.png"))
                except Exception:
                    pass

    qr_rel = "qr_code.png" if (qr_png and os.path.exists(qr_png)) else None
    subj_latex = build_subject_latex(subject, year, duration, exam, qr_rel)
    ok, err = compile_latex(subj_latex, work_dir, out_stem="subject")
    if not ok and qr_rel:
        subj_latex = build_subject_latex(subject, year, duration, exam, None)
        ok, err = compile_latex(subj_latex, work_dir, out_stem="subject")
    if not ok:
        raise RuntimeError(f"subject.pdf compilation failed: {err}")

    return {
        "subject":      subject,
        "year":         year,
        "duration":     duration,
        "subject_pdf":  os.path.join(work_dir, "subject.pdf"),
        "solution_pdf": os.path.join(work_dir, "solution.pdf") if solution.strip() else None,
        "drive_url":    drive_url,
        "qr_png":       qr_png,
    }


# ── Orchestrator ──────────────────────────────────────────────────────────────

def process_exam_pdf(pdf_bytes: bytes, work_dir: str,
                     original_filename: str = "exam",
                     compress: bool = True,
                     manual_crops: bool = False) -> dict:
    os.makedirs(work_dir, exist_ok=True)

    # 1. Compress + encode (skip compression for files already under 2 MB)
    _SIZE_THRESHOLD = 2 * 1024 * 1024
    if compress and len(pdf_bytes) > _SIZE_THRESHOLD:
        data = compress_pdf_bytes(pdf_bytes)
    else:
        if len(pdf_bytes) <= _SIZE_THRESHOLD:
            print(f"  Skipping compression ({len(pdf_bytes)/1024:.0f} KB < 2 MB)")
        data = pdf_bytes
    pdf_b64 = base64.b64encode(data).decode()

    # 2. Single Claude call (Fix 3)
    extracted  = extract_all_from_pdf(pdf_b64)
    cost_usd   = extracted.pop("_cost_usd", 0.0)
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
    input_pdf_path = os.path.join(work_dir, "input.pdf")
    if exam or solution:
        specs = parse_figure_placeholders(exam + "\n" + solution)
        figures_total = len(specs)
        if specs:
            # Always save PDF to disk — needed for cropping (auto or manual)
            with open(input_pdf_path, "wb") as f:
                f.write(data)

            if manual_crops and specs:
                # Render page images for the crop UI, then stop — caller will
                # receive figure specs and trigger /crops when user is done.
                render_page_images(input_pdf_path, work_dir)
                return {
                    "needs_crop":      True,
                    "subject":         subject,
                    "year":            year,
                    "duration":        duration,
                    "exam_latex":      exam,
                    "solution_latex":  solution,
                    "figure_specs":    specs,
                    "page_count":      len(fitz.open(input_pdf_path)),
                    "original_filename": original_filename,
                }

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
                stem = make_exam_stem(subject, year)
                drive_url = upload_to_drive(sol_pdf, f"{stem}_solution.pdf")
                qr_png    = generate_qr_code(drive_url, os.path.join(work_dir, "qr_code.png"))
            except Exception as e:
                print(f"  WARNING: Drive upload failed: {e}")
                # Still generate a placeholder QR so the layout is visible
                try:
                    qr_png = generate_placeholder_qr(os.path.join(work_dir, "qr_code.png"))
                except Exception:
                    pass

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

    stem = make_exam_stem(subject, year)
    return {
        "subject":           subject,
        "year":              year,
        "duration":          duration,
        "stem":              stem,
        "subject_pdf":       os.path.join(work_dir, "subject.pdf"),
        "solution_pdf":      os.path.join(work_dir, "solution.pdf") if solution.strip() else None,
        "drive_url":         drive_url,
        "qr_png":            qr_png,
        "figures_extracted": figures_extracted,
        "figures_total":     figures_total,
        "cost_usd":          cost_usd,
    }
