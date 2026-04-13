# Scanned Exams to LaTeX + QR Code

Takes a scanned Arabic exam PDF, extracts content with Claude, compiles clean LaTeX PDFs, uploads the solution to Google Drive, and embeds a QR code in the subject paper.

## What it does

1. Compress the scanned PDF (DPI 100) to reduce API costs
2. Send to Claude Sonnet — single call extracts subject, year, duration, full exam LaTeX, solution LaTeX, and figure bounding boxes
3. Crop figures from the original PDF using Claude's bounding boxes
4. Compile `solution.pdf` with XeLaTeX + Amiri font
5. Upload solution to Google Drive (OAuth2, your personal account)
6. Generate QR code pointing to the Drive URL
7. Compile `subject.pdf` with the QR embedded and figures placed beside text

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

**Python packages:**

| Package | Purpose |
|---------|---------|
| `anthropic` | Claude API client |
| `fastapi` + `uvicorn` | Web server |
| `python-multipart` | File upload support for FastAPI |
| `python-dotenv` | Load `.env` file |
| `pymupdf` | PDF compression, page rendering, figure cropping |
| `opencv-python-headless` + `numpy` | Image processing for figure extraction |
| `qrcode[pil]` | QR code generation |
| `google-api-python-client` | Google Drive API |
| `google-auth` + `google-auth-httplib2` + `google-auth-oauthlib` | OAuth2 authentication for Drive |

Also needs XeLaTeX with the Amiri font:

```bash
# Arch
sudo pacman -S texlive-xetex texlive-langarabic

# Ubuntu/Debian
sudo apt install texlive-xetex texlive-lang-arabic fonts-amiri
```

**LaTeX packages** (included in the above distro installs):

| Package | Purpose |
|---------|---------|
| `xelatex` | Unicode-aware LaTeX compiler (required for Arabic) |
| `polyglossia` | Arabic + French/English multilingual support |
| `fontspec` | Custom font loading (Amiri) |
| `amiri` | Arabic font used for all text |
| `amsmath` + `amssymb` | Math notation |
| `array` + `multirow` | Header table layout |
| `fancyhdr` | Header/footer with logo and decorative border |
| `tikz` | Page border drawing |
| `graphicx` | Figure/QR code inclusion |
| `xcolor` | Color support |
| `enumitem` | List formatting |

### 2. Configure environment

Copy `.env.example` (or create `.env`):

```bash
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_DRIVE_FOLDER_ID=1ABC...XYZ
GOOGLE_DRIVE_PUBLIC=true
```

### 3. Google Drive OAuth setup

- Go to [Google Cloud Console](https://console.cloud.google.com) → create a project
- Enable **Google Drive API**
- Create credentials → **OAuth client ID** → **Desktop app** → download JSON
- Save it as `oauth_client.json` in the project folder
- On first upload, a browser tab opens — click Allow. Token saved to `token.json` forever after

### 4. Run the web UI

```bash
uvicorn main:app --reload
```

Open `http://localhost:8000`, drag a PDF, click Process.

### 5. Batch mode

Put PDFs in `exams_input/`, run:

```bash
python batch.py
```

Results land in `exams_output/<filename>/subject.pdf` (and `solution.pdf` if present).

## Project structure

```
src/
  claude.py           — Claude API call, system prompt, cost calculation
  pdf_utils.py        — PDF compression, page rendering, filename slug
  figures.py          — figure placeholder parse / crop / replace
  drive.py            — OAuth2 token management, Drive upload
  compiler.py         — LaTeX template fill, xelatex compile, QR generation
  orchestrator.py     — process_exam_pdf(), compile_pdfs() — wires all above
main.py               — FastAPI server (/process, /crops, /skip-crops, file serving)
batch.py              — CLI batch processor (reads exams_input/, writes exams_output/)
template_subject.tex  — LaTeX template for the exam paper
template_solution.tex — LaTeX template for the solution
static/index.html     — upload UI with 7-step progress
static/crop.html      — manual figure crop tool (canvas drag-to-select)
oauth_client.json     — Google OAuth credentials (not committed)
token.json            — saved OAuth token (auto-generated, not committed)
.env                  — secrets (not committed)
```

## Figure format

Claude returns figures as placeholders:

```
[FIGURE:name:arabic_label:pageN:top:left:bottom:right]
```

Example: `[FIGURE:circuit_1:دارة كهربائية:page1:0.10:0.00:0.45:0.60]`

These are cropped from the original PDF and placed beside the text at 40% text width using `wrapfig`.

## Cost

Single Claude Sonnet call per exam. With prompt caching:
- First call: ~$0.05–0.15 depending on PDF size
- Cached calls: ~$0.01–0.03 (system prompt cached at $0.30/M vs $3.00/M)

Cost is logged to the terminal and shown in the web UI debug box after each run.

## Files not committed

```
.env
*.json          (oauth_client.json, token.json, service account keys)
exams_input/
exams_output/
outputs/
jobs/
```
