from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class TaskStatus(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    BLOCKED = "blocked"
    RESTART_REQUIRED = "restart_required"
    RUNNING = "running"


class ErrorType(str, Enum):
    COMMAND = "command"
    EVALUATION = "evaluation"
    PLANNING = "planning"
    MODEL = "model"
    PATCH = "patch"
    OTHER = "other"


@dataclass
class ErrorMemoryEntry:
    method: str
    reason: str
    error_type: ErrorType
    related_output: str
    round_index: int
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class StepRecord:
    round_index: int
    goal: str
    action: str
    result: str
    evaluation: Dict[str, Any]
    errors: List[ErrorMemoryEntry] = field(default_factory=list)
    improvement_request: Optional[Dict[str, Any]] = None
    patch_applied: Optional[Dict[str, Any]] = None
    restart_info: Optional[Dict[str, Any]] = None


@dataclass
class RuntimeState:
    session_id: str
    goal: str
    max_steps: int
    step_count: int = 0
    restart_count: int = 0
    recursion_count: int = 0
    status: TaskStatus = TaskStatus.RUNNING
    history_actions: List[Dict[str, Any]] = field(default_factory=list)
    command_history: List[str] = field(default_factory=list)
    planned_steps: List[str] = field(default_factory=list)
    last_result: str = ""


@dataclass
class ClawInput:
    goal: str
    context: Dict[str, Any]
    state: RuntimeState
    error_memory: List[ErrorMemoryEntry]


@dataclass
class ClawOutput:
    status: TaskStatus
    state: RuntimeState
    steps: List[StepRecord]
    patch_requests: List[Dict[str, Any]]
    error_memory: List[ErrorMemoryEntry]
    restart_payload: Optional[Dict[str, Any]] = None
