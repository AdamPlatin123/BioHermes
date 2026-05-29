"""BioHermes Tool Registry — auto-discovers and registers all tools."""
from __future__ import annotations

from .base import BaseTool, ToolResult
from .mineru_parser import MinerUParser
from .table_extractor import TableExtractor
from .structure_extractor import StructureExtractor
from .data_cleaner import DataCleaner
from .report_generator import ReportGenerator

TOOL_REGISTRY: dict[str, type[BaseTool]] = {
    "mineru_parse": MinerUParser,
    "table_extract": TableExtractor,
    "structure_extract": StructureExtractor,
    "data_clean": DataCleaner,
    "report_generate": ReportGenerator,
}


def create_tools(mineru_api_url: str = "http://10.123.45.9:8500") -> dict[str, BaseTool]:
    """Instantiate all tools with configuration."""
    tools: dict[str, BaseTool] = {}
    for name, cls in TOOL_REGISTRY.items():
        if name == "mineru_parse":
            tools[name] = cls(api_url=mineru_api_url)
        else:
            tools[name] = cls()
    return tools
