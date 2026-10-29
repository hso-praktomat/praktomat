from django.contrib import admin
from django import forms
from django.db.models import QuerySet as _QuerySet
from django.http import HttpRequest as _HttpRequest, HttpResponse as _HttpResponse
from attestation.models import *
from django.urls import URLPattern as _URLPattern, reverse
from django.utils.html import format_html
from django.utils.safestring import SafeString as _SafeString
import typing as _typing

import attestation.views

admin.autodiscover()

class RatingScaleItemInline(admin.TabularInline[RatingScaleItem, RatingScale] if _typing.TYPE_CHECKING else admin.TabularInline):
    model: type[RatingScaleItem] = RatingScaleItem
    extra = 0


class RatingScaleAdmin(admin.ModelAdmin[RatingScale] if _typing.TYPE_CHECKING else admin.ModelAdmin):
    model: type[RatingScale] = RatingScale
    inlines = [RatingScaleItemInline]

    class Media:
        js = (
              'frameworks/jquery/jquery.js',
              'frameworks/jquery/jquery-ui.js',
              'frameworks/jquery/jquery.tinysort.js',
              'script/rating_scale_sort.js',
        )

admin.site.register(RatingScale, RatingScaleAdmin)

admin.site.register(RatingAspect)


class AnnotatedSolutionFileAdminInline(admin.StackedInline[AnnotatedSolutionFile, Attestation] if _typing.TYPE_CHECKING else admin.StackedInline):
    model: type[AnnotatedSolutionFile] = AnnotatedSolutionFile
    fields = ('content',)
    extra, max_num  = 0, 0
    can_delete = False

class RatingResultAdminInline(admin.StackedInline[RatingResult, Attestation] if _typing.TYPE_CHECKING else admin.StackedInline):
    model: type[RatingResult] = RatingResult
    fields = ('mark',)
    extra, max_num  = 0, 0
    can_delete = False

class AttestationAdmin(admin.ModelAdmin[Attestation] if _typing.TYPE_CHECKING else admin.ModelAdmin):
    model: type[Attestation] = Attestation
    readonly_fields = ('created', 'show_solution',)
    fields = ( 'show_solution', 'author', 'created', 'public_comment', 'private_comment', 'final_grade', 'final', 'published', 'published_on')
    list_display = ('solution', 'author', 'created', 'final', 'published', 'published_on')
    list_filter = ('final', 'published', 'author', 'solution__author', 'solution__task')
    inlines = (RatingResultAdminInline, AnnotatedSolutionFileAdminInline)
    actions = ['export_attestations']

    def export_attestations(
        self, request: _HttpRequest, queryset: _QuerySet[Attestation, Attestation]
    ) -> _HttpResponse:
        """ Export Attestation action """
        from django.http import HttpResponse
        response = HttpResponse(Attestation.export_Attestation(queryset), content_type="application/xml")
        response['Content-Disposition'] = 'attachment; filename=AttestationExport.xml'
        return response

    def get_form(
        self,
        request: _HttpRequest,
        obj: Attestation | None = None,
        change: bool = False,
        **kwargs: _typing.Any,
    ) -> "type[forms.ModelForm[Attestation]]":
        form = super().get_form(request, obj, change, **kwargs)
        field = form.base_fields.get('final_grade')
        if field is not None:
            if not isinstance(field, forms.ModelChoiceField):
                raise TypeError("Expected a model choice field for final_grade")
            scale_id = obj.solution.task.final_grade_rating_scale_id if obj is not None else None
            field.queryset = (
                RatingScaleItem.objects.filter(scale_id=scale_id)
                if scale_id is not None else RatingScaleItem.objects.none()
            )
        return form

    @admin.display(description='Solution')
    def show_solution(self, instance: Attestation) -> _SafeString:
        return format_html('<a href="{0}">{1}</a> by <a href="{2}">{3}</a>',
                           reverse('admin:solutions_solution_change', args=(instance.solution.pk,)),
                           instance.solution,
                           reverse('admin:accounts_user_change', args=(instance.solution.author.pk,)),
                           instance.solution.author,
                          )


    def get_urls(self) -> list[_URLPattern]:
        """ Add URL to Attestation update """
        urls = super(AttestationAdmin, self).get_urls()
        from django.urls import re_path
        my_urls = [re_path(r'^update/$', attestation.views.update_attestations, name='attestation_update')]
        return my_urls + urls

    def has_add_permission(self, request: _HttpRequest) -> bool:
        return False

admin.site.register(Attestation, AttestationAdmin)


class RatingAdminInline(admin.StackedInline[Rating, Task] if _typing.TYPE_CHECKING else admin.StackedInline):
    """ used in task as inline """
    model: type[Rating] = Rating
    extra = 0
