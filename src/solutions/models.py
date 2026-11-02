import zipfile
import tempfile
import shutil
import os, re
from collections.abc import Sequence as _Sequence
from email.mime.base import MIMEBase as _MIMEBase
from datetime import datetime
from email.message import Message
from email.message import EmailMessage as StdlibEmailMessage
from email.generator import BytesGenerator
from email.parser import BytesParser
from email.policy import Policy
from contextlib import ExitStack
from io import BytesIO
from typing import TYPE_CHECKING, Any as _Any, BinaryIO

from hashlib import sha256

from django.db import models
from django.utils.translation import gettext_lazy
from django.core.files import File
from django.db.models import Max
from django.db import transaction
from django.conf import settings
from django.template.loader import render_to_string
from django.db.models.signals import post_delete
from django.dispatch.dispatcher import receiver
from django.core.mail import EmailMessage
from django.core.mail.backends.base import BaseEmailBackend

from accounts.models import User
from utilities import encoding, file_operations
from utilities.mimetypes import guess_mime_type_with_fallback as guess_mime_type
from configuration import get_settings

if TYPE_CHECKING:
    from django_stubs_ext import StrOrPromise
    from django.db.models.fields.related_descriptors import ReverseManyToOneDescriptor
    from attestation.models import AnnotatedSolutionFile
    from attestation.models import Attestation as _Attestation
    from checker.basemodels import CheckerResult as _CheckerResult
    from tasks.models import Task as _Task

class Solution(models.Model):
    """ """

    if TYPE_CHECKING:
        id: models.AutoField[int | None, int]
        attestation_set: ReverseManyToOneDescriptor[_Attestation]
        checkerresult_set: ReverseManyToOneDescriptor[_CheckerResult]
        solutionfile_set: ReverseManyToOneDescriptor["SolutionFile"]
        model_solution_task: ReverseManyToOneDescriptor[_Task]

    number: "models.IntegerField[int | None, int | None]" = models.IntegerField(null=False, editable=False, help_text = gettext_lazy("Id unique in task and user. E.g. Solution 1 of user X in task Y in contrast to global solution Z"))

    task: "models.ForeignKey[_Task, _Task]" = models.ForeignKey('tasks.task', on_delete=models.CASCADE)
    task_id: int
    author: "models.ForeignKey[User, User]" = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="solution author")
    author_id: int
    creation_date: "models.DateTimeField[datetime, datetime]" = models.DateTimeField(auto_now_add=True)

    testupload: "models.BooleanField[bool, bool]" = models.BooleanField( default = False, help_text = gettext_lazy('Indicates whether this solution is a test upload.'))
    accepted: "models.BooleanField[bool, bool]" = models.BooleanField( default = False, help_text = gettext_lazy('Indicates whether the solution has passed all public and required tests.'))
    warnings: "models.BooleanField[bool, bool]" = models.BooleanField( default = False, help_text = gettext_lazy('Indicates whether the solution has at least failed one public and not required test.'))
    plagiarism: "models.BooleanField[bool, bool]" = models.BooleanField( default = False, help_text = gettext_lazy('Indicates whether the solution is a rip-off of another one.'))
    final: "models.BooleanField[bool, bool]" = models.BooleanField( default = False, help_text = gettext_lazy('Indicates whether this solution is the last (accepted) of the author.'))
    all_checker_finished: "models.BooleanField[bool, bool]" = models.BooleanField(default = False, help_text = gettext_lazy('Indicates whether all checkers have been run for this solution.'))
    allow_llm_upload: "models.BooleanField[bool, bool]" = models.BooleanField(default = False, verbose_name=gettext_lazy("I agree to my solution being uploaded to an LLM for evaluation purposes."), help_text = gettext_lazy('Indicates whether the student allows the solution to be uploaded to an LLM.'))

    def __str__(self) -> str:
        return "%s:%s:%s" % (self.task, self.author , self.number)
        #return str(self.task) + ":" + str(self.author) + ":" + str(self.number)

    def allCheckerResults(self) -> "list[_CheckerResult]":
        results = self.checkerresult_set.all().prefetch_related('artefacts')
        return until_critical(sorted(results, key=lambda result: result.require_checker().order))

    def publicCheckerResults(self) -> "list[_CheckerResult]":
        # return self.checkerresult_set.filter(checker__public=True) won't work, because checker is a genericForeignKey!
        results = self.checkerresult_set.all().prefetch_related('artefacts')
        return until_critical(sorted([x for x in results if x.public()], key = lambda result: result.require_checker().order))

    def copySolutionFiles(self, toTempDir: str) -> None:
        for file in self.solutionfile_set.all():
            file.copyTo(toTempDir)

    @transaction.atomic
    def save(self, *args: _Any, **kwargs: _Any) -> None:
        """Override save calculate the number on first save"""
        if self.number == None:
            self.number = (self.task.solution_set.filter(author=self.author).aggregate(Max('number'))['number__max'] or 0) + 1
            if 'update_fields' in kwargs:
                kwargs['update_fields'] = {'number'}.union(kwargs['update_fields'])
        if self.final:
            # delete old final flag if this is the new final solution
            self.task.solutions(self.author).update(final=False)
            # may need to re-run jplag
            self.task.need_to_re_run_jplag()
        super(Solution, self).save(*args, **kwargs) # Call the "real" save() method.

    def check_solution(self, run_secret: object = 0, debug_keep_tmp: bool = False, secondary_check: bool = False) -> None:
        """Builds and tests this solution."""
        from checker.basemodels import check_solution
        check_solution(self, run_secret, debug_keep_tmp, secondary_check)

    def attestations_by(self, user: User) -> "models.QuerySet[_Attestation, _Attestation]":
        return self.attestation_set.filter(author=user)

    def copy(self) -> None:
        """ create a copy of this solution """
        self.final = False
        self.save()
        # We need to force the evaluation of the following queries before
        # duplicating the solution object in the database.
        # Otherwise, the queries will be executed for the new object instead of
        # the old one (and nothing will be found).
        solutionfiles = list(self.solutionfile_set.all())
        checkerresults = list(self.checkerresult_set.all())
        self.id = None
        self.number = None
        self.final = True
        self.save()
        for file in solutionfiles:
            file.id = None
            file.solution = self
            file.save()
        for result in checkerresults:
            result.id = None
            result.solution = self
            result.save()

    def textSolutionFiles(self) -> list["SolutionFile"]:
        return [file for file in self.solutionfile_set.all() if (not file.isBinary()) ]

    def displayableSolutionFiles(self) -> list["SolutionFile"]:
        return [file for file in self.solutionfile_set.all() if (not file.isBinary() or file.isImage() or file.isEmbeddable())]


def until_critical(l: "list[_CheckerResult]") -> "list[_CheckerResult]":
    res: list[_CheckerResult] = []
    for r in l:
        res.append(r)
        if r.is_critical():
            break
    return res

def get_solutionfile_upload_path(instance: "SolutionFile", filename: str) -> str:
    solution = instance.solution
    return 'SolutionArchive/Task_' + str(solution.task.id) + '/User_' + solution.author.username.replace("/","\u2044") + '/Solution_' + str(solution.id) + '/' + filename

class SolutionFile(models.Model):
    """docstring for SolutionFile"""

    if TYPE_CHECKING:
        id: models.AutoField[int | None, int]
        annotatedsolutionfile_set: ReverseManyToOneDescriptor[AnnotatedSolutionFile]

    solution: "models.ForeignKey[Solution, Solution]" = models.ForeignKey(Solution, on_delete=models.CASCADE)
    solution_id: int
    file: models.FileField = models.FileField(upload_to = get_solutionfile_upload_path, max_length=500, help_text = gettext_lazy('Source code file as part of a solution an archive file (.zip) containing multiple solution files.'))
    mime_type: "models.CharField[str, str]" = models.CharField(max_length=100, help_text = gettext_lazy("Guessed file type. Automatically  set on save()."))

    # ignore hidden or os-specific files, etc. in zipfiles
    regex: str = r'(' + '|'.join([
                        r'(^|/)\..*',         # files starting with a dot (unix hidden files)
                        r'__MACOSX/.*',
                        r'^/.*',            # path starting at the root dir
                        r'\.\..*',            # parent folder with '..'
                        r'/$',                # don't unpack folders - the zipfile package will create them on demand
                    ]) + r')'

    ignorred_file_names_re: re.Pattern[str] = re.compile(regex)

    def save(self, *args: _Any, **kwargs: _Any) -> None:
        """ override save method to automatically expand zip files"""
        name = file_operations.require_file_name(self.file)
        if name.upper().endswith('.ZIP'):
            with zipfile.ZipFile(self.file, 'r') as zip:
                for zip_file_name in zip.namelist():
                    if not self.ignorred_file_names_re.search(zip_file_name):
                        new_solution_file = SolutionFile(solution=self.solution)
                        with tempfile.NamedTemporaryFile() as temp_file:
                            temp_file.write(zip.read(zip_file_name))
                            temp_file.seek(0)
                            new_solution_file.file.save(zip_file_name, File(temp_file), save=True)
        else:
            self.mime_type = guess_mime_type(name)
            if 'update_fields' in kwargs:
                kwargs['update_fields'] = {'mime_type'}.union(kwargs['update_fields'])
            super().save(*args, **kwargs)

    def __str__(self) -> str:
        return file_operations.require_file_name(self.file).rpartition('/')[2]

    def get_hash(self) -> str:
        self.file.seek(0)
        s = sha256()
        s.update(self.file.read())
        return s.hexdigest()

    def isBinary(self) -> bool:
        return self.mime_type[:4] != "text"

    def isImage(self) -> bool:
        return self.mime_type[:5] == "image"

    def isEmbeddable(self) -> bool:
        return self.mime_type in ("application/pdf",)

    def path(self) -> str:
        """ path of file relative to the zip file, which once contained it """
        # dont use length of filename as in original Code but use reg-expression!!
        # Original Code was:
        # return self.file.name[len(get_solutionfile_upload_path(self, '')):]

        # Fix for: https://github.com/KITPraktomatTeam/Praktomat/issues/232
        # It is realy saver not to use the length, i.e. if someone resubmit a solution via button and the new solution-number switched
        # from xxxx to yyyyy, the first letter of filename get lost if here only the length was used!!

        # TODO: Refactoring at the end of file there is a regexpr-based function "id_for_path(path)"
        #       should or could we used that function here?
        #
        # This fix for https://github.com/KITPraktomatTeam/Praktomat/issues/232
        # is used at H-BRS since May 2016 (Robert Hartmann)
        name = file_operations.require_file_name(self.file)
        match = re.fullmatch(r'SolutionArchive/Task_\d+/User_[^/]+/Solution_\d+/(.+)', name, re.DOTALL)
        if match is None:
            raise ValueError(f"Invalid SolutionArchive file path: {name!r}")
        return match.group(1)


    def content(self) -> str:
        """docstring for content"""
        if self.isBinary():
            return "Binary Data"
        else:
            return encoding.get_unicode(self.file.read())

    def copyTo(self, directory: str) -> None:
        """ Copies this file to the given directory """
        new_file_path = os.path.join(directory, self.path())
        if self.isBinary():
            full_directory = os.path.join(directory, os.path.dirname(self.path()))
            if not os.path.exists(full_directory):
                file_operations.makedirs(full_directory)
            shutil.copy(self.file.path, new_file_path)
        else:
            file_operations.create_file(new_file_path, self.content())

# from http://stackoverflow.com/questions/5372934
@receiver(post_delete, sender=SolutionFile)
def solution_file_delete(
    sender: type[SolutionFile], instance: SolutionFile, **kwargs: object
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



def get_solutions_zip(solutions: "list[Solution] | models.QuerySet[Solution, Solution]",include_copy_checker_files: bool=False,include_artifacts: bool=False) -> BinaryIO:
    with ExitStack() as failed_export:
        zip_file = tempfile.TemporaryFile()
        failed_export.callback(zip_file.close)
        with ExitStack() as temporary, zipfile.ZipFile(zip_file, 'w', allowZip64=True) as zip:
            _write_solutions_zip(zip, solutions, include_copy_checker_files, include_artifacts, temporary)
        zip_file.seek(0)
        failed_export.pop_all()
        return zip_file


def _write_solutions_zip(
    zip: zipfile.ZipFile,
    solutions: "list[Solution] | models.QuerySet[Solution, Solution]",
    include_copy_checker_files: bool,
    include_artifacts: bool,
    temporary: ExitStack,
) -> None:
    praktomat_files_destination          = "praktomat-files/"
    testsuite_destination                = praktomat_files_destination + "testsuite/"
    createfile_checker_files_destination = praktomat_files_destination + "other/"
    script_checker_files_destination     = praktomat_files_destination + "other/"
    checkstyle_checker_files_destination = praktomat_files_destination + "checkstyle/"
    artefact_files_destination           = praktomat_files_destination + "artefacts/"
    solution_files_destination           = "solution/"

    createfile_checker_files_destinations: set[str] = set()
    createfile_checker_files: list[tuple[str, str]] = []

    if include_copy_checker_files:
        createfile_checker = { checker for solution in solutions for checker in solution.task.createfilechecker_set.all().filter(include_in_solution_download=True) }
        createfile_checker_files = [
            (createfile_checker_files_destination + checker.path_relative_to_sandbox(), checker.file.path)
            for checker in createfile_checker if not checker.unpack_zipfile
        ]
        # Temporary build directory
        sandbox = settings.SANDBOX_DIR
        tmpdir = file_operations.create_tempfolder(sandbox)
        temporary.callback(shutil.rmtree, tmpdir)
        for zipchecker in [ checker for checker in createfile_checker if checker.unpack_zipfile ]:
            cleanpath = zipchecker.path.lstrip("/ ")
            path = os.path.join(tmpdir, cleanpath)
            file_operations.unpack_zipfile_to(zipchecker.file.path, path,
                lambda n: None,
                lambda f: createfile_checker_files.append((
                    os.path.join(createfile_checker_files_destination, os.path.join(cleanpath, f)),
                    os.path.join(path, f)
                ))
            )
        createfile_checker_files_destinations = {createfile_checker_files_destination + checker.path for checker in createfile_checker if checker.is_sourcecode}



    for index, solution in enumerate(solutions, start=1):
        # TODO: make this work for anonymous attestation, too
        if get_settings().anonymous_attestation:
            project_path = f'User{index}'
            project_name = f'{solution.task}-User {index}'
        else:
            project_path = path_for_user(solution.author)
            project_name = str(solution.task) + "-" + solution.author.get_full_name()
        base_name = path_for_task(solution.task) + '/' + project_path + '/'

        # We need to pass unicode strings to ZipInfo to ensure that it sets bit
        # 11 appropriately if the filename contains non-ascii characters.
        assert isinstance(base_name, str)

        checkstyle_checker_files: list[tuple[str, str]] = []
        script_checker_files: list[tuple[str, str]] = []
        artefact_files: list[tuple[str, str]] = []
        junit_checker = solution.task.junitchecker_set.none()
        junit3 = False
        junit4 = False
        checkstyle = False
        if include_copy_checker_files:
            checkstyle_checker = solution.task.checkstylechecker_set.all()
            script_checker     = solution.task.scriptchecker_set.all()
            junit_checker      = solution.task.junitchecker_set.all()
            junit3     = bool([ 0 for j in junit_checker if  j.junit_version == 'junit3' ])
            junit4     = bool([ 0 for j in junit_checker if  j.junit_version == 'junit4' ])
            checkstyle = bool(checkstyle_checker)

            checkstyle_checker_files = [
                (checkstyle_checker_files_destination + os.path.basename(file_operations.require_file_name(checker.configuration)), checker.configuration.path)
                for checker in checkstyle_checker
            ]
            script_checker_files = [
                (script_checker_files_destination + checker.path_relative_to_sandbox(), checker.shell_script.path)
                for checker in script_checker
            ]

        if include_artifacts:
            artefacts = [ artefact for result in solution.allCheckerResults() for artefact in result.artefacts.all() ]
            artefact_files = [
                (artefact_files_destination + os.path.basename(file_operations.require_file_name(artefact.file)), artefact.file.path)
                for artefact in artefacts
            ]

        zip.writestr(base_name+'.project', render_to_string('solutions/eclipse/project.xml', { 'name': project_name, 'checkstyle' : checkstyle }).encode("utf-8"))
        zip.writestr(base_name+'.settings/org.eclipse.jdt.core.prefs', render_to_string('solutions/eclipse/settings/org.eclipse.jdt.core.prefs', { }).encode("utf-8"))

        zip.writestr(base_name+'.classpath', render_to_string('solutions/eclipse/classpath.xml', {'junit3' : junit3, 'junit4': junit4, 'createfile_checker_files' : include_copy_checker_files, 'createfile_checker_files_destinations' : createfile_checker_files_destinations, 'testsuite_destination' : testsuite_destination }).encode("utf-8"))
        if checkstyle:
            zip.writestr(base_name+'.checkstyle', render_to_string('solutions/eclipse/checkstyle.xml', {'checkstyle_files' : [filename for (filename, _) in checkstyle_checker_files], 'createfile_checker_files_destination' : createfile_checker_files_destination, 'testsuite_destination' : testsuite_destination }).encode("utf-8"))

        if junit4:
            zip.writestr(base_name+testsuite_destination+'AllJUnitTests.java', render_to_string('solutions/eclipse/AllJUnitTests.java', { 'testclasses' : [ j.class_name for j in junit_checker if j.junit_version == 'junit4' ]}).encode("utf-8"))
            zip.writestr(base_name+praktomat_files_destination+'AllJUnitTests.launch', render_to_string('solutions/eclipse/AllJUnitTests.launch', { 'project_name' : project_name, 'praktomat_files_destination' : praktomat_files_destination}).encode("utf-8"))
            zip.write(os.path.dirname(__file__)+"/../checker/scripts/eclipse-junit.policy", (base_name+praktomat_files_destination+'eclipse-junit.policy'))

        solution_files = [(solution_files_destination + solutionfile.path(), solutionfile.file.path) for solutionfile in solution.solutionfile_set.all()]

        for (name, source_path) in solution_files + createfile_checker_files + checkstyle_checker_files + script_checker_files + artefact_files:
            zippath = os.path.normpath(base_name + name)
            assert isinstance(zippath, str)
            try: # Do not overwrite files from the solution by checker files
                zip.getinfo(zippath)
            except KeyError:
                zip.write(source_path, zippath)
                assert zip.getinfo(zippath) # file was really added under name "zippath" (not only some normalization thereof)

def path_for_user(user: User) -> str:
    return user.get_full_name().replace("/","\u2044")+'-'+str(user.mat_number)+'-'+str(user.id)

def path_for_task(task: "_Task") -> str:
    return task.title

path_regexp: re.Pattern[str] = re.compile(r'[^-]*-[^-]*-(.*)')

def id_for_path(path: str) -> str:
    match = path_regexp.fullmatch(path)
    if match is None:
        raise ValueError(f"Invalid user archive path: {path!r}")
    return match.group(1)

class ConfirmationMessage(EmailMessage):
    """
    Special EmailMessage to combine headers set by OpenSSL S/MIME and django sendmail.
    """
    def __init__(
        self,
        subject: "StrOrPromise" = '',
        body: "StrOrPromise | None" = '',
        from_email: str | None = None,
        to: _Sequence[str] | None = None,
        bcc: _Sequence[str] | None = None,
        connection: BaseEmailBackend | None = None,
        attachments: _Sequence[
            _MIMEBase
            | tuple[str, str | bytes | Message | EmailMessage]
            | tuple[str | None, str | bytes | Message | EmailMessage, str]
            | tuple[str, str | bytes | Message | EmailMessage, None]
        ] | None = None,
        headers: dict[str, str] | None = None,
        cc: _Sequence[str] | None = None,
        reply_to: _Sequence[str] | None = None,
    ) -> None:
        super(ConfirmationMessage, self).__init__(
            subject, body, from_email, to, bcc=bcc, connection=connection,
            attachments=attachments, headers=headers, cc=cc, reply_to=reply_to,
        )

    def message(self, *, policy: Policy | None = None) -> "MessageWrapper":
        message = super(ConfirmationMessage, self).message()
        return MessageWrapper(message, policy=policy)

class MessageWrapper(StdlibEmailMessage):
    """Expose signed MIME content while preserving Django 5.2 wire serialization."""

    def __init__(self, message: Message, *, policy: Policy | None = None) -> None:
        super().__init__(policy=policy or message.policy)
        self.message = message
        parsed = BytesParser(policy=self.policy).parsebytes(self.as_bytes())
        for name, value in parsed.raw_items():
            self.set_raw(name, value)
        self.set_payload(parsed.get_payload())

    # Django supplies Strings as "linesep" (and not Bytes)
    def as_bytes(
        self, unixfrom: bool = False, policy: Policy | None = None, *, linesep: str | None = None
    ) -> bytes:
        selected_policy = policy or self.policy
        linesep = linesep if linesep is not None else selected_policy.linesep
        # byte version of linesep
        linesep_bytes = linesep.encode('ascii')
        # Construct the message with the full S/MIME mail as body
        stream = BytesIO()
        generator = BytesGenerator(stream, mangle_from_=False, policy=selected_policy)
        generator.flatten(self.message, unixfrom=unixfrom, linesep=linesep)
        msg = stream.getvalue()
        envelope = b''
        if unixfrom:
            envelope, _, msg = msg.partition(linesep_bytes)
            envelope += linesep_bytes
        # Now, use the S/MIME headers as headers for the email
        lines = msg.split(linesep_bytes)
        if (len(lines) < 3 or lines[0] != b'Content-Type: text/plain; charset="utf-8"' or
                lines[1] != b'MIME-Version: 1.0' or
                not re.match(b'Content-Transfer-Encoding: (7|8)bit', lines[2])):
            raise AssertionError('Assumptions on message format violated')
        try:
            i = lines.index(b'')
            j = lines[i+1:].index(b'') + i + 1
        except ValueError as error:
            raise ValueError("Invalid signed MIME message: missing header separator.") from error
        transformed = lines[i+1:j] + lines[3:i] + lines[j+1:]
        return envelope + linesep_bytes.join(transformed)

    def get_charset(self) -> None:
        return None
