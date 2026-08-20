"""Entrypoint: `uvicorn main:app --reload`"""
from api.routes import app  # noqa: F401
