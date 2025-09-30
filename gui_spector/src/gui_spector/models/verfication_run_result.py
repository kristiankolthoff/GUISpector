from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional, List
from uuid import UUID

from  gui_spector.models.requirements import Requirements
from gui_spector.models.interaction import Interaction
from gui_spector.models.usage import Usage


class VerificationStatus(Enum):
    MET = "met"
    UNMET = "unmet"
    PARTIALLY_MET = "partially_met"
    ERROR = "error"


@dataclass
class VerficationRunResult:
    requirement: Requirements
    requirement_id: UUID
    status: VerificationStatus
    started_at: datetime
    finished_at: datetime
    elapsed_s: float
    start_url: str
    current_url: Optional[str]
    steps_taken: int
    run_dir: Path
    model_decision: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    interactions: List[Interaction] = field(default_factory=list)
    usage_total: Optional[Usage] = None

    def __repr__(self) -> str:
        status_value = self.status.name if hasattr(self.status, "name") else str(self.status)
        return (
            f"VerficationRunResult(requirement_id={self.requirement_id}, status={status_value}, "
            f"elapsed_s={self.elapsed_s:.2f}, start_url={self.start_url!r}, steps_taken={self.steps_taken}, "
            f"interactions={len(self.interactions)}, "
            f"error={self.error!r})"
        )

    def __str__(self) -> str:
        status_value = self.status.value if hasattr(self.status, "value") else str(self.status)
        line1 = f"Result: {status_value} in {self.elapsed_s:.2f}s (req={self.requirement_id}, turns={len(self.interactions)})"
        if self.error:
            line2 = f"Error: {self.error}"
        else:
            line2 = ""
        return "\n".join([line1, line2]) if line2 else line1
