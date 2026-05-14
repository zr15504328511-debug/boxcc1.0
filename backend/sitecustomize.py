"""Backend interpreter startup hooks.

Keep this file intentionally inert. Historical live-module aliases made
`subagents.tools` resolve to a different implementation depending on the
Python startup path, which is dangerous for orchestration behavior.
"""
