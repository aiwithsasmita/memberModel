"""Client for a Databricks model serving / AI Gateway endpoint (OpenAI-compatible chat API)."""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from typing import Optional, Protocol


@dataclass
class LLMResponse:
    data: dict
    input_tokens: int = 0
    output_tokens: int = 0


class LLMClient(Protocol):
    def complete_json(self, endpoint: str, system: str, user: str, schema: dict,
                      temperature: float, max_tokens: int) -> LLMResponse: ...


def _extract_json(text: str) -> dict:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object in model output")
    return json.loads(text[start:end + 1])


class DatabricksLLMClient:
    """Uses the Databricks SDK to get an OpenAI client bound to the workspace's serving endpoints.

    Auth: inside Databricks it uses the notebook/job identity; in CI it uses DATABRICKS_HOST and
    DATABRICKS_TOKEN (or OAuth M2M: DATABRICKS_CLIENT_ID / DATABRICKS_CLIENT_SECRET) of sp-aidlc-agents.
    """

    def __init__(self, timeout: int = 120, max_retries: int = 3):
        self.max_retries = max_retries
        self._client = self._make_client(timeout)

    @staticmethod
    def _make_client(timeout: int):
        try:
            from databricks.sdk import WorkspaceClient
            return WorkspaceClient().serving_endpoints.get_open_ai_client()
        except Exception:
            from openai import OpenAI  # fallback: explicit host + token
            host = os.environ["DATABRICKS_HOST"].rstrip("/")
            return OpenAI(api_key=os.environ["DATABRICKS_TOKEN"],
                          base_url=f"{host}/serving-endpoints", timeout=timeout)

    def complete_json(self, endpoint, system, user, schema, temperature, max_tokens) -> LLMResponse:
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        formats = [{"type": "json_schema", "json_schema": schema}, {"type": "json_object"}, None]
        last_err: Optional[Exception] = None
        for fmt in formats:                       # degrade gracefully if structured output is unsupported
            for attempt in range(self.max_retries):
                try:
                    kwargs = dict(model=endpoint, messages=messages,
                                  temperature=temperature, max_tokens=max_tokens)
                    if fmt is not None:
                        kwargs["response_format"] = fmt
                    resp = self._client.chat.completions.create(**kwargs)
                    content = resp.choices[0].message.content or ""
                    usage = getattr(resp, "usage", None)
                    return LLMResponse(
                        data=_extract_json(content),
                        input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                        output_tokens=getattr(usage, "completion_tokens", 0) or 0,
                    )
                except Exception as e:  # noqa: BLE001
                    last_err = e
                    msg = str(e).lower()
                    if "response_format" in msg or "json_schema" in msg or "not supported" in msg:
                        break                     # try the next, simpler format
                    time.sleep(min(2 ** attempt, 10))
        raise RuntimeError(f"LLM call to {endpoint} failed: {last_err}")
