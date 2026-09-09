"""LLM provider abstraction.

Supports Anthropic, OpenAI, or a generic OpenAI-compatible endpoint (works with
Ollama, vLLM, LM Studio, etc.). With no key configured the system still works:
the pipeline falls back to heuristics and seeded knowledge (see seed.py), and
every LLM-derived claim is verified against source text either way.
"""
import json
import re

import httpx

from .config import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
    LLM_TIMEOUT,
    OPENAI_API_KEY,
    OPENAI_MODEL,
    active_provider,
)


class LLMError(RuntimeError):
    pass


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _extract_json(text: str):
    """Best-effort JSON extraction from a model response."""
    text = _strip_code_fence(text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Find the outermost JSON object/array in the text.
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        if start == -1:
            continue
        depth = 0
        for i in range(start, len(text)):
            if text[i] == opener:
                depth += 1
            elif text[i] == closer:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break
    raise LLMError("Could not parse JSON from model response")


class LLM:
    def __init__(self):
        self.provider = active_provider()
        self._client = httpx.Client(timeout=LLM_TIMEOUT)

    @property
    def available(self) -> bool:
        return self.provider != "none"

    def complete_json(self, system: str, user: str) -> dict:
        """Send a chat prompt, parse the response as JSON."""
        if self.provider == "anthropic":
            resp = self._client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                },
                json={
                    "model": ANTHROPIC_MODEL,
                    "max_tokens": 4096,
                    "system": system,
                    "messages": [{"role": "user", "content": user}],
                },
            )
        elif self.provider == "openai":
            resp = self._client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                json={
                    "model": OPENAI_MODEL,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
            )
        elif self.provider == "compatible":
            base = __import__("app.config", fromlist=["LLM_COMPAT_BASE"]).LLM_COMPAT_BASE
            resp = self._client.post(
                f"{base}/chat/completions",
                json={
                    "model": __import__("app.config", fromlist=["LLM_COMPAT_MODEL"]).LLM_COMPAT_MODEL,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
            )
        else:
            raise LLMError("No LLM provider configured")

        resp.raise_for_status()
        data = resp.json()
        if self.provider == "anthropic":
            text = data["content"][0]["text"]
        else:
            text = data["choices"][0]["message"]["content"]
        return _extract_json(text)
