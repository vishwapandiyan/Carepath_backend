"""
Shared pytest fixtures and configuration.
"""

import pytest
from app.core.session_store import clear_all


@pytest.fixture(autouse=True)
def reset_session_store():
    """Wipe in-memory sessions before every test to guarantee isolation."""
    clear_all()
    yield
    clear_all()
