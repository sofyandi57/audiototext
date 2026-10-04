"""FastAPI application. Run with:

    uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .api import documents, jobs, meetings, system
from .config import Settings, get_settings
from .services import Services, build_services
from .worker import Worker

log = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, services: Services | None = None,
               start_worker: bool | None = None) -> FastAPI:
    settings = settings or (services.settings if services else get_settings())
    services = services or build_services(settings)
    run_worker = settings.run_worker_in_process if start_worker is None else start_worker

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        stop = threading.Event()
        if run_worker:
            worker = Worker(services)
            t = threading.Thread(target=worker.run_forever, args=(stop,), daemon=True, name="worker")
            t.start()
            app.state.worker_thread = t
        yield
        stop.set()

    app = FastAPI(title="Meeting Intelligence Indonesia", version="0.1.0", lifespan=lifespan,
                  docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.state.services = services

    max_body = max(settings.max_pdf_mb, settings.max_media_mb) * 1024 * 1024 + 1024 * 1024

    @app.middleware("http")
    async def limit_body(request: Request, call_next):
        # Reject oversized uploads before multipart parsing spools them to disk.
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > max_body:
            return JSONResponse({"detail": "File terlalu besar."}, status_code=413)
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return JSONResponse({"detail": "Input tidak valid.", "errors": [
            {"field": ".".join(str(p) for p in e.get("loc", [])[1:]), "message": e.get("msg")}
            for e in exc.errors()]}, status_code=422)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        log.exception("unhandled error on %s", request.url.path)
        return JSONResponse({"detail": "Terjadi kesalahan internal. Coba lagi."}, status_code=500)

    app.include_router(system.router)
    app.include_router(documents.router)
    app.include_router(meetings.router)
    app.include_router(jobs.router)

    _mount_frontend(app, settings.frontend_dir)
    return app


def _mount_frontend(app: FastAPI, root: Path) -> None:
    """Serve the static Next.js export (same origin as the API)."""
    if not (root / "index.html").is_file():
        @app.get("/", include_in_schema=False)
        def no_frontend():
            return JSONResponse({"detail": "Frontend belum dibangun. Jalankan 'npm run build' di frontend/."
                                 " API tersedia di /api/docs."})
        return

    static = StaticFiles(directory=root, html=True)

    @app.exception_handler(StarletteHTTPException)
    async def spa_404(request: Request, exc: StarletteHTTPException):
        if exc.status_code == 404 and not request.url.path.startswith("/api/"):
            page = root / "404.html"
            if page.exists():
                return FileResponse(page, status_code=404)
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

    app.mount("/", static, name="frontend")


_app: FastAPI | None = None


def __getattr__(name: str):
    """Lazily build the default app so importing this module (e.g. in tests)
    has no side effects. ``uvicorn app.main:app`` still works."""
    global _app
    if name == "app":
        if _app is None:
            logging.basicConfig(level=logging.INFO,
                                format="%(asctime)s %(levelname)s %(name)s: %(message)s")
            _app = create_app()
        return _app
    raise AttributeError(name)
