import datetime
import re
import hashlib
import random
from typing import IO, TYPE_CHECKING, Any, Literal

from functools import reduce

from django.utils.translation import gettext_lazy
from django.conf import settings
from django.db import models, utils
from django.contrib.auth.models import User as BasicUser, UserManager
from django.contrib.admin import display
from django.db.models import signals
from django.core.validators import RegexValidator
from django.core.exceptions import ValidationError
from django.core.files import File
from django.core import serializers
from django.db.transaction import atomic

from configuration import get_settings

if TYPE_CHECKING:
    from attestation.models import Attestation
    from solutions.models import Solution
    from django.db.models.fields.related_descriptors import (
        ManyToManyDescriptor,
        ReverseManyToOneDescriptor,
    )


def validate_mat_number(value: int | None) -> None:
    if settings.DUMMY_MAT_NUMBERS:
        # If we're using dummy mat numbers, we don't care if they are valid
        return

    regex = get_settings().mat_number_validation_regex
    if regex:
        RegexValidator("^"+regex+"$", message="This is not a valid student number.", code="")(value)

class User(BasicUser):
    id: int

    if TYPE_CHECKING:
        user_ptr: models.OneToOneField[BasicUser, BasicUser]
        tutored_tutorials: ManyToManyDescriptor["Tutorial", models.Model]
        solution_set: ReverseManyToOneDescriptor[Solution]
        attestation_set: ReverseManyToOneDescriptor[Attestation]

    # all fields need to be null-able in order to create user
    tutorial: "models.ForeignKey[Tutorial | None, Tutorial | None]" = models.ForeignKey('Tutorial', on_delete=models.SET_NULL, null=True, blank=True, help_text = gettext_lazy("The tutorial the student belongs to."))
    tutorial_id: int | None
    mat_number: "models.IntegerField[int | None, int | None]" = models.IntegerField( null=True, blank=True, validators=[validate_mat_number]) # special blank and unique validation in forms
    final_grade: "models.CharField[str | None, str | None]" = models.CharField( null=True, blank=True, max_length=100,  help_text = gettext_lazy('The final grade for the whole class.'))
    programme: "models.CharField[str | None, str | None]" = models.CharField(null=True, blank=True, max_length=100, help_text = gettext_lazy('The programme the student is enlisted in.'))
    activation_key: "models.CharField[str, str]" = models.CharField(gettext_lazy('activation key'), max_length=40, editable=False)
    user_text: "models.CharField[str | None, str | None]" = models.CharField(null=True, blank=True, max_length=500, help_text = gettext_lazy("Custom text which will be shown to this student."))
    accepted_disclaimer: "models.BooleanField[bool, bool]" = models.BooleanField(default=False, help_text="Whether the user accepted the disclaimer.")

    # Use UserManager to get the create_user method, etc.
    objects = UserManager["User"]()

    # Inheriting runtime Meta options would change this model's migration state.
    class Meta(BasicUser.Meta if TYPE_CHECKING else object):
        ordering: list[str] = ['first_name', 'last_name']

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super(User, self).__init__(*args, **kwargs)
        self._cached_groups = None

    def __str__(self) -> str:
        return self.get_full_name() or self.username

    def set_new_activation_key(self) -> None:
        # The activation key will be a SHA1 hash, generated from a combination of the username and a random salt.
        sha = hashlib.sha1()
        to_hash = str(random.random()) + self.username
        sha.update(to_hash.encode('utf-8'))
        self.activation_key = sha.hexdigest()
        self.save()

    @display(boolean=True)
    def activation_key_expired(self) -> bool:
        """
        Determine whether the activation key has expired, returning a boolean -- ``True`` if the key has expired.

        The date the user signed up is incremented by the number of days specified in the setting ''get_settings().acount_activation_days`` (which should be the number of days after signup during which a user is allowed to activate their account); if the result is less than or equal to the current date, the key has expired and this method returns ``True``.
        """
        expiration_date = datetime.timedelta(days=get_settings().acount_activation_days)
        return     (self.date_joined + expiration_date <= datetime.datetime.now())

    @display(boolean=True)
    def is_activated(self) -> bool:
        """
        Determine whether the user is already activated, returning a boolean -- ``True`` if he is.

        If the user has already activated, the activation key will have been reset to the string ``ALREADY_ACTIVATED``
        """
        return self.activation_key == "ALREADY_ACTIVATED"

    @display(boolean=True)
    def can_activate(self) -> bool:
        """
        Determine whether the user can activate his account, returning a boolean.

        This is determined by a three-step process:

        1.     If the user has already activated, re-activating is not permitted, and so this method returns ``False`` in this case.

        2.     If the activation key has expired this method returns ``False``.

        3.     If an other user already activated an account with the same matnumber this method returns ``False``.
        """
        dublicate_matnumber = User.objects.filter(mat_number=self.mat_number, is_active=True).count() >= 1
        return not self.is_activated() and not self.activation_key_expired() and not dublicate_matnumber

    @staticmethod
    def activate_user(activation_key: str) -> "User | Literal[False] | None":
        """
        Validate an activation key and activate the corresponding ''User`` if valid.

        If the key is valid and has not expired, return the ``User`` after activating.

        If the key is not valid or has expired, return ``False``.

        If the key is valid but the ``User`` is already active, return ``False``.

        To prevent reactivation of an account which has been deactivated by site administrators, the activation key is reset to the string ``ALREADY_ACTIVATED`` after successful activation.

        """
        # Make sure the key we're trying conforms to the pattern of a
        # SHA1 hash; if it doesn't, no point trying to look it up in
        # the database.
        SHA1_RE = re.compile('^[a-f0-9]{40}$')
        if SHA1_RE.search(activation_key):
            try:
                user = User.objects.get(activation_key=activation_key)
            except User.DoesNotExist:
                return False
            if user.can_activate():
                user.is_active = True
                user.activation_key = "ALREADY_ACTIVATED"
                user.save()
                return user
            return False

    def is_shibboleth_user(self) -> bool:
        return not self.has_usable_password() and not self.is_ldap_user()
	
    def is_ldap_user(self) -> bool:
        return self.password == 'LDAP_AUTH'

    # Cache group membership for users
    def cached_groups(self) -> set[str]:
        if self._cached_groups is None:
            self._cached_groups = set(x['name'] for x in self.groups.values('name'))
        return self._cached_groups

    @property
    def is_user(self) -> bool:
        return 'User' in self.cached_groups()
    @property
    def is_tutor(self) -> bool:
        return 'Tutor' in self.cached_groups()
    @property
    def is_trainer(self) -> bool:
        return 'Trainer' in self.cached_groups()
    @property
    def is_coordinator(self) -> bool:
        return 'Coordinator' in self.cached_groups()

    @classmethod
    def export_user(cls, queryset: "models.QuerySet[User, User]") -> str:
        """ Serializes a user queryset and related objects to xml """
        users = list(queryset)
        django_users = list(BasicUser.objects.filter(user__in = queryset))
        return serializers.serialize("xml", django_users + users) # order does matter!

    @classmethod
    @atomic
    def import_user(
        cls, xml_data: "str | File[bytes] | IO[str] | IO[bytes]"
    ) -> "models.QuerySet[User, User]":
        basicUser_id_map: dict[int, BasicUser] = {}
        imported_user_ids: list[int] = []
        for deserialized_object in serializers.deserialize("xml", xml_data):
            object = deserialized_object.object
            if isinstance(object, User):
                try:
                    object.tutorial = None
                    object.final_grade = None
                    object.user_ptr = basicUser_id_map[int(object.pk)]    # object.id is null! so parse id.
                    deserialized_object.save()
                    imported_user_ids.append(int(object.pk))
                except KeyError:
                    pass # basicUser_id_map key not found because user already existed
            elif isinstance(object, BasicUser):
                try:
                    old_id = int(object.pk)
                    object.pk = None
                    object.date_joined = datetime.datetime.now()
                    deserialized_object.save()
                    basicUser_id_map[old_id] = object
                except utils.IntegrityError:
                    pass # unique username validation - user already existed
            else:
                raise ValidationError(
                    "Invalid model class in user import: %s" % object._meta.label
                )
        return User.objects.filter(id__in = imported_user_ids)     # get them fresh from the db, otherwise the user object won't have basicUser attributes set

    def clean(self) -> None:
        super(User, self).clean()
        if settings.DUMMY_MAT_NUMBERS:			
            self.mat_number = self.id			

    def tutored_users(self) -> "models.QuerySet[User, User] | None":
        tutored_users = None
        if self.is_trainer or self.is_superuser:
            tutored_users = User.objects.filter(groups__name="User", is_active=True).order_by('last_name')
        elif self.is_tutor and get_settings().tutors_can_edit_solutions:
            tutorials = Tutorial.objects.filter(tutors__id=self.id)
            tutored_users = User.objects.none()
            for tutorial in tutorials:
                tutored_users |= User.objects.filter(groups__name="User", is_active=True, tutorial=tutorial)
            tutored_users = tutored_users.order_by('last_name')
        return tutored_users

#    def save(self, force_insert=False, force_update=False, *args, **kwargs):
#        """ prevent redundancy: staff iff. superuser or trainer """
#        # the instance needs to have a primary key value before a many-to-many relationship groups can be used so save it twice
#        super(User, self).save(force_insert=force_insert, force_update=force_update, *args, **kwargs)
#        # Bug: groups are not saved at this point!
#        self.is_staff = (self.is_superuser or self.is_trainer)
#        super(User, self).save(force_insert=False, force_update=force_update, *args, **kwargs)


def create_user_for_basicuser(
    sender: type[BasicUser], instance: BasicUser, created: bool, **kwargs: Any
) -> None:
    """ Model inheritance is archived through joining of the base- and subclass's tables. To prevent inconsistencies a User is created every time a BaseUser is created. (ex. manage.py create_superuser)"""
    if created:
        u = User()
        vars(u).update(vars(instance))
        u.save()
signals.post_save.connect(create_user_for_basicuser, sender=BasicUser)

class Tutorial(models.Model):
    if TYPE_CHECKING:
        id: models.AutoField[int | None, int]
        user_set: ReverseManyToOneDescriptor[User]

    name: "models.CharField[str, str]" = models.CharField(max_length=100, blank=True, help_text=gettext_lazy("The name of the tutorial"))
    # A Tutorial may have many tutors as well as a Tutor may have multiple tutorials
    tutors: "models.ManyToManyField[User, models.Model]" = models.ManyToManyField('User', limit_choices_to = {'groups__name': 'Tutor'}, related_name='tutored_tutorials', help_text = gettext_lazy("The tutors in charge of the tutorial."))

    @display(description=gettext_lazy('Tutors'))
    def tutors_flat(self) -> str:
        return reduce(lambda x, y: x + ', ' + y.get_full_name(), self.tutors.all(), '')[2:]

    def __str__(self) -> str:
        return("%s: %s" % (self.name, self.tutors_flat()))
