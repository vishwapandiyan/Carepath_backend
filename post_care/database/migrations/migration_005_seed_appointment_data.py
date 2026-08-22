"""
Database Migration: Seed Appointment Data

Seeds test appointment providers and slots for development/demo environment.
Creates provider records matching live OSM discovery results and deterministic
appointment slots for testing.

Uses existing carepath_db PostgreSQL instance.

Run this migration:
    python -m post_care.database.migrations.migration_005_seed_appointment_data
"""

from datetime import datetime, timedelta
from post_care.database.connection import get_db_connection, close_db_connection


def up():
    """Execute the migration."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Provider data matching live OSM discovery
        providers = [
            {
                "provider_id": "osm:way:594121613",
                "provider_name": "Dr. R Bhaskaran",
                "destination": "PCP",
                "specialty": None,
            },
            {
                "provider_id": "osm:node:5665907772",
                "provider_name": "T B Kasthuri",
                "destination": "PCP",
                "specialty": None,
            },
            {
                "provider_id": "osm:node:6072445210",
                "provider_name": "Dr T Prasad",
                "destination": "PCP",
                "specialty": None,
            },
        ]

        # Insert providers
        for provider in providers:
            cursor.execute("""
                INSERT INTO appointment_providers
                (provider_id, provider_name, destination, specialty, active)
                VALUES (%s, %s, %s, %s, TRUE)
                ON CONFLICT (provider_id) DO NOTHING
            """, (
                provider["provider_id"],
                provider["provider_name"],
                provider["destination"],
                provider["specialty"],
            ))

        # Generate slots for each provider
        # Start from tomorrow at 09:00 AM, generate 10 slots per provider
        base_date = datetime.now() + timedelta(days=1)
        base_date = base_date.replace(hour=9, minute=0, second=0, microsecond=0)

        slot_counter = 1
        for provider in providers:
            for slot_offset in range(10):
                start_time = base_date + timedelta(minutes=30 * slot_offset)
                end_time = start_time + timedelta(minutes=30)
                slot_id = f"slot_{provider['provider_id'].replace(':', '_').replace('.', '_')}_{slot_counter:04d}"

                cursor.execute("""
                    INSERT INTO provider_slots
                    (slot_id, provider_id, start_time, end_time, status)
                    VALUES (%s, %s, %s, %s, 'AVAILABLE')
                    ON CONFLICT (slot_id) DO NOTHING
                """, (slot_id, provider["provider_id"], start_time, end_time))

                slot_counter += 1

        conn.commit()
        print("✅ Migration 005_seed_appointment_data: SUCCESS")
        print(f"   Providers seeded: {len(providers)}")
        print(f"   Total slots created: {len(providers) * 10}")
        print(f"   Slot date range: {base_date.date()} at 09:00 - 14:30")

    except Exception as e:
        conn.rollback()
        print(f"❌ Migration 005_seed_appointment_data: FAILED")
        print(f"   Error: {str(e)}")
        raise

    finally:
        close_db_connection(conn)


def down():
    """Revert the migration."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Delete all seeded data
        cursor.execute("DELETE FROM appointments;")
        cursor.execute("DELETE FROM provider_slots;")
        cursor.execute("DELETE FROM appointment_providers;")

        conn.commit()
        print("✅ Migration 005_seed_appointment_data reverted: SUCCESS")

    except Exception as e:
        conn.rollback()
        print(f"❌ Migration 005_seed_appointment_data revert: FAILED")
        print(f"   Error: {str(e)}")
        raise

    finally:
        close_db_connection(conn)


if __name__ == "__main__":
    up()
