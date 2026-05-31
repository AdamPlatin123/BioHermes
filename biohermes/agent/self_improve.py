"""Self-improve module: learns from execution history to optimize future decisions."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .models import AgentSession, TaskStatus
from ..pipeline.context import PipelineContext

logger = logging.getLogger("biohermes.agent")

DEFAULT_TOOL_TIMEOUT = 300.0


@dataclass
class ToolMetrics:
    success_count: int = 0
    failure_count: int = 0
    total_duration: float = 0.0

    @property
    def total_calls(self) -> int:
        return self.success_count + self.failure_count

    @property
    def success_rate(self) -> float:
        return self.success_count / self.total_calls if self.total_calls > 0 else 0.0

    @property
    def avg_duration(self) -> float:
        return self.total_duration / self.total_calls if self.total_calls > 0 else 0.0

    def to_dict(self) -> dict:
        return {
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "total_duration": round(self.total_duration, 2),
        }

    @classmethod
    def from_dict(cls, d: dict) -> ToolMetrics:
        return cls(
            success_count=d.get("success_count", 0),
            failure_count=d.get("failure_count", 0),
            total_duration=d.get("total_duration", 0.0),
        )


class SelfImprove:
    """Learns from execution history across sessions to optimize future decisions."""

    def __init__(self, metrics_path: str = "logs/metrics.json"):
        self.metrics_path = metrics_path
        # {tool_name: {task_type: ToolMetrics}}
        self.tool_metrics: dict[str, dict[str, ToolMetrics]] = {}
        # Judge accuracy per task type
        self.judge_accuracy: dict[str, int] = {}
        self.judge_total: dict[str, int] = {}
        self.session_count: int = 0
        self._load()

    def learn(self, session: AgentSession, context: PipelineContext):
        """Extract learning data from a completed session."""
        self.session_count += 1
        task_type = session.judge_result.task_type if session.judge_result else "unknown"

        for step in session.steps:
            if not step.tool_name:
                continue
            task_metrics = self.tool_metrics.setdefault(step.tool_name, {})
            metrics = task_metrics.setdefault(task_type, ToolMetrics())

            if step.status in ("completed", "completed_fallback"):
                metrics.success_count += 1
            elif step.status in ("failed",):
                metrics.failure_count += 1
            else:
                continue

            metrics.total_duration += step.duration()

        if session.judge_result:
            tt = session.judge_result.task_type
            self.judge_total[tt] = self.judge_total.get(tt, 0) + 1
            if session.status == TaskStatus.COMPLETED:
                self.judge_accuracy[tt] = self.judge_accuracy.get(tt, 0) + 1

        self._save()
        logger.info(f"SelfImprove: learned from session {session.session_id} (total: {self.session_count})")

    def get_tool_insights(self, task_type: str) -> dict[str, float]:
        """Get tool success rates for a given task type."""
        insights = {}
        for tool_name, task_map in self.tool_metrics.items():
            metrics = task_map.get(task_type)
            if metrics and metrics.total_calls >= 1:
                insights[tool_name] = round(metrics.success_rate, 3)
        return insights

    def get_judge_insights(self) -> dict[str, float]:
        """Get judge accuracy per task type."""
        result = {}
        for tt, total in self.judge_total.items():
            correct = self.judge_accuracy.get(tt, 0)
            result[tt] = round(correct / total, 3) if total > 0 else 0.0
        return result

    def suggest_timeout(self, tool_name: str, fallback: float = DEFAULT_TOOL_TIMEOUT) -> float:
        """Suggest timeout based on historical avg_duration * 3 (approx p95)."""
        task_map = self.tool_metrics.get(tool_name, {})
        if not task_map:
            return fallback

        total_duration = 0.0
        total_calls = 0
        for metrics in task_map.values():
            total_duration += metrics.total_duration
            total_calls += metrics.total_calls

        if total_calls == 0:
            return fallback

        avg = total_duration / total_calls
        # Use avg * 3 as rough p95 estimate, with floor of 10s and cap at fallback
        suggested = max(10.0, min(avg * 3.0, fallback))
        return round(suggested, 1)

    def get_all_metrics_summary(self) -> dict:
        """Get a summary of all collected metrics."""
        return {
            "session_count": self.session_count,
            "tool_metrics": {
                tool: {tt: m.to_dict() for tt, m in task_map.items()}
                for tool, task_map in self.tool_metrics.items()
            },
            "judge_accuracy": self.get_judge_insights(),
        }

    def _load(self):
        """Load metrics from JSON file."""
        path = Path(self.metrics_path)
        if not path.exists():
            return

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.session_count = data.get("session_count", 0)
            self.judge_accuracy = data.get("judge_accuracy", {})
            self.judge_total = data.get("judge_total", {})

            for tool_name, task_map in data.get("tool_metrics", {}).items():
                self.tool_metrics[tool_name] = {}
                for tt, m_dict in task_map.items():
                    self.tool_metrics[tool_name][tt] = ToolMetrics.from_dict(m_dict)

            logger.debug(f"SelfImprove: loaded metrics from {self.metrics_path} ({self.session_count} sessions)")
        except Exception as e:
            logger.warning(f"SelfImprove: failed to load metrics: {e}")

    def _save(self):
        """Persist metrics to JSON file."""
        try:
            path = Path(self.metrics_path)
            path.parent.mkdir(parents=True, exist_ok=True)

            data = {
                "session_count": self.session_count,
                "tool_metrics": {
                    tool: {tt: m.to_dict() for tt, m in task_map.items()}
                    for tool, task_map in self.tool_metrics.items()
                },
                "judge_accuracy": self.judge_accuracy,
                "judge_total": self.judge_total,
            }
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            logger.warning(f"SelfImprove: failed to save metrics: {e}")
