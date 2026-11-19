from django.contrib.admin.sites import AdminSite
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from tasks.models import Task


class ModelTaskAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        # ö , ä , ü = 0xC3 0xB6 , 0xC3 0xA4 , 0xC3 0xBC : letters coded in UTF8
        cls.umlautStudent: User = User.objects.create_user(
            username="umlautUser",
            first_name="LastNameAsUTF8",
            last_name=(b"\xc3\xb6\xc3\xa4\xc3\xbc").decode("utf-8"),
            email="user@praktomat.local",
            password="demü",
            is_staff=False,
            is_superuser=False,
        )
        cls.umlautStudent.mat_number = 424242
        cls.umlautStudent.save()
        import datetime

        cls.umlautTask: Task = Task.objects.create(
            title="German Umlauts äöü",
            description="Fußball is soccer. German umlauts are äöü",
            publication_date=datetime.date.today(),
            submission_date=datetime.date.today(),
        )
        cls.umlautTask.save()

    def setUp(self) -> None:
        self.site: AdminSite = AdminSite()
        self.client.login(username="trainer", password="demo")

    def test_TaskAdmin_ListView_shows_Umlauts(self) -> None:
        all_tasks = list(Task.objects.order_by("id").values())
        self.assertEqual(all_tasks[-1]["title"], "German Umlauts äöü")
        self.assertEqual(all_tasks[-1]["description"], "Fußball is soccer. German umlauts are äöü")
        # ö , ä , ü = 0xC3 0xB6 , 0xC3 0xA4 , 0xC3 0xBC : letters coded in UTF8
        self.assertEqual(all_tasks[-1]["title"].encode("utf-8"), b"German Umlauts \xc3\xa4\xc3\xb6\xc3\xbc")
        app_label = "tasks"
        model_name = "task"
        response = self.client.get(reverse(f"admin:{app_label}_{model_name}_changelist"))
        self.assertNotIn(
            b"Internal Server Error", response.content, msg='Admin site : tasks task : shows "Internal Server Error"'
        )
        self.assertIn(
            "äöü".encode(),
            response.content,
            msg="Admin site : tasks task : do not show task with german umlauts in title",
        )

    def test_TaskAdmin_ChangeView_shows_Umlauts(self) -> None:
        all_tasks = list(Task.objects.order_by("id").values())
        self.assertEqual(all_tasks[-1]["title"], "German Umlauts äöü")
        self.assertEqual(all_tasks[-1]["description"], "Fußball is soccer. German umlauts are äöü")
        # ö , ä , ü = 0xC3 0xB6 , 0xC3 0xA4 , 0xC3 0xBC : Buchstaben als UTF8-codiert
        self.assertEqual(all_tasks[-1]["title"].encode("utf-8"), b"German Umlauts \xc3\xa4\xc3\xb6\xc3\xbc")
        app_label = "tasks"
        model_name = "task"
        response = self.client.get("/admin/{}/{}/{}/change/".format(app_label, model_name, all_tasks[-1]["id"]))
        self.assertEqual(
            response.status_code,
            200,
            msg=f"Admin site : tasks task : Status was {response.status_code} != 200 : while forward lookup via URL",
        )
        self.assertNotIn(
            b"Internal Server Error",
            response.content,
            msg='Admin site : tasks task : change : shows "Internal Server Error"',
        )
        self.assertIn(
            "äöü".encode(),
            response.content,
            msg="Admin site : tasks task : change : do not show task with german umlauts in title",
        )
