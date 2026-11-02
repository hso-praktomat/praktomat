from datetime import datetime, timedelta
from unittest.mock import patch
from decimal import Decimal
from types import SimpleNamespace

from utilities.TestSuite import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django import forms
from django.forms.utils import ErrorList
from django.contrib.admin import AdminSite
from django.test import RequestFactory

from accounts.models import User
from attestation.admin import AttestationAdmin
from attestation.views import user_task_attestation_map
from checker.checker.TextChecker import TextChecker
from checker.basemodels import CheckerResult
from solutions.models import Solution
from tasks.models import Task
from attestation.models import AnnotatedSolutionFile, Attestation, Rating, RatingAspect, RatingResult, RatingScale, RatingScaleItem
from attestation.forms import (
    AttestationForm, RatingResultForm, AnnotatedFileForm,
    AnnotatedFileFormSet, RatingResultFormSet,
)
from solutions.models import SolutionFile


class TestAnnotationDiffContracts(TestCase):
    def diff(self, original: str, annotated: str) -> str:
        solution_file = SolutionFile(solution=Solution.objects.get(pk=1))
        annotation = AnnotatedSolutionFile(solution_file=solution_file, content=annotated)
        with patch.object(SolutionFile, 'content', return_value=original):
            return annotation.content_diff()

    def test_normalizes_line_endings_and_blank_borders(self) -> None:
        self.assertEqual(
            self.diff('\r\n \r\nfirst\r\nsecond\r\n\r\n', '\nfirst\nsecond\n \n'),
            '  first\n  second',
        )

    def test_preserves_added_removed_and_interior_blank_lines(self) -> None:
        self.assertEqual(
            self.diff('first\n\nold\n', 'first\n\nnew\n'),
            '  first\n  \n- old\n+ new',
        )

    def test_empty_and_blank_only_content(self) -> None:
        self.assertEqual(self.diff('', ''), '')
        self.assertEqual(self.diff(' \r\n\t\r', '\n '), '')


class TestAttestationHTTPContracts(TestCase):
    def setUp(self) -> None:
        self.client.force_login(User.objects.get(username='trainer'))

    def test_statistics_without_scale_or_students_keeps_chart_arrays(self) -> None:
        task = Task.objects.get(pk=1)
        task.final_grade_rating_scale = None
        task.save()
        User.objects.filter(groups__name='User').update(is_active=False)
        response = self.client.get(reverse('statistics', args=[task.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['final_grade_rating_scale_items'], '[]')
        self.assertEqual(response.context['user_count'], 0)
        self.assertEqual(response.context['acc_submissions'], [0.0])
        self.assertIsInstance(response.context['submissions'], list)
        self.assertEqual(response.context['runtimes'], [])

    def test_runtime_series_keep_checker_index_and_twenty_medians(self) -> None:
        task = Task.objects.get(pk=1)
        checker = TextChecker.objects.create(task=task, order=0)
        solution = Solution.objects.get(task=task)
        CheckerResult.objects.create(solution=solution, checker=checker, runtime=25)
        with patch.object(Task, 'get_checkers', return_value=[checker]):
            response = self.client.get(reverse('statistics', args=[task.pk]))
        self.assertEqual(response.status_code, 200)
        series = response.context['runtimes'][0]
        self.assertEqual(series['checker'], f'0: {checker.title()}')
        self.assertEqual(len(series['medians']), 20)
        self.assertEqual(series['runtimes'][0]['value'], 25)
        self.assertEqual(series['medians'][0]['value'], 25)
        self.assertTrue(response.context['has_runtime_chart'])

    def test_invalid_preview_post_renders_bound_errors(self) -> None:
        from attestation.forms import AttestationPreviewForm
        attestation = Attestation.objects.get(pk=1)
        form = AttestationPreviewForm({'final': True}, instance=attestation)
        form.is_valid()
        form.add_error(None, 'Preview validation failed')
        with patch('attestation.views.AttestationPreviewForm', return_value=form):
            response = self.client.post(reverse('view_attestation', args=[attestation.pk]), {'final': True})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Preview validation failed')
        attestation.refresh_from_db()
        self.assertFalse(attestation.published)

    def test_superuser_list_has_no_undefined_author_flag(self) -> None:
        user = User.objects.get(username='trainer')
        user.groups.clear()
        user.save()
        with patch('attestation.views.get_settings', return_value=SimpleNamespace(anonymous_attestation=True)):
            response = self.client.get(reverse('attestation_list', args=[1]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['show_author'])
        self.assertIsNone(response.context['all_attestations'])

    def test_rating_rows_preserve_decimal_thresholds_and_iterable_tasks(self) -> None:
        attestation = Attestation.objects.get(pk=1)
        task = attestation.solution.task
        task.warning_threshold = Decimal('1.5')
        task.submission_date = datetime.now() - timedelta(hours=1)
        task.save()
        scale = RatingScale.objects.create(name='HTTP numeric grade')
        grade = RatingScaleItem.objects.create(scale=scale, name='3', position=0)
        attestation.final_grade = grade
        attestation.published = True
        attestation.save()
        user = attestation.solution.author
        with patch('attestation.views.get_settings', return_value=SimpleNamespace(
            final_grades_arithmetic_option='AVG', final_grades_plagiarism_option='WP',
        )):
            rows = user_task_attestation_map([user, user], iter([task, task]))
        self.assertEqual(len(rows), 2)
        for _, cells, threshold, calculated in rows:
            self.assertEqual(len(cells), 2)
            self.assertEqual(threshold, Decimal('3'))
            self.assertEqual(calculated, 3.0)

    def test_rating_rows_ignore_non_numeric_and_excluded_plagiarism(self) -> None:
        attestation = Attestation.objects.get(pk=1)
        scale = RatingScale.objects.create(name='HTTP grade exclusion')
        grade = RatingScaleItem.objects.create(scale=scale, name='Pass', position=0)
        attestation.final_grade = grade
        attestation.published = True
        attestation.save()
        for option in ('NP', 'WP'):
            with self.subTest(option=option), patch('attestation.views.get_settings', return_value=SimpleNamespace(
                final_grades_arithmetic_option='SUM', final_grades_plagiarism_option=option,
            )):
                rows = user_task_attestation_map([attestation.solution.author], [attestation.solution.task])
                self.assertEqual(rows[0][3], 0.0)
        grade.name = '4'
        grade.save()
        attestation.solution.plagiarism = True
        attestation.solution.save()
        with patch('attestation.views.get_settings', return_value=SimpleNamespace(
            final_grades_arithmetic_option='SUM', final_grades_plagiarism_option='NP',
        )):
            self.assertEqual(user_task_attestation_map([attestation.solution.author], [attestation.solution.task])[0][3], 0.0)

    def test_import_errors_are_attached_to_form(self) -> None:
        with patch.object(Attestation, 'update_Attestations', side_effect=ValueError('bad document')):
            response = self.client.post(reverse('admin:attestation_update'), {
                'file': SimpleUploadedFile('attestations.xml', b'invalid'),
            })
        self.assertEqual(response.status_code, 200)
        self.assertIn('bad document', str(response.context['form'].errors['file']))


class TestAttestationAdminContracts(TestCase):
    def setUp(self) -> None:
        self.model_admin = AttestationAdmin(Attestation, AdminSite())
        self.request = RequestFactory().get('/')
        self.request.user = User(is_active=True, is_staff=True, is_superuser=True)
        self.attestation = Attestation.objects.get(pk=1)

    def test_grade_choices_are_scoped_without_mutating_request(self) -> None:
        scale = RatingScale.objects.create(name='Admin grade scale')
        item = RatingScaleItem.objects.create(scale=scale, name='Admin pass', position=1)
        unrelated = RatingScale.objects.create(name='Unrelated scale')
        other = RatingScaleItem.objects.create(scale=unrelated, name='Unrelated grade', position=1)
        self.attestation.solution.task.final_grade_rating_scale = scale
        form = self.model_admin.get_form(self.request, self.attestation, True)
        rendered = str(form(instance=self.attestation)['final_grade'])
        self.assertIn(f'value="{item.pk}"', rendered)
        self.assertNotIn(f'value="{other.pk}"', rendered)
        self.assertFalse(hasattr(self.request, 'obj'))

    def test_interleaved_form_factories_do_not_share_grade_choices(self) -> None:
        first = RatingScale.objects.create(name='First admin scale')
        second = RatingScale.objects.create(name='Second admin scale')
        a = RatingScaleItem.objects.create(scale=first, name='First grade', position=1)
        b = RatingScaleItem.objects.create(scale=second, name='Second grade', position=1)
        task = self.attestation.solution.task
        task.final_grade_rating_scale = first
        first_form = self.model_admin.get_form(self.request, self.attestation)
        task.final_grade_rating_scale = second
        second_form = self.model_admin.get_form(self.request, self.attestation)
        self.assertIn(f'value="{a.pk}"', str(first_form()['final_grade']))
        self.assertNotIn(f'value="{b.pk}"', str(first_form()['final_grade']))
        self.assertIn(f'value="{b.pk}"', str(second_form()['final_grade']))
        self.assertNotIn(f'value="{a.pk}"', str(second_form()['final_grade']))

    def test_missing_scale_and_missing_object_offer_no_grades(self) -> None:
        scale = RatingScale.objects.create(name='Unavailable scale')
        item = RatingScaleItem.objects.create(scale=scale, name='Unavailable grade', position=1)
        self.attestation.solution.task.final_grade_rating_scale = None
        for obj in (None, self.attestation):
            with self.subTest(obj=obj):
                form = self.model_admin.get_form(self.request, obj)
                self.assertNotIn(f'value="{item.pk}"', str(form()['final_grade']))

    def test_excluded_grade_and_unexpected_field_type(self) -> None:
        form = self.model_admin.get_form(self.request, self.attestation, fields=['public_comment'])
        self.assertNotIn('final_grade', form.base_fields)
        form.base_fields['final_grade'] = forms.CharField()
        with patch('django.contrib.admin.ModelAdmin.get_form', return_value=form):
            with self.assertRaisesRegex(TypeError, 'model choice field'):
                self.model_admin.get_form(self.request, self.attestation)

    def test_real_change_page_without_a_scale(self) -> None:
        task = self.attestation.solution.task
        task.final_grade_rating_scale = None
        task.save()
        user = User.objects.get(username='trainer')
        user.is_superuser = True
        user.is_staff = True
        user.save()
        self.client.force_login(user)
        response = self.client.get(reverse('admin:attestation_attestation_change', args=[self.attestation.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="final_grade"')


class TestAttestationFormContracts(TestCase):
    def test_attestation_choices_come_from_instance_scale(self) -> None:
        attestation = Attestation.objects.get(pk=1)
        scale = RatingScale.objects.create(name='Form scale')
        item = RatingScaleItem.objects.create(scale=scale, name='Pass', position=1)
        task = attestation.solution.task
        task.final_grade_rating_scale = scale
        task.save()
        form = AttestationForm(instance=attestation)
        field = form.fields['final_grade']
        assert isinstance(field, forms.ModelChoiceField)
        self.assertIn(f'<option value="{item.pk}">Pass</option>', str(form['final_grade']))

    def test_attestation_without_grade_scale_omits_grade_field(self) -> None:
        attestation = Attestation.objects.get(pk=1)
        task = attestation.solution.task
        task.final_grade_rating_scale = None
        task.save()
        self.assertNotIn('final_grade', AttestationForm(instance=attestation).fields)

    def test_positional_instance_is_used_for_grade_choices(self) -> None:
        attestation = Attestation.objects.get(pk=1)
        task = attestation.solution.task
        task.final_grade_rating_scale = None
        task.save()
        form = AttestationForm(None, None, False, None, None, ErrorList, None, False, attestation)
        self.assertNotIn('final_grade', form.fields)

    def test_rating_choices_labels_and_save_preserve_model_instances(self) -> None:
        attestation = Attestation.objects.get(pk=1)
        scale = RatingScale.objects.create(name='Aspect form scale')
        item = RatingScaleItem.objects.create(scale=scale, name='Good', position=1)
        aspect = RatingAspect.objects.create(name='Clarity', description='Readability')
        rating = Rating.objects.create(task=attestation.solution.task, aspect=aspect, scale=scale)
        result = RatingResult.objects.create(attestation=attestation, rating=rating)
        form = RatingResultForm({'mark': str(item.pk)}, instance=result)
        field = form.fields['mark']
        assert isinstance(field, forms.ModelChoiceField)
        self.assertEqual(field.label, 'Clarity')
        self.assertEqual(field.help_text, 'Readability')
        self.assertIn(f'<option value="{item.pk}" selected>Good</option>', str(form['mark']))
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        self.assertEqual(saved.mark, item)

    def test_annotation_hidden_id_resolves_to_solution_file_or_validation_error(self) -> None:
        file = SolutionFile.objects.all()[0]
        form = AnnotatedFileForm()
        form.cleaned_data = {'solution_file': file.pk}
        self.assertEqual(form.clean_solution_file(), file)
        form.cleaned_data = {'solution_file': -1}
        with self.assertRaises(forms.ValidationError):
            form.clean_solution_file()

    def test_generated_formsets_keep_parent_child_models(self) -> None:
        attestation = Attestation.objects.get(pk=1)
        annotations = AnnotatedFileFormSet(instance=attestation)
        ratings = RatingResultFormSet(instance=attestation)
        self.assertEqual(annotations.instance, attestation)
        self.assertEqual(ratings.instance, attestation)
        self.assertIn(AnnotatedFileForm, annotations.form.__mro__)
        self.assertIn(RatingResultForm, ratings.form.__mro__)


class TestRatingModelContracts(TestCase):
    def test_nullable_grades_and_reverse_relations(self) -> None:
        attestation = Attestation.objects.get(pk=1)
        scale = RatingScale.objects.create(name='Model contract scale')
        aspect = RatingAspect.objects.create(name='Correctness')
        rating = Rating.objects.create(task=attestation.solution.task, aspect=aspect, scale=scale)
        result = RatingResult.objects.create(attestation=attestation, rating=rating)
        self.assertIsNone(attestation.final_grade)
        self.assertIsNone(attestation.final_grade_id)
        self.assertIsNone(result.mark)
        self.assertIsNone(result.mark_id)
        item = RatingScaleItem.objects.create(scale=scale, name='Pass', position=1)
        result.mark = item
        result.save()
        attestation.final_grade = item
        attestation.save()
        self.assertEqual(scale.ratingscaleitem_set.get(), item)
        self.assertEqual(scale.rating_set.get(), rating)
        self.assertEqual(aspect.rating_set.get(), rating)
        self.assertEqual(rating.ratingresult_set.get(), result)
        self.assertEqual(item.attestation_set.get(), attestation)
        self.assertEqual(item.ratingresult_set.get(), result)
        self.assertEqual(attestation.solution.attestation_set.get(), attestation)
        self.assertIn(attestation, attestation.author.attestation_set.all())
        item.delete()
        result.refresh_from_db()
        attestation.refresh_from_db()
        self.assertIsNone(result.mark)
        self.assertIsNone(attestation.final_grade)

class TestViews(TestCase):
    def setUp(self) -> None:
        self.client.login(username='tutor', password='demo')
        self.task: Task = Task.objects.all()[0]
        self.task.submission_date = datetime.now() - timedelta(hours=1)
        self.task.save()
        self.task.check_all_final_solutions()
        self.solution: Solution = Solution.objects.all()[0]
        self.attestation: Attestation = Attestation.objects.all()[0]


    def tearDown(self) -> None:
        pass

    def test_get_attestation_list(self) -> None:
        response = self.client.get(reverse('attestation_list', args=[self.task.id]))
        self.assertEqual(response.status_code, 200)

    def test_get_new_attestation(self) -> None:
        response = self.client.get(reverse('new_attestation_for_solution', args=[self.solution.id]), follow=True)
        self.assertEqual(response.status_code, 200)

    def test_get_edit_attestation(self) -> None:
        response = self.client.get(reverse('edit_attestation', args=[self.attestation.id]))
        self.assertEqual(response.status_code, 200)

    def test_post_edit_attestation(self) -> None:
        response = self.client.post(reverse('edit_attestation', args=[self.attestation.id]), data={
                            'attestfiles-TOTAL_FORMS': '0',
                            'attestfiles-INITIAL_FORMS': '0',
                            'ratingresult-TOTAL_FORMS': '0',
                            'ratingresult-INITIAL_FORMS': '0',
                        }, follow=True)
        self.assertRedirectsToView(response, 'view_attestation')

    def test_get_view_attestation(self) -> None:
        response = self.client.get(reverse('view_attestation', args=[self.attestation.id]))
        self.assertEqual(response.status_code, 200)

    def test_post_view_attestation(self) -> None:
        response = self.client.post(reverse('view_attestation', args=[self.attestation.id]),  data={
                            'final': True,
                        }, follow=True)
        self.assertRedirectsToView(response, 'attestation_list')

class TestTrainerViews(TestCase):
    def setUp(self) -> None:
        self.client.login(username='trainer', password='demo')

    def tearDown(self) -> None:
        pass

    def test_get_raiting_overview(self) -> None:
        response = self.client.get(reverse('rating_overview'))
        self.assertEqual(response.status_code, 200)

    def test_post_raiting_overview(self) -> None:
        response = self.client.post(reverse('rating_overview'), data={
                            'form-TOTAL_FORMS': 1,
                            'form-INITIAL_FORMS': 1,
                            'form-0-user_ptr': 1,
                            'form-0-final_grade:': '',
                        })
        self.assertEqual(response.status_code, 200)

    def test_rating_export(self) -> None:
        response = self.client.get(reverse('rating_export'))
        self.assertEqual(response.status_code, 200)

    def test_update_attestations_from_uploaded_xml(self) -> None:
        uploaded = SimpleUploadedFile(
            'attestations.xml', b'<django-objects version="1.0"></django-objects>'
        )
        response = self.client.post(
            reverse('admin:attestation_update'), {'file': uploaded}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Updated 0 attestations, and 0 rating results.")

    def test_update_attestations_rejects_malformed_xml(self) -> None:
        uploaded = SimpleUploadedFile('attestations.xml', b'not XML')
        response = self.client.post(
            reverse('admin:attestation_update'), {'file': uploaded}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "The import file was propably malformed.")
