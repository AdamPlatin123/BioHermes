"""Tests for self_improve module: learning, insights, timeout suggestion, persistence."""
import json
import os
import tempfile
import pytest
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from biohermes.agent.self_improve import SelfImprove, ToolMetrics, DEFAULT_TOOL_TIMEOUT
from biohermes.agent.models import AgentSession, TaskStep, TaskStatus, JudgeResult


@pytest.fixture
def metrics_file(tmp_path):
    return str(tmp_path / "metrics.json")


@pytest.fixture
def si(metrics_file):
    return SelfImprove(metrics_path=metrics_file)


def _make_session(task_type="parse", status=TaskStatus.COMPLETED, steps=None):
    session = AgentSession(session_id="test", task="test task")
    session.judge_result = JudgeResult(task_type=task_type)
    session.status = status
    if steps:
        session.steps = steps
    return session


class TestToolMetrics:
    def test_success_rate(self):
        tm = ToolMetrics(success_count=8, failure_count=2)
        assert tm.success_rate == 0.8
        assert tm.total_calls == 10

    def test_avg_duration(self):
        tm = ToolMetrics(success_count=4, total_duration=20.0)
        assert tm.avg_duration == 5.0

    def test_empty_metrics(self):
        tm = ToolMetrics()
        assert tm.success_rate == 0.0
        assert tm.avg_duration == 0.0
        assert tm.total_calls == 0

    def test_serialization(self):
        tm = ToolMetrics(success_count=5, failure_count=1, total_duration=30.0)
        d = tm.to_dict()
        restored = ToolMetrics.from_dict(d)
        assert restored.success_count == 5
        assert restored.failure_count == 1
        assert restored.total_duration == 30.0


class TestSelfImproveLearn:
    def test_learn_extracts_tool_metrics(self, si):
        steps = [
            TaskStep(0, "Parse", "mineru_parse", status="completed",
                     start_time=100.0, end_time=110.0),
            TaskStep(1, "Extract", "table_extract", status="failed",
                     start_time=110.0, end_time=115.0),
        ]
        session = _make_session(steps=steps)
        si.learn(session, None)

        assert si.session_count == 1
        assert si.tool_metrics["mineru_parse"]["parse"].success_count == 1
        assert si.tool_metrics["table_extract"]["parse"].failure_count == 1

    def test_learn_judge_accuracy(self, si):
        session = _make_session(status=TaskStatus.COMPLETED)
        si.learn(session, None)

        assert si.judge_total["parse"] == 1
        assert si.judge_accuracy["parse"] == 1

    def test_learn_failed_session(self, si):
        session = _make_session(status=TaskStatus.FAILED)
        si.learn(session, None)

        assert si.judge_total["parse"] == 1
        assert si.judge_accuracy.get("parse", 0) == 0

    def test_learn_skips_no_tool_steps(self, si):
        steps = [TaskStep(0, "No tool", "", status="completed")]
        session = _make_session(steps=steps)
        si.learn(session, None)
        assert si.session_count == 1
        assert len(si.tool_metrics) == 0

    def test_learn_accumulates(self, si):
        for i in range(3):
            steps = [
                TaskStep(0, "Parse", "mineru_parse", status="completed",
                         start_time=100.0, end_time=110.0),
            ]
            session = _make_session(steps=steps)
            si.learn(session, None)

        assert si.tool_metrics["mineru_parse"]["parse"].success_count == 3
        assert si.session_count == 3


class TestSelfImproveInsights:
    def test_tool_insights_with_data(self, si):
        steps = [
            TaskStep(0, "Parse", "mineru_parse", status="completed"),
            TaskStep(1, "Extract", "table_extract", status="failed"),
        ]
        session = _make_session(steps=steps)
        si.learn(session, None)

        insights = si.get_tool_insights("parse")
        assert insights["mineru_parse"] == 1.0
        assert insights["table_extract"] == 0.0

    def test_tool_insights_cold_start(self, si):
        insights = si.get_tool_insights("parse")
        assert insights == {}

    def test_judge_insights(self, si):
        session = _make_session(status=TaskStatus.COMPLETED)
        si.learn(session, None)

        insights = si.get_judge_insights()
        assert insights["parse"] == 1.0

    def test_judge_insights_mixed(self, si):
        session1 = _make_session(status=TaskStatus.COMPLETED)
        si.learn(session1, None)
        session2 = _make_session(status=TaskStatus.FAILED)
        si.learn(session2, None)

        insights = si.get_judge_insights()
        assert insights["parse"] == 0.5


class TestSelfImproveTimeout:
    def test_suggest_timeout_with_history(self, si):
        steps = [
            TaskStep(0, "Parse", "mineru_parse", status="completed",
                     start_time=100.0, end_time=110.0),
        ]
        session = _make_session(steps=steps)
        si.learn(session, None)

        timeout = si.suggest_timeout("mineru_parse")
        # avg=10, *3 = 30
        assert timeout == 30.0

    def test_suggest_timeout_cold_start(self, si):
        timeout = si.suggest_timeout("unknown_tool")
        assert timeout == DEFAULT_TOOL_TIMEOUT

    def test_suggest_timeout_floor(self, si):
        steps = [
            TaskStep(0, "Fast", "fast_tool", status="completed",
                     start_time=100.0, end_time=101.0),
        ]
        session = _make_session(steps=steps)
        si.learn(session, None)

        timeout = si.suggest_timeout("fast_tool")
        # avg=1, *3=3, but floor is 10
        assert timeout == 10.0


class TestSelfImprovePersistence:
    def test_save_and_load(self, metrics_file):
        si1 = SelfImprove(metrics_path=metrics_file)
        steps = [
            TaskStep(0, "Parse", "mineru_parse", status="completed",
                     start_time=100.0, end_time=110.0),
        ]
        session = _make_session(steps=steps)
        si1.learn(session, None)

        # Load from same file
        si2 = SelfImprove(metrics_path=metrics_file)
        assert si2.session_count == 1
        assert si2.tool_metrics["mineru_parse"]["parse"].success_count == 1

    def test_cold_start_missing_file(self, tmp_path):
        si = SelfImprove(metrics_path=str(tmp_path / "nonexistent.json"))
        assert si.session_count == 0
        assert si.get_tool_insights("parse") == {}

    def test_cold_start_corrupt_file(self, metrics_file):
        with open(metrics_file, "w") as f:
            f.write("not valid json{{{")

        si = SelfImprove(metrics_path=metrics_file)
        assert si.session_count == 0  # Graceful degradation

    def test_metrics_summary(self, si):
        steps = [
            TaskStep(0, "Parse", "mineru_parse", status="completed",
                     start_time=100.0, end_time=110.0),
        ]
        session = _make_session(steps=steps)
        si.learn(session, None)

        summary = si.get_all_metrics_summary()
        assert summary["session_count"] == 1
        assert "mineru_parse" in summary["tool_metrics"]
        assert "parse" in summary["judge_accuracy"]
