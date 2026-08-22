"""
Database Migration: Create Appointment Service Tables

This migration creates tables for the Appointment Service that runs on port 8001.
These tables store:
1. Provider information (providers discovered via OSM)
2. Available appointment slots
3. Booked appointments

Table: appointment_providers
- Stores provider records from OSM discovery
- Uses OSM provider_id (e.g. osm:way:594121613)
- Tracks specialty, destination, active status

Table: provider_slots
- Stores available appointment slots
- Pre-populated with deterministic schedule
- Status: AVAILABLE, HELD, BOOKED, CANCELLED
- Slots are database-backed (not generated on-the-fly)

Table: appointments
- Stores booked appointments
- Links MRN + provider + slot
- Tracks appointment status

Run this migration:
    python -m post_care.database.migrations.migration_004_create_appointment_service_tables
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
                address VARCHAR(500),
                latitude DOUBLE PRECISION,
                longitude DOUBLE PRECISION,
                active BOOLEAN DEFAULT true,
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
                FOREIGN KEY (provider_id) REFERENCES appointment_providers(provider_id)
                    ON DELETE CASCADE
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
                FOREIGN KEY (provider_id) REFERENCES appointment_providers(provider_id)
                    ON DELETE CASCADE,
                FOREIGN KEY (slot_id) REFERENCES provider_slots(slot_id)
                    ON DELETE CASCADE
            );
        """)

        # Create indexes for common queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_appointment_providers_provider_id
            ON appointment_providers(provider_id);
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
        print("✅ Migration 004_create_appointment_service_tables: SUCCESS")
        print("   Tables created:")
        print("   - appointment_providers")
        print("   - provider_slots")
        print("   - appointments")

    except Exception as e:
        conn.rollback()
        print(f"❌ Migration 004_create_appointment_service_tables: FAILED")
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
        print("✅ Migration 004_create_appointment_service_tables reverted: SUCCESS")

    except Exception as e:
        conn.rollback()
        print(f"❌ Migration 004_create_appointment_service_tables revert: FAILED")
        print(f"   Error: {str(e)}")
        raise

    finally:
        close_db_connection(conn)


if __name__ == "__main__":
    up()
