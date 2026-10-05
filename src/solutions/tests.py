from os.path import dirname, join
from datetime import datetime, timedelta
import difflib

from utilities.TestSuite import TestCase
from django.test.client import Client
from django.urls import reverse

from solutions.models import Solution
from solutions.templatetags.highlight import colorize_diff_table
from tasks.models import Task


class TestHighlightDiffTable(TestCase):
    """Tests for the rendering of annotated solution diffs."""

    def render(self, original, anotated, filename):
        differ = difflib.Differ()
        diff = "\n".join(l.strip("\n") for l in differ.compare(original.splitlines(0), anotated.splitlines(0)))
        return colorize_diff_table(diff, filename)

    def test_empty_diff(self):
        self.assertEqual(colorize_diff_table("", "Hello.java"), "")

    def test_line_numbers_match_the_number_of_code_lines(self):
        html = self.render("a = 1\nb = 2\n", "a = 1\nb = 3\nc = 4\n", "t.py")
        linenos = html.split('<td class="code">')[0]
        # one number per code line, the "? " hint lines of difflib do not count
        self.assertEqual(linenos.count('<span class="normal">'), 4)
        self.assertIn('<span class="normal">4</span>', linenos)
        self.assertNotIn('<span class="normal">5</span>', linenos)

    def test_syntax_highlighting_is_not_confused_by_the_diff_markers(self):
        html = self.render("// comment\n", "int x = 0;\n", "Hello.java")
        # the leading +/- must neither end up inside a token nor be highlighted
        self.assertIn('<span class="c1">// comment</span>', html)
        self.assertIn('<span class="kt">int</span>', html)
        self.assertNotIn('<span class="o">-</span>', html)
        self.assertNotIn('<span class="o">+</span>', html)

    def test_changed_lines_get_a_css_class(self):
        html = self.render("a = 1\n", "a = 1\nb = 2\n", "t.py")
        self.assertIn('<div class="changed added">', html)

    def test_changed_characters_get_a_css_class(self):
        html = self.render('s = "Hello"\n', 's = "Hello World"\n', "t.py")
        self.assertIn('<span class="addedChar"> World</span>', html)

    def test_html_entities_count_as_one_character(self):
        html = self.render("a = b & c;\n", "a = b && c;\n", "T.java")
        self.assertIn('<span class="addedChar">&amp;</span>', html)

    def test_unknown_file_type_is_escaped(self):
        html = self.render("a < b\n", "a > b\n", "unknown.filetype")
        self.assertIn("&lt;", html)
        self.assertNotIn("a < b", html)


class TestViews(TestCase):
    def setUp(self):
        self.client.login(username='user', password='demo')
        self.task = Task.objects.all()[0]

    def tearDown(self):
        pass

    def test_get_solution_list(self):
        response = self.client.get(reverse('solution_list', args=[self.task.id]))
        self.assertEqual(response.status_code, 200)

    def test_post_solution(self):
        path = join(dirname(dirname(dirname(__file__))), 'examples', 'Tasks', 'AMI', 'ModelSolution(flat).zip')
        with open(path, 'rb') as f:
            response = self.client.post(reverse('solution_list', args=[self.task.id]), data={
                                'solutionfile_set-INITIAL_FORMS': '0',
                                'solutionfile_set-TOTAL_FORMS': '3',
                                'solutionfile_set-0-file': f
                            }, follow=True)
        self.assertRedirectsToView(response, 'solution_detail')

    def test_post_solution_expired(self):
        self.task.submission_date = datetime.now() - timedelta(hours=3)
        self.task.save()

        path = join(dirname(dirname(dirname(__file__))), 'examples', 'Tasks', 'AMI', 'ModelSolution(flat).zip')
        with open(path, 'rb') as f:
            response = self.client.post(reverse('solution_list', args=[self.task.id]), data={
                                'solutionfile_set-INITIAL_FORMS': '0',
                                'solutionfile_set-TOTAL_FORMS': '3',
                                'solutionfile_set-0-file': f
                            }, follow=True)
        self.assertEqual(response.status_code, 403)

    def test_get_solution(self):
        response = self.client.get(reverse('solution_detail', args=[self.task.solution_set.all()[0].id]))
        self.assertEqual(response.status_code, 200)


def test_concurrently(times):
    """
    Add this decorator to small pieces of code that you want to test
    concurrently to make sure they don't raise exceptions when run at the
    same time.  E.g., some Django views that do a SELECT and then a subsequent
    INSERT might fail when the INSERT assumes that the data has not changed
    since the SELECT.
    """
    def test_concurrently_decorator(test_func):
        def wrapper(*args, **kwargs):
            exceptions = []
            import threading
            def call_test_func():
                try:
                    test_func(*args, **kwargs)
                except Exception as e:
                    exceptions.append(e)
                    raise
            threads = []
            for i in range(times):
                threads.append(threading.Thread(target=call_test_func))
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            if exceptions:
                raise Exception('test_concurrently intercepted %s exceptions: %s' % (len(exceptions), exceptions))
        return wrapper
    return test_concurrently_decorator

        # Use like this:
        # Transaction in djangos testcase results in an deadlock so use pythons
        #class MyTest(TestCase):
        #        def testRegistrationThreaded(self):
        #                url = reverse('toggle_registration')
        #                @test_concurrently(15)
        #                def toggle_registration():
        #                        # perform the code you want to test here; it must be thread-safe
        #                        # (e.g., each thread must have its own Django test client)
        #                        c = Client()
        #                        c.login(username='user@example.com', password='abc123')
        #                        response = c.get(url)
        #                toggle_registration()


#from unittest import TestCase as ConcurrentTestCase
#class ConcurentTest(ConcurrentTestCase):
        #""" Will probably result in an error as not all db connections will be closed on table destruction """
        #def setUp(self):
            #self.task = Task.objects.all()[0]

        #def tearDown(self):
            #pass

        #def test_post_solution_concurrently(self):
                #url = reverse('solution_list', args=[self.task.id])
                #@test_concurrently(20)
                #def run():
                        #f = open('/Users/halluzinativ/untitled.c','r')
                        #client = Client()
                        #client.login(username='user', password='demo')
                        #response = client.post(url, follow=True, data={
                                #u'solutionfile_set-INITIAL_FORMS': u'0',
                                #u'solutionfile_set-TOTAL_FORMS': u'3',
                                #u'solutionfile_set-0-file': f
                            #})
                        #self.failUnlessEqual(response.status_code, 200)
                #run()
