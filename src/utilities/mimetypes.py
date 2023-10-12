from django.conf import settings
import mimetypes

for (mimetype, extension) in settings.MIMETYPE_ADDITIONAL_EXTENSIONS:
    mimetypes.add_type(mimetype, extension, strict=True)

def guess_mime_type_with_fallback(filename):
    content_type = mimetypes.guess_type(filename)[0]
    if content_type is None:
        return 'application/octet-stream'
    return content_type
