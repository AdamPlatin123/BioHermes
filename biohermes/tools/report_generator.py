"""Report generation tool."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from .base import BaseTool, ToolResult
from ..pipeline.context import PipelineContext

logger = logging.getLogger("biohermes.tools")


class ReportGenerator(BaseTool):
    name = "report_generate"
    description = "Generate structured reports from processing results"

    async def execute(self, args: dict, context: PipelineContext) -> ToolResult:
        template = args.get("template", "markdown")
        title = args.get("title", "BioHermes Processing Report")

        if template == "json":
            report = self._json_report(title, context)
        else:
            report = self._markdown_report(title, context)

        context.set_output(args.get("_step_index", 0), {"report": report})
        return ToolResult(
            success=True, data={"report": report, "template": template},
            metadata={"format": template},
        )

    def _markdown_report(self, title: str, ctx: PipelineContext) -> str:
        lines = [
            f"# {title}",
            f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n",
            "## Summary\n",
            f"- Files processed: {len(ctx.parsed_results)}",
            f"- Tables extracted: {len(ctx.tables)}",
            f"- Structures found: {len(ctx.structures)}",
            f"- Errors: {len(ctx.errors)}\n",
        ]

        if ctx.tables:
            lines.append("## Tables\n")
            for i, table in enumerate(ctx.tables):
                lines.append(f"### Table {i + 1}: {table.get('row_count', 0)} rows")
                headers = table.get("headers", [])
                if headers:
                    lines.append("| " + " | ".join(headers) + " |")
                    lines.append("| " + " | ".join("---" for _ in headers) + " |")
                    for row in table.get("rows", [])[:20]:
                        lines.append("| " + " | ".join(str(c) for c in row) + " |")
                lines.append("")

        if ctx.errors:
            lines.append("## Errors\n")
            for err in ctx.errors:
                lines.append(f"- Step {err['step']}: {err['error']}")
            lines.append("")

        return "\n".join(lines)

    def _json_report(self, title: str, ctx: PipelineContext) -> str:
        report = {
            "title": title,
            "generated": datetime.now().isoformat(),
            "summary": ctx.summary(),
            "tables": ctx.tables,
            "structures": ctx.structures,
            "errors": ctx.errors,
        }
        return json.dumps(report, ensure_ascii=False, indent=2)
