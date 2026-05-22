"""Enumerations shared across the domain, persistence and bot layers."""

from __future__ import annotations

from enum import StrEnum


class NewsStatus(StrEnum):
    """Lifecycle of a news item inside the processing pipeline."""

    RAW = "raw"  # collected, not yet scored
    PENDING_REVIEW = "pending_review"  # legacy — kept only for historical rows
    APPROVED = "approved"  # eligible for the next scheduled digest
    BREAKING = "breaking"  # must be pushed immediately, outside the schedule
    POSTED = "posted"  # already delivered in a digest
    REJECTED = "rejected"  # below threshold or rejected by a moderator
    FAILED = "failed"  # scoring failed irrecoverably


class NewsCategory(StrEnum):
    """High-level classification produced by the Gemini scorer."""

    MODEL_RELEASE = "model_release"
    TOOL = "tool"
    PAPER = "paper"
    INFRASTRUCTURE = "infrastructure"
    OTHER = "other"

    @property
    def emoji(self) -> str:
        return {
            NewsCategory.MODEL_RELEASE: "🧠",
            NewsCategory.TOOL: "🛠",
            NewsCategory.PAPER: "📄",
            NewsCategory.INFRASTRUCTURE: "⚙️",
            NewsCategory.OTHER: "✨",
        }[self]

    @property
    def title_ru(self) -> str:
        return {
            NewsCategory.MODEL_RELEASE: "Релиз модели",
            NewsCategory.TOOL: "Инструмент",
            NewsCategory.PAPER: "Исследование",
            NewsCategory.INFRASTRUCTURE: "Инфраструктура",
            NewsCategory.OTHER: "Прочее",
        }[self]


class DeliveryStatus(StrEnum):
    """Outcome of delivering one digest to one chat."""

    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"  # nothing to send
