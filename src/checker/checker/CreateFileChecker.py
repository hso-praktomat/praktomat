import os

from django.db import models
from django.utils.translation import gettext_lazy
from django.core.exceptions import ValidationError
from checker.basemodels import Checker, CheckerFileField
from utilities.file_operations import *
from utilities.encoding import *
from django.utils.html import escape
from django.contrib import admin


class CheckerWithFile(Checker):
    class Meta:
        abstract = True

    file = CheckerFileField(help_text=gettext_lazy("The file that is copied into the sandbox"))
    filename = models.CharField(max_length=500, blank=True, help_text=gettext_lazy("What the file will be named in the sandbox. If empty, we try to guess the right filename!"))
    path = models.CharField(max_length=500, blank=True, help_text=gettext_lazy("Subfolder in the sandbox which shall contain the file."))
    unpack_zipfile = models.BooleanField(default=False, help_text=gettext_lazy("Unpack the zip file into the given subfolder. (It will be an error if the file is not a zip file; the filename is ignored.)"))
    is_sourcecode = models.BooleanField(default=False, help_text=gettext_lazy("The file is (or, if it is a zipfile to be unpacked: contains) source code"))
    include_in_solution_download = models.BooleanField(default=True, help_text=gettext_lazy("The file is (or, if it is a zipfile to be unpacked: its content) is included in \"full\" solution download .zip files"))



    _add_to_environment = True

    def path_relative_to_sandbox(self):
        filename = self.filename if self.filename else self.file.path
        return os.path.join(self.path.lstrip("/ "), os.path.basename(filename))

    def add_to_environment(self, env, path):
        if (self._add_to_environment):
            with open(os.path.join(env.tmpdir(), path), 'rb') as fd:
                env.add_source(path, fd.read())

    def run_file(self, env):
        """ Tries to unpack all necessary files.
        Fails if there is a clash with files submitted by the student.
        In that case, this function creates and returns the (failed) CheckerResult.
        Otherwise (if the unpacking succeeds), this function returns None.
        """
        clashes = []
        cleanpath = self.path.lstrip("/ ")
        if (self.unpack_zipfile):
            path = os.path.join(env.tmpdir(), cleanpath)
            unpack_zipfile_to(self.file.path, path,
                lambda n: clashes.append(os.path.join(cleanpath, n)),
                lambda f: self.add_to_environment(env, os.path.join(cleanpath, f)))
        else:
            filename = self.filename if self.filename else self.file.path
            source_path = os.path.join(cleanpath, os.path.basename(filename))
            path = os.path.join(env.tmpdir(), source_path)
            overridden = os.path.exists(path)
            copy_file(self.file.path, path)
            if overridden:
                clashes.append(os.path.join(self.path, os.path.basename(filename)))
            self.add_to_environment(env, source_path)

        if clashes:
            result = self.create_result(env)
            result.set_passed(False)
            result.set_log("These files already existed. Do NOT include them in your submissions:<br/><ul>\n" + "\n".join(["<li>%s</li>" % escape(f) for f in clashes]) + "</ul>")
            return result

        return None

class CreateFileChecker(CheckerWithFile):

    def title(self):
        """ Returns the title for this checker category. """
        return "Copy File"

    @staticmethod
    def description():
        """ Returns a description for this Checker. """
        return "Diese Prüfung wird bestanden, falls die Zieldatei nicht schon vorhanden ist (z.B.: vom Studenten eingereicht wurde)!"

    def run(self, env):
        copyfile_result = self.run_file(env)
        if copyfile_result:
            return copyfile_result
        result = self.create_result(env)
        result.set_passed(True)
        return result


    def show_publicly(self, passed):
        return super(CreateFileChecker, self).show_publicly(passed) or (not passed)

    def clean(self):
        super(CreateFileChecker, self).clean()
        if not (self.required and self.always and (not self.public)): raise ValidationError("Florian says: CreateFileCheckers have to be required, always, non-public")

from checker.admin import    CheckerInline, AlwaysChangedModelForm

class CopyForm(AlwaysChangedModelForm):
    def __init__(self, **args):
        """ override public and required """
        super(CopyForm, self).__init__(**args)
        self.fields["public"].initial = False
        self.fields["required"].initial = True

    def clean_filename(self):
        filename = self.cleaned_data['filename']
        if (not filename.strip()):
            if 'file' in self.cleaned_data:
                file = self.cleaned_data['file']
                return (os.path.basename(file.name))
            else:
                return None
        else:
            return filename



class CreateFileCheckerInline(CheckerInline):
    model = CreateFileChecker
    form = CopyForm
