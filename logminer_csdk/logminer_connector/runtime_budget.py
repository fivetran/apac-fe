"""Finite invocation budget."""

import time
from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeBudget:
    started_at: float
    maximum_seconds: int
    safety_seconds: int = 15

    @classmethod
    def start(cls, maximum_seconds: int) -> "RuntimeBudget":
        return cls(started_at=time.monotonic(), maximum_seconds=maximum_seconds)

    def elapsed_seconds(self) -> float:
        return time.monotonic() - self.started_at

    def nearly_exhausted(self) -> bool:
        return self.elapsed_seconds() >= max(
            0, self.maximum_seconds - self.safety_seconds
        )

    def require_time(self) -> None:
        from errors import InvocationBudgetExceededError

        if self.nearly_exhausted():
            raise InvocationBudgetExceededError(
                "Invocation budget exhausted; uncheckpointed work will replay"
            )
