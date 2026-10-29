"""
DejaGnu Tests.
"""

import os
from os.path import join
import re
from typing import Any

from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy
from django.utils.html import escape
from checker.basemodels import (
    Checker,
    CheckerEnvironment,
    CheckerFileField,
    CheckerResult,
)
from checker.compiler.Builder import Builder
from utilities.safeexec import execute_arglist
from utilities import encoding
from utilities.file_operations import create_file, makedirs

# Stuff to highlight in output
RXFAIL       = re.compile(r"^(.*)(FAIL|ERROR|Abort|Exception |your program crashed|cpu time limit exceeded|"
                        "ABBRUCH DURCH ZEITUEBERSCHREITUNG|# of unexpected failures.*[0-9]+)(.*)$",    re.MULTILINE)
RXPASS       = re.compile(r"^(.*)(PASS)(.*)$", re.MULTILINE)
RXRUN_BY   = re.compile(r"Run By .* on ")

# Stuff to remove from output
RXREMOVE   = re.compile(r"(Schedule of variations:.*interface file.)|(Running \./[ -z]*/[a-z]*\.exp \.\.\.)", re.DOTALL)

class DejaGnu(object):
    """ Common superclass for all DejaGnu-related stuff. """

    # Directories
    def testsuite_dir(self, env: CheckerEnvironment) -> str:
        return os.path.join(env.tmpdir(), "testsuite")

    def config_dir(self, env: CheckerEnvironment) -> str:
        return os.path.join(self.testsuite_dir(env), "config")

    def lib_dir(self, env: CheckerEnvironment) -> str:
        return os.path.join(self.testsuite_dir(env), "lib")

    def tests_dir(self, env: CheckerEnvironment) -> str:
        program_name = env.program()
        assert program_name is not None
        return os.path.join(self.testsuite_dir(env), program_name + ".tests")

    def setup_dirs(self, env: CheckerEnvironment) -> None:
        makedirs(self.testsuite_dir(env))
        makedirs(self.config_dir(env))
        makedirs(self.lib_dir(env))
        makedirs(self.tests_dir(env))

class DejaGnuTester(Checker, DejaGnu):
    """ Run a test case on the program.  Requires a previous `DejaGnuSetup'. """

    name: "models.CharField[str, str]" = models.CharField(
        max_length=100,
        help_text=gettext_lazy("The name of the Test"),
    )
    test_case: CheckerFileField = CheckerFileField(
        help_text=gettext_lazy(
            "In den folgenden DejaGnu-Testfällen werden typischerweise Funktionen "
            "aufgerufen, die beim vorherigen Schritt <EM>Tests einrichten</EM> "
            "definiert wurden. Siehe auch den Abschnitt <EM>How to write a test "
            "case</EM> im <A TARGET=\"_blank\" HREF=\"http://www.gnu.org/manual/"
            "dejagnu/\">DejaGnu-Handbuch</A>."
        )
    )

    def __str__(self) -> str:
        return self.name

    def title(self) -> str:
        return self.name

    @staticmethod
    def description() -> str:
        return "Diese Prüfung ist bestanden, wenn alle Testfälle zum erwarteten Ergebnis führten."

    def requires(self) -> list[type[Checker]]:
        return [ DejaGnuSetup ]

    # Return 1 if the output is ok
    def output_ok(self, output: str) -> bool:
        return (RXFAIL.search(output) is None and
                output.find("runtest completed") >= 0 and
                output.find("non-expected failures") < 0 and
                output.find("unexpected failures") < 0)

    def htmlize_output(self, log: str) -> str:
        # Always kill the author's name from the log
        log = re.sub(RXRUN_BY, "Run By " + settings.SITE_NAME + " on ", log)

        # Clean the output
        log = re.sub(RXREMOVE, "", log)

        log = re.sub(re.escape(settings.JVM_SECURE), os.path.basename(settings.JVM_SECURE), log)

        # HTMLize it all
        log = escape(log)

        # Every line that contains a passed message is to be enhanced.
        log = re.sub(RXPASS, r'\1 <B class="passed"> \2 </B> \3', log)
        # Every line that contains a failure message is to be enhanced.
        return  "<TT><PRE>" + re.sub(RXFAIL, r'\1 <B class="error"> \2 </B> \3', log) + "</PRE></TT>"


    # Run tests.  Return a CheckerResult.
    def run(self, env: CheckerEnvironment) -> CheckerResult:

        # Save public test cases in `tests.exp'
        tests_exp = os.path.join(self.tests_dir(env), "tests.exp")
        program_name = env.program()
        assert program_name is not None
        test_cases = encoding.get_unicode(self.test_case.read()).replace("PROGRAM", program_name)
        create_file(tests_exp, test_cases)

        testsuite = self.testsuite_dir(env)

        if " " in program_name:
            result = self.create_result(env)
            result.set_log("<pre><b class=\"fail\">Error</b>: Path to the main() - source file contains spaces.\n\nFor Java .zip submittions, the directory hierarchy of the .zip file must exactly match the package structure.\nThe default package must correspond to the .zip root directory.</pre>")
            result.set_passed(False)
            return result

        cmd = [settings.DEJAGNU_RUNTEST, "--tool", program_name, "tests.exp"]

        environ: dict[str, str] = {}
        environ['JAVA'] = settings.JVM
        script_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'scripts')
        environ['POLICY'] = join(script_dir, "java.policy")
        environ['USER'] = env.user().get_full_name()
        environ['HOME'] = testsuite
        environ['UPLOAD_ROOT'] = settings.UPLOAD_ROOT
        environ['LANG'] = settings.LANG
        environ['LANGUAGE'] = settings.LANGUAGE
        environ['TASK_ID_CUSTOM'] = env.task().custom_id
        environ['ALLOW_LLM_UPLOAD'] = '1' if env.solution().allow_llm_upload else '0'

        [output, _, exitcode, timed_out, oom_ed] = \
                    execute_arglist(
                        cmd,
                        testsuite,
                        environment_variables=environ,
                        timeout=settings.TEST_TIMEOUT,
                        fileseeklimit=settings.TEST_MAXFILESIZE,
                        filenumberlimit=settings.TEST_MAXFILENUMBER,
                        extradirs=[env.tmpdir(), script_dir]
                        )
        output = encoding.get_unicode(output)
        #TODO this is just a workaround for the deprecation of Java Security Manager (since java 17)
        # the warnings occur because the java (alias-)script ../scripts/java that is called by Praktomat sets the command line option to use java security manager
        # problem is that these warning occur also in the output of the JUnit-checker and irritate the students
        output = output.replace("WARNING: A command line option has enabled the Security Manager\n","")
        output = output.replace("WARNING: The Security Manager is deprecated and will be removed in a future release\n","")

        try:
            with open(os.path.join(testsuite, program_name + ".sum"),"rb") as fd:
                _summary = encoding.get_unicode(fd.read())
            with open(os.path.join(testsuite, program_name + ".log"),"rb") as fd:
                log = encoding.get_unicode(fd.read())
        except:
            _summary = ""
            log = ""

        complete_output = self.htmlize_output(output + log)

        result = self.create_result(env)
        result.set_log(complete_output, timed_out=timed_out or oom_ed)
        result.set_passed(not exitcode and not timed_out and not oom_ed and self.output_ok(complete_output))
        return result


# A template for test cases.
DEFAULT_TEST_CASES = """# `tests.exp' template
# Insert test cases in the format
# PROGRAM_test "[input]" "[expected_output]"
"""

class DejaGnuSetup(Checker, DejaGnu):

    test_defs: CheckerFileField = CheckerFileField(
        help_text=gettext_lazy(
            "Das Setup benutzt den <A HREF=\"http://www.gnu.org/software/dejagnu/"
            "dejagnu.html\">DejaGnu-Testrahmen</A>, um die Programme zu testen. "
            "Die in dieser Datei enthaltenen Definitionen gelten für alle Testfälle "
            "dieser Aufgabe. Sie werden beim Testen in die DejaGnu-Datei "
            "<TT>default.exp</TT> geschrieben. Die Variablen PROGRAM und JAVA werden "
            "mit dem Programmnamen bzw. dem Pfad zur Java-Runtime ersetzt."
        )
    )

    def title(self) -> str:
        return "Tests einrichten"

    @staticmethod
    def description() -> str:
        return "Dies ist keine wirkliche Prüfung.  Sie dient nur dazu, den nachfolgenden Tests Definitionen zur Verfügung zu stellen. Diese 'Prüfung' wird immer bestanden."

    def requires(self) -> list[type[Checker]]:
        return [ Builder ]

    # Set up tests.
    def run(self, env: CheckerEnvironment) -> CheckerResult:
        self.setup_dirs(env)
        program_name = env.program()
        assert program_name is not None
        create_file(os.path.join(self.lib_dir(env), program_name + ".exp"), "")
        defs = encoding.get_unicode(self.test_defs.read()).replace("PROGRAM", program_name)
#        defs = defs.replace("JAVA", join(join(dirname(dirname(__file__)),"scripts"),"java"))
        defs = defs.replace("JAVA", settings.JVM_SECURE)
        create_file(os.path.join(self.config_dir(env), "default.exp"), defs)

        return self.create_result(env)

from checker.admin import    CheckerInline, AlwaysChangedModelForm

class SetupForm(AlwaysChangedModelForm):
    def __init__(self, **args: Any) -> None:
        """ override public and required """
        super(SetupForm, self).__init__(**args)
        self.fields["public"].initial = False
        self.fields["required"].initial = False

class DejaGnuSetupInline(CheckerInline[DejaGnuSetup]):
    form = SetupForm
    model: type[DejaGnuSetup] = DejaGnuSetup
    #exclude = ["public", "required"]



class DejaGnuTesterInline(CheckerInline[DejaGnuTester]):
    model: type[DejaGnuTester] = DejaGnuTester
