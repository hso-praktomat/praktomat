from collections.abc import Sequence

from django import template

register: template.Library = template.Library()


@register.filter
def list_item(lst: Sequence[object], i: int) -> object | None:
    try:
        return lst[i]
    except:
        return None
