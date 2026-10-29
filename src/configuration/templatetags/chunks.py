from configuration.models import Chunk
from django import template
from django.core.cache import cache
from django.template.base import Parser as _Parser, Token as _Token
from django.template.context import Context as _Context

register = template.Library()

CACHE_PREFIX = "chunk_"

def do_get_chunk(parser: _Parser, token: _Token) -> "ChunkNode":
    # split_contents() knows not to split quoted strings.
    tokens = token.split_contents()
    if len(tokens) < 2 or len(tokens) > 3:
        raise template.TemplateSyntaxError("%r tag should have either 2 or 3 arguments" % (tokens[0],))
    tag_name, key = tokens[:2]
    try:
        cache_time = int(tokens[2]) if len(tokens) == 3 else 0
    except ValueError as error:
        raise template.TemplateSyntaxError("Chunk cache time must be an integer") from error
    # Check to see if the key is properly double/single quoted
    if not (key[0] == key[-1] and key[0] in ('"', "'")):
        raise template.TemplateSyntaxError("%r tag's argument should be in quotes" % tag_name)
    # Send key without quotes and caching time
    return ChunkNode(key[1:-1], cache_time)

class ChunkNode(template.Node):
    def __init__(self, key: str, cache_time: int | str = 0) -> None:
        self.key = key
        self.cache_time = cache_time

    def render(self, context: _Context) -> str:
        try:
            cache_key = CACHE_PREFIX + self.key
            c = cache.get(cache_key)
            if c is None:
                c = Chunk.objects.get(key=self.key)
                cache.set(cache_key, c, int(self.cache_time))
            if not isinstance(c, Chunk):
                raise TypeError(f"Invalid cached chunk for {self.key!r}")
            content = c.content
        except Chunk.DoesNotExist:
            content = ''
        return content

register.tag('chunk', do_get_chunk)
