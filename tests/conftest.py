"""Pytest setup for the FastAPI application under test.

The API is a source-layout Python package.  Tests add that one source root to
``sys.path`` so the application can be exercised in-process without starting
an HTTP server.
"""

from pathlib import Path
import sys


API_SRC = Path(__file__).resolve().parents[1] / "apps" / "api" / "src"
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))
