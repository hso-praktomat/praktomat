from typing import Any, TYPE_CHECKING

from django.forms.models import ModelForm, inlineformset_factory, BaseInlineFormSet
from django import forms

from attestation.models import Attestation, AnnotatedSolutionFile, RatingResult, SolutionFile
from configuration.models import Settings


class AttestationForm(
    ModelForm[Attestation] if TYPE_CHECKING else ModelForm
):
    class Meta:
        model = Attestation
        exclude = ('solution', 'author', 'final', 'published', 'published_on')
        widgets = {
            'public_comment': forms.Textarea(attrs={'cols': 80, 'rows': 10}),
            'private_comment': forms.Textarea(attrs={'cols': 80, 'rows': 10}),
        }


    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super(AttestationForm, self).__init__(*args, **kwargs)
        final_grade_rating_scale = self.instance.solution.task.final_grade_rating_scale
        if final_grade_rating_scale:
            field = self.fields['final_grade']
            if not isinstance(field, forms.ModelChoiceField):
                raise TypeError("Expected a model choice field for final_grade")
            field.choices = [(item.pk, item.name) for item in final_grade_rating_scale.ratingscaleitem_set.all()]
        else:
            del self.fields['final_grade']

class AttestationPreviewForm(
    ModelForm[Attestation] if TYPE_CHECKING else ModelForm
):
    class Meta:
        model = Attestation
        fields = ('final',)

class AnnotatedFileForm(
    ModelForm[AnnotatedSolutionFile] if TYPE_CHECKING else ModelForm
):
    class Meta:
        model = AnnotatedSolutionFile
        fields=('content', 'solution_file',)

    solution_file: forms.IntegerField = forms.IntegerField(
        widget=forms.HiddenInput
    )

    def clean_solution_file(self) -> SolutionFile:
        solution_file_id: int = self.cleaned_data['solution_file']
        try:
            solution_file  = SolutionFile.objects.get(pk=solution_file_id)
        except SolutionFile.DoesNotExist:
            raise forms.ValidationError(
                f"No Solutionfile exists by id{solution_file_id}"
            )

        return solution_file



AnnotatedFileFormSet = inlineformset_factory(Attestation, AnnotatedSolutionFile, form=AnnotatedFileForm, formset=BaseInlineFormSet, can_delete=False, extra=0)


class RatingResultForm(
    ModelForm[RatingResult] if TYPE_CHECKING else ModelForm
):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super(RatingResultForm, self).__init__(*args, **kwargs)
        ratingResult = self.instance
        self.fields['mark'].label = ratingResult.rating.aspect.name
        self.fields['mark'].help_text = ratingResult.rating.aspect.description
        field = self.fields['mark']
        if not isinstance(field, forms.ModelChoiceField):
            raise TypeError("Expected a model choice field for mark")
        field.choices = [(item.pk, item.name) for item in ratingResult.rating.scale.ratingscaleitem_set.all()]

    class Meta:
        model = RatingResult
        fields=('mark',)

RatingResultFormSet = inlineformset_factory(Attestation, RatingResult, form=RatingResultForm, formset=BaseInlineFormSet, can_delete=False, extra=0)


class PublishFinalGradeForm(
    ModelForm[Settings] if TYPE_CHECKING else ModelForm
):
    class Meta:
        model = Settings
        fields = ('final_grades_published',)

class GenerateRatingScaleForm(forms.Form):
    name: forms.CharField = forms.CharField(max_length=200,  help_text = 'The Name of the rating scale for the aspects. E.g.: "School marks"')
    start: forms.FloatField = forms.FloatField(initial=0, help_text="The first RatingScaleItem to generate.")
    end: forms.FloatField = forms.FloatField(initial=15, help_text="The last RatingScaleItem to generate.")
    step: forms.FloatField = forms.FloatField(initial=1, help_text="The step size between the RatingScaleItems.")


class FinalGradeOptionForm(
    ModelForm[Settings] if TYPE_CHECKING else ModelForm
):
    class Meta:
        model = Settings
        fields = ('final_grades_arithmetic_option', 'final_grades_plagiarism_option')
