from django.utils.translation import gettext_lazy
from django.forms.models import ModelForm, inlineformset_factory, BaseInlineFormSet
from django import forms
import zipfile
from utilities.mimetypes import guess_mime_type_with_fallback as guess_mime_type
import re

from solutions.models import Solution, SolutionFile
from utilities import encoding
from functools import reduce

ziptype_re = re.compile(r'^application/(zip|x-zip|x-zip-compressed|x-compressed)$')
tartype_re = re.compile(r'^application/(tar|x-tar|x-tar-compressed)$')

def contains_NUL_char(bytestring):
    return encoding.get_unicode(bytestring).find("\x00") >= 0

class SolutionFileForm(ModelForm):
    class Meta:
        model = SolutionFile
        exclude = ('mime_type',)

    def clean_file(self):
        data = self.cleaned_data['file']
        task = self.cleaned_data['solution'].task
        max_file_size_kib = task.max_file_size
        max_file_size = 1024 * max_file_size_kib
        if data:
            contenttype = guess_mime_type(data.name) # don't rely on the browser: data.content_type could be wrong or empty
            if contenttype.startswith("text"):
                content = data.read()
                # undo the consuming the read method has done
                data.seek(0)
                if contains_NUL_char(content):
                    raise forms.ValidationError(gettext_lazy("The plain text file '%(file)s' contains a NUL character, which is not supported." %{'file':data.name}))
            if ziptype_re.match(contenttype):
                try:
                    zip = zipfile.ZipFile(data)
                    if zip.testzip():
                        raise forms.ValidationError(gettext_lazy('The zip file seems to be corrupt.'))
                    if sum(fileinfo.file_size for fileinfo in zip.infolist()) > (max_file_size * min(len(zip.infolist()), 8)):
                        # Protect against zip bombs
                        raise forms.ValidationError(gettext_lazy('The zip file is too big.'))
                    for fileinfo in zip.infolist():
                        filename = fileinfo.filename
                        mime_type = guess_mime_type(filename)
                        ignorred = SolutionFile.ignorred_file_names_re.search(filename)
                        is_text_file = not ignorred and mime_type and mime_type.startswith("text")
                        if is_text_file and contains_NUL_char(zip.read(filename)):
                            raise forms.ValidationError(gettext_lazy("The plain text file '%(file)s' in this zip file contains a NUL character, which is not supported." %{'file':filename}))
                        # check whole zip instead of contained files
                        #if fileinfo.file_size > max_file_size:
                        #    raise forms.ValidationError(gettext_lazy("The file '%(file)s' is bigger than %(size)KiB which is not suported." %{'file':fileinfo.filename, 'size':max_file_size_kib}))
                except forms.ValidationError:
                    raise
                except:
                    raise forms.ValidationError(gettext_lazy('Uhoh - something unexpected happened.'))
            elif tartype_re.match(contenttype):
                raise forms.ValidationError(gettext_lazy('Tar files are not supported, please upload the files individually or use a zip file.'))
            if data.size > max_file_size:
                raise forms.ValidationError(gettext_lazy("The file '%(file)s' is bigger than %(size)d KiB which is not supported." %{'file':data.name, 'size':max_file_size_kib}))
            return data

class MyBaseInlineFormSet(BaseInlineFormSet):
    def clean(self):
        super(MyBaseInlineFormSet, self).clean()
        if not reduce(lambda x, y: x + y.changed_data, self.forms, []):
            raise forms.ValidationError(gettext_lazy('You must choose at least one file.'))

SolutionFormSet = inlineformset_factory(Solution, SolutionFile, form=SolutionFileForm, formset=MyBaseInlineFormSet, can_delete=False, extra=1)
ModelSolutionFormSet = inlineformset_factory(Solution, SolutionFile, form=SolutionFileForm, formset=MyBaseInlineFormSet, can_delete=False, extra=1)
