from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class Inputs:
    """Container for user-provided input key/value pairs.

    Example: {
        "phone number": "555-123-4567",
        "email": "john.doe@example.org",
    }
    """

    key_value_mapping: Dict[str, str] = field(default_factory=dict)

    def add(self, key: str, value: str) -> None:
        """Add or update a key/value pair."""
        self.key_value_mapping[str(key)] = str(value)

    @staticmethod
    def create(initial: Optional[Dict[str, str]] = None) -> "Inputs":
        mapping: Dict[str, str] = {}
        if initial:
            mapping = {str(k): str(v) for k, v in initial.items()}
        return Inputs(key_value_mapping=mapping)


