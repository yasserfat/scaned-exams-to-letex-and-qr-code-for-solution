# Pipeline Refactor: 4 Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the exam processing pipeline to produce two separate PDFs, embed a QR code linking to the solution on Google Drive, merge 3 Claude API calls into 1, and replace figure placeholders with real extracted images.

**Architecture:** Create `pipeline.py` as the single shared module containing all logic. `main.py` and `batch.py` become thin callers (~50-100 lines each). Two new LaTeX templates (`template_subject.tex`, `template_solution.tex`) replace the current combined `template.tex` for new output.

**Tech Stack:** Python 3.10+, anthropic SDK, PyMuPDF (fitz), OpenCV (opencv-python-headless), qrcode[pil], google-api-python-client, FastAPI, xelatex

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `pipeline.py` | CREATE | All shared logic: Claude call, compression, LaTeX building, compilation, figure extraction, Drive upload, QR |
| `template_subject.tex` | CREATE | Exam-only template with `%%QR_CODE%%` placeholder |
| `template_solution.tex` | CREATE | Solution-only template with styled Arabic header |
| `main.py` | MODIFY | Thin FastAPI wrapper — call `process_exam_pdf()`, return JSON + serve files |
| `batch.py` | MODIFY | Thin batch runner — call `process_exam_pdf()`, write state.json |
| `static/index.html` | MODIFY | 7-step UI, two download buttons, Drive URL display |
| `requirements.txt` | CREATE | All pip dependencies declared |
| `.env` | MODIFY | Add 3 new Google Drive variables |

---

## Task 1: Create `requirements.txt` and install dependencies

**Files:**
- Create: `requirements.txt`

- [ ] **Step 1: Create requirements.txt**

```
# requirements.txt
anthropic>=0.25.0
fastapi>=0.110.0
uvicorn>=0.29.0
python-dotenv>=1.0.0
pymupdf>=1.24.0
opencv-python-headless>=4.9.0
numpy>=1.26.0
qrcode[pil]>=7.4.2
google-api-python-client>=2.120.0
google-auth>=2.28.0
google-auth-httplib2>=0.2.0
python-multipart>=0.0.9
```

- [ ] **Step 2: Install dependencies**

Run: `pip install -r requirements.txt`

Expected: all packages install without error. Key check: `import cv2; import qrcode; from google.oauth2 import service_account` in a Python shell returns no errors.

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "chore: add requirements.txt with new dependencies"
```

---

## Task 2: Create `template_subject.tex`

**Files:**
- Create: `template_subject.tex`

This is `template.tex` with `%%SOLUTION_CONTENT%%` removed and `%%QR_CODE%%` added after `%%EXAM_CONTENT%%`.

- [ ] **Step 1: Create the file**

```latex
\documentclass[12pt,a4paper]{article} 
\usepackage{geometry} 
\geometry{margin=1.4cm, top=1.6cm, bottom=3.2cm}  

\usepackage{amsmath,amssymb} 
\usepackage{array,multirow} 
\usepackage{fancyhdr} 
\usepackage{tikz} 
\usepackage{graphicx} 
\usepackage{xcolor} 
\usepackage{enumitem} 

% ── Language Setup ──
\usepackage{polyglossia}
\setmainlanguage[numerals=maghrib]{arabic}
\setotherlanguage{french}
\setotherlanguage{english}

\usepackage{fontspec}
\setmainfont[
  Script=Arabic,
  Scale=1.15,
  AutoFakeBold=2.5
]{Amiri}
\newfontfamily\arabicfont[
  Script=Arabic,
  Scale=1.15,
  AutoFakeBold=2.5
]{Amiri}
\newfontfamily\frenchfont[AutoFakeBold=2.5]{Amiri}
\newfontfamily\englishfont[AutoFakeBold=2.5]{Amiri}

% ── Section Formatting ──
\makeatletter 
\renewcommand\section{\@startsection{section}{1}{\z@}%   
  {-2.5ex \@plus -1ex \@minus -.2ex}%   
  {1.5ex \@plus.2ex}%   
  {\normalfont\large\bfseries}} 
\makeatother  

% ── Header & Footer ──
\pagestyle{fancy} 
\fancyhf{} 
\renewcommand{\headrulewidth}{0pt} 
\renewcommand{\footrulewidth}{0pt} 

\fancyhead[C]{%
  \begin{tikzpicture}[remember picture, overlay]
    \draw[line width=2pt, black]       
      ([xshift=0.72cm, yshift=-0.72cm]current page.north west)       
      rectangle ([xshift=-0.72cm, yshift=0.72cm]current page.south east);     
    \draw[line width=0.6pt, black]       
      ([xshift=0.85cm, yshift=-0.85cm]current page.north west)       
      rectangle ([xshift=-0.85cm, yshift=0.88cm]current page.south east);   
    \begin{scope}[opacity=0.05]
      \node at (current page.center) {%
        \includegraphics[width=0.7\paperwidth]{logo.png}%
      };
    \end{scope}
  \end{tikzpicture}%
}

\fancyfoot[C]{%   
  \noindent\fbox{%     
    \begin{minipage}[c][1.1cm][c]{\dimexpr\linewidth-2\fboxsep-2\fboxrule\relax}%       
      \hspace{0.5em}{\large\bfseries بالتوفيـــــق}\hfill       
      \includegraphics[height=0.85cm]{logo.png}\hspace{0.5em}     
    \end{minipage}%   
  }% 
}  

\begin{document}
\fontseries{sb}\selectfont

%% HEADER TABLE
\noindent{\setlength{\tabcolsep}{5pt}%
\renewcommand{\arraystretch}{1.2}%
\begin{tabular}{|p{0.285\textwidth}|p{0.345\textwidth}|p{0.285\textwidth}|}
\hline
\multirow{2}{*}{%
  \parbox[c][3.8cm][c]{0.285\textwidth}{%
    \centering
    \textbf{الديوان الوطني للامتحانات والمسابقات}\\[6pt]
    \textbf{اختبار في مادة: %%SUBJECT%%}}} & \parbox[c][1.9cm][c]{0.345\textwidth}{%
  \centering
  \textbf{الجمهورية الجزائرية الديمقراطية الشعبية}} & \multirow{2}{*}{%
  \parbox[c][3.8cm][c]{0.285\textwidth}{%
    \centering
    \textbf{وزارة التربية الوطنية}}} \\ \cline{2-2} & \parbox[c][1.9cm][c]{0.345\textwidth}{%
  \centering
  \textbf{امتحان شهادة التعليم المتوسط}\\[4pt]
  دورة: %%YEAR%%\\[2pt]
  المدة: %%DURATION%%} & \\ \hline
\end{tabular}}

\vspace{0.5cm}

%%EXAM_CONTENT%%

%%QR_CODE%%

\end{document}
```

- [ ] **Step 2: Commit**

```bash
git add template_subject.tex
git commit -m "feat: add template_subject.tex with QR code placeholder"
```

---

## Task 3: Create `template_solution.tex`

**Files:**
- Create: `template_solution.tex`

Same preamble as `template.tex`. Body has the Arabic solution header hardcoded and `%%SOLUTION_CONTENT%%`. No `%%EXAM_CONTENT%%`, no `%%QR_CODE%%`.

- [ ] **Step 1: Create the file**

```latex
\documentclass[12pt,a4paper]{article} 
\usepackage{geometry} 
\geometry{margin=1.4cm, top=1.6cm, bottom=3.2cm}  

\usepackage{amsmath,amssymb} 
\usepackage{array,multirow} 
\usepackage{fancyhdr} 
\usepackage{tikz} 
\usepackage{graphicx} 
\usepackage{xcolor} 
\usepackage{enumitem} 

% ── Language Setup ──
\usepackage{polyglossia}
\setmainlanguage[numerals=maghrib]{arabic}
\setotherlanguage{french}
\setotherlanguage{english}

\usepackage{fontspec}
\setmainfont[
  Script=Arabic,
  Scale=1.15,
  AutoFakeBold=2.5
]{Amiri}
\newfontfamily\arabicfont[
  Script=Arabic,
  Scale=1.15,
  AutoFakeBold=2.5
]{Amiri}
\newfontfamily\frenchfont[AutoFakeBold=2.5]{Amiri}
\newfontfamily\englishfont[AutoFakeBold=2.5]{Amiri}

% ── Section Formatting ──
\makeatletter 
\renewcommand\section{\@startsection{section}{1}{\z@}%   
  {-2.5ex \@plus -1ex \@minus -.2ex}%   
  {1.5ex \@plus.2ex}%   
  {\normalfont\large\bfseries}} 
\makeatother  

% ── Header & Footer ──
\pagestyle{fancy} 
\fancyhf{} 
\renewcommand{\headrulewidth}{0pt} 
\renewcommand{\footrulewidth}{0pt} 

\fancyhead[C]{%
  \begin{tikzpicture}[remember picture, overlay]
    \draw[line width=2pt, black]       
      ([xshift=0.72cm, yshift=-0.72cm]current page.north west)       
      rectangle ([xshift=-0.72cm, yshift=0.72cm]current page.south east);     
    \draw[line width=0.6pt, black]       
      ([xshift=0.85cm, yshift=-0.85cm]current page.north west)       
      rectangle ([xshift=-0.85cm, yshift=0.88cm]current page.south east);   
    \begin{scope}[opacity=0.05]
      \node at (current page.center) {%
        \includegraphics[width=0.7\paperwidth]{logo.png}%
      };
    \end{scope}
  \end{tikzpicture}%
}

\fancyfoot[C]{%   
  \noindent\fbox{%     
    \begin{minipage}[c][1.1cm][c]{\dimexpr\linewidth-2\fboxsep-2\fboxrule\relax}%       
      \hspace{0.5em}{\large\bfseries بالتوفيـــــق}\hfill       
      \includegraphics[height=0.85cm]{logo.png}\hspace{0.5em}     
    \end{minipage}%   
  }% 
}  

\begin{document}
\fontseries{sb}\selectfont

%% HEADER TABLE
\noindent{\setlength{\tabcolsep}{5pt}%
\renewcommand{\arraystretch}{1.2}%
\begin{tabular}{|p{0.285\textwidth}|p{0.345\textwidth}|p{0.285\textwidth}|}
\hline
\multirow{2}{*}{%
  \parbox[c][3.8cm][c]{0.285\textwidth}{%
    \centering
    \textbf{الديوان الوطني للامتحانات والمسابقات}\\[6pt]
    \textbf{اختبار في مادة: %%SUBJECT%%}}} & \parbox[c][1.9cm][c]{0.345\textwidth}{%
  \centering
  \textbf{الجمهورية الجزائرية الديمقراطية الشعبية}} & \multirow{2}{*}{%
  \parbox[c][3.8cm][c]{0.285\textwidth}{%
    \centering
    \textbf{وزارة التربية الوطنية}}} \\ \cline{2-2} & \parbox[c][1.9cm][c]{0.345\textwidth}{%
  \centering
  \textbf{امتحان شهادة التعليم المتوسط}\\[4pt]
  دورة: %%YEAR%%\\[2pt]
  المدة: %%DURATION%%} & \\ \hline
\end{tabular}}

\vspace{0.5cm}

\begin{center}
  {\Large\bfseries ─────────────────────────────}\\[0.3em]
  {\Large\bfseries التصحيح النموذجي}\\[0.3em]
  {\Large\bfseries ─────────────────────────────}
\end{center}
\vspace{0.5cm}

%%SOLUTION_CONTENT%%

\end{document}
```

- [ ] **Step 2: Commit**

```bash
git add template_solution.tex
git commit -m "feat: add template_solution.tex for standalone solution PDF"
```

---

## Task 4: Create `pipeline.py` — cleaning helpers + Fix 3 (merged Claude call)

**Files:**
- Create: `pipeline.py`

This task creates the file with all imports, cleaning helpers, the merged system prompt, `extract_all_from_pdf()`, and `compress_pdf_bytes()`. No other functions yet.

- [ ] **Step 1: Create `pipeline.py`**

```python
"""
pipeline.py — shared exam processing logic.
Imported by main.py and batch.py.
"""

import re
import os
import json
import base64
import subprocess
import shutil

import anthropic
import fitz  # PyMuPDF
import cv2
import numpy as np
import qrcode
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from dotenv import load_dotenv

load_dotenv()

_client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

# Templates loaded at import time — must run from project root
SUBJECT_TEMPLATE  = open("template_subject.tex",  encoding="utf-8").read()
SOLUTION_TEMPLATE = open("template_solution.tex", encoding="utf-8").read()

# ── System prompt ──────────────────────────────────────────────────────────────

SYSTEM_PROMPT_UNIFIED = r"""You are an expert at reading scanned Arabic exam papers and transcribing them into clean LaTeX.

OUTPUT FORMAT — return ONLY this raw JSON, no markdown fences, no explanation:
{
  "subject":  "subject name in Arabic exactly as written, e.g. الرياضيات",
  "year":     "4-digit year only, e.g. 2020",
  "duration": "exam duration in Arabic exactly as written, e.g. ساعتان",
  "exam":     "<LaTeX body — questions only>",
  "solution": "<LaTeX body — solution only, or the string NO_SOLUTION>"
}

RULES FOR exam AND solution FIELDS:
- LaTeX body only — no \documentclass, no preamble, no \begin{document}/\end{document}.
- Do NOT wrap in markdown fences or backticks.
- Write Arabic text directly in UTF-8.
- Math expressions: $...$ inline or \[...\] display.
- English/French text: \begin{english}...\end{english} or \begin{french}...\end{french}.
- Use \section*{...} for section titles, \begin{enumerate}...\end{enumerate} for lists.
- Simple geometric figures: recreate using TikZ.
- Complex figures (biology diagrams, circuits, detailed illustrations): use this exact placeholder format:
    \begin{center}
    \fbox{\parbox{7cm}{\centering\textbf{[FIGURE:descriptive_name:pageN]}\\[4pt]{\small أرفق الصورة هنا}}}
    \end{center}
  where N is the 1-based page number in the input PDF where the figure appears.
  Use a descriptive snake_case name (e.g. circuit_ex1, force_diagram_q2).

RULES FOR exam FIELD:
- Extract ONLY the questions section (not the solution/correction).
- Do NOT include the header table.
- Start directly with the first \section* command.
- Preserve all point values and instructions completely.

RULES FOR solution FIELD:
- Extract ONLY the solution/correction section (التصحيح النموذجي / الحل النموذجي).
- Do NOT repeat the questions.
- If no solution section exists in the document, return the string: NO_SOLUTION
"""


# ── Cleaning helpers ──────────────────────────────────────────────────────────

def clean_json_response(raw: str) -> str:
    """Strip markdown fences if Claude wrapped the JSON."""
    raw = raw.strip()
    raw = re.sub(r'^```[a-zA-Z]*\n?', '', raw)
    raw = re.sub(r'\n?```$', '', raw)
    return raw.strip()


def clean_latex(raw: str) -> str:
    """Strip markdown fences and stray document tags from LaTeX body."""
    raw = raw.strip()
    raw = re.sub(r'^```[a-zA-Z]*\n?', '', raw)
    raw = re.sub(r'\n?```$', '', raw)
    raw = re.sub(r'\\begin\{document\}', '', raw)
    raw = re.sub(r'\\end\{document\}', '', raw)
    return raw.strip()


# ── Fix 3: single merged Claude call ──────────────────────────────────────────

def extract_all_from_pdf(pdf_b64: str) -> dict:
    """
    One Claude API call. Returns dict with keys:
    subject, year, duration, exam, solution
    Raises ValueError if response is not valid JSON.
    """
    msg = _client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=20000,
        system=SYSTEM_PROMPT_UNIFIED,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": pdf_b64,
                    },
                },
                {
                    "type": "text",
                    "text": "Extract all content from this exam PDF and return the unified JSON.",
                },
            ],
        }],
    )
    raw = msg.content[0].text
    try:
        return json.loads(clean_json_response(raw))
    except json.JSONDecodeError as e:
        raise ValueError(f"Claude returned invalid JSON: {e}\nRaw response (first 500 chars): {raw[:500]}")


def compress_pdf_bytes(pdf_bytes: bytes, dpi: int = 150) -> bytes:
    """Re-render each page at dpi and recompress. Reduces file size ~50-80%."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    out = fitz.open()
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    for page in doc:
        pix = page.get_pixmap(matrix=mat, alpha=False)
        imgpdf = fitz.open("pdf", pix.pdfocr_tobytes())
        out.insert_pdf(imgpdf)
    result = out.tobytes(deflate=True, garbage=4, clean=True)
    doc.close()
    out.close()
    return result
```

- [ ] **Step 2: Smoke-test the imports**

Run: `python -c "import pipeline; print('OK')"`

Expected: `OK` with no import errors. If you see `ModuleNotFoundError` for cv2, qrcode, or google.oauth2, run `pip install -r requirements.txt` first.

- [ ] **Step 3: Commit**

```bash
git add pipeline.py
git commit -m "feat: add pipeline.py with merged Claude call (Fix 3)"
```

---

## Task 5: Add LaTeX builders and `compile_latex` to `pipeline.py`

**Files:**
- Modify: `pipeline.py` (append functions)

- [ ] **Step 1: Append builder functions to `pipeline.py`**

Add these functions after `compress_pdf_bytes`:

```python
# ── Fix 1: LaTeX builders ──────────────────────────────────────────────────────

def build_subject_latex(
    subject: str,
    year: str,
    duration: str,
    exam_content: str,
    qr_image_path: str | None = None,
) -> str:
    """
    Fill template_subject.tex.
    qr_image_path: filename only (e.g. 'qr_code.png'), must be in work_dir.
    If None, %%QR_CODE%% becomes empty string.
    """
    if qr_image_path:
        qr_block = (
            "\n\\vspace{1cm}\n"
            "\\begin{center}\n"
            "  {\\small رمز الاستجابة السريعة للوصول إلى التصحيح النموذجي}\\\\[0.4em]\n"
            f"  \\includegraphics[width=3cm]{{{qr_image_path}}}\n"
            "\\end{center}\n"
        )
    else:
        qr_block = ""

    latex = SUBJECT_TEMPLATE
    latex = latex.replace("%%SUBJECT%%",      subject.strip()  or "الرياضيات")
    latex = latex.replace("%%YEAR%%",         year.strip()     or "----")
    latex = latex.replace("%%DURATION%%",     duration.strip() or "----")
    latex = latex.replace("%%EXAM_CONTENT%%", clean_latex(exam_content))
    latex = latex.replace("%%QR_CODE%%",      qr_block)
    return latex


def build_solution_latex(
    subject: str,
    year: str,
    duration: str,
    solution_content: str,
) -> str:
    """Fill template_solution.tex with solution body."""
    latex = SOLUTION_TEMPLATE
    latex = latex.replace("%%SUBJECT%%",          subject.strip()  or "الرياضيات")
    latex = latex.replace("%%YEAR%%",             year.strip()     or "----")
    latex = latex.replace("%%DURATION%%",         duration.strip() or "----")
    latex = latex.replace("%%SOLUTION_CONTENT%%", clean_latex(solution_content))
    return latex


def compile_latex(
    latex_code: str,
    work_dir: str,
    out_stem: str = "exam",
) -> tuple[bool, str]:
    """
    Write {out_stem}.tex to work_dir, run xelatex twice.
    Returns (success, error_log).
    Copies logo.png into work_dir if it exists in cwd.
    """
    os.makedirs(work_dir, exist_ok=True)

    if os.path.exists("logo.png"):
        shutil.copy("logo.png", os.path.join(work_dir, "logo.png"))
    else:
        print("  WARNING: logo.png not found in cwd")

    tex_path = os.path.join(work_dir, f"{out_stem}.tex")
    with open(tex_path, "w", encoding="utf-8") as f:
        f.write(latex_code)

    for _ in range(2):
        subprocess.run(
            ["xelatex", "-interaction=nonstopmode", f"{out_stem}.tex"],
            cwd=work_dir,
            capture_output=True,
            timeout=120,
        )

    pdf_path = os.path.join(work_dir, f"{out_stem}.pdf")
    if not os.path.exists(pdf_path):
        log_path = os.path.join(work_dir, f"{out_stem}.log")
        if os.path.exists(log_path):
            log_text = open(log_path, encoding="utf-8", errors="ignore").read()
            error_lines = [
                line for line in log_text.splitlines()
                if line.startswith("!") or "Error" in line
            ]
            return False, "\n".join(error_lines)
        return False, "PDF not created and no log found"

    return True, ""
```

- [ ] **Step 2: Quick sanity check**

Run: `python -c "from pipeline import build_subject_latex, build_solution_latex, compile_latex; print('OK')"`

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add pipeline.py
git commit -m "feat: add LaTeX builders and compile_latex to pipeline.py (Fix 1)"
```

---

## Task 6: Add figure extraction functions to `pipeline.py`

**Files:**
- Modify: `pipeline.py` (append functions)

- [ ] **Step 1: Append figure extraction functions**

Add after `compile_latex`:

```python
# ── Fix 4: Figure extraction ───────────────────────────────────────────────────

def parse_figure_placeholders(latex: str) -> list[dict]:
    """
    Find all [FIGURE:name:pageN] tokens in latex.
    Returns list of {"name": str, "page": int} dicts.
    :pageN is optional — defaults to page 1 if absent.
    """
    pattern = r'\[FIGURE:([\w_-]+)(?::page(\d+))?\]'
    seen = set()
    results = []
    for m in re.finditer(pattern, latex):
        name = m.group(1)
        page = int(m.group(2)) if m.group(2) else 1
        key = (name, page)
        if key not in seen:
            seen.add(key)
            results.append({"name": name, "page": page})
    return results


def extract_figures_from_pdf(
    pdf_path: str,
    figure_specs: list[dict],
    work_dir: str,
    dpi: int = 200,
) -> dict[str, str]:
    """
    For each spec {"name": str, "page": int}, render the PDF page at dpi,
    run OpenCV contour detection, crop the largest non-text region, save as PNG.

    Returns {name: absolute_png_path} for successfully extracted figures.
    Specs where no suitable contour is found are omitted — the caller keeps
    the original fbox placeholder for those.
    """
    doc = fitz.open(pdf_path)
    figure_map: dict[str, str] = {}

    for spec in figure_specs:
        name = spec["name"]
        page_idx = spec["page"] - 1  # convert 1-based to 0-based

        if page_idx >= len(doc):
            print(f"  WARNING: figure {name} references page {spec['page']} but PDF has {len(doc)} pages")
            continue

        # 1. Render page to high-DPI RGB image
        page = doc[page_idx]
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)

        # 2. Threshold: invert so dark marks become white blobs on black
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)

        # 3. Morphological close: join nearby marks into contiguous blobs
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (20, 20))
        closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

        # 4. Find external contours
        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # 5. Filter: minimum 100pt × 100pt, max 95% page width, max 60% page height
        #    aspect ratio 0.2–5.0 (excludes thin rules and tall narrow bars)
        min_px = int(100 * dpi / 72)
        max_w  = int(pix.width  * 0.95)
        max_h  = int(pix.height * 0.60)

        candidates = []
        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            if min_px <= w <= max_w and min_px <= h <= max_h and 0.2 <= w / h <= 5.0:
                candidates.append((w * h, x, y, w, h))

        if not candidates:
            print(f"  INFO: no figure contour found for {name} on page {spec['page']} — keeping placeholder")
            continue

        # 6. Pick largest candidate by area and add 5% padding
        candidates.sort(reverse=True)
        _, x, y, w, h = candidates[0]
        pad_x = int(w * 0.05)
        pad_y = int(h * 0.05)
        x1 = max(0, x - pad_x)
        y1 = max(0, y - pad_y)
        x2 = min(pix.width,  x + w + pad_x)
        y2 = min(pix.height, y + h + pad_y)

        # 7. Crop and save
        cropped = img[y1:y2, x1:x2]
        out_path = os.path.join(work_dir, f"figure_{name}.png")
        cv2.imwrite(out_path, cv2.cvtColor(cropped, cv2.COLOR_RGB2BGR))
        figure_map[name] = out_path
        print(f"  OK: extracted figure_{name}.png ({x2-x1}×{y2-y1}px)")

    doc.close()
    return figure_map


def replace_figure_placeholders(
    latex: str,
    figure_map: dict[str, str],
) -> str:
    """
    Replace fbox placeholder blocks for resolved figures with \\includegraphics.
    Unresolved placeholders (not in figure_map) are left untouched.

    Matches the exact fbox structure produced by SYSTEM_PROMPT_UNIFIED:
    \\begin{center}
    \\fbox{\\parbox{7cm}{...\\textbf{[FIGURE:name:pageN]}...}}
    \\end{center}
    """
    pattern = (
        r'\\begin\{center\}\s*'
        r'\\fbox\{\\parbox\{[^}]+\}\{[^}]*'
        r'\\textbf\{\[FIGURE:([\w_-]+)(?::page\d+)?\]\}'
        r'[^}]*\}\}\s*'
        r'\\end\{center\}'
    )

    def replacer(m: re.Match) -> str:
        name = m.group(1)
        if name in figure_map:
            fname = os.path.basename(figure_map[name])
            return (
                "\\begin{center}\n"
                f"\\includegraphics[width=0.8\\textwidth]{{{fname}}}\n"
                "\\end{center}"
            )
        return m.group(0)  # keep placeholder as-is

    return re.sub(pattern, replacer, latex, flags=re.DOTALL)
```

- [ ] **Step 2: Test placeholder parsing**

Run:
```python
python -c "
from pipeline import parse_figure_placeholders
latex = r'\fbox{\parbox{7cm}{\centering\textbf{[FIGURE:circuit_ex1:page2]}}}'
result = parse_figure_placeholders(latex)
assert result == [{'name': 'circuit_ex1', 'page': 2}], result
print('parse OK:', result)
"
```

Expected: `parse OK: [{'name': 'circuit_ex1', 'page': 2}]`

- [ ] **Step 3: Commit**

```bash
git add pipeline.py
git commit -m "feat: add figure extraction functions to pipeline.py (Fix 4)"
```

---

## Task 7: Add Drive upload and QR generation to `pipeline.py`

**Files:**
- Modify: `pipeline.py` (append functions)

- [ ] **Step 1: Append Drive and QR functions**

Add after `replace_figure_placeholders`:

```python
# ── Fix 2: Google Drive upload + QR code ──────────────────────────────────────

def upload_to_drive(
    local_pdf_path: str,
    filename: str,
    folder_id: str | None = None,
) -> str:
    """
    Upload local_pdf_path to Google Drive using a service account.
    Makes the file publicly readable (anyone with link can view).
    Returns the shareable URL: https://drive.google.com/file/d/{id}/view?usp=sharing

    Required env vars:
      GOOGLE_DRIVE_CREDENTIALS — path to service account JSON key file
    Optional env vars:
      GOOGLE_DRIVE_FOLDER_ID   — parent folder ID; uploads to root if absent
      GOOGLE_DRIVE_PUBLIC      — "true" (default) or "false"
    """
    creds_path = os.environ.get("GOOGLE_DRIVE_CREDENTIALS", "")
    if not creds_path or not os.path.exists(creds_path):
        raise RuntimeError(
            f"GOOGLE_DRIVE_CREDENTIALS is not set or file not found: '{creds_path}'"
        )

    creds = service_account.Credentials.from_service_account_file(
        creds_path,
        scopes=["https://www.googleapis.com/auth/drive"],
    )
    service = build("drive", "v3", credentials=creds)

    resolved_folder = folder_id or os.environ.get("GOOGLE_DRIVE_FOLDER_ID", "")
    metadata: dict = {"name": filename}
    if resolved_folder:
        metadata["parents"] = [resolved_folder]

    media = MediaFileUpload(local_pdf_path, mimetype="application/pdf", resumable=True)
    file_obj = (
        service.files()
        .create(body=metadata, media_body=media, fields="id")
        .execute()
    )
    file_id = file_obj["id"]

    if os.environ.get("GOOGLE_DRIVE_PUBLIC", "true").lower() == "true":
        service.permissions().create(
            fileId=file_id,
            body={"role": "reader", "type": "anyone"},
        ).execute()

    return f"https://drive.google.com/file/d/{file_id}/view?usp=sharing"


def generate_qr_code(url: str, output_path: str) -> str:
    """
    Generate a QR code PNG at output_path encoding url.
    Returns output_path (for chaining).
    """
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=6,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img.save(output_path)
    return output_path
```

- [ ] **Step 2: Test QR generation (no Drive credentials needed)**

Run:
```python
python -c "
import tempfile, os
from pipeline import generate_qr_code
with tempfile.TemporaryDirectory() as d:
    path = os.path.join(d, 'test_qr.png')
    result = generate_qr_code('https://example.com', path)
    assert os.path.exists(result), 'QR file not created'
    size = os.path.getsize(result)
    assert size > 500, f'QR file suspiciously small: {size} bytes'
    print(f'QR OK: {size} bytes')
"
```

Expected: `QR OK: <N> bytes` (typically 1500-3000 bytes)

- [ ] **Step 3: Commit**

```bash
git add pipeline.py
git commit -m "feat: add Drive upload and QR code generation to pipeline.py (Fix 2)"
```

---

## Task 8: Add `process_exam_pdf` orchestrator to `pipeline.py`

**Files:**
- Modify: `pipeline.py` (append function)

- [ ] **Step 1: Append the orchestrator**

Add at the end of `pipeline.py`:

```python
# ── Orchestrator ───────────────────────────────────────────────────────────────

def process_exam_pdf(
    pdf_bytes: bytes,
    work_dir: str,
    original_filename: str = "exam",
    compress: bool = True,
) -> dict:
    """
    Full pipeline: compress → Claude → figure extraction → compile solution →
    Drive upload → QR → compile subject.

    Returns:
    {
      "subject":           str,
      "year":              str,
      "duration":          str,
      "subject_pdf":       str,        # absolute path to subject.pdf
      "solution_pdf":      str | None, # absolute path to solution.pdf (None if no solution)
      "drive_url":         str | None, # Google Drive shareable URL (None if upload failed/skipped)
      "qr_png":            str | None, # absolute path to qr_code.png (None if not generated)
      "figures_extracted": int,
      "figures_total":     int,
    }

    Raises RuntimeError if subject.pdf compilation fails after retry.
    Raises ValueError if Claude returns invalid JSON.
    Drive upload failures are caught and logged — pipeline continues without QR.
    """
    os.makedirs(work_dir, exist_ok=True)

    # 1. Compress and encode
    data = compress_pdf_bytes(pdf_bytes) if compress else pdf_bytes
    pdf_b64 = base64.b64encode(data).decode()

    # 2. Single Claude call (Fix 3)
    print("  Calling Claude (single merged call)...")
    extracted = extract_all_from_pdf(pdf_b64)
    subject  = extracted.get("subject",  "")
    year     = extracted.get("year",     "----")
    duration = extracted.get("duration", "----")
    exam     = extracted.get("exam",     "")
    solution = extracted.get("solution", "")
    if solution.strip() == "NO_SOLUTION":
        solution = ""

    print(f"  Extracted: subject='{subject}' year='{year}' duration='{duration}'")

    # 3. Figure extraction (Fix 4)
    figures_total     = 0
    figures_extracted_count = 0
    if exam or solution:
        specs = parse_figure_placeholders(exam + "\n" + solution)
        figures_total = len(specs)
        if specs:
            print(f"  Found {figures_total} figure placeholder(s) — extracting...")
            input_pdf_path = os.path.join(work_dir, "input.pdf")
            with open(input_pdf_path, "wb") as f:
                f.write(data)
            figure_map = extract_figures_from_pdf(input_pdf_path, specs, work_dir)
            figures_extracted_count = len(figure_map)
            exam     = replace_figure_placeholders(exam,     figure_map)
            solution = replace_figure_placeholders(solution, figure_map)

    # 4. Compile solution.pdf (Fix 1)
    drive_url  = None
    qr_png     = None
    solution_pdf_path = None

    if solution.strip():
        print("  Compiling solution.pdf...")
        sol_latex = build_solution_latex(subject, year, duration, solution)
        ok, err = compile_latex(sol_latex, work_dir, out_stem="solution")
        if ok:
            solution_pdf_path = os.path.join(work_dir, "solution.pdf")
            print("  solution.pdf OK")
        else:
            print(f"  WARNING: solution.pdf compilation failed: {err}")

        # 5. Upload to Drive and generate QR (Fix 2)
        if solution_pdf_path and os.path.exists(solution_pdf_path):
            try:
                stem = os.path.splitext(original_filename)[0]
                print("  Uploading solution.pdf to Google Drive...")
                drive_url = upload_to_drive(solution_pdf_path, f"{stem}_solution.pdf")
                print(f"  Drive URL: {drive_url}")
                qr_png = generate_qr_code(
                    drive_url, os.path.join(work_dir, "qr_code.png")
                )
                print("  QR code generated")
            except Exception as e:
                print(f"  WARNING: Drive upload/QR failed: {e}")
                drive_url = None
                qr_png    = None

    # 6. Compile subject.pdf with QR if available (Fix 1 + Fix 2)
    qr_rel = "qr_code.png" if (qr_png and os.path.exists(qr_png)) else None
    print("  Compiling subject.pdf...")
    subj_latex = build_subject_latex(subject, year, duration, exam, qr_rel)
    ok, err = compile_latex(subj_latex, work_dir, out_stem="subject")

    if not ok and qr_rel:
        # QR might be causing a compile error — retry without it
        print("  Retrying subject.pdf without QR code...")
        subj_latex = build_subject_latex(subject, year, duration, exam, None)
        ok, err = compile_latex(subj_latex, work_dir, out_stem="subject")

    if not ok:
        raise RuntimeError(f"subject.pdf compilation failed:\n{err}")

    print("  subject.pdf OK")

    return {
        "subject":           subject,
        "year":              year,
        "duration":          duration,
        "subject_pdf":       os.path.join(work_dir, "subject.pdf"),
        "solution_pdf":      solution_pdf_path,
        "drive_url":         drive_url,
        "qr_png":            qr_png,
        "figures_extracted": figures_extracted_count,
        "figures_total":     figures_total,
    }
```

- [ ] **Step 2: Verify the full pipeline function imports cleanly**

Run: `python -c "from pipeline import process_exam_pdf; print('orchestrator OK')"`

Expected: `orchestrator OK`

- [ ] **Step 3: Commit**

```bash
git add pipeline.py
git commit -m "feat: add process_exam_pdf orchestrator to pipeline.py"
```

---

## Task 9: Refactor `main.py`

**Files:**
- Modify: `main.py`

Replace the entire file. The new `main.py` is a thin FastAPI wrapper around `process_exam_pdf`. It returns JSON (not a PDF directly), and exposes two file-serving routes.

- [ ] **Step 1: Replace `main.py`**

```python
"""
main.py — FastAPI web server.
Thin wrapper around pipeline.process_exam_pdf().
"""

import os
import uuid

from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from pipeline import process_exam_pdf

app = FastAPI()


@app.post("/process")
async def process_exam(file: UploadFile = File(...)):
    pdf_bytes = await file.read()
    job_id    = str(uuid.uuid4())
    work_dir  = os.path.join("outputs", job_id)

    try:
        result = process_exam_pdf(pdf_bytes, work_dir, file.filename or "exam")
    except ValueError as e:
        return JSONResponse(status_code=422, content={"error": str(e)})
    except RuntimeError as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Unexpected error: {e}"})

    return JSONResponse(content={
        "job_id":            job_id,
        "subject":           result["subject"],
        "year":              result["year"],
        "duration":          result["duration"],
        "drive_url":         result["drive_url"],
        "figures_extracted": result["figures_extracted"],
        "figures_total":     result["figures_total"],
        "has_solution":      result["solution_pdf"] is not None,
    })


@app.get("/outputs/{job_id}/subject.pdf")
async def get_subject(job_id: str):
    path = os.path.join("outputs", job_id, "subject.pdf")
    if not os.path.exists(path):
        return JSONResponse(status_code=404, content={"error": "subject.pdf not found"})
    return FileResponse(path, media_type="application/pdf", filename="subject.pdf")


@app.get("/outputs/{job_id}/solution.pdf")
async def get_solution(job_id: str):
    path = os.path.join("outputs", job_id, "solution.pdf")
    if not os.path.exists(path):
        return JSONResponse(status_code=404, content={"error": "solution.pdf not found"})
    return FileResponse(path, media_type="application/pdf", filename="solution.pdf")


app.mount("/", StaticFiles(directory="static", html=True), name="static")
```

- [ ] **Step 2: Verify main.py starts**

Run: `uvicorn main:app --port 8001 &` then `curl -s http://localhost:8001/ | head -5` then kill the background process.

Expected: HTML content from `static/index.html`. No import errors.

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "refactor: rewrite main.py as thin wrapper around pipeline.process_exam_pdf"
```

---

## Task 10: Refactor `batch.py`

**Files:**
- Modify: `batch.py`

Replace the entire file. The new `batch.py` is a thin batch runner.

- [ ] **Step 1: Replace `batch.py`**

```python
"""
batch.py — Batch exam processor.
Thin wrapper around pipeline.process_exam_pdf().

Usage:
  1. Place PDF files in exams_input/
  2. (Optional) Run compress_all.py first to pre-compress
  3. Run: python batch.py
  4. Outputs appear in exams_output/<filename>/
     - subject.pdf
     - solution.pdf  (if present in source)
     - state.json    (metadata + Drive URL + figure stats)
"""

import os
import json

from pipeline import process_exam_pdf

INPUT_FOLDER  = "exams_input"
OUTPUT_FOLDER = "exams_output"
os.makedirs(INPUT_FOLDER,  exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

files = sorted([f for f in os.listdir(INPUT_FOLDER) if f.lower().endswith(".pdf")])

if not files:
    print(f"No PDF files found in {INPUT_FOLDER}/")
    exit(0)

print(f"Found {len(files)} PDF(s) to process\n")

done    = 0
failed  = 0
skipped = 0

for filename in files:
    in_path  = os.path.join(INPUT_FOLDER, filename)
    out_stem = os.path.splitext(filename)[0]
    out_dir  = os.path.join(OUTPUT_FOLDER, out_stem)

    # Skip if already processed
    if os.path.exists(os.path.join(out_dir, "subject.pdf")):
        print(f"[SKIP] {filename} (already processed)")
        skipped += 1
        continue

    print(f"\n[{done + failed + skipped + 1}/{len(files)}] Processing: {filename}")

    with open(in_path, "rb") as f:
        raw_bytes = f.read()

    try:
        result = process_exam_pdf(raw_bytes, out_dir, filename, compress=True)
        done += 1

        # Write state.json
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

        figs = result["figures_extracted"]
        total_figs = result["figures_total"]
        drive = result["drive_url"] or "N/A"
        print(f"  DONE — figures: {figs}/{total_figs} | drive: {drive}")

    except Exception as e:
        failed += 1
        print(f"  FAILED: {e}")

print(f"\n{'='*50}")
print(f"Results: {done} done, {failed} failed, {skipped} skipped")
```

- [ ] **Step 2: Verify syntax**

Run: `python -c "import ast; ast.parse(open('batch.py').read()); print('syntax OK')"`

Expected: `syntax OK`

- [ ] **Step 3: Commit**

```bash
git add batch.py
git commit -m "refactor: rewrite batch.py as thin wrapper around pipeline.process_exam_pdf"
```

---

## Task 11: Update `static/index.html` — 7-step UI

**Files:**
- Modify: `static/index.html`

The UI needs to reflect the new 7-step flow and handle the new JSON response format (job_id-based, two download buttons).

- [ ] **Step 1: Read the current file first**

Read `static/index.html` fully before editing — understand the current step structure and JS fetch logic.

- [ ] **Step 2: Update the steps panel**

Replace the existing `<div>` steps block with these 7 steps (keep the same CSS class structure that's already in the file):

```html
<div class="step" id="step1">
  <span class="step-icon">⬆️</span>
  <span class="step-label">رفع ومعالجة الملف</span>
  <span class="step-detail" id="step1-detail"></span>
</div>
<div class="step" id="step2">
  <span class="step-icon">🤖</span>
  <span class="step-label">استخراج المحتوى (Claude)</span>
  <span class="step-detail" id="step2-detail"></span>
</div>
<div class="step" id="step3">
  <span class="step-icon">🖼️</span>
  <span class="step-label">استخراج الصور التلقائي</span>
  <span class="step-detail" id="step3-detail"></span>
</div>
<div class="step" id="step4">
  <span class="step-icon">📄</span>
  <span class="step-label">توليد ملف التصحيح</span>
  <span class="step-detail" id="step4-detail"></span>
</div>
<div class="step" id="step5">
  <span class="step-icon">☁️</span>
  <span class="step-label">رفع التصحيح إلى Google Drive</span>
  <span class="step-detail" id="step5-detail"></span>
</div>
<div class="step" id="step6">
  <span class="step-icon">📱</span>
  <span class="step-label">توليد رمز QR</span>
  <span class="step-detail" id="step6-detail"></span>
</div>
<div class="step" id="step7">
  <span class="step-icon">✅</span>
  <span class="step-label">توليد ورقة الامتحان النهائية</span>
  <span class="step-detail" id="step7-detail"></span>
</div>
```

- [ ] **Step 3: Update the JS fetch and response handling**

Replace the fetch block and response handler so that:

1. `POST /process` receives JSON (not a PDF blob).
2. Two download links are created from `job_id`.
3. Drive URL is shown if present.
4. Figures summary is shown.

Find the existing `fetch('/process', ...)` block and replace the entire promise chain with:

```javascript
fetch('/process', { method: 'POST', body: formData })
  .then(async response => {
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || 'Unknown server error');
    }
    return data;
  })
  .then(data => {
    // Mark all steps done (server handles actual step progress)
    ['step1','step2','step3','step4','step5','step6','step7'].forEach(id => {
      setStep(id, 'done', '');
    });

    // Populate step details
    setStep('step2', 'done', `${data.subject} — ${data.year}`);
    setStep('step3', 'done', `${data.figures_extracted}/${data.figures_total} صورة`);
    if (!data.has_solution) {
      setStep('step4', 'done', 'لا يوجد تصحيح');
      setStep('step5', 'done', '—');
      setStep('step6', 'done', '—');
    } else {
      setStep('step5', 'done', data.drive_url ? '✓' : 'تخطي');
      setStep('step6', 'done', data.drive_url ? '✓' : 'تخطي');
    }

    // Show download buttons
    const jobId = data.job_id;
    document.getElementById('finalStatus').innerHTML = `
      <div style="margin-top:1rem;">
        <a href="/outputs/${jobId}/subject.pdf" download="subject.pdf"
           style="display:inline-block;margin:0.5rem;padding:0.5rem 1rem;background:#2563eb;color:white;border-radius:6px;text-decoration:none;">
          تحميل ورقة الامتحان
        </a>
        ${data.has_solution ? `
        <a href="/outputs/${jobId}/solution.pdf" download="solution.pdf"
           style="display:inline-block;margin:0.5rem;padding:0.5rem 1rem;background:#16a34a;color:white;border-radius:6px;text-decoration:none;">
          تحميل التصحيح النموذجي
        </a>` : ''}
        ${data.drive_url ? `
        <div style="margin-top:0.75rem;font-size:0.9rem;">
          <a href="${data.drive_url}" target="_blank">رابط التصحيح على Google Drive</a>
        </div>` : ''}
      </div>
    `;
  })
  .catch(err => {
    setStep('step1', 'failed', err.message);
    document.getElementById('finalStatus').textContent = `خطأ: ${err.message}`;
  });
```

- [ ] **Step 4: Verify HTML is valid**

Run: `python -c "from html.parser import HTMLParser; p = HTMLParser(); p.feed(open('static/index.html').read()); print('HTML OK')"`

Expected: `HTML OK` (no exception)

- [ ] **Step 5: Commit**

```bash
git add static/index.html
git commit -m "feat: update web UI to 7-step flow with two download buttons"
```

---

## Task 12: Update `.env` with new variables

**Files:**
- Modify: `.env`

- [ ] **Step 1: Append to `.env`**

Add these lines at the end of `.env`:

```dotenv
# Google Drive integration (Fix 2)
GOOGLE_DRIVE_CREDENTIALS=/path/to/your/service-account-key.json
GOOGLE_DRIVE_FOLDER_ID=
GOOGLE_DRIVE_PUBLIC=true
```

> **Note:** Replace `/path/to/your/service-account-key.json` with the actual path to the service account JSON key downloaded from Google Cloud Console. The service account must have the Drive API enabled and the `https://www.googleapis.com/auth/drive` scope.

- [ ] **Step 2: Commit**

```bash
git add .env
git commit -m "chore: add Google Drive env variables to .env"
```

---

## Task 13: End-to-End Verification

- [ ] **Step 1: Verify pipeline imports cleanly**

```bash
python -c "
from pipeline import (
    clean_json_response, clean_latex,
    extract_all_from_pdf, compress_pdf_bytes,
    build_subject_latex, build_solution_latex, compile_latex,
    parse_figure_placeholders, extract_figures_from_pdf, replace_figure_placeholders,
    upload_to_drive, generate_qr_code,
    process_exam_pdf,
)
print('All imports OK')
"
```

Expected: `All imports OK`

- [ ] **Step 2: Test figure placeholder round-trip**

```bash
python -c "
from pipeline import parse_figure_placeholders, replace_figure_placeholders
latex = r'''
\begin{center}
\fbox{\parbox{7cm}{\centering\textbf{[FIGURE:my_circuit:page2]}\\[4pt]{\small أرفق الصورة هنا}}}
\end{center}
'''
specs = parse_figure_placeholders(latex)
assert specs == [{'name': 'my_circuit', 'page': 2}], specs

# Simulate a resolved figure
figure_map = {'my_circuit': '/tmp/figure_my_circuit.png'}
result = replace_figure_placeholders(latex, figure_map)
assert 'includegraphics' in result, result
assert 'FIGURE:my_circuit' not in result, result
print('placeholder round-trip OK')
"
```

Expected: `placeholder round-trip OK`

- [ ] **Step 3: Test Drive failure graceful degradation**

```bash
python -c "
import os, tempfile
os.environ['GOOGLE_DRIVE_CREDENTIALS'] = '/nonexistent/path.json'
from pipeline import upload_to_drive
try:
    upload_to_drive('/tmp/test.pdf', 'test.pdf')
    print('ERROR: should have raised')
except RuntimeError as e:
    print(f'Drive error handled correctly: {e}')
"
```

Expected: `Drive error handled correctly: GOOGLE_DRIVE_CREDENTIALS is not set or file not found: '/nonexistent/path.json'`

- [ ] **Step 4: Full end-to-end test via web UI**

```bash
uvicorn main:app --reload --port 8000
```

Open `http://localhost:8000`, upload `exam.pdf`, and verify:
- All 7 steps complete without error
- Two download buttons appear (`تحميل ورقة الامتحان` and `تحميل التصحيح النموذجي`)
- `subject.pdf` opens and contains only exam questions (no solution section)
- `solution.pdf` opens and contains only the solution section with Arabic header
- If Drive credentials are configured: Drive URL link appears and QR code is visible in `subject.pdf`
- If Drive credentials are NOT configured: subject.pdf still compiles (no QR), no crash

- [ ] **Step 5: Batch test**

```bash
cp exam.pdf exams_input/
python batch.py
ls exams_output/exam/
cat exams_output/exam/state.json
```

Expected:
- `exams_output/exam/subject.pdf` exists
- `exams_output/exam/solution.pdf` exists (if exam has solution)
- `state.json` contains `drive_url` key (null if Drive not configured)

- [ ] **Step 6: Final commit**

```bash
git add .
git commit -m "feat: complete 4-fix pipeline refactor — two PDFs, QR, single Claude call, figure extraction"
```
