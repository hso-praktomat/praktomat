from datetime import date, datetime, timedelta
import tempfile
import typing as _typing
import decimal as _decimal
import zipfile
import os
import os.path
import shutil
from contextlib import ExitStack

from django.apps import apps
from django.db import models
from django.db import transaction
from django.core import serializers
from django.core.exceptions import ValidationError
from django.core.files import File
from django.utils.translation import gettext_lazy
from django.conf import settings
from django.db.models.fields.files import FieldFile

from accounts.models import User
from configuration import get_settings

from utilities.deleting_file_field import DeletingFileField
from utilities.file_operations import require_file_name
from utilities.safeexec import execute_arglist

if _typing.TYPE_CHECKING:
    from django.db.models.fields.related_descriptors import ReverseManyToOneDescriptor
    from attestation.models import Rating as _Rating
    from attestation.models import RatingScale as _RatingScale
    from checker.basemodels import Checker as _Checker
    from checker.checker.CheckStyleChecker import CheckStyleChecker as _CheckStyleChecker
    from checker.checker.CreateFileChecker import CreateFileChecker as _CreateFileChecker
    from checker.checker.JUnitChecker import JUnitChecker as _JUnitChecker
    from checker.checker.ScriptChecker import ScriptChecker as _ScriptChecker
    from solutions.models import Solution as _Solution


class Task(models.Model):
    if _typing.TYPE_CHECKING:
        id: models.AutoField[int | None, int]
        rating_set: ReverseManyToOneDescriptor[_Rating]
        solution_set: ReverseManyToOneDescriptor[_Solution]
        checkstylechecker_set: ReverseManyToOneDescriptor[_CheckStyleChecker]
        createfilechecker_set: ReverseManyToOneDescriptor[_CreateFileChecker]
        junitchecker_set: ReverseManyToOneDescriptor[_JUnitChecker]
        scriptchecker_set: ReverseManyToOneDescriptor[_ScriptChecker]
        mediafile_set: ReverseManyToOneDescriptor["MediaFile"]
        htmlinjector_set: ReverseManyToOneDescriptor["HtmlInjector"]
        submissionblacklistentry_set: ReverseManyToOneDescriptor["SubmissionBlacklistEntry"]
        deadlineextension_set: ReverseManyToOneDescriptor["DeadlineExtension"]
    title: "models.CharField[str, str]" = models.CharField(max_length=100, help_text = gettext_lazy("The name of the task"))
    description: "models.TextField[str, str]" = models.TextField(help_text = gettext_lazy("Description of the assignment."))
    publication_date: "models.DateTimeField[date | datetime, datetime]" = models.DateTimeField(help_text = gettext_lazy("The time on which the user will see the task."))
    submission_date: "models.DateTimeField[datetime, datetime]" = models.DateTimeField(help_text = gettext_lazy("The time up until the user has time to complete the task. This time will be extended by the duration configured with the deadline tolerance setting for those who just missed the deadline."))

    submission_free_uploads: "models.IntegerField[int, int]" = models.IntegerField(default=1, help_text =gettext_lazy("Number of submissions a user can make before waitdelta got active"))
    submission_waitdelta: "models.IntegerField[int, int]" = models.IntegerField(default=0,help_text=gettext_lazy("Timedelta in minutes. The user must wait before submitting the next solution of same task: I removed the linear function: Timedelta multiplied with number of current uploads"))
    submission_maxpossible: "models.IntegerField[int, int]" = models.IntegerField(default=-1,help_text=gettext_lazy("Number of uploads a user can submit for the same task. Value -1 means unlimited"))

    max_file_size: "models.IntegerField[int, int]" = models.IntegerField(default=1000, help_text = gettext_lazy("The maximum size of an uploaded solution file in kibibyte."))
    model_solution: "models.ForeignKey[_Solution | None, _Solution | None]" = models.ForeignKey('solutions.Solution', on_delete=models.SET_NULL, blank=True, null=True, related_name='model_solution_task')
    model_solution_id: int | None
    all_checker_finished: "models.BooleanField[bool, bool]" = models.BooleanField(default=False, editable=False, help_text = gettext_lazy("Indicates whether the checker which don't run immediately on submission have been executed."))
    final_grade_rating_scale: "models.ForeignKey[_RatingScale | None, _RatingScale | None]" = models.ForeignKey('attestation.RatingScale', on_delete=models.SET_NULL, null=True, help_text = gettext_lazy("The scale used to mark the whole solution."))
    final_grade_rating_scale_id: int | None
    warning_threshold: "models.DecimalField[_decimal.Decimal, _decimal.Decimal]" = models.DecimalField(max_digits=8, decimal_places=2, default=0, help_text = gettext_lazy("If the student has less points in his tasks than the sum of their warning thresholds, display a warning."))
    only_trainers_publish: "models.BooleanField[bool, bool]" = models.BooleanField(default=False, help_text = gettext_lazy("Indicates that only trainers may publish attestations. Otherwise, tutors may publish final attestations within their tutorials."))
    jplag_up_to_date: "models.BooleanField[bool, bool]" = models.BooleanField(default=False, help_text = gettext_lazy("No new solution uploads since the last jPlag run"))
    exam: "models.BooleanField[bool, bool]" = models.BooleanField(default=False, help_text = gettext_lazy("If enabled, solutions (incl. attestations) of expired tasks and active tasks that are not exams are not accessible for students starting 60 minutes before the publication date until 15 minutes after the deadline. Media files will only be visible while the task is active. After the deadline passed, solutions for this task won't be visible until they got attested."))
    custom_id: "models.CharField[str, str]" = models.CharField(max_length=255, blank=True, help_text = gettext_lazy("The custom ID of the task that is available as an environment variable within a checker (TASK_ID_CUSTOM). This is also used to replace the task ID in the external directory path for the checkers."))

    class Meta:
        ordering: list[str] = ['submission_date', 'title']

    def __str__(self) -> str:
        return self.title

    def solutions(self, user: User) -> "models.QuerySet[_Solution, _Solution]":
        """ get ALL solutions of the specified user """
        return self.solution_set.filter(author=user)

    def final_solution(self, user: User) -> "_Solution | None":
        """ get FINAL solution of specified user """
        solutions = self.solution_set.filter(author=user, final=True)
        return solutions.first()

    def expired(self) -> bool:
        """returns whether the task has expired"""
        return self.submission_date + get_settings().deadline_tolerance < datetime.now()

    def expired_for_user(self, user: User) -> bool:
        """returns whether the task has expired for a certain user"""
        if SubmissionBlacklistEntry.objects.filter(task=self, user=user).exists():
            return True
        for deadline_extension in DeadlineExtension.objects.filter(task=self, user=user):
            return deadline_extension.timestamp + get_settings().deadline_tolerance < datetime.now()
        return self.expired()

    def submission_date_for_user(self, user: User) -> datetime:
        """returns the effective submission date for a certain user"""
        for deadline_extension in DeadlineExtension.objects.filter(task=self, user=user):
            return deadline_extension.timestamp
        return self.submission_date

    def check_all_final_solutions(self, secondary_check: bool = False) -> int:
        from checker.basemodels import check_multiple
        final_solutions = [solution for solution in self.solution_set.filter(final=True) if self.expired_for_user(solution.author)]
        check_multiple(final_solutions, True, secondary_check=secondary_check)

        if self.expired():
            self.all_checker_finished = True
            self.save()
        return len(final_solutions)

    def check_all_latest_only_failed_solutions(self) -> int:
        from checker.basemodels import check_solution
        solution_queryset = self.solution_set
        final_solutions_queryset = solution_queryset.filter(final=True)
        final_users = set(final_solutions_queryset.values_list('author', flat=True))

        # All solutions from users without a final solution
        only_failed_solution_set = solution_queryset.exclude(author__in=final_users)
        # Users without a final solution (maybe without an upload at all)
        non_final_users = set(User.objects.all().values_list('id', flat=True)) - final_users

        count = 0
        for user in non_final_users:
            users_only_failed_solutions = only_failed_solution_set.filter(author=user)
            if users_only_failed_solutions.count() > 0:
                latest_only_failed_solution = users_only_failed_solutions.latest('number')
                if self.expired_for_user(user):
                    check_solution(latest_only_failed_solution, True)
                count += 1
        return count

    def check_unchecked_final_solutions(self, secondary_check: bool = False) -> int:
        from checker.basemodels import check_multiple
        final_solutions = [solution for solution in self.solution_set.filter(all_checker_finished=False, final=True) if self.expired_for_user(solution.author)]
        check_multiple(final_solutions, True, secondary_check = secondary_check)
        return len(final_solutions)

    def get_checkers(self) -> "list[_Checker]":
        from checker.basemodels import Checker
        checker_app = apps.get_app_config('checker')

        checker_classes = [x for x in checker_app.get_models() if issubclass(x, Checker)]
        unsorted_checker = [
            checker for checker_class in checker_classes
            for checker in checker_class.objects.filter(task=self)
        ]
        checkers = sorted(unsorted_checker, key=lambda checker: checker.order)
        return checkers

    def jplag_dir_path(self) -> str:
        return os.path.join(settings.UPLOAD_ROOT, 'jplag', 'Task_' + str(self.id))

    def jplag_index_url(self) -> str:
        return os.path.join('jplag', 'Task_' + str(self.id), "index.html")

    def jplag_log_url(self) -> str:
        return os.path.join('jplag', 'Task_' + str(self.id), "jplag.txt")

    def did_jplag_run(self) -> bool:
        return os.path.isdir(self.jplag_dir_path())

    def did_jplag_succeed(self) -> bool:
        return os.path.exists(os.path.join(self.jplag_dir_path(), 'index.html'))

    def need_to_re_run_jplag(self) -> None:
        if self.jplag_up_to_date:
            self.jplag_up_to_date = False
            self.save()

    def media_files(self) -> "models.QuerySet[MediaFile, MediaFile]":
        return MediaFile.objects.filter(task=self)

    def should_hide_media(self, user: User) -> bool:
        started = self.publication_date < datetime.now()
        return (self.exam and (not started or self.expired_for_user(user))) or (not self.exam and exam_is_active(user))

    def should_hide(self, user: User) -> bool:
        from attestation.models import Attestation
        exam_active = exam_is_active(user)
        attestations = Attestation.objects.filter(final = True, published = True, solution__task = self, solution__final = True, solution__author = user)
        return (exam_active and (not self.exam or self.expired_for_user(user))) or (not exam_active and self.exam and not attestations.exists())

    @staticmethod
    def jplag_languages() -> dict[str, dict[str, str]]:
        return { 'Java':     { 'param': 'java19', 'files': '.java,.JAVA' },
                 'R':        { 'param': 'text',   'files': '.R' },
                 'Python':   { 'param': 'text',   'files': '.py' },
                 'Isabelle': { 'param': 'text',   'files': '.thy' },
               }

    def run_jplag(self, lang: str) -> None:
        # sanity check
        if not hasattr(settings, 'JPLAGJAR'):
            raise RuntimeError("Setting JPLAGJAR not set")
        if not os.path.exists(settings.JPLAGJAR):
            raise RuntimeError("Setting JPLAGJAR points to non-existing file %s" % settings.JPLAGJAR)
        if not lang in self.jplag_languages():
            raise RuntimeError("Unknown jplag settings %s" % lang)

        # Remember jplag setting
        configuration = get_settings()
        configuration.jplag_setting = lang
        configuration.save()

        jplag_settings = self.jplag_languages()[lang]
        path = self.jplag_dir_path()
        tmp = os.path.join(path, "tmp")
        # clean out previous run
        if self.did_jplag_run():
            shutil.rmtree(path)
        # create output directory
        os.makedirs(path)

        # extract all final solutions
        os.mkdir(tmp)
        final_solutions = self.solution_set.filter(final=True)
        from solutions.models import path_for_user
        for solution in final_solutions:
            subpath = os.path.join(tmp, path_for_user(solution.author))
            os.mkdir(subpath)
            solution.copySolutionFiles(subpath)

        # run jplag
        args = [settings.JVM,
                "-jar", settings.JPLAGJAR,
                "-s",
                "-l", jplag_settings['param'],
                "-p", jplag_settings['files'],
                "-r", path,
                tmp]
        environ: dict[str, str] = {}
        environ['LANG'] = settings.LANG
        environ['LANGUAGE'] = settings.LANGUAGE
        output = execute_arglist(args, path, environment_variables=environ, unsafe=True).output

        # remove solution copies
        shutil.rmtree(tmp)

        # write log file
        with open(os.path.join(path, "jplag.txt"), 'w') as fd:
            fd.write(output)

        # mark jplag as up-to-date
        self.jplag_up_to_date = True
        self.save()


    @classmethod
    def export_Tasks(
        cls, queryset: "models.QuerySet[Task, Task]"
    ) -> "tempfile.SpooledTemporaryFile[bytes]":
        """ Serializes a task queryset and related checkers to xml and bundles it with all files into a zipfile  """
        from solutions.models import Solution, SolutionFile
        from attestation.models import RatingScaleItem

        # fetch tasks, media objects, checker and serialize
        task_objects = list(queryset)
        # prevent duplication of exported RatingScale objects
        rating_scale_objects = list( {t.final_grade_rating_scale for t in task_objects if t.final_grade_rating_scale} )
        rating_scale_item_objects = list( RatingScaleItem.objects.filter(scale__in=rating_scale_objects) )
        media_objects = list( MediaFile.objects.filter(task__in=task_objects) )
        model_solution_objects = list( Solution.objects.filter(model_solution_task__in=task_objects) )
        model_solution_file_objects = list( SolutionFile.objects.filter(solution__in=model_solution_objects) )

        from checker.basemodels import Checker
        checker_app = apps.get_app_config('checker')
        checker_classes = [x for x in checker_app.get_models() if issubclass(x, Checker)]
        checker_objects = [
            checker for checker_class in checker_classes
            for checker in checker_class.objects.filter(task__in=task_objects)
        ]
        # serialize RatingScale objects first since they are used by tasks
        data = serializers.serialize("xml", rating_scale_objects + rating_scale_item_objects + task_objects + media_objects + checker_objects + model_solution_objects + model_solution_file_objects)

        # fetch files
        files: list[FieldFile] = []
        for checker_object in checker_objects:
            file_fields = [x for x in checker_object.__class__._meta.fields if isinstance(x, models.FileField)]
            files.extend(getattr(checker_object, file_field.attname) for file_field in file_fields)
        for media_object in media_objects:
            files.append(media_object.media_file)
        for model_solution_file_object in model_solution_file_objects:
            files.append(model_solution_file_object.file)

        # zip it up
        with ExitStack() as failed_export:
            zip_file = tempfile.SpooledTemporaryFile()
            failed_export.callback(zip_file.close)
            with zipfile.ZipFile(zip_file, 'w') as zip:
                zip.writestr('data.xml', data)
                for file in files:
                    zip.write(file.path, require_file_name(file))
            zip_file.seek(0)
            failed_export.pop_all()
            return zip_file

    @classmethod
    @transaction.atomic
    def import_Tasks(
        cls,
        zip_file: "str | os.PathLike[str] | _typing.BinaryIO | File[bytes]",
        solution_author: User,
        is_template: bool = True,
    ) -> None:
        with zipfile.ZipFile(zip_file, 'r') as zip:
            cls._import_tasks(zip, solution_author, is_template)

    @classmethod
    def _import_tasks(
        cls, zip: zipfile.ZipFile, solution_author: User, is_template: bool
    ) -> None:
        from solutions.models import Solution, SolutionFile
        from attestation.models import RatingScale, RatingScaleItem
        from checker.basemodels import Checker

        data = zip.read('data.xml').decode('utf-8')

        task_id_map: dict[int, int] = {}
        scale_map: dict[int, RatingScale] = {}
        solution_id_map: dict[int, int] = {}
        old_solution_to_new_task_map: dict[int | None, int] = {}
        solution_list: list[Solution] = []
        for deserialized_object in serializers.deserialize("xml", data):
            object = deserialized_object.object
            if not isinstance(
                object,
                (Task, RatingScale, RatingScaleItem, Solution, SolutionFile,
                 MediaFile, HtmlInjector, Checker),
            ):
                raise ValidationError(
                    "Invalid model class in task import: %s" % object._meta.label
                )
            old_id = int(object.pk)
            #since Django Debug Toolbar didn't catch logger output, I print to console while in debugging mode
            #import logging
            #logger = logging.getLogger(__name__)
            #logger.error("Test!")
            #print("======================================")
            #print('OldID: %s -- Type: %s '%(str(old_id) , str(type(object))))
            #print("======================================")

            # from Django docs: "if the pk attribute in the serialized data doesn’t exist or is null, a new instance will be saved to the database."
            # we want to save a task always as new database entry, therefor we set the object.id to None.
            # but we do not want to save RatingScale or RatingScaleItem, if equivalent elements are in database already.
            object.pk = None
            if isinstance(object, Task):
            # save all tasks and their old id
                if is_template:
                    object.publication_date = date.max
                deserialized_object.save()
                task_id_map[old_id] = object.id
                #print("======================================")
                #print('OldID: %s -- NewID: %s -- Name: %s '%(str(old_id) , str(task_id_map[old_id]) , str(object.title)))
                #print("======================================")
                old_solution_to_new_task_map[object.model_solution_id] = object.id
                object.model_solution = None
                object.final_grade_rating_scale = (
                    None if is_template or object.final_grade_rating_scale_id is None
                    else scale_map.get(object.final_grade_rating_scale_id)
                )
                deserialized_object.save()

            elif isinstance(object, RatingScale):
                if not is_template:
                    dbobject=RatingScale.objects.filter(name=object.name).order_by('id').first()
                    #if there is no RatingScale with the name in database, we save the deserialized_object, else we are reusing existent data.
                    if dbobject is None:
                        deserialized_object.save()
                        scale_map[old_id] = object
                        #print("======================================")
                        #print('>> OldID: %s -- NewID: %s -- Name: %s '%(str(old_id) , str(scale_map[old_id].id) , str(object)))
                        #print("======================================")
                    else:
                        scale_map[old_id] = dbobject
                        #print("======================================")
                        #print('>> OldID: %s -- ReusingID: %s -- Name: %s '%(str(old_id) , str(scale_map[old_id].id) , str(object)))
                        #print("======================================")
                    #print (scale_map)
                    #print("===============")

            elif isinstance(object, RatingScaleItem):
                if not is_template:
                    #if there is no RatingScaleItem with the same name for corresponding RatingScale in database,
                    #we save the deserialized_object, else we are reusing existent data.
                    #The consequence is: If you where importing tasks from different praktomat instances having differences in names of RatingScaleItems
                    #but using same name for RatingScale, than these ScaleItems become merge into the same RatingScale.
                    dbobject=RatingScaleItem.objects.filter(name=object.name, scale=scale_map[object.scale_id].id ).order_by('id').first()
                    if dbobject is None:
                        object.scale = scale_map[object.scale_id]
                        deserialized_object.save()
                        #print("======================================")
                        #print('>> OldID: %s -- NewID: %s -- Name: %s '%(str(old_id) , str(object.id) , str(object)))
                        #print("======================================")
                    #else:
                        #print("======================================")
                        #print('>> OldID: %s -- ReusingID: %s -- Name: %s '%(str(old_id) , str(dbobject.id) , str(dbobject)))
                        #print("======================================")

            else:
                # save modelsolution, media and checker, update task id
                if isinstance(object, SolutionFile):
                    object.solution_id = solution_id_map[object.solution_id]
                else:
                    object.task_id = task_id_map[object.task_id]

                from django.core.files import File
                for file_field in [x for x in object.__class__._meta.fields if isinstance(x, models.FileField)]:
                    file_field_instance = getattr(object, file_field.attname)
                    if not isinstance(file_field_instance, FieldFile):
                        raise TypeError(f"Expected a stored file for {file_field.attname}")
                    name = require_file_name(file_field_instance)
                    with tempfile.NamedTemporaryFile() as temp_file:
                        temp_file.write(zip.read(name))
                        temp_file.seek(0)
                        file_field_instance.save(name, File(temp_file))

                deserialized_object.save()

                if isinstance(object, Solution):
                    task = Task.objects.get(id=old_solution_to_new_task_map[old_id])
                    task.model_solution = object
                    task.save()
                    assert object.id is not None
                    solution_id_map[old_id] = object.id
                    solution_list.append(object)
                    object.author = solution_author
                    object.save()

        for solution in solution_list:
            solution.check_solution(run_secret=True)

def get_mediafile_storage_path(instance: "MediaFile", filename: str) -> str:
    return 'TaskMediaFiles/Task_%s/%s' % (instance.task.pk, filename)

def get_htmlinjectorfile_storage_path(instance: "HtmlInjector", filename: str) -> str:
    return 'TaskHtmlInjectorFiles/Task_%s/%s' % (instance.task.pk, filename)

def exam_is_active(user: User) -> bool:
    for task in Task.objects.all():
        # Extend the "runtime" of a task in each direction for
        # this calculation. This ensures that students can't access earlier
        # solutions right before an exam/test starts.
        publication_date = task.publication_date - timedelta(minutes=60)
        submission_date = task.submission_date_for_user(user) + get_settings().deadline_tolerance + timedelta(minutes=15)
        now = datetime.now()
        is_active = publication_date < now and submission_date > now
        if is_active and task.exam:
            return True
    return False


class MediaFile(models.Model):

    if _typing.TYPE_CHECKING:
        id: models.AutoField[int | None, int]

    task: "models.ForeignKey[Task, Task]" = models.ForeignKey(Task, on_delete=models.CASCADE)
    task_id: int
    media_file: DeletingFileField = DeletingFileField(upload_to=get_mediafile_storage_path, max_length=500)
    description: "models.CharField[str, str]" = models.CharField(null=False, blank=True, max_length=255, default="", help_text = gettext_lazy("A short description of this file"))

    def basename(self) -> str:
        name = require_file_name(self.media_file)
        i = name.rfind("/") + 1
        return name[i:]


class HtmlInjector(models.Model):
    if _typing.TYPE_CHECKING:
        id: models.AutoField[int | None, int]

    task: "models.ForeignKey[Task, Task]" = models.ForeignKey(Task, on_delete=models.CASCADE)
    task_id: int
    inject_in_solution_view: "models.BooleanField[bool, bool]" = models.BooleanField(
        default=False,
        help_text = gettext_lazy("Indicates whether HTML code shall be injected in public  solution views, e.g.: in https://praktomat.cs.kit.edu/2016_WS_Abschluss/solutions/5710/")
    )
    inject_in_solution_full_view: "models.BooleanField[bool, bool]" = models.BooleanField(
        default=False,
        help_text = gettext_lazy("Indicates whether HTML code shall be injected in private solution views, e.g.: in https://praktomat.cs.kit.edu/2016_WS_Abschluss/solutions/5710/full")
    )
    inject_in_attestation_edit: "models.BooleanField[bool, bool]" = models.BooleanField(
        default=True,
        help_text = gettext_lazy("Indicates whether HTML code shall be injected in attestation edits, e.g.: in https://praktomat.cs.kit.edu/2016_WS_Abschluss/attestation/134/edit")
    )
    inject_in_attestation_view: "models.BooleanField[bool, bool]" = models.BooleanField(
        default=False,
        help_text = gettext_lazy("Indicates whether HTML code shall be injected in attestation views, e.g.: in https://praktomat.cs.kit.edu/2016_WS_Abschluss/attestation/134")
    )
    html_file: DeletingFileField = DeletingFileField(upload_to=get_htmlinjectorfile_storage_path, max_length=500)


class SubmissionBlacklistEntry(models.Model):
    if _typing.TYPE_CHECKING:
        id: models.AutoField[int | None, int]

    task: "models.ForeignKey[Task, Task]" = models.ForeignKey(Task, on_delete=models.CASCADE)
    task_id: int
    user: "models.ForeignKey[User, User]" = models.ForeignKey(User, on_delete=models.CASCADE, limit_choices_to={"groups__name": "User"})
    user_id: int


class DeadlineExtension(models.Model):
    if _typing.TYPE_CHECKING:
        id: models.AutoField[int | None, int]

    task: "models.ForeignKey[Task, Task]" = models.ForeignKey(Task, on_delete=models.CASCADE)
    task_id: int
    user: "models.ForeignKey[User, User]" = models.ForeignKey(User, on_delete=models.CASCADE, limit_choices_to={"groups__name": "User"})
    user_id: int
    timestamp: "models.DateTimeField[datetime, datetime]" = models.DateTimeField(help_text = gettext_lazy("The time up until the user has time to complete the task. This time will be extended by the duration configured with the deadline tolerance setting in case the student just missed the extended deadline."))
