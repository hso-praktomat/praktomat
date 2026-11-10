import os

from django.db import models
from django.utils.html import escape
from django.utils.translation import gettext_lazy

from checker.basemodels import Checker, CheckerEnvironment, CheckerResult


class KeepFileChecker(Checker):
    filename: "models.CharField[str, str]" = models.CharField(
        max_length=500,
        blank=True,
        help_text=gettext_lazy("The name of the file to preserve (e.g. out.txt)"),
    )

    def title(self) -> str:
        return f"Keep file {self.filename}"

    def run(self, env: CheckerEnvironment) -> CheckerResult:
        path = os.path.join(env.tmpdir(), self.filename)

        result = self.create_result(env)
        if os.path.isfile(path):
            result.add_artefact(self.filename, path)
            result.set_passed(True)
        else:
            result.set_log(f"<p>Could not find file <tt>{escape(self.filename)}</tt>.</p>")
            result.set_passed(False)

        return result


from checker.admin import CheckerInline  # noqa: E402  # Load after model definitions to avoid circular imports.


class KeepFileCheckerInline(CheckerInline[KeepFileChecker]):
    model: type[KeepFileChecker] = KeepFileChecker
