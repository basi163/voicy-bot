import json
import os
from typing import Any

_translations: dict[str, dict] = {}

LANG_NAMES = {
    "ru": "Русский",
    "en": "English",
    "zh": "中文",
    "es": "Español",
}


def load_translations():
    locales_dir = os.path.join(os.path.dirname(__file__), "..", "locales")
    for lang in ("ru", "en", "zh", "es"):
        path = os.path.join(locales_dir, f"{lang}.json")
        with open(path, encoding="utf-8") as f:
            _translations[lang] = json.load(f)


def t(lang: str, key: str, **kwargs: Any) -> str:
    """Translate a key to the given language with optional formatting."""
    locale = _translations.get(lang) or _translations.get("ru", {})
    text = locale.get(key) or _translations.get("ru", {}).get(key, key)
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, ValueError):
            pass
    return text


def lang_name(code: str) -> str:
    return LANG_NAMES.get(code, code)
