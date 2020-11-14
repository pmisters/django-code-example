from typing import Any, Dict

from django.template import Library
from django.utils import translation
from django.utils.html import format_html

from common.i18n import translate as _
from common import functions as cf

register = Library()


@register.simple_tag
def trans(origin, **kwargs):
    lang = translation.get_language()
    value = _(origin, lang, params=kwargs)
    return format_html(value)


@register.simple_tag
def trans_month(month: int, **kwargs):
    lang = translation.get_language()
    origin = f"common:month:{month}"
    value = _(origin, lang, params=kwargs)
    return format_html(value)


@register.simple_tag
def trans_week(week_day: int, **kwargs):
    lang = translation.get_language()
    origin = f"common:week:{week_day}"
    value = _(origin, lang, params=kwargs)
    return format_html(value)


@register.inclusion_tag("_menu.languages.html", takes_context=True)
def languages_menu(context) -> Dict[str, Any]:
    languages = []
    for code, __ in cf.get_config("LANGUAGES", []):
        languages.append(
            (code, _(f"common:language:{code}"), f"corporate/flags/{code}.png")
        )
    language_code = context["LANGUAGE_CODE"]
    return {
        "languages": languages,
        "language": _(f"common:language:{language_code}"),
        "language_flag": f"corporate/flags/{language_code}.png",
    }
