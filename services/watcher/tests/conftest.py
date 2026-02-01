"""Pytest configuration for watcher tests."""

import sys
from pathlib import Path

# Add the project root to Python path to make services package importable
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))
