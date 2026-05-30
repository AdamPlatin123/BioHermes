"""Base tool abstract class with validation support."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline.context import PipelineContext


@dataclass
class ToolResult:
    success: bool
    data: Any = None
    error: str = ""
    metadata: dict = field(default_factory=dict)

    def to_dict(self):
        return {
            "success": self.success,
            "data": self.data if not isinstance(self.data, (str, int, float, bool, type(None))) else self.data,
            "error": self.error,
            "metadata": self.metadata,
        }


class BaseTool(ABC):
    name: str = ""
    description: str = ""
    input_schema: dict = field(default_factory=dict)
    output_schema: dict = field(default_factory=dict)

    @abstractmethod
    async def execute(self, args: dict, context: PipelineContext) -> ToolResult:
        """Execute the tool with given args and pipeline context."""
        ...

    def validate_args(self, args: dict) -> tuple[bool, str]:
        """Validate args against input_schema.

        Returns (is_valid, error_message).
        If input_schema is empty, all args are accepted.
        """
        if not self.input_schema:
            return True, ""

        required = self.input_schema.get("required", [])
        for key in required:
            if key not in args:
                return False, f"Missing required argument: {key}"

        properties = self.input_schema.get("properties", {})
        for key, schema in properties.items():
            if key in args and schema:
                expected_type = schema.get("type", "")
                if expected_type == "string" and not isinstance(args[key], str):
                    return False, f"Argument '{key}' must be a string"
                elif expected_type == "integer" and not isinstance(args[key], int):
                    return False, f"Argument '{key}' must be an integer"
                elif expected_type == "boolean" and not isinstance(args[key], bool):
                    return False, f"Argument '{key}' must be a boolean"

        return True, ""
