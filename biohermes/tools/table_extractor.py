"""Table extraction tool — extracts and reconstructs tables from parsed content."""
from __future__ import annotations

import re
import logging
from .base import BaseTool, ToolResult
from ..pipeline.context import PipelineContext

logger = logging.getLogger("biohermes.tools")


class TableExtractor(BaseTool):
    name = "table_extract"
    description = "Extract and reconstruct tables from parsed content, with consistency validation"

    async def execute(self, args: dict, context: PipelineContext) -> ToolResult:
        content = args.get("content", "")
        if not content and context.parsed_results:
            first_result = next(iter(context.parsed_results.values()), {})
            content = first_result.get("content", "")

        if not content:
            return ToolResult(success=False, error="No content to extract tables from")

        tables = self.extract_from_markdown(content)

        # Validate each table's internal consistency
        for t in tables:
            issues = self.validate_consistency(t)
            t["consistency_issues"] = issues

        for t in tables:
            context.add_table(t)

        context.set_output(args.get("_step_index", 0), {"tables": tables, "count": len(tables)})
        return ToolResult(
            success=True,
            data={"tables": tables, "count": len(tables)},
            metadata={"source": "markdown"},
        )

    def extract_from_markdown(self, md_content: str) -> list[dict]:
        """Extract all markdown tables from content."""
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
        """Parse a markdown table into structured headers + rows."""
        clean_rows = []
        for r in rows:
            # Skip separator rows (---|---|---)
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

    def validate_consistency(self, table: dict) -> list[str]:
        """Check numeric consistency: sum of detail rows vs total/合计 row.

        Returns a list of issue descriptions (empty if consistent).
        """
        issues = []
        headers = table.get("headers", [])
        rows = table.get("rows", [])

        if not rows or not headers:
            return issues

        # Column alignment check (always runs)
        header_len = len(headers)
        for j, row in enumerate(rows):
            if len(row) != header_len:
                issues.append(f"Row {j}: {len(row)} cells vs {header_len} headers")

        # Identify total row (last row with a total-like header)
        total_keywords = ["合计", "总计", "total", "sum", "小计"]
        total_col_indices = []
        for i, h in enumerate(headers):
            if any(kw in str(h).lower() for kw in total_keywords):
                total_col_indices.append(i)

        if not total_col_indices:
            # Fallback: detect total row by first-column keyword
            total_row_keywords = ["合计", "总计", "total", "sum", "小计"]
            for ri, row in enumerate(rows):
                if row and any(kw in str(row[0]).lower() for kw in total_row_keywords):
                    # This is a total row — check all numeric columns
                    for ci in range(1, len(headers)):
                        if ci >= len(row):
                            continue
                        total_val = self._parse_number(row[ci])
                        if total_val is None:
                            continue
                        col_sum = 0.0
                        valid = True
                        for other_row in rows:
                            if other_row is row:
                                continue
                            if ci < len(other_row):
                                v = self._parse_number(other_row[ci])
                                if v is not None:
                                    col_sum += v
                                else:
                                    # Non-numeric value in detail row — skip this column
                                    valid = False
                                    break
                            else:
                                valid = False
                                break
                        if valid and abs(total_val - col_sum) > 0.01 and col_sum > 0:
                            issues.append(
                                f"Row {ri} col '{headers[ci]}': total={total_val} != sum={round(col_sum, 2)}"
                            )
            return issues

        # Check if last row is a total row (column-based detection)
        last_row = rows[-1]
        is_total_row = False
        for idx in total_col_indices:
            if idx < len(last_row):
                val = self._parse_number(last_row[idx])
                if val is not None:
                    is_total_row = True
                    # Compute sum of preceding rows
                    col_sum = 0.0
                    valid = True
                    for row in rows[:-1]:
                        if idx < len(row):
                            v = self._parse_number(row[idx])
                            if v is not None:
                                col_sum += v
                            else:
                                valid = False
                                break
                        else:
                            valid = False
                            break

                    if valid and abs(val - col_sum) > 0.01 and col_sum > 0:
                        issues.append(
                            f"Column '{headers[idx]}': total={val} != sum={round(col_sum, 2)}"
                        )

        return issues

    @staticmethod
    def _parse_number(value) -> float | None:
        """Safely parse a numeric string."""
        try:
            return float(str(value).replace(",", "").replace("，", "").replace(" ", "").strip())
        except (ValueError, TypeError):
            return None
