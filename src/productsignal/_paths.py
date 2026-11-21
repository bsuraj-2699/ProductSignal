"""
Shared path utilities for ProductSignal.

Provides reliable project root and default path resolution
independent of current working directory.
"""

from pathlib import Path
from typing import Optional


def get_project_root() -> Path:
    """
    Get the project root directory.

    Uses the location of this module to find the project root,
    independent of the current working directory.

    This file is at src/productsignal/_paths.py
    Project root is 3 levels up.
    """
    return Path(__file__).resolve().parent.parent.parent


def get_default_db_path() -> Path:
    """Get the default database path relative to project root."""
    return get_project_root() / "data" / "productsignal.db"


def get_default_config_dir() -> Path:
    """Get the default vibes configuration directory."""
    return get_project_root() / "config" / "vibes"


def get_supported_dataset_path() -> Optional[Path]:
    """Get the path to the supported Kaggle dataset if it exists."""
    path = get_project_root() / "data" / "raw" / "customer_support_tickets.csv"
    if path.exists():
        return path
    return None