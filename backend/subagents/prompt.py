"""Prompt builders for specialist subagents."""

from agents.master_prompt import load_master_prompt
from agents.spec_loader import load_prompt_spec
from subagents.config import SubagentConfig

GLOBAL_DEPARTMENT_RULES = """
## Global Execution Rules
- You are a stateless specialist. You do not have access to the full user chat history.
- Only use the current system prompt, the task packet, and any authorised KBs for this run.
- Do not claim hidden context or prior turns.
- If a `Worker Session Shard` block is provided, treat it as compressed same-conversation continuation memory for your agent only.
- Return concise, decision-ready output instead of long chain-of-thought.
- Surface concrete risks, constraints, and recommended actions.
- If the task is underspecified, state what is missing and make the safest reasonable assumption.
- Do not mention internal tools unless they directly affect the answer.
- Keep the answer practical and ready for the chairman to integrate.
""".strip()

WORKER_OUTPUT_CONTRACT = """
## Output Contract
- Organize the answer into clear sections such as conclusion, key evidence, risks, and actions.
- Prefer numbered points when there are multiple recommendations.
- Keep the tone factual and execution-oriented.
""".strip()

CRITIC_OUTPUT_CONTRACT = """
## Critic Output Contract
- You are the single validation authority for the run.
- Review the worker outputs for conflict, omission, risk, feasibility, and delivery quality.
- When the task involves code, webpages, images, video, PPT, or other artifacts, evaluate the artifact itself instead of only reviewing text summaries.
- Produce a decision-ready validation report.
- Your answer must end with a machine-readable block using this exact shape:
<validation_report>
pass_gate: passed|fixes_required|failed
summary: one-sentence verdict
rework_targets:
- agent_id: specific fix request
</validation_report>
- If no rework is needed, keep `rework_targets:` empty with no list items.
- `pass_gate=passed` means the output can be delivered.
- `pass_gate=fixes_required` means the output is valuable but must be revised before delivery.
- `pass_gate=failed` means the current result should not be delivered.
""".strip()


def build_department_system_prompt(dept: SubagentConfig) -> str:
    """Build the effective system prompt for a specialist agent.

    Note: the `dept` parameter name is kept for source-line stability with
    callers; semantically it's a single specialist agent, not a department.
    """
    base_prompt = load_prompt_spec(dept.spec_path, "") or f"You are the `{dept.id}` agent ({dept.name})."
    role_block = (
        "## Agent Identity\n"
        f"- Agent ID: {dept.id}\n"
        f"- Name: {dept.name}\n"
        f"- One-liner: {dept.one_liner or '(not set)'}\n"
        f"- Tags: {', '.join(dept.tags) if dept.tags else '(none)'}\n"
        f"- Authorised KBs (declared scope): {', '.join(dept.kb_refs) if dept.kb_refs else '(none)'}"
    )
    contract = CRITIC_OUTPUT_CONTRACT if dept.id == "crt" else WORKER_OUTPUT_CONTRACT

    # boxcc.md (master constitution) is prepended to every worker prompt so
    # that cross-agent rules (history policy, KB routing, output style) stay
    # in a single source of truth. Skip silently if missing.
    sections: list[str] = []
    master = load_master_prompt()
    if master:
        sections.append(master)
    sections.extend([base_prompt, role_block, GLOBAL_DEPARTMENT_RULES, contract])
    return "\n\n".join(sections)
