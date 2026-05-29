"""Recovery layer: retry, degrade, or skip failed steps."""
from __future__ import annotations

import logging

from .models import AgentSession, TaskStep, TaskStatus
from ..pipeline.context import PipelineContext
from ..tools.mineru_parser import MinerUParser

logger = logging.getLogger("biohermes.agent")


class Recovery:
    """Three-level recovery: retry → degrade → skip."""

    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries

    async def recover(self, session: AgentSession, step: TaskStep,
                      context: PipelineContext, executor) -> bool:
        """Attempt recovery for a failed step."""
        session.status = TaskStatus.RECOVERING
        session.retry_count += 1

        # Level 1: Retry
        if session.retry_count <= self.max_retries:
            logger.info(f"Retrying step {step.index} (attempt {session.retry_count})")
            return await executor.execute_step(session, step, context)

        # Level 2: Degrade (use PyMuPDF fallback)
        if step.tool_name == "mineru_parse":
            logger.warning(f"Degrading step {step.index} to PyMuPDF fallback")
            return await self._degrade_parse(step, context)

        # Level 3: Skip non-critical steps
        if self._is_non_critical(step):
            logger.warning(f"Skipping non-critical step {step.index}")
            step.status = "skipped"
            step.output = f"Skipped after {session.retry_count} retries"
            context.add_error(step.index, step.error or "skipped")
            return True

        return False

    async def _degrade_parse(self, step: TaskStep, context: PipelineContext) -> bool:
        """Use PyMuPDF local fallback."""
        file_path = step.tool_args.get("file_path", "")
        if not file_path and context.files:
            file_path = context.files[0]

        if not file_path:
            return False

        parser = MinerUParser()  # No API URL = will use fallback
        result = await parser._fallback_parse(file_path)

        if result["status"] in ("success_fallback", "degraded"):
            step.status = "completed_fallback"
            step.output = result
            context.add_parsed_result(result.get("metadata", {}).get("filename", "unknown"), result)
            return True

        return False

    def _is_non_critical(self, step: TaskStep) -> bool:
        """Determine if a step can be safely skipped."""
        non_critical_tools = {"data_clean", "report_generate"}
        return step.tool_name in non_critical_tools
