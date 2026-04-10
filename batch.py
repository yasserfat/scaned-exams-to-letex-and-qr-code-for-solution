"""
batch.py — Process all PDFs in exams_input/ automatically.
Run:  python batch.py
Results saved in exams_output/<exam_name>/exam.pdf
Science figure placeholders are left as [FIGURE:name] boxes in the output —
open the PDF and manually add figures using the web app's Phase 2 if needed.
"""

import re
import os
import base64
import subprocess
import shutil
import json
import anthropic
import fitz
from dotenv import load_dotenv

load_dotenv()
client        = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
LATEX_TEMPLATE = open("template.tex", encoding="utf-8").read()

INPUT_FOLDER  = "exams_input"
OUTPUT_FOLDER = "exams_output"
os.makedirs(INPUT_FOLDER,  exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# ── Prompts (same as main.py) ─────────────────────────────────────────────────

SYSTEM_PROMPT_METADATA = """
You are an expert at reading scanned Arabic exam papers.
Extract only the metadata and return a JSON object:
{
  "subject":  "subject name in Arabic exactly as written",
  "year":     "4-digit year only",
  "duration": "exam duration in Arabic exactly as written"
}
Return ONLY the raw JSON. No explanation, no markdown.
"""

SYSTEM_PROMPT_EXAM = """
You are an expert at transcribing scanned Arabic exam papers into clean LaTeX.
Extract ONLY the exam QUESTIONS section (not the solution).

RULES:
- Return ONLY LaTeX body content — no \\documentclass, no preamble, no \\begin{document}.
- Do NOT include the header table.
- Do NOT wrap in markdown fences.
- Start with the first \\section* command.
- Write Arabic in UTF-8. Math in $...$ or \\[...\\].
- English/French: wrap in \\begin{english}...\\end{english} or \\begin{french}...\\end{french}.
- Simple geometry: recreate in TikZ.
- Complex science figures: use named placeholder:
  \\begin{center}
  \\fbox{\\parbox{7cm}{\\centering\\textbf{[FIGURE:description\\_exN]}\\\\[4pt]{\\small أرفق الصورة هنا}}}
  \\end{center}
- Extract ALL questions completely. Preserve point values.
"""

SYSTEM_PROMPT_SOLUTION = """
You are an expert at transcribing Arabic exam solutions into clean LaTeX.
Extract ONLY the SOLUTION section.

RULES:
- Return ONLY LaTeX body — no preamble, no \\begin{document}.
- Do NOT wrap in markdown fences.
- Start with first \\section*.
- Arabic in UTF-8. Math in $...$ or \\[...\\].
- Simple geometry: TikZ. Complex figures: [FIGURE:name] placeholder.
- Extract ALL steps completely.
- If no solution exists, return exactly: NO_SOLUTION
"""

# ── Helpers ───────────────────────────────────────────────────────────────────

def compress_pdf(pdf_bytes, dpi=150):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    out = fitz.open()
    mat = fitz.Matrix(dpi/72, dpi/72)
    for page in doc:
        pix    = page.get_pixmap(matrix=mat, alpha=False)
        imgpdf = fitz.open("pdf", pix.pdfocr_tobytes())
        out.insert_pdf(imgpdf)
    result = out.tobytes(deflate=True, garbage=4, clean=True)
    doc.close(); out.close()
    return result

def clean_json(raw):
    raw = raw.strip()
    raw = re.sub(r'^```[a-zA-Z]*\n?', '', raw)
    raw = re.sub(r'\n?```$', '', raw)
    return raw.strip()

def clean_latex(raw):
    raw = raw.strip()
    raw = re.sub(r'^```[a-zA-Z]*\n?', '', raw)
    raw = re.sub(r'\n?```$', '', raw)
    raw = re.sub(r'\\begin\{document\}', '', raw)
    raw = re.sub(r'\\end\{document\}', '', raw)
    return raw.strip()

def build_solution_block(sol):
    if not sol.strip(): return ""
    return (
        "\n\\newpage\n"
        "\\begin{center}\n"
        "  {\\Large\\bfseries \\rule{4cm}{0.4pt}\\quad التصحيح النموذجي \\quad\\rule{4cm}{0.4pt}}\n"
        "\\end{center}\n\n" + sol
    )

def build_full_latex(subject, year, duration, exam, solution):
    latex = LATEX_TEMPLATE
    latex = latex.replace("%%SUBJECT%%",  subject.strip()  or "")
    latex = latex.replace("%%YEAR%%",     year.strip()     or "----")
    latex = latex.replace("%%DURATION%%", duration.strip() or "----")
    latex = latex.replace("%%EXAM_CONTENT%%",     clean_latex(exam))
    latex = latex.replace("%%SOLUTION_CONTENT%%", build_solution_block(clean_latex(solution)))
    return latex

def compile_latex(latex_code, work_dir):
    os.makedirs(work_dir, exist_ok=True)
    if os.path.exists("logo.png"):
        shutil.copy("logo.png", os.path.join(work_dir, "logo.png"))
    with open(os.path.join(work_dir, "exam.tex"), "w", encoding="utf-8") as f:
        f.write(latex_code)
    for _ in range(2):
        subprocess.run(["xelatex", "-interaction=nonstopmode", "exam.tex"],
                       cwd=work_dir, capture_output=True, timeout=120)
    return os.path.exists(os.path.join(work_dir, "exam.pdf"))

def call_claude(system, pdf_b64, user_text, max_tokens=16000):
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": [
            {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_b64}},
            {"type": "text", "text": user_text}
        ]}]
    )
    return msg.content[0].text

def count_figure_placeholders(tex):
    return len(re.findall(r'\[FIGURE:[a-zA-Z0-9_]+\]', tex))

# ── Main ──────────────────────────────────────────────────────────────────────

files = sorted([f for f in os.listdir(INPUT_FOLDER) if f.lower().endswith(".pdf")])
total = len(files)

if total == 0:
    print(f"No PDFs found in {INPUT_FOLDER}/")
    exit()

print(f"\n{'='*60}")
print(f"📚 {total} exam(s) to process")
print(f"{'='*60}")

done = failed = figures_needed = 0

for i, filename in enumerate(files, 1):
    print(f"\n[{i}/{total}] {filename}")
    out_dir = os.path.join(OUTPUT_FOLDER, filename.replace(".pdf", ""))

    if os.path.exists(os.path.join(out_dir, "exam.pdf")):
        print("  ⏭️  Already done"); done += 1; continue

    try:
        raw_bytes   = open(os.path.join(INPUT_FOLDER, filename), "rb").read()
        orig_kb     = len(raw_bytes)/1024
        pdf_bytes   = compress_pdf(raw_bytes)
        comp_kb     = len(pdf_bytes)/1024
        print(f"  🗜️  {orig_kb:.0f} KB → {comp_kb:.0f} KB ({100-comp_kb/orig_kb*100:.0f}% saved)")
        pdf_b64     = base64.standard_b64encode(pdf_bytes).decode("utf-8")

        # Metadata
        try:
            meta     = json.loads(clean_json(call_claude(SYSTEM_PROMPT_METADATA, pdf_b64,
                       "Extract subject, year, duration. JSON only.", max_tokens=300)))
            subject  = meta.get("subject", "")
            year     = meta.get("year",    "----")
            duration = meta.get("duration","----")
            print(f"  📌 {subject} | {year} | {duration}")
        except Exception as e:
            print(f"  ⚠️  Metadata failed: {e}")
            subject = year = duration = "----"

        # Exam
        print("  🤖 Extracting exam...")
        exam = clean_latex(call_claude(SYSTEM_PROMPT_EXAM, pdf_b64,
               "Extract exam questions. TikZ for math. [FIGURE:name] for science. No preamble."))
        print(f"     {len(exam)} chars")

        # Solution
        print("  🤖 Extracting solution...")
        sol_raw  = clean_latex(call_claude(SYSTEM_PROMPT_SOLUTION, pdf_b64,
                   "Extract solution. If none: NO_SOLUTION"))
        solution = "" if sol_raw.strip() == "NO_SOLUTION" else sol_raw
        print(f"     {'None' if not solution else str(len(solution))+' chars'}")

        # Compile
        print("  ⚙️  Compiling...")
        full_latex = build_full_latex(subject, year, duration, exam, solution)
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "state.json"), "w", encoding="utf-8") as f:
            json.dump({"subject": subject, "year": year, "duration": duration,
                       "exam": exam, "solution": solution,
                       "original_filename": filename}, f, ensure_ascii=False, indent=2)

        if compile_latex(full_latex, out_dir):
            pdf_kb  = os.path.getsize(os.path.join(out_dir, "exam.pdf"))/1024
            n_figs  = count_figure_placeholders(full_latex)
            status  = f"({n_figs} figure placeholder(s) — use web app to add images)" if n_figs else ""
            print(f"  ✅ Done → {out_dir}/exam.pdf ({pdf_kb:.0f} KB) {status}")
            if n_figs: figures_needed += 1
            done += 1
        else:
            print(f"  ❌ Compile failed — see {out_dir}/exam.log")
            failed += 1

    except Exception as e:
        print(f"  ❌ Error: {e}")
        failed += 1

print(f"\n{'='*60}")
print(f"✅ Done: {done}   ❌ Failed: {failed}   🖼️  Need figures: {figures_needed}   Total: {total}")
print(f"Results: {OUTPUT_FOLDER}/")
print(f"{'='*60}\n")