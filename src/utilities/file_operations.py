import os
import grp
import tempfile
from collections.abc import Callable
from django.conf import settings
from django.core.files import File
from utilities import encoding
import zipfile

gid: int | None = None
if (settings.USEPRAKTOMATTESTER):
    gid = grp.getgrnam('praktomat').gr_gid


def require_file_name(file: "File[bytes]") -> str:
    name = file.name
    if not name:
        raise ValueError("A file name is required.")
    return name


def makedirs(path: str) -> None:
    if os.path.exists(path):
        return
    else:
        (head, _) = os.path.split(path)
        makedirs(head)
        os.mkdir(path)
        if (gid):
            os.chown(path, -1, gid)
        os.chmod(path, 0o770)


def create_file(
    path: str,
    content: str | bytes,
    override: bool = True,
    binary: bool = False,
) -> None:
    """ """
    dirname = os.path.dirname(path)
    if not os.path.exists(dirname):
        makedirs(dirname)
    else:
        if os.path.exists(path):
            if override: # delete file
                os.remove(path)
            else: # throw exception
                raise Exception('File already exists')
    with open(path, 'wb') as fd:
        if binary:
            if not isinstance(content, bytes):
                raise TypeError("binary content must be bytes")
            fd.write(content)
        else:
            fd.write(encoding.get_utf8(encoding.get_unicode(content)))
    if (gid):
        # chown :praktomat <path>
        os.chown(path, -1, gid)
        # rwxrwx---     access for praktomattester:praktomat
        os.chmod(path, 0o770)


def copy_file(
    from_path: str,
    to_path: str,
    to_is_directory: bool = False,
    override: bool = True,
) -> None:
    """ """
    if to_is_directory:
        to_path = os.path.join(to_path, os.path.basename(from_path))
    with open(from_path, "rb") as fd:
        create_file(to_path, fd.read(), override=override, binary=True)


def create_tempfolder(path: str) -> str:
    makedirs(path)
    new_tmpdir = tempfile.mkdtemp(dir=path)
    if (gid):
        os.chown(new_tmpdir, -1, gid)
    os.chmod(new_tmpdir, 0o770)
    return new_tmpdir

class InvalidZipFile(Exception):
    pass

def unpack_zipfile_to(
    zipfilename: str,
    to_path: str,
    override_cb: Callable[[str], object] | None = None,
    file_cb: Callable[[str], object] | None = None,
) -> None:
    """
    Extracts a zipfile to the given location, trying to safeguard against wrong paths

    The override_cb is called for every file that overwrites an existing file,
    with the name of the file in the archive as the parameter.

    The file_cb is called for every file, after extracting it.
    """
    if not zipfile.is_zipfile(zipfilename):
        raise InvalidZipFile("File %s is not a zipfile." % zipfilename)
    root = os.path.realpath(to_path)
    with zipfile.ZipFile(zipfilename, 'r') as zip:
        if zip.testzip():
            raise InvalidZipFile("File %s is invalid." % zipfilename)

        for finfo in zip.infolist():
            dest = os.path.realpath(os.path.join(root, finfo.filename))
            if os.path.isabs(finfo.filename) or os.path.commonpath((root, dest)) != root:
                raise InvalidZipFile("File %s contains illegal path %s." % (zipfilename, finfo.filename))
            if override_cb is not None and os.path.exists(dest):
                override_cb(finfo.filename)
            zip.extract(finfo, root)
            if file_cb is not None and os.path.isfile(dest):
                file_cb(finfo.filename)
