"""MinerU document parser tool — supports MinerU v3 async task API."""
from __future__ import annotations

import json
import time
import logging
import urllib.request
import urllib.error
import asyncio
from pathlib import Path

from .base import BaseTool, ToolResult
from ..pipeline.context import PipelineContext

logger = logging.getLogger("biohermes.tools")

POLL_INTERVAL = 2   # seconds between status polls
MAX_POLL_TIME = 300  # max wait for task completion


class MinerUParser(BaseTool):
    name = "mineru_parse"
    description = "Parse document (PDF/DOCX/PPTX) to Markdown/JSON via MinerU API"

    def __init__(self, api_url: str = "http://10.123.45.9:8500"):
        self.api_url = api_url.rstrip("/")

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
        """Parse via MinerU v3 async task API, with PyMuPDF fallback."""
        logger.info(f"Parsing: {file_path}")
        filename = Path(file_path).name

        try:
            import requests as req_lib

            # Submit task via requests (proper multipart encoding)
            loop = asyncio.get_event_loop()
            with open(file_path, "rb") as fobj:
                resp = await loop.run_in_executor(
                    None,
                    lambda: req_lib.post(
                        f"{self.api_url}/file_parse",
                        files={"files": (filename, fobj, "application/octet-stream")},
                        data={
                            "return_md": "true" if output_format == "markdown" else "false",
                            "backend": "pipeline",
                            "formula_enable": str(enable_formula).lower(),
                            "table_enable": str(enable_table).lower(),
                        },
                        timeout=300,
                    )
                )

            if resp.status_code != 200:
                raise RuntimeError(f"MinerU API returned {resp.status_code}: {resp.text[:200]}")

            task_data = resp.json()

            # Sync response (has markdown directly)
            if "markdown" in task_data:
                return {
                    "content": task_data.get("markdown", ""),
                    "tables": task_data.get("tables", []),
                    "metadata": {"filename": filename, "format": output_format, "lang": lang or "auto"},
                    "status": "success",
                }

            # Async response: poll for result
            task_id = task_data.get("task_id", "")
            if not task_id:
                return {
                    "content": str(task_data.get("results", "")),
                    "tables": [], "metadata": {"filename": filename},
                    "status": "success",
                }

            return await self._poll_task(task_id, filename, output_format, lang)

        except ImportError:
            logger.warning("requests library not available, trying urllib fallback")
            return await self._urllib_parse(file_path, filename, output_format, lang, enable_formula, enable_table)
        except Exception as e:
            logger.warning(f"MinerU API error: {e}, using fallback")
            return await self._fallback_parse(file_path)

    async def _urllib_parse(self, file_path: str, filename: str,
                            output_format: str, lang: str,
                            enable_formula: bool, enable_table: bool) -> dict:
        """Fallback using urllib (less reliable multipart encoding)."""
        try:
            return await self._fallback_parse(file_path)
        except Exception as e:
            return {"content": "", "tables": [], "metadata": {}, "status": "error", "error": str(e)}

    async def _poll_task(self, task_id: str, filename: str,
                         output_format: str, lang: str) -> dict:
        """Poll MinerU async task until completion."""
        start = time.time()
        while time.time() - start < MAX_POLL_TIME:
            await asyncio.sleep(POLL_INTERVAL)

            try:
                req = urllib.request.Request(
                    f"{self.api_url}/tasks/{task_id}", method="GET"
                )
                with urllib.request.urlopen(req, timeout=30) as resp:
                    status_data = json.loads(resp.read())

                task_status = status_data.get("status", "")

                if task_status == "completed":
                    # Fetch the result
                    result_req = urllib.request.Request(
                        f"{self.api_url}/tasks/{task_id}/result", method="GET"
                    )
                    with urllib.request.urlopen(result_req, timeout=30) as resp:
                        result_data = json.loads(resp.read())

                    # Extract markdown from results (prefer result endpoint)
                    content = ""
                    results = result_data.get("results", {}) or status_data.get("results", {})
                    if isinstance(results, dict):
                        for fname, fdata in results.items():
                            if isinstance(fdata, dict):
                                content += fdata.get("md_content", fdata.get("markdown", ""))

                    if not content:
                        content = result_data.get("markdown", "")

                    logger.info(f"MinerU task {task_id} completed: {len(content)} chars")
                    return {
                        "content": content,
                        "tables": result_data.get("tables", []),
                        "metadata": {
                            "filename": filename, "format": output_format,
                            "lang": lang or "auto", "parser": "MinerU_v3",
                            "task_id": task_id,
                        },
                        "status": "success",
                    }

                elif task_status == "failed":
                    error = status_data.get("error", "Unknown error")
                    logger.error(f"MinerU task {task_id} failed: {error}")
                    return {
                        "content": "", "tables": [],
                        "metadata": {"filename": filename, "task_id": task_id},
                        "status": "error", "error": f"MinerU task failed: {error}",
                    }

                # Still processing
                logger.debug(f"MinerU task {task_id}: {task_status}")

            except Exception as e:
                logger.warning(f"Poll error for task {task_id}: {e}")
                continue

        return {
            "content": "", "tables": [],
            "metadata": {"filename": filename, "task_id": task_id},
            "status": "error", "error": f"MinerU task timed out after {MAX_POLL_TIME}s",
        }

    async def _fallback_parse(self, file_path: str) -> dict:
        """PyMuPDF local fallback."""
        logger.info(f"Using PyMuPDF fallback for: {file_path}")
        if not Path(file_path).exists():
            return {
                "content": "", "tables": [],
                "metadata": {"filename": Path(file_path).name, "parser": "none"},
                "status": "error", "error": f"File not found: {file_path}",
            }
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
