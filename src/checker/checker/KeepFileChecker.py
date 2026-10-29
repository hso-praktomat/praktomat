import os

from django.db import models
from django.utils.translation import gettext_lazy
from django.utils.html import escape
from checker.basemodels import Checker, CheckerEnvironment, CheckerResult


class KeepFileChecker(Checker):
    filename: "models.CharField[str, str]" = models.CharField(
        max_length=500,
        blank=True,
        help_text=gettext_lazy("The name of the file to preserve (e.g. out.txt)"),
    )

    def title(self) -> str:
        return "Keep file %s" % self.filename

    def run(self, env: CheckerEnvironment) -> CheckerResult:
        path = os.path.join(env.tmpdir(), self.filename)

        result = self.create_result(env)
        if os.path.isfile(path):
            result.add_artefact(self.filename, path)
            result.set_passed(True)
        else:
            result.set_log("<p>Could not find file <tt>%s</tt>.</p>" % escape(self.filename))
            result.set_passed(False)

        return result

from checker.admin import    CheckerInline
class KeepFileCheckerInline(CheckerInline[KeepFileChecker]):
    model: type[KeepFileChecker] = KeepFileChecker
