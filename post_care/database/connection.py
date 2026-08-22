"""
PostgreSQL Connection Module

Provides reusable PostgreSQL connection management for the post-care system.

Configuration:
- host: localhost
- port: 5432
- database: carepath_db
- user: vishwa (from environment or config)
- password: from environment variable (never hardcoded)

Usage:
    from database.connection import get_db_connection
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM patient_ehr WHERE mrn = %s", (mrn,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
"""

import psycopg2
import os
from typing import Optional


# PostgreSQL connection configuration
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "database": os.getenv("DB_NAME", "carepath_db"),
    "user": os.getenv("DB_USER", "vishwa"),  # Changed default from subitsha to vishwa
    "password": os.getenv("DB_PASSWORD", ""),  # Will fail if not set and required
}


def get_db_connection():
    """
    Create and return a PostgreSQL database connection.
    
    Returns:
        psycopg2 connection object
    
    Raises:
        psycopg2.Error: If connection fails
    
    Note:
        Caller is responsible for closing the connection.
        Use connection in a try-finally block or context manager.
    """
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except psycopg2.OperationalError as e:
        raise psycopg2.OperationalError(
            f"Failed to connect to PostgreSQL database at "
            f"{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}: {e}"
        )
    except Exception as e:
        raise Exception(f"Unexpected error connecting to PostgreSQL: {e}")


def close_db_connection(conn):
    """
    Close a PostgreSQL database connection.
    
    Args:
        conn: psycopg2 connection object
    """
    if conn:
        try:
            conn.close()
        except Exception as e:
            print(f"Warning: Error closing database connection: {e}")
