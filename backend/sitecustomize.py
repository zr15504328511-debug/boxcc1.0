"""Python startup hook.

Historically this file swapped `subagents.executor` → `subagents.executor_live`
and `subagents.tools` → `subagents.tools_live` at import time. The redirect
was disabled after the 6-dept rewrite (mer/sup/chl/gro/biz/crt) because the
`_live` variants stayed on the legacy 4-dept routing. The `_live` files have
since been deleted entirely after the 18-agent registry refactor.

This file is now an intentional no-op kept so that any tooling expecting a
`sitecustomize` module on the path still finds one.
"""
