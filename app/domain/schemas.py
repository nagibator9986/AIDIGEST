"""Pydantic data-transfer objects used between layers.

These are pure data contracts — no ORM, no I/O. The Gemini structured-output
schema (:class:`GeminiVerdict`) is also defined here and handed directly to the
``google-genai`` SDK as a ``response_schema``.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.enums import NewsCategory
from app.utils.url import normalize_url


class RawItem(BaseModel):
    """A news item as produced by a collector, before persistence or scoring."""

    model_config = ConfigDict(frozen=True)

    title: str
    url: str
    source: str
    raw_content: str = ""
    external_id: str | None = None
    points: int | None = None
    published_at: datetime | None = None

    @field_validator("title", "raw_content")
    @classmethod
    def _strip(cls, value: str) -> str:
        return " ".join(value.split())

    @property
    def normalized_url(self) -> str:
        return normalize_url(self.url)

    def fingerprint_text(self) -> str:
        """Text used for fuzzy duplicate detection."""
        return self.title.lower()


class GeminiVerdict(BaseModel):
    """Structured response returned by the Gemini scorer.

    Passed verbatim to the SDK as ``response_schema`` — the field descriptions
    are effectively part of the prompt, so they are written instructively. The
    field order matters: ``reasoning`` comes first so the model justifies the
    verdict before committing to a number.
    """

    reasoning: str = Field(
        ...,
        description=(
            "Сначала продумай обоснование оценки: 1–2 предложения, почему "
            "именно такой балл. Оценка должна следовать из этого обоснования."
        ),
    )
    score: int = Field(
        ...,
        ge=1,
        le=10,
        description=(
            "Значимость 1–10 по калибровке из системной инструкции. "
            "Большинство новостей — 3–6; 7+ нужно заслужить; 9–10 — редкость."
        ),
    )
    category: NewsCategory = Field(..., description="Наиболее подходящая категория.")
    is_hype: bool = Field(
        ...,
        description="true, если это маркетинговый хайп или обёртка над чужим API.",
    )
    summary_ru: str = Field(
        ...,
        description=(
            "Короткое описание простым языком, 2–3 предложения: что это и "
            "почему важно. Без жаргона и слова «революционный»."
        ),
    )
    key_points_ru: list[str] = Field(
        ...,
        description=(
            "2–3 очень коротких факта или цифры (например: «Контекст: 1M "
            "токенов», «Доступно бесплатно»). Каждый — сжатая фраза."
        ),
    )
    utility_ru: str = Field(
        ...,
        description=(
            "1–2 коротких предложения: кому и чем это полезно на практике "
            "(можно указать роль — аналитику, менеджеру, разработчику)."
        ),
    )
