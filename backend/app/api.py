import asyncio
import json

from fastapi import FastAPI, Header, Request as HttpRequest
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from sqlalchemy import select, text

from app.contracts import (
    Admission, ControlInput, ProbeInput, ProjectInput, RevisionInput, Settlement, ToolCall, schemas,
)
from app.domain import Attempt, Candidate, Event, Family, Project, Receipt, Request, Revision, Run, Task
from app.services import Business, DomainError, require, scoped
from app.settings import ROOT, Settings
from app.storage import Storage


def public(row):
    return {c.name: getattr(row, c.name) for c in row.__table__.columns
            if c.name not in {"token_hash"}}


def create_app(settings=None):
    store = Storage(settings or Settings.local())
    business = Business(store)
    app = FastAPI(title="标书工作台", version="0.1.0")
    app.state.business, app.state.store = business, store

    @app.middleware("http")
    async def local_only(request: HttpRequest, call_next):
        host = request.headers.get("host", "").split(":")[0]
        if host not in {"127.0.0.1", "localhost", "testserver"}:
            return JSONResponse({"error": "LOCAL_HOST_REQUIRED"}, status_code=403)
        origin = request.headers.get("origin")
        if origin and origin not in {"http://127.0.0.1:8765", "http://localhost:8765",
                                     "http://127.0.0.1:5173", "http://localhost:5173"}:
            return JSONResponse({"error": "ORIGIN_DENIED"}, status_code=403)
        if request.url.path.startswith("/api") and request.method not in {"GET", "HEAD"}:
            if request.headers.get("x-bid-local") != "1":
                return JSONResponse({"error": "LOCAL_ACTION_HEADER_REQUIRED"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.exception_handler(DomainError)
    async def domain_error(_, exc):
        return JSONResponse({"error": exc.code}, status_code=exc.status)

    @app.exception_handler(ValidationError)
    async def validation_error(_, exc):
        return JSONResponse({"error": "INVALID_TOOL_PAYLOAD", "details": str(exc)}, status_code=422)

    @app.get("/api/health")
    def health():
        with store.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        manifest = ROOT / "runtime/builds/active.json"
        build = json.loads(manifest.read_text()) if manifest.exists() else None
        if build:
            build = {k: v for k, v in build.items() if k != "files"}
        return {"status": "ok", "database": store.engine.dialect.name, "runtime": "fixture",
                "build": build,
                "acceptance": {"L3": "not_run", "L4": "not_run"}}

    @app.get("/api/projects")
    def projects():
        with store.tx() as s:
            return [public(p) for p in s.scalars(select(Project).order_by(Project.created_at))]

    @app.post("/api/projects", status_code=201)
    def create_project(data: ProjectInput):
        return business.create_project(data)

    @app.post("/api/projects/{project_id}/revisions", status_code=201)
    def save_revision(project_id: str, data: RevisionInput):
        return business.save_revision(project_id, data)

    @app.get("/api/projects/{project_id}/revisions/{revision_id}")
    def get_revision(project_id: str, revision_id: str):
        with store.tx() as s:
            return public(scoped(s, Revision, revision_id, project_id))

    @app.post("/api/projects/{project_id}/runs", status_code=202)
    def create_run(project_id: str, data: ProbeInput):
        return business.create_probe(project_id, data)

    @app.post("/api/projects/{project_id}/runs/{run_id}/control")
    def control(project_id: str, run_id: str, data: ControlInput):
        return business.control(project_id, run_id, data)

    @app.get("/api/projects/{project_id}/workspace")
    def workspace(project_id: str):
        with store.tx() as s:
            p = s.get(Project, project_id)
            require(p is not None, "PROJECT_NOT_FOUND", 404)
            revisions = s.scalars(select(Revision).where(Revision.project_id == p.id,
                                                        Revision.kind != "baseline")).all()
            tasks = s.scalars(select(Task).where(Task.project_id == p.id)).all()
            ids = [t.id for t in tasks]
            candidates = s.scalars(select(Candidate).where(Candidate.task_id.in_(ids))).all()
            requests = s.scalars(select(Request).where(Request.project_id == p.id)).all()
            return {"project": public(p), "revisions": [public(r) for r in revisions],
                    "runs": [public(r) for r in s.scalars(select(Run).where(Run.project_id == p.id))],
                    "tasks": [public(t) for t in tasks], "candidates": [public(c) for c in candidates],
                    "attempts": [public(a) for a in s.scalars(select(Attempt).where(Attempt.task_id.in_(ids)))],
                    "receipts": [public(r) for r in s.scalars(select(Receipt).where(Receipt.task_id.in_(ids)))],
                    "families": [public(f) for f in s.scalars(select(Family).where(Family.project_id == p.id))],
                    "budget": {"requests": len(requests), "max_requests": p.max_requests,
                               "max_cost": p.max_cost,
                               "charged": sum(r.actual or 0 for r in requests if r.status == "settled"),
                               "held": sum(r.reservation for r in requests if r.status != "settled"),
                               "unknown": sum(r.status == "unknown" for r in requests)},
                    "acceptance": {"content": "not_run", "files": "not_run", "release": "not_run"}}

    @app.get("/api/projects/{project_id}/events")
    async def events(project_id: str, request: HttpRequest, after: int = 0,
                     last_event_id: str | None = Header(default=None)):
        with store.tx() as s:
            require(s.get(Project, project_id) is not None, "PROJECT_NOT_FOUND", 404)
        cursor = max(after, int(last_event_id or 0))

        async def stream():
            nonlocal cursor
            while not await request.is_disconnected():
                with store.tx() as s:
                    rows = s.scalars(select(Event).where(Event.project_id == project_id, Event.id > cursor)
                                     .order_by(Event.id).limit(100)).all()
                for row in rows:
                    cursor = row.id
                    yield f"id: {row.id}\nevent: business\ndata: {json.dumps(public(row), ensure_ascii=False)}\n\n"
                if not rows:
                    yield ": keepalive\n\n"
                await asyncio.sleep(0.5)
        return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

    def token(authorization):
        require(bool(authorization) and authorization.startswith("Bearer "), "TASK_TOKEN_DENIED", 403)
        return authorization[7:]

    @app.get("/internal/manifest")
    def manifest(authorization: str | None = Header(default=None)):
        return business.manifest(token(authorization))

    @app.get("/internal/schemas")
    def tool_schemas(authorization: str | None = Header(default=None)):
        business.manifest(token(authorization))
        return schemas()

    @app.post("/internal/tools")
    def tools(call: ToolCall, authorization: str | None = Header(default=None)):
        return business.tool(token(authorization), call)

    @app.post("/internal/admit")
    def admit(data: Admission, authorization: str | None = Header(default=None)):
        return business.admission(token(authorization), data)

    @app.post("/internal/settle")
    def settle(data: Settlement, authorization: str | None = Header(default=None)):
        return business.settle(token(authorization), data)

    dist = ROOT / "frontend/dist"
    if dist.exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/")
        def index():
            return FileResponse(dist / "index.html")

    return app


app = create_app()
