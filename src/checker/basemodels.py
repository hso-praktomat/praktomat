import os.path
import shutil
import sys
import time
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.db import models
from tasks.models import Task
from solutions.models import Solution
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.utils.translation import gettext_lazy
from django.core.files.storage import Storage
from django.utils.encoding import force_str
from django.core.exceptions import ValidationError
from django.core.files import File
from django.db.models.signals import post_delete
from django.dispatch.dispatcher import receiver
from utilities import file_operations
from utilities.deleting_file_field import DeletingFileField

from functools import partial
from multiprocessing import Pool

from django.db import connection

from accounts.models import User
from tasks.models import Task
from django.template import loader
from django.core.mail import mail_admins
from datetime import datetime

if TYPE_CHECKING:
    from django.db.models.fields.related_descriptors import ReverseManyToOneDescriptor
    from django_stubs_ext import StrOrPromise


def get_checkerfile_storage_path(instance: "Checker", filename: str) -> str:
    """ Use this function as upload_to parameter for filefields. """
    return 'CheckerFiles/Task_%s/%s/%s' % (instance.task.pk, instance.__class__.__name__, filename)


class CheckerFileField(DeletingFileField):
    """ Custom filefield with greater path length and default upload location. Use this in all checker subclasses!"""

    def __init__(
        self,
        verbose_name: "StrOrPromise | None" = None,
        name: str | None = None,
        upload_to: "str | os.PathLike[str] | Callable[[Checker, str], str]" = get_checkerfile_storage_path,
        storage: Storage | Callable[[], Storage] | None = None,
        **kwargs: Any,
    ) -> None:
        # increment filename length from 100 to 500
        kwargs['max_length'] = kwargs.get('max_length', 500)
        super(CheckerFileField, self).__init__(verbose_name, name, upload_to, storage, **kwargs)

class Checker(models.Model):
    """ A Checker implements some quality assurance.

    A Checker has four indicators:
        1. Whether it is *public* - the results are presented to the user
        2. Whether it is *required* - it must be passed for submission
        3. Whether it is *critical* - prevents further results from being displayed if it fails
        3. Whether it is *always* run on submission.

    If a Checker is not always run, it is only run if a *task_maker*
    starts the complete rerun of all Checkers. """

    created: "models.DateTimeField[datetime, datetime]" = models.DateTimeField(auto_now_add=True)
    order: "models.IntegerField[int, int]" = models.IntegerField(help_text = gettext_lazy('Determines the order in which the checker will start. Not necessary continuously!'))

    task: "models.ForeignKey[Task, Task]" = models.ForeignKey(Task, on_delete=models.CASCADE)
    task_id: int

    public: "models.BooleanField[bool, bool]" = models.BooleanField(default=True, help_text = gettext_lazy('Test results are displayed to the submitter.'))
    required: "models.BooleanField[bool, bool]" = models.BooleanField(default=False, help_text = gettext_lazy('The test must be passed to submit the solution.'))
    always: "models.BooleanField[bool, bool]" = models.BooleanField(default=True, help_text = gettext_lazy('The test will run on submission time.'))
    critical: "models.BooleanField[bool, bool]" = models.BooleanField(default=False, help_text = gettext_lazy('If this test fails, do not display further test results.'))

    if TYPE_CHECKING:
        results: ReverseManyToOneDescriptor["CheckerResult"]
    else:
        results = GenericRelation("CheckerResult") # enables cascade on delete.

    class Meta:
        abstract = True
        app_label = 'checker'

    def __str__(self) -> str:
        return self.title()

    def create_result(self, env: "CheckerEnvironment") -> "CheckerResult":
        """ Creates a new result.
        May be overloaded by subclasses."""
        assert isinstance(env.solution(), Solution)
        result = CheckerResult(checker=self, solution=env.solution())
        result.save() # otherwise we cannot attach artefacts to it
        return result

    def show_publicly(self, passed: bool) -> bool:
        """ Are results of this Checker to be shown publicly, given whether the result was passed? """
        return self.public

    def is_critical(self, passed: bool) -> bool:
        """ Checks if further results should not be shown, given whether the result was passed? """
        return self.critical and not passed

    def run(self, env: "CheckerEnvironment") -> "CheckerResult":
        """ Runs tests in a special environment.
        Returns a CheckerResult. """
        assert isinstance(env, CheckerEnvironment)
        return self.create_result(env)

    def title(self) -> str:
        """ Returns the title for this checker category. To be overloaded in subclasses. """
        return "Prüfung"

    @staticmethod
    def description() -> str:
        """ Returns a description for this Checker.
        Overloaded by subclasses """
        return " no description "

    def requires(self) -> list[type["Checker"]]:
        """ Returns the list of passed Checkers required by this checker.
        Overloaded by subclasses. """
        return []

    def clean(self) -> None:
        if self.required and (not self.show_publicly(False)): raise ValidationError("Checker is required, but failure isn't publicly reported to student during submission")


class CheckerEnvironment:
    """ The environment for running a checker. """

    def __init__(self, solution: Solution) -> None:
        """ Constructor: Creates a standard environment. """
        # Temporary build directory
        sandbox = settings.SANDBOX_DIR
        # Sources as [(name, content)...]
        self._sources: list[tuple[str, str | bytes | None]] = []
        for file in solution.solutionfile_set.all().order_by('file'):
            self._sources.append((file.path(), file.content()))
        # Associated task for this solution
        self._task = solution.task
        # Submitter of this program
        self._user = solution.author
        # Executable program
        self._program: str | None = None

        # The solution
        self._solution = solution
        self._tmpdir = file_operations.create_tempfolder(sandbox)

    def solution(self) -> Solution:
        """ Returns the solution being checked """
        return self._solution

    def tmpdir(self) -> str:
        """ Returns the path name of temporary build directory. """
        return self._tmpdir

    def sources(self) -> list[tuple[str, str | bytes | None]]:
        """ Returns the list of source files. [(name, content)...] """
        return self._sources

    def string_sources(self) -> list[tuple[str, str]]:
        """ Returns the list of string-like source files,
            so it excludes byte-like content. [(name, content)...] """
        return [(name, content) for (name, content) in self._sources
                                if isinstance(content, str)]

    def add_source(self, path: str, content: str | bytes | None) -> None:
        """ Add source to the list of source files. [(name, content)...] """
        self._sources.append((path, content))

    def task(self) -> Task:
        """ Returns the associated task for this solution. """
        return self._task

    def user(self) -> User:
        """ Returns the submitter of this program (class User). """
        return self._user

    def program(self) -> str | None:
        """ Returns the name of the executable program, if already set. """
        return self._program

    def set_program(self, program: str | None) -> None:
        """ Sets the name of the executable program. """
        self._program = program




def truncated_log(log: str) -> tuple[str, bool]:
    """
    Assumes log to be raw (ie: non-HTML) checker result log
    Returns a (string,Bool) pair consisting of
          * the log, truncated if appropriate, i.e.: if it is longer than settings.TEST_MAXLOGSIZE*1
          * a flag indicating whether the log was truncated
    """

    log_length = len(log)
    if log_length > settings.TEST_MAXLOGSIZE*1024:
        # since we might be truncating utf8 encoded strings here, result may be erroneous, so we explicitly replace faulty byte tokens
        return (force_str('======= Warning: Output too long, hence truncated ======\n' + log[0:(settings.TEST_MAXLOGSIZE*1024)//2] + "\n...\n...\n...\n...\n" + log[log_length-((settings.TEST_MAXLOGSIZE*1024)//2):], errors='replace'), True)
    return (log, False)


class CheckerResult(models.Model):
    """ A CheckerResult returns the result of a Checker.
    It contains:
        - A flag that indicates if the check passed.
        - The title of the check.
        - The log of the run.
        - The time of the run. """

    if TYPE_CHECKING:
        id: models.AutoField[int | None, int]
        artefacts: ReverseManyToOneDescriptor["CheckerResultArtefact"]

    from solutions.models import Solution
    solution: "models.ForeignKey[Solution, Solution]" = models.ForeignKey(Solution, on_delete=models.CASCADE)
    solution_id: int
    content_type: "models.ForeignKey[ContentType, ContentType]" = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    content_type_id: int
    object_id: "models.PositiveIntegerField[int, int]" = models.PositiveIntegerField()
    checker = GenericForeignKey('content_type', 'object_id')

    passed: "models.BooleanField[int, bool]" = models.BooleanField(
        default=True,
        help_text=gettext_lazy('Indicates whether the test has been passed'),
    )
    passed_with_warning: "models.BooleanField[bool, bool]" = models.BooleanField(
        default=False,
        help_text=gettext_lazy(
            'Indicates whether the test has been passed with a warning'
        ),
    )
    log: "models.TextField[str, str]" = models.TextField(
        help_text=gettext_lazy('Text result of the checker')
    )
    creation_date: "models.DateTimeField[datetime, datetime]" = models.DateTimeField(auto_now_add=True)
    runtime: "models.IntegerField[int, int]" = models.IntegerField(default=0, help_text=gettext_lazy('Runtime in milliseconds'))

    def title(self) -> str:
        """ Returns the title of the Checker that did run. """
        return self.require_checker().title()

    def require_checker(self) -> Checker:
        checker: object = self.checker
        if not isinstance(checker, Checker):
            raise ValueError(f"Checker result {self.pk} has no valid checker")
        return checker

    def only_title(self) -> bool:
        """ Whether there is additional information (log or artefacts) """
        return not self.log and not self.artefacts.exists()

    def required(self) -> bool:
        """ Checks if the Checker is *required* to be passed. """
        return self.require_checker().required

    def public(self) -> bool:
        """ Checks if the results of the Checker are to be shown *publicly*, i.e.: even to the submitter """
        return self.require_checker().show_publicly(self.passed)

    def is_critical(self) -> bool:
        """ Checks if further results should not be shown """
        return self.require_checker().is_critical(self.passed)

    def set_log(
        self,
        log: str,
        timed_out: bool = False,
        truncated: bool = False,
        oom_ed: bool = False,
    ) -> None:
        """ Sets the log of the Checker run. timed_out and truncated indicated if appropriate error messages shall be appended  """
        if timed_out:
            log = f'<div class="error">Timeout occurred! (after {settings.TEST_TIMEOUT} seconds)</div>' + log
        if truncated:
            log = '<div class="error">Output too long, truncated</div>' + log
        if oom_ed:
            log = '<div class="error">Memory limit exceeded, execution cancelled.</div>' + log

        self.log = log

    def set_passed(self, passed: int) -> None:
        """ Sets the passing state of the Checker. """
        assert isinstance(passed, int)
        self.passed = passed

    def set_passed_with_warning(self, passed_with_warning: bool) -> None:
        """ Sets the passed with warning flag of the Checker. """
        assert isinstance(passed_with_warning, bool)
        self.passed_with_warning = passed_with_warning

    def add_artefact(self, filename: str, path: str) -> None:
        assert os.path.isfile(path)
        artefact = CheckerResultArtefact(result = self, filename=filename)
        with open(path, 'rb') as fd:
            artefact.file.save(filename, File(fd))

def get_checkerresultartefact_upload_path(
    instance: "CheckerResultArtefact", filename: str
) -> str:
    result = instance.result
    solution = result.solution
    return os.path.join(
        'SolutionArchive',
        'Task_' + str(solution.task.id),
        'User_' + solution.author.username,
        'Solution_' + str(solution.id),
        'Result_' + str(result.id),
        filename)

class CheckerResultArtefact(models.Model):

    if TYPE_CHECKING:
        id: models.AutoField[int | None, int]

    result: "models.ForeignKey[CheckerResult, CheckerResult]" = models.ForeignKey(CheckerResult, related_name='artefacts', on_delete=models.CASCADE)
    result_id: int
    filename: "models.CharField[str, str]" = models.CharField(max_length=128)
    file: models.FileField = models.FileField(
        upload_to = get_checkerresultartefact_upload_path,
        max_length=500,
        help_text = gettext_lazy('Artefact produced by a checker')
        )

    def __str__(self) -> str:
        return self.filename

    def path(self) -> str:
        return self.filename

# from http://stackoverflow.com/questions/5372934
@receiver(post_delete, sender=CheckerResultArtefact)
def solution_file_delete(
    sender: type[CheckerResultArtefact],
    instance: CheckerResultArtefact,
    **kwargs: object,
) -> None:
    # Pass false so FileField doesn't save the model.
    if not instance.file:
        return
    filename = instance.file.path
    instance.file.delete(False)
    # Remove left over empty directories
    dirname = os.path.dirname(filename)
    try:
        while os.path.basename(dirname) != "SolutionArchive":
            os.rmdir(dirname)
            dirname = os.path.dirname(dirname)
    except OSError:
        pass

def check_solution(
    solution: Solution,
    run_all: object = 0,
    debug_keep_tmp: bool = True,
    secondary_check: bool = False,
) -> None:
    """Builds and tests this solution."""
    
    # set up environment
    env = CheckerEnvironment(solution)

    try:
        solution.copySolutionFiles(env.tmpdir())
        run_checks(solution, env, run_all, secondary_check)
        if run_all:
            solution.all_checker_finished = True
            solution.save()
    finally:
        if not(debug_keep_tmp and settings.DEBUG):
            shutil.rmtree(env.tmpdir())

# Assumes to be called from within a @transaction.autocommit Context!!!!
def check_with_own_connection(
    solution: Solution,
    run_all: object = True,
    debug_keep_tmp: bool = True,
    secondary_check: bool = False,
) -> None:
    # Close the current db connection - will cause Django to create a new connection (not shared with other processes)
    # when one is needed, see https://groups.google.com/forum/#!msg/django-users/eCAIY9DAfG0/6DMyz3YuQDgJ
    connection.close()
    try:
        check_solution(solution, run_all, debug_keep_tmp, secondary_check)
    finally:
        connection.close()

def check_with_own_connection_rev(
    run_all: object,
    debug_keep_tmp: bool,
    solution: Solution,
    secondary_check: bool = False,
) -> None:
    return check_with_own_connection(solution, run_all, debug_keep_tmp, secondary_check)


def check_multiple(
    solutions: "Iterable[Solution]",
    run_secret: object = False,
    debug_keep_tmp: bool = False,
    secondary_check: bool = False,
) -> None:
    if settings.NUMBER_OF_TASKS_TO_BE_CHECKED_IN_PARALLEL <= 1:
        for solution in solutions:
            solution.check_solution(run_secret, debug_keep_tmp, secondary_check)
    else:
        check_it = partial(check_with_own_connection_rev, run_secret, debug_keep_tmp, secondary_check = secondary_check)

        try:
            with Pool(processes=settings.NUMBER_OF_TASKS_TO_BE_CHECKED_IN_PARALLEL) as pool:
                pool.map(check_it, solutions, 1)
        finally:
            connection.close()





def run_checks(
    solution: Solution,
    env: CheckerEnvironment,
    run_all: object,
    secondary_check: bool = False,
) -> None:
    """  """

    passed_checkers: set[type[Checker]] = set()
    checkers = solution.task.get_checkers()

    solution_accepted = True
    solution.warnings = False

    for checker in checkers:
        # dont rerun previously run checkers in nightly run
        dont_rerun = secondary_check and checker.results.filter(solution=solution).exists()

        if (checker.always or run_all) and not dont_rerun:
            # Check dependencies -> This requires the right order of the checkers
            can_run_checker = True
            for requirement in checker.requires():
                passed_requirement = False
                for passed_checker in passed_checkers:
                    passed_requirement = passed_requirement or issubclass(passed_checker, requirement)
                can_run_checker = can_run_checker and passed_requirement

            start_time = time.time()

            if can_run_checker:
                # Invoke Checker
                # TODO: well perhaps we could use settings.MIRROR to let store mails as file for development or test
                if settings.DEBUG or 'test' in sys.argv:
                    result = checker.run(env)
                else:
                    try:
                        result = checker.run(env)
                    except Exception as error:
                        result = checker.create_result(env)
                        result.set_log("The Checker caused an unexpected internal error.")
                        result.set_passed(False)
                        #TODO: signed Email Admins
                        # sys has been imported at top of file
                        exnow = datetime.now()
                        dt_string = exnow.strftime("%d/%m/%Y %H:%M:%S")
#                        myRequestUser = User.objects.filter(id=request.user.id)
                        myTask = Task.objects.filter(id=solution.task_id)
                        myerrmsg = " %s => %s " % (type(error).__name__, error)
                        plaintext = loader.get_template('checker/exception.txt')
                        htmly = loader.get_template('checker/exception.html')
                        c = {
#                              'protocol' : request.is_secure() and "https" or "http",
#                              'domain' : RequestSite(request).domain,
                              'base_host' : settings.BASE_HOST,
                              'site_name' : settings.SITE_NAME,
                              'solution' : solution,
                              'checker' : checker,
                              'errormsg' : myerrmsg,
                              'datetime' : dt_string,
                        }
                        mail_admins(gettext_lazy("%s : checker in %s failed")%(settings.SITE_NAME, myTask), plaintext.render(c),html_message=htmly.render(c))
                        if settings.DEBUG :
                            print (gettext_lazy("%s : checker in %s failed \n %s")%(settings.SITE_NAME, myTask, plaintext.render(c)))
                        #raise
            else:
                # make non passed result
                # this as well as the dependency check should propably go into checker class
                # TODO: Move code to checker class ?
                result = checker.create_result(env)
                #result.set_log("Checker konnte nicht ausgeführt werden, da benötigte Checker nicht bestanden wurden.")
                result.set_log("Checker failed to run because required checkers failed.")
                result.set_passed(False)

            elapsed_time = time.time() - start_time
            result.runtime = int(elapsed_time*1000)
            result.log = result.log.replace("\x00", "")
            result.save()

            if not result.passed and checker.show_publicly(result.passed):
                if checker.required:
                    solution_accepted = False
                else:
                    solution.warnings= True

            if result.passed:
                passed_checkers.add(checker.__class__)
                if result.passed_with_warning and checker.show_publicly(result.passed):
                    solution.warnings = True
    solution.accepted = solution_accepted
    solution.save()
