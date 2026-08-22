"""
Appointment Availability Repository

Handles querying available appointment slots for the appointment service.
Uses the same psycopg2 + raw SQL pattern as other repositories.

Architecture:
    Appointment Service (localhost:8001)
        ↓
    AppointmentAvailabilityRepository (this module)
        ↓
    PostgreSQL (carepath_db → provider_slots table)
"""

import logging
from datetime import datetime, timedelta
from secrets import token_urlsafe
from typing import Any, Dict, List, Optional

from post_care.database.connection import get_db_connection, close_db_connection

logger = logging.getLogger(__name__)


class AppointmentAvailabilityRepository:
    """Repository for querying appointment availability."""

    @staticmethod
    def get_available_slots(
        provider_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Get available appointment slots for a provider.

        Args:
            provider_id: The provider's OSM ID (e.g. osm:way:594121613)
            start_date: Start date for slot query (default: today)
            end_date: End date for slot query (default: 7 days from start)
            limit: Maximum slots to return (default 100)

        Returns:
            List of slots with: slot_id, provider_id, start_time, end_time, status
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor()

            if start_date is None:
                start_date = datetime.now()
            if end_date is None:
                end_date = start_date + timedelta(days=7)

            cursor.execute("""
                SELECT 
                    slot_id,
                    provider_id,
                    start_time,
                    end_time,
                    status
                FROM provider_slots
                WHERE provider_id = %s
                  AND status = 'AVAILABLE'
                  AND start_time >= %s
                  AND start_time < %s
                ORDER BY start_time ASC
                LIMIT %s
            """, (provider_id, start_date, end_date, limit))

            results = cursor.fetchall()

            slots = []
            for row in results:
                slots.append({
                    "slot_id": row[0],
                    "provider_id": row[1],
                    "start_time": row[2].isoformat(),
                    "end_time": row[3].isoformat(),
                    "status": row[4],
                })

            logger.info(
                "get_available_slots: found %d slots for provider=%s "
                "between %s and %s",
                len(slots), provider_id, start_date, end_date,
            )

            return slots

        finally:
            close_db_connection(conn)

    @staticmethod
    def provider_exists(provider_id: str) -> bool:
        """
        Check if a provider exists in the system.

        Args:
            provider_id: The provider's OSM ID

        Returns:
            True if provider exists, False otherwise
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT id FROM appointment_providers
                WHERE provider_id = %s AND active = TRUE
            """, (provider_id,))

            result = cursor.fetchone()
            return result is not None

        finally:
            close_db_connection(conn)

    @staticmethod
    def get_provider(provider_id: str) -> Optional[Dict[str, Any]]:
        """
        Get provider details.

        Args:
            provider_id: The provider's OSM ID

        Returns:
            Provider dict or None if not found
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT id, provider_id, provider_name, destination, specialty, active
                FROM appointment_providers
                WHERE provider_id = %s
            """, (provider_id,))

            result = cursor.fetchone()

            if not result:
                return None

            return {
                "id": result[0],
                "provider_id": result[1],
                "provider_name": result[2],
                "destination": result[3],
                "specialty": result[4],
                "active": result[5],
            }

        finally:
            close_db_connection(conn)

    @staticmethod
    def book_slot(
        mrn: str,
        provider_id: str,
        slot_id: str,
    ) -> Dict[str, Any]:
        """
        Book an available appointment slot, atomically.

        Validates that the slot exists, belongs to provider_id, and is
        currently AVAILABLE before booking. Marks the slot BOOKED and
        inserts a row into appointments in the same transaction, so a
        concurrent double-booking of the same slot is not possible.

        Args:
            mrn: Patient identifier (Medical Record Number)
            provider_id: The provider's OSM ID (e.g. osm:way:594121613)
            slot_id: The slot to book (must be AVAILABLE and belong to provider_id)

        Returns:
            {
                "appointment_id": str,
                "provider_id": str,
                "slot_id": str,
                "start_time": str (ISO-8601),
                "end_time": str (ISO-8601),
                "status": "BOOKED",
            }

        Raises:
            ValueError: If the slot does not exist, does not belong to
                provider_id, or is not currently AVAILABLE (already booked
                or held by someone else).
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor()

            # Lock the slot row for update so a concurrent booking attempt
            # on the same slot_id cannot race past this check.
            cursor.execute(
                """
                SELECT slot_id, provider_id, start_time, end_time, status
                FROM provider_slots
                WHERE slot_id = %s
                FOR UPDATE
                """,
                (slot_id,),
            )
            slot_row = cursor.fetchone()

            if slot_row is None:
                raise ValueError(f"Slot '{slot_id}' does not exist")

            _, slot_provider_id, start_time, end_time, status = slot_row

            if slot_provider_id != provider_id:
                raise ValueError(
                    f"Slot '{slot_id}' belongs to provider "
                    f"'{slot_provider_id}', not '{provider_id}'"
                )

            if status != "AVAILABLE":
                raise ValueError(
                    f"Slot '{slot_id}' is not available (current status: {status})"
                )

            appointment_id = f"APT-{token_urlsafe(8)}"

            cursor.execute(
                """
                INSERT INTO appointments
                    (appointment_id, mrn, provider_id, slot_id,
                     start_time, end_time, status, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, 'BOOKED',
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (appointment_id, mrn, provider_id, slot_id, start_time, end_time),
            )

            cursor.execute(
                """
                UPDATE provider_slots
                SET status = 'BOOKED', updated_at = CURRENT_TIMESTAMP
                WHERE slot_id = %s
                """,
                (slot_id,),
            )

            conn.commit()

            logger.info(
                "book_slot: booked appointment_id=%s mrn=%s provider_id=%s slot_id=%s",
                appointment_id, mrn, provider_id, slot_id,
            )

            return {
                "appointment_id": appointment_id,
                "provider_id": provider_id,
                "slot_id": slot_id,
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "status": "BOOKED",
            }

        except ValueError:
            conn.rollback()
            raise
        except Exception as exc:
            conn.rollback()
            raise ValueError(f"Failed to book slot: {exc}")

        finally:
            close_db_connection(conn)
