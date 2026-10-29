from collections.abc import Iterable
from typing import TYPE_CHECKING
from django.db import models, transaction
from django.conf import settings
from django.http import HttpRequest
from django.core.files.uploadedfile import UploadedFile
from tasks.models import Task
from solutions.models import Solution, SolutionFile
from django.utils.translation import gettext_lazy
from django.core.mail import EmailMessage
from django.core import serializers
from django.core.serializers.base import DeserializedObject
from django.template import loader
from django.contrib.sites.requests import RequestSite
from django.contrib import messages
from datetime import datetime
from utilities.nub import nub
import difflib

from accounts.models import User
from configuration import get_settings

if TYPE_CHECKING:
    from django.db.models.fields.related_descriptors import ReverseManyToOneDescriptor


class Attestation(models.Model):
    """An attestation for a student's solution."""

    if TYPE_CHECKING:
        id: models.AutoField[int | None, int]
        annotatedsolutionfile_set: ReverseManyToOneDescriptor["AnnotatedSolutionFile"]
        ratingresult_set: ReverseManyToOneDescriptor["RatingResult"]

    created: "models.DateTimeField[datetime, datetime]" = models.DateTimeField(auto_now_add=True)
    solution: "models.ForeignKey[Solution, Solution]" = models.ForeignKey(Solution, on_delete=models.CASCADE)
    solution_id: int
    author: "models.ForeignKey[User, User]" = models.ForeignKey(User, verbose_name="attestation author", limit_choices_to = {'groups__name': 'Tutor'}, on_delete=models.CASCADE)
    author_id: int

    public_comment: "models.TextField[str, str]" = models.TextField(blank=True, help_text = gettext_lazy('Comment which is shown to the user.'))
    private_comment: "models.TextField[str, str]" = models.TextField(blank=True, help_text = gettext_lazy('Comment which is only visible to tutors'))
    final_grade: "models.ForeignKey[RatingScaleItem | None, RatingScaleItem | None]" = models.ForeignKey('RatingScaleItem', null=True, help_text = gettext_lazy('The mark for the whole solution.'), on_delete=models.SET_NULL)
    final_grade_id: int | None

    final: "models.BooleanField[bool, bool]" = models.BooleanField(default = False, help_text = gettext_lazy('Indicates whether the attestation is ready to be published'))
    published: "models.BooleanField[bool, bool]" = models.BooleanField(default = False, help_text = gettext_lazy('Indicates whether the user can see the attestation.'))
    published_on: "models.DateTimeField[datetime | None, datetime | None]" = models.DateTimeField(blank=True, null=True, help_text = gettext_lazy('The Date/Time the attestation was published.'))

    def publish(self, request: HttpRequest, by: User) -> None:
        """ Publish attestation and send email to user """
        self.published = True
        self.published_on = datetime.now()
        self.save()

        email = self.solution.author.email
        if not email:
            return

        # Send confirmation email
        t = loader.get_template('attestation/attestation_email.html')
        c = {
            'attest': self,
            'protocol': request.is_secure() and "https" or "http",
            'domain': RequestSite(request).domain,
            'site_name': settings.SITE_NAME,
            'by': by,
            'invisible_attestor': get_settings().invisible_attestor,
        }
        subject = gettext_lazy("New attestation for your solution of the task '%s'") % self.solution.task
        body = t.render(c)
        reply_to = ([self.author.email] if self.author.email and (not get_settings().invisible_attestor) else []) \
                 + ([get_settings().attestation_reply_to]  if get_settings().attestation_reply_to else [])
        headers = {'Reply-To': ', '.join(reply_to)} if reply_to else None
        email = EmailMessage(subject, body, None, (email,), headers = headers)
        email.send()

    def withdraw(self, request: HttpRequest, by: User) -> None:
        self.published = False
        self.final = False
        self.published_on = datetime.now()
        self.save()

        recps = nub([
            self.solution.author, # student
            self.author,          # attestation writer
            by,                   # usually attestation writer, may be trainer
            ] + list(User.objects.filter(groups__name="Trainer"))  # and, for withdrawals, all trainers
            )
        emails = [u.email for u in recps if u.email]

        if not emails:
            return

        # Send confirmation email
        t = loader.get_template('attestation/attestation_withdraw_email.html')
        c = {
            'attest': self,
            'protocol': request.is_secure() and "https" or "http",
            'domain': RequestSite(request).domain,
            'site_name': settings.SITE_NAME,
            'by': by,
        }
        subject = gettext_lazy("Attestation for your solution of the task '%s' withdrawn") % self.solution.task
        body = t.render(c)
        recipients = emails[0:1]
        bcc_recipients = emails[1:]
        email = EmailMessage(subject, body, None, recipients, bcc=bcc_recipients)
        email.send()

    @classmethod
    def export_Attestation(cls, qureyset: Iterable["Attestation"]) -> str:
        """ Serializes an Attestation queryset to xml """
        # fetch tasks, media objects, checker and serialize
        attestation_objects = list(qureyset)
        solution_objects = list([attestation.solution for attestation in attestation_objects])
        annotatedsolutionfiles_objects = list(AnnotatedSolutionFile.objects.filter(attestation__in = attestation_objects).defer('content'))
        for annotatedsolutionfile in annotatedsolutionfiles_objects:
            annotatedsolutionfile.content = ""
            annotatedsolutionfile._meta.model_name = "annotatedsolutionfile" # *sigh*
        solutionfile_objects = list([annotatedsolutionfile.solution_file for annotatedsolutionfile in annotatedsolutionfiles_objects])

        ratingresult_objects  = list(RatingResult.objects.filter(attestation__in = attestation_objects))
        aspect_grades_objects = {ratingresult.mark for ratingresult in ratingresult_objects}
        final_grades_objects  = {attestation.final_grade for attestation in attestation_objects}
        rating_objects        = {ratingresult.rating for ratingresult in ratingresult_objects}
        aspect_objects        = {rating.aspect for rating in rating_objects}
        ratingscale_objects = list(
              set(RatingScale.objects.filter(ratingscaleitem__in = final_grades_objects | aspect_grades_objects))
        )
        ratingscaleitems_objects = list(RatingScaleItem.objects.filter(scale__in = ratingscale_objects))

        data = serializers.serialize("xml", attestation_objects + solution_objects + ratingscale_objects + ratingscaleitems_objects + ratingresult_objects + list(rating_objects) + list(aspect_objects) + annotatedsolutionfiles_objects + solutionfile_objects)

        return data

    @classmethod
    @transaction.atomic
    def update_Attestations(
        cls, request: HttpRequest, xml_file: "UploadedFile[bytes]"
    ) -> None:
        from solutions.models import Solution, SolutionFile
        deserialized = list(serializers.deserialize("xml", xml_file))

        tosave_attestation: list[DeserializedObject] = []
        tosave_ratingresult: list[DeserializedObject] = []


        for deserialized_object in deserialized:
            new_object = deserialized_object.object

            if isinstance(new_object, Attestation):
                old_object = Attestation.objects.get(id = new_object.id)

                if not(attributes_equal(new_object, old_object, ["solution"])):
                    messages.error(request, "1Invalid change from " + str(old_object) + " to " + str(new_object) + ". Nothing was imported.")
                    return
                tosave_attestation.append(deserialized_object)

            elif isinstance(new_object, RatingResult):
                old_object = RatingResult.objects.get(id = new_object.id)
                if not(attributes_equal(new_object, old_object, ["attestation", "rating"])):
                    messages.error(request, "2Invalid change from " + str(old_object) + " to " + str(new_object) + ". Nothing was imported.")
                    return
                tosave_ratingresult.append(deserialized_object)

            elif isinstance(new_object, AnnotatedSolutionFile):
                old_object = AnnotatedSolutionFile.objects.get(id = new_object.id)
                if not(attributes_equal(new_object, old_object, ["attestation", "solutionfile"])):
                    messages.error(request, "4Invalid change from " + str(old_object) + " to " + str(new_object) + ". Nothing was imported.")
                    return

            elif ( isinstance(new_object, Solution)
                   or isinstance(new_object, Rating)
                   or isinstance(new_object, RatingAspect)
                   or isinstance(new_object, RatingScale)
                   or isinstance(new_object, SolutionFile)
                   or isinstance(new_object, RatingScaleItem)):
                old_object = new_object.__class__.objects.get(id = new_object.id)
                if not(model_fields_equal(new_object, old_object)):
                    messages.error(request, "3Invalid change from " + str(old_object) + " to " + str(new_object) + ". Nothing was imported.")
                    return
            else:
                messages.error(request, "Invalid model class for: " + str(new_object) + ". Nothing was imported.")
                return

        for object in (tosave_attestation + tosave_ratingresult):
            object.save()

        messages.success(request, "Updated %d attestations, and %d rating results." % (len(tosave_attestation), len(tosave_ratingresult)))

        return



class AnnotatedSolutionFile(models.Model):
    """"""
    if TYPE_CHECKING:
        id: models.AutoField[int | None, int]

    attestation: "models.ForeignKey[Attestation, Attestation]" = models.ForeignKey(Attestation, on_delete=models.CASCADE)
    attestation_id: int
    solution_file: "models.ForeignKey[SolutionFile, SolutionFile]" = models.ForeignKey(SolutionFile, on_delete=models.CASCADE)
    solution_file_id: int
    content: "models.TextField[str, str]" = models.TextField(help_text = gettext_lazy('The content of the solution file annotated by the tutor.'), blank = True)

    def has_anotations(self) -> bool:
        original = self.solution_file.content().replace("\r\n", "\n").replace("\r", "\n")
        anotated = self.content.replace("\r\n", "\n").replace("\r", "\n")
        return not original == anotated

    def content_diff(self) -> str:
        def strip_blank_border_lines(lines: list[str]) -> list[str]:
            start = 0
            end = len(lines)
            while start < end and lines[start].strip() == "":
                start += 1
            while end > start and lines[end - 1].strip() == "":
                end -= 1
            return lines[start:end]

        d = difflib.Differ()
        original = strip_blank_border_lines(self.solution_file.content().replace("\r\n", "\n").replace("\r", "\n").splitlines())
        anotated = strip_blank_border_lines(self.content.replace("\r\n", "\n").replace("\r", "\n").splitlines())
        result = list(d.compare(original, anotated))
        return "\n".join([l.strip("\n") for l in result])

    def __str__(self) -> str:
        return self.solution_file.__str__()

class RatingAspect(models.Model):
    """ describes a review aspect which the reviewer has to evaluate """
    if TYPE_CHECKING:
        id: models.AutoField[int | None, int]
        rating_set: ReverseManyToOneDescriptor["Rating"]

    name: "models.CharField[str, str]" = models.CharField(max_length=100, help_text = gettext_lazy('The Name of the Aspect to be rated. E.g.: "Readability"'))
    description: "models.TextField[str, str]" = models.TextField(help_text = gettext_lazy('Description of the Aspect and how it should be rated. E.w.: "How well is the code structured?"'))

    def __str__(self) -> str:
        return self.name

class RatingScale(models.Model):
    """ describes a scale upon which the reviewer rates the aspect """
    if TYPE_CHECKING:
        id: models.AutoField[int | None, int]
        ratingscaleitem_set: ReverseManyToOneDescriptor["RatingScaleItem"]
        rating_set: ReverseManyToOneDescriptor["Rating"]
        task_set: ReverseManyToOneDescriptor[Task]

    name: "models.CharField[str, str]" = models.CharField(max_length=100, help_text = gettext_lazy('The Name of the rating scale for the aspects. E.g.: "School marks"'))

    def __str__(self) -> str:
        return self.name

class RatingScaleItem(models.Model):
    """ lists all items(marks) of an rating scale"""
    if TYPE_CHECKING:
        id: models.AutoField[int | None, int]
        attestation_set: ReverseManyToOneDescriptor[Attestation]
        ratingresult_set: ReverseManyToOneDescriptor["RatingResult"]

    scale: "models.ForeignKey[RatingScale, RatingScale]" = models.ForeignKey(RatingScale, on_delete=models.CASCADE)
    scale_id: int
    name: "models.CharField[str, str]" = models.CharField(max_length=100, help_text = gettext_lazy('The Name of the item(mark) in the rating scale. E.g.: "A" or "very good" '))
    position: "models.PositiveSmallIntegerField[int, int]" = models.PositiveSmallIntegerField(help_text = gettext_lazy('Defines the order in which the items are sorted. Lowest is best.'))

    class Meta:
        ordering: list[str] = ['position']

    def __str__(self) -> str:
        return self.name

class Rating(models.Model):
    """ intermediate model to assign a rating aspect and a rating scale to a task """
    if TYPE_CHECKING:
        id: models.AutoField[int | None, int]
        ratingresult_set: ReverseManyToOneDescriptor["RatingResult"]

    task: "models.ForeignKey[Task, Task]" = models.ForeignKey(Task, on_delete=models.CASCADE)
    task_id: int
    aspect: "models.ForeignKey[RatingAspect, RatingAspect]" = models.ForeignKey(RatingAspect, on_delete=models.CASCADE)
    aspect_id: int
    scale: "models.ForeignKey[RatingScale, RatingScale]" = models.ForeignKey(RatingScale, on_delete=models.CASCADE)
    scale_id: int

    def __str__(self) -> str:
        return "%s - %s - %s" % (self.task.title, self.aspect.name, self.scale.name)

class RatingResult(models.Model):
    """ the rating of particular aspect of a specific solution """
    if TYPE_CHECKING:
        id: models.AutoField[int | None, int]

    attestation: "models.ForeignKey[Attestation, Attestation]" = models.ForeignKey(Attestation, on_delete=models.CASCADE)
    attestation_id: int
    rating: "models.ForeignKey[Rating, Rating]" = models.ForeignKey(Rating, on_delete=models.CASCADE)
    rating_id: int
    mark: "models.ForeignKey[RatingScaleItem | None, RatingScaleItem | None]" = models.ForeignKey(RatingScaleItem, null=True, on_delete=models.SET_NULL) # allow for db-null so that rating results can be created programaticly without mark (blank = False !)
    mark_id: int | None

    def __str__(self) -> str:
        return str(self.rating.aspect)

class Script(models.Model):
    """ save java script function of the rating overview page """
    script: "models.TextField[str, str]" = models.TextField(blank=True, help_text = gettext_lazy("This JavaScript will calculate a recommend end note for every user based on final grade of every task."), default="""var sum = 0.0;\nfor (x = 0; x != grades.length; ++x) {\n    grade = parseFloat(grades[x]);\n    if (!isNaN(grade)) {\n        sum += grade;\n    }\n}\nresult=sum;""")




def attributes_equal(
    this: models.Model, that: models.Model, attrs: Iterable[str]
) -> bool:
    _NOTFOUND = object()
    for attr in attrs:
        v1, v2 = [getattr(obj, attr, _NOTFOUND) for obj in [this, that]]
        if (v1 is _NOTFOUND) != (v2 is _NOTFOUND):
            return False
        elif v1 != v2:
            return False
    return True

def model_fields_equal(this: models.Model, that: models.Model) -> bool:
    this_fields = [field.name for field in this._meta.fields]
    that_fields = [field.name for field in that._meta.fields]
    return this_fields == that_fields and attributes_equal(this, that, this_fields)
