from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Union
from uuid import UUID, uuid4


class RequirementsPriority(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


from .acceptance_criterion import AcceptanceCriterion, AcceptanceState


@dataclass
class Requirements:
    id: UUID
    created_at: datetime
    title: str
    description: str
    source: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    acceptance_criteria: List[AcceptanceCriterion] = field(default_factory=list)
    priority: RequirementsPriority = RequirementsPriority.MEDIUM
    metadata: Optional[Dict[str, Any]] = None

    @staticmethod
    def _normalize_acceptance(
        acceptance: Optional[Sequence[Union[str, Dict[str, Any], AcceptanceCriterion]]]
    ) -> List[AcceptanceCriterion]:
        if not acceptance:
            return []
        result: List[AcceptanceCriterion] = []
        index = 1
        for item in acceptance:
            if isinstance(item, AcceptanceCriterion):
                result.append(item)
                index += 1
                continue
            if isinstance(item, str):
                name = f"AC-{index}"
                result.append(AcceptanceCriterion.create(name=name, text=item))
                index += 1
                continue
            if isinstance(item, dict):
                # Try to coerce dicts, supporting a few legacy keys
                text = str(
                    item.get("text")
                    or item.get("criteria")
                    or item.get("criterion")
                    or item.get("description")
                    or item.get("name")
                    or ""
                )
                name = str(item.get("name") or f"AC-{index}")
                state = item.get("state")
                # If complete structure provided, try to respect it
                if item.get("id") and item.get("created_at") and text:
                    try:
                        crit_id = item["id"] if isinstance(item["id"], UUID) else UUID(str(item["id"]))
                    except Exception:
                        crit_id = uuid4()
                    try:
                        created_at_raw = str(item["created_at"]).replace("Z", "+00:00")
                        created_at = datetime.fromisoformat(created_at_raw)
                    except Exception:
                        created_at = datetime.now(timezone.utc)
                    if isinstance(state, str):
                        try:
                            state_val = AcceptanceState(state)
                        except Exception:
                            state_val = AcceptanceState.UNPROCESSED
                    elif isinstance(state, AcceptanceState):
                        state_val = state
                    else:
                        state_val = AcceptanceState.UNPROCESSED
                    result.append(
                        AcceptanceCriterion(
                            id=crit_id,
                            created_at=created_at,
                            name=name,
                            text=text,
                            state=state_val,
                        )
                    )
                else:
                    result.append(AcceptanceCriterion.create(name=name, text=text, state=state))
                index += 1
                continue
        return result

    @staticmethod
    def create(
        title: str,
        description: str,
        source: Optional[str] = None,
        tags: Optional[List[str]] = None,
        acceptance_criteria: Optional[Sequence[Union[str, Dict[str, Any], AcceptanceCriterion]]] = None,
        priority: RequirementsPriority = RequirementsPriority.MEDIUM,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "Requirements":
        return Requirements(
            id=uuid4(),
            created_at=datetime.now(timezone.utc),
            title=title,
            description=description,
            source=source,
            tags=tags or [],
            acceptance_criteria=Requirements._normalize_acceptance(acceptance_criteria),
            priority=priority,
            metadata=metadata,
        )

    def __repr__(self) -> str:
        return (
            f"Requirements(id={self.id}, title={self.title!r}, "
            f"created_at={self.created_at.isoformat()}, priority={self.priority.name}, "
            f"tags={len(self.tags)}, acceptance_criteria={len(self.acceptance_criteria)})"
        )

    def __str__(self) -> str:
        tags_str = ", ".join(self.tags) if self.tags else "None"
        criteria_str = (
            "\n".join(f"  - {c.text}" for c in self.acceptance_criteria)
            if self.acceptance_criteria
            else "  None"
        )
        source_str = self.source if self.source else "Not specified"
        metadata_str = str(self.metadata) if self.metadata else "None"
        
        return (
            f"[{self.priority.name}] {self.title} (ID: {self.id})\n"
            f"Created: {self.created_at.isoformat()}\n"
            f"Source: {source_str}\n"
            f"Description: {self.description}\n"
            f"Tags: {tags_str}\n"
            f"Acceptance Criteria:\n{criteria_str}\n"
            f"Metadata: {metadata_str}"
        )
