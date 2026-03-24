"""FastAPI application entry point."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.jobs import router as jobs_router
from app.api.providers import router as providers_router


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    app = FastAPI(
        title="ALTO LLM Corrector",
        description="Post-OCR text correction of ALTO XML files using LLM providers.",
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS
    cors_origins_raw = os.environ.get("CORS_ORIGINS", "*")
    if cors_origins_raw == "*":
        origins = ["*"]
    else:
        origins = [o.strip() for o in cors_origins_raw.split(",") if o.strip()]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API routers
    app.include_router(providers_router, prefix="/api/providers", tags=["providers"])
    app.include_router(jobs_router, prefix="/api/jobs", tags=["jobs"])

    # Static frontend (HF Spaces single-container mode)
    static_dir = Path(__file__).parent.parent / "static"
    if static_dir.exists():
        app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa_fallback(full_path: str):
            index = static_dir / "index.html"
            if index.exists():
                return FileResponse(str(index))
            raise HTTPException(status_code=404, detail="Not found")

    return app


app = create_app()
