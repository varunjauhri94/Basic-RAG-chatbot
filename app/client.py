"""Phase 7 — shared Groq API client with retry/backoff.

Both gate.py and generator.py import get_client() from here.
GROQ_API_KEY is loaded from .env via python-dotenv.
"""
from __future__ import annotations

import os
import time
from functools import lru_cache

from dotenv import load_dotenv
from groq import Groq, APIStatusError

load_dotenv()

_MAX_RETRIES = 3
_RETRY_STATUSES = {429, 500, 502, 503, 504}


@lru_cache(maxsize=1)
def get_client() -> Groq:
    key = os.environ.get("GROQ_API_KEY", "")
    if not key:
        raise EnvironmentError(
            "GROQ_API_KEY is not set. Add it to .env or export it as an env var."
        )
    return Groq(api_key=key)


def chat_with_retry(
    model: str,
    messages: list[dict],
    temperature: float = 0,
    max_tokens: int = 512,
    response_format: dict | None = None,
) -> str:
    """Call Groq chat completions with exponential-backoff retry on transient errors."""
    client = get_client()
    kwargs: dict = dict(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    if response_format:
        kwargs["response_format"] = response_format

    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            resp = client.chat.completions.create(**kwargs)
            return resp.choices[0].message.content or ""
        except APIStatusError as exc:
            if exc.status_code in _RETRY_STATUSES:
                last_exc = exc
                time.sleep(2 ** attempt)
                continue
            raise
    raise RuntimeError(f"Groq API failed after {_MAX_RETRIES} retries") from last_exc
