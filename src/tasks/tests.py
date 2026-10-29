from os.path import dirname, join
from datetime import datetime, timedelta
from io import BytesIO
from zipfile import ZipFile
from tempfile import SpooledTemporaryFile
from unittest.mock import patch

from utilities.TestSuite import TestCase
from accounts.models import Tutorial, User
from attestation.models import RatingScale, RatingScaleItem
from django.core import serializers
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.urls import reverse
from django.contrib.admin import AdminSite
from django.test import RequestFactory

from checker.checker.ScriptChecker import ScriptChecker, ScriptCheckerInline
from checker.checker.TextChecker import TextChecker, TextCheckerInline
from tasks.admin import TaskAdmin
from solutions.models import Solution
from tasks.models import MediaFile, Task


class TestTaskAdminContracts(TestCase):
    def test_import_failure_is_rendered_as_a_file_error(self) -> None:
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.client.force_login(User.objects.get(username='trainer'))
        with patch.object(Task, 'import_Tasks', side_effect=ValueError('bad archive')):
            response = self.client.post(reverse('admin:task_import'), {
                'file': SimpleUploadedFile('tasks.zip', b'invalid'), 'is_template': True,
            })
        self.assertEqual(response.status_code, 200)
        self.assertIn('bad archive', str(response.context['form'].errors['file']))

    def test_checker_fieldsets_group_controls_once(self) -> None:
        request = RequestFactory().get('/')
        request.user = User(is_active=True, is_staff=True, is_superuser=True)
        task = Task.objects.get(pk=1)
        for inline in (TextCheckerInline(Task, AdminSite()), ScriptCheckerInline(Task, AdminSite())):
            with self.subTest(inline=inline):
                fieldsets = list(inline.get_fieldsets(request, task))
                self.assertEqual(fieldsets[0][1]['fields'], (('public', 'required', 'always', 'critical'),))
                self.assertEqual(fieldsets[0][0], inline.model.description())
                for control in ('public', 'required', 'always', 'critical'):
                    self.assertNotIn(control, fieldsets[1][1]['fields'])
                self.assertIn('order', fieldsets[1][1]['fields'])

    def test_checker_registry_preserves_concrete_forms(self) -> None:
        request = RequestFactory().get('/')
        request.user = User(is_active=True, is_staff=True, is_superuser=True)
        self.assertIn(ScriptCheckerInline, TaskAdmin.inlines)
        self.assertIn(TextCheckerInline, TaskAdmin.inlines)
        inline = TextCheckerInline(Task, AdminSite())
        formset = inline.get_formset(request, Task.objects.get(pk=1))()
        self.assertEqual(formset.model, TextChecker)
        self.assertTrue(formset.empty_form.has_changed())

    def test_recheck_action_reports_checked_count(self) -> None:
        request = RequestFactory().post('/')
        model_admin = TaskAdmin(Task, AdminSite())
        queryset = Task.objects.filter(pk=1)
        with patch.object(Task, 'check_all_final_solutions', return_value=3) as check, patch.object(model_admin, 'message_user') as message:
            model_admin.run_all_checkers_on_finals(request, queryset)
        check.assert_called_once_with()
        self.assertIn('3 final solutions', message.call_args.args[1])
        self.assertEqual(getattr(TaskAdmin.run_all_checkers_on_finals, 'short_description'), 'check only finals (Admin)')


class TestTaskExport(TestCase):
    def test_missing_export_file_closes_archive_and_raises(self) -> None:
        task = Task.objects.get(pk=1)
        MediaFile.objects.create(task=task)
        with SpooledTemporaryFile() as stream, patch('tasks.models.tempfile.SpooledTemporaryFile', return_value=stream):
            with self.assertRaises(ValueError):
                Task.export_Tasks(Task.objects.filter(pk=task.pk))
            self.assertTrue(stream.closed)

    def test_media_basename_requires_a_stored_file_name(self) -> None:
        media = MediaFile(task=Task.objects.get(pk=1))
        with self.assertRaisesRegex(ValueError, 'name'):
            media.basename()
        media.media_file.name = 'TaskMediaFiles/Task_1/folder/example.txt'
        self.assertEqual(media.basename(), 'example.txt')

    def test_empty_export_contains_only_empty_xml(self) -> None:
        with Task.export_Tasks(Task.objects.none()) as archive:
            self.assertEqual(archive.tell(), 0)
            with ZipFile(archive) as output:
                self.assertEqual(output.namelist(), ['data.xml'])
                self.assertEqual(
                    list(serializers.deserialize('xml', output.read('data.xml').decode())),
                    [],
                )

    def test_export_contains_related_models_and_file_contents(self) -> None:
        task = Task.objects.get(pk=1)
        scale = RatingScale.objects.create(name='Export test scale')
        item = RatingScaleItem.objects.create(scale=scale, name='Pass', position=1)
        solution = Solution.objects.get(task=task)
        task.final_grade_rating_scale = scale
        task.model_solution = solution
        task.save()
        media = MediaFile(task=task)
        media.media_file.save('export.txt', ContentFile(b'export media'))
        checker = ScriptChecker(task=task, order=2)
        checker.shell_script.save('export.sh', ContentFile(b'#!/bin/sh\nexit 0\n'))
        solution_file = solution.solutionfile_set.get()

        with Task.export_Tasks(Task.objects.filter(pk=task.pk)) as archive:
            self.assertEqual(archive.tell(), 0)
            with ZipFile(archive) as output:
                records = list(serializers.deserialize(
                    'xml', output.read('data.xml').decode()
                ))
                self.assertEqual(
                    [(record.object._meta.label_lower, record.object.pk) for record in records],
                    [
                        ('attestation.ratingscale', scale.pk),
                        ('attestation.ratingscaleitem', item.pk),
                        ('tasks.task', task.pk),
                        ('tasks.mediafile', media.pk),
                        ('checker.scriptchecker', checker.pk),
                        ('solutions.solution', solution.pk),
                        ('solutions.solutionfile', solution_file.pk),
                    ],
                )
                assert media.media_file.name is not None
                assert checker.shell_script.name is not None
                assert solution_file.file.name is not None
                self.assertEqual(output.read(media.media_file.name), b'export media')
                self.assertEqual(output.read(checker.shell_script.name), b'#!/bin/sh\nexit 0\n')
                with solution_file.file.open('rb') as source:
                    self.assertEqual(output.read(solution_file.file.name), source.read())

    def test_get_checkers_preserves_subclasses_and_execution_order(self) -> None:
        task = Task.objects.get(pk=1)
        later = TextChecker.objects.create(task=task, order=20, text='later')
        earlier = ScriptChecker.objects.create(task=task, order=10)
        other_task = Task.objects.create(
            title='Other task', publication_date=task.publication_date,
            submission_date=task.submission_date,
        )
        TextChecker.objects.create(task=other_task, order=0, text='unrelated')
        checkers = task.get_checkers()
        self.assertEqual(checkers, [earlier, later])
        self.assertIsInstance(checkers[0], ScriptChecker)
        self.assertIsInstance(checkers[1], TextChecker)


class TestTaskImport(TestCase):
    @staticmethod
    def archive(data: str) -> BytesIO:
        archive = BytesIO()
        with ZipFile(archive, 'w') as output:
            output.writestr('data.xml', data)
        archive.seek(0)
        return archive

    def test_import_rejects_unrelated_models(self) -> None:
        task = Task.objects.get(pk=1)
        task.model_solution = None
        data = serializers.serialize('xml', [task, *Tutorial.objects.all()])
        count = Task.objects.count()
        with self.assertRaises(ValidationError):
            Task.import_Tasks(self.archive(data), User.objects.get(username='trainer'))
        self.assertEqual(Task.objects.count(), count)

    def test_import_reuses_rating_scale_and_items(self) -> None:
        scale = RatingScale.objects.create(name='Import test scale')
        item = RatingScaleItem.objects.create(scale=scale, name='Pass', position=1)
        task = Task.objects.get(pk=1)
        task.model_solution = None
        task.final_grade_rating_scale = scale
        data = serializers.serialize('xml', [scale, item, task])
        Task.import_Tasks(
            self.archive(data), User.objects.get(username='trainer'), is_template=False
        )
        imported = Task.objects.exclude(pk=task.pk).get(title=task.title)
        self.assertEqual(imported.final_grade_rating_scale_id, scale.pk)
        self.assertEqual(imported.publication_date, task.publication_date)
        self.assertEqual(RatingScale.objects.filter(name=scale.name).count(), 1)
        self.assertEqual(scale.ratingscaleitem_set.count(), 1)

    def test_template_import_clears_rating_scale_and_defers_publication(self) -> None:
        task = Task.objects.get(pk=1)
        task.model_solution = None
        data = serializers.serialize('xml', [task])
        Task.import_Tasks(self.archive(data), User.objects.get(username='trainer'))
        imported = Task.objects.exclude(pk=task.pk).get(title=task.title)
        self.assertIsNone(imported.final_grade_rating_scale)
        self.assertEqual(imported.publication_date, datetime(9999, 12, 31))


class TestUserViews(TestCase):
    def setUp(self) -> None:
        self.client.login(username='user', password='demo')
        self.task: Task = Task.objects.all()[0]

    def tearDown(self) -> None:
        pass

    def test_get_task_list(self) -> None:
        response = self.client.get(reverse('task_list'))
        self.assertEqual(response.status_code, 200)

    def test_get_task_detail(self) -> None:
        response = self.client.get(reverse('task_detail', args=[self.task.id]))
        self.assertEqual(response.status_code, 200)

class TestStaffViews(TestCase):
    def setUp(self) -> None:
        self.client.login(username='trainer', password='demo')
        self.task: Task = Task.objects.all()[0]

    def tearDown(self) -> None:
        pass

    def test_get_task_import(self) -> None:
        response = self.client.get(reverse('admin:task_import'))
        self.assertEqual(response.status_code, 200)

    def test_post_task_import(self) -> None:
        path = join(dirname(dirname(dirname(__file__))), 'examples', 'Tasks', 'AMI', 'TaskExport.zip')
        with open(path, 'rb') as f:
            response = self.client.post(reverse('admin:task_import'), data={
                               'file': f,
                               'is_template': True,
                            }, follow=True)
        self.assertRedirectsToView(response, 'changelist_view')

    def test_get_model_solution(self) -> None:
        response = self.client.get(reverse('model_solution', args=[self.task.id]))
        self.assertEqual(response.status_code, 200)

    def test_post_model_solution(self) -> None:
        with open(join(dirname(dirname(dirname(__file__))), 'examples', 'Tasks', 'AMI', 'ModelSolution(flat).zip'), 'rb') as f:
            response = self.client.post(reverse('model_solution', args=[self.task.id]), data={
                                'solutionfile_set-INITIAL_FORMS': '0',
                                'solutionfile_set-TOTAL_FORMS': '3',
                                'solutionfile_set-0-file': f
                            })
        self.assertNotContains(response, 'error_list')

    def test_task_export(self) -> None:
        response = self.client.post(reverse('admin:tasks_task_changelist'), data={
                            '_selected_action': 1,
                            'action': 'export_tasks'
                        })
        self.assertEqual(response.status_code, 200)

    def test_task_run_all_checker(self) -> None:
        # needs to be expired first
        self.task.submission_date = datetime.now() - timedelta(hours=2)
        self.task.save()

        # TODO: Create checker for test task!
        response = self.client.post(reverse('admin:tasks_task_changelist'), data={
                            '_selected_action': self.task.pk,
                            'action': 'run_all_checkers'
                        }, follow=True)
        self.task.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.task.all_checker_finished)

    def test_task_run_all_checker_parallel(self) -> None:
        with self.settings(NUMBER_OF_TASKS_TO_BE_CHECKED_IN_PARALLEL=4):
            self.test_task_run_all_checker()
