"""
conftest.py — shared pytest fixtures and import stubs for the test suite.

Stubs src.logging before any test module imports it, so the real loguru
setup (which reads config files) never runs during unit tests.
"""
import sys
import types
from unittest.mock import MagicMock

# Stub src.logging so discord_reporter can import `from src.logging import logger`
# without triggering the real loguru initialisation that reads config files.
_logging_stub = types.ModuleType("src.logging")
_logging_stub.logger = MagicMock()
sys.modules.setdefault("src.logging", _logging_stub)
