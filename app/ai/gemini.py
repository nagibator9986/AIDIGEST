"""Gemini client wrapper.

Wraps ``google-genai`` with three guarantees the rest of the app relies on:

* **Structured output** — the SDK is handed :class:`GeminiVerdict` as a
  ``response_schema``, so we always parse a typed object, never free text.
* **Resilience** — transient API failures are retried with exponential backoff.
* **Bounded concurrency** — scoring many items never opens more than a fixed
  number of simultaneous requests.
"""

from __future__ import annotations

import asyncio

try:
    from google import genai
    from google.genai import types
except ImportError as exc:  # pragma: no cover -- depends on local environment
    genai = None  # type: ignore[assignment]
    types = None  # type: ignore[assignment]
    _IMPORT_ERROR: ImportError | None = exc
else:
    _IMPORT_ERROR = None
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.ai.prompts import SCORING_SYSTEM_PROMPT, build_user_prompt
from app.config import get_settings
from app.domain.schemas import GeminiVerdict
from app.logging import get_logger

log = get_logger(__name__)

# Errors worth retrying — rate limits and transient server faults.
_RETRYABLE = ((genai.errors.APIError,) if genai is not None else ()) + (
    asyncio.TimeoutError,
    ConnectionError,
)


class GeminiClient:
    """Thin async wrapper around the Gemini structured-output API."""

    def __init__(self, *, max_concurrency: int = 5) -> None:
        if _IMPORT_ERROR is not None or genai is None or types is None:
            raise RuntimeError(
                "Gemini client is unavailable: install project dependencies "
                "including `google-genai` before running scoring."
            ) from _IMPORT_ERROR
        settings = get_settings()
        self._client = genai.Client(api_key=settings.gemini_api_key.get_secret_value())
        self._model = settings.gemini_model
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._config = types.GenerateContentConfig(
            system_instruction=SCORING_SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=GeminiVerdict,
            # A little spread helps the scorer discriminate rather than
            # anchoring every item to the same "safe" middling score.
            temperature=0.4,
            # Generous ceiling: Cyrillic summaries are token-heavy and a
            # truncated response yields invalid JSON.
            max_output_tokens=2048,
            # Disable "thinking": this is structured extraction, not a
            # reasoning task. Thinking tokens would otherwise eat into the
            # output budget and truncate the JSON.
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )

    async def score(self, *, source: str, title: str, url: str, content: str) -> GeminiVerdict:
        """Score a single item. Raises on unrecoverable failure."""
        prompt = build_user_prompt(source=source, title=title, url=url, content=content)
        async with self._semaphore:
            return await self._generate(prompt)

    @retry(
        retry=retry_if_exception_type(_RETRYABLE),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=2, min=4, max=60),
        reraise=True,
    )
    async def _generate(self, prompt: str) -> GeminiVerdict:
        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=prompt,
            config=self._config,
        )
        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, GeminiVerdict):
            return parsed
        # Fallback: the SDK returned text instead of a parsed object.
        text = getattr(response, "text", None)
        if not text:
            raise ValueError("Gemini returned an empty response")
        return GeminiVerdict.model_validate_json(text)
