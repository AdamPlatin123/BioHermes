"""Verifier layer: automatic result validation."""
from __future__ import annotations

import logging
from typing import Optional

from .models import AgentSession, VerifyResult
from ..llm.client import LLMClient
from ..llm.prompts import VERIFIER_SYSTEM, VERIFIER_USER
from ..pipeline.context import PipelineContext

logger = logging.getLogger("biohermes.agent")


class Verifier:
    """Verifies execution results at format, completeness, and consistency levels."""

    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def verify(self, session: AgentSession, context: PipelineContext) -> VerifyResult:
        """Three-level verification: format → completeness → consistency."""
        checks = []
        warnings = []
        errors = []

        # Level 1: Format validation
        fmt = self._check_format(session, context)
        checks.extend(fmt["checks"])
        if fmt["errors"]:
            errors.extend(fmt["errors"])

        # Level 2: Completeness validation
        comp = self._check_completeness(session, context)
        checks.extend(comp["checks"])
        if comp["warnings"]:
            warnings.extend(comp["warnings"])

        # Level 3: Consistency validation (data integrity)
        cons = self._check_consistency(session, context)
        checks.extend(cons["checks"])
        if cons["errors"]:
            errors.extend(cons["errors"])
        if cons["warnings"]:
            warnings.extend(cons["warnings"])

        # Level 4: LLM quality check (optional, if LLM available)
        if self.llm.available and not errors:
            llm_check = await self._llm_verify(session, context)
            if llm_check:
                checks.append(llm_check)

        passed = len(errors) == 0
        result = VerifyResult(
            passed=passed, level="all",
            checks=checks, warnings=warnings, errors=errors,
        )
        session.verify_result = result
        return result

    def _check_format(self, session: AgentSession, ctx: PipelineContext) -> dict:
        checks = []
        errors = []

        for step in session.steps:
            if step.status == "completed" and not step.output:
                checks.append({"name": f"step_{step.index}_output", "passed": False, "detail": "No output"})
                errors.append(f"Step {step.index} completed but produced no output")
            elif step.status == "completed":
                checks.append({"name": f"step_{step.index}_output", "passed": True, "detail": "Has output"})

        if not ctx.parsed_results and any("parse" in s.tool_name for s in session.steps):
            errors.append("No parsed results produced")

        return {"checks": checks, "errors": errors}

    def _check_completeness(self, session: AgentSession, ctx: PipelineContext) -> dict:
        checks = []
        warnings = []

        completed = sum(1 for s in session.steps if s.status == "completed")
        total = len(session.steps)
        checks.append({
            "name": "step_completion", "passed": completed == total,
            "detail": f"{completed}/{total} steps completed",
        })

        if completed < total:
            warnings.append(f"Only {completed}/{total} steps completed")

        if ctx.tables:
            for i, table in enumerate(ctx.tables):
                if table.get("row_count", 0) == 0:
                    warnings.append(f"Table {i} has no data rows")
                checks.append({
                    "name": f"table_{i}", "passed": table.get("row_count", 0) > 0,
                    "detail": f"{table.get('row_count', 0)} rows",
                })

        return {"checks": checks, "warnings": warnings}

    def _check_consistency(self, session: AgentSession, ctx: PipelineContext) -> dict:
        checks = []
        errors = []
        warnings = []

        for i, table in enumerate(ctx.tables):
            headers = table.get("headers", [])
            rows = table.get("rows", [])
            for j, row in enumerate(rows):
                if len(row) != len(headers) and headers:
                    errors.append(f"Table {i} row {j}: column mismatch ({len(row)} vs {len(headers)})")
                    break

            # Check numeric totals
            consistency = self._check_table_totals(table)
            if consistency:
                checks.append(consistency)
                if not consistency["passed"]:
                    warnings.append(consistency["detail"])

        return {"checks": checks, "errors": errors, "warnings": warnings}

    def _check_table_totals(self, table: dict) -> Optional[dict]:
        headers = table.get("headers", [])
        rows = table.get("rows", [])
        for i, h in enumerate(headers):
            if any(kw in str(h).lower() for kw in ["合计", "总计", "total"]):
                if rows and i < len(rows[-1]):
                    try:
                        total = float(str(rows[-1][i]).replace(",", "").replace("，", ""))
                        col_sum = 0
                        for row in rows[:-1]:
                            if i < len(row):
                                try:
                                    col_sum += float(str(row[i]).replace(",", "").replace("，", ""))
                                except ValueError:
                                    pass
                        if abs(total - col_sum) > 0.01 and col_sum > 0:
                            return {
                                "name": f"total_check_{i}",
                                "passed": False,
                                "detail": f"Total {total} != sum {col_sum}",
                            }
                        return {"name": f"total_check_{i}", "passed": True, "detail": "Consistent"}
                    except ValueError:
                        pass
        return None

    async def _llm_verify(self, session: AgentSession, ctx: PipelineContext) -> Optional[dict]:
        try:
            import json
            results_summary = {
                "steps_completed": sum(1 for s in session.steps if s.status == "completed"),
                "steps_total": len(session.steps),
                "tables": len(ctx.tables),
                "structures": len(ctx.structures),
                "errors": len(ctx.errors),
            }
            resp = self.llm.chat_json(
                VERIFIER_SYSTEM,
                VERIFIER_USER.format(task=session.task, results=json.dumps(results_summary)),
            )
            return {
                "name": "llm_quality", "passed": resp.get("passed", True),
                "detail": "LLM quality check",
            }
        except Exception:
            return None
