"""
Database Migration: Create Appointment Scheduling Tables

Creates tables for managing provider schedules and appointment availability:
1. appointment_providers - provider registry with OSM IDs
2. provider_slots - available appointment time slots
3. appointments - booked appointments

Uses existing carepath_db PostgreSQL instance.
Supports OSM provider IDs (e.g. osm:way:594121613).

Run this migration:
    python -m post_care.database.migrations.migration_004_create_appointment_scheduling
"""

from post_care.database.connection import get_db_connection, close_db_connection


def up():
    """Execute the migration."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Create appointment_providers table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS appointment_providers (
                id BIGSERIAL PRIMARY KEY,
                provider_id VARCHAR(255) UNIQUE NOT NULL,
                provider_name VARCHAR(255) NOT NULL,
                destination VARCHAR(50) NOT NULL
                    CHECK (destination IN ('PCP', 'URGENT_CARE', 'SPECIALIST', 'TELEHEALTH', 'DENTISTRY')),
                specialty VARCHAR(100),
                active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Create provider_slots table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS provider_slots (
                id BIGSERIAL PRIMARY KEY,
                slot_id VARCHAR(255) UNIQUE NOT NULL,
                provider_id VARCHAR(255) NOT NULL,
                start_time TIMESTAMP NOT NULL,
                end_time TIMESTAMP NOT NULL,
                status VARCHAR(50) NOT NULL DEFAULT 'AVAILABLE'
                    CHECK (status IN ('AVAILABLE', 'HELD', 'BOOKED', 'CANCELLED')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (provider_id) REFERENCES appointment_providers(provider_id) ON DELETE CASCADE
            );
        """)

        # Create appointments table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS appointments (
                id BIGSERIAL PRIMARY KEY,
                appointment_id VARCHAR(255) UNIQUE NOT NULL,
                mrn VARCHAR(50) NOT NULL,
                provider_id VARCHAR(255) NOT NULL,
                slot_id VARCHAR(255) NOT NULL,
                start_time TIMESTAMP NOT NULL,
                end_time TIMESTAMP NOT NULL,
                status VARCHAR(50) NOT NULL DEFAULT 'BOOKED'
                    CHECK (status IN ('BOOKED', 'RESCHEDULED', 'CANCELLED', 'COMPLETED')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (provider_id) REFERENCES appointment_providers(provider_id) ON DELETE RESTRICT,
                FOREIGN KEY (slot_id) REFERENCES provider_slots(slot_id) ON DELETE RESTRICT
            );
        """)

        # Create indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_appointment_providers_provider_id
            ON appointment_providers(provider_id);
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_appointment_providers_destination
            ON appointment_providers(destination);
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_provider_slots_provider_id
            ON provider_slots(provider_id);
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_provider_slots_status
            ON provider_slots(status);
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_provider_slots_start_time
            ON provider_slots(start_time);
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_appointments_mrn
            ON appointments(mrn);
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_appointments_provider_id
            ON appointments(provider_id);
        """)

        conn.commit()
        print("✅ Migration 004_create_appointment_scheduling: SUCCESS")
        print("   Tables created:")
        print("   - appointment_providers")
        print("   - provider_slots")
        print("   - appointments")

    except Exception as e:
        conn.rollback()
        print(f"❌ Migration 004_create_appointment_scheduling: FAILED")
        print(f"   Error: {str(e)}")
        raise

    finally:
        close_db_connection(conn)


def down():
    """Revert the migration."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        cursor.execute("DROP TABLE IF EXISTS appointments CASCADE;")
        cursor.execute("DROP TABLE IF EXISTS provider_slots CASCADE;")
        cursor.execute("DROP TABLE IF EXISTS appointment_providers CASCADE;")

        conn.commit()
        print("✅ Migration 004_create_appointment_scheduling reverted: SUCCESS")

    except Exception as e:
        conn.rollback()
        print(f"❌ Migration 004_create_appointment_scheduling revert: FAILED")
        print(f"   Error: {str(e)}")
        raise

    finally:
        close_db_connection(conn)


if __name__ == "__main__":
    up()
