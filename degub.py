"""
debug_figures.py — Check what Claude extracts from a physics exam.
Run: python debug_figures.py your_exam.pdf
"""

import sys
import re
import os
import base64
import anthropic
import fitz
from dotenv import load_dotenv

load_dotenv()
client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

if len(sys.argv) < 2:
    print("Usage: python debug_figures.py path/to/exam.pdf")
    sys.exit(1)

pdf_path = sys.argv[1]
print(f"\n{'='*60}")
print(f"📄 Analyzing: {pdf_path}")

# Read PDF
pdf_bytes = open(pdf_path, "rb").read()
print(f"   Size: {len(pdf_bytes)/1024:.1f} KB")

# Check how many pages and what's on them
doc = fitz.open(pdf_path)
print(f"   Pages: {len(doc)}")
for i, page in enumerate(doc):
    images = page.get_images(full=True)
    text   = page.get_text().strip()
    print(f"   Page {i+1}: {len(images)} embedded image(s), text chars: {len(text)}")
doc.close()

# Compress
print("\n🗜️  Compressing...")
doc = fitz.open(stream=pdf_bytes, filetype="pdf")
out = fitz.open()
mat = fitz.Matrix(150/72, 150/72)
for page in doc:
    pix    = page.get_pixmap(matrix=mat, alpha=False)
    imgpdf = fitz.open("pdf", pix.pdfocr_tobytes())
    out.insert_pdf(imgpdf)
compressed = out.tobytes(deflate=True, garbage=4, clean=True)
doc.close(); out.close()
print(f"   {len(pdf_bytes)/1024:.1f} KB → {len(compressed)/1024:.1f} KB")
pdf_b64 = base64.standard_b64encode(compressed).decode("utf-8")

# Ask Claude to describe what it sees (no LaTeX, just describe)
print("\n🤖 Step 1: Asking Claude to DESCRIBE what it sees (figures, text, layout)...")
describe_msg = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=2000,
    messages=[{
        "role": "user",
        "content": [
            {
                "type": "document",
                "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_b64}
            },
            {
                "type": "text",
                "text": (
                    "Describe what you see in this exam PDF. For each page tell me:\n"
                    "1. What text/questions are present\n"
                    "2. What figures/diagrams/images are present (describe each one in detail)\n"
                    "3. What type each figure is: simple geometry (can be drawn in TikZ) or "
                    "complex science/physics diagram (needs a real image)\n"
                    "Be very specific about every figure you can see."
                )
            }
        ]
    }]
)

description = describe_msg.content[0].text
print("\n" + "="*60)
print("CLAUDE'S DESCRIPTION OF THE EXAM:")
print("="*60)
print(description)

# Now ask Claude to extract with explicit figure instructions
print("\n\n🤖 Step 2: Extracting LaTeX with explicit figure instructions...")
extract_msg = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=8000,
    system="""You are an expert at transcribing scanned Arabic exam papers into clean LaTeX.

FOR FIGURES — READ THIS CAREFULLY:
- Simple shapes (triangles, circles, axes, arrows): use TikZ
- ANY physics diagram, circuit, wave, optics, mechanics, electricity, 
  force diagram, apparatus, scientific equipment, ray diagram, 
  or any diagram that requires artistic detail: 
  YOU MUST use this EXACT placeholder format:
  \\begin{center}
  \\fbox{\\parbox{7cm}{\\centering\\textbf{[FIGURE:description_exN]}\\\\[4pt]{\\small أرفق الصورة هنا}}}
  \\end{center}
  
  IMPORTANT: Do NOT try to recreate physics diagrams in TikZ — 
  they will look wrong. ALWAYS use the placeholder for physics diagrams.
  
Return only the LaTeX body. No preamble. No markdown fences.""",
    messages=[{
        "role": "user",
        "content": [
            {
                "type": "document",
                "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_b64}
            },
            {
                "type": "text",
                "text": "Extract the exam questions. Use [FIGURE:name] placeholders for ALL physics/science diagrams. Return LaTeX body only."
            }
        ]
    }]
)

latex = extract_msg.content[0].text
print("\n" + "="*60)
print("EXTRACTED LaTeX:")
print("="*60)
print(latex[:3000])
if len(latex) > 3000:
    print(f"\n... (truncated, total {len(latex)} chars)")

# Count placeholders
placeholders = re.findall(r'\[FIGURE:[a-zA-Z0-9_]+\]', latex)
tikz_count   = latex.count(r'\begin{tikzpicture}')

print("\n" + "="*60)
print("SUMMARY:")
print("="*60)
print(f"  [FIGURE:...] placeholders found: {len(placeholders)}")
for p in placeholders:
    print(f"    → {p}")
print(f"  TikZ figures found: {tikz_count}")
print(f"  Total LaTeX chars: {len(latex)}")

# Save output for inspection
os.makedirs("debug_output", exist_ok=True)
with open("debug_output/description.txt", "w", encoding="utf-8") as f:
    f.write(description)
with open("debug_output/extracted.tex", "w", encoding="utf-8") as f:
    f.write(latex)

print(f"\n💾 Saved:")
print(f"   debug_output/description.txt  ← Claude's description of what it sees")
print(f"   debug_output/extracted.tex    ← Extracted LaTeX")
print(f"{'='*60}\n")