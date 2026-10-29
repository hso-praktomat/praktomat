import base64
import collections
import csv
from collections.abc import Mapping, Sequence
from io import BytesIO
from typing import Literal, Protocol, TypedDict, cast

from django.contrib import messages
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.timezone import now
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.backends.backend_agg import FigureCanvasAgg

from accounts.authentication import require_user
from tasks.models import Task
from taskstatistics.models import TasksStatistic

StatisticValue = str | int | float
StatisticRow = collections.OrderedDict[str, StatisticValue]
UploadStatus = Literal['prefailed', 'postpassed', 'postfailed']


class UserUploads(TypedDict):
    task_id: list[int]
    status: list[UploadStatus]
    uploads: list[int]


class BoxStatistics(TypedDict):
    med: int | float
    q1: int | float
    q3: int | float
    whislo: int | float
    whishi: int | float
    mean: int | float
    fliers: list[int]
    label: str


class _StatisticsAxes(Protocol):
    def set_title(self, label: str) -> object: ...
    def set_xlabel(self, xlabel: str) -> object: ...
    def set_ylabel(self, ylabel: str) -> object: ...
    def bxp(self, bxpstats: list[BoxStatistics], *, showmeans: bool) -> dict[str, list[Line2D]]: ...
    def legend(self, handles: Sequence[Line2D], labels: Sequence[str]) -> object: ...


class _PNGCanvas(Protocol):
    def print_png(self, filename_or_obj: BytesIO) -> None: ...


def getQuerySet() -> QuerySet[TasksStatistic, dict[str, object]]:
    return TasksStatistic.objects.filter(
        task__publication_date__lte=now(), task__all_checker_finished=True,
    ).values().order_by('id')


def _number(row: Mapping[str, StatisticValue], key: str) -> int | float:
    value = row[key]
    if not isinstance(value, (int, float)):
        raise TypeError(f"Statistic {key} must be numeric")
    return value


def _task_id(row: Mapping[str, StatisticValue]) -> int:
    value = row['task_id']
    if not isinstance(value, int):
        raise TypeError("Statistic task_id must be an integer")
    return value


def boxblot_to_graphic_list(
    glist: list[str] | None = None,
    dtupel: Mapping[str, StatisticValue] | None = None,
    fliers: UserUploads | None = None,
) -> list[str]:
    if glist is None or dtupel is None:
        raise TypeError("boxblot_to_graphic_list cannot be called with None in the first two arguments")
    task_id = _task_id(dtupel)
    user_uploads: dict[UploadStatus, int] = {}
    if fliers:
        if not fliers['task_id'] or not fliers['status'] or not fliers['uploads']:
            raise ValueError("User upload data must contain task, status and upload count")
        if task_id != max(fliers['task_id']):
            raise ValueError("User upload data belongs to a different task")
        status = fliers['status'][0]
        if status not in ('prefailed', 'postpassed', 'postfailed'):
            raise ValueError(f"Invalid upload status: {status}")
        user_uploads[status] = max(fliers['uploads'])

    figure = Figure()
    axes = cast(_StatisticsAxes, figure.subplots())
    axes.set_title(
        "Task %d : %s\n Submitters passed Posttest: %d \n Submitters passed Pretest but failed Posttest: %d\n Submitters failed Pretest: %d\n Uploads accepted: %d\n Uploads rejected: %d"
        % (
            task_id, dtupel['title'], _number(dtupel, 'submitters_passed_finals'),
            _number(dtupel, 'submitters_failed_finals'),
            _number(dtupel, 'submitters_latest_not_accepted'),
            _number(dtupel, 'uploads_accepted'), _number(dtupel, 'uploads_rejected'),
        )
    )
    groups: list[tuple[UploadStatus, str, tuple[str, str, str, str, str, str]]] = [
        ('postpassed', 'posttest\n passed', (
            'med_upl_til_final_pass', 'lo_quart_upl_til_final_pass',
            'up_quart_upl_til_final_pass', 'lo_whisker_upl_til_final_pass',
            'up_whisker_upl_until_final_pass', 'avg_upl_until_final_pass',
        )),
        ('postfailed', 'posttest\n failed', (
            'median_uploads_final_failed', 'lo_quart_upl_final_fail',
            'up_quart_upl_final_failed', 'lo_whisker_upl_final_fail',
            'up_whisker_upl_final_failed', 'avg_uploads_final_failed',
        )),
        ('prefailed', 'pretest\n failed', (
            'median_uploads_only_failed', 'lo_quart_upl_only_fail',
            'up_quart_upl_only_failed', 'lo_whisker_upl_only_fail',
            'up_whisker_upl_only_failed', 'avg_uploads_only_failed',
        )),
    ]
    boxes: list[BoxStatistics] = []
    for status, label, fields in groups:
        median, q1, q3, low, high, mean = (_number(dtupel, field) for field in fields)
        count = user_uploads.get(status, 0)
        boxes.append({
            'med': median, 'q1': q1, 'q3': q3, 'whislo': low, 'whishi': high,
            'mean': mean, 'fliers': [count] if count > 0 else [], 'label': label,
        })
    artists = axes.bxp(boxes, showmeans=True)
    handles = [artists['medians'][0], artists['means'][0]]
    labels = ['median', 'mean']
    if any(user_uploads.values()):
        handles.append(artists['fliers'][0])
        labels.append('your position')
    axes.legend(handles, labels)
    axes.set_ylabel("Anzahl der Uploads pro Person")
    axes.set_xlabel("Kategorien der jeweils letzten Einreichungen von Studierenden")
    figure.tight_layout()
    with BytesIO() as buffer:
        cast(_PNGCanvas, FigureCanvasAgg(figure)).print_png(buffer)
        glist.append(base64.b64encode(buffer.getvalue()).decode('ascii'))
    return glist


def prepare_statistic_data() -> tuple[list[StatisticRow], QuerySet[Task, Task]]:
    rows: list[StatisticRow] = []
    for row in getQuerySet():
        ordered: StatisticRow = collections.OrderedDict()
        for field in TasksStatistic._meta.fields:
            key = field.attname
            value = row[key]
            if value is None:
                ordered[key] = 0
            elif isinstance(value, (str, int, float)):
                ordered[key] = value
            else:
                raise TypeError(f"Unexpected statistic value for {key}: {type(value).__name__}")
        rows.append(ordered)
    tasks = Task.objects.filter(
        publication_date__lte=now(), all_checker_finished=True,
    ).order_by('id')
    return rows, tasks


def prepare_graphic_list(
    data_: list[StatisticRow] | None,
    userdata_: dict[int, UserUploads] | None = None,
) -> list[str]:
    graphics: list[str] = []
    for row in data_ or []:
        uploads = userdata_.get(_task_id(row)) if userdata_ is not None else None
        boxblot_to_graphic_list(graphics, row, uploads)
    return graphics


def tasks_statistic(request: HttpRequest) -> HttpResponse:
    data, tasks = prepare_statistic_data()
    uploads: dict[int, UserUploads] = {}
    if hasattr(request, "user") and request.user.is_authenticated:
        request.user = require_user(request)
        for task in tasks:
            final = task.final_solution(request.user)
            count = 0
            status: UploadStatus = 'prefailed'
            if final is not None:
                if final.number is None:
                    raise ValueError("A final solution must have an upload number")
                count = final.number
                status = 'postpassed' if final.accepted else 'postfailed'
            uploads[task.pk] = {'task_id': [task.pk], 'status': [status], 'uploads': [count]}
    graphics = prepare_graphic_list(data, uploads)
    if not data:
        messages.warning(request, "Apparently no data available...")
    return render(request, 'taskstatistics/overview.html', {'data': data, 'graphics': graphics})


def tasks_statistic_download(request: HttpRequest) -> HttpResponse:
    data, _ = prepare_statistic_data()
    if not data:
        messages.warning(request, "Apparently no data available...")
        return render(request, 'taskstatistics/overview.html', {'data': data})
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="TaskStatistic.csv"'
    writer = csv.writer(response, lineterminator='\n')
    columns = list(data[0])
    float_columns = {key for key in columns if any(isinstance(row[key], float) for row in data)}
    writer.writerow(columns)
    for row in data:
        writer.writerow([
            float(value) if key in float_columns and isinstance(value, int) else value
            for key, value in row.items()
        ])
    return response
