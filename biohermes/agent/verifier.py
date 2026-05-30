"""Verifier layer: automatic result validation at three levels."""
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
        """Three-level verification: format -> completeness -> consistency."""
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
        """Level 1: Check outputs are non-empty and well-formed."""
        checks = []
        errors = []

        for step in session.steps:
            if step.status == "completed":
                if not step.output:
                    checks.append({"name": f"step_{step.index}_output", "passed": False,
                                   "detail": "No output"})
                    errors.append(f"Step {step.index} completed but produced no output")
                elif isinstance(step.output, dict) and step.output.get("note") == "Already parsed":
                    checks.append({"name": f"step_{step.index}_output", "passed": True,
                                   "detail": "Skipped (already parsed)"})
                else:
                    checks.append({"name": f"step_{step.index}_output", "passed": True,
                                   "detail": "Has output"})
            elif step.status == "skipped":
                checks.append({"name": f"step_{step.index}_output", "passed": True,
                               "detail": "Non-critical step skipped"})

        if not ctx.parsed_results and any("parse" in s.tool_name for s in session.steps):
            errors.append("No parsed results produced")

        return {"checks": checks, "errors": errors}

    def _check_completeness(self, session: AgentSession, ctx: PipelineContext) -> dict:
        """Level 2: Check step completion rate and data volumes."""
        checks = []
        warnings = []

        completed = sum(1 for s in session.steps
                        if s.status in ("completed", "completed_fallback", "skipped"))
        total = len(session.steps)
        checks.append({
            "name": "step_completion", "passed": completed == total,
            "detail": f"{completed}/{total} steps completed",
        })

        if completed < total:
            warnings.append(f"Only {completed}/{total} steps completed")

        if ctx.tables:
            for i, table in enumerate(ctx.tables):
                row_count = table.get("row_count", 0)
                col_count = table.get("col_count", 0)
                if row_count == 0:
                    warnings.append(f"Table {i} has no data rows")
                if col_count == 0:
                    warnings.append(f"Table {i} has no columns")
                checks.append({
                    "name": f"table_{i}", "passed": row_count > 0 and col_count > 0,
                    "detail": f"{row_count} rows x {col_count} cols",
                })

        return {"checks": checks, "warnings": warnings}

    def _check_consistency(self, session: AgentSession, ctx: PipelineContext) -> dict:
        """Level 3: Check data integrity — column alignment and numeric totals."""
        checks = []
        errors = []
        warnings = []

        for i, table in enumerate(ctx.tables):
            headers = table.get("headers", [])
            rows = table.get("rows", [])

            # Column alignment check
            for j, row in enumerate(rows):
                if headers and len(row) != len(headers):
                    errors.append(
                        f"Table {i} row {j}: column mismatch ({len(row)} vs {len(headers)})")
                    break

            # Numeric totals check
            consistency = self._check_table_totals(table, i)
            if consistency:
                checks.append(consistency)
                if not consistency["passed"]:
                    warnings.append(consistency["detail"])

        return {"checks": checks, "errors": errors, "warnings": warnings}

    def _check_table_totals(self, table: dict, table_idx: int) -> Optional[dict]:
        """Check numeric totals: last row sum vs computed sum of preceding rows."""
        headers = table.get("headers", [])
        rows = table.get("rows", [])

        for i, h in enumerate(headers):
            if not any(kw in str(h).lower() for kw in ["合计", "总计", "total", "sum"]):
                continue

            if not rows or i >= len(rows[-1]):
                continue

            try:
                total = self._parse_number(rows[-1][i])
                if total is None:
                    continue

                col_sum = 0.0
                valid = True
                for row in rows[:-1]:
                    if i >= len(row):
                        valid = False
                        break
                    val = self._parse_number(row[i])
                    if val is None:
                        valid = False
                        break
                    col_sum += val

                if not valid:
                    continue

                if abs(total - col_sum) > 0.01 and col_sum > 0:
                    return {
                        "name": f"total_check_t{table_idx}_c{i}",
                        "passed": False,
                        "detail": f"Table {table_idx} col '{h}': total={total} != sum={col_sum}",
                    }
                return {
                    "name": f"total_check_t{table_idx}_c{i}",
                    "passed": True,
                    "detail": f"Table {table_idx} col '{h}': consistent",
                }
            except Exception:
                continue

        return None

    @staticmethod
    def _parse_number(value) -> Optional[float]:
        """Safely parse a string to float, handling commas and Chinese punctuation."""
        try:
            return float(str(value).replace(",", "").replace("，", "").replace(" ", "").strip())
        except (ValueError, TypeError):
            return None

    async def _llm_verify(self, session: AgentSession, ctx: PipelineContext) -> Optional[dict]:
        """Level 4: Optional LLM-based quality assessment."""
        try:
            import json
            results_summary = {
                "steps_completed": sum(
                    1 for s in session.steps if s.status in ("completed", "completed_fallback")),
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
                "detail": resp.get("reason", "LLM quality check"),
            }
        except Exception as e:
            logger.warning(f"LLM verify failed: {e}")
            return None
