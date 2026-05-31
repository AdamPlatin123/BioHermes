"""Judge layer: LLM-powered task analysis."""
from __future__ import annotations

import logging
from .models import JudgeResult
from ..llm.client import LLMClient
from typing import Optional, TYPE_CHECKING
if TYPE_CHECKING:
    from .self_improve import SelfImprove
from ..llm.prompts import JUDGE_SYSTEM, JUDGE_USER
from ..tools import TOOL_REGISTRY

logger = logging.getLogger("biohermes.agent")


class Judge:
    """Analyzes user task to determine type, complexity, and optimal strategy."""

    def __init__(self, llm: LLMClient, self_improve: Optional[SelfImprove] = None):
        self.llm = llm
        self.self_improve = self_improve

    async def analyze(self, task: str,
                      previous_judge: Optional[JudgeResult] = None,
                      verify_errors: Optional[list[str]] = None,
                      failed_steps: Optional[list[str]] = None) -> JudgeResult:
        """Judge the task using LLM, with keyword fallback.

        On re-judge (verify failure loop), receives structured context from
        the previous iteration so LLM can adjust its assessment.
        """
        tools_desc = self._tools_description()

        if self.llm.available:
            try:
                user_prompt = JUDGE_USER.format(task=task, tools=tools_desc)

                # Attach re-judge context for iterative correction
                if verify_errors or failed_steps:
                    context_parts = []
                    if previous_judge:
                        context_parts.append(
                            f"[Previous judge assessment] type={previous_judge.task_type}, "
                            f"complexity={previous_judge.complexity}, "
                            f"tools={previous_judge.recommended_tools}"
                        )
                    if verify_errors:
                        context_parts.append(
                            f"[Verification errors] {'; '.join(verify_errors)}"
                        )
                    if failed_steps:
                        context_parts.append(
                            f"[Failed steps] {'; '.join(failed_steps)}"
                        )
                    user_prompt += "\n\n" + "\n".join(context_parts)

                result = self.llm.chat_json(JUDGE_SYSTEM, user_prompt)
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

        # Apply self-improve insights: reorder tools by historical success rate
        risk_factors = []
        if self.self_improve:
            insights = self.self_improve.get_tool_insights(task_type)
            if insights:
                tools = sorted(tools, key=lambda t: insights.get(t, 0.5), reverse=True)
                low_rate_tools = [t for t in tools if insights.get(t, 1.0) < 0.5]
                if low_rate_tools:
                    risk_factors.append(f"Low historical success: {', '.join(low_rate_tools)}")

        return JudgeResult(
            task_type=task_type, complexity="medium" if len(tools) > 3 else "simple",
            document_features=features, recommended_tools=tools,
            execution_strategy=strategy, risk_factors=risk_factors,
            fallback_plan="Use PyMuPDF if MinerU unavailable",
        )

    def _tools_description(self) -> str:
        lines = []
        for name, cls in TOOL_REGISTRY.items():
            lines.append(f"- {name}: {cls.description}")
        return "\n".join(lines)
