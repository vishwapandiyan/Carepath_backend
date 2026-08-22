"""
Database Migration: Add conversation_state to Appointment Sessions Table

This migration adds a conversation_state JSONB column to the existing
appointment_sessions table so the Appointment Agent's LLM message history
(the tool-calling loop's `messages` list) can be persisted across HTTP
requests and restored on a follow-up /chat turn.

No existing columns are modified or removed. No existing Post-care tables
are touched.

SQL Schema (added column):
    ALTER TABLE appointment_sessions
    ADD COLUMN IF NOT EXISTS conversation_state JSONB;

Run this migration:
    python -m post_care.database.migrations.migration_003_add_conversation_state_to_appointment_sessions
"""

from post_care.database.connection import get_db_connection, close_db_connection


def up():
    """Execute the migration."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        cursor.execute("""
            ALTER TABLE appointment_sessions
            ADD COLUMN IF NOT EXISTS conversation_state JSONB;
        """)

        conn.commit()
        print("✅ Migration 003_add_conversation_state_to_appointment_sessions: SUCCESS")
        print("   Column conversation_state added to appointment_sessions")

    except Exception as e:
        conn.rollback()
        print(f"❌ Migration 003_add_conversation_state_to_appointment_sessions: FAILED")
        print(f"   Error: {str(e)}")
        raise

    finally:
        close_db_connection(conn)


def down():
    """Revert the migration."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        cursor.execute("""
            ALTER TABLE appointment_sessions
            DROP COLUMN IF EXISTS conversation_state;
        """)

        conn.commit()
        print("✅ Migration 003_add_conversation_state_to_appointment_sessions reverted: SUCCESS")

    except Exception as e:
        conn.rollback()
        print(f"❌ Migration 003_add_conversation_state_to_appointment_sessions revert: FAILED")
        print(f"   Error: {str(e)}")
        raise

    finally:
        close_db_connection(conn)


if __name__ == "__main__":
    up()
