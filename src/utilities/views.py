import os, sys, mimetypes, urllib
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, Http404
from django.shortcuts import get_object_or_404
from django.conf import settings
from django.views.static import serve
from django.utils.encoding import smart_str

from accounts.views import access_denied
from solutions.models import Solution
from tasks.models import Task

def serve_unrestricted(request, path):
    return sendfile(request, path)

@login_required
def serve_staff_only(request, path):
    if  request.user.is_staff:
        return sendfile(request, path)
    return forbidden(request, path)

def serve_access_denied(request, path):
    return forbidden(request, path)

@login_required
def serve_solution_file(request, path, solution_id):
    solution = get_object_or_404(Solution, pk=solution_id)
    hide = request.user.is_user and solution.task.should_hide(request.user)
    if (solution.author == request.user and not hide) or request.user.is_staff or (solution.author.tutorial is not None and request.user.tutored_tutorials.filter(id=solution.author.tutorial.id)):
        return sendfile(request, path)
    return forbidden(request, path)

@login_required
def serve_media_file(request, path, task_id):
    task = get_object_or_404(Task, pk=task_id)
    hide = request.user.is_user and task.should_hide_media(request.user)
    if hide:
        return forbidden(request, path)
    return sendfile(request, path)

def sendfile(request, path):
    """ Serve files with mod_xsendfile (http://tn123.ath.cx/mod_xsendfile/)"""
    filename = os.path.join(settings.UPLOAD_ROOT, path)
    if not os.path.isfile(filename):
        raise Http404
    if 'runserver' in sys.argv or 'runserver_plus' in sys.argv or 'runconcurrentserver' in sys.argv:
        # serve with development server when not run in apache
        return serve(request, path, document_root=settings.UPLOAD_ROOT)
    response = HttpResponse()
    # Need to url-quote the filename for mod_xsendfile V1.0
    response['X-Sendfile'] =  urllib.parse.quote(smart_str(filename)) if settings.MOD_XSENDFILE_V1_0 else smart_str(filename)
    content_type, encoding = mimetypes.guess_type(path)
    if not content_type:
        content_type = 'application/octet-stream'
    response['Content-Type'] = content_type
    response['Content-Length'] = os.path.getsize(filename)
    return response

def forbidden(request, path):
    filename = os.path.join(settings.UPLOAD_ROOT, path)
    if not os.path.isfile(filename):
        raise Http404
    return access_denied(request)
