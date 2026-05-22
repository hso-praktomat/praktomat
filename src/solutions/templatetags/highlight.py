from django import template
from django.template.defaultfilters import stringfilter
from django.utils.safestring import mark_safe
from django.utils.html import escape
import re
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name, guess_lexer, guess_lexer_for_filename, ClassNotFound
from pygments.lexers._mapping import LEXERS
from pygments import __version__ as pygments_version

import logging
logger = logging.getLogger(__name__)


# This is a hack to register our Isabelle Lexer without patching pygments or using setuptools' entry_points.
LEXERS['IsarLexer'] = ('utilities.isar_lexer', 'Isabelle/Isar', ('isabelle',), ('*.thy',), ('text/x-isabelle',))

register = template.Library()

def get_lexer(value, arg):
    if arg is None:
        logger.debug("RH: guess_lexer: %s"%(guess_lexer(value)))
        return guess_lexer(value)
    logger.debug("RH: guess_lexer_for_filename: %s"%(guess_lexer_for_filename(arg, value)))
    return guess_lexer_for_filename(arg, value) #get_lexer_by_name(arg)

def _with_linenos(s):
    return "\n".join(
        ["%4d: %r" % (i, line) for i, line in enumerate(s.splitlines(True), start=1)]
    )
    
@register.filter(name='highlight')
@stringfilter
def colorize(value, arg=None):
    try:
        logger.debug("RH Output lexer HtmlFormatter : \n *********\n%s\n ********\n"%(_with_linenos(mark_safe(highlight(value, get_lexer(value, arg), HtmlFormatter())))))
        return mark_safe(highlight(value, get_lexer(value, arg), HtmlFormatter()))
    except ClassNotFound:
        logger.debug("RH Output lexer ClassNotFound : \n *********\n%s\n ********\n"%(_with_linenos(mark_safe("<pre>%s</pre>" % escape(value)))))
        return mark_safe("<pre>%s</pre>" % escape(value))

# Match am Zeilenanfang:
# optional: <span></span>
# dann: <span class="o">+</span> bzw mit - oder ?
RX_LINE_START_DIFFOP = re.compile(
    r'(?P<emptyspan><span></span>)?'
    r'(?P<opspan><span class="o">(?P<pmq>[+\-?])</span>)'
)

# Diff-Zeilenanfang aus difflib: genau das erste Zeichen ist typischerweise ' ', '+', '-', '?'
RX_DIFF_PREFIX = re.compile(r'^([ \t+\-?])')

# Kommentarzeilen sind manchmal nicht richtig von ihren Diff-Markern befreit, vermutlich eine unpassende Anwendung von Pygments.
RX_COMMENTSPAN_WITH_MARKER = re.compile(r'<span class="(cm|c1)">([+\-?])(.*?)(</span>)')

@register.filter(name="fix_table_code")
def workaround_fix_table_code(value, original_diff):
    """
    value: Output von highlight_table(...)
    original_diff: anotfile.content_diff (zusätzliches Argument)

    Für JEDE Code-Zeile in der Code-Spalte:
      - prüfe die korrespondierende Zeile in original_diff
      - wenn sie mit +, - oder ? beginnt, dann klassifiziere in der Highlight-Zeile
        das führende <span class="o">+</span>/<span class="o">-</span>/<span class="o">?</span>
        zu <span class="diffop">...</span> um.
      - wenn die Diff-Zeile mit Leerzeichen beginnt: keine Änderung
    
    Somit werden in value in der Code-Spalte der highlighttable pro Zeile ersetzt das erste Aufkommen von
           <span class="o">+</span> durch <span class="diffop">+</span>
     sowie <span class="o">-</span> durch <span class="diffop">-</span>
     und   <span class="o">?</span> durch <span class="diffop">?</span>
    wenn in original_diff in gleichen Zeile als erstes Zeichen ein +,-,? steht.
    Falls in original_diff in der gleichen Zeile als erstes Zeichen ein Leerzeichen steht, dann findet keine Ersetzung statt.
 
    Funktioniert mit beiden Pygments-Varianten (Whitespace als Text oder <span class="w">...</span>).
    """
    
    html = "" if value is None else str(value)
    diff_text = "" if original_diff is None else str(original_diff)
    diff_lines = diff_text.splitlines()

    m = re.search(r'(<td class="code">)(.*?)(</td>)', html, flags=re.DOTALL)
    if not m:
        return mark_safe(html)

    code_inner = m.group(2)
    code_lines = code_inner.splitlines(True)

    out_lines = []
    di = 0

    for cl in code_lines:
        # Nur Zeilen zählen, die wirklich Codezeilen sind
        if "<span></span>" not in cl and not cl.lstrip().startswith("<span"):
            out_lines.append(cl)
            continue

        if di >= len(diff_lines):
            out_lines.append(cl)
            continue

        dl = diff_lines[di]
        di += 1

        md = RX_DIFF_PREFIX.match(dl)
        if md:
            marker = md.group(1)
            if marker in ["+", "-", "?"]:
                # Ersetze nur, wenn der Operator im HTML auch derselbe ist
                def _repl(mm):
                    pmq = mm.group("pmq")
                    if pmq != marker:
                        return mm.group(0)
                    # optionales <span></span> beibehalten
                    emptyspan = mm.group("emptyspan") or ""
                    # optionales <span></span> entfernen
                    emptyspan = ""
                    return '%s<span class="diffop">%s</span>' % (emptyspan, pmq)

                cl = RX_LINE_START_DIFFOP.sub(_repl, cl, count=1)
                if di > 1 and not cl.startswith("<span class=\"diffop\">"):
                    #logger.debug("DIFF-Line %d has marker : %s \nOutline would be : %s \n<<<<<<<<<<<<<FIXME ---- FIXME ----- FIXME ----FIXME>>>>>>>>>>>\n"%(di, marker,cl)) 
                    mc = RX_COMMENTSPAN_WITH_MARKER.match(cl)

                    if not mc:
                        return cl
                    
                    if mc.group(2) != marker:
                        return cl
                    
                    cs = mc.group(1)          # cm oder c1
                    rest = mc.group(3)         # alles nach dem Marker (inkl. evtl. führendem Leerzeichen)
                    end = mc.group(4)
                    cl= '<span class="diffop">%s</span><span class="%s">%s%s\n' % (marker, cs, rest, end)
                    #logger.debug("FIXED-Line : [ %s ]"%(cl)) 
        #logger.debug(">>>> appending [ %s ]"%(cl))
        out_lines.append(cl)

    fixed_code_inner = "".join(out_lines)
    fixed_html = html[:m.start(2)] + fixed_code_inner + html[m.end(2):]

    logger.debug(
        "\n***************\nCODE_INNER\n***************\n%s\n***************\n"
        "FIXED_CODE_INNER\n***************\n%s\n***************\n"
        % (_with_linenos(code_inner), _with_linenos(fixed_code_inner))
    )

    return mark_safe(fixed_html)

@register.filter(name='highlight_table')
@stringfilter
def colorize_table(value,arg=None):
    logger.debug("RH: parameter value is \n ********** \n%s\n *********** \n"%(_with_linenos(value)))
    try:
        logger.debug("RH Output HtmlFormatter : \n *********\n%s\n ********\n"%(_with_linenos(mark_safe(highlight(value, get_lexer(value, arg), HtmlFormatter(linenos='table'))))))
        return mark_safe(highlight(value, get_lexer(value, arg), HtmlFormatter(linenos='table')))
    except ClassNotFound:
        logger.debug("RH Output ClassNotFound : \n *********\n%s\n ********\n"%(_with_linenos(mark_safe("<pre>%s</pre>" % escape(value)))))
        return mark_safe("<pre>%s</pre>" % escape(value))

rx_diff_pm = re.compile(r'^(?P<first_line>\d*</pre></div></td><td class="code"><div class="highlight"><pre>)?(?P<line>(<span class=".*?">)?(?P<plusminus>\+|-).*?)(?P<endtag></pre>)?$')
rx_diff_questionmark = re.compile(r'(?P<line>(<span class="\w*">)?\?.*$)')
rx_tag = re.compile(r'^(<[^<]*>)+')
rx_char = re.compile(r'^(&\w+;|.)')
rx_diff_pm = re.compile(
    r'^'
    # Optionaler "first_line"-Prefix: Übergang von der linken Linenumber-Spalte
    # zur rechten Code-Spalte (kommt typischerweise nur am Beginn des <pre>-Blocks vor).
    r'(?P<first_line>'
        r'(?:'
            # Zeilennummer, je nach Pygments-Version entweder:
            #   23 (älter)
            # oder:
            #   <span class="normal">23</span> (neuer)
            r'(?:<span class="normal">)?\d+(?:</span>)?'

            # Danach der HTML-Übergang von </pre> (linenos) zur Code-Zelle und Start des <pre>.
            # Pygments-Varianten:
            #   <td class="code"><div class="highlight"><pre>   (älter)
            #   <td class="code"><div><pre>                   (neuer)
            r'</pre></div></td><td class="code"><div(?: class="highlight")?><pre>'
        r')?'
    r')'

    # "line": eigentliche Diff-Zeile, beginnt *strikt* mit einem diffop-Span dafür sorgt die Filter-Funktion workaround_fix_table_code
    #   <span class="diffop">+</span>...
    # oder
    #   <span class="diffop">-</span>...
    r'(?P<line>'
        r'<span class="diffop">'
            # plusminus: das eigentliche Diff-Markierungszeichen (+ oder -)
            r'(?P<plusminus>[+\-])'
        r'</span>'
        # Rest der Zeile (Highlighting/Text/weitere Spans etc.)
        r'.*?'
    r')'

    # Optionaler End-Tag, falls die Zeile direkt am Ende des <pre>-Blocks endet.
    r'(?P<endtag></pre>)?'
    r'$'
)


def count_diffop_question_lines(text):
    """
    Counts lines that contain the substring: <span class="diffop">?</span>
    """
    if text is None:
        return 0
    substring = '<span class="diffop">?</span>'
    return sum(1 for line in str(text).splitlines() if substring in line)


@register.filter
def highlight_diff(value):
    "enclose highlighted lines beginning with an +-? in a span"
    result = ""
    prevline = None
    logger.debug("RH: ---Pygments: [%s]"%(pygments_version))
    
    # we need to count questionmark-lines, because we will highlighting innerline changes using colors
    # and the cell containing the colored diff-code gets fewer lines than the diff-code without color has.
    # Therefor the number of questionmark-lines in uncolored diff-code determines how much lines
    # we have to reduce in the linenumber cell.
    
    number_of_questionmarklines = count_diffop_question_lines(value)
    logger.debug("RH: highlight_diff: number of questionmark lines = %d"%number_of_questionmarklines)

    logger.debug("RH: highlight_diff parameter value is \n ********** \n%s\n *********** \n"%(_with_linenos(value)))    
    m = re.search(r'(<td class="linenos">)(.*?)(</td>)', value, flags=re.DOTALL)
    linenos_inner = m.group(2)
    linenos_lines = linenos_inner.splitlines(True)
    number_of_lineos_lines = sum (1 for line in linenos_lines)
    number_of_needed_lines = number_of_lineos_lines - number_of_questionmarklines
    linenos_lines[number_of_needed_lines-1]=linenos_lines[number_of_lineos_lines-1]
    
    # Fall 1: <span class="normal">29</span>...
    # Fall 2: 29</pre></div>...
    # in both cases replace the number , i.e. 29, with number_of_needed_lines

    m = re.match(r'^(?P<prefix>(?:<span class="normal">)?)'
             r'(?P<num>\d+)'
             r'(?P<postfix>(?:</span>)?.*)$',
             linenos_lines[number_of_needed_lines - 1])
    if m:
       linenos_lines[number_of_needed_lines - 1] = "%s%d%s" % (m.group("prefix"), number_of_needed_lines, m.group("postfix"))
    
    
    new_linenos = "".join(linenos_lines[:number_of_needed_lines])
    logger.debug("\n*********\nNummernspalte:\n%s\n*********\n"%(_with_linenos(linenos_inner)))
    logger.debug("\n*********\nNeu Nummernspalte:\n%s\n*********\n"%(_with_linenos(new_linenos)))
    
    # originale Zeilennummerspalte in value durch verkürzte Zeilennummerspalte ersetzen.
    new_value = re.sub(
        r'(<td class="linenos">).*?(</td>)',
        r'\1%s\2' % new_linenos,
        value,
        count=1,
        flags=re.DOTALL
    )
    logger.debug("\n*********\nnew_value mit berichtigter Zeilennummerspalte:\n%s\n*********\n"%(_with_linenos(new_value)))
    value=new_value
    for line in value.splitlines(1):
        #logger.debug("RH: Inside splitlines.")
        #logger.debug("RH: line = [%s]"%(str(line)))
        m1 = rx_diff_questionmark.match(line)
        if m1:
            #logger.debug("RH: Questionmark line found")
            # We have a ? line. Instead of printing it, we annotate the previous line with the markers, which can be -, ^ or +
            # First remove newline from the end (or just all whitespace, does not hurt)
            line = line.rstrip()
            while line:
                #logger.debug(
                #            "RH:  line after rstrip is : [%s]",
                #            str(line)
                #)
                # First strip all leading tags from both strings
                m2 = rx_tag.match(line)
                if m2:
                    assert m2.end() > 0
                    line = line[m2.end():]
                    continue

                m2 = rx_tag.match(prevline)
                if m2:
                    assert m2.end() > 0
                    result += m2.group()
                    prevline = prevline[m2.end():]
                    continue
                #logger.debug("RH: line is [%s]"%(line))
                #logger.debug("RH: prevline is [%s]"%(prevline))

                # First character on both strings is a proper character
                cml = rx_char.match(line)
                assert cml, "regex rx_tag failed to match on non-empty string"
                cmpl = rx_char.match(prevline)
                if not cmpl:
                    # This can only happen if the syntax highlighter changes the number of symbols (e.g. the Isabelle syntax highlighter)
                    #assert cmpl, ("highlight_diff: previous line ended before ? marker. line: \"%s\", prevline: \"%s\"" % (line, prevline))
                    line = line[cml.end():]
                    continue

                lc = cml.group()
                plc = cmpl.group()

                if lc == '+':
                    #logger.debug(
                    #        "RH: highlight found +  : lc = [%s] , plc = [%s]",
                    #        str(lc),
                    #        str(plc)
                    #    )
                    result += "<span class=\"addedChar\">%s</span>" % plc
                elif lc == '-':
                    #logger.debug(
                    #        "RH: highlight found -  : lc = [%s] , plc = [%s]",
                    #        str(lc),
                    #        str(plc)
                    #    )
                    result += "<span class=\"deletedChar\">%s</span>" % plc
                elif lc == '^':
                    #logger.debug(
                    #        "RH: highlight found ^  : lc = [%s] , plc = [%s]",
                    #        str(lc),
                    #        str(plc)
                    #    )
                    result += "<span class=\"changedChar\">%s</span>" % plc
                elif lc == ' ' or lc == '?' or lc == '\t':
                    result += plc
                else:
                    assert False, ("Unexpected character in diff indicator line: \"%s\"" % lc)
                    result += plc[0]
                line = line[cml.end():]
                prevline = prevline[cmpl.end():]
            result += prevline
            prevline = None
        else:
            #logger.debug("RH: NO Questionmark line")
            if prevline is not None:
                result += prevline
            #logger.debug(
            #                "RH: highlight my line is : [%s]",
            #                str(line)
            #    )
            m = rx_diff_pm.match(line)
            if m:
                if m.group('first_line'):
                   # logger.debug(
                   #         "RH: FIRST LINE"
                   #     )
                    result += m.group('first_line')
                if m.group('plusminus') == '+':
                   # logger.debug(
                   #         "RH: PLUSMINUS +"
                   #     )
                    extra_class = "added"
                elif m.group('plusminus') == '-':
                   # logger.debug(
                   #         "RH: PLUSMINUS -"
                   #     )
                    extra_class = "removed"
                #logger.debug("RH: line : [%s]"%(line))
                prevline = "<div class='changed %s'>%s</div>" % (extra_class, m.group('line'))
                #logger.debug("RH: prevline = [%s]"%(prevline))
                if m.group('endtag'):
                    prevline += m.group('endtag')
            else:
                prevline = line
    if prevline is not None:
        result += prevline
    logger.debug("RH Output highlight_diff : \n *********\n%s\n ********\n"%(_with_linenos(mark_safe(result))))
    return mark_safe(result)
