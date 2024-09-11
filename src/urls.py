from django.urls import re_path, include
from django.views.generic.base import RedirectView
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.urls import reverse
import sys
import os

import django.contrib.admindocs.urls
import tasks.views
import attestation.views
import solutions.views
import utilities.views
import accounts.urls
import tinymce.urls

import taskstatistics.views

from django.contrib import admin

from django.contrib.staticfiles.storage import staticfiles_storage


favicon_view_static = RedirectView.as_view(url=settings.BASE_PATH+'static/favicon.ico', permanent=True)
favicon_view = RedirectView.as_view(url=staticfiles_storage.url('favicon.ico'), permanent=True)


urlpatterns = [
    #favicon.ico
    re_path('favicon.ico', favicon_view),
    re_path(r'^.*favicon\.ico$', favicon_view_static),


    # Index page
    re_path(r'^$', RedirectView.as_view(pattern_name='task_list', permanent=True), name="index"),

    # Admin
    re_path(r'^admin/tasks/task/(?P<task_id>\d+)/model_solution', tasks.views.model_solution, name="model_solution"),
    re_path(r'^admin/tasks/task/(?P<task_id>\d+)/final_solutions', tasks.views.download_final_solutions, name="download_final_solutions"),
    re_path(r'^admin/attestation/ratingscale/generate', attestation.views.generate_ratingscale, name="generate_ratingscale"),
    re_path(r'^admin/doc/', include(django.contrib.admindocs.urls)),
    re_path(r'^admin/', admin.site.urls),

    # Login and Registration
    re_path(r'^accounts/', include(accounts.urls)),

    # tinyMCE
    re_path(r'^tinymce/', include(tinymce.urls)),

    #Tasks
    re_path(r'^tasks/$', tasks.views.taskList, name = 'task_list'),
    re_path(r'^tasks/(?P<task_id>\d+)/$', tasks.views.taskDetail, name='task_detail'),

    #TasksStatistic
    re_path(r'^tasks/statistic$', taskstatistics.views.tasks_statistic, name='tasks_statistic'),
    re_path(r'^tasks/statistic/download$', taskstatistics.views.tasks_statistic_download, name='tasks_statistic_download'),

    # Solutions
    re_path(r'^solutions/(?P<solution_id>\d+)/$', solutions.views.solution_detail, name='solution_detail',kwargs={'full' : False}),
    re_path(r'^solutions/(?P<solution_id>\d+)/full/$', solutions.views.solution_detail, name='solution_detail_full', kwargs={'full': True}),
    re_path(r'^solutions/(?P<solution_id>\d+)/download$', solutions.views.solution_download, name='solution_download', kwargs={'include_checker_files' : False, 'include_artifacts' : False}),
    re_path(r'^solutions/(?P<solution_id>\d+)/download/artifacts/$', solutions.views.solution_download, name='solution_download_artifacts', kwargs={'include_checker_files' : False, 'include_artifacts' : True}),
    re_path(r'^solutions/(?P<solution_id>\d+)/download/full/$', solutions.views.solution_download, name='solution_download_full', kwargs={'include_checker_files' : True, 'include_artifacts' : True}),
    re_path(r'^solutions/(?P<solution_id>\d+)/run_checker$', solutions.views.solution_run_checker, name='solution_run_checker'),
    re_path(r'^tasks/(?P<task_id>\d+)/checkerresults/$', solutions.views.checker_result_list, name='checker_result_list'),
    re_path(r'^tasks/(?P<task_id>\d+)/solutiondownload$', solutions.views.solution_download_for_task, name='solution_download_for_task', kwargs={'include_checker_files' : False, 'include_artifacts' : False}),
    re_path(r'^tasks/(?P<task_id>\d+)/solutiondownload/artifacts/$', solutions.views.solution_download_for_task, name='solution_download_for_task_artifacts', kwargs={'include_checker_files' : False, 'include_artifacts' : True}),
    re_path(r'^tasks/(?P<task_id>\d+)/solutiondownload/full/$', solutions.views.solution_download_for_task, name='solution_download_for_task_full', kwargs={'include_checker_files' : True, 'include_artifacts' : True}),
    re_path(r'^tasks/(?P<task_id>\d+)/solutionupload/$', solutions.views.solution_list, name='solution_list'),
    re_path(r'^tasks/(?P<task_id>\d+)/solutionupload/user/(?P<user_id>\d+)$', solutions.views.solution_list, name='solution_list'),
    re_path(r'^tasks/(?P<task_id>\d+)/solutionupload/test/$', solutions.views.test_upload, name='upload_test_solution'),
    re_path(r'^tasks/(?P<task_id>\d+)/solutionupload/test/student/$', solutions.views.test_upload_student, name='upload_test_solution_student'),

    re_path(r'^tasks/(?P<task_id>\d+)/jplag$', solutions.views.jplag, name='solution_jplag'),

    #Attestation
    re_path(r'^tasks/(?P<task_id>\d+)/attestation/statistics$', attestation.views.statistics, name='statistics'),
    re_path(r'^tasks/(?P<task_id>\d+)/attestation/$', attestation.views.attestation_list, name='attestation_list'),
    re_path(r'^tasks/(?P<task_id>\d+)/attestation/new$', attestation.views.new_attestation_for_task, name='new_attestation_for_task'),
    re_path(r'^solutions/(?P<solution_id>\d+)/attestation/new$', attestation.views.new_attestation_for_solution, name='new_attestation_for_solution', kwargs={'force_create' : False}),
    re_path(r'^solutions/(?P<solution_id>\d+)/attestation/new/(?P<force_create>force_create)$', attestation.views.new_attestation_for_solution, name='new_attestation_for_solution'),
    re_path(r'^attestation/(?P<attestation_id>\d+)/edit$', attestation.views.edit_attestation, name='edit_attestation'),
    re_path(r'^attestation/(?P<attestation_id>\d+)/withdraw$', attestation.views.withdraw_attestation, name='withdraw_attestation'),
    re_path(r'^attestation/(?P<attestation_id>\d+)/run_checker', attestation.views.attestation_run_checker, name='attestation_run_checker'),
    re_path(r'^attestation/(?P<attestation_id>\d+)$', attestation.views.view_attestation, name='view_attestation'),
    re_path(r'^attestation/rating_overview$', attestation.views.rating_overview, name='rating_overview'),
    re_path(r'^attestation/rating_export.csv$', attestation.views.rating_export, name='rating_export'),

    re_path(r'^tutorial/$', attestation.views.tutorial_overview, name='tutorial_overview'),
    re_path(r'^tutorial/(?P<tutorial_id>\d+)$', attestation.views.tutorial_overview, name='tutorial_overview'),

    # Uploaded media
    re_path(r'^upload/(?P<path>SolutionArchive/Task_\d+/User_.*/Solution_(?P<solution_id>\d+)/.*)$', utilities.views.serve_solution_file),
    re_path(r'^upload/(?P<path>TaskMediaFiles/Task_(?P<task_id>\d+)/.*)$', utilities.views.serve_media_file),
    re_path(r'^upload/(?P<path>TaskHtmlInjectorFiles.*)$', utilities.views.serve_staff_only),
    re_path(r'^upload/(?P<path>jplag.*)$', utilities.views.serve_staff_only, name='jplag_download'),
    re_path(r'^upload/(?P<path>CheckerFiles.*)$', utilities.views.serve_staff_only),
    re_path(r'^upload/(?P<path>.*)$', utilities.views.serve_access_denied),
]

if settings.DEBUG:
    import debug_toolbar
    urlpatterns += [
        re_path(r'^__debug__/', include(debug_toolbar.urls)),
    ]
