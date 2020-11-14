import hashlib
import json
from string import Template
from typing import Dict

from django.core.cache import DefaultCacheProxy, cache
from django.utils.translation import get_language

from common import functions as cf
from common.loggers import Logger


def translate(origin: str, lang: str = None, store: DefaultCacheProxy = None, params: dict = None) -> str:
    try:
        if store is None:
            store = cache
        if lang is None:
            lang = get_language() or cf.get_config("LANGUAGE_CODE")

        _store = _load_from_file(lang)
        text = _store.get(origin)

        # key = cache_key_for_i18n(lang, origin)
        # text = store.get(key)
        if text is not None and isinstance(text, bytes):
            text = text.decode("utf8")
        tmpl = Template(text or origin)
        return tmpl.safe_substitute(params or {})
    except Exception as err:
        Logger.error(__name__, f'Error translate "{origin}": {err}')
    return origin


def cache_key_for_i18n(lang: str, origin: str) -> str:
    key = hashlib.md5(origin.encode("utf8")).hexdigest()
    return f"I18N:{lang.upper()}:{key}"


def _load_from_file(lang: str) -> Dict[str, str]:
    project_root = cf.get_config("PROJECT_ROOT")
    filename = project_root.joinpath("_i18n", f"{lang}.json")
    if not filename.exists():
        Logger.warning(__name__, f"Translation file [{filename}] not exists")
        return {}
    try:
        with open(filename, "r") as f:
            return json.load(f)
    except Exception as err:
        Logger.warning(__name__, f"Error load translation from {filename} : {err}")
    return {}
