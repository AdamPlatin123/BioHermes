"""Structure extraction tool."""
from __future__ import annotations

import re
import logging
from .base import BaseTool, ToolResult
from ..pipeline.context import PipelineContext

logger = logging.getLogger("biohermes.tools")


class StructureExtractor(BaseTool):
    name = "structure_extract"
    description = "Extract structured information (sections, metadata, formulas) from documents"

    async def execute(self, args: dict, context: PipelineContext) -> ToolResult:
        content = args.get("content", "")
        if not content and context.parsed_results:
            content = next(iter(context.parsed_results.values()), {}).get("content", "")

        if not content:
            return ToolResult(success=False, error="No content to extract structure from")

        sections = self.extract_sections(content)
        metadata = self.extract_metadata(content)
        formulas = self.extract_formulas(content)

        result = {"sections": sections, "metadata": metadata, "formulas": formulas}
        context.add_structure(result)
        context.set_output(args.get("_step_index", 0), result)

        return ToolResult(
            success=True, data=result,
            metadata={"section_count": len(sections), "formula_count": len(formulas)},
        )

    def extract_sections(self, content: str) -> list[dict]:
        sections = []
        current = {"title": "Root", "level": 0, "content": ""}

        for line in content.split("\n"):
            header = re.match(r'^(#{1,6})\s+(.+)', line)
            if header:
                if current["content"].strip():
                    sections.append(current)
                level = len(header.group(1))
                current = {"title": header.group(2).strip(), "level": level, "content": ""}
            else:
                current["content"] += line + "\n"

        if current["content"].strip():
            sections.append(current)

        return sections

    def extract_metadata(self, content: str) -> dict:
        metadata = {}
        title_match = re.search(r'^#\s+(.+)', content, re.MULTILINE)
        if title_match:
            metadata["title"] = title_match.group(1).strip()

        metadata["char_count"] = len(content)
        metadata["line_count"] = content.count("\n") + 1
        return metadata

    def extract_formulas(self, content: str) -> list[str]:
        """Extract LaTeX formulas from content."""
        formulas = []
        # Block formulas: $$...$$
        for m in re.finditer(r'\$\$(.+?)\$\$', content, re.DOTALL):
            formulas.append(m.group(1).strip())
        # Inline formulas: $...$
        for m in re.finditer(r'(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)', content):
            formulas.append(m.group(1).strip())
        return formulas
