# Pipeline Refactor Design

**Date:** 2026-04-13
**Scope:** Split `pipeline.py` into focused modules. No behaviour changes. `main.py` and `batch.py` import lines update; everything else stays the same.

---

## Problem

`pipeline.py` is 530 lines owning 10 unrelated concerns: Claude API calls, PDF compression, page rendering, figure parsing/cropping/replacement, Google Drive OAuth, Drive upload, QR code generation, LaTeX building, LaTeX compilation, and the top-level orchestration that wires them together.

Result: any change touches the whole file, nothing is independently testable, and the duplication between `process_exam_pdf()` and `compile_pdfs()` (same 40-line compile pattern in both) will silently diverge over time.

---

## Design

### New structure

```
src/
  __init__.py         (empty)
  claude.py           Claude API call, system prompt, cost calculation
  pdf_utils.py        PDF compression, page rendering, filename slug
  figures.py          Figure placeholder parse / crop / replace
  drive.py            OAuth2 token management, Drive upload
  compiler.py         LaTeX template filling, xelatex compilation, QR generation
  orchestrator.py     process_exam_pdf(), compile_pdfs() — imports the 5 above
```

`pipeline.py` is deleted. `main.py` and `batch.py` update their imports.

### Module responsibilities

**`src/claude.py`**
- `SYSTEM_PROMPT_UNIFIED` constant
- `extract_all_from_pdf(pdf_b64) -> dict` — single Claude Sonnet call, returns `{subject, year, duration, exam, solution, _cost_usd}`
- `clean_json_response(raw) -> str` — strip markdown fences from JSON
- `clean_latex(raw) -> str` — strip fences + `\begin{document}` wrappers

**`src/pdf_utils.py`**
- `compress_pdf_bytes(pdf_bytes, dpi=100) -> bytes` — re-render at lower DPI
- `render_page_images(pdf_path, work_dir, dpi=150) -> list[str]` — PNG per page for crop UI
- `make_exam_stem(subject, year) -> str` — Arabic subject + year → ASCII filename slug

**`src/figures.py`**
- `parse_figure_placeholders(latex) -> list[dict]` — extract `[FIGURE:name:label:pageN:top:left:bottom:right]`
- `extract_figures_from_pdf(pdf_path, figure_specs, work_dir, dpi=200) -> dict[str, str]` — crop regions → PNG files
- `replace_figure_placeholders(latex, figure_map) -> str` — swap fbox blocks with `\includegraphics`

**`src/drive.py`**
- `_get_drive_service()` — OAuth2 credential refresh / first-time browser auth
- `upload_to_drive(local_pdf_path, filename, folder_id=None) -> str` — upload + make public, return share URL

**`src/compiler.py`**
- `build_subject_latex(subject, year, duration, exam_content, qr_image_path) -> str`
- `build_solution_latex(subject, year, duration, solution_content) -> str`
- `compile_latex(latex_code, work_dir, out_stem) -> tuple[bool, str]` — write .tex, run xelatex ×2
- `generate_qr_code(url, output_path) -> str`
- `generate_placeholder_qr(output_path) -> str`

**`src/orchestrator.py`**
- `process_exam_pdf(pdf_bytes, work_dir, original_filename, compress, manual_crops) -> dict`
- `compile_pdfs(work_dir, subject, year, duration, exam, solution, original_filename) -> dict`

These two functions are the only ones with cross-module dependencies. They import from all five modules above.

### Import changes

**`main.py`** — before:
```python
from pipeline import (
    process_exam_pdf,
    extract_figures_from_pdf,
    replace_figure_placeholders,
    compile_pdfs,
)
```
After:
```python
from src.orchestrator import process_exam_pdf, compile_pdfs
from src.figures import extract_figures_from_pdf, replace_figure_placeholders
```

**`batch.py`** — before:
```python
from pipeline import process_exam_pdf
```
After:
```python
from src.orchestrator import process_exam_pdf
```

**`qr_gen.py`** — before:
```python
from pipeline import generate_qr_code
```
After:
```python
from src.compiler import generate_qr_code
```

**`drive_upload.py`** — before:
```python
from pipeline import upload_to_drive
```
After:
```python
from src.drive import upload_to_drive
```

### `pipeline.py` fate

Deleted. No shim. Two callers (`main.py`, `batch.py`) update their imports directly. Standalone scripts (`qr_gen.py`, `drive_upload.py`) update likewise.

### What does not change

- `main.py` logic — only import lines
- `batch.py` logic — only import lines
- `static/index.html`, `static/crop.html` — untouched
- `template_subject.tex`, `template_solution.tex` — untouched
- `.env`, `oauth_client.json`, `token.json` — untouched
- External API contracts, file formats, job directory layout — identical

---

## Data flow (unchanged)

```
PDF bytes
  → compress_pdf_bytes()          [pdf_utils]
  → extract_all_from_pdf()        [claude]
  → parse_figure_placeholders()   [figures]
  → render_page_images()          [pdf_utils]  ← crop UI path
  → extract_figures_from_pdf()    [figures]
  → replace_figure_placeholders() [figures]
  → build_solution_latex()        [compiler]
  → compile_latex()               [compiler]
  → upload_to_drive()             [drive]
  → generate_qr_code()            [compiler]
  → build_subject_latex()         [compiler]
  → compile_latex()               [compiler]
```

---

## Verification

```bash
# After refactor, both entry points must work identically
uvicorn main:app --reload          # web UI at localhost:8000
python batch.py                    # batch mode

# Quick smoke test (no real PDF needed for import check)
python -c "from src.orchestrator import process_exam_pdf, compile_pdfs; print('OK')"
python -c "from src.figures import extract_figures_from_pdf; print('OK')"
python -c "from src.claude import extract_all_from_pdf; print('OK')"
```

No runtime behaviour should change. The test is: upload a real exam PDF through the web UI and get the same PDFs out.
