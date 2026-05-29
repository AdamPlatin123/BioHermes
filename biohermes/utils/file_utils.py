"""File validation and utility functions."""
import hashlib
from pathlib import Path

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".pptx", ".png", ".jpg", ".jpeg"}


def validate_file(file_path: str) -> tuple[bool, str]:
    """Check if file exists and is a supported format."""
    p = Path(file_path)
    if not p.exists():
        return False, f"File not found: {file_path}"
    if not p.is_file():
        return False, f"Not a file: {file_path}"
    if p.suffix.lower() not in SUPPORTED_EXTENSIONS:
        return False, f"Unsupported format: {p.suffix}"
    return True, "OK"


def file_hash(file_path: str) -> str:
    """SHA256 hash of file content."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def scan_directory(dir_path: str) -> list[str]:
    """Scan directory for supported document files."""
    p = Path(dir_path)
    if not p.exists():
        return []
    return sorted(
        str(f) for f in p.rglob("*")
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
    )


def ensure_dir(path: str) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p
