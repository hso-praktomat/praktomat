from django import template
from django.template.defaultfilters import stringfilter
from django.utils.safestring import mark_safe
from django.utils.html import escape
import re
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name, guess_lexer, guess_lexer_for_filename, ClassNotFound
from pygments.lexers._mapping import LEXERS


# This is a hack to register our Isabelle Lexer without patching pygments or using setuptools' entry_points.
LEXERS['IsarLexer'] = ('utilities.isar_lexer', 'Isabelle/Isar', ('isabelle',), ('*.thy',), ('text/x-isabelle',))

register = template.Library()

def get_lexer(value, arg):
    if arg is None:
        return guess_lexer(value)
    return guess_lexer_for_filename(arg, value) #get_lexer_by_name(arg)

@register.filter(name='highlight')
@stringfilter
def colorize(value, arg=None):
    try:
        return mark_safe(highlight(value, get_lexer(value, arg), HtmlFormatter()))
    except ClassNotFound:
        return mark_safe("<pre>%s</pre>" % escape(value))

@register.filter(name='highlight_table')
@stringfilter
def colorize_table(value, arg=None):
    try:
        return mark_safe(highlight(value, get_lexer(value, arg), HtmlFormatter(linenos='table')))
    except ClassNotFound:
        return mark_safe("<pre>%s</pre>" % escape(value))

# --- rendering of annotated solution diffs ----------------------------------
#
# The input is the output of difflib.Differ (see
# attestation.models.AnnotatedSolutionFile.content_diff): every line carries a
# two character prefix, one of "  ", "+ ", "- " or "? ".
#
# Rather than letting Pygments lex the diff *including* its markers and then
# repairing the generated HTML with regular expressions, the markers are
# stripped before highlighting:
#   1. Pygments only ever sees plain source code. With nowrap=True it returns
#      exactly one HTML snippet per input line.
#   2. The line number column and the code column are assembled here, where the
#      diff markers are still known, so no generated HTML has to be parsed.

# css class per difflib line marker
DIFF_LINE_CLASSES = {'+': 'added', '-': 'removed'}

# css class per character marker of a difflib "? " hint line
DIFF_CHAR_CLASSES = {'+': 'addedChar', '-': 'deletedChar', '^': 'changedChar'}

# One "visible" character of highlighted output: either an HTML entity
# (Pygments escapes &, < and >) or a single character.
rx_html_char = re.compile(r'&(?:\w+|#x?[0-9a-fA-F]+);|.', re.DOTALL)


def _split_diff(diff):
    """Split difflib.Differ output into [marker, text, char_markers] records.

    A "? " line does not describe a line of its own, it annotates the preceding
    line column by column, so it is merged into that line's record.
    """
    records = []
    for raw in diff.splitlines():
        marker, text = (raw[:1] or ' '), raw[2:]
        if marker == '?':
            if records:
                records[-1][2] = text
            continue
        records.append([marker, text, ''])
    return records


def _highlight_lines(texts, filename):
    """Highlight the given source lines, returning one HTML snippet per line."""
    source = "\n".join(texts)
    try:
        lexer = get_lexer(source, filename)
    except ClassNotFound:
        return [escape(text) for text in texts]

    lines = highlight(source, lexer, HtmlFormatter(nowrap=True)).split("\n")
    if lines and lines[-1] == '':
        lines.pop()     # trailing newline appended by Pygments
    if len(lines) != len(texts):
        # Some lexers do not preserve the line structure (e.g. the Isabelle
        # lexer). Highlighting would desynchronise the diff markers, so fall
        # back to unhighlighted but correctly aligned output.
        return [escape(text) for text in texts]
    return lines


def _mark_characters(html_line, char_markers):
    """Wrap the characters marked by a difflib "? " line in a span.

    char_markers holds one character per column of the *plain text* line, while
    the highlighted line additionally contains tags (skipped) and HTML entities
    (counted as a single character).
    """
    result = []
    column = 0
    pos = 0
    while pos < len(html_line):
        if html_line[pos] == '<':
            end = html_line.find('>', pos)
            if end < 0:
                result.append(html_line[pos:])
                break
            result.append(html_line[pos:end + 1])
            pos = end + 1
            continue

        # Collect all following characters that are marked the same way, so
        # that one span is enough for a whole marked word.
        chars = []
        css_class = DIFF_CHAR_CLASSES.get(char_markers[column] if column < len(char_markers) else ' ')
        while pos < len(html_line) and html_line[pos] != '<':
            marker = char_markers[column] if column < len(char_markers) else ' '
            if DIFF_CHAR_CLASSES.get(marker) != css_class:
                break
            match = rx_html_char.match(html_line, pos)
            chars.append(match.group())
            column += 1
            pos = match.end()
        text = "".join(chars)
        result.append('<span class="%s">%s</span>' % (css_class, text) if css_class else text)
    return "".join(result)


@register.filter(name='highlight_diff_table')
@stringfilter
def colorize_diff_table(value, arg=None):
    """Render difflib.Differ output as a syntax highlighted table."""
    records = _split_diff(value)
    if not records:
        return mark_safe('')

    html_lines = _highlight_lines([text for _, text, _ in records], arg)

    code = []
    for (marker, _text, char_markers), html_line in zip(records, html_lines):
        if char_markers:
            html_line = _mark_characters(html_line, char_markers)
        css_class = DIFF_LINE_CLASSES.get(marker)
        if css_class:
            # The div is a block element and therefore already ends the line.
            # An empty one would collapse, so keep a zero width space in it.
            code.append('<div class="changed %s">%s</div>' % (css_class, html_line or '&#8203;'))
        else:
            code.append(html_line + "\n")

    linenos = "\n".join('<span class="normal">%d</span>' % no for no in range(1, len(records) + 1))

    return mark_safe(
        '<table class="highlighttable"><tr>'
        '<td class="linenos"><div class="linenodiv"><pre>%s</pre></div></td>'
        '<td class="code"><div class="highlight"><pre>%s</pre></div></td>'
        '</tr></table>' % (linenos, "".join(code))
    )
