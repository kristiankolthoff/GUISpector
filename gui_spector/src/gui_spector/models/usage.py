from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class Usage:
    tokens_in: int
    tokens_out: int
    tokens_reasoning: int
    tokens_total: int

    def add(self, other: "Usage") -> "Usage":
        return Usage(
            tokens_in=self.tokens_in + other.tokens_in,
            tokens_out=self.tokens_out + other.tokens_out,
            tokens_reasoning=self.tokens_reasoning + other.tokens_reasoning,
            tokens_total=self.tokens_total + other.tokens_total,
        )

    @staticmethod
    def sum(usages: List["Usage"]) -> "Usage":
        total = Usage(0, 0, 0, 0)
        for u in usages:
            total = total.add(u)
        return total

    def to_dict(self) -> dict:
        return {
            "input_tokens": self.tokens_in,
            "output_tokens": self.tokens_out,
            "reasoning_tokens": self.tokens_reasoning,
            "total_tokens": self.tokens_total,
        }

    def __repr__(self) -> str:
        return (
            f"Usage(in={self.tokens_in}, out={self.tokens_out}, "
            f"reasoning={self.tokens_reasoning}, total={self.tokens_total})"
        )

    def __str__(self) -> str:
        return (
            f"tokens: in={self.tokens_in}, out={self.tokens_out}, "
            f"reasoning={self.tokens_reasoning}, total={self.tokens_total}"
        )
