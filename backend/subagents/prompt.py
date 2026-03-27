"""Prompt builders for department subagents."""

from agents.spec_loader import load_prompt_spec
from subagents.config import SubagentConfig

GLOBAL_DEPARTMENT_RULES = """
## Global Execution Rules
- You are a stateless specialist. You do not have access to the full user chat history.
- Only use the current system prompt, the task packet, and any approved skill packs for this run.
- Do not claim hidden context or prior turns.
- If a `Worker Session Shard` block is provided, treat it as compressed same-conversation continuation memory for your department only.
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
- worker_id: specific fix request
</validation_report>
- If no rework is needed, keep `rework_targets:` empty with no list items.
- `pass_gate=passed` means the output can be delivered.
- `pass_gate=fixes_required` means the output is valuable but must be revised before delivery.
- `pass_gate=failed` means the current result should not be delivered.
""".strip()


def build_department_system_prompt(dept: SubagentConfig) -> str:
    """Build the effective system prompt for a department agent."""
    base_prompt = load_prompt_spec(dept.spec_path, dept.system_prompt) or f"You are the {dept.name} department."
    role_block = (
        "## Department Identity\n"
        f"- Department ID: {dept.id}\n"
        f"- Department Name: {dept.name}\n"
        f"- Display Name: {dept.display_name or dept.id}\n"
        f"- Responsibility: {dept.description or 'Not specified'}\n"
        f"- Registered Skill Packs: {', '.join(dept.skill_packs) if dept.skill_packs else 'None'}"
    )
    contract = CRITIC_OUTPUT_CONTRACT if dept.id == "crt" else WORKER_OUTPUT_CONTRACT
    return "\n\n".join([base_prompt, role_block, GLOBAL_DEPARTMENT_RULES, contract])
