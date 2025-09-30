from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import UUID, uuid4

from .usage import Usage
from .computer_action import ComputerAction


@dataclass
class Interaction:
    id: UUID
    turn_index: int
    started_at: datetime
    finished_at: datetime
    elapsed_s: float
    model_response_id: Optional[str]
    reasoning_summary: Optional[str]
    message_text: Optional[str]
    screenshot_path: Optional[Path]
    usage: Optional[Usage]
    action: Optional[ComputerAction]

    @staticmethod
    def create(
        turn_index: int,
        started_at: datetime,
        finished_at: datetime,
        elapsed_s: float,
        model_response_id: Optional[str] = None,
        reasoning_summary: Optional[str] = None,
        message_text: Optional[str] = None,
        screenshot_path: Optional[Path] = None,
        usage: Optional[Usage] = None,
        action: Optional[ComputerAction] = None,
    ) -> "Interaction":
        return Interaction(
            id=uuid4(),
            turn_index=turn_index,
            started_at=started_at,
            finished_at=finished_at,
            elapsed_s=elapsed_s,
            model_response_id=model_response_id,
            reasoning_summary=reasoning_summary,
            message_text=message_text,
            screenshot_path=screenshot_path,
            usage=usage,
            action=action,
        )

    def __repr__(self) -> str:
        return (
            f"Interaction(turn={self.turn_index}, elapsed_s={self.elapsed_s:.2f}, "
            f"response_id={self.model_response_id!r}, action={self.action})"
        )

    def __str__(self) -> str:
        lines = []
        summ = self.reasoning_summary or self.message_text or ""
        header = f"Turn {self.turn_index}: {summ[:160]}" if summ else f"Turn {self.turn_index}"
        lines.append(header)
        if self.message_text:
            lines.append(f"Message: {self.message_text}")
        if self.action:
            lines.append(f"Action: {self.action}")
        if self.usage:
            lines.append(f"Usage: {self.usage}")
        return "\n".join(lines)
