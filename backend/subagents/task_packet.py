"""Structured task packets exchanged from orc to worker departments."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator


_HISTORY_ROLE_ALIASES = {
    'human': 'user',
    'ai': 'assistant',
    'assistant_message': 'assistant',
    'user_message': 'user',
}


class AttachedHistoryItem(BaseModel):
    """A single conversation fragment hand-picked by orc for a worker.

    Workers are otherwise stateless; this lets orc surface only the
    minimum prior context needed for the task. Each item is rendered as
    a HumanMessage or AIMessage before the task packet body.
    """

    role: Literal['user', 'assistant'] = 'user'
    content: str = Field(min_length=1)

    @field_validator('role', mode='before')
    @classmethod
    def _coerce_role(cls, value):
        text = str(value or 'user').strip().lower()
        return _HISTORY_ROLE_ALIASES.get(text, text)


_PRIORITY_ALIASES = {
    'medium': 'normal',
    'mid': 'normal',
    'urgent': 'high',
}


class WorkerTaskPacket(BaseModel):
    """Normalized task packet sent from orc to a worker."""

    objective: str = Field(min_length=1, description='What business outcome this worker should achieve.')
    task: str = Field(min_length=1, description='The concrete assignment for this worker.')
    context: list[str] = Field(default_factory=list, description='Condensed facts selected by orc.')
    constraints: list[str] = Field(default_factory=list, description='Hard constraints the worker must obey.')
    required_output: list[str] = Field(default_factory=list, description='Expected output sections.')
    requested_skill_packs: list[str] = Field(default_factory=list, description='Skill packs that orc wants this worker to use if available.')
    priority: Literal['low', 'normal', 'high'] = 'normal'
    notes: list[str] = Field(default_factory=list, description='Optional execution notes from orc.')
    success_criteria: list[str] = Field(default_factory=list, description='What a good result should explicitly cover.')
    attached_history: list[AttachedHistoryItem] = Field(
        default_factory=list,
        description='Conversation fragments orc hand-picked for this worker. Each item is rendered as a HumanMessage or AIMessage before the task body. Use sparingly.',
    )
    kb_refs: list[str] = Field(
        default_factory=list,
        description='Knowledge base ids that orc assigned to this worker. Workers may only query KBs listed here.',
    )

    @field_validator('objective', mode='before')
    @classmethod
    def _normalize_objective(cls, value):
        text = ' '.join(str(value or '').split())
        return text[:700].rstrip()

    @field_validator('task', mode='before')
    @classmethod
    def _normalize_task(cls, value):
        text = ' '.join(str(value or '').split())
        return text[:1600].rstrip()

    @field_validator('priority', mode='before')
    @classmethod
    def _normalize_priority(cls, value):
        if value is None:
            return 'normal'
        text = str(value).strip().lower()
        return _PRIORITY_ALIASES.get(text, text)

    @field_validator('context', 'constraints', 'required_output', 'requested_skill_packs', 'notes', 'success_criteria', 'kb_refs', mode='before')
    @classmethod
    def _normalize_string_list(cls, value):
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise TypeError('Expected a list of strings.')
        normalized = []
        for item in value[:8]:
            text = str(item).strip()
            if text:
                normalized.append(' '.join(text.split())[:420].rstrip())
        return normalized


def render_task_packet(packet: WorkerTaskPacket, available_skill_packs: list[str] | None = None) -> str:
    """Render a task packet into the worker-facing request body."""
    available_skill_packs = available_skill_packs or []
    lines = [
        f'Objective\n{packet.objective}',
        f'Task\n{packet.task}',
        f'Priority\n{packet.priority}',
    ]

    if packet.context:
        lines.append('Context\n' + '\n'.join(f'- {item}' for item in packet.context))
    if packet.constraints:
        lines.append('Constraints\n' + '\n'.join(f'- {item}' for item in packet.constraints))
    if packet.required_output:
        lines.append('Required Output\n' + '\n'.join(f'- {item}' for item in packet.required_output))
    if packet.success_criteria:
        lines.append('Success Criteria\n' + '\n'.join(f'- {item}' for item in packet.success_criteria))
    if available_skill_packs:
        lines.append('Registered Skill Packs\n' + '\n'.join(f'- {item}' for item in available_skill_packs))
    if packet.requested_skill_packs:
        lines.append('Approved Skill Packs For This Task\n' + '\n'.join(f'- {item}' for item in packet.requested_skill_packs))
    if packet.notes:
        lines.append('Execution Notes\n' + '\n'.join(f'- {item}' for item in packet.notes))
    if packet.kb_refs:
        lines.append('Assigned Knowledge Bases\n' + '\n'.join(f'- {item}' for item in packet.kb_refs))

    return '\n\n'.join(lines)
