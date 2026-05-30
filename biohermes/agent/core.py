"""BioHermes Agent Core — orchestrates Judge→Select→Execute→Verify loop."""
from __future__ import annotations

import os
import re
import uuid
import time
import logging
from typing import Callable, Optional

from .models import AgentSession, TaskStatus
from .judge import Judge
from .planner import Planner
from .executor import Executor
from .verifier import Verifier
from .recovery import Recovery
from ..llm.client import LLMClient
from ..pipeline.context import PipelineContext
from ..tools import create_tools
from ..tools.base import BaseTool
from ..utils.logging import AgentLogger
from .. import config

logger = logging.getLogger("biohermes")


class BioHermesAgent:
    """
    BioHermes Data Agent v2.0

    Architecture: Judge → Select → Execute → Verify (loop)
    - Judge: LLM analyzes task, outputs task_type, complexity, recommended tools
    - Select (Planner): Generates optimal execution plan from judge result
    - Execute (Executor): Runs steps with PipelineContext data passing
    - Verify: Auto-validates results at format/completeness/consistency levels
    - Recovery: Retry → Degrade → Skip on failure
    """

    def __init__(self, mineru_api_url: str = "", llm_api_key: str = "",
                 llm_base_url: str = "", llm_model: str = "",
                 log_dir: str = "", on_event: Optional[Callable] = None):
        self.mineru_api_url = mineru_api_url or config.MINERU_API_URL
        self.log_dir = log_dir or config.LOG_DIR

        self.llm = LLMClient(
            api_key=llm_api_key or config.LLM_API_KEY,
            base_url=llm_base_url or config.LLM_BASE_URL,
            model=llm_model or config.LLM_MODEL,
        )

        self.tools: dict[str, BaseTool] = create_tools(self.mineru_api_url)
        self.judge = Judge(self.llm)
        self.planner = Planner(self.llm)
        self.verifier = Verifier(self.llm)
        self.recovery = Recovery(max_retries=config.MAX_RETRIES)
        self.agent_logger = AgentLogger(self.log_dir)
        self.on_event = on_event
        self.sessions: dict[str, AgentSession] = {}
        self._max_sessions = 100  # Memory safety limit

    def _emit(self, session_id: str, event: str, data: dict):
        if self.on_event:
            self.on_event(session_id, event, data)

    async def run(self, task: str, session_id: str = None) -> AgentSession:
        """
        Execute complete agent loop: Judge → Select → Execute → Verify.
        If verify fails, loop back to Judge with error context.
        """
        session = AgentSession(
            session_id=session_id or uuid.uuid4().hex[:16],
            task=task,
        )
        self.sessions[session.session_id] = session

        # Evict oldest sessions if over limit
        if len(self.sessions) > self._max_sessions:
            oldest_ids = sorted(
                self.sessions.keys(),
                key=lambda k: self.sessions[k].created_at,
            )[:len(self.sessions) - self._max_sessions]
            for sid in oldest_ids:
                del self.sessions[sid]

        context = PipelineContext()
        max_loops = 3  # Iterative judge loops: initial + up to 2 re-judgments

        # Extract file paths from task description
        file_paths = re.findall(r'/[\w\-./]+\.(?:pdf|docx|pptx|png|jpg|jpeg)', task, re.IGNORECASE)
        if file_paths:
            existing = [fp for fp in file_paths if os.path.exists(fp)]
            if existing:
                context.files = existing

        try:
            for loop in range(max_loops):
                # ─── JUDGE ───
                session.status = TaskStatus.JUDGING
                self._emit(session.session_id, "judging", {"task": task, "loop": loop})
                session.add_event("judging", {"task": task, "loop": loop})

                # On re-judge, pass structured context from previous iteration
                prev_judge = session.judge_result if loop > 0 else None
                verify_errors = session.verify_result.errors if (loop > 0 and session.verify_result) else None
                failed_steps = [
                    f"Step {s.index} ({s.tool_name}): {s.error}"
                    for s in session.steps if s.status == "failed"
                ] if loop > 0 else None

                judge_result = await self.judge.analyze(
                    task,
                    previous_judge=prev_judge,
                    verify_errors=verify_errors,
                    failed_steps=failed_steps,
                )
                session.judge_result = judge_result

                self._emit(session.session_id, "judge_complete", judge_result.to_dict())
                session.add_event("judge_complete", judge_result.to_dict())

                # ─── SELECT (PLAN) ───
                session.status = TaskStatus.PLANNING
                self._emit(session.session_id, "planning", {"loop": loop})

                steps = await self.planner.plan(task, judge_result, failed_steps=failed_steps)
                session.steps = steps

                self._emit(session.session_id, "plan_ready", {
                    "total_steps": len(steps),
                    "steps": [s.description for s in steps],
                })
                session.add_event("plan_ready", {
                    "total_steps": len(steps),
                    "steps": [s.description for s in steps],
                })

                # ─── EXECUTE ───
                session.status = TaskStatus.EXECUTING
                executor = Executor(self.tools, self.on_event)

                for step in steps:
                    success = await executor.execute_step(session, step, context)
                    if not success:
                        recovered = await self.recovery.recover(session, step, context, executor)
                        if not recovered:
                            session.status = TaskStatus.FAILED
                            session.error = f"Step {step.index} failed and could not recover"
                            break

                if session.status == TaskStatus.FAILED:
                    break

                # ─── VERIFY ───
                session.status = TaskStatus.VERIFYING
                self._emit(session.session_id, "verifying", {"loop": loop})

                verify_result = await self.verifier.verify(session, context)

                self._emit(session.session_id, "verify_complete", verify_result.to_dict())
                session.add_event("verify_complete", verify_result.to_dict())

                if verify_result.passed:
                    break  # All good
                elif loop < max_loops - 1:
                    # Re-judge: structured context is passed via Judge/Planner params
                    logger.warning(
                        f"Verify failed (loop {loop}): {verify_result.errors}. "
                        f"Re-judging with error context."
                    )
                else:
                    # Final loop, accept with warnings
                    logger.warning("Verify failed on final loop, accepting with warnings")

            # ─── SUMMARIZE ───
            if session.status != TaskStatus.FAILED:
                session.status = TaskStatus.COMPLETED
                session.result = self._summarize(session, context)

            session.finished_at = time.time()
            session.add_event("task_complete", {
                "status": session.status.value,
                "duration": session.duration(),
                "context_summary": context.summary(),
            })
            self._emit(session.session_id, "task_complete", {
                "status": session.status.value,
                "duration": session.duration(),
            })

        except Exception as e:
            session.status = TaskStatus.FAILED
            session.error = str(e)
            session.finished_at = time.time()
            logger.error(f"Agent run failed: {e}")

        self.agent_logger.log_session(session)
        return session

    def _summarize(self, session: AgentSession, context: PipelineContext) -> str:
        completed = sum(1 for s in session.steps if s.status in ("completed", "completed_fallback", "skipped"))
        total = len(session.steps)
        tools_used = set()
        for s in session.steps:
            for tc in s.tool_calls:
                tools_used.add(tc.name)

        ctx = context.summary()
        return (f"任务完成: {completed}/{total} 步骤成功, "
                f"工具: {', '.join(tools_used) or '无'}, "
                f"解析: {ctx['parsed']} 文件, "
                f"表格: {ctx['tables']}, "
                f"耗时: {session.duration()}s")


async def quick_run(task: str, log_dir: str = "logs") -> AgentSession:
    agent = BioHermesAgent(log_dir=log_dir)
    return await agent.run(task)
