# --- Standard library ---
import json
import os
import requests
import traceback
from datetime import datetime

# --- Django core ---
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.files.base import ContentFile
from django.http import JsonResponse, HttpResponseNotFound
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils.text import slugify
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import (
    TemplateView, ListView, DetailView,
    FormView, CreateView, UpdateView
)
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin

# --- Local imports ---
from mainapp.models import Character, Worldbook, ChatSettings
from .forms import AddCharacterForm, UploadFileForm
from .models import Character, Worldbook, ChatSettings
from .utils import build_ai_request

#from django.contrib.auth.decorators import login_required
#from .utils import build_ai_request



#def index_page(request):
#    return render(request, 'index.html')

@login_required
def index_page(request):
    # Беремо лише дефолтні персонажі для поточного користувача
    default_characters = Character.objects.filter(author=request.user, is_default=True)

    context = {
        'characters': default_characters
    }
    return render(request, 'index.html', context)



def characters_list(request):
    return render(request, 'mainapp/characters.html')


@login_required
def chat(request, slug):
    character = get_object_or_404(Character, slug=slug)

    #--- Дістаємо ApiConfig користувача ---
    api_config = getattr(request.user, "api_config", None)
    if not api_config or not api_config.chat_key:
        return JsonResponse({"error": "API key is not configured for this user."}, status=400)

    OPENROUTER_API_KEY = api_config.chat_key
    MODEL_NAME = api_config.or_model or "nousresearch/hermes-3-llama-3.1-405b"

    # --- Chat log file ---
    if character.chat_log_file:
        chat_file_path = character.chat_log_file.path
    else:
        username = request.user.username
        filename = f"{username}_{character.slug}_chat.json"
        #filename = f"{character.slug}_chat.json"
        chat_dir = os.path.join(settings.MEDIA_ROOT, "chat_logs")
        os.makedirs(chat_dir, exist_ok=True)
        chat_file_path = os.path.join(chat_dir, filename)
        character.chat_log_file.name = f"chat_logs/{filename}"
        character.save()

    #--- Load messages & fix old logs ---
    # def load_messages():
    #     if os.path.exists(chat_file_path):
    #         with open(chat_file_path, "r", encoding="utf-8") as f:
    #             try:
    #                 messages = json.load(f)
    #                 fixed_messages = []
    #                 for msg in messages:
    #                     if len(msg) == 3:
    #                         role, time, text = msg
    #                         fixed_messages.append((role, time, text, "neutral"))
    #                     elif len(msg) >= 4:
    #                         fixed_messages.append(tuple(msg[:4]))
    #                 return fixed_messages
    #             except json.JSONDecodeError:
    #                 return []
    #     else:
    #         return []

    def load_messages():
        if os.path.exists(chat_file_path):
            with open(chat_file_path, "r", encoding="utf-8") as f:
                try:
                    messages_list = json.load(f)
                    fixed_messages = []
                    for msg in messages_list:
                        if len(msg) == 3:
                            role, time, text = msg
                            fixed_messages.append((role, time, text, "neutral"))
                        elif len(msg) >= 4:
                            fixed_messages.append(tuple(msg[:4]))
                    return fixed_messages
                except json.JSONDecodeError:
                    return []
        else:
            return []

    # --- Save messages to file ---
    def save_messages(messages):
        with open(chat_file_path, "w", encoding="utf-8") as f:
            json.dump(messages, f, ensure_ascii=False, indent=2)

    messages = load_messages()

    # --- Initial assistant message ---
    if not messages and character.initial_message:
        messages.append(("assistant", datetime.now().strftime("%H:%M"), character.initial_message, "neutral"))
        save_messages(messages)

    # --- POST request ---
    if request.method == "POST":
        data = json.loads(request.body)
        action = data.get("action", "chat")

        # Handle edit action
        if action == "edit":
            try:
                index = int(data.get("index"))
                new_text = data.get("text", "").strip()

                if not new_text:
                    return JsonResponse({"success": False, "error": "Message cannot be empty"})

                if 0 <= index < len(messages):
                    # Update the message text, keep other fields
                    role, time, old_text, emotion = messages[index]
                    messages[index] = (role, time, new_text, emotion)
                    save_messages(messages)
                    return JsonResponse({"success": True})
                else:
                    return JsonResponse({"success": False, "error": "Invalid message index"})

            except (ValueError, KeyError) as e:
                return JsonResponse({"success": False, "error": "Invalid request data"})

        # Handle delete action
        elif action == "delete":
            try:
                index = int(data.get("index"))

                if 0 <= index < len(messages):
                    # Delete message and all subsequent messages
                    messages = messages[:index]
                    save_messages(messages)
                    return JsonResponse({"success": True})
                else:
                    return JsonResponse({"success": False, "error": "Invalid message index"})

            except (ValueError, KeyError) as e:
                return JsonResponse({"success": False, "error": "Invalid request data"})

        # Handle regular chat message
        else:
            user_message = data.get("message", "").strip()
            if user_message:
                messages.append(("user", datetime.now().strftime("%H:%M"), user_message, "neutral"))

                # --- Prepare history for API ---
                api_messages = []

                # Add system message if character has one
                if hasattr(character, 'system_prompt') and character.system_prompt:
                    api_messages.append({"role": "system", "content": character.system_prompt})

                # Add conversation history
                for role, time, text, emotion in messages:
                    if role == "user":
                        api_messages.append({"role": "user", "content": text})
                    elif role == "assistant":
                        api_messages.append({"role": "assistant", "content": text})

                try:
                    try:
                        chat_settings = ChatSettings.objects.get(author=request.user)
                    except ChatSettings.DoesNotExist:
                        chat_settings = None
                #=================================
                    #prompt = build_ai_request(request.user, character, chat_settings)
                    #prompt = build_ai_request(request.user, character, chat_settings, worldbook_slug=character.slug)
                    print("USER_MESSAGE", user_message)
                    worldbook = None
                    if character.worldbook and character.worldbook.author == request.user:
                        worldbook = character.worldbook

                    if worldbook:
                        worldbook_slug = worldbook.slug
                    else:
                        worldbook_slug = None
                    prompt = build_ai_request(request.user, character, chat_settings, worldbook_slug=worldbook_slug, message=user_message)
                    # --- Формуємо структуровані system messages ---
                    system_messages = []

                    if "Core" in prompt and prompt["Core"]:
                        system_messages.append({
                            "role": "system",
                            "content": f"[CORE SETTINGS]\n{json.dumps(prompt['Core'], indent=2, ensure_ascii=False)}"
                        })

                    if "SystemPrompts" in prompt and prompt["SystemPrompts"]:
                        system_messages.append({
                            "role": "system",
                            "content": f"[SYSTEM PROMPTS]\n{json.dumps(prompt['SystemPrompts'], indent=2, ensure_ascii=False)}"
                        })

                    if "CharacterDescription" in prompt and prompt["CharacterDescription"]:
                        system_messages.append({
                            "role": "system",
                            "content": f"[CHARACTER DESCRIPTION]\n{json.dumps(prompt['CharacterDescription'], indent=2, ensure_ascii=False)}"
                        })

                    if "UserPersona" in prompt and prompt["UserPersona"]:
                        system_messages.append({
                            "role": "system",
                            "content": f"[USER PERSONA]\n{json.dumps(prompt['UserPersona'], indent=2, ensure_ascii=False)}"
                        })

                    if "ChatHistory" in prompt and prompt["ChatHistory"]:
                        system_messages.append({
                            "role": "system",
                            "content": f"[CHAT HISTORY]\n{json.dumps(prompt['ChatHistory'], indent=2, ensure_ascii=False)}"
                        })

                    if "LastUserMessage" in prompt and prompt["LastUserMessage"]:
                        system_messages.append({
                            "role": "system",
                            "content": f"[LAST USER MESSAGE]\n{json.dumps(prompt['LastUserMessage'], indent=2, ensure_ascii=False)}"
                        })

                    if "WorldbookMatches" in prompt and prompt["WorldbookMatches"]:
                        system_messages.append({
                            "role": "system",
                            "content": f"[WORLDBOOK MATCHES]\n{json.dumps(prompt['WorldbookMatches'], indent=2, ensure_ascii=False)}"
                        })

                    # --- Підготовка payload: system_messages перед api_messages ---
                    payload = {
                        "model": MODEL_NAME,
                        "messages": system_messages + api_messages,  # <-- Останнім буде user-повідомлення
                        **prompt.get("Core", {})
                    }

                    # --- Друк payload у консоль ---
                    print("=== OpenRouter API Request ===")
                    #print(json.dumps(payload, indent=2, ensure_ascii=False))
                    print("================================")

                    # --- Виклик API ---
                    response = requests.post(
                        url="https://openrouter.ai/api/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                            "Content-Type": "application/json",
                        },
                        json=payload,
                        timeout=15
                    )
                    response.raise_for_status()
                    result = response.json()
                    reply = result["choices"][0]["message"]["content"]
                except Exception as e:
                    print(f"Error generating reply: {e}")
                    reply = "Вибачте, сталася помилка при генерації відповіді."

                # --- Classify emotion ---
                try:
                    emo_messages = [
                        {
                            "role": "system",
                            "content": (
                                "Classify the following text into exactly one word "
                                "from [neutral, happy, sad, angry, surprised, scared, confused, calm, scheming]. "
                                "Output only the word."
                            )
                        },
                        {"role": "user", "content": reply}
                    ]
                    emo_response = requests.post(
                        url="https://openrouter.ai/api/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                            "Content-Type": "application/json",
                        },
                        data=json.dumps({
                            #"model": "nousresearch/hermes-3-llama-3.1-405b",
                            "model": MODEL_NAME,
                            "messages": emo_messages,
                            "max_tokens": 5,
                            "temperature": 0.0
                        }),
                        timeout=10
                    )
                    emo_response.raise_for_status()
                    emo_result = emo_response.json()
                    raw_emotion = emo_result["choices"][0]["message"]["content"].strip().lower()
                    emotion = raw_emotion.split()[0]  # беремо перше слово
                    if emotion not in ["neutral", "happy", "sad", "angry", "surprised", "scared", "confused", "calm",
                                       "scheming"]:
                        emotion = "neutral"
                except Exception as e:
                    print(f"Error classifying emotion: {e}")
                    emotion = "neutral"

                # --- Append assistant message with emotion ---
                messages.append(("assistant", datetime.now().strftime("%H:%M"), reply, emotion))

                # --- Select photo for emotion ---
                emotion_field = f"photo_{emotion}"
                #photo_url = getattr(character, emotion_field).url if getattr(character, emotion_field) else None
                photo_attr = getattr(character, emotion_field, None)
                photo_url = photo_attr.url if photo_attr else None

                # --- Save log ---
                save_messages(messages)

                return JsonResponse({
                    "reply": reply,
                    "emotion": emotion,
                    "photo_url": photo_url,
                })

    # --- GET request ---
    last_emotion = messages[-1][3] if messages else "neutral"
    emotion_field = f"photo_{last_emotion}"
    #photo_url = getattr(character, emotion_field).url if getattr(character, emotion_field) else None
    photo_attr = getattr(character, f"photo_{last_emotion}", None)
    # fallback на photo_neutral
    if photo_attr and hasattr(photo_attr, 'url'):
        photo_url = photo_attr.url
    elif character.photo_neutral:
        photo_url = character.photo_neutral.url
    else:
        photo_url = None

    context = {
        "messages": messages,
        "character": character,
        "photo_url": photo_url,
        "photo_neutral": photo_url
    }

    return render(request, "mainapp/chat_page.html", context)



@login_required
def chat_settings(request):
    # --- POST-запит: збереження налаштувань ---
    if request.method == "POST":
        try:
            if not request.body:
                return JsonResponse({"status": "error", "message": "Empty request body"}, status=400)

            try:
                data = json.loads(request.body.decode("utf-8"))
            except json.JSONDecodeError as e:
                return JsonResponse({"status": "error", "message": f"Invalid JSON: {str(e)}"}, status=400)

            # Переконаємося, що структура правильна
            if "prompt" not in data or not isinstance(data["prompt"], dict):
                data["prompt"] = {}
            if "mood" not in data["prompt"]:
                data["prompt"]["mood"] = "balanced"  # дефолт

            settings_json = json.dumps(data, indent=2)

            # Визначаємо користувача та файл
            if request.user.is_authenticated:
                chat_settings_obj, _ = ChatSettings.objects.get_or_create(author=request.user)
                file_name = f"{request.user.username}_settings.json"
            else:
                chat_settings_obj = ChatSettings.objects.create(author=None)
                file_name = "anonymous_settings.json"

            # Видаляємо старий файл, якщо існує
            if chat_settings_obj.json_file:
                chat_settings_obj.json_file.delete(save=False)

            # Зберігаємо новий JSON-файл
            chat_settings_obj.json_file.save(
                file_name,
                ContentFile(settings_json.encode("utf-8")),
                save=True
            )

            return JsonResponse({"status": "ok"})

        except Exception:
            print(traceback.format_exc())
            return JsonResponse({"status": "error", "message": "Failed to save settings"}, status=400)

    # --- GET-запит: зчитуємо налаштування для шаблону ---
    settings_data = {"prompt": {"mood": "balanced"}}  # дефолт
    try:
        if request.user.is_authenticated:
            chat_settings_obj = ChatSettings.objects.filter(author=request.user).first()
        else:
            chat_settings_obj = ChatSettings.objects.filter(author=None).first()

        if chat_settings_obj and chat_settings_obj.json_file:
            file_path = chat_settings_obj.json_file.path
            if os.path.exists(file_path):
                with open(file_path, "r", encoding="utf-8") as f:
                    file_data = json.load(f)
                    # переконаємося, що структура правильна
                    if "prompt" in file_data and isinstance(file_data["prompt"], dict):
                        settings_data = file_data
                    else:
                        settings_data["prompt"].update(file_data.get("prompt", {}))
            else:
                print(f"Settings file not found: {file_path}")

    except Exception:
        print("Failed to load settings:", traceback.format_exc())

    #return render(request, "mainapp/chat_settings_v1_06102015.html", {
    #    "settings": settings_data
    # nsfw_custom_json = json.dumps(settings_data["nsfw"]["custom"] or {})
    # prompts_custom_json = json.dumps(settings_data["prompts"]["custom"] or {})
    nsfw_custom_json = json.dumps((settings_data.get("nsfw", {}) or {}).get("custom", {}) or {})
    prompts_custom_json = json.dumps((settings_data.get("prompts", {}) or {}).get("custom", {}) or {})
    settings_data["nsfw_custom_json"]= nsfw_custom_json
    settings_data["prompts_custom_json"] = prompts_custom_json
    print(settings_data)
    return render(request, "mainapp/fixed_chat_settings_new.html", {
        "settings": settings_data
    })


@login_required
def worldbook_create(request):
    if request.method == "POST":
        try:
            # Парсимо JSON із тіла запиту
            data = json.loads(request.body.decode("utf-8"))
            print(data)
            # Отримуємо title та slug
            title = data.get("title", "Untitled")
            slug = data.get("id")  # у data ключ "id" відповідає slug

            if not slug:
                return JsonResponse({"status": "error", "message": "Missing 'id' for slug"}, status=400)

            # Створюємо об’єкт Worldbook
            wb = Worldbook(title=title, slug=slug, description=data.get("description", ""))

            # Формуємо ім'я файлу
            if request.user.is_authenticated:
                username = request.user.username
                file_name = f"{username}_{slug}.json"
                wb.author = request.user
            else:
                file_name = f"{slug}.json"

            # Створюємо JSON-файл та зберігаємо у поле json_file
            json_content = json.dumps(data, ensure_ascii=False, indent=2)
            wb.json_file.save(file_name, ContentFile(json_content))

            wb.save()

            return JsonResponse({"status": "ok", "worldbook_id": wb.id, "title": wb.title})
        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)}, status=400)
    else:
        # GET-запит -> показуємо форму
        return render(request, "mainapp/worldbook_create_new.html")




# @login_required
# def worldbook_detail(request, slug):
#     # Дістаємо лише worldbook-и, які належать залогіненому користувачу
#     wb = get_object_or_404(Worldbook, slug=slug, author=request.user)
#
#     if request.method == 'POST':
#         try:
#             data = json.loads(request.body)
#             entries = data.get('entries', [])
#         except json.JSONDecodeError:
#             return JsonResponse({"error": "Invalid JSON"}, status=400)
#
#         try:
#             # Зберігаємо всі entries в json_file
#             json_content = json.dumps({"entries": entries}, indent=2, ensure_ascii=False)
#             wb.json_file.save(f"{wb.slug}.json", ContentFile(json_content))
#             wb.save()
#         except Exception as e:
#             return JsonResponse({"error": str(e)}, status=500)
#
#         return JsonResponse({"status": "ok", "count": len(entries)})
#
#     # --- GET-запит ---
#     entries_data = []
#     if wb.json_file:
#         try:
#             wb.json_file.open('r')
#             file_content = wb.json_file.read()
#             wb.json_file.close()
#             json_data = json.loads(file_content)
#             entries_data = json_data.get('entries', []) if isinstance(json_data, dict) else []
#         except Exception:
#             entries_data = []
#
#     worldbook_json = {
#         "id": wb.slug,
#         "title": wb.title,
#         "entries": entries_data
#     }
#
#     return render(request, 'mainapp/worldbook_detail_new2.html', {
#         'json_data': json.dumps(worldbook_json)
#     })
#

@login_required
def worldbook_detail(request, slug):
    wb = get_object_or_404(Worldbook, slug=slug, author=request.user)

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            entries = data.get('entries', [])
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        try:
            # серіалізуємо entries у JSON
            json_content = json.dumps({"entries": entries}, indent=2, ensure_ascii=False)

            # якщо файл вже існує — перезаписуємо його
            if wb.json_file:
                wb.json_file.open('w')
                wb.json_file.write(json_content)
                wb.json_file.close()
            else:
                wb.json_file.save(f"{wb.slug}.json", ContentFile(json_content))

            wb.save()
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

        return JsonResponse({"status": "ok", "count": len(entries)})

    # --- GET-запит ---
    entries_data = []
    if wb.json_file:
        try:
            wb.json_file.open('r')
            file_content = wb.json_file.read()
            wb.json_file.close()
            json_data = json.loads(file_content)
            entries_data = json_data.get('entries', []) if isinstance(json_data, dict) else []
        except Exception:
            entries_data = []

    worldbook_json = {
        "id": wb.slug,
        "title": wb.title,
        "entries": entries_data
    }

    return render(request, 'mainapp/worldbook_detail_new2.html', {
        'json_data': json.dumps(worldbook_json)
    })



@login_required
def worldbook_list(request):
    # Вибираємо лише worldbook-и поточного користувача
    worldbooks = Worldbook.objects.filter(author=request.user)  # автоматично відсортовані завдяки Meta.ordering
    return render(request, "mainapp/worldbook_list_new.html", {"worldbooks": worldbooks})



class CharactersList(LoginRequiredMixin, ListView):
    model = Character
    template_name = 'mainapp/character_list_proba.html'
    context_object_name = 'characters'
    title_page = "Characters List"
    # paginate_by = 3

    def get_queryset(self):
        # повертаємо тільки персонажів, створених поточним користувачем
        return Character.objects.filter(author=self.request.user)




class AddCharacter(LoginRequiredMixin, CreateView):
    form_class = AddCharacterForm
    template_name = "mainapp/add_character_proba.html"
    title_page = "Add Character"
    success_url = reverse_lazy('characters_list')

    def form_valid(self, form):
        a = form.save(commit=False)
        a.author = self.request.user
        # Формуємо slug: username + "-" + slugified name
        username = self.request.user.username
        base_slug = slugify(a.name)
        a.slug = f"{username}-{base_slug}"
        a.save()
        return super().form_valid(form)





class UpdateCharacter(LoginRequiredMixin, UpdateView):
    model = Character
    form_class = AddCharacterForm
    template_name = "mainapp/add_character_proba.html"
    title_page = "Edit Character"
    slug_field = "slug"
    slug_url_kwarg = "slug"

    # --- Обмежуємо queryset лише персонажами залогіненого користувача ---
    def get_queryset(self):
        return Character.objects.filter(author=self.request.user)

    # --- Після успішного збереження редіректимо на чат ---
    def form_valid(self, form):
        character = form.save()
        return redirect(reverse('chat', kwargs={'slug': character.slug}))


def page_not_found(request, exception):
    print("Hi, hi")
    return HttpResponseNotFound("<h1>Сторінку не знайдено. Вибачте, будь ласка!!!</h1>")

