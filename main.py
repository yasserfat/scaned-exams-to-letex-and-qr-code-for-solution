import os
import uuid

from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from pipeline import process_exam_pdf

app = FastAPI()


@app.post("/process")
async def process_exam(file: UploadFile = File(...)):
    print(f"\n{'='*60}")
    print(f"Received: {file.filename}")

    pdf_bytes = await file.read()
    print(f"  Size: {len(pdf_bytes)/1024:.1f} KB")

    job_id  = str(uuid.uuid4())
    work_dir = os.path.join("outputs", job_id)

    try:
        result = process_exam_pdf(
            pdf_bytes,
            work_dir,
            original_filename=file.filename or "exam.pdf",
        )
    except Exception as e:
        print(f"  ERROR: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

    print(f"  subject: {result['subject']} | year: {result['year']}")
    print(f"  figures: {result['figures_extracted']}/{result['figures_total']}")
    print(f"  drive_url: {result['drive_url']}")
    print(f"{'='*60}\n")

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


app.mount("/", StaticFiles(directory="static", html=True), name="static")
