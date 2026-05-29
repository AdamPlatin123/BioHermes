"""Base tool abstract class."""
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
            "success": self.success, "error": self.error,
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

    def validate_args(self, args: dict) -> bool:
        return True
