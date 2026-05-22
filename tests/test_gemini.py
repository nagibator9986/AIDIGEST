"""Gemini client import/degradation behaviour."""

from __future__ import annotations

import importlib.util

import pytest
from app.ai.gemini import GeminiClient


def test_gemini_client_missing_dependency_has_clear_error() -> None:
    if importlib.util.find_spec("google.genai") is not None:
        pytest.skip("google.genai is installed in this environment")
    with pytest.raises(RuntimeError, match="google-genai"):
        GeminiClient()
