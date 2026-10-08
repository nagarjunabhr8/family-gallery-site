"""FastAPI entry point. Serves the API and, when built, the frontend."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config, db, safety
from .api import folders, groups, media, people, scan
from .scanner.jobs import manager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    data = safety.set_data_dir(config.default_data_dir())
    db.init_db(data)
    manager.start()
    logging.getLogger(__name__).info("Data folder: %s", data)
    yield
    manager.stop()


app = FastAPI(title="Family Memories", lifespan=lifespan)
app.include_router(folders.router)
app.include_router(scan.router)
app.include_router(media.router)
app.include_router(groups.router)
app.include_router(people.router)


@app.get("/api/health")
def health():
    return {"ok": True, "data_dir": str(safety.data_dir())}


# Built frontend (npm run build). In dev, Vite serves it on :5173 instead.
if (config.FRONTEND_DIST / "index.html").is_file():
    app.mount("/assets", StaticFiles(directory=config.FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(404)
        candidate = (config.FRONTEND_DIST / full_path).resolve()
        if full_path and candidate.is_file() and candidate.is_relative_to(config.FRONTEND_DIST):
            return FileResponse(candidate)
        return FileResponse(config.FRONTEND_DIST / "index.html")
