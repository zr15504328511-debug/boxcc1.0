import importlib
import sys

for legacy_name, live_name in [
    ("subagents.executor", "subagents.executor_live"),
    ("subagents.tools", "subagents.tools_live"),
]:
    try:
        sys.modules[legacy_name] = importlib.import_module(live_name)
    except Exception:
        pass
