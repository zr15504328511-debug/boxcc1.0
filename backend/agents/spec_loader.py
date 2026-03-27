"""Helpers for loading prompt spec files."""

import logging
from pathlib import Path

from config.paths import resolve_path

logger = logging.getLogger(__name__)


def load_prompt_spec(spec_path: str | None, fallback_text: str = "") -> str:
    """Load a prompt spec from disk, falling back to inline text if needed."""
    if spec_path:
        path = resolve_path(spec_path)
        try:
            return path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            logger.warning("Prompt spec file not found: %s", path)
        except OSError as exc:
            logger.warning("Failed to read prompt spec %s: %s", path, exc)

    return (fallback_text or "").strip()