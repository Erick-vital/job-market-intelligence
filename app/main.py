from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routes.api import router as api_router
from app.routes.web import router as web_router

app = FastAPI(
    title="Job Market Intelligence",
    version="0.1.0",
    description="Local-first job matching and market intelligence app.",
)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(web_router)
app.include_router(api_router)
