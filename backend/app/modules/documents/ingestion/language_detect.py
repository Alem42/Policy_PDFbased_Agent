"""Statistical language detection via lingua (replaces keyword guessing).

lingua uses character n-gram language models, so it is far more robust than the
old substring heuristics — especially for short OCR fragments and mixed-language
policy documents. The detector is restricted to the languages our corpus
realistically contains to keep the memory footprint small.

Import is defensive: if lingua is not installed yet, detection degrades to None
and callers keep their own fallback rather than crashing ingestion.
"""

from __future__ import annotations

import logging
from functools import lru_cache

logger = logging.getLogger(__name__)

# Restrict the model set (memory scales with language count). Extend as needed.
_LANGUAGE_NAMES = [
    "ENGLISH",
    "FRENCH",
    "SPANISH",
    "GERMAN",
    "PORTUGUESE",
    "ITALIAN",
    "DUTCH",
    "BULGARIAN",
    "RUSSIAN",
    "UKRAINIAN",
    "ARABIC",
    "CHINESE",
    "JAPANESE",
    "KOREAN",
]

_MIN_CHARS = 20  # below this, detection is unreliable; return None


@lru_cache(maxsize=1)
def _detector():
    """Build and cache the lingua detector once. Returns None if unavailable."""
    try:
        from lingua import Language, LanguageDetectorBuilder

        languages = [getattr(Language, name) for name in _LANGUAGE_NAMES if hasattr(Language, name)]
        return LanguageDetectorBuilder.from_languages(*languages).build()
    except Exception as exc:
        logger.warning("lingua unavailable, language detection disabled: %s", exc)
        return None


def detect_language(text: str) -> str | None:
    """Return the English name of the dominant language, or None if uncertain."""
    sample = (text or "").strip()
    if len(sample) < _MIN_CHARS:
        return None
    detector = _detector()
    if detector is None:
        return None
    try:
        language = detector.detect_language_of(sample[:5000])  # a slice is enough
    except Exception as exc:
        logger.warning("Language detection failed: %s", exc)
        return None
    if language is None:
        return None
    # lingua enum name is UPPERCASE, e.g. "FRENCH" -> "French".
    return language.name.capitalize()
