"""
FastAPI application wrapper - imports from refactored app/ package.

The main FastAPI app is now in app/main.py.
This file is kept for backward compatibility.
"""

from app.main import app

__all__ = ["app"]

