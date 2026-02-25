"""FastAPI web application for MatterOS.

Self-contained: no Node.js required. Uses HTMX + Jinja2 templates.
Localhost-only by default with bearer token auth.
"""

from __future__ import annotations

import asyncio
import json
import secrets
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from fastapi.templating import Jinja2Templates

from matteros.core.config import load_config
from matteros.core.factory import resolve_home
from matteros.core.store import SQLiteStore
from matteros.drafts.manager import DraftManager


AUTH_COOKIE_NAME = "matteros_session"
AUTH_QUERY_PARAM = "access_token"


def create_app(*, home: Path | None = None) -> FastAPI:
    home_dir = resolve_home(home)
    app = FastAPI(title="MatterOS", docs_url=None, redoc_url=None)
    templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

    # Generate a session token for bearer auth
    _token = secrets.token_urlsafe(32)
    app.state.web_token = _token
    app.state.auth_query_param = AUTH_QUERY_PARAM
    app.state.auth_cookie_name = AUTH_COOKIE_NAME

    def _store() -> SQLiteStore:
        return SQLiteStore(home_dir / "matteros.db")

    def _extract_bearer_token(request: Request) -> str | None:
        authorization = request.headers.get("authorization")
        if not authorization:
            return None
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() != "bearer" or not value:
            return None
        return value.strip()

    def _is_authorized(candidate: str | None) -> bool:
        if not candidate:
            return False
        return secrets.compare_digest(candidate, _token)

    @app.middleware("http")
    async def _auth_middleware(request: Request, call_next):
        bearer_token = _extract_bearer_token(request)
        cookie_token = request.cookies.get(AUTH_COOKIE_NAME)
        query_token = request.query_params.get(AUTH_QUERY_PARAM)

        presented_token = bearer_token or cookie_token or query_token
        if not _is_authorized(presented_token):
            return Response(
                status_code=401,
                content=(
                    "Unauthorized. Provide a valid bearer token or open the bootstrap URL "
                    "printed by `matteros web`."
                ),
                media_type="text/plain",
            )

        response = await call_next(request)
        if _is_authorized(query_token):
            response.set_cookie(
                key=AUTH_COOKIE_NAME,
                value=_token,
                httponly=True,
                samesite="strict",
            )
        return response

    @app.on_event("startup")
    async def _startup() -> None:
        # Ensure DB exists
        _store()

    # ---------- Dashboard ----------

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request) -> HTMLResponse:
        store = _store()
        conn = store._connect()
        try:
            run_count = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
            recent_runs = conn.execute(
                "SELECT id, playbook_name, status, started_at, dry_run "
                "FROM runs ORDER BY started_at DESC LIMIT 10"
            ).fetchall()
            pending_approvals = conn.execute(
                "SELECT COUNT(*) FROM approvals WHERE decision = 'pending'"
            ).fetchone()[0]
        finally:
            conn.close()

        loaded = load_config(path=home_dir / "config.yml", home=home_dir)
        cfg = loaded.config

        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "run_count": run_count,
            "pending_approvals": pending_approvals,
            "recent_runs": [dict(r) for r in recent_runs],
            "config": cfg,
            "home": str(home_dir),
        })

    # ---------- Runs ----------

    @app.get("/runs", response_class=HTMLResponse)
    async def runs_page(request: Request) -> HTMLResponse:
        store = _store()
        conn = store._connect()
        try:
            rows = conn.execute(
                "SELECT id, playbook_name, status, started_at, ended_at, dry_run "
                "FROM runs ORDER BY started_at DESC LIMIT 50"
            ).fetchall()
        finally:
            conn.close()

        return templates.TemplateResponse("runs.html", {
            "request": request,
            "runs": [dict(r) for r in rows],
        })

    @app.get("/runs/{run_id}", response_class=HTMLResponse)
    async def run_detail(request: Request, run_id: str) -> HTMLResponse:
        store = _store()
        conn = store._connect()
        try:
            run_row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
            if not run_row:
                raise HTTPException(status_code=404, detail="Run not found")
            steps = conn.execute(
                "SELECT * FROM steps WHERE run_id = ? ORDER BY id", (run_id,)
            ).fetchall()
            events = conn.execute(
                "SELECT * FROM audit_events WHERE run_id = ? ORDER BY seq", (run_id,)
            ).fetchall()
        finally:
            conn.close()

        return templates.TemplateResponse("run_detail.html", {
            "request": request,
            "run": dict(run_row),
            "steps": [dict(s) for s in steps],
            "events": [dict(e) for e in events],
        })

    # ---------- Approvals ----------

    @app.get("/approvals", response_class=HTMLResponse)
    async def approvals_page(request: Request) -> HTMLResponse:
        store = _store()
        conn = store._connect()
        try:
            rows = conn.execute(
                "SELECT a.*, r.playbook_name FROM approvals a "
                "JOIN runs r ON a.run_id = r.id "
                "ORDER BY a.created_at DESC LIMIT 50"
            ).fetchall()
        finally:
            conn.close()

        return templates.TemplateResponse("approvals.html", {
            "request": request,
            "approvals": [dict(r) for r in rows],
        })

    # ---------- Drafts ----------

    @app.get("/drafts", response_class=HTMLResponse)
    async def drafts_page(request: Request) -> HTMLResponse:
        store = _store()
        manager = DraftManager(store)
        drafts = manager.list_drafts(limit=50)
        return templates.TemplateResponse("drafts.html", {
            "request": request,
            "drafts": drafts,
        })

    @app.post("/drafts/{draft_id}/approve")
    async def approve_draft(draft_id: str) -> Response:
        store = _store()
        manager = DraftManager(store)
        manager.approve_draft(draft_id)
        return Response(status_code=204)

    @app.post("/drafts/{draft_id}/reject")
    async def reject_draft(draft_id: str) -> Response:
        store = _store()
        manager = DraftManager(store)
        manager.reject_draft(draft_id)
        return Response(status_code=204)

    # ---------- Audit ----------

    @app.get("/audit", response_class=HTMLResponse)
    async def audit_page(request: Request) -> HTMLResponse:
        store = _store()
        events = store.list_audit_events(limit=200)
        events.reverse()
        return templates.TemplateResponse("audit.html", {
            "request": request,
            "events": events,
        })

    # ---------- Settings ----------

    @app.get("/settings", response_class=HTMLResponse)
    async def settings_page(request: Request) -> HTMLResponse:
        loaded = load_config(path=home_dir / "config.yml", home=home_dir)
        return templates.TemplateResponse("settings.html", {
            "request": request,
            "config": loaded.config,
            "home": str(home_dir),
        })

    # ---------- SSE for real-time updates ----------

    @app.get("/events/stream")
    async def event_stream(since: int = Query(0, ge=0)) -> StreamingResponse:
        store = _store()

        async def generate():
            last_seq = since
            while True:
                with store.connection() as conn:
                    rows = conn.execute(
                        """
                        SELECT seq, run_id, event_type, step_id, data_json
                        FROM audit_events
                        WHERE seq > ?
                        ORDER BY seq ASC
                        LIMIT 100
                        """,
                        (last_seq,),
                    ).fetchall()

                if rows:
                    for row in rows:
                        last_seq = int(row["seq"])
                        payload = {
                            "seq": last_seq,
                            "type": row["event_type"],
                            "run_id": row["run_id"],
                            "step_id": row["step_id"],
                            "data": json.loads(row["data_json"]) if row["data_json"] else {},
                        }
                        yield f"id: {last_seq}\n"
                        yield f"data: {json.dumps(payload)}\n\n"
                else:
                    yield ": keepalive\n\n"

                await asyncio.sleep(1.0)

        return StreamingResponse(generate(), media_type="text/event-stream")

    # ---------- API endpoints ----------

    @app.get("/api/runs")
    async def api_runs(limit: int = Query(20, ge=1, le=100)) -> list[dict]:
        store = _store()
        conn = store._connect()
        try:
            rows = conn.execute(
                "SELECT id, playbook_name, status, started_at, ended_at, dry_run "
                "FROM runs ORDER BY started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    @app.get("/api/audit")
    async def api_audit(
        run_id: str | None = Query(None),
        limit: int = Query(50, ge=1, le=500),
    ) -> list[dict]:
        store = _store()
        if run_id:
            return store.list_audit_events_for_run(run_id=run_id)
        return store.list_audit_events(limit=limit)

    return app
