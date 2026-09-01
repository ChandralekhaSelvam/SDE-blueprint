"""HTTP surface.

Upload is deliberately two-phase. POST /api/inventory parses and validates the
file immediately and returns a summary plus an inventory_id; the client shows
what was actually read before committing to a run. That means a malformed file
fails at upload with a precise message, never halfway through a demo.
"""
from __future__ import annotations

import io
import json
import os
import csv
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from .cache import TaskCache
from .config import settings
from .agents.pipeline import Pipeline
from .ingest import IngestError, parse_inventory, summarise
from .schemas import Blueprint, StageEvent, Task

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
ALLOWED_SUFFIXES = (".csv", ".tsv", ".txt", ".xlsx", ".xlsm", ".xls", ".json")

INDUSTRIES = [
    {"id": "industrial", "label": "Industrial", "pattern": "Honeywell GBS pattern", "functions": ["Procurement", "Finance", "Supply chain"], "sample": "honeywell-p2p.csv"},
    {"id": "consumer_products", "label": "Consumer products", "pattern": "Unilever and KDP pattern", "functions": ["Legal", "Finance", "HR"], "sample": "unilever-legal.csv"},
    {"id": "life_sciences", "label": "Life sciences", "pattern": "CSL Pharma GBS pattern", "functions": ["Quality", "Regulatory", "Finance"], "sample": "csl-quality.csv"},
    {"id": "telecom", "label": "Telecom and media", "pattern": "TMT shared services", "functions": ["Customer service", "Billing", "Field operations"], "sample": "charter-care.csv"},
]

app = FastAPI(title="Agentification Blueprint Assistant", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")] if settings.cors_origins != "*" else ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs(settings.data_dir, exist_ok=True)
CACHE = TaskCache(os.path.join(settings.data_dir, "task_cache.sqlite"))

INVENTORIES: dict[str, dict[str, Any]] = {}
RUNS: dict[str, dict[str, Any]] = {}
AUDIT: list[dict[str, Any]] = []
MOCK_DIR = os.environ.get("MOCK_DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "mock-data"))


def audit(action: str, **fields: Any) -> None:
    AUDIT.append({"at": datetime.now(timezone.utc).isoformat(), "action": action, **fields})


# ----------------------------------------------------------------- metadata

@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "config": settings.describe(), "cache": CACHE.stats(), "runs": len(RUNS)}


@app.get("/api/industries")
def industries() -> dict[str, Any]:
    available = []
    for item in INDUSTRIES:
        path = os.path.join(MOCK_DIR, item["sample"])
        available.append({**item, "sample_available": os.path.exists(path)})
    return {"industries": available}


# ------------------------------------------------------------------- upload

class InventoryResponse(BaseModel):
    inventory_id: str
    filename: str
    summary: dict
    warnings: list[str]
    preview: list[dict]


def _register(tasks: list[Task], filename: str, warnings: list[str]) -> InventoryResponse:
    inventory_id = uuid.uuid4().hex[:10]
    INVENTORIES[inventory_id] = {"tasks": tasks, "filename": filename, "warnings": warnings, "at": time.time()}
    audit("inventory.parsed", inventory_id=inventory_id, filename=filename, rows=len(tasks))
    preview = [
        {"l1": t.l1_code, "l3": t.l3_code, "l4_code": t.l4_code, "l4_name": t.l4_name,
         "volume": t.volume_per_month, "fte": round(t.annual_hours / 1720.0, 2)}
        for t in tasks[:8]
    ]
    return InventoryResponse(
        inventory_id=inventory_id, filename=filename,
        summary=summarise(tasks), warnings=warnings, preview=preview,
    )


@app.post("/api/inventory", response_model=InventoryResponse)
async def upload_inventory(file: UploadFile = File(...)) -> InventoryResponse:
    """Parse an uploaded process inventory. Fails loudly here, never mid-run."""
    name = file.filename or "upload"
    if not name.lower().endswith(ALLOWED_SUFFIXES):
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type. Upload one of: {', '.join(ALLOWED_SUFFIXES)}.",
        )

    raw = await file.read()
    await file.close()

    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File is {len(raw) / 1e6:.1f} MB. The limit is 20 MB.")
    if not raw:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")

    try:
        tasks, warnings = parse_inventory(raw, name)
    except IngestError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - never leak a stack trace to the UI
        raise HTTPException(status_code=422, detail=f"Could not read {name}: {exc}") from exc

    return _register(tasks, name, warnings)


@app.post("/api/inventory/sample", response_model=InventoryResponse)
def load_sample(industry: str = Form(...)) -> InventoryResponse:
    """Load a bundled sample so the app is demonstrable with no file at hand."""
    meta = next((i for i in INDUSTRIES if i["id"] == industry), None)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"Unknown industry '{industry}'.")
    path = os.path.abspath(os.path.join(MOCK_DIR, meta["sample"]))
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"Sample file {meta['sample']} is not present in {MOCK_DIR}.")
    with open(path, "rb") as fh:
        raw = fh.read()
    tasks, warnings = parse_inventory(raw, meta["sample"])
    return _register(tasks, meta["sample"], warnings)


# --------------------------------------------------------------------- runs

class RunRequest(BaseModel):
    inventory_id: str
    industry: str = "consumer_products"
    function: str = "Legal"


@app.post("/api/runs")
def start_run(req: RunRequest) -> dict[str, str]:
    if req.inventory_id not in INVENTORIES:
        raise HTTPException(status_code=404, detail="Inventory not found. Upload the file again.")
    run_id = uuid.uuid4().hex[:12]
    RUNS[run_id] = {"status": "queued", "request": req.model_dump(), "events": [], "blueprint": None}
    audit("run.created", run_id=run_id, **req.model_dump())
    return {"run_id": run_id}


def _sse(payload: dict[str, Any], event: str = "message") -> str:
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"


@app.get("/api/runs/{run_id}/stream")
def stream_run(run_id: str) -> StreamingResponse:
    """Execute the pipeline, streaming one event per stage transition."""
    record = RUNS.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Run not found.")

    inv = INVENTORIES[record["request"]["inventory_id"]]

    def generate():
        record["status"] = "running"
        pipeline = Pipeline(settings, cache=CACHE)
        try:
            for item in pipeline.run(
                inv["tasks"], record["request"]["industry"], record["request"]["function"], list(inv["warnings"])
            ):
                if isinstance(item, StageEvent):
                    record["events"].append(item.model_dump())
                    yield _sse(item.model_dump(), "stage")
                elif isinstance(item, Blueprint):
                    record["blueprint"] = item.model_dump()
                    record["status"] = "done"
                    audit("run.completed", run_id=run_id, agents=len(item.agents), cost=item.cost.total_cost_usd)
                    yield _sse(item.model_dump(), "blueprint")
        except Exception as exc:  # noqa: BLE001 - surfaced as an SSE error frame
            record["status"] = "failed"
            audit("run.failed", run_id=run_id, error=str(exc))
            yield _sse({"message": str(exc)}, "error")
        yield _sse({"run_id": run_id, "status": record["status"]}, "end")

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@app.post("/api/runs/{run_id}/execute")
def execute_run(run_id: str) -> dict[str, Any]:
    """Synchronous alternative to the SSE stream, for scripting and tests."""
    record = RUNS.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    inv = INVENTORIES[record["request"]["inventory_id"]]
    pipeline = Pipeline(settings, cache=CACHE)
    blueprint = None
    for item in pipeline.run(inv["tasks"], record["request"]["industry"], record["request"]["function"], list(inv["warnings"])):
        if isinstance(item, StageEvent):
            record["events"].append(item.model_dump())
        else:
            blueprint = item
    record["blueprint"] = blueprint.model_dump() if blueprint else None
    record["status"] = "done"
    return record["blueprint"]


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    record = RUNS.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    return {"run_id": run_id, "status": record["status"], "blueprint": record["blueprint"], "events": record["events"]}


# ------------------------------------------------------------------ overrides

class OverrideRequest(BaseModel):
    task_id: str
    new_band: str
    reason: str
    reviewer: str = "unnamed reviewer"


@app.post("/api/runs/{run_id}/override")
def override_task(run_id: str, req: OverrideRequest) -> dict[str, Any]:
    """A human changes a band. Recorded, attributed and reversible."""
    record = RUNS.get(run_id)
    if record is None or not record.get("blueprint"):
        raise HTTPException(status_code=404, detail="Run not found or not finished.")
    if not req.reason.strip():
        raise HTTPException(status_code=400, detail="An override needs a reason. It goes into the audit log.")

    blueprint = record["blueprint"]
    touched = 0
    for row in blueprint["traceability"]:
        if row["task_id"] == req.task_id:
            row["band"] = req.new_band
            touched += 1
    for item in blueprint["scored_tasks"]:
        if item["task"]["id"] == req.task_id:
            item["human_override"] = {
                "from": item["band"], "to": req.new_band,
                "reason": req.reason, "reviewer": req.reviewer,
                "at": datetime.now(timezone.utc).isoformat(),
            }
            item["band"] = req.new_band
            touched += 1

    if not touched:
        raise HTTPException(status_code=404, detail=f"Task {req.task_id} is not in this run.")

    audit("band.override", run_id=run_id, task_id=req.task_id, to=req.new_band, reason=req.reason, reviewer=req.reviewer)
    return {"ok": True, "task_id": req.task_id, "band": req.new_band}


@app.get("/api/audit")
def get_audit() -> dict[str, Any]:
    return {"entries": AUDIT[-500:]}


# -------------------------------------------------------------------- export

@app.get("/api/runs/{run_id}/export/traceability.csv")
def export_traceability(run_id: str) -> StreamingResponse:
    record = RUNS.get(run_id)
    if record is None or not record.get("blueprint"):
        raise HTTPException(status_code=404, detail="Run not found or not finished.")

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["task_id", "l1", "l3", "l4_code", "l4_name", "agent_id", "agent_name", "band", "score", "gate", "resolution", "overrides", "evidence"])
    for row in record["blueprint"]["traceability"]:
        writer.writerow([
            row["task_id"], row["l1_code"], row["l3_code"], row["l4_code"], row["l4_name"],
            row["agent_id"], row["agent_name"], row["band"], row["score"], row["gate_id"] or "",
            row["resolution"],
            "; ".join(o["rule"] for o in row["overrides"]),
            "; ".join(f"{e['kind']}:{e['source']}" for e in row["evidence"]),
        ])
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="traceability-{run_id}.csv"'},
    )


@app.get("/api/runs/{run_id}/export/blueprint.json")
def export_blueprint(run_id: str) -> JSONResponse:
    record = RUNS.get(run_id)
    if record is None or not record.get("blueprint"):
        raise HTTPException(status_code=404, detail="Run not found or not finished.")
    return JSONResponse(
        record["blueprint"],
        headers={"Content-Disposition": f'attachment; filename="blueprint-{run_id}.json"'},
    )
