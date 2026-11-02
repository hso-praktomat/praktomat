from logging import LogRecord

from django.http import UnreadablePostError

def skip_unreadable_post(record: LogRecord) -> bool:
    if record.exc_info:
        _, exc_value = record.exc_info[:2]
        if isinstance(exc_value, UnreadablePostError):
            return False
    return True
