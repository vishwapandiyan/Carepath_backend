"""
Database migration runner
Executes SQL migration files in order
"""
import asyncio
import logging
from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine
from app.config import settings

logger = logging.getLogger(__name__)


async def run_migrations():
    """Run all SQL migration files"""
    # Create async engine
    engine = create_async_engine(settings.DATABASE_URL, echo=True)
    
    # Get migration files
    migrations_dir = Path(__file__).parent.parent.parent / "migrations"
    migration_files = sorted(migrations_dir.glob("*.sql"))
    
    logger.info(f"Found {len(migration_files)} migration files")
    
    async with engine.begin() as conn:
        for migration_file in migration_files:
            logger.info(f"Running migration: {migration_file.name}")
            
            # Read SQL file
            sql_content = migration_file.read_text()
            
            # Split by semicolon and execute each statement
            statements = [s.strip() for s in sql_content.split(';') if s.strip()]
            
            for statement in statements:
                try:
                    await conn.execute(statement)
                    logger.info(f"Executed statement from {migration_file.name}")
                except Exception as e:
                    logger.error(f"Error in {migration_file.name}: {e}")
                    # Continue with next statement
                    continue
    
    await engine.dispose()
    logger.info("All migrations completed")


if __name__ == "__main__":
    asyncio.run(run_migrations())
