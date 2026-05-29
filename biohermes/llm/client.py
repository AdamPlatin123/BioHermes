"""Unified LLM client (Anthropic-compatible API)."""
from __future__ import annotations

import json
import logging
from typing import Optional

import anthropic

from .. import config

logger = logging.getLogger("biohermes.llm")


class LLMClient:
    """Wraps Anthropic SDK for LLM calls."""

    def __init__(self, api_key: str = "", base_url: str = "", model: str = ""):
        self.api_key = api_key or config.LLM_API_KEY
        self.base_url = base_url or config.LLM_BASE_URL
        self.model = model or config.LLM_MODEL
        self._client: Optional[anthropic.Anthropic] = None

    @property
    def client(self) -> anthropic.Anthropic:
        if self._client is None:
            if not self.api_key:
                raise ValueError("LLM_API_KEY not configured")
            self._client = anthropic.Anthropic(
                api_key=self.api_key,
                base_url=self.base_url,
            )
        return self._client

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def chat(self, system: str, user: str, max_tokens: int = 2048) -> str:
        """Single-turn chat, returns text response."""
        if not self.available:
            raise ConnectionError("LLM not configured")
        try:
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            return resp.content[0].text
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            raise

    def chat_json(self, system: str, user: str, max_tokens: int = 2048) -> dict:
        """Chat expecting JSON response."""
        text = self.chat(system, user, max_tokens)
        # Extract JSON from possible markdown code blocks
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to find JSON array/object in text
            import re
            match = re.search(r'[\[{].*[\]}]', text, re.DOTALL)
            if match:
                return json.loads(match.group())
            raise ValueError(f"LLM did not return valid JSON: {text[:200]}")
