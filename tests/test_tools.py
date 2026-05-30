"""Tests for tool layer: all tools + BaseTool."""
import asyncio
import os
import pytest
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from biohermes.pipeline.context import PipelineContext
from biohermes.tools.base import BaseTool, ToolResult
from biohermes.tools.mineru_parser import MinerUParser
from biohermes.tools.table_extractor import TableExtractor
from biohermes.tools.structure_extractor import StructureExtractor
from biohermes.tools.data_cleaner import DataCleaner
from biohermes.tools.report_generator import ReportGenerator


@pytest.fixture
def context():
    return PipelineContext()


# ─── BaseTool Tests ───

class TestBaseTool:
    def test_validate_args_empty_schema(self):
        class Dummy(BaseTool):
            name = "dummy"
            description = "test"
            async def execute(self, args, context):
                return ToolResult(success=True)

        d = Dummy()
        valid, err = d.validate_args({"anything": "ok"})
        assert valid is True

    def test_validate_args_required_missing(self):
        class Dummy(BaseTool):
            name = "dummy"
            description = "test"
            input_schema = {"required": ["file_path"]}
            async def execute(self, args, context):
                return ToolResult(success=True)

        d = Dummy()
        valid, err = d.validate_args({})
        assert valid is False
        assert "file_path" in err

    def test_validate_args_type_mismatch(self):
        class Dummy(BaseTool):
            name = "dummy"
            description = "test"
            input_schema = {"properties": {"count": {"type": "integer"}}}
            async def execute(self, args, context):
                return ToolResult(success=True)

        d = Dummy()
        valid, err = d.validate_args({"count": "not_int"})
        assert valid is False

    def test_tool_result_to_dict(self):
        tr = ToolResult(success=True, data={"key": "val"}, error="")
        d = tr.to_dict()
        assert d["success"] is True


# ─── MinerUParser Tests ───

class TestMinerUParser:
    def test_health_check_unavailable(self):
        parser = MinerUParser(api_url="http://localhost:99999")
        result = parser.health_check()
        assert result["available"] is False

    @pytest.mark.asyncio
    async def test_parse_no_file(self, context):
        parser = MinerUParser()
        result = await parser.execute({"file_path": ""}, context)
        assert result.success is False
        assert "file_path" in result.error

    @pytest.mark.asyncio
    async def test_parse_nonexistent_file(self, context):
        parser = MinerUParser()
        result = await parser.execute({"file_path": "/nonexistent/test.pdf"}, context)
        # Should fail gracefully
        assert result.success is False

    @pytest.mark.asyncio
    async def test_fallback_parse(self):
        pdf_path = "/home/zhidao-2/medgeclaw-migration/MedgeClaw/texput.pdf"
        if not os.path.exists(pdf_path):
            pytest.skip("Test PDF not available")
        parser = MinerUParser()
        result = await parser._fallback_parse(pdf_path)
        assert result["status"] == "success_fallback"
        assert len(result["content"]) > 0


# ─── TableExtractor Tests ───

class TestTableExtractor:
    def test_extract_from_markdown_basic(self):
        extractor = TableExtractor()
        md = """
| Name | Age | Score |
|------|-----|-------|
| Alice | 25 | 90 |
| Bob | 30 | 85 |
"""
        tables = extractor.extract_from_markdown(md)
        assert len(tables) == 1
        assert tables[0]["headers"] == ["Name", "Age", "Score"]
        assert tables[0]["row_count"] == 2
        assert tables[0]["col_count"] == 3

    def test_extract_from_markdown_multiple(self):
        extractor = TableExtractor()
        md = """
| A | B |
|---|---|
| 1 | 2 |

Some text

| C | D |
|---|---|
| 3 | 4 |
"""
        tables = extractor.extract_from_markdown(md)
        assert len(tables) == 2

    def test_extract_from_markdown_empty(self):
        extractor = TableExtractor()
        tables = extractor.extract_from_markdown("No tables here")
        assert len(tables) == 0

    def test_validate_consistency_pass(self):
        extractor = TableExtractor()
        table = {
            "headers": ["Item", "合计"],
            "rows": [["A", "100"], ["B", "200"], ["Total", "300"]],
        }
        issues = extractor.validate_consistency(table)
        assert len(issues) == 0

    def test_validate_consistency_fail(self):
        extractor = TableExtractor()
        table = {
            "headers": ["Item", "合计"],
            "rows": [["A", "100"], ["B", "200"], ["Total", "999"]],
        }
        issues = extractor.validate_consistency(table)
        assert len(issues) > 0
        assert any("999" in i for i in issues)

    def test_validate_consistency_empty_table(self):
        extractor = TableExtractor()
        issues = extractor.validate_consistency({})
        assert len(issues) == 0

    def test_validate_consistency_column_mismatch(self):
        extractor = TableExtractor()
        table = {
            "headers": ["A", "B", "C"],
            "rows": [["1", "2"]],  # 2 vs 3
        }
        issues = extractor.validate_consistency(table)
        assert any("cells vs" in i or "headers" in i for i in issues)

    @pytest.mark.asyncio
    async def test_execute_with_content(self, context):
        extractor = TableExtractor()
        context.add_parsed_result("test.md", {"content": "| A | B |\n|---|---|\n| 1 | 2 |"})
        result = await extractor.execute({}, context)
        assert result.success is True
        assert result.data["count"] == 1

    @pytest.mark.asyncio
    async def test_execute_no_content(self, context):
        extractor = TableExtractor()
        result = await extractor.execute({}, context)
        assert result.success is False


# ─── DataCleaner Tests ───

class TestDataCleaner:
    @pytest.mark.asyncio
    async def test_deduplicate(self, context):
        context.tables = [{
            "headers": ["A", "B"],
            "rows": [["1", "2"], ["1", "2"], ["3", "4"]],
            "row_count": 3, "col_count": 2,
        }]
        cleaner = DataCleaner()
        result = await cleaner.execute({"actions": ["deduplicate"]}, context)
        assert result.success is True
        assert context.tables[0]["row_count"] == 2

    @pytest.mark.asyncio
    async def test_validate_column_mismatch(self, context):
        context.tables = [{
            "headers": ["A", "B"],
            "rows": [["1", "2", "3"]],  # 3 cols vs 2 headers
            "row_count": 1, "col_count": 2,
        }]
        cleaner = DataCleaner()
        result = await cleaner.execute({"actions": ["validate"]}, context)
        assert result.success is True
        assert any("mismatch" in i for i in result.data["issues"])

    @pytest.mark.asyncio
    async def test_normalize_numbers(self, context):
        context.tables = [{
            "headers": ["Value"],
            "rows": [["1,234.56"], ["78%"]],
            "row_count": 2, "col_count": 1,
        }]
        cleaner = DataCleaner()
        result = await cleaner.execute({"actions": ["normalize"]}, context)
        assert result.success is True
        assert context.tables[0]["rows"][0][0] == "1234.56"
        assert context.tables[0]["rows"][1][0] == "0.78"

    @pytest.mark.asyncio
    async def test_deduplicate_unhashable(self, context):
        context.tables = [{
            "headers": ["A"],
            "rows": [["x"], ["y"]],
            "row_count": 2, "col_count": 1,
        }]
        cleaner = DataCleaner()
        result = await cleaner.execute({"actions": ["deduplicate"]}, context)
        assert result.success is True


# ─── StructureExtractor Tests ───

class TestStructureExtractor:
    @pytest.mark.asyncio
    async def test_extract_sections(self, context):
        context.add_parsed_result("test.md", {"content": "# Title\n## Section 1\nContent\n## Section 2\nMore"})
        extractor = StructureExtractor()
        result = await extractor.execute({}, context)
        assert result.success is True
        assert len(context.structures) > 0

    @pytest.mark.asyncio
    async def test_extract_no_content(self, context):
        extractor = StructureExtractor()
        result = await extractor.execute({}, context)
        assert result.success is True  # Graceful empty result
        assert result.data["count"] == 0


# ─── ReportGenerator Tests ───

class TestReportGenerator:
    @pytest.mark.asyncio
    async def test_generate_report(self, context):
        context.add_parsed_result("test.pdf", {"content": "test content", "status": "success"})
        context.tables = [{"headers": ["A"], "rows": [["1"]], "row_count": 1, "col_count": 1}]
        generator = ReportGenerator()
        result = await generator.execute({"task": "解析文档"}, context)
        assert result.success is True
        assert result.data is not None
