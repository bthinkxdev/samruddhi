"""Catalog template helpers."""

from __future__ import annotations

from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def query_with(context, **kwargs) -> str:
    """Build a query string from the current request, overriding named params."""
    request = context["request"]
    params = request.GET.copy()
    for key, value in kwargs.items():
        if value is None or value == "":
            params.pop(key, None)
        else:
            params[key] = str(value)
    return params.urlencode()
