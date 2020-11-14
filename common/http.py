import json

import attr
from django import shortcuts
from django.http import HttpResponse


def json_response(data, status: int = 200) -> HttpResponse:
    resp = HttpResponse(
        json.dumps(data), content_type="application/json", status=status
    )
    resp["Access-Control-Allow-Origin"] = "*"
    return resp


@attr.attrs
class Render:
    """Injectable shortcut."""

    template_name = attr.attrib()
    request = attr.attrib()

    def do(self, context: dict = None) -> HttpResponse:
        if callable(self.template_name):
            template_name = self.template_name()
        else:
            template_name = self.template_name
        return shortcuts.render(self.request, template_name, context)


@attr.attrs
class RenderForbidden:
    request = attr.attrib()

    def do(self, context: dict = None) -> HttpResponse:
        template_name = "access_denied.html"
        return shortcuts.render(self.request, template_name, context)


@attr.attrs
class RenderServerError:
    request = attr.attrib()

    def do(self, context: dict = None) -> HttpResponse:
        template_name = "500.html"
        return shortcuts.render(self.request, template_name, context)
