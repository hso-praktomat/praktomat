import os
import re
import shlex
from collections.abc import Collection
from django.db import models
from django.utils.translation import gettext_lazy
from django.utils.html import escape
from django.template.loader import get_template

from django.core.exceptions import ValidationError
from django.conf import settings


from checker.basemodels import Checker, CheckerEnvironment, CheckerResult
from utilities.safeexec import execute_arglist
from functools import reduce


def program_output_flags(flags: str, program: str | None) -> list[str]:
    arguments = shlex.split(flags)
    if program is None:
        return arguments
    return [argument.replace('%s', program) for argument in arguments]

# ----------------------------- #
class MainNeedHelper(models.Model):
    """ Abstract class supporting infrastructur on django admin webinterface for checking if a main method or function is neccessary """

    class Meta(Checker.Meta):
        abstract = True

    # elements for using via django admin webinterface
    _main_required: "models.BooleanField[bool, bool]" = models.BooleanField(default = True, help_text = gettext_lazy('Is a submission required to provide a main method or function?'))

    def main_required(self) -> bool:
        """ Returns true, if Trainer has choosen, that a submission have to provide a main. """
        return self._main_required

    def main_search(self, env: CheckerEnvironment) -> str:
        """ default implementation of main_search throws a TypeError """
        raise TypeError("Can't instantiate class with abstract method main_search(self,env). You have to implement it.")


    def main_check(self, env: CheckerEnvironment) -> bool:
        """ returns True if main is required and found or if main is not required """
        if self._main_required:
            return bool(self.main_search(env))
        return True



# ----------------------------- #

class LibraryHelper(models.Model):
    """ Abstract class supporting infrastructur on django admin webinterface for handling libraries via compiler or linker """

    class Meta(Checker.Meta):
        abstract = True

    # elements for using via django admin webinterface
    _libs: "models.CharField[str, str]" = models.CharField(max_length = 1000, blank = True, default = "", help_text = gettext_lazy('flags for libraries like \'-lm \' as math library for C'))

    def libs(self) -> list[str]:
        """ returns flags for compiler or linker interaction with libraries. To be overloaded in subclasses. """
        return self._libs.strip().split(" ") if self._libs else []

# ----------------------------- #

class IncludeHelper(models.Model):
    """ Abstract class supporting infrastructur on django admin webinterface for handling additional search-pathes while interacting with compiler or linker """

    class Meta(Checker.Meta):
        abstract = True

    # elements for using via django admin webinterface
    _search_path: "models.CharField[str, str]" = models.CharField(max_length = 1000, blank = True, default = "", help_text = gettext_lazy('flags for additional search path for compiler or linker '))

    def search_path(self) -> list[str]:
        """ returns flags for additional search path for compiler or linker interaction. To be overloaded in subclasses. """
        return self._search_path.strip().split(" ") if self._search_path else []

# ----------------------------- #

class CompilerOrLinker(Checker, IncludeHelper):
    """ Abstract class as generalisation for Compiler and Linker calls.  Specialized subclass provided for different languages and compilers, linkers. """


    class Meta(IncludeHelper.Meta):
        abstract = True

    # configuration. override in subclass
    _language: str = "language_configurable"    # the language of the compiler eg. C++ or Java
    _rx_warnings: str = r"^([^:]*:[^:].*)$"        # Regular expression describing warings and errors in the output of the compiler
    _env: dict[str, str] = {}

    # do not override in subclass (dont hack name mangeling)
    __output_flags: str = ""
    __flags: str = ""
    __runner: str = "__runner_to_be_defined_via__fetch_runner"

    # elements for using via django admin webinterface
    _flags: "models.CharField[str, str]" = models.CharField(max_length = 1000, blank = True, default="-Wall -Wextra", help_text = gettext_lazy('Compiler or Linker flags'))
    _file_pattern: "models.CharField[str, str]" = models.CharField(max_length = 1000, default = r"^[a-zA-Z0-9_]*$", help_text = gettext_lazy('Regular expression describing all source files to be passed to the compiler or linker. (Play with  RegEx at <a href=\"http://pythex.org/\" target=\"_blank\">http://pythex.org/ </a>'))



    def _fetch_runner(self, runner: str) -> None:
        self.__runner = runner

    def post_run(self, env: CheckerEnvironment) -> tuple[bool, str]:
        """ default implementation of post_run throws a TypeError """
        raise TypeError("Can't instantiate class with abstract method post_run(self,env). You have to implement it.")

    def pre_run(self, env: CheckerEnvironment) -> str:
        """ default implementation of pre_run throws a TypeError """
        raise TypeError("Can't instantiate class with abstract method pre_run(self,env). You have to implement it.")


    class NotFoundError(Exception):
            def __init__(self, description: str) -> None:
                self.description = description
            def __str__(self) -> str:
                return self.description

    def main_module(self, env: CheckerEnvironment) -> str:
        """ Creates the name of the main module from the (first) source file name. Independently from a main symbol in there """
        # use it where you want like this :  env.set_program(self.main_module(env)) #
        for module_name in self.get_file_names(env):
            try:
                return module_name[:module_name.index('.')]
            except ValueError:
                pass
        # Module name not found

        raise self.NotFoundError("The module containing a main could not be found.\n")



    def run(self, env: CheckerEnvironment) -> CheckerResult:
        """ Build it. """

        self._fetch_runner(self.pre_run(env))

        result = self.create_result(env)

        # Try to find out the main modules name with only the source files present
        try:
            env.set_program(self.main_module(env))
        except self.NotFoundError:
             pass

        filenames = [name for name in self.get_file_names(env)]

#        if (issubclass(type(self), Compiler)) and ('Ignoring' in self.__class__.__name__):
#            raise TypeError

        args = [self.__runner] + self.output_flags(env) + filenames + self.connected_flags(env)
        script_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)),'scripts')

        myenviron = self.environment()
        myenviron['LANG'] = settings.LANG
        myenviron['LANGUAGE'] = settings.LANGUAGE
        myenviron['TASK_ID_CUSTOM'] = env.task().custom_id
        execution = execute_arglist(args, env.tmpdir(), myenviron, extradirs=[script_dir])
        output = execution.output

        output = escape(output)
        output = self.enhance_output(env, output)

        # We mustn't have any warnings.
        passed = execution.exitcode == 0 and not execution.timed_out and not execution.oom_ed and not self.has_warnings(output)
        #log  = self.build_log(output,args,set(filenames).intersection([solutionfile.path() for solutionfile in env.solution().solutionfile_set.all()]))
        log  = self.logbuilder(output,args,env)


        # Now that submission was successfully built, try to find the main modules name again

        if passed:
            [post_passed, post_log] = self.post_run(env)
            passed = passed and post_passed
            log += "<pre>" + str(post_log) + "</pre>"


        result.set_passed(passed)
        result.set_log(log, timed_out=execution.timed_out, oom_ed=execution.oom_ed)
        return result


    def flags(self) -> list[str]:
        """ Compiler or linker flags.    To be overloaded in subclasses. """
        return self._flags.strip().split(" ") if self._flags else []

    def output_flags(self, env: CheckerEnvironment) -> list[str]:
        """ Output flags """
        return program_output_flags(self.__output_flags, env.program())

    def _fetch_output_flags(self, oflags: str) -> None:
        self.__output_flags = oflags


    def connected_flags(self, env: CheckerEnvironment) -> list[str]:
        """ default implementation of run throws a TypeError """
        raise TypeError("Can't instantiate class with abstract method connected_flags(self,env). You have to implement it.")



    def environment(self) -> dict[str, str]:
        """ Environment to be set on onvocation of Compiler. """
        return self._env.copy()


    def language(self) -> str:
        """ Language.  To be overloaded in subclasses """
        return self._language

    def rxarg(self) -> str:
        """ Regexp for compile or link command argument.  Files that do not match this regexp will be uploaded,
            but not passed as argument to the compiler     (such as header files in C/C++).
            This also protects somewhat against options (`-foo') and metacharacters (`foo; ls') in file names. To be overloaded in subclasses. """
        return self._file_pattern

#    def get_file_names(self,env):
#          """ default implementation of get_file_names throws a TypeError """
#        raise TypeError("Can't instantiate class with abstract method get_file_names(self,env). You have to implement it using rxarg(self).")
    def get_file_names(self, env: CheckerEnvironment) -> list[str]:
        rxarg = re.compile(self.rxarg())
        return [name for (name, _) in env.sources() if rxarg.match(name)]



    def enhance_output(self, env: CheckerEnvironment, output: str) -> str:
        """ Add more info to build output OUTPUT.  To be overloaded in subclasses. """
        return re.sub(re.compile(self._rx_warnings, re.MULTILINE), r"<b>\1</b>", output)

    def has_warnings(self, output: str) -> bool:
        """ Return true if there are any warnings in OUTPUT """
        return re.compile(self._rx_warnings, re.MULTILINE).search(output) != None

    def logbuilder(
        self, output: str, args: list[str], env: CheckerEnvironment
    ) -> str:
        """ For Child classes to do additional things """
        filenames = [name for name in self.get_file_names(env)]

        foo =  self.build_log(output,args,set(filenames).intersection([solutionfile.path() for solutionfile in env.solution().solutionfile_set.all()]))

        return foo

    def isLinker(self) -> bool:
        return False

    def build_log(
        self, output: str, args: list[str], filenames: Collection[str]
    ) -> str:
        t = get_template('checker/compiler/builder_report.html')
        return t.render({
            'filenames' : filenames,
            'output' : output,
            'cmdline' : os.path.basename(args[0]) + ' ' +  reduce(lambda parm,ps: parm + ' ' + ps,args[1:],''),
            'regexp' : self.rxarg(),
            'debug'  : False,
            'linker' : self.isLinker()
        })

# ----------------------------- #

class Compiler(CompilerOrLinker):
    """ Abstract class as generalisation for Compiler calls.  Specialized subclass provided for different languages and compilers. """


    class Meta(CompilerOrLinker.Meta):
        abstract = True

    # builder configuration. override in subclass
    _compiler    = "compiler_configurable"        # command to invoce the compiler in the shell

    _output_flags: "models.CharField[str, str]" = models.CharField(max_length = 1000, blank = True, default ="-c -g -O0", help_text = gettext_lazy('Output flags. \'%s\' will be replaced by the program name.'))

    def compiler(self) -> str:
        return self._compiler

    def title(self) -> str:
        return u"%s - Compiler" % self.language()


#    def get_file_names(self,env):
#        rxarg = re.compile(self.rxarg())
#        return [name for (name,content) in env.sources() if rxarg.match(name)]


    def output_flags(self, env: CheckerEnvironment) -> list[str]:
        self._fetch_output_flags(self._output_flags)
        return super(Compiler, self).output_flags(env)

    def clean(self) -> None:
        super(Compiler, self).clean()
        rx = re.compile(r"^.*(-c.*(-o.*|%s)).*$")
        if rx.match(self._output_flags)  : raise ValidationError("You cannot put flag -c in combination with -o ; -c %s doesn't fit together, too.")

# ----------------------------- #

class Linker(CompilerOrLinker):
    """ Abstract class as generalisation for Compiler calls.  Specialized subclass provided for different languages and compilers. """


    class Meta(CompilerOrLinker.Meta):
        abstract = True

    # builder configuration. override in subclass
    _linker        = "linker_configurable"            # command to invoce the compiler in the shell


    _LINK_CHOICES = (
      (u'out', u'-o %s (Link to executable program)'),
      (u'so', u'-shared -fPIC -o %s (Link to shared object)'),
    )

    _LINK_DICT = {u'out': u'-o', u'so': u'-shared -fPIC -o'}
    _output_flags: "models.CharField[str, str]" = models.CharField(max_length=16, choices=_LINK_CHOICES,default="-o %s", help_text = gettext_lazy('choose link output type. \'%s\' will replaced by output_name. '))


    _output_name: "models.CharField[str, str]" = models.CharField(max_length=16, default="%s", help_text = gettext_lazy('choose a outputname. \'%s\' will be replaced by an internal default name.'))


    def linker(self) -> str:
        return self._linker

    def isLinker(self) -> bool:
        return True

    def title(self) -> str:
        return u"%s - Linker" % self.language()



#    def get_file_names(self,env):
#        rxarg = re.compile(self.rxarg())
#        #ToDo: think again if env.sources() fits here - perhaps not! ...
#        return [name for (name,content) in env.sources() if rxarg.match(name)]

    def output_flags(self, env: CheckerEnvironment) -> list[str]:
        self._fetch_output_flags(self._LINK_DICT[self._output_flags]+ u' ' +self._output_name)
        myOutputFlags = super(Linker, self).output_flags(env)
        myOutputFlags[-1] = myOutputFlags[-1]+u"."+self._output_flags #append file ending
        return myOutputFlags


# ----------------------------- #

class Builder(Checker):
    """ Build a program. This contains the general infrastructure to build a program with a compiler.  Specialized subclass are provided for different languages and compilers. """

    class Meta(Checker.Meta):
        abstract = True

    # builder configuration. override in subclass
    _compiler: str = "gcc"                        # command to invoke the compiler in the shell
    _language: str = "konfigurierbar"            # the language of the compiler, e.g. C++ or Java
    _rx_warnings: str = r"^([^:]*:[^:].*)$"        # Regular expression describing warnings and errors in the output of the compiler
    _env: dict[str, str] = {}


    _flags: "models.CharField[str, str]" = models.CharField(max_length = 1000, blank = True, default="-Wall", help_text = gettext_lazy('Compiler flags'))
    _output_flags: "models.CharField[str, str]" = models.CharField(max_length = 1000, blank = True, default ="-o %s", help_text = gettext_lazy('Output flags. \'%s\' will be replaced by the program name.'))
    _libs: "models.CharField[str, str]" = models.CharField(max_length = 1000, blank = True, default = "", help_text = gettext_lazy('Compiler libraries'))
    _file_pattern: "models.CharField[str, str]" = models.CharField(max_length = 1000, default = r"^[a-zA-Z0-9_]*$", help_text = gettext_lazy('Regular expression describing all source files to be passed to the compiler.'))
    _main_required: "models.BooleanField[bool, bool]" = models.BooleanField(default = True, help_text = gettext_lazy('Is a submission required to provide a main method?'))

    def title(self) -> str:
        return "%s - Compiler" % self.language()

    @staticmethod
    def description() -> str:
        return "Diese Prüfung ist bestanden, wenn der Compiler das Programm ohne Fehler oder Warnungen übersetzt."

    def compiler(self) -> str:
        """ Compiler name. To be overloaded in subclasses. """
        return self._compiler

    def flags(self, env: CheckerEnvironment) -> list[str]:
        """ Compiler flags.    To be overloaded in subclasses. """
        return self._flags.split(" ") if self._flags else []


    def is_MainRequired(self, env: CheckerEnvironment) -> bool:
        return self._main_required

    def output_flags(self, env: CheckerEnvironment) -> list[str]:
        """ Output flags """
        return program_output_flags(self._output_flags, env.program())

    def libs(self) -> list[str]:
        """ Compiler libraries.     To be overloaded in subclasses. """
        return self._libs.split(" ") if self._libs else []

    def environment(self) -> dict[str, str]:
        """ Environment to be set on onvocation of Compiler. """
        return self._env.copy()

    def language(self) -> str:
        """ Language.  To be overloaded in subclasses """
        return self._language

    def rxarg(self) -> str:
        """ Regexp for compile command argument.  Files that do not match this regexp will be uploaded,
            but not passed as argument to the compiler     (such as header files in C/C++).
            This also protects somewhat against options (`-foo') and metacharacters (`foo; ls') in file names. To be overloaded in subclasses. """
        return self._file_pattern

    def get_file_names(self, env: CheckerEnvironment) -> list[str]:
        rxarg = re.compile(self.rxarg())
        return [name for (name, _) in env.sources() if rxarg.match(name)]

    def exec_file(self, tmpdir: str, program_name: str) -> str:
        """ File of the generated executable.  To be overloaded in subclasses. """
        return os.path.join(tmpdir, program_name)

    def enhance_output(self, env: CheckerEnvironment, output: str) -> str:
        """ Add more info to build output OUTPUT.  To be overloaded in subclasses. """
        return re.sub(re.compile(self._rx_warnings, re.MULTILINE), r"<b>\1</b>", output)

    def has_warnings(self, output: str) -> bool:
        """ Return true if there are any warnings in OUTPUT """
        return re.compile(self._rx_warnings, re.MULTILINE).search(output) != None

    class NotFoundError(Exception):
        def __init__(self, description: str) -> None:
            self.description = description
        def __str__(self) -> str:
            return self.description

    def main_module(self, env: CheckerEnvironment) -> str:
        """ Creates the name of the main module from the (first) source file name. """
        for module_name in self.get_file_names(env):
            try:
                return module_name[:module_name.index('.')]
            except ValueError:
                pass
        # Module name not found

        raise self.NotFoundError("The main module could not be found.\n")

    def run(self, env: CheckerEnvironment) -> CheckerResult:
        """ Build it. """
        result = self.create_result(env)

        # Try to find out the main modules name with only the source files present
        if self._main_required:
            try:
                env.set_program(self.main_module(env))
            except self.NotFoundError:
                pass

        filenames = [name for name in self.get_file_names(env)]
        args = [self.compiler()] + self.output_flags(env) + self.flags(env) + filenames + self.libs()
        script_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'scripts')
        environ = self.environment()
        environ['LANG'] = settings.LANG
        environ['LANGUAGE'] = settings.LANGUAGE
        execution = execute_arglist(args, env.tmpdir(), environ, extradirs=[script_dir])
        output = execution.output

        output = escape(output)
        output = self.enhance_output(env, output)

        # We mustn't have any warnings.
        passed = execution.exitcode == 0 and not execution.timed_out and not execution.oom_ed and not self.has_warnings(output)
        log  = self.build_log(output, args, set(filenames).intersection([solutionfile.path() for solutionfile in env.solution().solutionfile_set.all()]))

        # Now that submission was successfully built, try to find the main modules name again
        if self._main_required and passed:
            try:
                env.set_program(self.main_module(env))
            except self.NotFoundError as e:
                log += "<pre>" + str(e) + "</pre>"
                passed = False

        result.set_passed(passed)
        result.set_log(log, timed_out=execution.timed_out, oom_ed=execution.oom_ed)
        return result

    def build_log(self, output: str, args: list[str], filenames: set[str]) -> str:
        t = get_template('checker/compiler/builder_report.html')
        return t.render({
            'filenames' : filenames,
            'output' : output,
            'cmdline' : os.path.basename(args[0]) + ' ' +  reduce(lambda parm, ps: parm + ' ' + ps, args[1:], ''),
            'regexp' : self.rxarg(),
            'debug'  : False
        })
