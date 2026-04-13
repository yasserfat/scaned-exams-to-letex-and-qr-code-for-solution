# Pipeline Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split `pipeline.py` (530 lines, 10 concerns) into 6 focused modules under `src/`, then delete `pipeline.py` and update all callers.

**Architecture:** Create `src/` package with one module per concern (claude, pdf_utils, figures, drive, compiler, orchestrator). Each module is a direct cut of the existing code — no logic changes. Callers (`main.py`, `batch.py`, `qr_gen.py`, `drive_upload.py`) update one import line each.

**Tech Stack:** Python 3.11+, existing deps unchanged (anthropic, fitz/PyMuPDF, qrcode, google-auth, googleapiclient, xelatex)

---

## File map

| Action | Path | Responsibility |
|--------|------|---------------|
| Create | `src/__init__.py` | Empty package marker |
| Create | `src/claude.py` | Claude API call, system prompt, cost calc, JSON/LaTeX cleaners |
| Create | `src/pdf_utils.py` | PDF compression, page rendering, filename slug |
| Create | `src/figures.py` | Figure placeholder parse / crop / replace |
| Create | `src/drive.py` | OAuth2 token management, Drive upload |
| Create | `src/compiler.py` | LaTeX template fill, xelatex compile, QR generation |
| Create | `src/orchestrator.py` | `process_exam_pdf()`, `compile_pdfs()` — wires the 5 modules |
| Modify | `main.py` | Update imports only |
| Modify | `batch.py` | Update imports only |
| Modify | `qr_gen.py` | Update imports only |
| Modify | `drive_upload.py` | Update imports only |
| Delete | `pipeline.py` | Gone — replaced by `src/` |

---

## Task 1: Create `src/` package and `src/claude.py`

**Files:**
- Create: `src/__init__.py`
- Create: `src/claude.py`

- [ ] **Step 1: Create `src/__init__.py`**

```bash
mkdir -p src
touch src/__init__.py
```

- [ ] **Step 2: Create `src/claude.py`**

Copy exactly the following functions and constants from `pipeline.py` into `src/claude.py`:
- `SYSTEM_PROMPT_UNIFIED` (lines 22–55)
- `clean_json_response()` (lines 59–64)
- `clean_latex()` (lines 67–74)
- `extract_all_from_pdf()` (lines 110–149)

The file needs these imports (copy from `pipeline.py` top, keeping only what's used here):

```python
import re
import json
import anthropic
from anthropic.types import TextBlock
from dotenv import load_dotenv
import os

load_dotenv()
_client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
```

- [ ] **Step 3: Verify import works**

```bash
python -c "from src.claude import extract_all_from_pdf, clean_json_response, clean_latex; print('OK')"
```

Expected output: `OK`

- [ ] **Step 4: Commit**

```bash
git add src/__init__.py src/claude.py
git commit -m "refactor: extract src/claude.py from pipeline"
```

---

## Task 2: Create `src/pdf_utils.py`

**Files:**
- Create: `src/pdf_utils.py`

- [ ] **Step 1: Create `src/pdf_utils.py`**

Copy exactly the following from `pipeline.py` into `src/pdf_utils.py`:
- `make_exam_stem()` (lines 77–92)
- `compress_pdf_bytes()` (lines 95–107)
- `render_page_images()` (lines 354–366)

Imports needed:

```python
import re
import os
import unicodedata
from datetime import datetime
import fitz
```

- [ ] **Step 2: Verify import works**

```bash
python -c "from src.pdf_utils import compress_pdf_bytes, render_page_images, make_exam_stem; print('OK')"
```

Expected output: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/pdf_utils.py
git commit -m "refactor: extract src/pdf_utils.py from pipeline"
```

---

## Task 3: Create `src/figures.py`

**Files:**
- Create: `src/figures.py`

- [ ] **Step 1: Create `src/figures.py`**

Copy exactly the following from `pipeline.py` into `src/figures.py`:
- `parse_figure_placeholders()` (lines 211–234)
- `extract_figures_from_pdf()` (lines 237–269)
- `replace_figure_placeholders()` (lines 272–284)

Imports needed:

```python
import re
import os
import fitz
```

- [ ] **Step 2: Verify import works**

```bash
python -c "from src.figures import parse_figure_placeholders, extract_figures_from_pdf, replace_figure_placeholders; print('OK')"
```

Expected output: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/figures.py
git commit -m "refactor: extract src/figures.py from pipeline"
```

---

## Task 4: Create `src/drive.py`

**Files:**
- Create: `src/drive.py`

- [ ] **Step 1: Create `src/drive.py`**

Copy exactly the following from `pipeline.py` into `src/drive.py`:
- `_SCOPES`, `_BASE_DIR`, `_OAUTH_CLIENT`, `_TOKEN_FILE` constants (lines 289–292)
- `_get_drive_service()` (lines 295–310)
- `upload_to_drive()` (lines 313–332)

Imports needed:

```python
import os
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

load_dotenv()
```

- [ ] **Step 2: Verify import works**

```bash
python -c "from src.drive import upload_to_drive; print('OK')"
```

Expected output: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/drive.py
git commit -m "refactor: extract src/drive.py from pipeline"
```

---

## Task 5: Create `src/compiler.py`

**Files:**
- Create: `src/compiler.py`

- [ ] **Step 1: Create `src/compiler.py`**

Copy exactly the following from `pipeline.py` into `src/compiler.py`:
- Template loading (lines 17–18): `SUBJECT_TEMPLATE` and `SOLUTION_TEMPLATE`
- `build_subject_latex()` (lines 154–170)
- `build_solution_latex()` (lines 173–180)
- `compile_latex()` (lines 183–206)
- `generate_qr_code()` (lines 335–344)
- `generate_placeholder_qr()` (lines 347–349)

Also copy `clean_latex()` from `pipeline.py` (lines 67–74) — compiler needs it for `build_subject_latex()` and `build_solution_latex()`. Do NOT import it from `src.claude`; keep a local copy to avoid circular imports.

Imports needed:

```python
import os
import re
import shutil
import subprocess
import qrcode
import qrcode.constants
```

- [ ] **Step 2: Verify import works**

```bash
python -c "from src.compiler import build_subject_latex, build_solution_latex, compile_latex, generate_qr_code, generate_placeholder_qr; print('OK')"
```

Expected output: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/compiler.py
git commit -m "refactor: extract src/compiler.py from pipeline"
```

---

## Task 6: Create `src/orchestrator.py`

**Files:**
- Create: `src/orchestrator.py`

- [ ] **Step 1: Create `src/orchestrator.py`**

Copy exactly the following from `pipeline.py` into `src/orchestrator.py`:
- `compile_pdfs()` (lines 369–417)
- `process_exam_pdf()` (lines 422–524)

Replace the internal imports at the top of the file. Instead of everything being in one file, import from the new modules:

```python
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
```

No other changes to the function bodies.

- [ ] **Step 2: Verify import works**

```bash
python -c "from src.orchestrator import process_exam_pdf, compile_pdfs; print('OK')"
```

Expected output: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/orchestrator.py
git commit -m "refactor: extract src/orchestrator.py from pipeline"
```

---

## Task 7: Update callers and delete `pipeline.py`

**Files:**
- Modify: `main.py` (import lines only)
- Modify: `batch.py` (import line only)
- Modify: `qr_gen.py` (import line only)
- Modify: `drive_upload.py` (import line only)
- Delete: `pipeline.py`

- [ ] **Step 1: Update `main.py` imports**

Find this block near the top of `main.py`:

```python
from pipeline import (
    process_exam_pdf,
    extract_figures_from_pdf,
    replace_figure_placeholders,
    compile_pdfs,
)
```

Replace with:

```python
from src.orchestrator import process_exam_pdf, compile_pdfs
from src.figures import extract_figures_from_pdf, replace_figure_placeholders
```

- [ ] **Step 2: Update `batch.py` imports**

Find in `batch.py`:

```python
from pipeline import process_exam_pdf
```

Replace with:

```python
from src.orchestrator import process_exam_pdf
```

- [ ] **Step 3: Update `qr_gen.py` imports**

Find in `qr_gen.py`:

```python
from pipeline import generate_qr_code
```

Replace with:

```python
from src.compiler import generate_qr_code
```

- [ ] **Step 4: Update `drive_upload.py` imports**

Find in `drive_upload.py`:

```python
from pipeline import upload_to_drive
```

Replace with:

```python
from src.drive import upload_to_drive
```

- [ ] **Step 5: Verify all callers import cleanly**

```bash
python -c "import main; print('main OK')"
python -c "import batch; print('batch OK')"
python -c "import qr_gen; print('qr_gen OK')"
python -c "import drive_upload; print('drive_upload OK')"
```

All four must print OK with no errors.

- [ ] **Step 6: Delete `pipeline.py`**

```bash
git rm pipeline.py
```

- [ ] **Step 7: Full smoke test**

```bash
python -c "
from src.claude import extract_all_from_pdf
from src.pdf_utils import compress_pdf_bytes, render_page_images, make_exam_stem
from src.figures import parse_figure_placeholders, extract_figures_from_pdf, replace_figure_placeholders
from src.drive import upload_to_drive
from src.compiler import build_subject_latex, build_solution_latex, compile_latex, generate_qr_code
from src.orchestrator import process_exam_pdf, compile_pdfs
print('All imports OK')
"
```

Expected output: `All imports OK`

- [ ] **Step 8: Commit**

```bash
git add main.py batch.py qr_gen.py drive_upload.py
git commit -m "refactor: update all callers to import from src/, delete pipeline.py"
```

---

## Task 8: Open pull request

- [ ] **Step 1: Push branch**

```bash
git push -u origin refactor/split-pipeline
```

- [ ] **Step 2: Open PR**

```bash
gh pr create \
  --title "refactor: split pipeline.py into src/ modules" \
  --body "$(cat <<'EOF'
## Summary

- Splits `pipeline.py` (530 lines, 10 concerns) into 6 focused modules under `src/`
- `src/claude.py` — Claude API call, system prompt, cost calc
- `src/pdf_utils.py` — PDF compression, page rendering, filename slug
- `src/figures.py` — figure placeholder parse / crop / replace
- `src/drive.py` — OAuth2 token management, Drive upload
- `src/compiler.py` — LaTeX template fill, xelatex compile, QR generation
- `src/orchestrator.py` — `process_exam_pdf()`, `compile_pdfs()` wiring all above
- Deletes `pipeline.py`; updates imports in `main.py`, `batch.py`, `qr_gen.py`, `drive_upload.py`

## No behaviour changes

All function signatures, return values, file formats, and API contracts are identical. The only change is where the code lives.

## Test plan

- [ ] `python -c "from src.orchestrator import process_exam_pdf, compile_pdfs; print('OK')"` passes
- [ ] `uvicorn main:app --reload` starts without import errors
- [ ] Upload a real exam PDF through the web UI — same output PDFs as before
EOF
)"
```

---

## Self-review

**Spec coverage check:**
- `src/claude.py` ✓ — Task 1
- `src/pdf_utils.py` ✓ — Task 2
- `src/figures.py` ✓ — Task 3
- `src/drive.py` ✓ — Task 4
- `src/compiler.py` ✓ — Task 5
- `src/orchestrator.py` ✓ — Task 6
- `pipeline.py` deleted ✓ — Task 7
- `main.py`, `batch.py`, `qr_gen.py`, `drive_upload.py` imports updated ✓ — Task 7

**Placeholder scan:** No TBDs, no vague steps. Every step has exact file paths and exact code.

**Type consistency:** `clean_latex()` intentionally duplicated in `src/compiler.py` (noted in Task 5) to avoid circular import. All other function names consistent across tasks.

**Scope:** Pure move, no logic changes. Tight scope.
