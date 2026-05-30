"""Pipeline context for inter-step data passing."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PipelineContext:
    """Shared state accumulated across pipeline steps.

    Provides structured data flow between Judge→Select→Execute→Verify layers.
    Each tool reads from and writes to the context, enabling loose coupling.
    """
    files: list[str] = field(default_factory=list)
    parsed_results: dict[str, dict] = field(default_factory=dict)
    tables: list[dict] = field(default_factory=list)
    structures: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    errors: list[dict] = field(default_factory=list)
    _step_outputs: dict[int, Any] = field(default_factory=dict)

    def get_output(self, step_index: int) -> Any:
        """Get output from a specific step."""
        return self._step_outputs.get(step_index)

    def set_output(self, step_index: int, output: Any):
        """Set output for a specific step."""
        self._step_outputs[step_index] = output

    def add_parsed_result(self, filename: str, result: dict):
        """Add a parsed document result, keyed by filename."""
        if not isinstance(result, dict):
            return
        self.parsed_results[filename] = result

    def add_table(self, table: dict):
        """Add an extracted table."""
        if isinstance(table, dict):
            table.setdefault("row_count", len(table.get("rows", [])))
            table.setdefault("col_count", len(table.get("headers", [])))
            self.tables.append(table)

    def add_structure(self, structure: dict):
        """Add a structure extraction result."""
        if isinstance(structure, dict):
            self.structures.append(structure)

    def add_error(self, step_index: int, error: str):
        """Record an error from a specific step."""
        self.errors.append({"step": step_index, "error": str(error)})

    def get_content(self) -> str:
        """Get concatenated content from all parsed results."""
        parts = []
        for result in self.parsed_results.values():
            content = result.get("content", "")
            if content:
                parts.append(content)
        return "\n".join(parts)

    def has_parsed(self, filename: str = "") -> bool:
        """Check if a file has been parsed. Empty string checks any."""
        if not filename:
            return len(self.parsed_results) > 0
        return filename in self.parsed_results

    def summary(self) -> dict:
        """Return a summary of context state for logging/verification."""
        content_chars = sum(
            len(r.get("content", "")) for r in self.parsed_results.values()
        )
        return {
            "files": len(self.files),
            "parsed": len(self.parsed_results),
            "tables": len(self.tables),
            "structures": len(self.structures),
            "errors": len(self.errors),
            "content_chars": content_chars,
            "step_outputs": len(self._step_outputs),
        }
