from django.contrib.admin.sites import AdminSite
from django.test import TestCase
from django.urls import reverse

from accounts.admin import UserAdmin
from accounts.models import User

# Some of our users have non-ASCII based names, therefor we create such a user, and testing the admin interface


class ModelUserAdminTests(TestCase):
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

    def setUp(self) -> None:
        self.site: AdminSite = AdminSite()
        self.client.login(username="trainer", password="demo")

    def test_UserAdmin_str(self) -> None:
        ua = UserAdmin(User, self.site)
        self.assertEqual(str(ua), "accounts.UserAdmin")

    def test_UserAdminView_url_exists_at_desired_location(self) -> None:
        response = self.client.get("/admin/accounts/user/")
        self.assertEqual(
            response.status_code,
            200,
            msg=f"Admin site : users user : Status was {response.status_code} != 200 : while forward lookup via URL",
        )

    def test_view_url_accessible_by_name(self) -> None:
        url = reverse("admin:accounts_user_changelist")
        response = self.client.get(url)
        self.assertEqual(
            response.status_code,
            200,
            msg=f"Admin site : users user : Status was {response.status_code} != 200 : while reverse lookup from function name",
        )

    def test_view_uses_correct_template(self) -> None:
        app_label = "accounts"
        model_name = "user"
        response = self.client.get(reverse(f"admin:{app_label}_{model_name}_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "admin/accounts/user/change_list.html")

    def test_UserAdmin_ListView_shows_Umlauts(self) -> None:
        all_users = list(User.objects.values())
        self.assertEqual(all_users[-1]["username"], "umlautUser")
        self.assertEqual(all_users[-1]["last_name"], "öäü")
        self.assertEqual(all_users[-1]["last_name"].encode("utf-8"), b"\xc3\xb6\xc3\xa4\xc3\xbc")
        app_label = "accounts"
        model_name = "user"
        response = self.client.get(reverse(f"admin:{app_label}_{model_name}_changelist"))
        self.assertNotIn(
            b"Internal Server Error", response.content, msg='Admin site : users user : shows "Internal Server Error"'
        )
        self.assertIn(
            "öäü".encode(), response.content, msg="Admin site : users user : do not show user with german umlauts"
        )

    def test_UserAdmin_ChangeView_shows_Umlauts(self) -> None:
        all_users = list(User.objects.order_by("id").values())
        self.assertEqual(all_users[-1]["username"], "umlautUser")
        self.assertEqual(all_users[-1]["last_name"], "öäü")
        self.assertEqual(all_users[-1]["last_name"].encode("utf-8"), b"\xc3\xb6\xc3\xa4\xc3\xbc")
        app_label = "accounts"
        model_name = "user"
        response = self.client.get("/admin/{}/{}/{}/change/".format(app_label, model_name, all_users[-1]["id"]))
        self.assertEqual(
            response.status_code,
            200,
            msg=f"Admin site : users user : Status was {response.status_code} != 200 : while forward lookup via URL",
        )
        self.assertNotIn(
            b"Internal Server Error",
            response.content,
            msg='Admin site : users user : change : shows "Internal Server Error"',
        )
        self.assertIn(
            "öäü".encode(),
            response.content,
            msg="Admin site : users user : change : do not show user with german umlauts",
        )
