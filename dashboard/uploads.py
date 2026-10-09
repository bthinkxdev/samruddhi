from __future__ import annotations

import mimetypes
import os
import uuid

from django import forms
from django.core import signing
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile

RETAINED_UPLOAD_DIR = "tmp/retained-uploads"
_TOKEN_SALT = "dashboard.retained-upload"
_TOKEN_MAX_AGE = 60 * 60 * 24  


class RetainedUpload:
    """What the template needs to render one field's hidden token and preview."""

    def __init__(self, form: "RetainUploadsMixin", field_name: str):
        self._form = form
        self._field_name = field_name
        self.name = ""
        self.url = ""

    @property
    def token(self):
        return self._form[RetainUploadsMixin.token_field_name(self._field_name)]


class RetainUploadsMixin:
    """Mix into a (Model)Form and list the file fields in ``retained_upload_fields``."""

    retained_upload_fields: tuple[str, ...] = ()

    @staticmethod
    def token_field_name(field_name: str) -> str:
        return f"{field_name}_retained"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.retained = {}
        self._retained_paths: dict[str, str] = {}
        for name in self.retained_upload_fields:
            self.fields[self.token_field_name(name)] = forms.CharField(
                required=False, widget=forms.HiddenInput
            )
            self.retained[name] = RetainedUpload(self, name)
        if self.is_bound:
            self._restore_retained_uploads()

    # -- token helpers -------------------------------------------------------

    @staticmethod
    def _path_from_token(token: str) -> str:
        if not token:
            return ""
        try:
            path = signing.loads(token, salt=_TOKEN_SALT, max_age=_TOKEN_MAX_AGE)
        except signing.BadSignature:
            return ""
        if not isinstance(path, str) or not path.startswith(RETAINED_UPLOAD_DIR + "/"):
            return ""
        return path if default_storage.exists(path) else ""

    def _set_data(self, key: str, value: str) -> None:
        data = self.data.copy()
        data[key] = value
        self.data = data

    def _remember(self, name: str, path: str) -> None:
        self._retained_paths[name] = path
        self.retained[name].name = os.path.basename(path)
        self.retained[name].url = default_storage.url(path)

    # -- restore on the next submit -----------------------------------------

    def _restore_retained_uploads(self) -> None:
        for name in self.retained_upload_fields:
            file_key = self.add_prefix(name)
            token_key = self.add_prefix(self.token_field_name(name))
            path = self._path_from_token(self.data.get(token_key, ""))
            if not path:
                continue
            cleared = bool(self.data.get(f"{file_key}-clear"))
            if file_key in self.files or cleared:
                #a newly chosen file (or "clear") replaces the parked one
                default_storage.delete(path)
                self._set_data(token_key, "")
                continue
            with default_storage.open(path, "rb") as fh:
                content = fh.read()
            filename = os.path.basename(path)
            content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
            files = self.files.copy()
            files[file_key] = SimpleUploadedFile(filename, content, content_type)
            self.files = files
            self._remember(name, path)

    # -- park uploads when validation fails ---------------------------------

    def full_clean(self):
        super().full_clean()
        if self.is_bound and self._errors:
            self.retain_uploads()

    def retain_uploads(self) -> None:
        """
        Park this form's valid uploads. Runs automatically when the form itself
        fails; views call it directly when the page fails elsewhere (another
        form or formset) while this form was valid.
        """
        if not self.is_bound:
            return
        self.errors  # make sure validation has run
        for name in self.retained_upload_fields:
            file_key = self.add_prefix(name)
            token_key = self.add_prefix(self.token_field_name(name))
            if name in self._errors:
                #an invalid file is not worth keeping; drop any parked copy too
                if name in self._retained_paths:
                    default_storage.delete(self._retained_paths.pop(name))
                self._set_data(token_key, "")
                self.retained[name].name = self.retained[name].url = ""
                continue
            if name in self._retained_paths:
                continue  #  its token is still in the data
            upload = self.files.get(file_key)
            if not upload:
                continue
            upload.seek(0)
            filename = os.path.basename(upload.name) or "upload"
            path = default_storage.save(
                f"{RETAINED_UPLOAD_DIR}/{uuid.uuid4().hex}/{filename}",
                ContentFile(upload.read()),
            )
            self._set_data(token_key, signing.dumps(path, salt=_TOKEN_SALT))
            self._remember(name, path)


    def save(self, commit=True):
        obj = super().save(commit=commit)
        if commit:
            self.discard_retained_uploads()
        return obj

    def discard_retained_uploads(self) -> None:
        for path in self._retained_paths.values():
            default_storage.delete(path)
        self._retained_paths.clear()
