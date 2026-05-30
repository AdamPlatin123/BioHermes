"""Planner layer: generates optimal execution plan from judge result."""
from __future__ import annotations

import logging
from typing import Optional
from .models import JudgeResult, TaskStep
from ..llm.client import LLMClient
from ..llm.prompts import PLANNER_SYSTEM, PLANNER_USER
from ..tools import TOOL_REGISTRY

logger = logging.getLogger("biohermes.agent")


class Planner:
    """Selects optimal tools and generates execution plan based on judge assessment."""

    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def plan(self, task: str, judge: JudgeResult,
                   failed_steps: Optional[list[str]] = None) -> list[TaskStep]:
        """Generate execution plan from judge result.

        On re-plan (after verify failure), receives failed step descriptions
        so the plan can avoid or adjust previously failing steps.
        """
        if self.llm.available:
            try:
                return await self._llm_plan(task, judge, failed_steps)
            except Exception as e:
                logger.warning(f"LLM planner failed, using fallback: {e}")

        return self._rule_plan(task, judge, failed_steps)

    async def _llm_plan(self, task: str, judge: JudgeResult,
                        failed_steps: Optional[list[str]] = None) -> list[TaskStep]:
        tools_desc = "\n".join(f"- {name}: {cls.description}" for name, cls in TOOL_REGISTRY.items())

        user_prompt = PLANNER_USER.format(task=task, judge_result=judge.to_dict())
        if failed_steps:
            user_prompt += f"\n\n[Previously failed steps to avoid or adjust: {'; '.join(failed_steps)}]"

        result = self.llm.chat_json(
            PLANNER_SYSTEM.format(tools=tools_desc),
            user_prompt,
        )

        steps = []
        valid_tools = set(TOOL_REGISTRY.keys()) | {"scan_files"}
        for s in result if isinstance(result, list) else result.get("steps", []):
            tool_name = s.get("tool", "")
            if tool_name and tool_name not in valid_tools:
                logger.warning(f"LLM planner returned unknown tool '{tool_name}', skipping")
                continue
            steps.append(TaskStep(
                index=s.get("index", len(steps)),
                description=s.get("description", ""),
                tool_name=tool_name,
                tool_args=s.get("args", {}),
            ))
        return steps if steps else self._rule_plan(task, judge, failed_steps)

    def _rule_plan(self, task: str, judge: JudgeResult,
                   failed_steps: Optional[list[str]] = None) -> list[TaskStep]:
        """Rule-based fallback planner. Adjusts plan when re-planning after failure."""
        # Identify tools that previously failed so we can skip them
        failed_tools: set[str] = set()
        if failed_steps:
            for desc in failed_steps:
                for tool in TOOL_REGISTRY:
                    if f"({tool})" in desc:
                        failed_tools.add(tool)

        steps = []
        tt = judge.task_type

        if tt == "batch":
            steps = [
                TaskStep(0, "扫描目录，发现所有文档文件", "scan_files", {}),
                TaskStep(1, "并行调用 MinerU 解析所有文档", "mineru_parse", {}),
                TaskStep(2, "提取所有表格数据", "table_extract", {}),
                TaskStep(3, "数据清洗与验证", "data_clean", {}),
                TaskStep(4, "汇总生成批量处理报告", "report_generate", {}),
            ]
        elif tt == "extract":
            steps = [
                TaskStep(0, "调用 MinerU 解析文档", "mineru_parse", {}),
                TaskStep(1, "提取表格数据", "table_extract", {}),
                TaskStep(2, "数据清洗与一致性验证", "data_clean", {}),
                TaskStep(3, "生成提取报告", "report_generate", {}),
            ]
        elif tt == "pipeline":
            steps = [
                TaskStep(0, "文档摄入与去重", "scan_files", {}),
                TaskStep(1, "MinerU 解析所有文档", "mineru_parse", {}),
                TaskStep(2, "智能切分与结构化提取", "structure_extract", {}),
                TaskStep(3, "表格数据提取", "table_extract", {}),
                TaskStep(4, "数据清洗与验证", "data_clean", {}),
                TaskStep(5, "生成知识库索引报告", "report_generate", {}),
            ]
        else:  # parse
            steps = [
                TaskStep(0, "调用 MinerU 解析文档", "mineru_parse", {}),
                TaskStep(1, "提取结构化信息（章节、公式、元数据）", "structure_extract", {}),
                TaskStep(2, "提取表格数据", "table_extract", {}),
                TaskStep(3, "生成解析报告", "report_generate", {}),
            ]

        # On re-plan: skip tools that failed in previous iteration
        if failed_tools:
            filtered = [s for s in steps if s.tool_name not in failed_tools]
            if filtered:
                # Re-index
                for i, s in enumerate(filtered):
                    s.index = i
                steps = filtered
                logger.info(f"Re-planned, skipped failed tools: {failed_tools}")

        return steps
