from dataclasses import dataclass
from datetime import datetime
from typing import Any


_FIRST_PROMPT_MAX = 200


@dataclass
class Breadcrumb:
    """One Claude session's breadcrumb. Pushed to claude-journal/raw/.

    Phase 1 stores structural fields only — the central nightly routine
    consolidates these into digests/memories/skills with its own LLM calls.
    """
    session_id: str
    device: str
    project: str
    started_at: datetime
    ended_at: datetime
    files_touched: list[str]
    skills_invoked: list[str]
    first_prompt: str

    def __post_init__(self) -> None:
        # Truncation is a property of the data, not of serialization.
        if len(self.first_prompt) > _FIRST_PROMPT_MAX:
            self.first_prompt = self.first_prompt[:_FIRST_PROMPT_MAX]

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "device": self.device,
            "project": self.project,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat(),
            "files_touched": list(self.files_touched),
            "skills_invoked": list(self.skills_invoked),
            "first_prompt": self.first_prompt,
        }
