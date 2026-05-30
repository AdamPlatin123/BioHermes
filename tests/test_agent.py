"""Comprehensive tests for agent layer: Judge, Planner, Executor, Verifier, Recovery, Core."""
import asyncio
import os
import pytest
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from biohermes.agent.judge import Judge
from biohermes.agent.planner import Planner
from biohermes.agent.executor import Executor
from biohermes.agent.verifier import Verifier
from biohermes.agent.recovery import Recovery
from biohermes.agent.core import BioHermesAgent
from biohermes.agent.models import (
    AgentSession, JudgeResult, TaskStep, VerifyResult, ToolCall, TaskStatus,
)
from biohermes.llm.client import LLMClient
from biohermes.pipeline.context import PipelineContext
from biohermes.tools import create_tools


# ─── Fixtures ───

@pytest.fixture
def context():
    return PipelineContext()


@pytest.fixture
def llm_client():
    return LLMClient(api_key="test", base_url="http://localhost:9999", model="test")


@pytest.fixture
def judge(llm_client):
    return Judge(llm_client)


@pytest.fixture
def planner(llm_client):
    return Planner(llm_client)


@pytest.fixture
def tools():
    return create_tools()


@pytest.fixture
def executor(tools):
    return Executor(tools)


@pytest.fixture
def verifier(llm_client):
    return Verifier(llm_client)


@pytest.fixture
def recovery():
    return Recovery(max_retries=2, base_delay=0.01)


@pytest.fixture
def session():
    return AgentSession(session_id="test_session", task="test task")


# ─── Judge Tests ───

class TestJudge:
    @pytest.mark.asyncio
    async def test_keyword_fallback_parse(self, judge):
        result = await judge.analyze("解析这个PDF文档")
        assert result.task_type == "parse"
        assert result.recommended_tools is not None
        assert len(result.recommended_tools) > 0

    @pytest.mark.asyncio
    async def test_keyword_fallback_batch(self, judge):
        result = await judge.analyze("批量处理所有文件")
        assert result.task_type == "batch"
        assert result.execution_strategy == "parallel"

    @pytest.mark.asyncio
    async def test_keyword_fallback_extract(self, judge):
        result = await judge.analyze("提取这份文档中的表格数据")
        assert result.task_type == "extract"
        assert "table_extract" in result.recommended_tools

    @pytest.mark.asyncio
    async def test_keyword_fallback_pipeline(self, judge):
        result = await judge.analyze("构建知识库pipeline")
        assert result.task_type == "pipeline"
        assert result.execution_strategy == "hybrid"

    @pytest.mark.asyncio
    async def test_keyword_features_formula(self, judge):
        result = await judge.analyze("解析含数学公式的学术论文")
        assert result.document_features.get("has_formulas") is True

    @pytest.mark.asyncio
    async def test_keyword_features_scan(self, judge):
        result = await judge.analyze("扫描图片中的文字")
        assert result.document_features.get("is_scan") is True

    @pytest.mark.asyncio
    async def test_keyword_features_multicolumn(self, judge):
        result = await judge.analyze("解析双栏学术论文")
        assert result.document_features.get("is_multicolumn") is True

    @pytest.mark.asyncio
    async def test_no_false_batch(self, judge):
        """'所有表格' should NOT trigger batch mode."""
        result = await judge.analyze("解析这份PDF文档，提取所有表格和结构化信息")
        assert result.task_type != "batch"

    @pytest.mark.asyncio
    async def test_rejudge_with_context(self, judge):
        prev = JudgeResult(task_type="extract", complexity="medium")
        result = await judge.analyze(
            "提取表格",
            previous_judge=prev,
            verify_errors=["Table consistency check failed"],
            failed_steps=["Step 1 (table_extract): No content"],
        )
        assert result is not None
        assert isinstance(result, JudgeResult)


# ─── Planner Tests ───

class TestPlanner:
    @pytest.mark.asyncio
    async def test_rule_plan_parse(self, planner):
        judge = JudgeResult(task_type="parse")
        steps = await planner.plan("解析文档", judge)
        assert len(steps) == 4
        assert steps[0].tool_name == "mineru_parse"
        assert steps[-1].tool_name == "report_generate"

    @pytest.mark.asyncio
    async def test_rule_plan_batch(self, planner):
        judge = JudgeResult(task_type="batch")
        steps = await planner.plan("批量处理", judge)
        assert len(steps) == 5
        assert steps[0].tool_name == "scan_files"

    @pytest.mark.asyncio
    async def test_rule_plan_extract(self, planner):
        judge = JudgeResult(task_type="extract")
        steps = await planner.plan("提取表格", judge)
        assert any(s.tool_name == "table_extract" for s in steps)

    @pytest.mark.asyncio
    async def test_rule_plan_pipeline(self, planner):
        judge = JudgeResult(task_type="pipeline")
        steps = await planner.plan("构建知识库", judge)
        assert len(steps) == 6

    @pytest.mark.asyncio
    async def test_replan_skips_failed_tools(self, planner):
        judge = JudgeResult(task_type="parse")
        failed = ["Step 1 (structure_extract): error", "Step 2 (table_extract): error"]
        steps = await planner.plan("解析文档", judge, failed_steps=failed)
        tool_names = [s.tool_name for s in steps]
        assert "structure_extract" not in tool_names
        assert "table_extract" not in tool_names
        assert "mineru_parse" in tool_names


# ─── Executor Tests ───

class TestExecutor:
    @pytest.mark.asyncio
    async def test_execute_step_success(self, executor, session, context):
        context.files = ["/home/zhidao-2/medgeclaw-migration/MedgeClaw/texput.pdf"]
        step = TaskStep(0, "Parse document", "mineru_parse", {"file_path": context.files[0]})
        result = await executor.execute_step(session, step, context)
        assert result is True
        assert step.status == "completed"

    @pytest.mark.asyncio
    async def test_execute_step_unknown_tool(self, executor, session, context):
        step = TaskStep(0, "Unknown", "nonexistent_tool", {})
        result = await executor.execute_step(session, step, context)
        assert result is False
        assert step.status == "failed"

    @pytest.mark.asyncio
    async def test_execute_no_file_path(self, executor, session, context):
        step = TaskStep(0, "Parse", "mineru_parse", {})
        result = await executor.execute_step(session, step, context)
        assert result is False

    @pytest.mark.asyncio
    async def test_execute_auto_file_from_context(self, executor, session, context):
        context.files = ["/home/zhidao-2/medgeclaw-migration/MedgeClaw/texput.pdf"]
        step = TaskStep(0, "Parse", "mineru_parse", {})
        result = await executor.execute_step(session, step, context)
        assert result is True

    @pytest.mark.asyncio
    async def test_scan_files_no_directory(self, executor, session, context):
        step = TaskStep(0, "Scan", "scan_files", {})
        result = await executor.execute_step(session, step, context)
        assert result is False  # No directory specified


# ─── Verifier Tests ───

class TestVerifier:
    @pytest.mark.asyncio
    async def test_verify_pass(self, verifier, session, context):
        context.add_parsed_result("test.pdf", {"content": "test"})
        session.steps = [
            TaskStep(0, "Step 0", "mineru_parse", status="completed", output={"content": "test"}),
        ]
        result = await verifier.verify(session, context)
        assert result.passed is True
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_verify_fail_empty_output(self, verifier, session, context):
        context.add_parsed_result("test.pdf", {"content": "test"})
        session.steps = [
            TaskStep(0, "Step 0", "mineru_parse", status="completed", output=None),
        ]
        result = await verifier.verify(session, context)
        assert result.passed is False
        assert any("no output" in e.lower() for e in result.errors)

    @pytest.mark.asyncio
    async def test_verify_table_consistency(self, verifier, session, context):
        context.tables = [{
            "headers": ["项目", "合计"],
            "rows": [["A", "100"], ["B", "200"], ["合计", "300"]],
            "row_count": 3, "col_count": 2,
        }]
        session.steps = [TaskStep(0, "Extract", "table_extract", status="completed", output={"tables": 1})]
        result = await verifier.verify(session, context)
        # 100 + 200 = 300, should pass
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_verify_table_inconsistency(self, verifier, session, context):
        context.tables = [{
            "headers": ["项目", "合计"],
            "rows": [["A", "100"], ["B", "200"], ["合计", "500"]],
            "row_count": 3, "col_count": 2,
        }]
        session.steps = [TaskStep(0, "Extract", "table_extract", status="completed", output={"tables": 1})]
        result = await verifier.verify(session, context)
        # 100 + 200 != 500, should have warnings
        assert any("total=500" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_verify_column_mismatch(self, verifier, session, context):
        context.tables = [{
            "headers": ["A", "B", "C"],
            "rows": [["1", "2"]],  # 2 cols vs 3 headers
            "row_count": 1, "col_count": 3,
        }]
        session.steps = [TaskStep(0, "Extract", "table_extract", status="completed", output={"tables": 1})]
        result = await verifier.verify(session, context)
        assert result.passed is False
        assert any("column mismatch" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_verify_skipped_step_ok(self, verifier, session, context):
        context.add_parsed_result("test.pdf", {"content": "x"})
        session.steps = [
            TaskStep(0, "Parse", "mineru_parse", status="completed", output={"content": "x"}),
            TaskStep(1, "Clean", "data_clean", status="skipped"),
        ]
        result = await verifier.verify(session, context)
        assert result.passed is True

    def test_parse_number(self):
        assert Verifier._parse_number("1,234.56") == 1234.56
        assert Verifier._parse_number("1234") == 1234.0
        assert Verifier._parse_number("abc") is None
        assert Verifier._parse_number(None) is None
        assert Verifier._parse_number("12，345") == 12345.0


# ─── Recovery Tests ───

class TestRecovery:
    @pytest.mark.asyncio
    async def test_recovery_skip_non_critical(self, recovery, session, context, executor):
        step = TaskStep(0, "Clean", "data_clean", status="failed", error="test error")
        session.retry_count = 3  # Exceed max retries
        result = await recovery.recover(session, step, context, executor)
        assert result is True
        assert step.status == "skipped"

    @pytest.mark.asyncio
    async def test_recovery_skip_table_extract(self, recovery, session, context, executor):
        step = TaskStep(1, "Extract tables", "table_extract", status="failed", error="No content")
        session.retry_count = 3
        result = await recovery.recover(session, step, context, executor)
        assert result is True
        assert step.status == "skipped"

    @pytest.mark.asyncio
    async def test_recovery_cannot_skip_critical(self, recovery, session, context, executor):
        step = TaskStep(0, "Parse", "mineru_parse", status="failed", error="timeout")
        session.retry_count = 3
        # No file to degrade to
        result = await recovery.recover(session, step, context, executor)
        assert result is False


# ─── Models Tests ───

class TestModels:
    def test_judge_result_to_dict(self):
        jr = JudgeResult(task_type="parse", complexity="simple", recommended_tools=["mineru_parse"])
        d = jr.to_dict()
        assert d["task_type"] == "parse"
        assert d["recommended_tools"] == ["mineru_parse"]

    def test_task_step_duration(self):
        step = TaskStep(0, "Test", start_time=100.0, end_time=105.5)
        assert step.duration() == 5.5

    def test_task_step_duration_zero(self):
        step = TaskStep(0, "Test")
        assert step.duration() == 0

    def test_session_duration(self):
        session = AgentSession(session_id="s1", task="t")
        session.finished_at = session.created_at + 10
        assert session.duration() == 10.0

    def test_verify_result_to_dict(self):
        vr = VerifyResult(passed=True, checks=[{"name": "c1", "passed": True}], warnings=[], errors=[])
        d = vr.to_dict()
        assert d["passed"] is True
        assert len(d["checks"]) == 1

    def test_session_to_dict(self):
        session = AgentSession(session_id="s1", task="test")
        d = session.to_dict()
        assert d["session_id"] == "s1"
        assert d["status"] == "pending"

    def test_tool_call_to_dict(self):
        tc = ToolCall(id="tc_0", name="parse", args={"file": "test.pdf"})
        d = tc.to_dict()
        assert d["name"] == "parse"


# ─── Core Integration Tests ───

class TestCoreIntegration:
    @pytest.mark.asyncio
    async def test_full_pipeline_with_real_file(self):
        pdf_path = "/home/zhidao-2/medgeclaw-migration/MedgeClaw/texput.pdf"
        if not os.path.exists(pdf_path):
            pytest.skip("Test PDF not available")

        agent = BioHermesAgent()
        session = await agent.run(f"解析 {pdf_path}，提取所有表格和结构化信息")

        # Either completed or failed (empty PDF may cause table_extract to fail after recovery)
        assert session.status in (TaskStatus.COMPLETED, TaskStatus.FAILED)
        assert session.judge_result is not None
        assert len(session.steps) > 0
        assert session.result is not None or session.error is not None

    @pytest.mark.asyncio
    async def test_full_pipeline_nonexistent_file(self):
        agent = BioHermesAgent()
        session = await agent.run("解析 /nonexistent/file.pdf")

        # Should still judge and plan, but execution will fail
        assert session.judge_result is not None
        assert session.status in (TaskStatus.COMPLETED, TaskStatus.FAILED)

    @pytest.mark.asyncio
    async def test_session_events_recorded(self):
        pdf_path = "/home/zhidao-2/medgeclaw-migration/MedgeClaw/texput.pdf"
        if not os.path.exists(pdf_path):
            pytest.skip("Test PDF not available")

        agent = BioHermesAgent()
        session = await agent.run(f"解析 {pdf_path}")

        event_types = [m["event"] for m in session.messages]
        assert "judging" in event_types
        assert "judge_complete" in event_types
        assert "plan_ready" in event_types
        assert "task_complete" in event_types

    @pytest.mark.asyncio
    async def test_session_memory_eviction(self):
        agent = BioHermesAgent()
        agent._max_sessions = 3
        for i in range(5):
            sid = f"session_{i}"
            agent.sessions[sid] = AgentSession(session_id=sid, task="t")
        agent._evict_sessions()
        assert len(agent.sessions) <= 3
