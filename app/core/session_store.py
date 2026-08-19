"""
In-memory session store — prototype grade.
Data is lost on server restart.
To promote to production: replace this module with Redis (aioredis)
or a DB-backed session table without changing any callers.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

# ── Internal store ────────────────────────────────────────────────────────────
_sessions: dict[str, dict[str, Any]] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── Public API ────────────────────────────────────────────────────────────────

def create_session(patient_id: str) -> dict[str, Any]:
    """Create a new session and store it in memory. Returns the session dict."""
    session_id = str(uuid.uuid4())
    session: dict[str, Any] = {
        "session_id": session_id,
        "patient_id": patient_id,
        "status": "IN_PROGRESS",   # IN_PROGRESS | COMPLETE | ERROR
        "features": None,          # dict — cumulative LLMExtraction, None until first message
        "messages": [],            # list[{role, content, timestamp}]
        "next_question": None,
        "created_at": _now(),
        "updated_at": _now(),
    }
    _sessions[session_id] = session
    return session


def get_session(session_id: str) -> dict[str, Any] | None:
    """Return session dict or None if not found."""
    return _sessions.get(session_id)


def update_session(session_id: str, **kwargs: Any) -> dict[str, Any] | None:
    """Patch arbitrary fields on an existing session. Returns updated session or None."""
    if session_id not in _sessions:
        return None
    _sessions[session_id].update(kwargs)
    _sessions[session_id]["updated_at"] = _now()
    return _sessions[session_id]


def append_message(session_id: str, role: str, content: str) -> bool:
    """Append a message to the session history. Returns False if session not found."""
    if session_id not in _sessions:
        return False
    _sessions[session_id]["messages"].append(
        {"role": role, "content": content, "timestamp": _now().isoformat()}
    )
    _sessions[session_id]["updated_at"] = _now()
    return True


def clear_all() -> None:
    """Wipe all sessions. Test helper only — never call in production code."""
    _sessions.clear()
