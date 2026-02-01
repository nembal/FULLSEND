"""Pytest configuration for roundtable tests."""

import pytest


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "integration: mark test as an integration test that requires API keys and calls real LLMs"
    )
