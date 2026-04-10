"""
compress_all.py — Compress all PDFs before batch processing.
Run ONCE before batch.py to reduce API costs by 50-80%.

Usage:  python compress_all.py
Then:   set INPUT_FOLDER = "exams_input_compressed" in batch.py
"""

import os
import fitz

INPUT  = "exams_input"
OUTPUT = "exams_input_compressed"
DPI    = 150  # increase to 200 if Claude misses small math symbols

os.makedirs(OUTPUT, exist_ok=True)
files = sorted([f for f in os.listdir(INPUT) if f.lower().endswith(".pdf")])
total = len(files)

if total == 0:
    print(f"No PDFs in {INPUT}/"); exit()

print(f"\n{'='*60}")
print(f"🗜️  Compressing {total} PDFs at {DPI} DPI")
print(f"{'='*60}\n")

orig_total = comp_total = 0

for i, filename in enumerate(files, 1):
    src = os.path.join(INPUT,  filename)
    dst = os.path.join(OUTPUT, filename)

    if os.path.exists(dst):
        print(f"[{i}/{total}] ⏭️  {filename} — already compressed"); continue

    orig_kb = os.path.getsize(src)/1024
    try:
        doc = fitz.open(src)
        out = fitz.open()
        mat = fitz.Matrix(DPI/72, DPI/72)
        for page in doc:
            pix = page.get_pixmap(matrix=mat, alpha=False)
            out.insert_pdf(fitz.open("pdf", pix.pdfocr_tobytes()))
        out.save(dst, deflate=True, garbage=4, clean=True)
        doc.close(); out.close()

        comp_kb = os.path.getsize(dst)/1024
        saving  = 100 - comp_kb/orig_kb*100
        orig_total += orig_kb; comp_total += comp_kb
        print(f"[{i}/{total}] ✅ {filename}")
        print(f"        {orig_kb:.0f} KB → {comp_kb:.0f} KB  ({saving:.0f}% saved)")
    except Exception as e:
        print(f"[{i}/{total}] ❌ {filename} — {e}")

print(f"\n{'='*60}")
if orig_total:
    print(f"Total: {orig_total:.0f} KB → {comp_total:.0f} KB  ({100-comp_total/orig_total*100:.0f}% overall)")
print(f"Output: {OUTPUT}/")
print(f"\nNext step: open batch.py and set INPUT_FOLDER = '{OUTPUT}'")
print(f"{'='*60}\n")