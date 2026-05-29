"""Pipeline context for inter-step data passing."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PipelineContext:
    """Shared state accumulated across pipeline steps."""
    files: list[str] = field(default_factory=list)
    parsed_results: dict[str, dict] = field(default_factory=dict)
    tables: list[dict] = field(default_factory=list)
    structures: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    errors: list[dict] = field(default_factory=list)
    _step_outputs: dict[int, Any] = field(default_factory=dict)

    def get_output(self, step_index: int) -> Any:
        return self._step_outputs.get(step_index)

    def set_output(self, step_index: int, output: Any):
        self._step_outputs[step_index] = output

    def add_parsed_result(self, filename: str, result: dict):
        self.parsed_results[filename] = result

    def add_table(self, table: dict):
        self.tables.append(table)

    def add_structure(self, structure: dict):
        self.structures.append(structure)

    def add_error(self, step_index: int, error: str):
        self.errors.append({"step": step_index, "error": error})

    def summary(self) -> dict:
        return {
            "files": len(self.files),
            "parsed": len(self.parsed_results),
            "tables": len(self.tables),
            "structures": len(self.structures),
            "errors": len(self.errors),
        }
