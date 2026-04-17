import os
import re
import shutil
import subprocess
import qrcode
import qrcode.constants

# ── Templates ─────────────────────────────────────────────────────────────────

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
SUBJECT_TEMPLATE  = open(os.path.join(_ROOT, "template_subject.tex"),  encoding="utf-8").read()
SOLUTION_TEMPLATE = open(os.path.join(_ROOT, "template_solution.tex"), encoding="utf-8").read()


# ── Helpers ───────────────────────────────────────────────────────────────────

def clean_latex(raw: str) -> str:
    r"""Strip markdown fences AND \begin{document}/\end{document} wrappers."""
    raw = raw.strip()
    raw = re.sub(r'^```[a-zA-Z]*\n?', '', raw)
    raw = re.sub(r'\n?```$', '', raw)
    raw = re.sub(r'\\begin\{document\}', '', raw)
    raw = re.sub(r'\\end\{document\}', '', raw)
    return raw.strip()


# ── LaTeX builders ────────────────────────────────────────────────────────────

def build_subject_latex(subject: str, year: str, duration: str,
                        exam_content: str,
                        qr_image_path: str | None = None) -> str:
    qr_footer = (
        rf"\includegraphics[height=0.85cm]{{{qr_image_path}}}%"
    ) if qr_image_path else ""
    qr_footer_label = (
        r"{\small لتحميل التصحيح}\hspace{0.4em}%"
    ) if qr_image_path else ""
    qr_block = (
        r"\vspace{1cm}" "\n"
        r"\begin{center}" "\n"
        r"  {\small رمز الاستجابة السريعة للوصول إلى التصحيح النموذجي}\\[0.4em]" "\n"
        rf"  \includegraphics[width=3cm]{{{qr_image_path}}}" "\n"
        r"\end{center}"
    ) if qr_image_path else ""
    latex = SUBJECT_TEMPLATE
    latex = latex.replace("%%SUBJECT%%",          subject.strip()  or "الرياضيات")
    latex = latex.replace("%%YEAR%%",             year.strip()     or "----")
    latex = latex.replace("%%DURATION%%",         duration.strip() or "----")
    latex = latex.replace("%%EXAM_CONTENT%%",     clean_latex(exam_content))
    latex = latex.replace("%%QR_FOOTER_LABEL%%",  qr_footer_label)
    latex = latex.replace("%%QR_FOOTER%%",        qr_footer)
    latex = latex.replace("%%QR_CODE%%",          qr_block)
    return latex


def build_solution_latex(subject: str, year: str, duration: str,
                         solution_content: str) -> str:
    latex = SOLUTION_TEMPLATE
    latex = latex.replace("%%SUBJECT%%",          subject.strip()  or "الرياضيات")
    latex = latex.replace("%%YEAR%%",             year.strip()     or "----")
    latex = latex.replace("%%DURATION%%",         duration.strip() or "----")
    latex = latex.replace("%%SOLUTION_CONTENT%%", clean_latex(solution_content))
    latex = latex.replace("%%QR_FOOTER_LABEL%%",  "")
    latex = latex.replace("%%QR_FOOTER%%",        "")
    return latex


def compile_latex(latex_code: str, work_dir: str,
                  out_stem: str = "exam") -> tuple[bool, str]:
    """Write {out_stem}.tex, run xelatex twice, return (success, error_log)."""
    os.makedirs(work_dir, exist_ok=True)
    logo_src = os.path.join(_ROOT, "logo.png")
    if os.path.exists(logo_src):
        shutil.copy(logo_src, os.path.join(work_dir, "logo.png"))
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


# ── QR code generation ────────────────────────────────────────────────────────

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
