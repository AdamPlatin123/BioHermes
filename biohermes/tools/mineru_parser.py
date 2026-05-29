"""MinerU document parser tool."""
from __future__ import annotations

import json
import logging
import urllib.request
import urllib.error
import asyncio
from pathlib import Path

from .base import BaseTool, ToolResult
from ..pipeline.context import PipelineContext

logger = logging.getLogger("biohermes.tools")


class MinerUParser(BaseTool):
    name = "mineru_parse"
    description = "Parse document (PDF/DOCX/PPTX) to Markdown/JSON via MinerU API"

    def __init__(self, api_url: str = "http://10.123.45.9:8500"):
        self.api_url = api_url

    def health_check(self) -> dict:
        try:
            req = urllib.request.Request(f"{self.api_url}/health", method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                return {"available": True, "details": json.loads(resp.read())}
        except Exception as e:
            return {"available": False, "error": str(e)}

    async def execute(self, args: dict, context: PipelineContext) -> ToolResult:
        file_path = args.get("file_path", "")
        output_format = args.get("output_format", "markdown")
        enable_formula = args.get("enable_formula", True)
        enable_table = args.get("enable_table", True)
        lang = args.get("lang", "")

        if not file_path:
            return ToolResult(success=False, error="file_path is required")

        result = await self._parse(file_path, output_format, lang, enable_formula, enable_table)

        if result["status"] in ("success", "success_fallback"):
            filename = Path(file_path).name
            context.add_parsed_result(filename, result)
            context.set_output(args.get("_step_index", 0), result)
            return ToolResult(success=True, data=result, metadata={"parser": result.get("status")})

        return ToolResult(success=False, error=result.get("error", "Parse failed"), data=result)

    async def _parse(self, file_path: str, output_format: str = "markdown",
                     lang: str = "", enable_formula: bool = True,
                     enable_table: bool = True) -> dict:
        logger.info(f"Parsing: {file_path}")

        try:
            boundary = "----BioHermesBoundary"
            with open(file_path, "rb") as f:
                file_data = f.read()

            filename = Path(file_path).name
            body = (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="files"; filename="{filename}"\r\n'
                f"Content-Type: application/octet-stream\r\n\r\n"
            ).encode() + file_data + f"\r\n--{boundary}\r\n".encode()

            for name, value in [
                ("return_md", "true" if output_format == "markdown" else "false"),
                ("backend", "pipeline"),
                ("formula_enable", str(enable_formula).lower()),
                ("table_enable", str(enable_table).lower()),
            ]:
                body += (
                    f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                    f"{value}\r\n--{boundary}\r\n"
                ).encode()
            body += b"--\r\n"

            req = urllib.request.Request(
                f"{self.api_url}/file_parse",
                data=body,
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=300) as resp:
                result = json.loads(resp.read())

            return {
                "content": result.get("markdown", ""),
                "tables": result.get("tables", []),
                "metadata": {
                    "filename": filename, "format": output_format,
                    "lang": lang or "auto",
                },
                "status": "success",
            }

        except urllib.error.URLError:
            logger.warning("MinerU API unavailable, using fallback")
            return await self._fallback_parse(file_path)
        except Exception as e:
            logger.error(f"Parse error: {e}")
            return {"content": "", "tables": [], "metadata": {}, "status": "error", "error": str(e)}

    async def _fallback_parse(self, file_path: str) -> dict:
        logger.info(f"Using PyMuPDF fallback for: {file_path}")
        try:
            import fitz
            doc = fitz.open(file_path)
            content = ""
            for page in doc:
                content += page.get_text() + "\n"
            doc.close()
            return {
                "content": content, "tables": [],
                "metadata": {"filename": Path(file_path).name, "parser": "PyMuPDF_fallback"},
                "status": "success_fallback",
            }
        except ImportError:
            return {
                "content": f"[降级解析] {Path(file_path).name}",
                "tables": [], "metadata": {"parser": "none"},
                "status": "degraded",
            }

    async def batch_parse(self, file_paths: list[str], max_concurrent: int = 3) -> list[dict]:
        semaphore = asyncio.Semaphore(max_concurrent)

        async def _parse_one(fp):
            async with semaphore:
                return await self._parse(fp)

        tasks = [_parse_one(fp) for fp in file_paths]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return [
            r if not isinstance(r, Exception) else {"status": "error", "error": str(r)}
            for r in results
        ]
