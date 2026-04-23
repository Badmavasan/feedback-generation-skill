"""TraceCollector — captures every agent step during a generation run."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TraceEvent:
    step_number: int
    agent: str          # orchestrator | mistral | claude_relevance | mistral_simulator | gemini
    role: str           # planning | generation | evaluation | relevance | simulation | assembly | image
    tool_name: str | None
    characteristic: str | None
    attempt: int | None
    verdict: str | None     # passed | failed | regenerating | accepted | rejected
    notes: str | None       # Claude critique / reasoning text
    input_data: Any
    output_data: Any
    duration_ms: int


class TraceCollector:
    """
    Collects ordered trace events for one generation run.
    Thread-unsafe by design — one instance per request.
    """

    def __init__(self) -> None:
        self._events: list[TraceEvent] = []
        self._step = 0
        self._timers: dict[str, float] = {}

    # ── Timer helpers ──────────────────────────────────────────────────────────

    def start_timer(self, key: str) -> None:
        self._timers[key] = time.monotonic()

    def elapsed_ms(self, key: str) -> int:
        start = self._timers.pop(key, None)
        if start is None:
            return 0
        return int((time.monotonic() - start) * 1000)

    # ── Logging ───────────────────────────────────────────────────────────────

    def log(
        self,
        agent: str,
        role: str,
        *,
        tool_name: str | None = None,
        characteristic: str | None = None,
        attempt: int | None = None,
        verdict: str | None = None,
        notes: str | None = None,
        input_data: Any = None,
        output_data: Any = None,
        duration_ms: int = 0,
    ) -> None:
        self._step += 1
        self._events.append(TraceEvent(
            step_number=self._step,
            agent=agent,
            role=role,
            tool_name=tool_name,
            characteristic=characteristic,
            attempt=attempt,
            verdict=verdict,
            notes=notes,
            input_data=input_data,
            output_data=output_data,
            duration_ms=duration_ms,
        ))

    # ── Access ────────────────────────────────────────────────────────────────

    @property
    def events(self) -> list[TraceEvent]:
        return list(self._events)

    @property
    def total_iterations(self) -> int:
        """Count all generation attempts across all characteristics."""
        return sum(
            1 for e in self._events
            if e.tool_name == "generate_text_feedback" or e.role == "generation"
        )

    def to_dicts(self) -> list[dict]:
        result = []
        for e in self._events:
            result.append({
                "step_number": e.step_number,
                "agent": e.agent,
                "role": e.role,
                "tool_name": e.tool_name,
                "characteristic": e.characteristic,
                "attempt": e.attempt,
                "verdict": e.verdict,
                "notes": e.notes,
                "input_data": e.input_data,
                "output_data": e.output_data,
                "duration_ms": e.duration_ms,
            })
        return result
