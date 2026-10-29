from django.test import TestCase

# Create your tests here.

from django.urls import resolve


from django.http import HttpRequest, HttpResponse
from django.template.loader import render_to_string

from django.db import connection
from django.db.backends.base.introspection import FieldInfo

from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware

from taskstatistics.models import TasksStatistic
from taskstatistics.views import tasks_statistic
from taskstatistics.views import prepare_statistic_data
from taskstatistics.views import prepare_graphic_list
from taskstatistics.views import tasks_statistic_download

from tasks.models import Task

from collections import OrderedDict
from unittest.mock import Mock, patch
import base64
import csv
import io
from django.test import SimpleTestCase
from taskstatistics.views import StatisticRow, UserUploads, boxblot_to_graphic_list


class TestStatisticsBoundary(SimpleTestCase):
    @staticmethod
    def row() -> StatisticRow:
        row: StatisticRow = OrderedDict(
            (field.attname, 0) for field in TasksStatistic._meta.fields
        )
        row['task_id'] = 42
        row['title'] = 'A task'
        return row

    def test_empty_graphics_and_real_png_without_pyplot_state(self) -> None:
        from matplotlib import pyplot
        figures = pyplot.get_fignums()
        self.assertEqual(prepare_graphic_list(None), [])
        self.assertEqual(prepare_graphic_list([]), [])
        graphics = prepare_graphic_list([self.row()])
        self.assertEqual(len(graphics), 1)
        self.assertTrue(base64.b64decode(graphics[0]).startswith(b'\x89PNG\r\n\x1a\n'))
        self.assertEqual(pyplot.get_fignums(), figures)

    @patch('taskstatistics.views.FigureCanvasAgg')
    @patch('taskstatistics.views.Figure')
    def test_box_categories_and_personal_positions_are_correct(self, figure: Mock, canvas: Mock) -> None:
        axes = figure.return_value.subplots.return_value
        axes.bxp.return_value = {'medians': [Mock()], 'means': [Mock()], 'fliers': [Mock()]}
        for status in ('postpassed', 'postfailed', 'prefailed'):
            with self.subTest(status=status):
                row = self.row()
                row['med_upl_til_final_pass'] = 3
                row['lo_quart_upl_final_fail'] = 2
                row['up_whisker_upl_only_failed'] = 9
                uploads: UserUploads = {'task_id': [42], 'status': [], 'uploads': [7]}
                if status == 'postpassed':
                    uploads['status'] = ['postpassed']
                elif status == 'postfailed':
                    uploads['status'] = ['postfailed']
                else:
                    uploads['status'] = ['prefailed']
                graphics: list[str] = []
                self.assertIs(boxblot_to_graphic_list(graphics, row, uploads), graphics)
                boxes = axes.bxp.call_args.args[0]
                self.assertEqual(boxes[0]['med'], 3)
                self.assertEqual(boxes[1]['q1'], 2)
                self.assertEqual(boxes[2]['whishi'], 9)
                selected = ['postpassed', 'postfailed', 'prefailed'].index(status)
                self.assertEqual([box['fliers'] for box in boxes], [
                    [7] if index == selected else [] for index in range(3)
                ])
                self.assertEqual(axes.legend.call_args.args[1], ['median', 'mean', 'your position'])
                canvas.assert_called()

    def test_invalid_plot_inputs_raise_explicit_errors(self) -> None:
        with self.assertRaises(TypeError):
            boxblot_to_graphic_list()
        with self.assertRaisesRegex(ValueError, 'different task'):
            boxblot_to_graphic_list([], self.row(), {'task_id': [1], 'status': ['prefailed'], 'uploads': [1]})
        with self.assertRaisesRegex(ValueError, 'must contain'):
            boxblot_to_graphic_list([], self.row(), {'task_id': [], 'status': [], 'uploads': []})
        row = self.row()
        row['uploads_accepted'] = 'invalid'
        with self.assertRaisesRegex(TypeError, 'numeric'):
            boxblot_to_graphic_list([], row)

    @patch('taskstatistics.views.prepare_statistic_data')
    def test_csv_preserves_column_order_float_columns_and_quoting(self, prepare: Mock) -> None:
        first: StatisticRow = OrderedDict([('id', 1), ('title', 'Gr\u00f6\u00dfe, "quoted"\nname'), ('average', 0)])
        second: StatisticRow = OrderedDict([('id', 2), ('title', 'B'), ('average', 1.5)])
        prepare.return_value = ([first, second], [])
        response = tasks_statistic_download(HttpRequest())
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertEqual(response['Content-Disposition'], 'attachment; filename="TaskStatistic.csv"')
        self.assertEqual(list(csv.reader(io.StringIO(response.content.decode()))), [
            ['id', 'title', 'average'], ['1', 'Gr\u00f6\u00dfe, "quoted"\nname', '0.0'], ['2', 'B', '1.5'],
        ])
        self.assertNotIn(b'\r\n', response.content)

    @patch('taskstatistics.views.getQuerySet')
    def test_database_nulls_become_zero_and_field_order_is_preserved(self, query: Mock) -> None:
        query.return_value = [dict(self.row(), avg_upl_until_final_pass=None)]
        with patch('taskstatistics.views.Task.objects.filter') as tasks:
            data, _ = prepare_statistic_data()
        self.assertEqual(data[0]['avg_upl_until_final_pass'], 0)
        self.assertEqual(list(data[0]), [field.attname for field in TasksStatistic._meta.fields])
        self.assertEqual(query.call_count, 1)
        tasks.assert_called_once()


class TasksStatisticTest(TestCase):

    def get_table_description(self, table: str) -> list[FieldInfo]:
        with connection.cursor() as cursor:
           return connection.introspection.get_table_description(cursor, table)

    def assertTableOrViewExists(self, tableOrView: str) -> None:
        with connection.cursor() as cursor:
           self.assertIn(tableOrView, connection.introspection.table_names(cursor, include_views=True))

    def test_DBview_tasksstatistic_isavailable(self) -> None:
        #check if view with correct name as been created in database
        self.assertTableOrViewExists("dbview_tasksstatistic")
        #heuristic check about correct created view, that is checking if database view has a attribute with needed field name
        self.assertIn("up_whisker_upl_until_final_pass", str(self.get_table_description("dbview_tasksstatistic")))

    def test_Model_TasksStatistic_isavailable(self) -> None:
        v=TasksStatistic.objects.values()
        self.assertIn("QuerySet", str(v))

    def test_Foreignkey_Connection_works(self) -> None:
        ts = TasksStatistic.objects.get(pk=1)
        self.assertIsInstance(ts,TasksStatistic)
        t = ts.task
        self.assertIsInstance(t,Task)


    def test_Model_TasksStatistic_isUnmanaged(self) -> None:
        self.assertFalse(TasksStatistic._meta.managed, "TasksStatistic should be a not managed class since it use a database view.")

    def test_tasksstatistic_url_resolves_to_tasksstatistic_view(self) -> None:
        found = resolve('/tasks/statistic')
        self.assertEqual(found.func, tasks_statistic, "Update urls.py to make url resolveable.")

    def test_taskstatistic_returns_correct_html_title(self) -> None:
        request = HttpRequest()

        """Annotate a request object with a session"""
        middleware = SessionMiddleware(get_response=lambda request: HttpResponse())
        middleware.process_request(request)
        request.session.save()

        """Annotate a request object with a messages"""
        middleware = MessageMiddleware(get_response=lambda request: HttpResponse())
        middleware.process_request(request)
        request.session.save()


        response = tasks_statistic(request)
        self.assertContains(text="<!DOCTYPE html",response=response,html=False)
        self.assertContains(text="<html",response=response,html=False)
        self.assertTrue(response.content.strip().startswith(b'<!DOCTYPE html'), "No HTML Doctype has been defined at beginning.")
        self.assertIn(b'<h1>Task statistics</h1>', response.content, "Website has wrong h1 element, maybe its content is wrong, too.")
        self.assertTrue(response.content.strip().endswith(b'</html>'), "No valid HTML has been returned.")

    def remove_csrf_tag(self, text: str) -> str:
        """Remove csrf tag from TEXT"""
        import re
        return re.sub(r'<[^>]*csrfmiddlewaretoken[^>]*>', '', text)


    def test_taskstatistic_returns_correct_html(self) -> None:
        request = HttpRequest()

        """Annotate a request object with a session"""
        middleware = SessionMiddleware(get_response=lambda request: HttpResponse())
        middleware.process_request(request)
        request.session.save()

        """Annotate a request object with a messages"""
        middleware = MessageMiddleware(get_response=lambda request: HttpResponse())
        middleware.process_request(request)
        request.session.save()

        response = tasks_statistic(request)
        data_, _ = prepare_statistic_data()
        graphic_list_ = prepare_graphic_list(data_)
        context = {'data':data_ , 'graphics':graphic_list_ }
        expected_html = render_to_string('taskstatistics/overview.html',context,request=request)
        self.assertEqual(self.remove_csrf_tag(response.content.strip().decode('utf-8')),self.remove_csrf_tag(expected_html.strip()))

    def test_taskstatistic_uses_Template(self) -> None:
        self.client.login(username='trainer', password='demo')
        response = self.client.get('/tasks/statistic')
        self.assertTemplateUsed(response,'taskstatistics/overview.html')
        self.assertEqual(response.status_code, 200) # should work
        self.client.logout()

    def test_taskstatistic_returns_html_table_for_trainers(self) -> None:
        data_, _ = prepare_statistic_data()
        context = {'data':data_ }
        #print(context)
        html_output = render_to_string('taskstatistics/overview.html', context)
        #print(html_output)
        self.assertNotIn("<table" , html_output , "There shouldn't be a html table on statistic overview page for non trainers.")
        self.assertNotIn("median" , html_output )
        self.client.login(username='trainer', password='demo')
        responseC = self.client.get('/tasks/statistic')
        self.assertEqual(responseC.status_code, 200) # should work
        self.assertIn("<table".encode("utf-8"), responseC.content, "There should be a html table on statistic overview page for trainers.")
        self.client.logout()

    def test_column_order_as_basis_for_html_table(self) -> None:
        data_, _ = prepare_statistic_data()
        self.assertIs(type(data_), list)
        for f in data_:
            self.assertIs(type(f), OrderedDict)

    def test_tasksstatistic_url_resolves_to_tasksstatistic_download(self) -> None:
        found = resolve('/tasks/statistic/download')
        self.assertEqual(found.func, tasks_statistic_download, "Update urls.py to make url resolveable.")

    def test_taskstatistic_csv_download(self) -> None:
        data_, _ = prepare_statistic_data()
        context = {'data':data_ }
        html_output = render_to_string('taskstatistics/overview.html', context)
        self.assertNotIn("<a href=/tasks/statistic/download", html_output, "There should not be a download link on statistic overview page, without login as tutor, trainer or superuser")
        self.client.login(username='trainer', password='demo')
        responseC = self.client.get('/tasks/statistic')
        self.assertEqual(responseC.status_code, 200) # should work
        self.assertIn("<a href=/tasks/statistic/download".encode("utf-8"), responseC.content, "There should be a download link on statistic overview page")
        self.client.logout() # without login a statistic view should possible, if there are data.
        responseC = self.client.get('/tasks/statistic/download')
        self.assertEqual(responseC.status_code, 200) # should work
        request = HttpRequest()

        """Annotate a request object with a session"""
        middleware = SessionMiddleware(get_response=lambda request: HttpResponse())
        middleware.process_request(request)
        request.session.save()

        """Annotate a request object with a messages"""
        middleware = MessageMiddleware(get_response=lambda request: HttpResponse())
        middleware.process_request(request)
        request.session.save()

        response = tasks_statistic_download(request)

        self.assertEqual(self.remove_csrf_tag(responseC.content.strip().decode("utf-8")), self.remove_csrf_tag(response.content.strip().decode("utf-8")))
        self.client.logout()

    # ToDo: Think of integrating Whisker-Boxplot-Data for given Task on statistics View of attestation.
    # URL is like  tasks/1363/attestation/statistics
    # self.fail('Finish the test')
