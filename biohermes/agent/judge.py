"""Judge layer: LLM-powered task analysis."""
from __future__ import annotations

import logging
from .models import JudgeResult
from ..llm.client import LLMClient
from ..llm.prompts import JUDGE_SYSTEM, JUDGE_USER
from ..tools import TOOL_REGISTRY

logger = logging.getLogger("biohermes.agent")


class Judge:
    """Analyzes user task to determine type, complexity, and optimal strategy."""

    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def analyze(self, task: str) -> JudgeResult:
        """Judge the task using LLM, with keyword fallback."""
        tools_desc = self._tools_description()

        if self.llm.available:
            try:
                result = self.llm.chat_json(
                    JUDGE_SYSTEM,
                    JUDGE_USER.format(task=task, tools=tools_desc),
                )
                return JudgeResult(
                    task_type=result.get("task_type", "parse"),
                    complexity=result.get("complexity", "simple"),
                    document_features=result.get("document_features", {}),
                    recommended_tools=result.get("recommended_tools", []),
                    execution_strategy=result.get("execution_strategy", "sequential"),
                    risk_factors=result.get("risk_factors", []),
                    fallback_plan=result.get("fallback_plan", ""),
                    raw_response=str(result),
                )
            except Exception as e:
                logger.warning(f"LLM judge failed, using fallback: {e}")

        return self._keyword_fallback(task)

    def _keyword_fallback(self, task: str) -> JudgeResult:
        """Keyword-based fallback when LLM is unavailable."""
        t = task.lower()
        features = {}
        tools = []
        strategy = "sequential"

        # Batch requires explicit multi-file context
        if any(kw in t for kw in ["批量", "batch", "多个文件", "所有文件", "目录下"]):
            task_type = "batch"
            tools = ["mineru_parse", "table_extract", "structure_extract", "data_clean", "report_generate"]
            strategy = "parallel"
        elif any(kw in t for kw in ["表格", "table", "报表", "财务"]):
            task_type = "extract"
            tools = ["mineru_parse", "table_extract", "data_clean", "report_generate"]
            features["has_tables"] = True
        elif any(kw in t for kw in ["知识库", "pipeline", "流水线", "索引"]):
            task_type = "pipeline"
            tools = ["mineru_parse", "structure_extract", "table_extract", "data_clean", "report_generate"]
            strategy = "hybrid"
        else:
            task_type = "parse"
            tools = ["mineru_parse", "structure_extract", "table_extract", "report_generate"]

        if any(kw in t for kw in ["公式", "formula", "数学", "latex"]):
            features["has_formulas"] = True
        if any(kw in t for kw in ["扫描", "scan", "图片", "image"]):
            features["is_scan"] = True
        if any(kw in t for kw in ["双栏", "多栏", "学术论文", "paper"]):
            features["is_multicolumn"] = True

        return JudgeResult(
            task_type=task_type, complexity="medium" if len(tools) > 3 else "simple",
            document_features=features, recommended_tools=tools,
            execution_strategy=strategy, risk_factors=[],
            fallback_plan="Use PyMuPDF if MinerU unavailable",
        )

    def _tools_description(self) -> str:
        lines = []
        for name, cls in TOOL_REGISTRY.items():
            lines.append(f"- {name}: {cls.description}")
        return "\n".join(lines)
