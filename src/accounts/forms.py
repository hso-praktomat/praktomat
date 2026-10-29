import re
import typing as _typing

from django.conf import settings
from django.db import transaction
from django.db.models import QuerySet
from django.template import loader
from django.utils.translation import gettext_lazy
from django.contrib.auth.models import Group
from django import forms
from django.contrib.auth.forms import AdminUserCreationForm as AdminUserBaseCreationForm, UserChangeForm as UserBaseChangeForm
from django.core.mail import send_mail
from django.utils.http import int_to_base36
from django.utils.safestring import mark_safe
from configuration import get_settings

from accounts.models import User, Tutorial

class MyRegistrationForm(
    AdminUserBaseCreationForm[User] if _typing.TYPE_CHECKING else AdminUserBaseCreationForm
):

    def __init__(self, *args: _typing.Any, **kwargs: _typing.Any) -> None:
        # post, domaine=None, use_https=None):
        if 'domain' in kwargs:
            self.domain: str = kwargs.pop('domain')
        if 'use_https' in kwargs:
            self.use_https: bool = kwargs.pop('use_https')
        super(MyRegistrationForm, self).__init__(*args, **kwargs)

    # overriding modelfields to ensure required fields are provided
    first_name = forms.CharField(max_length = 30, required=True)
    last_name = forms.CharField(max_length = 30, required=True)
    email = forms.EmailField(required=True)

    # adding first and last name, email to the form
    class Meta(AdminUserBaseCreationForm.Meta if _typing.TYPE_CHECKING else object):
        model = User
        fields = ("username", "first_name", "last_name", "email", "mat_number")

    def clean_email(self) -> str:
        # cleaning the email in the form doesn't validate it in the admin (good for tutors etc.)
        data = self.cleaned_data['email']
        email_validation_regex = get_settings().email_validation_regex
        if email_validation_regex and not re.match(email_validation_regex, data):
            raise forms.ValidationError("The email you have provided is not valid. It has to be in: " + email_validation_regex)
        return data

    def clean_mat_number(self) -> int:
        # Special error message for un-unique / empty matnumbers on user registration.
        data = self.cleaned_data['mat_number']
        if not data:
            raise forms.ValidationError("This field is required.")
        for user in User.objects.filter(mat_number=data):
            if user.is_activated():
                trainer_group = Group.objects.get(name='Trainer')
                trainers = ["<a href='mailto:%s'>%s</a>" % (trainer.email, trainer.get_full_name() or trainer.email) for trainer in User.objects.filter(groups=trainer_group)]
                trainers = ', '.join(trainers)
                raise forms.ValidationError(mark_safe("A user with this number is already registered. Please contact a trainer: %s" % trainers ))
        return data


    @transaction.atomic
    def save(self, *args: _typing.Any, **kwargs: _typing.Any) -> User:
        user: User = super(MyRegistrationForm, self).save(*args, **kwargs)

        # default group: user
        user.groups.set(Group.objects.filter(name='User'))

        # disable user until activated via email
        user.is_active=False

        user.set_new_activation_key()

        user.mat_number=self.cleaned_data.get("mat_number")

        user.save()

        # Send activation email
        c = {
            'email': user.email,
            'domain': self.domain,
            'site_name': settings.SITE_NAME,
            'uid': int_to_base36(user.id),
            'user': user,
            'protocol': self.use_https and 'https' or 'http',
            'activation_key': user.activation_key,
            'expiration_days': get_settings().acount_activation_days,
            }

        if get_settings().account_manual_validation:
            t = loader.get_template('registration/registration_email_manual_to_staff.html')
            send_mail(gettext_lazy("Account activation on %s for %s (%s) ") % (settings.SITE_NAME, user.username, str(user)), t.render(c), None, [staff.email for staff in User.objects.all().filter(is_staff=True)])

            t = loader.get_template('registration/registration_email_manual_to_user.html')
            send_mail(gettext_lazy("Account activation on %s") % settings.SITE_NAME, t.render(c), None, [user.email])
        else:
            t = loader.get_template('registration/registration_email.html')
            send_mail(gettext_lazy("Account activation on %s") % settings.SITE_NAME, t.render(c), None, [user.email])

        return user

class UserChangeForm(
    forms.ModelForm[User] if _typing.TYPE_CHECKING else forms.ModelForm
):

    # overriding modelfields to ensure required fields are provided
    first_name = forms.CharField(max_length = 30, required=True)
    last_name = forms.CharField(max_length = 30, required=True)
    #email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ("first_name", "last_name")


class AdminUserCreationForm(
    AdminUserBaseCreationForm[User] if _typing.TYPE_CHECKING else AdminUserBaseCreationForm
):
    # Django accepts "__all__"; the creation-form stub restricts fields to tuples.
    if _typing.TYPE_CHECKING:
        class Meta(AdminUserBaseCreationForm.Meta):
            model = User
    else:
        class Meta:
            model = User
            fields = "__all__"


class AdminUserChangeForm(
    UserBaseChangeForm[User] if _typing.TYPE_CHECKING else UserBaseChangeForm
):
    class Meta(UserBaseChangeForm.Meta if _typing.TYPE_CHECKING else object):
        model = User
        fields = "__all__"
        widgets = {
            'user_text': forms.Textarea,
        }

    def clean(self) -> dict[str, _typing.Any]:
        # Require a mat number only if user is in group "User".
        cleaned_data = super(AdminUserChangeForm, self).clean()
        if cleaned_data is None:
            cleaned_data = self.cleaned_data
        groups: object = cleaned_data.get("groups")
        if not groups:
            if not self.has_error("groups"):
                self.add_error("groups", "This field is required.")
        elif not isinstance(groups, QuerySet):
            raise forms.ValidationError("Invalid groups selection.")
        else:
            group_queryset = _typing.cast("QuerySet[Group]", groups)
            if group_queryset.model is not Group:
                raise forms.ValidationError("Invalid groups selection.")
            if group_queryset.filter(name="User").exists() and not (cleaned_data.get("mat_number") or settings.DUMMY_MAT_NUMBERS):
                self.add_error("mat_number", "This field is required for Users.")
        return cleaned_data

reactivation_message_text = """ {% autoescape off %}
You're receiving this e-mail because you have been registered at {{ site_name }}.

Please go to the following page to activate your account within {{ expiration_days }} days.

{{ protocol }}://{{ domain }}{% url registration_activate activation_key=activation_key %}

Your username, in case you've forgotten: {{ user.username }}

Thanks for using our site!

The {{ site_name }} team

{% endautoescape %} """

class ImportForm(forms.Form):
    file = forms.FileField(required=True, help_text = "The file exported from the list view. Already existing users will be ignored.")
    require_reactivation = forms.BooleanField(initial=True, required=False, help_text = "Deactivate all imported users")
    send_reactivation_email = forms.BooleanField(initial=False, required=False, help_text = "Send activation email to imported users (if deactivated during import)")
    meassagetext = forms.CharField(required=False, widget=forms.Textarea, initial = reactivation_message_text, help_text = "Message to be embedded into activation mail if reactivation is required.")

class ImportLDAPForm(forms.Form):
    tutorial = forms.ModelChoiceField(queryset=Tutorial.objects.all(), required=False)
    uids = forms.CharField(label='UIDs', required=False, widget=forms.Textarea, initial = '', help_text = "List of UIDs to be imported, delimited by whitespace. Already existing accounts will be ignored.")


IMPORT_TUTORIAL_ASSIGNMENT_TYPES = (
    ("mat_number", "Matriculation number"),
    ("username", "Username"),
)


class ImportTutorialAssignmentForm(forms.Form):
    csv_file = forms.FileField(required=True, help_text = "The csv file containing the tutorial name and the students' mat number or username.")
    delimiter = forms.CharField(required=True, max_length = 1, initial = ";", help_text = "A one-character string used to separate fields.")
    quotechar = forms.CharField(required=True, max_length = 1, initial = "|", help_text = "A one-character string used to quote fields.")
    name_column = forms.IntegerField(required=True, initial = 0, help_text = "The index of the field containing the name of the tutorial.")
    user_id_column = forms.IntegerField(required=True, initial = 1, help_text = "The index of the field containing the mat number or username of the user.")
    user_id_type = forms.ChoiceField(required=True, choices = IMPORT_TUTORIAL_ASSIGNMENT_TYPES, initial = "mat_number", help_text = "The type of user identification.")

class ImportUserTextsForm(forms.Form):
    csv_file = forms.FileField(required=True, help_text = "The csv file containing the tutorial name and the students' mat number.")
    delimiter = forms.CharField(required=True, max_length = 1, initial = ";", help_text = "A one-character string used to separate fields.")
    quotechar = forms.CharField(required=True, max_length = 1, initial = "|", help_text = "A one-character string used to quote fields.")

class ImportMatriculationListForm(forms.Form):
    mat_number_file = forms.FileField(required=True, help_text = "A text file consisting of one matriculation number per line.")
    remove_others = forms.BooleanField(required=False, initial = True, help_text = "Also remove all users from the group if they are not listed here.")
    create_users = forms.BooleanField(required=False, initial = False, help_text = "If a matriculation number is not known yet, create a stub user object")

class AcceptDisclaimerForm(forms.Form):
    accept_disclaimer = forms.BooleanField(required=True, initial = False, help_text = "You need to accept the disclaimer before using the site.")
