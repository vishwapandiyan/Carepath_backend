"""
Apply PostgreSQL Schema to ehr_db
Creates database ehr_db if needed, executes database/schema.sql,
and initializes SQLAlchemy tables.
"""

import asyncio
import asyncpg
from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine
from app.db.base import Base
import app.models  # load all models

DB_USER = "postgres"
DB_PASS = "admin123"
DB_HOST = "localhost"
DB_PORT = 5432
TARGET_DB = "ehr_db"
SCHEMA_FILE = Path("database/schema.sql")

async def run_setup():
    print(f"1. Checking connection to PostgreSQL server on {DB_HOST}:{DB_PORT}...")
    try:
        sys_conn = await asyncpg.connect(user=DB_USER, password=DB_PASS, host=DB_HOST, port=DB_PORT, database="postgres")
        
        # Check if target database exists
        rows = await sys_conn.fetch("SELECT datname FROM pg_database WHERE datname = $1", TARGET_DB)
        if not rows:
            print(f"2. Database '{TARGET_DB}' does not exist. Creating '{TARGET_DB}'...")
            await sys_conn.execute(f'CREATE DATABASE "{TARGET_DB}"')
            print(f"✓ Database '{TARGET_DB}' created successfully.")
        else:
            print(f"2. Database '{TARGET_DB}' already exists.")
        
        await sys_conn.close()
    except Exception as e:
        print(f"✗ Server connection error: {e}")
        return

    print(f"\n3. Connecting directly to '{TARGET_DB}'...")
    db_conn = await asyncpg.connect(user=DB_USER, password=DB_PASS, host=DB_HOST, port=DB_PORT, database=TARGET_DB)

    if SCHEMA_FILE.exists():
        print(f"4. Reading SQL schema from {SCHEMA_FILE}...")
        sql_content = SCHEMA_FILE.read_text(encoding="utf-8")
        
        print("5. Executing SQL schema script...")
        try:
            await db_conn.execute(sql_content)
            print("[SUCCESS] Executed SQL schema script.")
        except Exception as e:
            print(f"Schema execution note: {e}")
    else:
        print(f"⚠️ Schema file {SCHEMA_FILE} not found!")

    await db_conn.close()

    # Create all ORM tables using SQLAlchemy metadata
    print("\n6. Synchronizing SQLAlchemy models with 'ehr_db'...")
    async_url = f"postgresql+asyncpg://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{TARGET_DB}"
    engine = create_async_engine(async_url, echo=False)
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    await engine.dispose()
    print("[SUCCESS] SQLAlchemy models synchronized successfully!")
    print(f"\nSUCCESS: All tables created and initialized in database '{TARGET_DB}'!")

if __name__ == "__main__":
    asyncio.run(run_setup())
