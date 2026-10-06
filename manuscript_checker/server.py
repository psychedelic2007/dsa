"""Web app. Start it with `python manuscript_checker/run.py` (works from any directory).

Uploads exist only for the duration of one request (large ones in a temporary file that is
deleted afterwards); nothing is stored and nothing leaves the machine running the server.
"""

import json
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from .analyze import analyze
from .extract import ROLES, load_document
from .report import to_dict

MAX_FILE_BYTES = 50 * 1024 * 1024
STATIC = Path(__file__).parent / "static"

app = FastAPI(title="Manuscript figure check")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC / "index.html")


LIMIT_KEYS = ("abstract_words", "main_text_words", "figures", "tables", "references")


@app.post("/api/check")
async def check(
    files: list[UploadFile] = File(...),
    roles: str = Form(...),
    ref_style: str = Form("auto"),
    limits: str = Form("{}"),
):
    try:
        role_list = json.loads(roles)
        limit_values = {k: int(v) for k, v in json.loads(limits).items() if k in LIMIT_KEYS and v}
    except (json.JSONDecodeError, TypeError, ValueError):
        raise HTTPException(400, "roles must be a JSON list and limits a JSON object of numbers")
    if len(role_list) != len(files):
        raise HTTPException(400, "one role per file is required")
    docs = []
    for upload, role in zip(files, role_list):
        if role not in ROLES:
            raise HTTPException(400, f"unknown role {role!r}")
        data = await upload.read()
        if len(data) > MAX_FILE_BYTES:
            raise HTTPException(413, f"{upload.filename} is larger than 50 MB")
        try:
            docs.append(load_document(upload.filename or "file", data, role))
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        except Exception as exc:  # corrupt or password-protected files
            raise HTTPException(422, f"Could not read {upload.filename}: {exc}")
    return to_dict(analyze(docs, ref_style, limit_values))
