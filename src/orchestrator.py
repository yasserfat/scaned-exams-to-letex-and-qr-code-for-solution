import os
import base64
import json
import fitz
from src.claude import extract_all_from_pdf
from src.pdf_utils import compress_pdf_bytes, render_page_images, make_exam_stem
from src.figures import parse_figure_placeholders, extract_figures_from_pdf, replace_figure_placeholders
from src.drive import upload_to_drive
from src.compiler import (
    build_subject_latex, build_solution_latex,
    compile_latex, generate_qr_code, generate_placeholder_qr,
)


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
