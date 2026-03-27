"""Memory API endpoints."""

from fastapi import APIRouter

from agents.memory.updater import get_memory_data, _save_memory

router = APIRouter()


@router.get("/memory")
async def get_memory():
    return get_memory_data()


@router.put("/memory")
async def update_memory(data: dict):
    success = _save_memory(data)
    return {"ok": success}
