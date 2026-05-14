"""Path utilities for data directories."""

import os
from pathlib import Path


def get_backend_root() -> Path:
    return Path(__file__).parent.parent


def get_data_dir() -> Path:
    override = os.getenv("BOXCC_BACKEND_DATA_DIR")
    d = Path(override).expanduser() if override else get_backend_root() / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def resolve_path(relative_path: str) -> Path:
    """Resolve a path relative to backend root."""
    p = Path(relative_path)
    if p.is_absolute():
        return p
    if p.parts and p.parts[0] == "data":
        return get_data_dir().joinpath(*p.parts[1:])
    return get_backend_root() / p
