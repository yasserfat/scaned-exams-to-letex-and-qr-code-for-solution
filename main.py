import json
import os
import uuid

from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from pipeline import (
    process_exam_pdf,
    extract_figures_from_pdf,
    replace_figure_placeholders,
    compile_pdfs,
)

app = FastAPI()


# ── POST /process ─────────────────────────────────────────────────────────────

@app.post("/process")
async def process_exam(file: UploadFile = File(...)):
    print(f"\n{'='*60}")
    print(f"Received: {file.filename}")

    pdf_bytes = await file.read()
    print(f"  Size: {len(pdf_bytes)/1024:.1f} KB")

    job_id   = str(uuid.uuid4())
    work_dir = os.path.join("outputs", job_id)

    try:
        result = process_exam_pdf(
            pdf_bytes,
            work_dir,
            original_filename=file.filename or "exam.pdf",
            manual_crops=True,
        )
    except Exception as e:
        print(f"  ERROR: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

    # Claude found figures — hand off to crop UI
    if result.get("needs_crop"):
        # Persist state for the crop endpoint
        state = {
            "subject":           result["subject"],
            "year":              result["year"],
            "duration":          result["duration"],
            "exam_latex":        result["exam_latex"],
            "solution_latex":    result["solution_latex"],
            "figure_specs":      result["figure_specs"],
            "page_count":        result["page_count"],
            "original_filename": result["original_filename"],
        }
        with open(os.path.join(work_dir, "state.json"), "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

        print(f"  needs_crop: {len(result['figure_specs'])} figures on {result['page_count']} pages")
        return JSONResponse(content={
            "job_id":       job_id,
            "needs_crop":   True,
            "subject":      result["subject"],
            "year":         result["year"],
            "duration":     result["duration"],
            "figure_specs": result["figure_specs"],
            "page_count":   result["page_count"],
        })

    # No figures — PDFs already compiled
    print(f"  subject: {result['subject']} | year: {result['year']}")
    print(f"  figures: {result['figures_extracted']}/{result['figures_total']}")
    return JSONResponse(content={
        "job_id":            job_id,
        "needs_crop":        False,
        "subject":           result["subject"],
        "year":              result["year"],
        "duration":          result["duration"],
        "drive_url":         result["drive_url"],
        "figures_extracted": result["figures_extracted"],
        "figures_total":     result["figures_total"],
        "has_solution":      result["solution_pdf"] is not None,
    })


# ── POST /outputs/{job_id}/crops ──────────────────────────────────────────────

class CropItem(BaseModel):
    name: str
    page: int
    top: float
    left: float
    bottom: float
    right: float
    description: str = ""

class CropsPayload(BaseModel):
    crops: list[CropItem]

@app.post("/outputs/{job_id}/crops")
async def apply_crops(job_id: str, payload: CropsPayload):
    work_dir   = os.path.join("outputs", job_id)
    state_path = os.path.join(work_dir, "state.json")

    if not os.path.exists(state_path):
        return JSONResponse(status_code=404, content={"error": "job not found"})

    with open(state_path, encoding="utf-8") as f:
        state = json.load(f)

    input_pdf = os.path.join(work_dir, "input.pdf")
    if not os.path.exists(input_pdf):
        return JSONResponse(status_code=500, content={"error": "input.pdf missing"})

    # Build figure_specs from user crop coordinates
    figure_specs = [
        {
            "name":   c.name,
            "page":   c.page,
            "top":    c.top,
            "left":   c.left,
            "bottom": c.bottom,
            "right":  c.right,
        }
        for c in payload.crops
    ]

    # Save descriptions alongside state for future use
    state["crop_descriptions"] = {c.name: c.description for c in payload.crops if c.description}
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

    try:
        figure_map = extract_figures_from_pdf(input_pdf, figure_specs, work_dir)
        exam     = replace_figure_placeholders(state["exam_latex"],     figure_map)
        solution = replace_figure_placeholders(state["solution_latex"], figure_map)

        result = compile_pdfs(
            work_dir,
            state["subject"], state["year"], state["duration"],
            exam, solution,
            original_filename=state.get("original_filename", "exam.pdf"),
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

    return JSONResponse(content={
        "subject_pdf":  f"/outputs/{job_id}/subject.pdf",
        "solution_pdf": f"/outputs/{job_id}/solution.pdf" if result["solution_pdf"] else None,
        "drive_url":    result["drive_url"],
        "figures_extracted": len(figure_map),
        "figures_total":     len(figure_specs),
        "has_solution": result["solution_pdf"] is not None,
    })


# ── GET /outputs/{job_id}/skip-crops ─────────────────────────────────────────

@app.post("/outputs/{job_id}/skip-crops")
async def skip_crops(job_id: str):
    """Compile PDFs using Claude's original bbox estimates, no manual correction."""
    work_dir   = os.path.join("outputs", job_id)
    state_path = os.path.join(work_dir, "state.json")

    if not os.path.exists(state_path):
        return JSONResponse(status_code=404, content={"error": "job not found"})

    with open(state_path, encoding="utf-8") as f:
        state = json.load(f)

    input_pdf = os.path.join(work_dir, "input.pdf")
    figure_map = {}
    if os.path.exists(input_pdf) and state.get("figure_specs"):
        figure_map = extract_figures_from_pdf(input_pdf, state["figure_specs"], work_dir)

    exam     = replace_figure_placeholders(state["exam_latex"],     figure_map)
    solution = replace_figure_placeholders(state["solution_latex"], figure_map)

    try:
        result = compile_pdfs(
            work_dir,
            state["subject"], state["year"], state["duration"],
            exam, solution,
            original_filename=state.get("original_filename", "exam.pdf"),
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

    return JSONResponse(content={
        "subject_pdf":  f"/outputs/{job_id}/subject.pdf",
        "solution_pdf": f"/outputs/{job_id}/solution.pdf" if result["solution_pdf"] else None,
        "drive_url":    result["drive_url"],
        "has_solution": result["solution_pdf"] is not None,
    })


# ── File serving ──────────────────────────────────────────────────────────────

@app.get("/outputs/{job_id}/subject.pdf")
async def get_subject_pdf(job_id: str):
    path = os.path.join("outputs", job_id, "subject.pdf")
    if not os.path.exists(path):
        return JSONResponse(status_code=404, content={"error": "not found"})
    return FileResponse(path, media_type="application/pdf", filename="subject.pdf")


@app.get("/outputs/{job_id}/solution.pdf")
async def get_solution_pdf(job_id: str):
    path = os.path.join("outputs", job_id, "solution.pdf")
    if not os.path.exists(path):
        return JSONResponse(status_code=404, content={"error": "not found"})
    return FileResponse(path, media_type="application/pdf", filename="solution.pdf")


@app.get("/outputs/{job_id}/state.json")
async def get_state(job_id: str):
    path = os.path.join("outputs", job_id, "state.json")
    if not os.path.exists(path):
        return JSONResponse(status_code=404, content={"error": "not found"})
    return FileResponse(path, media_type="application/json")


@app.get("/outputs/{job_id}/pages/{filename}")
async def get_page_image(job_id: str, filename: str):
    if not filename.startswith("page_") or not filename.endswith(".png"):
        return JSONResponse(status_code=400, content={"error": "invalid filename"})
    path = os.path.join("outputs", job_id, filename)
    if not os.path.exists(path):
        return JSONResponse(status_code=404, content={"error": "not found"})
    return FileResponse(path, media_type="image/png")


app.mount("/", StaticFiles(directory="static", html=True), name="static")
