"""Executor layer: runs pipeline steps with context passing."""
from __future__ import annotations

import time
import logging
from typing import Callable, Optional

from .models import AgentSession, TaskStep, ToolCall
from ..pipeline.context import PipelineContext
from ..tools.base import BaseTool, ToolResult

logger = logging.getLogger("biohermes.agent")


class Executor:
    """Executes pipeline steps, passing PipelineContext between tools."""

    def __init__(self, tools: dict[str, BaseTool],
                 on_event: Optional[Callable] = None):
        self.tools = tools
        self.on_event = on_event

    def _emit(self, session_id: str, event: str, data: dict):
        if self.on_event:
            self.on_event(session_id, event, data)

    async def execute_step(self, session: AgentSession, step: TaskStep,
                           context: PipelineContext) -> bool:
        """Execute a single step. Returns True on success."""
        step.status = "running"
        step.start_time = time.time()
        self._emit(session.session_id, "step_start", step.to_dict())
        session.add_event("step_start", {"step": step.index, "desc": step.description})

        try:
            tool_result = await self._call_tool(step, context)
            step.status = "completed"
            step.output = tool_result.data
            step.end_time = time.time()
            self._emit(session.session_id, "step_complete", step.to_dict())
            session.add_event("step_complete", {"step": step.index, "duration": step.duration()})
            return True

        except Exception as e:
            step.status = "failed"
            step.error = str(e)
            step.end_time = time.time()
            logger.error(f"Step {step.index} failed: {e}")
            self._emit(session.session_id, "step_error", {"step": step.index, "error": str(e)})
            return False

    async def _call_tool(self, step: TaskStep, context: PipelineContext) -> ToolResult:
        """Call the tool specified in the step."""
        tool_name = step.tool_name
        args = dict(step.tool_args)
        args["_step_index"] = step.index

        # Pass context data to tool args when needed
        if tool_name == "mineru_parse" and not args.get("file_path"):
            if context.files:
                args["file_path"] = context.files[0]
            elif context.parsed_results:
                return ToolResult(success=True, data={"note": "Already parsed"}, metadata={"skipped": True})
            else:
                return ToolResult(success=False, error="No files to parse")
        elif tool_name in ("table_extract", "structure_extract", "data_clean"):
            if context.parsed_results and "content" not in args:
                first_result = next(iter(context.parsed_results.values()), {})
                args["content"] = first_result.get("content", "")
        elif tool_name == "scan_files":
            return self._scan_files(args, context)

        # Look up and execute tool
        tool = self.tools.get(tool_name)
        if not tool:
            raise ValueError(f"Unknown tool: {tool_name}")

        tc = ToolCall(id=f"tc_{step.index}", name=tool_name, args=args)
        tc.start_time = time.time()
        step.tool_calls.append(tc)

        result = await tool.execute(args, context)

        tc.status = "completed" if result.success else "failed"
        tc.result = result.data
        tc.error = result.error
        tc.end_time = time.time()

        if not result.success:
            raise RuntimeError(f"Tool {tool_name} failed: {result.error}")

        return result

    def _scan_files(self, args: dict, context: PipelineContext) -> ToolResult:
        """Built-in file scanner."""
        from ..utils.file_utils import scan_directory, validate_file

        target = args.get("directory", args.get("path", ""))
        if not target:
            return ToolResult(success=False, error="No directory specified")

        files = scan_directory(target)
        context.files = files
        context.set_output(args.get("_step_index", 0), {"files": files, "count": len(files)})

        return ToolResult(
            success=True,
            data={"files": files, "count": len(files)},
            metadata={"directory": target},
        )
