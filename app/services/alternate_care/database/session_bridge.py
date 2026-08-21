"""
Database bridge - reuse CarePath's existing PostgreSQL connection
Uses async SQLAlchemy (CarePath's existing setup)
"""
from __future__ import annotations

from typing import Optional, Dict, Any, List
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import json
import logging

logger = logging.getLogger(__name__)


class AppointmentSessionRepository:
    """Repository for appointment session state using CarePath's async DB"""
    
    @staticmethod
    async def create_session(
        db: AsyncSession,
        mrn: str,
        destination: str,
        specialty: Optional[str],
        rule_id: str,
        latitude: float,
        longitude: float,
        radius_km: float,
        source: str,
        session_id: str,
        conversation_state: Optional[List[Dict]] = None
    ) -> str:
        """Create new appointment session"""
        
        query = text("""
            INSERT INTO appointment_sessions (
                session_id, mrn, destination, specialty, rule_id,
                latitude, longitude, radius_km, source, conversation_state
            ) VALUES (
                :session_id, :mrn, :destination, :specialty, :rule_id,
                :latitude, :longitude, :radius_km, :source, CAST(:conversation_state AS jsonb)
            )
            RETURNING session_id
        """)
        
        result = await db.execute(query, {
            "session_id": session_id,
            "mrn": mrn,
            "destination": destination,
            "specialty": specialty,
            "rule_id": rule_id,
            "latitude": latitude,
            "longitude": longitude,
            "radius_km": radius_km,
            "source": source,
            "conversation_state": json.dumps(conversation_state) if conversation_state else None
        })
        
        await db.commit()
        return session_id
    
    @staticmethod
    async def get_session(
        db: AsyncSession,
        session_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get session by ID"""
        
        query = text("""
            SELECT * FROM appointment_sessions
            WHERE session_id = :session_id
            AND expires_at > NOW()
        """)
        
        result = await db.execute(query, {"session_id": session_id})
        row = result.fetchone()
        
        if not row:
            return None
        
        # Convert to dict
        session_dict = dict(row._mapping)
        
        # JSONB fields are already parsed by asyncpg
        # No need to json.loads() them
        
        return session_dict
    
    @staticmethod
    async def update_session(
        db: AsyncSession,
        session_id: str,
        updates: Dict[str, Any]
    ) -> None:
        """Update session fields"""
        
        # Build dynamic UPDATE query
        set_clauses = []
        params = {"session_id": session_id}
        
        for key, value in updates.items():
            if key in ["conversation_state", "provider_candidates", "available_slots"]:
                # JSONB fields
                set_clauses.append(f"{key} = CAST(:{key} AS jsonb)")
                params[key] = json.dumps(value) if value else None
            else:
                set_clauses.append(f"{key} = :{key}")
                params[key] = value
        
        set_clauses.append("updated_at = NOW()")
        
        query = text(f"""
            UPDATE appointment_sessions
            SET {", ".join(set_clauses)}
            WHERE session_id = :session_id
        """)
        
        await db.execute(query, params)
        await db.commit()


__all__ = ["AppointmentSessionRepository"]
