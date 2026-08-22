"""
Database Migration: Create Follow-Up Check-Ins Table

This migration creates the follow_up_checkins table for storing check-in records
created and managed by the Follow-Up Agent.

Table: follow_up_checkins
- Stores communication check-ins with patients
- Associates check-ins with tasks via foreign key
- Tracks check-in status and patient responses
- Maintains audit trail with created_at/updated_at timestamps

SQL Schema:
    CREATE TABLE follow_up_checkins (
        id BIGSERIAL PRIMARY KEY,
        checkin_id VARCHAR(255) UNIQUE NOT NULL,
        task_id VARCHAR(255) NOT NULL,
        checkin_type VARCHAR(100) NOT NULL,
        scheduled_at TIMESTAMP,
        channel VARCHAR(50),
        status VARCHAR(50) NOT NULL,
        message TEXT,
        response TEXT,
        response_received_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (task_id) REFERENCES care_plan_tasks(task_id) ON DELETE CASCADE
    );

Run this migration:
    python -m post_care.database.migrations.run 001_create_follow_up_checkins
"""

from post_care.database.connection import get_db_connection, close_db_connection


def up():
    """Execute the migration."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # Create follow_up_checkins table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS follow_up_checkins (
                id BIGSERIAL PRIMARY KEY,
                checkin_id VARCHAR(255) UNIQUE NOT NULL,
                task_id VARCHAR(255) NOT NULL,
                checkin_type VARCHAR(100) NOT NULL,
                scheduled_at TIMESTAMP,
                channel VARCHAR(50),
                status VARCHAR(50) NOT NULL 
                    CHECK (status IN ('SCHEDULED', 'SENT', 'RESPONSE_RECEIVED', 'COMPLETED', 'MISSED', 'CANCELLED')),
                message TEXT,
                response TEXT,
                response_received_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES care_plan_tasks(task_id) ON DELETE CASCADE
            );
        """)
        
        # Create indexes for common queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_follow_up_checkins_task_id
            ON follow_up_checkins(task_id);
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_follow_up_checkins_status
            ON follow_up_checkins(status);
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_follow_up_checkins_created_at
            ON follow_up_checkins(created_at);
        """)
        
        conn.commit()
        print("✅ Migration 001_create_follow_up_checkins: SUCCESS")
        print("   Table follow_up_checkins created successfully")
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Migration 001_create_follow_up_checkins: FAILED")
        print(f"   Error: {str(e)}")
        raise
    
    finally:
        close_db_connection(conn)


def down():
    """Revert the migration."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        cursor.execute("DROP TABLE IF EXISTS follow_up_checkins CASCADE;")
        
        conn.commit()
        print("✅ Migration 001_create_follow_up_checkins reverted: SUCCESS")
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Migration 001_create_follow_up_checkins revert: FAILED")
        print(f"   Error: {str(e)}")
        raise
    
    finally:
        close_db_connection(conn)
