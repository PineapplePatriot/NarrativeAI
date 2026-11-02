"""
Puts a backup from the stats page ("Download backup") back: the database and the uploaded files.

    python manage.py restore_backup /path/to/narrativeai-backup.zip
    python manage.py restore_backup "https://…direct download link…"

Everything now on the server is replaced by the backup's contents (files only in the backup are added; files
uploaded after it stay). Redeploy the service afterwards so every request reads the restored database.
"""
import os
import shutil
import sqlite3
import tempfile
import zipfile

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Restore the database and uploads from a backup zip (a path or a direct download link)."

    def add_arguments(self, parser):
        parser.add_argument("source")
        parser.add_argument("--yes", action="store_true", help="Don't ask for confirmation")

    def handle(self, source, yes=False, **options):
        tmp = tempfile.mkdtemp()
        try:
            path = source
            if source.startswith(("http://", "https://")):
                path = os.path.join(tmp, "backup.zip")
                self.stdout.write("Downloading…")
                with requests.get(source, stream=True, timeout=300) as r:
                    r.raise_for_status()
                    with open(path, "wb") as f:
                        for chunk in r.iter_content(1 << 20):
                            f.write(chunk)
            if not zipfile.is_zipfile(path):
                raise CommandError("That isn't a zip file (for a share link, make sure it's a direct download).")
            with zipfile.ZipFile(path) as z:
                if "db.sqlite3" not in z.namelist():
                    raise CommandError("That zip isn't a Narrative AI backup (no db.sqlite3 in it).")
                if not yes and input("This replaces the live database with the backup. Type yes to go on: ") != "yes":
                    raise CommandError("Stopped; nothing changed.")
                z.extractall(tmp)
            from django.db import connection
            connection.ensure_connection()
            source_db = sqlite3.connect(os.path.join(tmp, "db.sqlite3"))
            try:
                source_db.backup(connection.connection)  # into the live database, safe while the app runs
            finally:
                source_db.close()
            media_in = os.path.join(tmp, "media")
            if os.path.isdir(media_in):
                shutil.copytree(media_in, str(settings.MEDIA_ROOT), dirs_exist_ok=True)
            self.stdout.write(self.style.SUCCESS("Restored. Now redeploy the service (Railway: Deployments → ⋮ → Redeploy)."))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
