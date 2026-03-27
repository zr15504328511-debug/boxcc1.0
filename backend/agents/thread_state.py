"""Thread state schema for boxcc agents."""

from typing import Annotated, NotRequired

from langchain.agents import AgentState


def merge_department_results(
    existing: list[dict] | None, new: list[dict] | None
) -> list[dict]:
    if existing is None:
        return new or []
    if new is None:
        return existing
    # Merge by department id, new overrides existing
    result = {r["id"]: r for r in existing}
    for r in new:
        result[r["id"]] = r
    return list(result.values())


class ThreadState(AgentState):
    """State schema for boxcc conversation threads.

    Simplified from DeerFlow - no sandbox, uploads, or viewed_images.
    """
    title: NotRequired[str | None]
    department_results: Annotated[list[dict], merge_department_results]
