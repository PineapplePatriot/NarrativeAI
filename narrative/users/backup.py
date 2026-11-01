"""
A backup the project's owners download from the stats page (Railway's own backups need its Pro plan): one zip
with a consistent copy of the database (SQLite's backup API, safe while the app is running) and the uploaded
files. What's in it: every account, chat and setting, emails, and saved API keys, which are encrypted with
DJANGO_SECRET_KEY (unreadable without it). Keep the zip private. Restoring: docs/DEPLOY.md.
"""
import os
import sqlite3
import tempfile
import zipfile

from django.conf import settings
from django.utils import timezone


def make_zip():
    """An open temporary file holding the zip (already unlinked: it goes away when closed), and its name."""
    from django.db import connection
    media = str(settings.MEDIA_ROOT)
    tmp_dir = tempfile.mkdtemp()
    try:
        copy = os.path.join(tmp_dir, "db.sqlite3")
        connection.ensure_connection()
        target = sqlite3.connect(copy)
        try:
            connection.connection.backup(target)  # a consistent copy while the app keeps running
        finally:
            target.close()
        out = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as z:
            z.write(copy, "db.sqlite3")
            if os.path.isdir(media):
                for folder, _, files in os.walk(media):
                    for f in files:
                        path = os.path.join(folder, f)
                        z.write(path, os.path.join("media", os.path.relpath(path, media)))
            z.writestr("README.txt", "Narrative AI backup, " + timezone.now().strftime("%Y-%m-%d %H:%M UTC") +
                       ".\nRestore: see docs/DEPLOY.md, \"Backups\". Keep this file private: it has every account.\n")
        out.flush()
        out.seek(0)
        os.unlink(out.name)  # the open handle keeps it readable; nothing is left on disk afterwards
        return out, f"narrativeai-backup-{timezone.now().strftime('%Y-%m-%d-%H%M')}.zip"
    finally:
        for f in os.listdir(tmp_dir):
            os.remove(os.path.join(tmp_dir, f))
        os.rmdir(tmp_dir)
