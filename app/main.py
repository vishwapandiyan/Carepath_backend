import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.v1.api import api_router
from app.care_manager import care_manager_router
from app.config import settings
from app.db.base import Base, engine
from app.patient import patient_router

logging.basicConfig(
    level=logging.DEBUG if settings.app_env == "development" else logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ───────────────────────────────────────────────────────────────
    logger.info("Starting AI Medical System API  env=%s", settings.app_env)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            
        # Safe column additions and sequence setup for pre-existing PostgreSQL tables
        col_statements = [
            "CREATE SEQUENCE IF NOT EXISTS users_id_seq;",
            "ALTER TABLE users ALTER COLUMN id TYPE INTEGER USING id::integer;",
            "ALTER TABLE users ALTER COLUMN id SET DEFAULT nextval('users_id_seq');",
            "ALTER TABLE users ALTER COLUMN email DROP NOT NULL;",
            "ALTER TABLE users ALTER COLUMN first_name DROP NOT NULL;",
            "ALTER TABLE users ALTER COLUMN last_name DROP NOT NULL;",
            "ALTER TABLE users ALTER COLUMN hashed_password DROP NOT NULL;",
            "ALTER TABLE users ALTER COLUMN is_active DROP NOT NULL;",
            "ALTER TABLE users ALTER COLUMN is_active SET DEFAULT TRUE;",
            "ALTER TABLE users ALTER COLUMN is_superuser DROP NOT NULL;",
            "ALTER TABLE users ALTER COLUMN full_name DROP NOT NULL;",
            "ALTER TABLE users ALTER COLUMN created_at DROP NOT NULL;",
            "ALTER TABLE users ALTER COLUMN created_at SET DEFAULT NOW();",
            "ALTER TABLE users ALTER COLUMN updated_at DROP NOT NULL;",
            "ALTER TABLE users ALTER COLUMN updated_at SET DEFAULT NOW();",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255);",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(50);",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS patient_id VARCHAR(50);",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();",
            "ALTER TABLE patients ADD COLUMN IF NOT EXISTS mrn VARCHAR(50);",
            "ALTER TABLE patients ADD COLUMN IF NOT EXISTS gender VARCHAR(20);",
            "ALTER TABLE patients ADD COLUMN IF NOT EXISTS contact_number VARCHAR(50);",
            "ALTER TABLE patients ADD COLUMN IF NOT EXISTS email VARCHAR(255);",
            "ALTER TABLE patients ADD COLUMN IF NOT EXISTS address VARCHAR(500);",
            "ALTER TABLE patients ADD COLUMN IF NOT EXISTS admission_date VARCHAR(25);",
            "ALTER TABLE patients ADD COLUMN IF NOT EXISTS discharge_date VARCHAR(25);",
            "ALTER TABLE patients ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;",
            "ALTER TABLE patients ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP WITH TIME ZONE;",
            "ALTER TABLE patients ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE;",
            "ALTER TABLE patients ALTER COLUMN created_at DROP NOT NULL;",
            "ALTER TABLE patients ALTER COLUMN created_at SET DEFAULT NOW();",
            "ALTER TABLE patients ALTER COLUMN updated_at DROP NOT NULL;",
            "ALTER TABLE patients ALTER COLUMN updated_at SET DEFAULT NOW();",
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_patients_mrn ON patients (mrn) WHERE mrn IS NOT NULL;",
        ]





        for stmt in col_statements:
            try:
                async with engine.begin() as conn:
                    await conn.execute(text(stmt))
            except Exception as col_exc:
                logger.debug("Column migration skipped (%s)", col_exc)

        logger.info("Database tables and columns verified / created.")

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
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth and EHR endpoints mounted under /api/v1
app.include_router(api_router, prefix="/api/v1")

# Patient endpoints mounted under /api/v1
app.include_router(patient_router, prefix="/api/v1")

# Care Manager endpoints mounted under /api/v1/care-manager
app.include_router(care_manager_router, prefix="/api/v1/care-manager")


@app.get("/health", tags=["health"], summary="Health check")
async def health_check():
    return {
        "status": "ok",
        "version": settings.app_version,
        "env": settings.app_env,
    }
