from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Union
from uuid import UUID, uuid4


class AcceptanceState(Enum):
    UNPROCESSED = "unprocessed"
    MET = "met"
    UNMET = "unmet"


@dataclass
class AcceptanceCriterion:
    id: UUID
    created_at: datetime
    name: str  # e.g., AC-1, AC-2 (per-requirement numbering)
    text: str
    state: AcceptanceState = AcceptanceState.UNPROCESSED

    @staticmethod
    def create(name: str, text: str, state: Optional[Union[str, AcceptanceState]] = None) -> "AcceptanceCriterion":
        if isinstance(state, str):
            try:
                state_val = AcceptanceState(state)
            except Exception:
                state_val = AcceptanceState.UNPROCESSED
        elif isinstance(state, AcceptanceState):
            state_val = state
        else:
            state_val = AcceptanceState.UNPROCESSED
        return AcceptanceCriterion(
            id=uuid4(),
            created_at=datetime.now(timezone.utc),
            name=name,
            text=text,
            state=state_val,
        )


