import json
import sqlite3
import uuid
import warnings
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from threading import Lock
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, UnidentifiedImageError
from pipeline import LABELS, extract, validate
from pydantic import BaseModel, Field

ROOT = Path(__file__).parent
DATA = ROOT / "runtime"
DATA.mkdir(exist_ok=True)
DB = DATA / "documents.sqlite3"
app = FastAPI(title="Document AI Workbench")
lock = Lock()
engine = None


def connect():
    db = sqlite3.connect(DB)
    db.execute(
        "CREATE TABLE IF NOT EXISTS docs (id TEXT PRIMARY KEY, body TEXT NOT NULL)"
    )
    return db


@app.middleware("http")
async def local_only(request: Request, call_next):
    if request.url.hostname not in ("127.0.0.1", "localhost", "testserver"):
        return JSONResponse({"detail": "Local demo only"}, status_code=403)
    origin = request.headers.get("origin")
    if origin and origin != str(request.base_url).rstrip("/"):
        return JSONResponse({"detail": "Origin rejected"}, status_code=403)
    return await call_next(request)


def get_doc(doc_id):
    with connect() as db:
        row = db.execute("SELECT body FROM docs WHERE id=?", (doc_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Document not found")
    return json.loads(row[0])


def normalize(data):
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(413, "Limit: 8 MB")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            im = Image.open(BytesIO(data))
            if im.format not in ("PNG", "JPEG", "WEBP"):
                raise ValueError()
            if im.width * im.height > 12_000_000:
                raise HTTPException(413, "Limit: 12 megapixels")
            im.load()
            return im.convert("RGB")
    except HTTPException:
        raise
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        raise HTTPException(400, "Use a valid PNG, JPEG, or WebP image")


def process(data):
    global engine
    im = normalize(data)
    doc_id = uuid.uuid4().hex
    path = DATA / f"{doc_id}.png"
    im.save(path)
    # Serialize inference: one bounded CPU pipeline for this local learning app.
    with lock:
        if engine is None:
            from rapidocr_onnxruntime import RapidOCR

            engine = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=2)
        result, _elapsed = engine(str(path))
    lines = [
        {"id": i, "box": box, "text": text, "score": float(score)}
        for i, (box, text, score) in enumerate(result or [])
    ]
    fields = extract(lines)
    values = {k: v["value"] for k, v in fields.items()}
    doc = {
        "id": doc_id,
        "revision": 0,
        "status": "needs_review",
        "width": im.width,
        "height": im.height,
        "lines": lines,
        "extracted": fields,
        "values": values,
        "issues": validate(values),
        "audit": [
            {"action": "extracted", "at": datetime.now(timezone.utc).isoformat()}
        ],
        "model": "RapidOCR ONNX / bundled PP-OCR models",
        "extractor": "Label-based rules v1",
    }
    with connect() as db:
        db.execute("INSERT INTO docs VALUES (?,?)", (doc_id, json.dumps(doc)))
    return doc


@app.get("/api/documents")
def documents():
    with connect() as db:
        docs = [
            json.loads(r[0])
            for r in db.execute("SELECT body FROM docs ORDER BY rowid DESC LIMIT 30")
        ]
    return [
        {"id": d["id"], "status": d["status"], "invoice": d["values"]["invoice_number"]}
        for d in docs
    ]


@app.post("/api/upload")
def upload(file: Annotated[UploadFile, File()]):
    return process(file.file.read(8 * 1024 * 1024 + 1))


@app.post("/api/sample/{name}")
def sample(name: str):
    if name not in ("clean", "mismatch", "soft-scan"):
        raise HTTPException(404)
    return process((ROOT / "samples" / f"{name}.png").read_bytes())


@app.get("/api/documents/{doc_id}")
def read(doc_id: str):
    return get_doc(doc_id)


@app.get("/api/documents/{doc_id}/image")
def document_image(doc_id: str):
    get_doc(doc_id)
    return FileResponse(DATA / f"{doc_id}.png")


class Review(BaseModel):
    revision: int = Field(ge=0)
    values: dict[str, str]
    note: str = Field(min_length=3, max_length=1000)
    approve: bool = False


@app.post("/api/documents/{doc_id}/review")
def review(doc_id: str, body: Review):
    if set(body.values) != set(LABELS) or any(
        len(v) > 200 for v in body.values.values()
    ):
        raise HTTPException(
            422, "Provide the seven supported fields, at most 200 characters each"
        )
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT body FROM docs WHERE id=?", (doc_id,)).fetchone()
        if not row:
            raise HTTPException(404)
        doc = json.loads(row[0])
        if doc["revision"] != body.revision:
            raise HTTPException(409, "Stale revision; reload the document")
        issues = validate(body.values)
        if body.approve and issues:
            raise HTTPException(422, "; ".join(issues))
        changes = {
            k: {"before": doc["values"][k], "after": v}
            for k, v in body.values.items()
            if doc["values"][k] != v
        }
        doc.update(
            values=body.values,
            issues=issues,
            revision=doc["revision"] + 1,
            status="approved" if body.approve else "needs_review",
        )
        doc["audit"].append(
            {
                "action": "approved" if body.approve else "edited",
                "note": body.note,
                "changes": changes,
                "at": datetime.now(timezone.utc).isoformat(),
                "actor": "local reviewer",
            }
        )
        db.execute("UPDATE docs SET body=? WHERE id=?", (json.dumps(doc), doc_id))
    return doc


@app.get("/api/documents/{doc_id}/export")
def export(doc_id: str):
    return JSONResponse(
        get_doc(doc_id),
        headers={
            "Content-Disposition": f'attachment; filename="document-{doc_id}.json"'
        },
    )


app.mount("/", StaticFiles(directory=ROOT / "web", html=True), name="web")
