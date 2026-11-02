from django.contrib import admin
from django.db.models import QuerySet as _QuerySet
from django.forms.models import ModelForm
from django.http import HttpRequest as _HttpRequest
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import SafeString as _SafeString
import typing as _typing
from .basemodels import Checker, CheckerResult
from tasks.models import Task

_CheckerT = _typing.TypeVar('_CheckerT', bound=Checker)


if _typing.TYPE_CHECKING:
    from django_stubs_ext import FieldsetSpec

class AlwaysChangedModelForm(
    ModelForm[_typing.Any] if _typing.TYPE_CHECKING else ModelForm
):
    """ This fixes the creation of inlines without modifying any of it's values. The standart ModelForm would just ignore these inlines. """
    def has_changed(self) -> bool:
        """ Should return True if data differs from initial. By always returning true even unchanged inlines will get validated and saved."""
        return True

class CheckerInline(
    admin.StackedInline[_CheckerT, Task] if _typing.TYPE_CHECKING else admin.StackedInline,
    _typing.Generic[_CheckerT],
):
    """ Base class for checker inlines """
    extra: int = 0
    form = AlwaysChangedModelForm
    # added checker class to inlinegroup and inlinerelated for js ordering in admin
    # this is a copy of the django template with only minor changes - keep in sync with new django versions
    template: str = "admin/tasks/stacked.html"

    def get_fieldsets(
        self, request: _HttpRequest, obj: Task | None = None
    ) -> "FieldsetSpec":
        """ Get the fields public, required, always and critical on the first line without defining fieldsets in every subclass. This saves a lot of space. """

        # The stub's generic instance attribute is also used on the generated class.
        form = _typing.cast(
            "type[ModelForm[_CheckerT]]",
            getattr(self.get_formset(request, obj, fields=None), 'form'),
        )
        fields = list(form.base_fields.keys()) + list(self.get_readonly_fields(request, obj))
        fields.remove('public')
        fields.remove('required')
        fields.remove('always')
        fields.remove('critical')
        return [(self.model.description(), {'fields':(('public', 'required', 'always', 'critical'),)}),
                    (None, {'fields': tuple(fields)})]

class CheckerResultAdmin(admin.ModelAdmin[CheckerResult] if _typing.TYPE_CHECKING else admin.ModelAdmin):
    model: type[CheckerResult] = CheckerResult
    list_display = ["edit", "view_solution", "solution_final", "checker", "passed", "creation_date", "runtime"]
    readonly_fields = ["solution", "checker", "passed", "creation_date", "runtime"]
    list_filter = ["solution__final", "passed", "solution__task", "creation_date"]

    def get_queryset(
        self, request: _HttpRequest
    ) -> _QuerySet[CheckerResult, CheckerResult]:
        qs = super(CheckerResultAdmin, self).get_queryset(request)
        qs = qs.select_related("solution", "solution__task", "solution__author")
        qs = qs.prefetch_related("checker")
        return qs

    @admin.display(description='Edit (Admin Site)')
    def edit(self, checkerResult: CheckerResult) -> str:
        return 'Edit'

    @admin.display(description='View Solution (User Site)')
    def view_solution(self, checkerResult: CheckerResult) -> _SafeString:
        return format_html('<a href="{0}">{1}</a>', reverse('solution_detail_full', args=[checkerResult.solution.id]), checkerResult.solution)

    @admin.display(boolean=True)
    def solution_final(self, checkerResult: CheckerResult) -> bool:
        return checkerResult.solution.final

    def has_add_permission(self, request: _HttpRequest) -> bool:
        return False

admin.site.register(CheckerResult, CheckerResultAdmin)
