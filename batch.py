"""
batch.py — Process all PDFs in exams_input/ automatically.
Run:  python batch.py

Results saved in exams_output/<stem>/subject.pdf (+ solution.pdf if present).
Figures are cropped automatically using Claude's bounding box estimates.
"""

import os
import json

from src.orchestrator import process_exam_pdf

INPUT_FOLDER  = "exams_input"
OUTPUT_FOLDER = "exams_output"
os.makedirs(INPUT_FOLDER,  exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

files = sorted(f for f in os.listdir(INPUT_FOLDER) if f.lower().endswith(".pdf"))
total = len(files)

if total == 0:
    print(f"No PDFs found in {INPUT_FOLDER}/")
    raise SystemExit(0)

print(f"\n{'='*60}")
print(f"{total} exam(s) to process")
print(f"{'='*60}")

done = failed = 0

for i, filename in enumerate(files, 1):
    print(f"\n[{i}/{total}] {filename}")
    stem    = os.path.splitext(filename)[0]
    out_dir = os.path.join(OUTPUT_FOLDER, stem)

    if os.path.exists(os.path.join(out_dir, "subject.pdf")):
        print("  Already done — skipping")
        done += 1
        continue

    try:
        raw_bytes = open(os.path.join(INPUT_FOLDER, filename), "rb").read()
        orig_kb   = len(raw_bytes) / 1024
        print(f"  Size: {orig_kb:.0f} KB")

        result = process_exam_pdf(
            raw_bytes,
            out_dir,
            original_filename=filename,
            compress=True,
            manual_crops=False,   # auto-crop using Claude's bounding boxes
        )

        # Rename output folder to smart stem (subject_year_date)
        smart_stem = result.get("stem", stem)
        smart_out_dir = os.path.join(OUTPUT_FOLDER, smart_stem)
        if smart_out_dir != out_dir and not os.path.exists(smart_out_dir):
            os.rename(out_dir, smart_out_dir)
            out_dir = smart_out_dir

        print(f"  Subject:  {result['subject']} | {result['year']}")
        print(f"  Figures:  {result['figures_extracted']}/{result['figures_total']}")
        print(f"  Cost:     ${result.get('cost_usd', 0):.4f}")
        if result["drive_url"]:
            print(f"  Drive:    {result['drive_url']}")

        # Write state.json for reference / web app
        state = {
            "subject":           result["subject"],
            "year":              result["year"],
            "duration":          result["duration"],
            "drive_url":         result["drive_url"],
            "figures_extracted": result["figures_extracted"],
            "figures_total":     result["figures_total"],
            "original_filename": filename,
        }
        with open(os.path.join(out_dir, "state.json"), "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

        subject_kb = os.path.getsize(os.path.join(out_dir, "subject.pdf")) / 1024
        print(f"  Done -> {out_dir}/subject.pdf ({subject_kb:.0f} KB)")
        if result["solution_pdf"] and os.path.exists(result["solution_pdf"]):
            sol_kb = os.path.getsize(result["solution_pdf"]) / 1024
            print(f"       -> {out_dir}/solution.pdf ({sol_kb:.0f} KB)")
        done += 1

    except Exception as e:
        print(f"  ERROR: {e}")
        failed += 1

print(f"\n{'='*60}")
print(f"Done: {done}   Failed: {failed}   Total: {total}")
print(f"Results: {OUTPUT_FOLDER}/")
print(f"{'='*60}\n")
