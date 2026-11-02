"""
Deleting an account: everything the person made goes with it (characters and their chats, worldbooks, presets,
Bulba conversations, settings, keys, usage and activity records) plus the files those point to (pictures, chat
logs, voice clips, their own backgrounds and music). Files another account still uses are left alone.
"""
import logging
import os
import shutil

from django.conf import settings
from django.db import models, transaction

log = logging.getLogger(__name__)


def _file_fields(model):
    return [f.name for f in model._meta.get_fields() if isinstance(f, models.FileField)]


def _still_used(name, skip_ids):
    """Is this stored file still referenced by a character or template that isn't being deleted?"""
    from mainapp.models import Character, CharacterTemplate
    for model, exclude in ((Character, skip_ids), (CharacterTemplate, ())):
        query = models.Q()
        for field in _file_fields(model):
            query |= models.Q(**{field: name})
        if model.objects.filter(query).exclude(id__in=exclude).exists():
            return True
    return False


def _media_path(url_or_name):
    """A path inside MEDIA_ROOT for a stored name or a /media/ URL; None for anything outside it."""
    name = str(url_or_name or "")
    if name.startswith(settings.MEDIA_URL):
        name = name[len(settings.MEDIA_URL):]
    if not name or name.startswith(("/", "http")):
        return None
    root = os.path.realpath(settings.MEDIA_ROOT)
    path = os.path.realpath(os.path.join(root, name))
    return path if path.startswith(root + os.sep) else None


def delete_account(user):
    from mainapp import chats
    from mainapp.models import Character, ChatSettings, Worldbook

    characters = list(Character.objects.filter(author=user))
    char_ids = [c.id for c in characters]
    files = set()
    for character in characters:
        for field in _file_fields(Character):
            name = getattr(character, field).name
            if name and not _still_used(name, char_ids):
                files.add(name)
        for chat in character.chats.all():
            if chat.log_file:
                files.add(chat.log_file.name)
            try:
                messages = chats.read(chat).get("messages") or []
            except Exception:  # an unreadable log still goes
                messages = []
            for m in messages:
                audio = (chats._extras(m).get("audio") or {}).get("url") if isinstance(m, (list, tuple)) else None
                if audio:
                    files.add(audio)
    for book in Worldbook.objects.filter(author=user):
        if book.json_file:
            files.add(book.json_file.name)
    settings_obj = ChatSettings.objects.filter(author=user).first()
    if settings_obj and settings_obj.json_file:
        files.add(settings_obj.json_file.name)
    photo = getattr(user, "photo", None)
    default_photo = str(getattr(settings, "DEFAULT_USER_IMAGE", "")).replace(settings.MEDIA_URL, "", 1)
    if photo and photo.name and photo.name != default_photo:
        files.add(photo.name)
    files.add(f"chat_settings2/chat_settings2_{user.id}.json")
    folders = [os.path.join(settings.MEDIA_ROOT, kind, "custom", f"u{user.id}") for kind in ("backgrounds", "music")]

    with transaction.atomic():
        Character.objects.filter(id__in=char_ids).delete()   # their chats go with them
        Worldbook.objects.filter(author=user).delete()        # after the characters that used them
        ChatSettings.objects.filter(author=user).delete()
        user.delete()                                          # presets, keys, Bulba, usage, activity: cascade

    for name in files:  # after the database, so a failed delete never leaves records pointing at missing files
        path = _media_path(name)
        if path and os.path.isfile(path):
            try:
                os.remove(path)
            except OSError as e:
                log.warning("Could not remove %s: %s", path, e)
    for folder in folders:
        shutil.rmtree(folder, ignore_errors=True)
