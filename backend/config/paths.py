"""Path utilities for data directories."""

import os
from pathlib import Path


def get_backend_root() -> Path:
    return Path(__file__).parent.parent


def get_data_dir() -> Path:
    d = get_backend_root() / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def resolve_path(relative_path: str) -> Path:
    """Resolve a path relative to backend root."""
    p = Path(relative_path)
    if p.is_absolute():
        return p
    return get_backend_root() / p
