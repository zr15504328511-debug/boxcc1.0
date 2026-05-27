"""Deliverable template registry — recipes for high-quality product output.

Each registered deliverable type defines:
- which export tool to call (`output_tool`)
- the structural skeleton orc should fill (`structure` sections)
- which workers must / should contribute (`required_workers` /
  `suggested_workers`) and what each worker owns
  (`worker_contribution_map`)
- the critic checklist (`quality_gates`)

Templates live in `config.yaml` under `deliverable_types:` so adding a
new product type is a config edit, not a Python change.
"""

from deliverables.registry import (
    describe_deliverable_types,
    get_deliverable_type,
    list_deliverable_types,
    match_deliverable_type,
    render_deliverable_brief,
    reset_deliverables_cache,
)

__all__ = [
    "describe_deliverable_types",
    "get_deliverable_type",
    "list_deliverable_types",
    "match_deliverable_type",
    "render_deliverable_brief",
    "reset_deliverables_cache",
]
