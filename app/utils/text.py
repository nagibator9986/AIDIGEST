"""Text helpers: keyword matching, truncation, Telegram MarkdownV2 escaping."""

from __future__ import annotations

import re

# Characters that must be escaped in Telegram MarkdownV2.
_MDV2_SPECIAL = r"_*[]()~`>#+-=|{}.!\\"
_MDV2_RE = re.compile(f"([{re.escape(_MDV2_SPECIAL)}])")

# Whole-word AI/ML relevance vocabulary used by keyword-filtered collectors.
AI_KEYWORDS: frozenset[str] = frozenset(
    {
        "ai",
        "ml",
        "llm",
        "llms",
        "gpt",
        "genai",
        "rag",
        "agent",
        "agents",
        "agentic",
        "transformer",
        "diffusion",
        "embedding",
        "embeddings",
        "fine-tune",
        "finetune",
        "fine-tuning",
        "inference",
        "quantization",
        "quantized",
        "openai",
        "anthropic",
        "claude",
        "gemini",
        "llama",
        "mistral",
        "deepseek",
        "qwen",
        "huggingface",
        "langchain",
        "llamaindex",
        "vllm",
        "ollama",
        "pytorch",
        "tensorflow",
        "neural",
        "multimodal",
        "vision-language",
        "vlm",
        "moe",
        "reasoning",
        "chatbot",
        "copilot",
        "machine learning",
        "deep learning",
        "model",
        "models",
        "dataset",
        "benchmark",
        "prompt",
        "tokenizer",
        "context window",
    }
)

_WORD_RE = re.compile(r"[a-z0-9][a-z0-9\-]*")


def escape_markdown_v2(text: str) -> str:
    """Escape *text* so it is safe inside a Telegram MarkdownV2 message."""
    return _MDV2_RE.sub(r"\\\1", text or "")


def is_ai_relevant(*chunks: str) -> bool:
    """True if any chunk mentions an AI/ML keyword (whole-word match)."""
    haystack = " ".join(chunks).lower()
    words = set(_WORD_RE.findall(haystack))
    if words & {kw for kw in AI_KEYWORDS if " " not in kw}:
        return True
    return any(phrase in haystack for phrase in AI_KEYWORDS if " " in phrase)


def truncate(text: str, limit: int, *, suffix: str = "…") -> str:
    """Truncate *text* to *limit* characters on a word boundary when possible."""
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[: limit - len(suffix)].rstrip()
    if " " in cut:
        cut = cut[: cut.rfind(" ")].rstrip()
    return cut + suffix


def clean_html(text: str) -> str:
    """Strip HTML tags and collapse whitespace (good enough for RSS summaries)."""
    no_tags = re.sub(r"<[^>]+>", " ", text or "")
    return " ".join(no_tags.split())
