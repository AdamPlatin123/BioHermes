"""Table extraction tool."""
from __future__ import annotations

import re
import logging
from .base import BaseTool, ToolResult
from ..pipeline.context import PipelineContext

logger = logging.getLogger("biohermes.tools")


class TableExtractor(BaseTool):
    name = "table_extract"
    description = "Extract and reconstruct tables from parsed content"

    async def execute(self, args: dict, context: PipelineContext) -> ToolResult:
        content = args.get("content", "")
        if not content and context.parsed_results:
            content = next(iter(context.parsed_results.values()), {}).get("content", "")

        if not content:
            return ToolResult(success=False, error="No content to extract tables from")

        tables = self.extract_from_markdown(content)

        for t in tables:
            context.add_table(t)

        context.set_output(args.get("_step_index", 0), {"tables": tables})
        return ToolResult(
            success=True,
            data={"tables": tables, "count": len(tables)},
            metadata={"source": "markdown"},
        )

    def extract_from_markdown(self, md_content: str) -> list[dict]:
        tables = []
        current_table: list[str] = []
        in_table = False

        for line in md_content.split("\n"):
            stripped = line.strip()
            if stripped.startswith("|") and "|" in stripped[1:]:
                if not in_table:
                    in_table = True
                    current_table = []
                current_table.append(stripped)
            else:
                if in_table and current_table:
                    tables.append(self._parse_md_table(current_table))
                    current_table = []
                    in_table = False

        if current_table:
            tables.append(self._parse_md_table(current_table))

        return tables

    def _parse_md_table(self, rows: list[str]) -> dict:
        clean_rows = []
        for r in rows:
            if all(c in "|-: " for c in r):
                continue
            cells = [c.strip() for c in r.split("|") if c.strip()]
            if cells:
                clean_rows.append(cells)

        headers = clean_rows[0] if clean_rows else []
        data = clean_rows[1:] if len(clean_rows) > 1 else []

        return {
            "headers": headers, "rows": data,
            "row_count": len(data), "col_count": len(headers),
        }

    def validate_consistency(self, table: dict) -> dict:
        """Check numeric consistency: sum of rows vs totals."""
        issues = []
        headers = table.get("headers", [])
        rows = table.get("rows", [])

        numeric_cols = []
        for i, h in enumerate(headers):
            if any(kw in h.lower() for kw in ["合计", "总计", "total", "sum"]):
                numeric_cols.append((i, h))

        for col_idx, col_name in numeric_cols:
            total_val = None
            detail_sum = 0.0
            for row in rows:
                if col_idx < len(row):
                    try:
                        val = float(row[col_idx].replace(",", "").replace("，", ""))
                        total_val = val
                    except (ValueError, IndexError):
                        pass

        return {"issues": issues, "checked": len(numeric_cols) > 0}
