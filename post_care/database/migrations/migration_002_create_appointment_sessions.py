"""
Database Migration: Create Appointment Sessions Table

This migration creates the appointment_sessions table for persisting
navigation recommendation and appointment workflow state.

Table: appointment_sessions
- Stores the navigation care decision and patient location
- Persists provider discovery results (JSONB)
- Tracks appointment lifecycle (availability, booking, reschedule, cancel)
- Supports both patient-side and post-care-side appointment flows via source column
- Uses MRN as the patient identifier (same as patient_ehr)
- Replaces the in-memory RecommendationStore with durable persistence

SQL Schema:
    CREATE TABLE appointment_sessions (
        id BIGSERIAL PRIMARY KEY,
        session_id VARCHAR(255) UNIQUE NOT NULL,
        mrn VARCHAR(50) NOT NULL,
        destination VARCHAR(50) NOT NULL,
        specialty VARCHAR(100),
        rule_id VARCHAR(100),
        latitude DOUBLE PRECISION,
        longitude DOUBLE PRECISION,
        radius_km DOUBLE PRECISION DEFAULT 15.0,
        provider_candidates JSONB,
        ranked_providers JSONB,
        selected_provider_id VARCHAR(255),
        available_slots JSONB,
        selected_slot_id VARCHAR(255),
        appointment_id VARCHAR(255),
        appointment_status VARCHAR(50),
        workflow_stage VARCHAR(50) NOT NULL DEFAULT 'NAVIGATION_COMPLETE',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        expires_at TIMESTAMP,
        source VARCHAR(50) NOT NULL DEFAULT 'PATIENT',
        care_plan_id VARCHAR(255)
    );

Run this migration:
    python -m post_care.database.migrations.migration_002_create_appointment_sessions
"""

from post_care.database.connection import get_db_connection, close_db_connection


def up():
    """Execute the migration."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Create appointment_sessions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS appointment_sessions (
                id BIGSERIAL PRIMARY KEY,
                session_id VARCHAR(255) UNIQUE NOT NULL,
                mrn VARCHAR(50) NOT NULL,
                destination VARCHAR(50) NOT NULL
                    CHECK (destination IN ('PCP', 'URGENT_CARE', 'SPECIALIST', 'TELEHEALTH', 'DENTISTRY')),
                specialty VARCHAR(100),
                rule_id VARCHAR(100),
                latitude DOUBLE PRECISION,
                longitude DOUBLE PRECISION,
                radius_km DOUBLE PRECISION DEFAULT 15.0,
                provider_candidates JSONB,
                ranked_providers JSONB,
                selected_provider_id VARCHAR(255),
                available_slots JSONB,
                selected_slot_id VARCHAR(255),
                appointment_id VARCHAR(255),
                appointment_status VARCHAR(50)
                    CHECK (appointment_status IS NULL OR appointment_status IN (
                        'BOOKED', 'RESCHEDULED', 'CANCELLED', 'COMPLETED'
                    )),
                workflow_stage VARCHAR(50) NOT NULL DEFAULT 'NAVIGATION_COMPLETE'
                    CHECK (workflow_stage IN (
                        'NAVIGATION_COMPLETE',
                        'PROVIDERS_SEARCHED',
                        'PROVIDER_SELECTED',
                        'AVAILABILITY_CHECKED',
                        'SLOT_SELECTED',
                        'BOOKED',
                        'RESCHEDULED',
                        'CANCELLED'
                    )),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                source VARCHAR(50) NOT NULL DEFAULT 'PATIENT'
                    CHECK (source IN ('PATIENT', 'POST_CARE')),
                care_plan_id VARCHAR(255)
            );
        """)

        # Create indexes for common queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_appointment_sessions_mrn
            ON appointment_sessions(mrn);
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_appointment_sessions_session_id
            ON appointment_sessions(session_id);
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_appointment_sessions_workflow_stage
            ON appointment_sessions(workflow_stage);
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_appointment_sessions_expires_at
            ON appointment_sessions(expires_at);
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_appointment_sessions_source
            ON appointment_sessions(source);
        """)

        conn.commit()
        print("✅ Migration 002_create_appointment_sessions: SUCCESS")
        print("   Table appointment_sessions created successfully")

    except Exception as e:
        conn.rollback()
        print(f"❌ Migration 002_create_appointment_sessions: FAILED")
        print(f"   Error: {str(e)}")
        raise

    finally:
        close_db_connection(conn)


def down():
    """Revert the migration."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        cursor.execute("DROP TABLE IF EXISTS appointment_sessions CASCADE;")

        conn.commit()
        print("✅ Migration 002_create_appointment_sessions reverted: SUCCESS")

    except Exception as e:
        conn.rollback()
        print(f"❌ Migration 002_create_appointment_sessions revert: FAILED")
        print(f"   Error: {str(e)}")
        raise

    finally:
        close_db_connection(conn)


if __name__ == "__main__":
    up()
