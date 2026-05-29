"""Document parsing API routes."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, UploadFile, File

from ..tools.mineru_parser import MinerUParser
from ..utils.file_utils import ensure_dir
from .. import config

router = APIRouter(prefix="/api/document", tags=["document"])

_upload_dir: Path = Path("logs") / "uploads"


@router.post("/parse")
async def parse_document(file: UploadFile = File(...)):
    parser = MinerUParser(config.MINERU_API_URL)
    ensure_dir(str(_upload_dir))
    file_path = _upload_dir / file.filename
    file_path.write_bytes(await file.read())
    result = await parser._parse(str(file_path))
    return result


@router.post("/batch")
async def batch_parse(files: list[UploadFile] = File(...)):
    parser = MinerUParser(config.MINERU_API_URL)
    ensure_dir(str(_upload_dir))
    file_paths = []
    for f in files:
        fp = _upload_dir / f.filename
        fp.write_bytes(await f.read())
        file_paths.append(str(fp))
    results = await parser.batch_parse(file_paths)
    return {"total": len(results), "results": results}
