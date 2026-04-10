import re
import os
import uuid
import base64
import subprocess
import shutil
import json
import anthropic

from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

load_dotenv()
client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
app = FastAPI()

LATEX_TEMPLATE = open("template.tex", encoding="utf-8").read()

SYSTEM_PROMPT = SYSTEM_PROMPT_METADATA = """
You are an expert at reading scanned Arabic exam papers.
Extract only the metadata from the document and return a JSON object:
{
  "subject":  "subject name in Arabic exactly as written, e.g. الرياضيات",
  "year":     "4-digit year only, e.g. 2020",
  "duration": "exam duration in Arabic exactly as written, e.g. ساعتان"
}
Return ONLY the raw JSON. No explanation, no markdown, no extra text.
"""

SYSTEM_PROMPT_EXAM = """
You are an expert at transcribing scanned Arabic exam papers into clean LaTeX.
Extract ONLY the exam QUESTIONS section (not the solution/correction).

RULES:
- Return ONLY the LaTeX body content — no \\documentclass, no preamble, no \\begin{document}.
- Do NOT include the header table.
- Do NOT wrap in markdown fences or backticks.
- Start directly with the first \\section* command.
- Write Arabic text directly in UTF-8.
- Use \\section*{...} for titles, \\begin{enumerate}...\\end{enumerate} for lists.
- Math inside $...$ or \\[...\\].
- For English/French text wrap in \\begin{english}...\\end{english} or \\begin{french}...\\end{french}.
- Recreate simple geometric figures using TikZ.
- For complex figures (biology, detailed illustrations) insert: \\includegraphics[width=0.5\\textwidth]{figure.png}
- Extract ALL questions and instructions completely — do not skip anything.
"""

SYSTEM_PROMPT_SOLUTION = """
You are an expert at transcribing Arabic exam solution papers into clean LaTeX.
Extract ONLY the SOLUTION / CORRECTION section (التصحيح النموذجي / الحل النموذجي).

RULES:
- Return ONLY the LaTeX body content — no \\documentclass, no preamble, no \\begin{document}.
- Do NOT wrap in markdown fences or backticks.
- Start directly with the first \\section* command of the solution.
- Write Arabic text directly in UTF-8.
- Use \\section*{...} for titles, \\begin{enumerate}...\\end{enumerate} for lists.
- Math inside $...$ or \\[...\\].
- For English/French text wrap in \\begin{english}...\\end{english} or \\begin{french}...\\end{french}.
- Recreate geometric figures using TikZ where present.
- Extract ALL solution steps and answers completely — do not skip anything.
- If no solution section exists in the document, return exactly: NO_SOLUTION
"""


def clean_json_response(raw: str) -> str:
    """Strip markdown fences if Claude wrapped the JSON."""
    raw = raw.strip()
    raw = re.sub(r'^```[a-zA-Z]*\n?', '', raw)
    raw = re.sub(r'\n?```$', '', raw)
    return raw.strip()


def clean_latex(raw: str) -> str:
    """Clean any stray document tags from latex content."""
    raw = raw.strip()
    raw = re.sub(r'^```[a-zA-Z]*\n?', '', raw)
    raw = re.sub(r'\n?```$', '', raw)
    raw = re.sub(r'\\begin\{document\}', '', raw)
    raw = re.sub(r'\\end\{document\}', '', raw)
    return raw.strip()


def build_solution_block(solution_latex: str) -> str:
    """Wrap solution in a styled separator block."""
    if not solution_latex.strip():
        return ""
    return r"""
\newpage
\begin{center}
  \vspace{0.5cm}
  {\Large\bfseries ─────────────────────────────}\\[0.3em]
  {\Large\bfseries التصحيح النموذجي}\\[0.3em]
  {\Large\bfseries ─────────────────────────────}
  \vspace{0.5cm}
\end{center}

""" + solution_latex


def build_full_latex(subject: str, year: str, duration: str,
                     exam_content: str, solution_content: str) -> str:
    latex = LATEX_TEMPLATE
    latex = latex.replace("%%SUBJECT%%",   subject.strip()   or "الرياضيات")
    latex = latex.replace("%%YEAR%%",      year.strip()      or "----")
    latex = latex.replace("%%DURATION%%",  duration.strip()  or "----")
    latex = latex.replace("%%EXAM_CONTENT%%",     clean_latex(exam_content))
    latex = latex.replace("%%SOLUTION_CONTENT%%", build_solution_block(clean_latex(solution_content)))
    return latex


def compile_latex(latex_code: str, work_dir: str) -> tuple[bool, str]:
    os.makedirs(work_dir, exist_ok=True)

    if os.path.exists("logo.png"):
        shutil.copy("logo.png", os.path.join(work_dir, "logo.png"))
    else:
        print("  ⚠️  WARNING: logo.png not found!")

    tex_path = os.path.join(work_dir, "exam.tex")
    with open(tex_path, "w", encoding="utf-8") as f:
        f.write(latex_code)

    print(f"  📄 Written: {tex_path}")

    full_log = ""
    for i in range(2):
        print(f"  🔄 xelatex run {i+1}/2...")
        result = subprocess.run(
            ["xelatex", "-interaction=nonstopmode", "exam.tex"],
            cwd=work_dir,
            capture_output=True,
            timeout=120
        )
        full_log = result.stdout.decode(errors="ignore")

    pdf_exists = os.path.exists(os.path.join(work_dir, "exam.pdf"))

    if not pdf_exists:
        log_path = os.path.join(work_dir, "exam.log")
        if os.path.exists(log_path):
            log_text = open(log_path, encoding="utf-8", errors="ignore").read()
            error_lines = [l for l in log_text.splitlines()
                           if l.startswith("!") or "Error" in l]
            print("  ❌ Compile errors:")
            for e in error_lines:
                print(f"     {e}")
            return False, "\n".join(error_lines)

    return pdf_exists, ""


@app.post("/process")
async def process_exam(file: UploadFile = File(...)):
    print(f"\n{'='*60}")
    print(f"📥 Received: {file.filename}")

    pdf_bytes = await file.read()
    print(f"   Size: {len(pdf_bytes)/1024:.1f} KB")
    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")

  # ── Step 1: Extract metadata ──
    print("\n🤖 Step 1: Extracting metadata (subject, year, duration)...")
    try:
        meta_message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=500,
            system=SYSTEM_PROMPT_METADATA,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_b64}
                    },
                    {"type": "text", "text": "Extract the subject, year, and duration from this exam. Return only the JSON object."}
                ]
            }]
        )
        meta = json.loads(clean_json_response(meta_message.content[0].text))
        subject  = meta.get("subject",  "الرياضيات")
        year     = meta.get("year",     "----")
        duration = meta.get("duration", "----")
        print(f"  ✅ Subject: {subject} | Year: {year} | Duration: {duration}")

    except Exception as e:
        print(f"  ⚠️  Metadata extraction failed: {e} — using defaults")
        subject, year, duration = "الرياضيات", "----", "----"

    # ── Step 2: Extract exam questions ──
    print("\n🤖 Step 2: Extracting exam questions...")
    try:
        exam_message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=16000,
            system=SYSTEM_PROMPT_EXAM,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_b64}
                    },
                    {"type": "text", "text": "Extract only the exam questions section into LaTeX. No preamble, no markdown fences."}
                ]
            }]
        )
        exam = clean_latex(exam_message.content[0].text)
        print(f"  ✅ Exam content: {len(exam)} characters")
        print(f"  📝 Preview: {exam[:200]}...")

    except Exception as e:
        print(f"  ❌ Exam extraction failed: {e}")
        return JSONResponse(status_code=500, content={
            "step": "claude_exam", "error": str(e)
        })

    # ── Step 3: Extract solution ──
    print("\n🤖 Step 3: Extracting solution...")
    try:
        solution_message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=16000,
            system=SYSTEM_PROMPT_SOLUTION,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_b64}
                    },
                    {"type": "text", "text": "Extract only the solution/correction section into LaTeX. No preamble, no markdown fences. If no solution exists return exactly: NO_SOLUTION"}
                ]
            }]
        )
        solution_raw = clean_latex(solution_message.content[0].text)
        solution = "" if solution_raw.strip() == "NO_SOLUTION" else solution_raw
        print(f"  ✅ Solution content: {len(solution)} characters" if solution else "  ℹ️  No solution found in document")

    except Exception as e:
        print(f"  ⚠️  Solution extraction failed: {e} — continuing without solution")
        solution = ""
    

    # ── Step 3: Build full LaTeX ──
    print("\n⚙️  Step 3: Building LaTeX document...")
    full_latex = build_full_latex(subject, year, duration, exam, solution)

    job_id = str(uuid.uuid4())
    work_dir = os.path.join("outputs", job_id)
    os.makedirs(work_dir, exist_ok=True)

    # Save for inspection
    with open(os.path.join(work_dir, "exam_raw.tex"), "w", encoding="utf-8") as f:
        f.write(full_latex)
    print(f"  💾 Saved raw .tex to: {work_dir}/exam_raw.tex")

    # ── Step 4: Compile ──
    print("\n🖨️  Step 4: Compiling...")
    success, error_log = compile_latex(full_latex, work_dir)

    # ── Step 5: Auto-fix if failed ──
    if not success:
        print("\n🔧 Step 5: Compile failed — asking Claude to fix...")
        try:
            fix_message = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=16000,
                messages=[{
                    "role": "user",
                    "content": (
                        f"This LaTeX document failed to compile with xelatex.\n\n"
                        f"EXAM CONTENT:\n{exam}\n\n"
                        f"SOLUTION CONTENT:\n{solution}\n\n"
                        f"ERRORS:\n{error_log}\n\n"
                        f"Return a fixed JSON with the same structure: "
                        f"{{\"subject\":\"...\",\"year\":\"...\",\"duration\":\"...\","
                        f"\"exam\":\"...\",\"solution\":\"...\"}}. "
                        f"Fix only the LaTeX errors. No markdown fences."
                    )
                }]
            )
            fixed = json.loads(clean_json_response(fix_message.content[0].text))
            full_latex = build_full_latex(
                fixed.get("subject", subject),
                fixed.get("year", year),
                fixed.get("duration", duration),
                fixed.get("exam", exam),
                fixed.get("solution", solution)
            )
        except Exception as e:
            print(f"  ❌ Fix attempt failed: {e}")
            return JSONResponse(status_code=500, content={
                "step": "compile",
                "error": "Compilation failed and auto-fix also failed.",
                "details": error_log
            })

        fix_dir = os.path.join("outputs", job_id + "_fix")
        success, error_log = compile_latex(full_latex, fix_dir)
        work_dir = fix_dir

    if not success:
        print(f"\n❌ Final failure: {error_log}")
        return JSONResponse(status_code=500, content={
            "step": "compile",
            "error": "LaTeX compilation failed after auto-fix.",
            "details": error_log,
            "tex_file": os.path.join(work_dir, "exam.tex")
        })

    pdf_out = os.path.join(work_dir, "exam.pdf")
    pdf_size = os.path.getsize(pdf_out)
    original_name = os.path.splitext(file.filename)[0]

    print(f"\n✅ SUCCESS — {pdf_out} ({pdf_size/1024:.1f} KB)")
    print(f"{'='*60}\n")

    return FileResponse(
        pdf_out,
        media_type="application/pdf",
        filename=f"{original_name}_clean.pdf"
    )


app.mount("/", StaticFiles(directory="static", html=True), name="static")