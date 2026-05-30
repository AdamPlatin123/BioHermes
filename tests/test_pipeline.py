"""Tests for PipelineContext and data flow."""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from biohermes.pipeline.context import PipelineContext


class TestPipelineContext:
    def test_initial_state(self):
        ctx = PipelineContext()
        assert ctx.files == []
        assert ctx.parsed_results == {}
        assert ctx.tables == []
        assert ctx.structures == []
        assert ctx.errors == []

    def test_add_parsed_result(self):
        ctx = PipelineContext()
        ctx.add_parsed_result("test.pdf", {"content": "hello", "status": "success"})
        assert ctx.has_parsed("test.pdf")
        assert not ctx.has_parsed("other.pdf")
        assert ctx.has_parsed()  # Any parsed

    def test_add_parsed_result_not_dict(self):
        ctx = PipelineContext()
        ctx.add_parsed_result("test.pdf", "not a dict")
        assert not ctx.has_parsed("test.pdf")

    def test_add_table_auto_defaults(self):
        ctx = PipelineContext()
        ctx.add_table({"headers": ["A", "B"], "rows": [["1", "2"]]})
        assert len(ctx.tables) == 1
        assert ctx.tables[0]["row_count"] == 1
        assert ctx.tables[0]["col_count"] == 2

    def test_add_table_not_dict(self):
        ctx = PipelineContext()
        ctx.add_table("not a table")
        assert len(ctx.tables) == 0

    def test_add_structure(self):
        ctx = PipelineContext()
        ctx.add_structure({"type": "section", "title": "Intro"})
        assert len(ctx.structures) == 1

    def test_add_structure_not_dict(self):
        ctx = PipelineContext()
        ctx.add_structure("not a dict")
        assert len(ctx.structures) == 0

    def test_add_error(self):
        ctx = PipelineContext()
        ctx.add_error(0, "test error")
        assert len(ctx.errors) == 1
        assert ctx.errors[0]["step"] == 0

    def test_step_outputs(self):
        ctx = PipelineContext()
        ctx.set_output(0, {"result": "step 0"})
        ctx.set_output(1, {"result": "step 1"})
        assert ctx.get_output(0) == {"result": "step 0"}
        assert ctx.get_output(2) is None

    def test_get_content(self):
        ctx = PipelineContext()
        ctx.add_parsed_result("a.pdf", {"content": "hello"})
        ctx.add_parsed_result("b.pdf", {"content": "world"})
        assert ctx.get_content() == "hello\nworld"

    def test_get_content_empty(self):
        ctx = PipelineContext()
        assert ctx.get_content() == ""

    def test_summary(self):
        ctx = PipelineContext()
        ctx.files = ["a.pdf", "b.pdf"]
        ctx.add_parsed_result("a.pdf", {"content": "x" * 100})
        ctx.add_table({"headers": ["A"], "rows": [["1"]], "row_count": 1, "col_count": 1})
        ctx.set_output(0, {"done": True})

        summary = ctx.summary()
        assert summary["files"] == 2
        assert summary["parsed"] == 1
        assert summary["tables"] == 1
        assert summary["content_chars"] == 100
        assert summary["step_outputs"] == 1
        assert summary["errors"] == 0
