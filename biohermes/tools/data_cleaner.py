"""Data cleaning and validation tool."""
from __future__ import annotations

import re
import logging
from .base import BaseTool, ToolResult
from ..pipeline.context import PipelineContext

logger = logging.getLogger("biohermes.tools")


class DataCleaner(BaseTool):
    name = "data_clean"
    description = "Clean, deduplicate, and validate extracted data"

    async def execute(self, args: dict, context: PipelineContext) -> ToolResult:
        actions = args.get("actions", ["deduplicate", "validate"])
        issues = []

        if "deduplicate" in actions:
            dup_count = self._deduplicate_tables(context)
            if dup_count > 0:
                issues.append(f"Removed {dup_count} duplicate rows")

        if "validate" in actions:
            val_issues = self._validate_data(context)
            issues.extend(val_issues)

        if "normalize" in actions:
            self._normalize_numbers(context)

        context.set_output(args.get("_step_index", 0), {"cleaned": True, "issues": issues})
        return ToolResult(
            success=True,
            data={"actions": actions, "issues": issues},
            metadata={"table_count": len(context.tables)},
        )

    def _deduplicate_tables(self, context: PipelineContext) -> int:
        removed = 0
        for table in context.tables:
            rows = table.get("rows", [])
            seen = set()
            unique_rows = []
            for row in rows:
                # Convert all cells to strings for stable hashing
                try:
                    key = tuple(str(c) for c in row)
                except TypeError:
                    # Unhashable cell — keep the row
                    unique_rows.append(row)
                    continue
                if key not in seen:
                    seen.add(key)
                    unique_rows.append(row)
                else:
                    removed += 1
            table["rows"] = unique_rows
            table["row_count"] = len(unique_rows)
        return removed

    def _validate_data(self, context: PipelineContext) -> list[str]:
        issues = []
        for i, table in enumerate(context.tables):
            headers = table.get("headers", [])
            rows = table.get("rows", [])
            for j, row in enumerate(rows):
                if len(row) != len(headers) and headers:
                    issues.append(f"Table {i} row {j}: column count mismatch ({len(row)} vs {len(headers)})")
            # Check for empty headers
            if not headers and rows:
                issues.append(f"Table {i}: has data rows but no headers")
        return issues

    def _normalize_numbers(self, context: PipelineContext):
        """Normalize number formats: remove commas, currency symbols, handle % and scientific notation."""
        for table in context.tables:
            for row in table.get("rows", []):
                for i, cell in enumerate(row):
                    s = str(cell).strip()
                    # Handle percentage
                    if s.endswith("%"):
                        try:
                            row[i] = str(float(s[:-1].replace(",", "").replace("，", "")) / 100)
                            continue
                        except ValueError:
                            pass
                    # Handle currency and separators
                    cleaned = re.sub(r'[\s，,¥$€£]', '', s)
                    try:
                        float(cleaned)
                        row[i] = cleaned
                    except ValueError:
                        pass
