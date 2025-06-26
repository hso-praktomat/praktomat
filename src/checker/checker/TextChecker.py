import re
from collections import defaultdict

from django.db import models
from django.utils.html import escape

from checker.basemodels import Checker


class TextChecker(Checker):
    SET_OF_CHOICES = [
        (0, 'The text must not be in the solution'),
        (1, 'The text has to be in the solution'),
    ]

    text = models.TextField(help_text="Enter multiple lines, one per pattern.")
    choices = models.IntegerField(default=1, verbose_name='Select:', choices=SET_OF_CHOICES)
    use_regex = models.BooleanField(default=False, help_text="Treat input as regular expressions.")
    ignore_case_and_whitespace = models.BooleanField(
        default=True, help_text="Ignore case differences and all whitespace (e.g., spaces, tabs) during matching.")

    skip_lines = models.BooleanField(
        default=True,
        help_text="Skip lines that begin with comment symbols or are inside block comments."
    )
    begin_with = models.CharField(
        max_length=100,
        blank=True,
        default='// #',
        help_text="Space-separated line prefixes for single-line comments (e.g., // #)."
    )
    multi_block = models.CharField(
        max_length=100,
        blank=True,
        default='/* */',
        help_text="Space-separated start and end symbols for block comments (e.g., /* */)."
    )

    def title(self):
        return "Text Checker"

    @staticmethod
    def description():
        return ("Checks for one or more strings or patterns in solution files, "
                "with options to use regex, ignore case, and skip commented lines.")

    def _normalize(self, text: str) -> str:
        if self.ignore_case_and_whitespace:
            return re.sub(r'\s+', '', text.lower())
        return text

    def _get_patterns(self) -> list[str]:
        return [line.strip() for line in self.text.splitlines() if line.strip()]

    def _get_matched_text(self, line: str, match) -> str:
        if isinstance(match, re.Match):
            start, end = match.span()
        else:
            start, end = match
        return line[start:end]

    def _is_commented_line(self, line: str) -> bool:
        if not self.skip_lines or not self.begin_with:
            return False
        prefixes = self.begin_with.strip().split()
        return any(line.strip().startswith(sym) for sym in prefixes)

    def _remove_multiblock_comments_with_line_map(self, text: str, log_messages: list[str]) -> tuple[list[str], list[int]]:
        if not self.skip_lines or not self.multi_block:
            lines = text.splitlines()
            return lines, list(range(1, len(lines) + 1))

        symbols = self.multi_block.strip().split()
        if len(symbols) % 2 != 0:
            log_messages.append(
                self._format_system_message("Warnung", "Ungültige Einstellungen in 'multi_block'. Es müssen Paare von Start- und Endsymbolen sein, z.&nbsp;B. <code>/* */</code>."))

            lines = text.splitlines()
            return lines, list(range(1, len(lines) + 1))

        start_end_pairs = [(re.escape(symbols[i]), re.escape(symbols[i + 1])) for i in range(0, len(symbols), 2)]
        cleaned_lines = []
        line_map = []
        inside_block = False
        block_start_re = re.compile('|'.join(start for start, _ in start_end_pairs))
        block_end_re = re.compile('|'.join(end for _, end in start_end_pairs))

        for lineno, line in enumerate(text.splitlines(), start=1):
            if inside_block:
                if block_end_re.search(line):
                    inside_block = False
                continue
            elif block_start_re.search(line):
                inside_block = True
                continue
            cleaned_lines.append(line)
            line_map.append(lineno)

        return cleaned_lines, line_map

    def run(self, env):
        result = self.create_result(env)
        patterns = self._get_patterns()
        passed = 1
        log = []
        log_messages = []
        occurrences = defaultdict(list)
        explanations = defaultdict(list)
        normalized_patterns = {p: self._normalize(p) for p in patterns}

        for filename, content in env.string_sources():
            lines, line_map = self._remove_multiblock_comments_with_line_map(content, log_messages)
            for i, line in enumerate(lines):
                if self._is_commented_line(line):
                    continue

                norm_line = self._normalize(line)
                lineno = line_map[i]

                for pattern, norm_pattern in normalized_patterns.items():
                    matches = []
                    if self.use_regex:
                        try:
                            matches = list(re.finditer(norm_pattern, norm_line))
                        except re.error:
                            log_messages.append(
                                self._format_system_message("Fehler", f"Ungültiger regulärer Ausdruck: '<code>{escape(pattern)}</code>'."))
                            continue
                    else:
                        start = 0
                        while (idx := norm_line.find(norm_pattern, start)) != -1:
                            matches.append((idx, idx + len(pattern)))
                            start = idx + len(pattern)

                    for match in matches:
                        matched_text = self._get_matched_text(line, match)
                        occurrences[pattern].append((filename, lineno, matched_text))
                        explanations[pattern].append(
                            f"<li>Das Muster '<code>{escape(pattern)}</code>' passt zu "
                            f"<code>{escape(matched_text)}</code> in Zeile {lineno} der Datei "
                            f"<code>{escape(filename)}</code>.</li>"
                        )

        for pattern in patterns:
            hits = occurrences[pattern]
            has_hits = bool(hits)
            must_be_present = self.choices == 1

            if must_be_present and not has_hits:
                passed = 0
                log.append(self._format_message("Fehler", f"'<code>{escape(pattern)}</code>' wurde nicht gefunden."))
            elif must_be_present:
                log.append(self._format_message("OK", f"'<code>{escape(pattern)}</code>' gefunden an:"))
                log.append(self._format_hits(hits))
            elif has_hits:
                passed = 0
                log.append(self._format_message(
                    "Fehler", f"'<code>{escape(pattern)}</code>' sollte nicht vorkommen, wurde aber gefunden:"))
                log.append(self._format_hits(hits))
            else:
                log.append(self._format_message("OK", f"'<code>{escape(pattern)}</code>' wurde nicht gefunden."))

            if self.use_regex and explanations[pattern]:
                log.append('<details><summary><em>Details</em></summary><ul>')
                log.extend(explanations[pattern])
                log.append('</ul></details>')

        if log_messages:
            log.append('<hr><p><strong>Systemhinweise:</strong></p>')
            log.extend(log_messages)

        result.set_log("".join(log))
        result.set_passed(passed)
        return result

    def _format_message(self, status, message):
        css_class = "passed" if status == "OK" else "error"
        return f'<p><span class="{css_class}"><strong>{status}:</strong></span> {message}</p>'

    def _format_hits(self, hits):
        return f"<ul>{''.join(f'<li>{escape(f)} Zeile {l}</li>' for f, l, _ in hits)}</ul>"

    def _format_system_message(self, level: str, message: str) -> str:
        return f'<p><em>{level}:</em> {message}</p>'


from checker.admin import CheckerInline

class TextCheckerInline(CheckerInline):
    model = TextChecker
