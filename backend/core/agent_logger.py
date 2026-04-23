"""File-based prompt logger — writes every agent prompt to /app/logs/agents.log."""
from __future__ import annotations

import logging
import os
from pathlib import Path

_LOG_DIR = Path(os.getenv("AGENT_LOG_DIR", "/app/logs"))
_LOG_DIR.mkdir(parents=True, exist_ok=True)

_file_logger = logging.getLogger("agent_prompts")
_file_logger.setLevel(logging.DEBUG)
_file_logger.propagate = False

if not _file_logger.handlers:
    _handler = logging.FileHandler(_LOG_DIR / "agents.log", encoding="utf-8")
    _handler.setFormatter(logging.Formatter("%(asctime)s\n%(message)s"))
    _file_logger.addHandler(_handler)

_SEP = "=" * 80
_DIV = "-" * 60


def log_prompt(
    run_id: str | None,
    agent: str,
    user: str,
    system: str | None = None,
    extra: str | None = None,
) -> None:
    """Write a full prompt (system + user) to the agent log file."""
    rid = run_id or "unknown"
    parts = [
        _SEP,
        f"RUN: {rid}  |  AGENT: {agent}",
        _SEP,
    ]
    if system:
        parts += [_DIV + "  SYSTEM  " + _DIV, system.strip(), ""]
    parts += [_DIV + "  USER  " + _DIV, user.strip()]
    if extra:
        parts += ["", _DIV + "  EXTRA  " + _DIV, extra.strip()]
    parts.append(_SEP + "\n")
    _file_logger.info("\n".join(parts))
