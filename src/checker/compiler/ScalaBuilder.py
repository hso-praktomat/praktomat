"""
A Scala compiler for construction.
"""

import os
from typing import Any

from django.conf import settings
from checker.compiler.JavaBuilder import ClassFileGeneratingBuilder
from django.template.loader import get_template
from functools import reduce

class ScalaBuilder(ClassFileGeneratingBuilder):
    """ A Scala compiler. """

    # Initialization sets attributes to default values.
    _compiler = settings.SCALAC
    _language = "scala"

# _rx_warnings            = r"^([^ :]*:[^:].*)$"

    def build_log(
        self, output: str, args: list[str], filenames: set[str]
    ) -> str:
        t = get_template('checker/compiler/scala_builder_report.html')
        return t.render({'filenames' : filenames, 'output' : output, 'cmdline' : os.path.basename(args[0]) + ' ' +  reduce(lambda parm, ps: parm + ' ' + ps, args[1:], '')})

from checker.admin import CheckerInline, AlwaysChangedModelForm


class CheckerForm(AlwaysChangedModelForm):
    """ override default values for the model fields """

    def __init__(self, **args: Any) -> None:
        super(CheckerForm, self).__init__(**args)
        self.fields["_flags"].initial = ""
        self.fields["_output_flags"].initial = ""
        self.fields["_file_pattern"].initial = r"^[A-Z][a-zA-Z0-9_]*\.scala$"
        self.fields["required"].initial = True


class ScalaBuilderInline(CheckerInline[ScalaBuilder]):
    model: type[ScalaBuilder] = ScalaBuilder
    form = CheckerForm
