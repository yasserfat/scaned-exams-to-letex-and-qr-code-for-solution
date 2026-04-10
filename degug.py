import re
import os
import base64
import subprocess
import shutil
import anthropic
from dotenv import load_dotenv

load_dotenv()
client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

LATEX_TEMPLATE = open("template.tex", encoding="utf-8").read()

SYSTEM_PROMPT = """
You are an expert at transcribing scanned exam papers into clean LaTeX.
The exams may be in Arabic, French, English, or a mix.

Your job is to extract ONLY the exam content body and return it as LaTeX.

STRICT RULES:
- Return ONLY content that goes after \\vspace{0.5cm} in the template.
- Do NOT include \\documentclass, \\usepackage, \\begin{document}, \\end{document}, or any preamble.
- Do NOT include the 3-column header table — it is already in the template.
- Do NOT wrap output in markdown fences or backticks.
- Start directly with the first \\section* command.

FOR ARABIC EXAMS:
- Write Arabic text directly in UTF-8 Arabic script.
- Use \\section*{...} for section titles.
- Use \\begin{enumerate} ... \\end{enumerate} for numbered lists.
- Math goes inside $...$ or \\[...\\] as normal.

FOR ENGLISH OR FRENCH EXAMS:
- Wrap all non-Arabic text in \\begin{english}...\\end{english}
  or \\begin{french}...\\end{french} so RTL does not break it.

FOR MIXED EXAMS:
- Use \\begin{english}...\\end{english} or \\begin{french}...\\end{french}
  around each non-Arabic block. Arabic text needs no wrapper.

ALWAYS:
- Preserve ALL text faithfully — do not skip any question or instruction.
- Recreate math equations in proper LaTeX notation.
- Recreate geometric figures using TikZ when present.
- Preserve point values shown next to section titles.
"""

# ── Change this to your actual exam PDF path ──
PDF_PATH = "input/math.pdf"   

print(f"Reading: {PDF_PATH}")
pdf_bytes = open(PDF_PATH, "rb").read()
pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")

print("Sending to Claude...")
message = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=8000,
    system=SYSTEM_PROMPT,
    messages=[{
        "role": "user",
        "content": [
            {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": pdf_b64
                }
            },
            {
                "type": "text",
                "text": "Transcribe the exam content. Return only the LaTeX body — no preamble, no header table, no document tags, no markdown fences."
            }
        ]
    }]
)

raw = message.content[0].text

# Clean
raw = raw.strip()
raw = re.sub(r'^```[a-zA-Z]*\n?', '', raw)
raw = re.sub(r'\n?```$', '', raw)
raw = re.sub(r'\\begin\{document\}', '', raw)
raw = re.sub(r'\\end\{document\}', '', raw)
exam_content = raw.strip()

print("\n" + "="*60)
print("CLAUDE OUTPUT (full):")
print("="*60)
print(exam_content)
print("="*60)

# Build full LaTeX
full_latex = LATEX_TEMPLATE.replace("%%EXAM_CONTENT%%", exam_content)

# Save debug files
os.makedirs("debug_output", exist_ok=True)
if os.path.exists("logo.png"):
    shutil.copy("logo.png", "debug_output/logo.png")

with open("debug_output/exam.tex", "w", encoding="utf-8") as f:
    f.write(full_latex)

print("\nSaved: debug_output/exam.tex")
print("Running xelatex...")

result = subprocess.run(
    ["xelatex", "-interaction=nonstopmode", "exam.tex"],
    cwd="debug_output",
    capture_output=True,
    timeout=120
)

print("\n" + "="*60)
print("XELATEX OUTPUT:")
print("="*60)
print(result.stdout.decode(errors="ignore"))

if os.path.exists("debug_output/exam.pdf"):
    print("\n✅ SUCCESS — open debug_output/exam.pdf")
else:
    print("\n❌ FAILED — reading error log...")
    log_path = "debug_output/exam.log"
    if os.path.exists(log_path):
        log = open(log_path, encoding="utf-8", errors="ignore").read()
        # Print only error lines
        errors = [l for l in log.splitlines() if l.startswith("!") or "Error" in l or "error" in l]
        print("\nERRORS FOUND:")
        for e in errors:
            print(" ", e)
        print("\nFull log saved at: debug_output/exam.log")