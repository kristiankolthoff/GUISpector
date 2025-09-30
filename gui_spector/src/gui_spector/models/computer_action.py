from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional


class ActionType(Enum):
    CLICK = "click"
    DOUBLE_CLICK = "double_click"
    SCROLL = "scroll"
    TYPE = "type"
    KEYPRESS = "keypress"
    MOVE = "move"
    DRAG = "drag"
    WAIT = "wait"


@dataclass
class ComputerAction:
    type: ActionType
    params: Dict[str, Any]
    call_id: Optional[str] = None
    status: Optional[str] = None
    safety_checks: Optional[list[str]] = None

    def __repr__(self) -> str:
        return (
            f"ComputerAction(type={self.type.name}, status={self.status!r}, "
            f"call_id={self.call_id!r}, params={self.params})"
        )

    def __str__(self) -> str:
        return f"{self.type.value} {self.params} (status={self.status})"
