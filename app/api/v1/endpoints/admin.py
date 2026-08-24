"""
Admin endpoints for system management
"""
from fastapi import APIRouter, HTTPException
from sqlalchemy import text
from app.db.base import get_db
from app.migrations.run_migrations import run_migrations
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/migrate", tags=["admin"])
async def run_database_migrations():
    """
    Run database migrations
    
    Executes all SQL migration files in the migrations directory
    """
    try:
        await run_migrations()
        return {
            "status": "success",
            "message": "Database migrations completed successfully"
        }
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise HTTPException(status_code=500, detail=f"Migration failed: {str(e)}")


@router.get("/db-status", tags=["admin"])
async def check_database_status():
    """Check database connection and basic status"""
    try:
        async for db in get_db():
            result = await db.execute(text("SELECT version()"))
            version = result.scalar()
            
            # Check if tables exist
            result = await db.execute(text("""
                SELECT COUNT(*) 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
            """))
            table_count = result.scalar()
            
            return {
                "status": "connected",
                "database_version": version,
                "table_count": table_count
            }
    except Exception as e:
        logger.error(f"Database check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Database check failed: {str(e)}")
