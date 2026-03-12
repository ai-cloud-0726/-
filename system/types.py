from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class TaskStatus(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    BLOCKED = "blocked"
    NEED_RESTART = "need_restart"
    RUNNING = "running"


@dataclass
class Action:
    kind: str
    name: str
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RoundEvaluation:
    success: bool
    reason: str
    next_step: str
    need_restart: bool = False


@dataclass
class ErrorRecord:
    failed_method: str
    failed_reason: str
    error_type: str
    related_output: str
    round_index: int
    timestamp: str


@dataclass
class PatchRequest:
    request_id: str
    target_file: str
    reason: str
    new_content: str


@dataclass
class ClawResult:
    status: TaskStatus
    message: str
    rounds: int
    patch_requests: List[PatchRequest] = field(default_factory=list)
    carried_context: Dict[str, Any] = field(default_factory=dict)
    final_output: Optional[str] = None
