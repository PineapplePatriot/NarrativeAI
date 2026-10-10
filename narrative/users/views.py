import json

from django.db import transaction
from django.http import JsonResponse
from django.utils.http import url_has_allowed_host_and_scheme

# --- Django auth ---
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, PasswordChangeView

# --- Django core ---
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render, redirect
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import CreateView, UpdateView

# --- Local imports ---
from narrative import settings
from .forms import (
    LoginUserForm, RegisterUserForm,
    ProfileUserForm, UserPasswordChangeForm,
)
from .models import ApiConfig, ConnectionProfile, TaskSetting


class LoginUser(LoginView):
    form_class = LoginUserForm
    template_name = 'users/login.html'
    extra_context = {"title": "Log in"}


class RegisterUser(CreateView):
    form_class = RegisterUserForm
    template_name = 'users/register.html'
    extra_context = {"title": "Create an account"}
    success_url = reverse_lazy('users:welcome')  # після успішної реєстрації

    def form_valid(self, form):
        # Signed in straight away, then the welcome page (key + model), no second password prompt
        from django.contrib.auth import login
        response = super().form_valid(form)
        login(self.request, self.object, backend="django.contrib.auth.backends.ModelBackend")
        return response


class ProfileUser(LoginRequiredMixin, UpdateView):
    model = get_user_model()
    form_class = ProfileUserForm
    template_name = 'users/profile.html'
    extra_context = {
        'title': 'Profile',
        'default_image': settings.DEFAULT_USER_IMAGE,             }

    def get_success_url(self):
        return reverse_lazy('home')

    def get_object(self, queryset=None):
        return self.request.user

class UserPasswordChange(LoginRequiredMixin, PasswordChangeView):
    form_class = UserPasswordChangeForm
    success_url = reverse_lazy("users:password_change_done")
    template_name = "users/password_change_form.html"


def _connections_state(user):
    from mainapp.ai_client import TASKS, get_task_setting

    profiles = [{
        "id": p.id, "name": p.name, "provider": p.provider, "base_url": p.base_url,
        "model": p.model, "key_hint": p.key_hint, "has_key": bool(p.api_key),
    } for p in ConnectionProfile.objects.filter(user=user)]

    tasks = []
    for task, info in TASKS.items():
        if info.get("hidden"):
            continue
        ts = get_task_setting(user, task)
        tasks.append({
            "task": task, "label": info["label"], "help": info["help"],
            "schedulable": info.get("schedulable", False), "toggleable": info.get("toggleable", False),
            "profile_id": ts.profile_id, "model": ts.model, "enabled": ts.enabled,
            "mode": ts.mode, "interval": ts.interval,
        })
    api_config = ApiConfig.objects.filter(user=user).first()
    eleven = api_config.eleven_key if api_config else ""
    return {
        "profiles": profiles,
        "tasks": tasks,
        "providers": [{"value": v, "label": l} for v, l in ConnectionProfile.PROVIDERS],
        "eleven_key_hint": f"…{eleven[-4:]}" if len(eleven) >= 8 else ("set" if eleven else ""),
    }


class ConnectionsError(Exception):
    pass


@transaction.atomic
def _save_connections(user, data):
    from mainapp.ai_client import TASKS, get_task_setting

    valid_providers = {v for v, _ in ConnectionProfile.PROVIDERS}
    existing = {p.id: p for p in ConnectionProfile.objects.filter(user=user)}
    ref_to_profile = {}  # client id (int or "new-1") -> saved profile
    seen_names = set()

    incoming = data.get("profiles", [])
    keep_ids = {p.get("id") for p in incoming if isinstance(p.get("id"), int)}
    for pid, profile in existing.items():
        if pid not in keep_ids:
            profile.delete()

    for item in incoming:
        name = (item.get("name") or "").strip()
        if not name:
            raise ConnectionsError("Every connection needs a name.")
        if name.lower() in seen_names:
            raise ConnectionsError(f'Two connections are called "{name}".')
        seen_names.add(name.lower())

        provider = item.get("provider")
        if provider not in valid_providers:
            raise ConnectionsError(f'"{name}": unknown provider.')
        model = (item.get("model") or "").strip()
        if not model:
            raise ConnectionsError(f'"{name}": choose a model.')
        base_url = (item.get("base_url") or "").strip()
        if provider == ConnectionProfile.PROVIDER_CUSTOM and not base_url.startswith(("http://", "https://")):
            raise ConnectionsError(f'"{name}": enter the API base URL, starting with http:// or https://.')

        profile = existing.get(item.get("id")) if isinstance(item.get("id"), int) else None
        if profile is None:
            profile = ConnectionProfile(user=user)
        new_key = (item.get("api_key") or "").strip()
        if new_key:
            profile.api_key = new_key  # blank means "keep the saved key"
        if provider == ConnectionProfile.PROVIDER_OPENROUTER and not profile.api_key:
            raise ConnectionsError(f'"{name}": enter your OpenRouter API key.')

        profile.name, profile.provider, profile.base_url, profile.model = name, provider, base_url, model
        profile.save()
        ref_to_profile[item.get("id")] = profile

    for item in data.get("tasks", []):
        task = item.get("task")
        if task not in TASKS or TASKS[task].get("hidden"):
            continue
        ts = get_task_setting(user, task)
        ts.profile = ref_to_profile.get(item.get("profile_id"))
        ts.model = (item.get("model") or "").strip()
        ts.enabled = bool(item.get("enabled", True)) if TASKS[task].get("toggleable") else True
        if TASKS[task].get("schedulable"):
            ts.mode = item.get("mode") if item.get("mode") in dict(TaskSetting.MODES) else TaskSetting.MODE_MANUAL
            try:
                ts.interval = max(1, int(item.get("interval") or 10))
            except (TypeError, ValueError):
                ts.interval = 10
        ts.save()

    # The main chat always has a connection once any exists
    chat = TaskSetting.objects.filter(user=user, task="chat").first()
    first = ConnectionProfile.objects.filter(user=user).first()
    if first and (chat is None or chat.profile is None):
        chat = chat or TaskSetting(user=user, task="chat")
        chat.profile = first
        chat.save()

    api_config, _ = ApiConfig.objects.get_or_create(user=user)
    if data.get("clear_eleven_key"):
        api_config.eleven_key = ""
    elif (data.get("eleven_key") or "").strip():
        api_config.eleven_key = data["eleven_key"].strip()
    api_config.save()


@login_required
def connections(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body.decode("utf-8"))
            _save_connections(request.user, data)
        except (ValueError, UnicodeDecodeError):
            return JsonResponse({"error": "Invalid request."}, status=400)
        except ConnectionsError as e:
            return JsonResponse({"error": str(e)}, status=400)
        return JsonResponse({"status": "ok", "state": _connections_state(request.user)})

    next_url = request.GET.get("next", "")
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        next_url = ""
    return render(request, "users/api_config.html", {
        "state": _connections_state(request.user),
        "next_url": next_url,
    })


@login_required
def connections_test(request):
    from mainapp.ai_client import test_connection

    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)
    try:
        data = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid request."}, status=400)

    api_key = (data.get("api_key") or "").strip()
    if not api_key and isinstance(data.get("id"), int):
        saved = ConnectionProfile.objects.filter(user=request.user, id=data["id"]).first()
        api_key = saved.api_key if saved else ""
    ok, message = test_connection(data.get("provider"), data.get("base_url"), api_key, data.get("model"))
    return JsonResponse({"ok": ok, "message": message})


class MyLogoutView(View):
    def get(self, request):
        logout(request)
        return redirect(reverse_lazy('users:login'))


# --- First run: an OpenRouter key and the model you want to chat with ---------------------

def _welcome_models():
    from mainapp import model_profiles
    cards = []
    for p in model_profiles.all_profiles():
        card = p.get("card") or {}
        cards.append({"id": p["id"], "name": p["name"], "openrouter": p["ids"].get("openrouter", ""),
                      "recommended": bool(card.get("recommended")), "price": card.get("price", ""),
                      "best_for": card.get("best_for", ""), "watch_out": card.get("watch_out", ""),
                      "order": card.get("order", 99)})
    return sorted(cards, key=lambda c: c["order"])


@login_required
def welcome(request):
    """Two questions instead of the full Connections page: your key, and your chat model."""
    from mainapp import ai_client
    from mainapp.ai_client import get_task_setting, main_profile, test_connection

    models = _welcome_models()
    current = main_profile(request.user)
    if request.method == "POST":
        try:
            data = json.loads(request.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return JsonResponse({"error": "Invalid request."}, status=400)
        if data.get("action") == "ready":  # the ready preset only, no Bulba
            from mainapp import starters
            try:
                obj = starters.apply_ready(request.user, data.get("starter"))
            except ValueError as e:
                return JsonResponse({"error": str(e)}, status=400)
            return JsonResponse({"status": "ok", "preset": obj.name, "next": reverse("characters_list")})
        choice = next((m for m in models if m["id"] == data.get("model")), None)
        if choice is None or not choice["openrouter"]:
            return JsonResponse({"error": "Pick one of the models."}, status=400)
        api_key = (data.get("api_key") or "").strip()
        if not api_key and current and current.provider == ConnectionProfile.PROVIDER_OPENROUTER:
            api_key = current.api_key  # keep the saved key
        if not api_key:
            return JsonResponse({"error": "Paste your OpenRouter key first."}, status=400)
        if not data.get("skip_check"):
            ok, message = test_connection(ConnectionProfile.PROVIDER_OPENROUTER, "", api_key, choice["openrouter"])
            if not ok:
                return JsonResponse({"error": message, "can_skip": True}, status=400)

        profile = current if current and current.provider == ConnectionProfile.PROVIDER_OPENROUTER else None
        if profile is None:
            name = "Main"
            while ConnectionProfile.objects.filter(user=request.user, name=name).exists():
                name = f"{name} (OpenRouter)"
            profile = ConnectionProfile(user=request.user, name=name, provider=ConnectionProfile.PROVIDER_OPENROUTER)
        profile.api_key, profile.model = api_key, choice["openrouter"]
        profile.save()
        chat = get_task_setting(request.user, "chat")
        chat.profile, chat.model = profile, ""
        chat.save()
        from mainapp import starters
        return JsonResponse({"status": "ok", "model": choice["name"], "ready": starters.ready_for(choice["id"])})

    return render(request, "users/welcome.html", {"welcome_data": {
        "models": models,
        "has_key": bool(current and current.provider == ConnectionProfile.PROVIDER_OPENROUTER and current.api_key),
        "current_model": current.model if current else "",
        "connected": ai_client.has_connection(request.user),
    }})


# --- Extras: the feature switches in plain words (for people who skip Bulba) --------------

BACKGROUND_TASKS = ("summary", "trackers", "emotion", "voice_split")


def _cheap_models():
    return [m for m in _welcome_models() if m["price"] == "$"]


def _extras_state(user):
    from mainapp.ai_client import get_task_setting, main_profile
    from mainapp.game import user_default as game_default
    from mainapp.extras import ideas_on, kinds_for as story_extras
    main = main_profile(user)
    settings_ = {t: get_task_setting(user, t) for t in ("summary", "trackers", "emotion")}
    bg_profiles = {get_task_setting(user, t).profile_id for t in BACKGROUND_TASKS}
    bg = ConnectionProfile.objects.filter(id=next(iter(bg_profiles))).first() if len(bg_profiles) == 1 else None
    cheap = next((m for m in _cheap_models() if bg and main and bg.id != main.id and bg.model == m["openrouter"]), None)
    eleven = ApiConfig.objects.filter(user=user).first()
    return {
        "chat_model": next((m["name"] for m in _welcome_models() if main and m["openrouter"] == main.model), main.model if main else ""),
        "has_eleven_key": bool(eleven and eleven.eleven_key),
        "summary": {"mode": settings_["summary"].mode, "interval": settings_["summary"].interval},
        "trackers": {"mode": settings_["trackers"].mode, "interval": settings_["trackers"].interval},
        "sprites": settings_["emotion"].enabled,
        "game": game_default(user),
        "story_extras": story_extras(user),
        "ideas": ideas_on(user),
        "watch": get_task_setting(user, "watch").enabled,
        "background": cheap["id"] if cheap else "chat",
        "cheap_models": [m for m in _cheap_models() if not (main and m["openrouter"] == main.model)],
        "openrouter": bool(main and main.provider == ConnectionProfile.PROVIDER_OPENROUTER),
    }


def apply_extras(user, data):
    """Saves the Extras switches (also used by Bulba's proposals). Returns an error message or None."""
    from mainapp.ai_client import get_task_setting, main_profile
    # Check everything first, so a mistake changes nothing
    background = data.get("background")
    main = main_profile(user)
    choice = None
    if background and background != "chat":
        choice = next((m for m in _cheap_models() if m["id"] == background), None)
        if choice is None:
            return "Pick one of the listed models."
        if not (main and main.provider == ConnectionProfile.PROVIDER_OPENROUTER and main.api_key):
            return "A cheaper model needs your OpenRouter key; set it on the welcome page first."

    with transaction.atomic():
        for task in ("summary", "trackers"):
            item = data.get(task) if isinstance(data.get(task), dict) else {}
            setting = get_task_setting(user, task)
            if item.get("mode") in (TaskSetting.MODE_AUTO, TaskSetting.MODE_MANUAL):
                setting.mode = item["mode"]
            try:
                setting.interval = max(1, min(200, int(item.get("interval", setting.interval))))
            except (TypeError, ValueError):
                pass
            setting.save()
        if isinstance(data.get("story_extras"), list):
            from mainapp import extras
            extras.set_kinds(user, data["story_extras"])
        if isinstance(data.get("ideas"), bool):
            from mainapp import extras
            extras.set_ideas(user, data["ideas"])
        if isinstance(data.get("watch"), bool):
            watch = get_task_setting(user, "watch")
            watch.enabled = data["watch"]
            watch.save()
        if data.get("game") in ("off", "dice", "full"):
            from mainapp import game
            game.set_user_default(user, data["game"])
        if "sprites" in data:
            emotion = get_task_setting(user, "emotion")
            emotion.enabled = bool(data["sprites"])
            emotion.save()

        eleven = ApiConfig.objects.get_or_create(user=user)[0]
        if data.get("remove_eleven_key"):
            eleven.eleven_key = ""
        elif (data.get("eleven_key") or "").strip():
            eleven.eleven_key = data["eleven_key"].strip()
        eleven.save()

        if background == "chat":
            for task in BACKGROUND_TASKS:
                setting = get_task_setting(user, task)
                setting.profile, setting.model = None, ""
                setting.save()
        elif choice:
            bg, _ = ConnectionProfile.objects.get_or_create(
                user=user, name="Background (cheaper)",
                defaults={"provider": ConnectionProfile.PROVIDER_OPENROUTER})
            bg.provider, bg.api_key, bg.model = ConnectionProfile.PROVIDER_OPENROUTER, main.api_key, choice["openrouter"]
            bg.save()
            for task in BACKGROUND_TASKS:
                setting = get_task_setting(user, task)
                setting.profile, setting.model = bg, ""
                setting.save()
    return None


@login_required
def extras(request):
    from mainapp.ai_client import get_task_setting, main_profile

    if request.method == "POST":
        try:
            data = json.loads(request.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return JsonResponse({"error": "Invalid request."}, status=400)
        error = apply_extras(request.user, data)
        if error:
            return JsonResponse({"error": error}, status=400)
        return JsonResponse({"status": "ok", "state": _extras_state(request.user)})

    return render(request, "users/extras.html", {"extras_data": _extras_state(request.user)})
