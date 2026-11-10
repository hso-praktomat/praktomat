"""
A C++ compiler for construction.
"""

from typing import Any

from django.conf import settings

from checker.basemodels import CheckerEnvironment
from checker.compiler.Builder import Compiler


class CXXBuilder(Compiler):
    """ A C++ compiler for construction. """

    # override configuration
    _compiler                = settings.CXX_BINARY
    _language                = "C++"
    #_rx_warnings            = r"^([^ :]*:[^:].*)$"

    def pre_run(self, env: CheckerEnvironment) -> str:
        return self.compiler()



    def post_run(self, env: CheckerEnvironment) -> tuple[bool, str]:
        passed = True
        log = ""
        return passed, log


    def connected_flags(self, env: CheckerEnvironment) -> list[str]:
        return self.search_path() + self.flags()


from checker.admin import (  # noqa: E402  # Load after model definitions to avoid circular imports.
    AlwaysChangedModelForm,
    CheckerInline,
)


class CheckerForm(AlwaysChangedModelForm):
    def __init__(self, **args: Any) -> None:
        """ override default values for the model fields """
        super().__init__(**args)
        self.fields["_flags"].initial = "-Wall -Wextra"
        #self.fields["_output_flags"].initial = "-o %s"
        self.fields["_output_flags"].initial = "-c"
        #self.fields["_libs"].initial = ""
        # GCC accepts the following extensions for C++ files: ".cc", ".cxx", ".cpp", ".c++", ".C".
        self.fields["_file_pattern"].initial = r"^[a-zA-Z0-9_]*\.(c|C|cc|CC|cxx|CXX|c\+\+|C\+\+|cpp|CPP)$"
        self.fields["required"].initial = True

class CXXBuilderInline(CheckerInline[CXXBuilder]):
    model: type[CXXBuilder] = CXXBuilder
    form = CheckerForm
    verbose_name = "C++ Compiler"
