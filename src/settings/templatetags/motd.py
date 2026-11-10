from django import template
from django.conf import settings
from django.template.base import Parser, Token
from django.template.context import Context

register: template.Library = template.Library()


def do_get_motd(parser: Parser, token: Token) -> "MotdNode":
    # split_contents() knows not to split quoted strings.
    tokens = token.split_contents()
    if len(tokens) != 1:
        raise template.TemplateSyntaxError(f"{tokens[0]!r} tag should have no arguments")
    return MotdNode()

class MotdNode(template.Node):
    def __init__(self) -> None:
        pass

    def render(self, context: Context) -> str:
        if not settings.SYSADMIN_MOTD_URL:
            return ''
        return f'<iframe src="{settings.SYSADMIN_MOTD_URL}" id="motd" onLoad="resize(\'motd\')" width="100%"> </iframe>'

register.tag('motd', do_get_motd)
