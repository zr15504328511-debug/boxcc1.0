"""Models endpoint - list available models from config."""

from fastapi import APIRouter

from config.app_config import get_app_config

router = APIRouter()


@router.get("/models")
async def list_models():
    config = get_app_config()
    return [
        {
            "name": m.name,
            "display_name": m.display_name or m.name,
        }
        for m in config.models
    ]
