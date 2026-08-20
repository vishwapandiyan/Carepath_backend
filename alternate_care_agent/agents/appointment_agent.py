"""
THE SHARED APPOINTMENT AGENT — NOT owned by this codebase.

This module is intentionally just a re-export of appointment/client.py's
HTTP client. It exists so the agents/ package reads as the complete list
of "agents in this pipeline" (Classification -> Ranking -> Appointment),
while making it unmistakable that the third one is external: your
teammate's service, reused by every navigation agent on the team (not
just this one). Do not add booking/availability logic in this file — it
belongs in the teammate's service, this is only ever a client.
"""

from appointment.client import AppointmentAgentClient  # noqa: F401
