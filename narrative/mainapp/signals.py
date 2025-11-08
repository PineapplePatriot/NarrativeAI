# import json
# from datetime import datetime
# from django.db.models.signals import post_save
# from django.dispatch import receiver
# from django.utils.text import slugify
# from django.core.files.base import ContentFile
# from django.contrib.auth import get_user_model
# from mainapp.models import Character, CharacterTemplate
#
# User = get_user_model()
#
# @receiver(post_save, sender=User)
# def create_default_characters(sender, instance, created, **kwargs):
#     if not created:
#         return
#
#     templates = CharacterTemplate.objects.all()
#     for template in templates:
#         # Генерація унікального slug
#         slug_base = slugify(template.name)
#         slug = slug_base
#         i = 1
#         while Character.objects.filter(slug=slug).exists():
#             slug = f"{slug_base}-{i}"
#             i += 1
#
#         # Створюємо character
#         character = Character.objects.create(
#             name=template.name,
#             slug=slug,
#             description=template.description,
#             scenario=template.scenario,
#             initial_message=template.initial_message,
#             photo_neutral=template.photo_neutral,
#             photo_happy=template.photo_happy,
#             photo_sad=template.photo_sad,
#             photo_angry=template.photo_angry,
#             photo_surprised=template.photo_surprised,
#             photo_scared=template.photo_scared,
#             photo_confused=template.photo_confused,
#             photo_calm=template.photo_calm,
#             photo_scheming=template.photo_scheming,
#             author=instance,
#             is_default=True
#         )
#
#         # Формуємо ім'я файлу: username_slug_chat.json
#         username_safe = slugify(instance.username)
#         filename = f"{username_safe}_{slug}_chat.json"
#
#         # Створюємо JSON з initial_message
#         initial_msg = [
#             "assistant",
#             datetime.now().strftime("%H:%M"),
#             template.initial_message,
#             "neutral"
#         ]
#         chat_data = {"messages": [initial_msg]}
#         json_content = json.dumps(chat_data, ensure_ascii=False, indent=2)
#         character.chat_log_file.save(filename, ContentFile(json_content), save=True)
#

import json
from datetime import datetime
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.text import slugify
from django.core.files.base import ContentFile
from django.contrib.auth import get_user_model
from mainapp.models import Character, CharacterTemplate

User = get_user_model()


@receiver(post_save, sender=User)
def create_default_characters(sender, instance, created, **kwargs):
    """
    Створюємо дефолтних персонажів для нового користувача.
    Якщо персонажі вже існують, повторно не створюємо.
    """
    if not created:
        return  # Додаємо лише при створенні нового користувача

    templates = CharacterTemplate.objects.all()
    for template in templates:
        # Перевіряємо, чи користувач вже має цього дефолтного персонажа
        if Character.objects.filter(author=instance, name=template.name, is_default=True).exists():
            continue  # Уже є, пропускаємо

        # Генерація унікального slug
        slug_base = slugify(template.name)
        slug = slug_base
        i = 1
        while Character.objects.filter(slug=slug).exists():
            slug = f"{slug_base}-{i}"
            i += 1

        # Створюємо нового Character
        character = Character.objects.create(
            name=template.name,
            slug=slug,
            description=template.description,
            scenario=template.scenario,
            initial_message=template.initial_message,
            photo_neutral=template.photo_neutral,
            photo_happy=template.photo_happy,
            photo_sad=template.photo_sad,
            photo_angry=template.photo_angry,
            photo_surprised=template.photo_surprised,
            photo_scared=template.photo_scared,
            photo_confused=template.photo_confused,
            photo_calm=template.photo_calm,
            photo_scheming=template.photo_scheming,
            author=instance,
            is_default=True
        )

        # Формуємо ім'я файлу для chat log
        username_safe = slugify(instance.username)
        filename = f"{username_safe}_{slug}_chat.json"

        # Створюємо JSON з initial_message
        initial_msg = [
            "assistant",
            datetime.now().strftime("%H:%M"),
            template.initial_message,
            "neutral"
        ]
        #chat_data = {"messages": [initial_msg]}
        chat_data = [initial_msg]
        json_content = json.dumps(chat_data, ensure_ascii=False, indent=2)

        # Зберігаємо файл chat log
        character.chat_log_file.save(filename, ContentFile(json_content), save=True)
