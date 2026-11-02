from django.contrib import admin
from django.db import models
from django.http import HttpRequest as _HttpRequest, HttpResponse as _HttpResponse
from django.urls import URLPattern as _URLPattern, reverse
from django.utils.html import format_html
from django.utils.safestring import SafeString as _SafeString
import typing as _typing

from tasks.models import Task, MediaFile, HtmlInjector, SubmissionBlacklistEntry, DeadlineExtension
from solutions.models import Solution
from attestation.admin import RatingAdminInline
from accounts.authentication import require_user

import tasks.views

from checker.admin import CheckerInline
from timeit import default_timer as timer

admin.autodiscover()

class MediaInline(
    admin.StackedInline[MediaFile, Task] if _typing.TYPE_CHECKING else admin.StackedInline
):
    model: type[MediaFile] = MediaFile
    extra = 0

class HtmlInjectorInline(
    admin.StackedInline[HtmlInjector, Task] if _typing.TYPE_CHECKING else admin.StackedInline
):
    model: type[HtmlInjector] = HtmlInjector
    extra = 0

class SubmissionBlacklistInline(
    admin.TabularInline[SubmissionBlacklistEntry, Task]
    if _typing.TYPE_CHECKING
    else admin.TabularInline
):
    model: type[SubmissionBlacklistEntry] = SubmissionBlacklistEntry
    verbose_name_plural = "Submission Blacklist Entries"
    extra = 0

class DeadlineExtensionInline(
    admin.TabularInline[DeadlineExtension, Task]
    if _typing.TYPE_CHECKING
    else admin.TabularInline
):
    model: type[DeadlineExtension] = DeadlineExtension
    extra = 0

class TaskAdmin(admin.ModelAdmin[Task] if _typing.TYPE_CHECKING else admin.ModelAdmin):
    model: type[Task] = Task
    readonly_fields = ('useful_links',)
    fieldsets = (
        (None, {
            'fields': (
                            'title',
                            ('publication_date', 'submission_date', 'exam'),
                            'description',
                            'max_file_size',
                            ('submission_free_uploads', 'submission_waitdelta', 'submission_maxpossible'),
                            'final_grade_rating_scale',
                            'only_trainers_publish',
                            'warning_threshold',
                            'useful_links',
                            'custom_id'
                        )
        }),
    )
    list_display = ('title', 'attestations_url', 'testupload_url', 'publication_date', 'submission_date', 'all_checker_finished')
    list_filter = ['publication_date']
    search_fields = ['title']
    date_hierarchy = 'publication_date'
    save_on_top = True

    # The registry contains different checker model specializations.
    inlines = (
        SubmissionBlacklistInline, DeadlineExtensionInline, MediaInline, HtmlInjectorInline,
        *_typing.cast("list[type[admin.StackedInline[_typing.Any, Task]]]", CheckerInline.__subclasses__()),
        RatingAdminInline,
    )
    actions = ['export_tasks', 'run_all_checkers', 'run_all_checkers_on_finals', 'run_all_checkers_on_latest_only_failed', 'check_unchecked_final_solutions', 'delete_attestations', 'unset_all_checker_finished', 'run_all_uploadtime_checkers_on_all']

    class Media:
        js = (
                'frameworks/jquery/jquery.js',
                'frameworks/jquery/jquery-ui.js',
                'frameworks/jquery/jquery.tinysort.js',
                'script/checker-sort.js',
        )


    def export_tasks(
        self, request: _HttpRequest, queryset: models.QuerySet[Task, Task]
    ) -> _HttpResponse:
        """ Export Task action """
        from django.http import HttpResponse
        response = HttpResponse(Task.export_Tasks(queryset).read(), content_type="application/zip")
        response['Content-Disposition'] = 'attachment; filename=TaskExport.zip'
        return response


    @admin.action(description="check only finals (Admin)")
    def run_all_checkers_on_finals(
        self, request: _HttpRequest, queryset: models.QuerySet[Task, Task]
    ) -> None:
        """ Rerun all checker on final solutions including "not always" action """
        start = timer()
        count = 0
        for task in queryset:
            count += task.check_all_final_solutions()
        end = timer()
        self.message_user(request, "%d final solutions were successfully checked (%d seconds elapsed)." % (count, end-start))

    @admin.action(description="recheck only latest failed (Admin)")
    def run_all_checkers_on_latest_only_failed(
        self, request: _HttpRequest, queryset: models.QuerySet[Task, Task]
    ) -> None:
        """ Rerun all checker on latest of only failed solutions including "not always" action """
        start = timer()
        count = 0
        for task in queryset:
            count += task.check_all_latest_only_failed_solutions()
        end = timer()
        self.message_user(request, "%d users with only failed solutions were checked (%d seconds elapsed)." % (count, end-start))


    @admin.action(description="run all checkers (Trainer)")
    def run_all_checkers(
        self, request: _HttpRequest, queryset: models.QuerySet[Task, Task]
    ) -> None:
        """ Rerun all checker including "not always" action for students with final or latest of only failed solutions """
        self.run_all_checkers_on_finals(request, queryset)
        self.run_all_checkers_on_latest_only_failed(request, queryset)

    @admin.action(description="delete attestations (Admin)")
    def delete_attestations(
        self, request: _HttpRequest, queryset: models.QuerySet[Task, Task]
    ) -> None:
        """ delete given attestations for task solutions """
        from attestation.models import Attestation
        start = timer()
        count = 0
        tcount = 0
        for task in queryset:
                        solution_set = Solution.objects.filter(task=task.id)
                        for sol in solution_set :
                                for a in Attestation.objects.filter(solution=sol):
                                        a.delete()
                                        count += 1
                        tcount += 1
        end = timer()
        self.message_user(request, "Deleted %d Attestations over %d Tasks: LoopTimer: %d " %(count, tcount, end-start),"warning")

    @admin.action(description="recheck all submissions with uploadtime checker (Admin)")
    def run_all_uploadtime_checkers_on_all(
        self, request: _HttpRequest, queryset: models.QuerySet[Task, Task]
    ) -> None:
        """ Rerun on all solutions all checkers which are running at uploadtime """
        request.user = require_user(request)
        from checker.basemodels import check_multiple, check_solution
        from accounts.models import User
        from django.template import loader
        from django.contrib.sites.requests import RequestSite
        from django.conf import settings
        from django.core.mail import send_mail
        from django.utils.translation import gettext_lazy
        myRequestUser = User.objects.filter(id=request.user.id)
        allstart = timer()
        task_set = queryset
        for task in task_set:
            start = timer()
             #solutions = Solution.objects.filter(task=task.id).order_by('author', 'number')
            solution_set = task.solution_set.order_by('author','number')

            old_final_solution_set =  solution_set.filter(final=True)
            users_with_old_final_solution = list(set(old_final_solution_set.values('author').values_list('author',flat = True)))

            for solution in old_final_solution_set:
                solution.final = False
                solution.accepted = False
                solution.save()

            #TODO: some how inform user how long time they must wait until this method will be finish.
            #print("rerun checkers ... wait much time ...")
            #this takes many time !!!!
            if  solution_set.count() > 1 :
                check_multiple(solution_set,False)  # just run upload-time_checkers  ... should we ignore Testuploads?
            elif  solution_set.count() == 1 :
                for solution in solution_set :
                    check_solution(solution,False)

            new_accepted_solution_set = Solution.objects.filter(task=task.id , accepted=True , testupload=False ).order_by('author', 'number')
            users_with_accepted_solutions = list(set(
                                                         new_accepted_solution_set.values('author').values_list('author', flat=True)
                                                        ))


            for userid in users_with_accepted_solutions :
                new_final_solution = new_accepted_solution_set.filter(author = userid).latest('number')
                new_final_solution.final = True
                new_final_solution.save()


            new_final_solution_set =  new_accepted_solution_set.filter(final=True)
            users_with_final_solution =  list(set(new_final_solution_set.values('author').values_list('author',flat = True)))

            users_missing_in_new_final_solution = list(set(users_with_old_final_solution) - set(users_with_final_solution))
            missing_users_in_new_final_solution_set = task.solution_set.filter(author__in=users_missing_in_new_final_solution).order_by('author','number')

            for userid in users_missing_in_new_final_solution :
                latestfailed_user_solution = missing_users_in_new_final_solution_set.filter(author=userid).latest('number')
                # Send final solution lost email to current RequestUser tutor/trainer/superuser
                t = loader.get_template('solutions/submission_final_lost_email.html')
                c = {
                                        'protocol': request.is_secure() and "https" or "http",
                                        'domain': RequestSite(request).domain,
                                        'site_name': settings.SITE_NAME,
                                        'solution': latestfailed_user_solution,
                                        'request_user': myRequestUser,
                }
                if request.user.email and latestfailed_user_solution.author.email:
                    send_mail(gettext_lazy("[%s] lost final submission confirmation") % settings.SITE_NAME, t.render(c), None, [request.user.email, latestfailed_user_solution.author.email])
                elif request.user.email and not latestfailed_user_solution.author.email:
                    send_mail(gettext_lazy("[%s] lost final submission confirmation") % settings.SITE_NAME, t.render(c), None, [request.user.email])
                elif not request.user.email and latestfailed_user_solution.author.email:
                    send_mail(gettext_lazy("%s lost final submission confirmation") % settings.SITE_NAME, t.render(c), None, [latestfailed_user_solution.author.email])
            end = timer()
            self.message_user(request, "Task %s : Checked %d authors lost their finals: LoopTimer: %d seconds elapsed "%(task.title, len(users_missing_in_new_final_solution),(end-start)),"warning")
        allend = timer()
        self.message_user(request, "%d Tasks rechecked : LoopTimer: %d seconds elapsed" % (task_set.count(),allend-allstart))


    @admin.action(description="Run checkers for unchecked final solutions (Admin)")
    def check_unchecked_final_solutions(
        self, request: _HttpRequest, queryset: models.QuerySet[Task, Task]
    ) -> None:
        """ Run all checkers on solutions where all_checker_finished is unset and which were submitted through a deadline extension that has expired """
        start = timer()
        count = 0
        for task in queryset:
            count += task.check_unchecked_final_solutions()
        end = timer()
        self.message_user(request, "%d final solutions were successfully checked (%d seconds elapsed)." % (count, end-start))


    @admin.action(description="unset all checker finished (Admin)")
    def unset_all_checker_finished(
        self, request: _HttpRequest, queryset: models.QuerySet[Task, Task]
    ) -> None:
        """ Unset task attribute: all_checker_finished """
        start = timer()
        count = 0
        for task in queryset:
            task.all_checker_finished = False
            task.save()
            count += 1
        end = timer()
        self.message_user(request, "State of attribute \"all_checker_finished\" at %d Tasks resetted to \"FALSE\": LoopTimer: %d " % (count, end-start),"warning")



    def get_urls(self) -> list[_URLPattern]:
        """ Add URL to task import """
        urls = super(TaskAdmin, self).get_urls()
        from django.urls import re_path
        my_urls = [re_path(r'^import/$', tasks.views.import_tasks, name='task_import')]
        return my_urls + urls

    @admin.display(description='Attestations')
    def attestations_url(self, task: Task) -> _SafeString:
        return format_html ('<a href="{0}">Attestations (User site)</a>',
                            reverse('attestation_list', kwargs={'task_id': task.id}))

    @admin.display(description='Test Submission')
    def testupload_url(self, task: Task) -> _SafeString:
        return format_html ('<a href="{0}">Test Submission</a>',
                            reverse('upload_test_solution', kwargs={'task_id': task.id}))

    def useful_links(self, instance: Task) -> _SafeString | str:
        if instance.id:
            return format_html (
                '<a href="{0}">Attestations (including for-user-submission)</a> • ' +
                '<a href="{1}">Test upload</a>',
                reverse('attestation_list', kwargs={'task_id': instance.id}),
                reverse('upload_test_solution', kwargs={'task_id': instance.id})
                )
        else:
            return ""


admin.site.register(Task, TaskAdmin)
