"""Pytest configuration for backend test suite."""

from __future__ import annotations

import os
import pytest

# Set default test environment variables before any test runs
os.environ.setdefault("LLM_PRIMARY_PROVIDER", "fake")
os.environ.setdefault("LLM_FALLBACK_PROVIDER", "fake")
os.environ.setdefault("INTEGRATION_MODE", "simulated")
