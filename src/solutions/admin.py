from django.contrib import admin
from django.db.models import QuerySet as _QuerySet
from django.http import HttpRequest as _HttpRequest
from solutions.models import Solution, SolutionFile
from checker.basemodels import CheckerResult
from checker.basemodels import check_multiple
from django.urls import reverse
from django.db.models import Max
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.safestring import SafeString as _SafeString
import typing as _typing


def _boolean_annotation(solution: Solution, name: str) -> bool:
    value: object = getattr(solution, name)
    if isinstance(value, (bool, int)) and value in (0, 1):
        return bool(value)
    raise TypeError(f"Expected a boolean query annotation for {name}")


class CheckerResultInline(admin.TabularInline[CheckerResult, Solution] if _typing.TYPE_CHECKING else admin.TabularInline):
    model: type[CheckerResult] = CheckerResult
    extra = 0
    can_delete = False
    fields = ["checker", "passed", "log"]
    readonly_fields = ["checker", "passed", "log"]

class SolutionFileInline(admin.TabularInline[SolutionFile, Solution] if _typing.TYPE_CHECKING else admin.TabularInline):
    model: type[SolutionFile] = SolutionFile
    extra = 0
    can_delete = False
    fields = ["file", "mime_type"]
    readonly_fields=["mime_type"]


class IsLatestOfOnlyFailedFilter(admin.SimpleListFilter):
    title = 'latest of only failed'
    parameter_name = 'latest_of_only_failed'

    def lookups(
        self, request: _HttpRequest, model_admin: "admin.ModelAdmin[Solution]"
    ) -> tuple[tuple[str, str], tuple[str, str]]:
        return (
          ('Yes','Yes'),
          ('No','No'),
        )

    def queryset(
        self, request: _HttpRequest, queryset: _QuerySet[Solution, Solution]
    ) -> _QuerySet[Solution, Solution]:
        value = self.value()

        if value == 'Yes':
            return queryset.filter(_latest_of_only_failed_computed_for_sorting=True)
        elif value == 'No':
            return queryset.filter(_latest_of_only_failed_computed_for_sorting=False)
        return queryset


        q=queryset
#        print(type(q))
#        print(q)
        filterlist=[]

        for solution in q:
#           print("=====")
#           print("TaskID:" , solution.task_id)
#           print(solution)
           successfull_solution_from_user_for_task_available = solution.final or  [ s for s in Solution.objects.all().filter(author=solution.author, task=solution.task) if s.final]
#           print("successfull_solution_from_user_for_task_available:", successfull_solution_from_user_for_task_available)
           is_latest_failed_attempt = (not solution.final) and (Solution.objects.all().filter(task=solution.task, author=solution.author).aggregate(Max('number'))['number__max'] == solution.number)
#           print("is_latest_failed_attempt:", is_latest_failed_attempt)
           latestfailed = (not successfull_solution_from_user_for_task_available) and is_latest_failed_attempt
#           print("latestfailed:",latestfailed)
           if True == latestfailed:
#               print("FOUND, put to list" )
               filterlist += [solution.id]
#        print("===============")
#        print(type(filterlist))
#        print(filterlist)
#        print("===============")
        if value == 'Yes':
          return queryset.filter(pk__in=filterlist)
        elif value == 'No':
          return queryset.exclude(pk__in=filterlist)
        return queryset







class SolutionAdmin(admin.ModelAdmin[Solution] if _typing.TYPE_CHECKING else admin.ModelAdmin):
    model: type[Solution] = Solution
    list_display = ["edit", "view_url", "download_url", "run_checker_url", "task", "show_author", "number", "creation_date", "final", "accepted", "tests_failed", "all_checker_finished", "latest_of_only_failed", "plagiarism"]
    list_filter = ["task", "author", "author__groups", "creation_date" , IsLatestOfOnlyFailedFilter ,"final", "accepted", "warnings", "plagiarism"]
    fieldsets = ((None, {
                    'fields': ( "task", "author", "creation_date", ("final", "accepted", "warnings", "all_checker_finished"), "plagiarism", "allow_llm_upload", 'useful_links')
                }),)
    readonly_fields = ["creation_date", "accepted", "all_checker_finished", "tests_failed", 'useful_links']
    inlines = [CheckerResultInline, SolutionFileInline]
    actions = ['run_checkers', 'run_checkers_all', 'mark_plagiarism', 'mark_no_plagiarism']

    def get_readonly_fields(
        self, request: _HttpRequest, obj: Solution | None = None
    ) -> list[str] | tuple[str, ...]:
        # If obj exists (Edit mode), make task and author readonly
        if obj:
            return list(self.readonly_fields) + ["task", "author"]
        # On creation (obj=None), all fields defined in fieldsets are editable
        return self.readonly_fields

    #for sorting computed values "tests_failed" and "latest of only failed" which are not stored in database,
    #wie have to implement the behavior of get_queryset to simulate a return of SQL's ORDER BY

    def get_queryset(
        self, request: _HttpRequest
    ) -> _QuerySet[Solution, Solution]:
        queryset = super(SolutionAdmin,self).get_queryset(request)
        from django.db.models import Exists, OuterRef
        from django.db.models.expressions import RawSQL

        #example snipplet 1
        # events = Event.objects.all().annotate(paid_participants=models.Sum(
        #   models.Case(
        #             models.When(participant__is_paid=True, then=1),
        #             default=0,
        #             output_field=models.IntegerField()
        # )))

        #example snipplet 2
        # Item.objects.filter(serial__in=license_ids
        # ).update(renewable=Case(
        #     When(renewable=True, then=Value(False)),
        #     default=Value(True))
        #     )
        # )

        #example snipplet 3
        #Join chains can be as deep as you require. For example, to extract the age of the youngest author of any book available for sale, you could issue the query:
        #>>> Store.objects.aggregate(youngest_age=Min('books__authors__age'))

        #example snipplet 4
        # _computed_value= ExpressionWrapper(
        # F('entiyAttributeOne') < F('otherEntity__'), output_field=BooleanField()))

        queryset = queryset.annotate(
             # Outside the query annotation, we would get the the correct value for each mysolution with:
             # CheckerResult.objects.filter(solution=mysolution,passed=False).exists();
             #
             # In pure SQL we could use a correlated Subquery with EXISTS in outer SELECT-statement:
             # SELECT EXISTS
             #    (
             #       SELECT c.id AS checkerID
             #       FROM checker_checkerresult c
             #       WHERE ( (NOT c.passed) AND (c.solution_id = s.id))
             #    ) AS "has failed Checkers"
             # FROM solutions_solution s

            _tests_failed_computed_for_sorting=  Exists( CheckerResult.objects.only('id').filter( solution_id=OuterRef('id'),passed=False)) ,


            # In pure SQL we could use a correlated Subquery with EXISTS in outer SELECT-statement:
            #
            # I did not find any possibility to use the Django ORM-Manager for writing it, therefor I am now using RawSQL

            _latest_of_only_failed_computed_for_sorting=RawSQL(
              '''SELECT EXISTS(
                   SELECT s.id, s.final, s.accepted, s.author_id
                   FROM solutions_solution s
                   WHERE ((Not s.final) and (Not s.accepted))
                           AND (s.author_id, s.task_id) NOT IN ( SELECT i.author_id, i.task_id
                                                        FROM solutions_solution i
                                                        WHERE i.final )
                   GROUP BY s.author_id, s.task_id, s.id, s.final, s.accepted
                   HAVING MAX(s.number) = s.number
                   AND s.id = o.id
                 ) as latest_of_only_failed
                 FROM solutions_solution o
                 WHERE o.id = solutions_solution.id
                 ''', []),  #OuterRef('id')  --- because we cannot use OuterRef as parameter , I coded solutions_solution.id in a hard way, it is the reference to the outer part of query generated by the framework...
           )
        return queryset





    @admin.action(description="Run Checkers (including those not run at submission) for selected solution ")
    def run_checkers_all(
        self, request: _HttpRequest, queryset: _QuerySet[Solution, Solution]
    ) -> None:
        """ Run Checkers (including those not run at submission) for selected solution """
        check_multiple(queryset, True)
        self.message_user(request, "Checkers (including those not run at submission) for selected solutions were successfully run.")


    @admin.action(description="Run Checkers (only those also run at submission) for selected solutions")
    def run_checkers(
        self, request: _HttpRequest, queryset: _QuerySet[Solution, Solution]
    ) -> None:
        """ Run Checkers (only those also run at submission) for selected solutions"""
        check_multiple(queryset, False)
        self.message_user(request, "Checkers (only those also run at submission) for selected solutions were successfully run.")


    def mod_plagiarism(
        self, queryset: _QuerySet[Solution, Solution], value: bool
    ) -> int:
        count = 0
        for s in queryset:
            if s.plagiarism != value:
                s.plagiarism = value
                s.save()
                count += 1
        return count

    @admin.action(description="Mark as plagiated")
    def mark_plagiarism(
        self, request: _HttpRequest, queryset: _QuerySet[Solution, Solution]
    ) -> None:
        count = self.mod_plagiarism(queryset, True)
        self.message_user(request, "%d solutions marked as plagiated" % count)

    @admin.action(description="Mark as not plagiated")
    def mark_no_plagiarism(
        self, request: _HttpRequest, queryset: _QuerySet[Solution, Solution]
    ) -> None:
        count = self.mod_plagiarism(queryset, False)
        self.message_user(request, "%d solutions marked as not plagiated" % count)


    @admin.display(description='Edit (Admin Site)')
    def edit(self, solution: Solution) -> str:
        return 'Edit'

    @admin.display(description='View (User Site)')
    def view_url(self, solution: Solution) -> _SafeString:
        return mark_safe('<a href="%s">View</a>' % (reverse('solution_detail_full', args=[solution.id])))

    @admin.display(description='Download')
    def download_url(self, solution: Solution) -> _SafeString:
        return mark_safe('<a href="%s">Download</a>' % (reverse('solution_download', args=[solution.id])))

    @admin.display(description='Run Checker (incl. those run at submission)')
    def run_checker_url(self, solution: Solution) -> _SafeString:
        return mark_safe('<a href="%s">Run Checkers</a>' % (reverse('solution_run_checker', args=[solution.id])))

    @admin.display(description='Solution author', ordering='author')
    def show_author(self, instance: Solution) -> _SafeString:
        return format_html('<a href="{0}">{1}</a>',
                           reverse('admin:accounts_user_change', args=(instance.author.pk,)),
                           instance.author)

    def useful_links(self, instance: Solution) -> _SafeString | str:
        if instance.pk:
            return format_html ('<a href="{0}">Attestations of this solution</a> • <a href="{1}">User Site view of this solution</a>',
                reverse('admin:attestation_attestation_changelist') + ("?solution__exact=%d" % instance.pk),
                reverse('solution_detail', args=[instance.pk])
                )
        else:
            return ""

    @admin.display(boolean=True, ordering='_tests_failed_computed_for_sorting')
    def tests_failed(self, solution: Solution) -> bool:
        #return CheckerResult.objects.filter(solution=solution,passed=False).exists();
        #since we had annotated the queryset already, for sorting this computed column, just reuse that annotated values for visualisation
        return _boolean_annotation(solution, '_tests_failed_computed_for_sorting')


    @admin.display(boolean=True, ordering='_latest_of_only_failed_computed_for_sorting')
    def latest_of_only_failed(self, solution: Solution) -> bool:
        # ToDo ... perhaps to slow for many solutions ... rethink about it using subqueries:
        # https://hansonkd.medium.com/the-dramatic-benefits-of-django-subqueries-and-annotations-4195e0dafb16
        # https://medium.com/kolonial-no-product-tech/pushing-the-orm-to-its-limits-d26d87a66d28
        #successfull_solution_from_user_for_task_available = solution.final or  [ s for s in Solution.objects.all().filter(author=solution.author, task=solution.task) if s.final]
        #is_latest_failed_attempt = (not solution.final) and (Solution.objects.all().filter(task=solution.task, author=solution.author).aggregate(Max('number'))['number__max'] == solution.number)
        #return (not successfull_solution_from_user_for_task_available) and is_latest_failed_attempt

        #since we had annotated the queryset already, for sorting this computed column, just reuse that annotated values for visualisation
        #on Admin Solution change listview the green circle is "Yes"
        # => here "Yes" means "latest of only failed solution" and that is not a "positive" information
        # => therfor it would be better to change the symbolic - like mentioned in https://github.com/KITPraktomatTeam/Praktomat/issues/315
        return _boolean_annotation(solution, '_latest_of_only_failed_computed_for_sorting')


admin.site.register(Solution, SolutionAdmin)
