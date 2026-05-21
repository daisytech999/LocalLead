from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from sqlalchemy import inspect, text

from .config import get_settings
from .database import Base, engine
from .routers import auth, billing, leads

settings = get_settings()

Base.metadata.create_all(bind=engine)


def _ensure_columns() -> None:
    """Add columns introduced after initial release to existing SQLite DBs."""
    if not settings.database_url.startswith("sqlite"):
        return
    inspector = inspect(engine)
    if "leads" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("leads")}
    for col, ddl in [("contact_email", "VARCHAR(255)"), ("contact_socials", "TEXT")]:
        if col not in existing:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE leads ADD COLUMN {col} {ddl}"))


_ensure_columns()

app = FastAPI(title="LocalLead API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin] if settings.frontend_origin != "*" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(leads.router)
app.include_router(billing.router)

# Serve the marketing frontend (index.html lives at the repo root).
FRONTEND = Path(__file__).resolve().parents[2] / "index.html"


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "google_places_configured": bool(settings.google_places_api_key),
        "stripe_configured": bool(settings.stripe_secret_key),
    }


@app.get("/", include_in_schema=False)
def index():
    if FRONTEND.exists():
        return FileResponse(FRONTEND)
    return JSONResponse({"message": "LocalLead API. Frontend not found.", "docs": "/docs"})
