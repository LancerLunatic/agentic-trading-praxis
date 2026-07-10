"""
Public, read-only decision-logic dashboard for the Agentic Trading Praxis system.

Design goals:
  * NO login required (safe for hiring managers / Praxis committee).
  * NO live trading — serves the graph topology + pre-recorded, sanitized runs.
  * Fails gracefully: if the real compiled graph can't be imported (missing keys
    or deps at build time), it falls back to a checked-in static topology so the
    page always renders.

Endpoints:
  GET  /            -> dashboard HTML
  GET  /health      -> readiness probe (used by Cloud Run)
  GET  /api/graph   -> Mermaid definition of the agent graph
  GET  /api/runs    -> list of sample decision runs (summaries)
  GET  /api/runs/{id} -> full sanitized trace for one run
"""
import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="Agentic Trading Praxis — Decision Logic Dashboard")


# ----------------------------------------------------------------------------
# Graph topology (Mermaid)
# ----------------------------------------------------------------------------
def _load_mermaid() -> str:
    """Prefer the live compiled graph; fall back to the static snapshot."""
    try:
        # Only attempt if creds are present so we never crash the public page.
        from main import app as compiled_app  # noqa: WPS433 (local import by design)

        return compiled_app.get_graph().draw_mermaid()
    except Exception:  # pragma: no cover - defensive fallback
        snapshot = DATA_DIR / "graph.mmd"
        if snapshot.exists():
            return snapshot.read_text(encoding="utf-8")
        return "graph TD;\n  A[Graph unavailable];"


_MERMAID_CACHE: str | None = None


def get_mermaid() -> str:
    global _MERMAID_CACHE
    if _MERMAID_CACHE is None:
        _MERMAID_CACHE = _load_mermaid()
    return _MERMAID_CACHE


# ----------------------------------------------------------------------------
# Sample runs (sanitized, pre-recorded)
# ----------------------------------------------------------------------------
def _load_runs() -> dict:
    path = DATA_DIR / "sample_runs.json"
    if not path.exists():
        return {"runs": []}
    return json.loads(path.read_text(encoding="utf-8"))


# ----------------------------------------------------------------------------
# Routes
# ----------------------------------------------------------------------------
@app.get("/health")
def health() -> JSONResponse:
    return JSONResponse({"status": "ok", "mode": "public-readonly-demo"})


@app.get("/api/graph", response_class=PlainTextResponse)
def api_graph() -> str:
    return get_mermaid()


@app.get("/api/runs")
def api_runs() -> dict:
    data = _load_runs()
    summaries = [
        {
            "id": r["id"],
            "title": r["title"],
            "ticker": r.get("ticker"),
            "final_decision": r.get("final_decision"),
            "confidence_score": r.get("confidence_score"),
            "regime": r.get("regime"),
        }
        for r in data.get("runs", [])
    ]
    return {"runs": summaries}


@app.get("/api/runs/{run_id}")
def api_run(run_id: str) -> dict:
    data = _load_runs()
    for r in data.get("runs", []):
        if r["id"] == run_id:
            return r
    raise HTTPException(status_code=404, detail="run not found")


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


# Serve static assets (css/js) if any are added later.
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
