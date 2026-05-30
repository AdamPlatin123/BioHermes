"""Recovery layer: retry with backoff, degrade, or skip failed steps."""
from __future__ import annotations

import asyncio
import logging

from .models import AgentSession, TaskStep, TaskStatus
from ..pipeline.context import PipelineContext
from ..tools.mineru_parser import MinerUParser

logger = logging.getLogger("biohermes.agent")


class Recovery:
    """Three-level recovery: retry (backoff) → degrade → skip."""

    def __init__(self, max_retries: int = 3, base_delay: float = 1.0):
        self.max_retries = max_retries
        self.base_delay = base_delay

    async def recover(self, session: AgentSession, step: TaskStep,
                      context: PipelineContext, executor) -> bool:
        """Attempt recovery for a failed step."""
        session.status = TaskStatus.RECOVERING
        session.retry_count += 1

        # Level 1: Retry with exponential backoff
        if session.retry_count <= self.max_retries:
            delay = self.base_delay * (2 ** (session.retry_count - 1))
            logger.info(f"Retrying step {step.index} in {delay:.1f}s (attempt {session.retry_count})")
            await asyncio.sleep(delay)

            # Reset step state for clean retry
            step.status = "pending"
            step.error = None
            step.tool_calls = []

            return await executor.execute_step(session, step, context)

        # Level 2: Degrade (use PyMuPDF fallback)
        if step.tool_name == "mineru_parse":
            logger.warning(f"Degrading step {step.index} to PyMuPDF fallback")
            return await self._degrade_parse(step, context)

        # Level 3: Skip non-critical steps
        if self._is_non_critical(step):
            logger.warning(f"Skipping non-critical step {step.index} ({step.tool_name})")
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

        parser = MinerUParser()
        result = await parser._fallback_parse(file_path)

        if result["status"] in ("success_fallback", "degraded"):
            step.status = "completed_fallback"
            step.output = result
            filename = result.get("metadata", {}).get("filename", "unknown")
            context.add_parsed_result(filename, result)

            content_len = len(result.get("content", ""))
            logger.info(f"PyMuPDF fallback succeeded: {filename}, {content_len} chars")
            return True

        logger.warning(f"PyMuPDF fallback also failed for step {step.index}")
        return False

    def _is_non_critical(self, step: TaskStep) -> bool:
        """Determine if a step can be safely skipped without affecting core output."""
        non_critical_tools = {"data_clean", "report_generate", "table_extract"}
        return step.tool_name in non_critical_tools
