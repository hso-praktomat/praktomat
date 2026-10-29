from django.conf import settings   # for switching via ACCOUNT_CHANGE_POSSIBLE

from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.forms.models import modelformset_factory
from django.db.models import Count, QuerySet
from django.db import transaction
from django.contrib.auth.models import Group
from django.views.decorators.cache import cache_control
from django.http import HttpRequest, HttpResponse
from django.template import loader
from django import forms
import datetime
from decimal import Decimal
from collections.abc import Iterable, Iterator
from typing import TypedDict

from tasks.models import Task, HtmlInjector
from solutions.models import Solution
from checker.basemodels import check_solution
from attestation.models import Attestation, AnnotatedSolutionFile, RatingResult, RatingScale, RatingScaleItem
from attestation.forms import AnnotatedFileFormSet, RatingResultFormSet, AttestationForm, AttestationPreviewForm, PublishFinalGradeForm, GenerateRatingScaleForm, FinalGradeOptionForm
from accounts.models import User, Tutorial
from accounts.authentication import require_user
from accounts.views import access_denied
from configuration import get_settings


class _RatingSource(TypedDict):
    title: str
    desc: str
    ratings: QuerySet[RatingScaleItem]


class _RuntimePoint(TypedDict):
    date: datetime.datetime
    value: int


class _MedianPoint(TypedDict):
    date: datetime.datetime
    value: int | None


class _RuntimeSeries(TypedDict):
    checker: str
    runtimes: list[_RuntimePoint]
    medians: list[_MedianPoint]


class _TutorStats(TypedDict):
    tutor: User | None
    unattested: int
    final: int
    nonfinal: int
    attested: int
    total: int


_AttestationCell = tuple[Attestation | None, Solution | None]
_AttestationRow = tuple[User, list[_AttestationCell], Decimal, float]


@login_required
def statistics(request: HttpRequest, task_id: str) -> HttpResponse:
    request.user = require_user(request)
    task = get_object_or_404(Task, pk=task_id)

    if not (request.user.is_trainer or request.user.is_tutor or request.user.is_superuser):
        return access_denied(request)

    final_solutions = task.solution_set.filter(final=True)
    unfinal_solutions = task.solution_set.filter(final=False)
    user = User.objects.filter(groups=Group.objects.get(name='User'), is_active=True)

    tutorials = request.user.tutored_tutorials.all()
    if request.user.is_tutor:
        final_solutions = final_solutions.filter(author__tutorial__in = tutorials)
        unfinal_solutions = unfinal_solutions.filter(author__tutorial__in = tutorials)
        user = User.objects.filter(tutorial__in = tutorials)

    final_solution_count = final_solutions.count()
    user_count = user.count()

    submissions: list[int] = []
    submissions_final: list[int] = []
    accumulated = [0]
    creation_datetimes = list(unfinal_solutions.values_list('creation_date', flat=True))
    creation_datetimes_final = list(final_solutions.values_list('creation_date', flat=True))
    creation_dates = [created.date() for created in creation_datetimes]
    creation_dates_final = [created.date() for created in creation_datetimes_final]
    for date in daterange(task.publication_date.date(), min(task.submission_date.date(), datetime.date.today())):
        submissions.append(creation_dates.count(date))
        submissions_final.append(creation_dates_final.count(date))
        accumulated.append(accumulated[-1]+submissions_final[-1])
    acc_submissions = [count / user_count if user_count else 0.0 for count in accumulated[1:]]

    creation_times = [[(created.hour*3600+created.minute*60)*1000, created.weekday()] for created in creation_datetimes]
    creation_times_final = [[(created.hour*3600+created.minute*60)*1000, created.weekday()] for created in creation_datetimes_final]

    if request.user.is_trainer:
        attestations = Attestation.objects.filter(solution__task__id=task.id, final=True, published=False).aggregate(final=Count('id'))
        attestations.update( Attestation.objects.filter(solution__task__id=task.id, final=True, published=True).aggregate(published=Count('id')) )
    else: # Tutor
        attestations = Attestation.objects.filter(solution__task__id=task.id, final=True, published=False, author__tutored_tutorials__in = tutorials).aggregate(final=Count('id'))
        attestations.update( Attestation.objects.filter(solution__task__id=task.id, final=True, published=True, author__tutored_tutorials__in = tutorials).aggregate(published=Count('id')))

    attestations['all'] = final_solution_count


    scale = task.final_grade_rating_scale
    names = [item.name.strip() for item in scale.ratingscaleitem_set.all()] if scale is not None else []
    final_grade_rating_scale_items = "['" + "','".join(names) + "']" if names else "[]"

    rating_sources: list[_RatingSource] = []
    if request.user.is_trainer:
        # Each Tutorials ratings
        for t in Tutorial.objects.all():
            rating_sources.append({'title'   : "Final Grades for Students in Tutorial %s" % str(t),
                                'desc'    : "This chart shows the distribution of final grades for students from Tutorial %s. Plagiarism is excluded." % str(t),
                                'ratings' : RatingScaleItem.objects.filter(attestation__solution__task=task_id, attestation__solution__plagiarism=False, attestation__final=True, attestation__solution__author__tutorial = t)})
        for t in User.objects.filter(groups__name='Tutor'):
            rating_sources.append({'title'   : "Final Grades for Attestations created by %s" % str(t),
                                'desc'    : "This chart shows the distribution of final grades for Attestations created by %s. Plagiarism is excluded." % str(t),
                                'ratings' : RatingScaleItem.objects.filter(attestation__solution__task=task_id, attestation__solution__plagiarism=False, attestation__final=True, attestation__author__id = t.id)})
    else:
        # The Tutorials ratings
        rating_sources.append(        {'title'   : "Final grades (My Tutorials)",
                                    'desc'    : "This chart shows the distribution of final grades for students from any of your tutorials. Plagiarism is excluded.",
                                    'ratings' : RatingScaleItem.objects.filter(attestation__solution__task=task_id, attestation__solution__plagiarism=False, attestation__final=True, attestation__solution__author__tutorial__in = tutorials)})
        rating_sources.append(        {'title'   : "Final grades (My Attestations)",
                                    'desc'    : "This chart shows the distribution of final grades for your attestations. Plagiarism is excluded.",
                                    'ratings' : RatingScaleItem.objects.filter(attestation__solution__task=task_id, attestation__solution__plagiarism=False, attestation__final=True, attestation__author__id = request.user.id)})
    # Overall ratings
    rating_sources.append({'title'   : "Final grades (overall)",
                        'desc'    : "This chart shows the distribution of final grades for all students. Plagiarism is excluded.",
                        'ratings' : RatingScaleItem.objects.filter(attestation__solution__task=task_id, attestation__solution__plagiarism=False, attestation__final=True)})

    all_ratings = [
        {'title': source['title'], 'desc': source['desc'],
         'ratings': [list(rating) for rating in source['ratings'].annotate(Count('id')).values_list('position', 'id__count')]}
        for source in rating_sources
    ]

    has_runtimes = False
    runtimes: list[_RuntimeSeries] = []
    for checker_index, checker in enumerate(task.get_checkers()):
        checker_runtimes: list[_RuntimePoint] = []
        for result in checker.results.order_by('creation_date').filter(runtime__gt = 0):
            has_runtimes = True
            checker_runtimes.append({ 'date': result.creation_date, 'value': result.runtime})

        if checker_runtimes:
            first = checker_runtimes[0]
            last = checker_runtimes[-1]
            n = 20 # number of buckets
            buckets: list[list[int]] = [[] for _ in range(n)]
            span = last['date'] - first['date'] + datetime.timedelta(seconds=1)
            for point in checker_runtimes:
                bucket_index = timedelta_diff((point['date'] - first['date'])*n, span)
                buckets[bucket_index].append(point['value'])
            medians: list[_MedianPoint] = []
            for i in range(n):
                date = first['date'] + ((span//2)*(2*i+1) // n);
                if buckets[i]:
                    buckets[i].sort()
                    value = buckets[i][((len(buckets[i])+1)//2)-1]
                else:
                    value = None
                medians.append({'date': date, 'value': value});

            runtimes.append({
                             'checker': "%d: %s" % (checker_index, checker.title()),
                             'runtimes': checker_runtimes,
                             'medians': medians
            })

    return render(request, "attestation/statistics.html",
            {'task':                           task,
            'user_count':                      user_count,
            'solution_count':                  final_solution_count,
            'submissions':                     submissions,
            'submissions_final':               submissions_final,
            'creation_times':                  creation_times,
            'creation_times_final':            creation_times_final,
            'acc_submissions':                 acc_submissions,
            'attestations':                    attestations,
            'final_grade_rating_scale_items':  final_grade_rating_scale_items,
            'all_ratings':                     all_ratings,
            'runtimes':                        runtimes,
            'has_runtime_chart':               has_runtimes,
            })

def daterange(
    start_date: datetime.date, end_date: datetime.date
) -> Iterator[datetime.date]:
    for n in range((end_date - start_date).days + 1):
        yield start_date + datetime.timedelta(n)


def tutor_attestation_stats(
    task: Task, tutor: User | None
) -> _TutorStats:
    unattested = Solution.objects.filter(task=task, final=True, plagiarism=False, attestation=None, author__tutorial__tutors=tutor).count()
    final = Attestation.objects.filter(solution__task=task, final=True, author=tutor).count()
    nonfinal = Attestation.objects.filter(solution__task=task, final=False, author=tutor).count()
    return {'tutor': tutor, 'unattested': unattested, 'final': final, 'nonfinal': nonfinal,
            'attested': final + nonfinal, 'total': final + nonfinal + unattested}


@login_required
@cache_control(must_revalidate=True, no_cache=True, no_store=True, max_age=0) #reload the page from the server even if the user used the back button
def attestation_list(request: HttpRequest, task_id: str) -> HttpResponse:
    request.user = require_user(request)
    if not (request.user.is_tutor or request.user.is_trainer or request.user.is_superuser):
        return access_denied(request)

    task = Task.objects.get(pk=task_id)

    attestation_stats = []
    no_tutorial_stats: _TutorStats | dict[str, object] = {}
    if request.user.is_trainer:
        attestation_stats =  [ tutor_attestation_stats(task, tutor)
                                  for tutor in User.objects.filter(groups__name="Tutor")]

        no_tutorial_stats = tutor_attestation_stats(task, None)


    tutored_users = request.user.tutored_users()

    unattested_solutions = Solution.objects.filter(task = task, final=True, attestation = None, all_checker_finished = True)
    if request.user.is_tutor: # the trainer sees them all
        unattested_solutions = unattested_solutions.filter(author__tutorial__in = request.user.tutored_tutorials.all())
    # Only show solutions from users for which the task expired
    expired_unattested_solutions = [solution for solution in unattested_solutions if task.expired_for_user(solution.author)]

    all_attestations = Attestation.objects \
        .filter(solution__task = task, solution__final = True) \
        .order_by('-created') \
        .select_related('solution', 'solution__author', 'author')

    # Filter out attestations that have already been created for students which get a deadline extension
    invalid_attestation_ids = [attestation.id for attestation in all_attestations if not task.expired_for_user(attestation.solution.author)]
    all_attestations = all_attestations.exclude(id__in = invalid_attestation_ids)

    my_attestations = all_attestations \
        .filter(author = request.user) \

    all_attestations_for_my_tutorials = all_attestations \
        .filter(solution__author__tutorial__in = request.user.tutored_tutorials.all()) \

    attestations_by_others = all_attestations_for_my_tutorials \
        .exclude(author = request.user)

    # for the warning about solutions marked as plagiarism
    if request.user.is_trainer:
        # show all to trainer
        solutions_with_plagiarism = Solution.objects.filter(task = task, plagiarism = True)
    else:
        # show from my turials to tutors
        solutions_with_plagiarism = Solution.objects.filter(task = task, plagiarism = True, author__tutorial__in = request.user.tutored_tutorials.all())

    publishable_tutorial = all_attestations_for_my_tutorials.filter(final = True, published = False)

    publishable_all = all_attestations.filter(final=True, published=False)

    if request.method == "POST":
        if request.POST['what'] == 'tutorial':
            if not request.user.is_tutor:
                return access_denied(request)
            if task.only_trainers_publish:
                return access_denied(request)
            for attestation in publishable_tutorial:
                attestation.publish(request, request.user)
            return HttpResponseRedirect(reverse('attestation_list', args=[task_id]))

        if request.POST['what'] == 'all':
            if not request.user.is_trainer:
                return access_denied(request)
            for attestation in publishable_all:
                attestation.publish(request, request.user)
            return HttpResponseRedirect(reverse('attestation_list', args=[task_id]))

    show_author = not get_settings().anonymous_attestation or request.user.is_tutor or request.user.is_trainer

    data = {'task': task,
            'tutored_users': tutored_users,
            'solutions_with_plagiarism': solutions_with_plagiarism,
            'my_attestations': my_attestations,
            'attestations_by_others': attestations_by_others,
            'all_attestations': all_attestations if request.user.is_trainer else None,
            'unattested_solutions': expired_unattested_solutions,
            'publishable_tutorial': publishable_tutorial,
            'publishable_all': publishable_all if request.user.is_trainer else None,
            'show_author': show_author,
            'attestation_stats': attestation_stats,
            'no_tutorial_stats': no_tutorial_stats,}
    return render(request, "attestation/attestation_list.html", data)


@login_required
def new_attestation_for_task(
    request: HttpRequest, task_id: str
) -> HttpResponse:
    """ Start an attestation on a restrained random set of my tutored users """
    request.user = require_user(request)
    if not (request.user.is_tutor or request.user.is_trainer or request.user.is_superuser):
        return access_denied(request)

    # fetch a solution of a user I have already attested in the past.
    users_i_have_attestated = User.objects.filter(solution__attestation__author = request.user)
    all_available_solutions = Solution.objects.filter(task__id = task_id, final=True, author__tutorial__in = request.user.tutored_tutorials.all(), attestation = None)
    if (not all_available_solutions):
        # if an other tutor just grabbed the last solution just go back to the list
        return HttpResponseRedirect(reverse('attestation_list', args=[task_id]))
    solutions = all_available_solutions.filter(author__in = users_i_have_attestated)
    if (solutions):
        solution = solutions[0]
    else:
        solution = all_available_solutions[0]

    return new_attestation_for_solution(request, solution.id)


@login_required
@transaction.atomic
def new_attestation_for_solution(
    request: HttpRequest,
    solution_id: int | str | None,
    force_create: bool | str = False,
) -> HttpResponse:
    request.user = require_user(request)
    if not (request.user.is_tutor or request.user.is_trainer or request.user.is_superuser):
        return access_denied(request)

    solution = get_object_or_404(Solution, pk=solution_id)

    attestations = Attestation.objects.filter(solution = solution)
    if ((not force_create) and attestations):
        return render(request, "attestation/attestation_already_exists_for_solution.html", { 'task' : solution.task, 'attestations' : attestations, 'solution' : solution, 'show_author': not get_settings().anonymous_attestation })

    attest = Attestation(solution = solution, author = request.user)
    attest.save()
    for solutionFile in solution.textSolutionFiles():
        annotatedFile = AnnotatedSolutionFile(attestation = attest, solution_file=solutionFile, content=solutionFile.content())
        annotatedFile.save()
    for rating in solution.task.rating_set.all():
        ratingResult = RatingResult(attestation = attest, rating=rating)
        ratingResult.save()
    return HttpResponseRedirect(reverse('edit_attestation', args=[attest.id]))

@login_required
@transaction.atomic
def withdraw_attestation(
    request: HttpRequest, attestation_id: str
) -> HttpResponse:
    request.user = require_user(request)
    if not (request.user.is_tutor or request.user.is_trainer or request.user.is_superuser):
        return access_denied(request)

    attest = get_object_or_404(Attestation, pk=attestation_id)
    if not (attest.author == request.user or request.user.is_trainer):
        return access_denied(request)

    if attest.solution.task.only_trainers_publish and not request.user.is_trainer:
        return access_denied(request)

    if not attest.published:
        # If if this attestation is already final or not by this user redirect to view_attestation
        return HttpResponseRedirect(reverse('view_attestation', args=[attestation_id]))

    if request.method != "POST":
        return HttpResponseRedirect(reverse('view_attestation', args=[attestation_id]))

    attest.withdraw(request, by=request.user)
    return HttpResponseRedirect(reverse('edit_attestation', args=[attestation_id]))

@login_required
def edit_attestation(request: HttpRequest, attestation_id: str) -> HttpResponse:
    request.user = require_user(request)
    if not (request.user.is_tutor or request.user.is_trainer or request.user.is_superuser):
        return access_denied(request)

    attest = get_object_or_404(Attestation, pk=attestation_id)
    if not (attest.author == request.user or request.user.is_trainer):
        return access_denied(request)
    if attest.published:
        # If if this attestation is already final or not by this user redirect to view_attestation
        return HttpResponseRedirect(reverse('view_attestation', args=[attestation_id]))

    solution = attest.solution
    model_solution = solution.task.model_solution

    if request.method == "POST":
        with transaction.atomic():
            attestForm = AttestationForm(request.POST, instance=attest, prefix='attest')
            attestFileFormSet = AnnotatedFileFormSet(request.POST, instance=attest, prefix='attestfiles')
            ratingResultFormSet = RatingResultFormSet(request.POST, instance=attest, prefix='ratingresult')
            if attestForm.is_valid() and attestFileFormSet.is_valid() and ratingResultFormSet.is_valid():
                publish = 'publish' in request.POST
                attestForm.save()
                attest.final = publish
                attest.save()
                attestFileFormSet.save()
                ratingResultFormSet.save()

                if publish:
                    if attest.solution.task.only_trainers_publish and not request.user.is_trainer:
                        return access_denied(request)

                    attest.publish(request, by = request.user)
                    return HttpResponseRedirect(reverse('attestation_list', args=[attest.solution.task.id]))

                return HttpResponseRedirect(reverse('view_attestation', args=[attestation_id]))
    else:
        attestForm = AttestationForm(instance=attest, prefix='attest')
        attestFileFormSet = AnnotatedFileFormSet(instance=attest, prefix='attestfiles')
        ratingResultFormSet = RatingResultFormSet(instance=attest, prefix='ratingresult')

    show_author = not get_settings().anonymous_attestation
    show_run_checkers = get_settings().attestation_allow_run_checkers
    htmlinjectors = HtmlInjector.objects.filter(task = solution.task, inject_in_attestation_edit = True)
    htmlinjector_snippets = [ injector.html_file.read().decode("utf-8") for injector in htmlinjectors ]

    return render(request,
        "attestation/attestation_edit.html",
         {
            "attestForm": attestForm,
            "attestFileFormSet": attestFileFormSet,
            "ratingResultFormSet": ratingResultFormSet,
            "solution": solution,
            "model_solution": model_solution,
            "show_author": show_author,
            "show_run_checkers": show_run_checkers,
            "htmlinjector_snippets": htmlinjector_snippets,
        }
    )

@login_required
def view_attestation(
    request: HttpRequest, attestation_id: str
) -> HttpResponse:
    request.user = require_user(request)
    attest = get_object_or_404(Attestation, pk=attestation_id)
    # Whether to hide solutions of expired tasks
    hide = request.user.is_user and attest.solution.task.should_hide(request.user)
    may_modify = attest.author == request.user or request.user.is_trainer
    may_view = (attest.solution.author == request.user and not hide) or request.user.is_tutor or may_modify
    if not may_view:
        return access_denied(request)

    if request.method == "POST":
        if not may_modify:
            return access_denied(request)
        with transaction.atomic():
            form = AttestationPreviewForm(request.POST, instance=attest)
            if form.is_valid():
                form.save()
                if 'publish' in request.POST:
                    if attest.solution.task.only_trainers_publish and not request.user.is_trainer:
                        return access_denied(request)

                    attest.publish(request, by = request.user)
                return HttpResponseRedirect(reverse('attestation_list', args=[attest.solution.task.id]))
    else:
        form = AttestationPreviewForm(instance=attest)
    submitable = may_modify and not attest.published
    withdrawable = may_modify and attest.published

    htmlinjectors = HtmlInjector.objects.filter(task = attest.solution.task, inject_in_attestation_view = True)
    htmlinjector_snippets = [ injector.html_file.read().decode("utf-8") for injector in htmlinjectors ]

    return render(request,
        "attestation/attestation_view.html",
        {
            "attest": attest,
            "submitable": submitable,
            "withdrawable": withdrawable,
            "form": form,
            "show_author": not get_settings().anonymous_attestation,
            "show_attestor": not get_settings().invisible_attestor,
            "htmlinjector_snippets": htmlinjector_snippets,
        }
    )

def user_task_attestation_map(
    users: Iterable[User],
    tasks: Iterable[Task],
    only_published: bool = True,
) -> list[_AttestationRow]:
    tasks = tuple(tasks)
    if only_published:
        attestations = Attestation.objects.filter( published=True )
    else:
        attestations = Attestation.objects.all()

    attestations = attestations.select_related("solution", "final_grade")
    attestations = attestations.prefetch_related("ratingresult_set")
    attestation_dict: dict[tuple[int, int], Attestation] = {}
    for attestation in attestations:
        attestation_dict[attestation.solution.task_id, attestation.solution.author_id] = attestation

    solutions = Solution.objects.filter( final=True )
    final_solutions_dict: dict[tuple[int, int], Solution] = {}
    for solution in solutions:
        final_solutions_dict[solution.task_id, solution.author_id] = solution

    settings = get_settings()
    arithmetic_option = settings.final_grades_arithmetic_option
    plagiarism_option = settings.final_grades_plagiarism_option

    rating_list: list[_AttestationRow] = []
    for user in users:
        rating_for_user_list: list[_AttestationCell] = []
        grade_sum = 0.0
        threshold = Decimal(0)

        for task in tasks:
            solution = final_solutions_dict.get((task.id, user.id), None)

            rating = attestation_dict.get((task.id, user.id))
            if rating is not None and rating.final_grade is None:
                # Unfinished attestations without a grade do not count as ratings.
                rating = None
            if rating or (task.expired_for_user(user) and not solution):
                threshold += task.warning_threshold

            if rating is not None and rating.final_grade is not None:
                if plagiarism_option == 'WP' or (plagiarism_option == 'NP' and not rating.solution.plagiarism):
                    try:
                        grade_sum += float(rating.final_grade.name)
                    except ValueError:
                        pass #non-numeric grade, ignore

            rating_for_user_list.append((rating, solution))

        if arithmetic_option == 'SUM':
            calculated_grade = grade_sum
        else:
            # in this case: arithmetic_option == 'AVG'
            if len(rating_for_user_list) == 0:
                calculated_grade = 0.0
            else:
                calculated_grade = grade_sum / len(rating_for_user_list)

        rating_list.append((user, rating_for_user_list, threshold, calculated_grade))

    return rating_list

@login_required
def rating_overview(request: HttpRequest) -> HttpResponse:
    request.user = require_user(request)
    full_form = request.user.is_trainer or request.user.is_superuser

    if not (full_form or (request.user.is_coordinator and request.method != "POST")):
        return access_denied(request)

    tasks = Task.objects.filter(submission_date__lt = datetime.datetime.now())
    users = User.objects.filter(groups__name='User').filter(is_active=True).order_by('last_name', 'first_name', 'id')
    # corresponding user to user_id_list in reverse order! important for easy displaying in template
    rev_users = users.reverse()
    users = users.select_related("user_ptr", "user_ptr__groups__name", "user_ptr__is_active", "user_ptr__user_id")

    FinalGradeFormSet = modelformset_factory(User, fields=('final_grade',), extra=0)

    if request.method == "POST":
        final_grade_option_form = FinalGradeOptionForm(request.POST, instance=get_settings())
        if final_grade_option_form.is_valid():
            final_grade_option_form.save()

        if 'save' in request.POST:
            # also save final grades
            final_grade_formset = FinalGradeFormSet(request.POST, request.FILES, queryset=rev_users)
            publish_final_grade_form = PublishFinalGradeForm(request.POST, instance=get_settings())
            if final_grade_formset.is_valid() and publish_final_grade_form.is_valid():
                final_grade_formset.save()
                publish_final_grade_form.save()
        else:
            final_grade_formset = FinalGradeFormSet(queryset=rev_users)
            publish_final_grade_form = PublishFinalGradeForm(instance=get_settings())

    else:
        # all 3 forms are created without request input
        final_grade_option_form = FinalGradeOptionForm(instance=get_settings())
        final_grade_formset = FinalGradeFormSet(queryset=rev_users)
        publish_final_grade_form = PublishFinalGradeForm(instance=get_settings())

    rating_list = user_task_attestation_map(users, tasks)

    return render(request, "attestation/rating_overview.html", {'rating_list': rating_list, 'tasks': tasks, 'final_grade_formset': final_grade_formset, 'final_grade_option_form': final_grade_option_form, 'publish_final_grade_form': publish_final_grade_form, 'full_form': full_form})


@login_required
def tutorial_overview(
    request: HttpRequest, tutorial_id: str | None = None
) -> HttpResponse:
    request.user = require_user(request)
    if not (request.user.is_tutor or request.user.is_trainer or request.user.is_superuser):
        return access_denied(request)

    if (tutorial_id):
        tutorial = get_object_or_404(Tutorial, pk=tutorial_id)
        if request.user.is_tutor and not tutorial.tutors.filter(id=request.user.id):
            return access_denied(request)
    else:
        tutorials = request.user.tutored_tutorials.all()
        if (not tutorials):
            return render(request, "attestation/tutorial_none.html")

        tutorial = request.user.tutored_tutorials.all()[0]

    if request.user.is_tutor:
        other_tutorials = request.user.tutored_tutorials.all()
    else:
        other_tutorials = Tutorial.objects.all()
    other_tutorials = other_tutorials.exclude(id=tutorial.id)

    tasks = Task.objects.filter(submission_date__lt = datetime.datetime.now()).order_by('publication_date', 'submission_date')
    users = User.objects.filter(groups__name='User').filter(is_active=True, tutorial=tutorial).order_by('last_name', 'first_name')
    rating_list = user_task_attestation_map(users, tasks, False)

    def numeric_grade(a: Attestation | None) -> float | None:
        if a is None or a.final_grade is None:
            return None
        try:
            return float(str(a.final_grade))
        except ValueError:
            return None

    totals = [0.0 for _ in tasks]
    nr_of_grades = [0 for _ in tasks]
    for _, attestations, _, _ in rating_list:
        for i, (attestation, _) in enumerate(attestations):
            grade = numeric_grade(attestation)
            if grade is not None:
                totals[i] += grade
                nr_of_grades[i] += 1
    averages = [total / (count or 1) for total, count in zip(totals, nr_of_grades)]

    return render(request, "attestation/tutorial_overview.html", {'other_tutorials':other_tutorials, 'tutorial':tutorial, 'rating_list':rating_list, 'tasks':tasks, 'final_grades_published': get_settings().final_grades_published, 'averages':averages})


@login_required
def rating_export(request: HttpRequest) -> HttpResponse:
    request.user = require_user(request)
    if not (request.user.is_trainer or request.user.is_coordinator or request.user.is_superuser):
        return access_denied(request)

    tasks = Task.objects.filter(submission_date__lt = datetime.datetime.now()).order_by('publication_date', 'submission_date')
    users = User.objects.filter(groups__name='User').filter(is_active=True).order_by('last_name', 'first_name')
    rating_list = user_task_attestation_map(users, tasks)

    response = HttpResponse(content_type='text/csv')
    if settings.LDAP_ENABLED:
        response['Content-Disposition'] = 'attachment; filename=rating_export_ldap.csv'
        t = loader.get_template('attestation/rating_export_ldap.csv')
        c = {'rating_list': rating_list, 'tasks': tasks}
        #response.write(u'\ufeff') setting utf-8 BOM for Exel doesn't work
        response.write(t.render(c))
    else:
        response['Content-Disposition'] = 'attachment; filename=rating_export.csv'
        t = loader.get_template('attestation/rating_export.csv')
        c = {'rating_list': rating_list, 'tasks': tasks}
        #response.write(u'\ufeff') setting utf-8 BOM for Excel doesn't work
        response.write(t.render(c))
    return response

def frange(start: float, end: float, inc: float) -> list[float]:
    "A range function, that does accept float increments..."
    L: list[float] = []
    while True:
        next = start + len(L) * inc
        if inc > 0 and next > end:
            break
        elif inc < 0 and next < end:
            break
        L.append(next)
    return L

@staff_member_required
def generate_ratingscale(request: HttpRequest) -> HttpResponse:
    """ View in the admin """
    if request.method == 'POST':
        form = GenerateRatingScaleForm(request.POST)
        if form.is_valid():
            scale = RatingScale(name=form.cleaned_data['name'])
            scale.save()
            start = form.cleaned_data['start']
            end = form.cleaned_data['end']
            step = form.cleaned_data['step']
            count = 0
            for x in frange(start, end, step):
                item = RatingScaleItem(scale=scale, name=x, position=count)
                item.save()
                count += 1
            return HttpResponseRedirect(reverse('admin:attestation_ratingscale_changelist'))
    else:
        form = GenerateRatingScaleForm()
    return render(request, 'admin/attestation/ratingscale/generate.html', {'form': form, 'title':"Generate RatingScale"  })


@login_required
def attestation_run_checker(
    request: HttpRequest, attestation_id: str
) -> HttpResponse:
    request.user = require_user(request)
    if not (request.user.is_tutor or request.user.is_trainer or request.user.is_superuser):
        return access_denied(request)

    attestation = get_object_or_404(Attestation, pk=attestation_id)
    if not (attestation.author == request.user or request.user.is_trainer or request.user.is_superuser):
        return access_denied(request)

    if attestation.published:
        return access_denied(request)

    if not get_settings().attestation_allow_run_checkers:
        return access_denied(request)



    solution = attestation.solution
    check_solution(solution, True)
    return HttpResponseRedirect(reverse('edit_attestation', args=[attestation_id]))

class ImportForm(forms.Form):
    file: forms.FileField = forms.FileField()

@staff_member_required
def update_attestations(request: HttpRequest) -> HttpResponse:
    """ View in the admin """
    if request.method == 'POST':
        form = ImportForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                Attestation.update_Attestations(request, form.cleaned_data['file'])
                return render(request, 'admin/attestation/update.html', {'form': form, 'title':"Update Attestations"  })
            except Exception as e:
                msg = "An Error occured. The import file was propably malformed.: %s" % str(e)
                form.add_error("file", msg)
    else:
        form = ImportForm()
    return render(request, 'admin/attestation/update.html', {'form': form, 'title':"Update Attestations"  })

def timedelta_diff(
    td1: datetime.timedelta, td2: datetime.timedelta
) -> int:
    # The result of "//" is a whole number, but with type float.
    # Since you cannot use that to index a list, we explicitly convert it to int
    return int(td1.total_seconds() // td2.total_seconds())
