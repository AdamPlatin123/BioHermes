"""BioHermes Agent data models."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class TaskStatus(str, Enum):
    PENDING = "pending"
    JUDGING = "judging"
    PLANNING = "planning"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    RECOVERING = "recovering"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict
    status: str = "pending"
    result: Any = None
    error: Optional[str] = None
    start_time: float = 0
    end_time: float = 0

    def duration(self):
        if self.end_time and self.start_time:
            return round(self.end_time - self.start_time, 2)
        return 0

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "args": self.args,
            "status": self.status, "duration": self.duration(),
            "error": self.error,
        }


@dataclass
class TaskStep:
    index: int
    description: str
    tool_name: str = ""
    tool_args: dict = field(default_factory=dict)
    tool_calls: list[ToolCall] = field(default_factory=list)
    status: str = "pending"
    output: Any = None
    error: Optional[str] = None
    start_time: float = 0
    end_time: float = 0

    def duration(self):
        if self.end_time and self.start_time:
            return round(self.end_time - self.start_time, 2)
        return 0

    def to_dict(self):
        return {
            "index": self.index, "description": self.description,
            "tool_name": self.tool_name, "status": self.status,
            "duration": self.duration(),
            "tool_calls": [tc.to_dict() for tc in self.tool_calls],
            "output": str(self.output)[:500] if self.output else None,
            "error": self.error,
        }


@dataclass
class JudgeResult:
    task_type: str = "parse"
    complexity: str = "simple"
    document_features: dict = field(default_factory=dict)
    recommended_tools: list[str] = field(default_factory=list)
    execution_strategy: str = "sequential"
    risk_factors: list[str] = field(default_factory=list)
    fallback_plan: str = ""
    raw_response: str = ""

    def to_dict(self):
        return {
            "task_type": self.task_type, "complexity": self.complexity,
            "recommended_tools": self.recommended_tools,
            "execution_strategy": self.execution_strategy,
            "risk_factors": self.risk_factors,
        }


@dataclass
class VerifyResult:
    passed: bool = True
    level: str = "format"
    checks: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self):
        return {
            "passed": self.passed, "level": self.level,
            "warnings": self.warnings, "errors": self.errors,
            "checks": self.checks,
        }


@dataclass
class AgentSession:
    session_id: str
    task: str
    status: TaskStatus = TaskStatus.PENDING
    judge_result: Optional[JudgeResult] = None
    steps: list[TaskStep] = field(default_factory=list)
    verify_result: Optional[VerifyResult] = None
    messages: list[dict] = field(default_factory=list)
    result: Optional[str] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    retry_count: int = 0

    def duration(self):
        end = self.finished_at or time.time()
        return round(end - self.created_at, 1)

    def add_event(self, event_type: str, data: dict):
        self.messages.append({"event": event_type, "data": data, "ts": time.time()})

    def to_dict(self):
        return {
            "session_id": self.session_id, "task": self.task,
            "status": self.status.value,
            "judge_result": self.judge_result.to_dict() if self.judge_result else None,
            "steps": [s.to_dict() for s in self.steps],
            "verify_result": self.verify_result.to_dict() if self.verify_result else None,
            "result": self.result, "error": self.error,
            "duration": self.duration(), "retry_count": self.retry_count,
        }
