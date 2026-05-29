"""Structured JSON logger for BioHermes."""
import json
import logging
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("biohermes")


class AgentLogger:
    """Structured session logger."""

    def __init__(self, log_dir: str = "logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def log_session(self, session):
        log_file = self.log_dir / f"{session.session_id}.json"
        log_file.write_text(
            json.dumps(session.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return str(log_file)

    def log_event(self, session_id: str, event: str, data: dict):
        entry = {"session_id": session_id, "event": event, "data": data, "ts": time.time()}
        event_file = self.log_dir / f"{session_id}_events.jsonl"
        with open(event_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
