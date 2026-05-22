from django import template
register = template.Library()
@register.filter
def list_item(lst, i):
    try:
        return lst[i]
    except:
        return None
