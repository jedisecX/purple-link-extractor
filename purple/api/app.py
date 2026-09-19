from __future__ import annotations

import asyncio
import csv
import io
import json
import threading
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from purple.config import load_config
from purple.database import get_db
from purple.importer import Importer
from purple.services import library as lib

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
INBOX = Path(__file__).resolve().parents[2] / "inbox"
INBOX.mkdir(exist_ok=True)

_cfg = load_config()
DB = Path(_cfg.database)
_import_state: dict[str, Any] = {
    "running": False,
    "file": None,
    "discovered": 0,
    "inserted": 0,
    "duplicates": 0,
    "invalid": 0,
    "status": "IDLE",
    "error": None,
}
_lock = threading.Lock()


class QueueIn(BaseModel):
    link_ids: list[int]
    priority: str = "NORMAL"


class SearchSave(BaseModel):
    name: str
    query: str = ""
    filters: dict = {}


class ExportIn(BaseModel):
    mode: str = "all"
    fmt: str = "txt"
    link_ids: list[int] = []
    domain: str = ""
    source: str = ""
    include_source: bool = True
    include_domain: bool = True
    include_timestamps: bool = False
    include_normalized: bool = True
    include_original: bool = False


def create_app(db_path: str | Path | None = None) -> FastAPI:
    global DB
    if db_path:
        DB = Path(db_path)
    app = FastAPI(title="Purple Link Extractor Control Center")

    @app.get("/api/stats")
    def api_stats():
        return lib.stats(DB)

    @app.get("/api/urls")
    def api_urls(
        q: str = "",
        domain: str = "",
        registered_domain: str = "",
        scheme: str = "",
        extension: str = "",
        source: str = "",
        status: str = "",
        date_from: str = "",
        date_to: str = "",
        path_contains: str = "",
        limit: int = 50,
        offset: int = 0,
        after: int | None = None,
        include_total: bool = True,
    ):
        return lib.list_urls(
            DB,
            q=q,
            domain=domain,
            registered_domain=registered_domain,
            scheme=scheme,
            extension=extension,
            source=source,
            status=status,
            date_from=date_from,
            date_to=date_to,
            path_contains=path_contains,
            limit=limit,
            offset=offset,
            after=after,
            include_total=include_total,
        )

    @app.get("/api/urls/{link_id}")
    def api_url(link_id: int):
        row = lib.url_detail(DB, link_id)
        if not row:
            raise HTTPException(404, "URL not found")
        return row

    @app.get("/api/domains")
    def api_domains(q: str = "", tld: str = "", limit: int = 50, offset: int = 0):
        return lib.list_domains(DB, q=q, tld=tld, limit=limit, offset=offset)

    @app.get("/api/sources")
    def api_sources(limit: int = 50, offset: int = 0):
        return lib.list_sources(DB, limit=limit, offset=offset)

    @app.get("/api/sources/{source_id}")
    def api_source(source_id: int, limit: int = 50, offset: int = 0):
        row = lib.source_detail(DB, source_id, limit=limit, offset=offset)
        if not row:
            raise HTTPException(404, "Source not found")
        return row

    @app.get("/api/activity")
    def api_activity(limit: int = 40):
        return {"items": lib.recent_activity(DB, limit=limit)}

    @app.get("/api/queue")
    def api_queue(limit: int = 50, offset: int = 0):
        return lib.queue_list(DB, limit=limit, offset=offset)

    @app.post("/api/queue")
    def api_queue_add(payload: QueueIn = Body(...)):
        n = lib.queue_add(DB, payload.link_ids, payload.priority)
        return {"added": n}

    @app.delete("/api/queue/{qid}")
    def api_queue_del(qid: int):
        lib.queue_remove(DB, [qid])
        return {"ok": True}

    @app.post("/api/queue/clear")
    def api_queue_clear():
        lib.queue_clear(DB)
        return {"ok": True}

    @app.get("/api/saved-searches")
    def api_saved():
        return {"items": lib.list_saved_searches(DB)}

    @app.post("/api/saved-searches")
    def api_save(payload: SearchSave = Body(...)):
        sid = lib.save_search(DB, payload.name, payload.query, payload.filters)
        return {"id": sid}

    @app.post("/api/export")
    def api_export(payload: ExportIn = Body(...)):
        rows = _collect_export(payload)
        if payload.fmt == "json":
            data = json.dumps(rows, indent=2).encode()
            media = "application/json"
            name = "purple-export.json"
        elif payload.fmt == "csv":
            buf = io.StringIO()
            fields = list(rows[0].keys()) if rows else ["url"]
            w = csv.DictWriter(buf, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
            data = buf.getvalue().encode()
            media = "text/csv"
            name = "purple-export.csv"
        else:
            data = ("\n".join(r.get("url") or r.get("normalized_url") or "" for r in rows) + "\n").encode()
            media = "text/plain"
            name = "purple-export.txt"
        with get_db(DB) as conn:
            lib.log_activity(conn, "EXPORT CREATED", f"{len(rows)} {payload.fmt}")
            conn.commit()
        return StreamingResponse(
            io.BytesIO(data),
            media_type=media,
            headers={"Content-Disposition": f'attachment; filename="{name}"'},
        )

    def _collect_export(body: ExportIn) -> list[dict]:
        with get_db(DB) as conn:
            if body.mode == "selected" and body.link_ids:
                qmarks = ",".join("?" * len(body.link_ids))
                rows = conn.execute(
                    f"SELECT * FROM links WHERE id IN ({qmarks})", body.link_ids
                ).fetchall()
            elif body.mode == "domain" and body.domain:
                rows = conn.execute(
                    "SELECT * FROM links WHERE hostname=? OR registered_domain=?",
                    (body.domain, body.domain),
                ).fetchall()
            elif body.mode == "source" and body.source:
                rows = conn.execute(
                    "SELECT * FROM links WHERE source_file=?", (body.source,)
                ).fetchall()
            elif body.mode == "queue":
                rows = conn.execute(
                    "SELECT l.* FROM harvest_queue q JOIN links l ON l.id=q.link_id"
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM links ORDER BY id").fetchall()
        out = []
        for r in rows:
            item = {}
            if body.include_normalized:
                item["url"] = r["normalized_url"]
                item["normalized_url"] = r["normalized_url"]
            if body.include_original:
                item["original_url"] = r["original_url"]
            if body.include_domain:
                item["domain"] = r["hostname"]
                item["registered_domain"] = r["registered_domain"]
            if body.include_source:
                item["source"] = r["source_file"]
            if body.include_timestamps:
                item["first_seen"] = r["first_seen"]
                item["last_seen"] = r["last_seen"]
            if not item:
                item["url"] = r["normalized_url"]
            out.append(item)
        return out

    @app.post("/api/import")
    async def api_import(files: list[UploadFile] = File(...)):
        with _lock:
            if _import_state["running"]:
                raise HTTPException(409, "Import already running")
            _import_state.update(running=True, status="PROCESSING", error=None, discovered=0, inserted=0, duplicates=0)
        saved: list[Path] = []
        for f in files:
            name = Path(f.filename or "upload.txt").name
            if Path(name).suffix.lower() not in {".txt", ".csv"}:
                continue
            dest = INBOX / name
            dest.write_bytes(await f.read())
            saved.append(dest)
        if not saved:
            with _lock:
                _import_state.update(running=False, status="IDLE")
            raise HTTPException(400, "No txt/csv files")

        def _run():
            def cb(payload):
                with _lock:
                    _import_state.update(payload)

            try:
                imp = Importer(DB)
                imp.progress_cb = cb
                for p in saved:
                    with _lock:
                        _import_state["file"] = p.name
                    stats = imp.import_path(p)
                    with get_db(DB) as conn:
                        lib.log_activity(conn, "SOURCE IMPORTED", f"{p.name} +{stats.unique_urls}")
                        conn.commit()
                with _lock:
                    _import_state.update(running=False, status="COMPLETE")
            except Exception as exc:
                with _lock:
                    _import_state.update(running=False, status="FAILED", error=str(exc))

        threading.Thread(target=_run, daemon=True).start()
        return {"started": True, "files": [p.name for p in saved]}

    @app.get("/api/import/status")
    def api_import_status():
        with _lock:
            return dict(_import_state)

    @app.get("/api/import/stream")
    async def api_import_stream():
        async def gen():
            while True:
                with _lock:
                    payload = dict(_import_state)
                yield f"data: {json.dumps(payload)}\n\n"
                if not payload.get("running") and payload.get("status") in {"COMPLETE", "FAILED", "IDLE"}:
                    break
                await asyncio.sleep(0.4)

        return StreamingResponse(gen(), media_type="text/event-stream")

    if FRONTEND.is_dir():
        @app.get("/")
        def index():
            return FileResponse(FRONTEND / "index.html")

        app.mount("/static", StaticFiles(directory=str(FRONTEND)), name="static")

    return app


app = create_app()
