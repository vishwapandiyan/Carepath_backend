import logging
import warnings
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

# Suppress future warnings early
warnings.filterwarnings('ignore', category=FutureWarning, module='google.generativeai')

from app.api.v1.api import api_router
from app.care_manager import care_manager_router
from app.config import settings
from app.db.base import Base, engine
from app.patient import patient_router

# Import all models to ensure they are registered with SQLAlchemy
from app.models import User, PatientEHR, MLPrediction

# Configure logging
logging.basicConfig(
    level=logging.INFO,  # Always use INFO to reduce noise
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# Silence SQLAlchemy engine logs completely
logging.getLogger("sqlalchemy.engine").setLevel(logging.ERROR)
logging.getLogger("sqlalchemy.pool").setLevel(logging.ERROR)
logging.getLogger("sqlalchemy.dialects").setLevel(logging.ERROR)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ───────────────────────────────────────────────────────────────
    logger.info("Starting AI Medical System API  env=%s", settings.app_env)
    
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            
        logger.info("Database tables verified / created.")

    except Exception as exc:
        logger.warning(
            "Database unavailable at startup (%s). "
            "Safety /evaluate and /assessment endpoints require PostgreSQL. "
            "Intake endpoints (in-memory) are fully operational.",
            exc,
        )
    yield
    # ── Shutdown ──────────────────────────────────────────────────────────────
    await engine.dispose()
    logger.info("Database pool closed.")


app = FastAPI(
    title=settings.app_title,
    version=settings.app_version,
    description=(
        "Dual-Domain AI Medical System API.\n"
        "- Patient Domain: /api/v1/patient (Intake, Safety, Triage Chatbot)\n"
        "- Care Manager Domain: /api/v1/care-manager (Dashboard, Patient CRUD, Readmission, Post-Discharge, Analytics)"
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://d2wdvr99379bz0.cloudfront.net",  # Frontend CloudFront
        "http://localhost:5173",  # Local development
        "http://localhost:3000",
        "*"  # Allow all origins as fallback
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Auth and EHR endpoints mounted under /api/v1
app.include_router(api_router, prefix="/api/v1")

# Patient endpoints mounted under /api/v1
app.include_router(patient_router, prefix="/api/v1")

# Care Manager endpoints mounted under /api/v1/care-manager
app.include_router(care_manager_router, prefix="/api/v1/care-manager")

# Alternate Care Agent endpoints mounted under /api/v1/care
from app.services.alternate_care.api import routes as alternate_care_routes
app.include_router(
    alternate_care_routes.app,
    prefix="/api/v1/care",
    tags=["Alternate Care"]
)


@app.get("/health", tags=["health"], summary="Health check")
async def health_check():
    return {
        "status": "ok",
        "version": settings.app_version,
        "env": settings.app_env,
    }
