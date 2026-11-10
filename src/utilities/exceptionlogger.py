# From http://www.obeythetestinggoat.com/how-to-log-exceptions-to-stderr-in-django.html
import logging
from collections.abc import Callable

from django.http import HttpRequest, HttpResponseBase


class ExceptionLoggingMiddleware:
    def __init__(
        self, get_response: Callable[[HttpRequest], HttpResponseBase]
    ) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponseBase:
        return self.get_response(request)

    def process_exception(self, request: HttpRequest, exception: Exception) -> None:
        logging.exception('Exception handling request for ' + request.path)
