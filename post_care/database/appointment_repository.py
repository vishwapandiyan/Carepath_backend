"""
Appointment Session Repository Layer

Provides PostgreSQL persistence for appointment sessions — the shared state
between the Navigation Agent's care decision and the Appointment Agent's
scheduling workflow.

This layer:
- Replaces the in-memory RecommendationStore for durable persistence
- Uses the same psycopg2 + raw SQL pattern as repositories.py
- Shares the same carepath_db PostgreSQL instance
- Uses MRN as the patient identifier (consistent with patient_ehr)

Architecture:
    Navigation / Appointment Agent
        ↓
    Repository Layer (this module)
        ↓
    PostgreSQL (carepath_db → appointment_sessions table)
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from secrets import token_urlsafe
from typing import Any, Dict, List, Optional

from post_care.database.connection import get_db_connection, close_db_connection

logger = logging.getLogger(__name__)


class AppointmentSessionRepository:
    """Repository for appointment session persistence in PostgreSQL."""

    @staticmethod
    def create_session(
        mrn: str,
        destination: str,
        specialty: Optional[str] = None,
        rule_id: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        radius_km: float = 15.0,
        source: str = "PATIENT",
        care_plan_id: Optional[str] = None,
        ttl_minutes: int = 30,
        session_id: Optional[str] = None,
        conversation_state: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Create a new appointment session in PostgreSQL.

        Sets expires_at based on ttl_minutes from now.

        Args:
            mrn: Medical Record Number (must exist in patient_ehr)
            destination: Care destination (PCP, URGENT_CARE, SPECIALIST, etc.)
            specialty: Specialist sub-type when destination is SPECIALIST
            rule_id: Matched rule ID from the care classifier
            latitude: Patient latitude
            longitude: Patient longitude
            radius_km: Search radius in km (default 15.0)
            source: Who triggered this session — 'PATIENT' or 'POST_CARE'
            care_plan_id: FK to care_plans when source is POST_CARE
            ttl_minutes: Session time-to-live in minutes (default 30)
            session_id: Optional explicit session identifier. When the
                caller already has an authoritative ID (e.g. the
                recommendation_id generated upstream by a navigation
                pipeline), pass it here so the appointment session shares
                that same identifier instead of minting a second,
                unrelated ID. When omitted, a new ID is generated
                (format: rec_<token>).
            conversation_state: Optional JSON-serializable value (e.g. the
                Appointment Agent's LLM message history) to persist
                alongside the session from creation time.

        Returns:
            Dictionary with created session data including session_id

        Raises:
            ValueError: If insertion fails or destination is invalid
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor()

            resolved_session_id = session_id or f"rec_{token_urlsafe(12)}"
            expires_at = datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)
            conversation_state_json = (
                json.dumps(conversation_state) if conversation_state is not None else None
            )

            cursor.execute(
                """
                INSERT INTO appointment_sessions
                (session_id, mrn, destination, specialty, rule_id,
                 latitude, longitude, radius_km, source, care_plan_id,
                 workflow_stage, expires_at, conversation_state,
                 created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb,
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                RETURNING id, session_id, mrn, destination, specialty, rule_id,
                          latitude, longitude, radius_km, workflow_stage,
                          created_at, updated_at, expires_at, source, care_plan_id,
                          conversation_state
                """,
                (
                    resolved_session_id, mrn, destination, specialty, rule_id,
                    latitude, longitude, radius_km, source, care_plan_id,
                    "NAVIGATION_COMPLETE", expires_at, conversation_state_json,
                ),
            )

            result = cursor.fetchone()
            conn.commit()

            return {
                "id": result[0],
                "session_id": result[1],
                "mrn": result[2],
                "destination": result[3],
                "specialty": result[4],
                "rule_id": result[5],
                "latitude": result[6],
                "longitude": result[7],
                "radius_km": result[8],
                "workflow_stage": result[9],
                "created_at": result[10].isoformat() if result[10] else None,
                "updated_at": result[11].isoformat() if result[11] else None,
                "expires_at": result[12].isoformat() if result[12] else None,
                "source": result[13],
                "care_plan_id": result[14],
                "conversation_state": result[15],
                "provider_candidates": None,
                "ranked_providers": None,
                "selected_provider_id": None,
                "available_slots": None,
                "selected_slot_id": None,
                "appointment_id": None,
                "appointment_status": None,
            }

        except Exception as e:
            conn.rollback()
            raise ValueError(f"Failed to create appointment session: {str(e)}")

        finally:
            close_db_connection(conn)

    @staticmethod
    def get_session(session_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve an appointment session by session_id.

        Only returns non-expired sessions. Expired sessions return None.

        Args:
            session_id: The session identifier (e.g. "rec_aBcDeFgHiJkL")

        Returns:
            Session dictionary if found and not expired, None otherwise
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT id, session_id, mrn, destination, specialty, rule_id,
                       latitude, longitude, radius_km,
                       provider_candidates, ranked_providers, selected_provider_id,
                       available_slots, selected_slot_id,
                       appointment_id, appointment_status,
                       workflow_stage, created_at, updated_at, expires_at,
                       source, care_plan_id, conversation_state
                FROM appointment_sessions
                WHERE session_id = %s
                  AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
                """,
                (session_id,),
            )

            result = cursor.fetchone()

            if not result:
                return None

            return {
                "id": result[0],
                "session_id": result[1],
                "mrn": result[2],
                "destination": result[3],
                "specialty": result[4],
                "rule_id": result[5],
                "latitude": result[6],
                "longitude": result[7],
                "radius_km": result[8],
                "provider_candidates": result[9],
                "ranked_providers": result[10],
                "selected_provider_id": result[11],
                "available_slots": result[12],
                "selected_slot_id": result[13],
                "appointment_id": result[14],
                "appointment_status": result[15],
                "workflow_stage": result[16],
                "created_at": result[17].isoformat() if result[17] else None,
                "updated_at": result[18].isoformat() if result[18] else None,
                "expires_at": result[19].isoformat() if result[19] else None,
                "source": result[20],
                "care_plan_id": result[21],
                "conversation_state": result[22],
            }

        finally:
            close_db_connection(conn)

    @staticmethod
    def update_session(session_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update appointment session fields.

        JSONB fields (provider_candidates, ranked_providers, available_slots)
        are serialized to JSON before storage.

        Args:
            session_id: The session identifier
            updates: Dictionary of fields to update. Supported fields:
                     provider_candidates, ranked_providers, selected_provider_id,
                     available_slots, selected_slot_id, appointment_id,
                     appointment_status, workflow_stage

        Returns:
            Updated session dictionary

        Raises:
            ValueError: If session not found or update fails
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor()

            # Serialize JSONB fields
            jsonb_fields = {
                "provider_candidates", "ranked_providers", "available_slots",
                "conversation_state",
            }
            processed_updates = {}
            for key, value in updates.items():
                if key in jsonb_fields and value is not None:
                    processed_updates[key] = json.dumps(value)
                else:
                    processed_updates[key] = value

            # Build dynamic UPDATE query
            set_clauses = []
            values = []
            for key, value in processed_updates.items():
                if key in jsonb_fields and value is not None:
                    set_clauses.append(f"{key} = %s::jsonb")
                else:
                    set_clauses.append(f"{key} = %s")
                values.append(value)

            set_clauses.append("updated_at = CURRENT_TIMESTAMP")
            set_clause_str = ", ".join(set_clauses)

            values.append(session_id)

            cursor.execute(
                f"""
                UPDATE appointment_sessions
                SET {set_clause_str}
                WHERE session_id = %s
                  AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
                RETURNING id, session_id, mrn, destination, specialty, rule_id,
                          latitude, longitude, radius_km,
                          provider_candidates, ranked_providers, selected_provider_id,
                          available_slots, selected_slot_id,
                          appointment_id, appointment_status,
                          workflow_stage, created_at, updated_at, expires_at,
                          source, care_plan_id, conversation_state
                """,
                values,
            )

            result = cursor.fetchone()

            if not result:
                raise ValueError(
                    f"Appointment session '{session_id}' not found or expired"
                )

            conn.commit()

            return {
                "id": result[0],
                "session_id": result[1],
                "mrn": result[2],
                "destination": result[3],
                "specialty": result[4],
                "rule_id": result[5],
                "latitude": result[6],
                "longitude": result[7],
                "radius_km": result[8],
                "provider_candidates": result[9],
                "ranked_providers": result[10],
                "selected_provider_id": result[11],
                "available_slots": result[12],
                "selected_slot_id": result[13],
                "appointment_id": result[14],
                "appointment_status": result[15],
                "workflow_stage": result[16],
                "created_at": result[17].isoformat() if result[17] else None,
                "updated_at": result[18].isoformat() if result[18] else None,
                "expires_at": result[19].isoformat() if result[19] else None,
                "source": result[20],
                "care_plan_id": result[21],
                "conversation_state": result[22],
            }

        except ValueError:
            conn.rollback()
            raise
        except Exception as e:
            conn.rollback()
            raise ValueError(f"Failed to update appointment session: {str(e)}")

        finally:
            close_db_connection(conn)

    @staticmethod
    def expire_sessions() -> int:
        """
        Delete all expired appointment sessions.

        Returns:
            Number of sessions deleted

        Note:
            Call this periodically (e.g. via scheduler) to clean up
            stale sessions.
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor()

            cursor.execute(
                """
                DELETE FROM appointment_sessions
                WHERE expires_at IS NOT NULL
                  AND expires_at <= CURRENT_TIMESTAMP
                """
            )

            deleted_count = cursor.rowcount
            conn.commit()

            if deleted_count > 0:
                logger.info(
                    "expire_sessions: deleted %d expired appointment sessions",
                    deleted_count,
                )

            return deleted_count

        except Exception as e:
            conn.rollback()
            logger.error("expire_sessions failed: %s", e)
            return 0

        finally:
            close_db_connection(conn)
