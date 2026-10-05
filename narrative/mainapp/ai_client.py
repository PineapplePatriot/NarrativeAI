"""
The one place that talks to AI providers (OpenRouter or any OpenAI-compatible API).

Every feature calls `complete(user, task, messages, ...)` with a task name from
TASKS. Which connection profile and model a task uses is set per user on the
Connections page; tasks without their own setting use the main chat connection.
"""
import os

import requests

from users.models import ConnectionProfile, TaskSetting

# Local testing only: a longer wait for every AI call (seconds), e.g. for a hand-driven stand-in model
TEST_TIMEOUT = int(os.environ.get("NARRATIVE_AI_TIMEOUT") or 0)

# Ordered: this is also the order on the Connections page
TASKS = {
    "chat": {
        "label": "Main chat",
        "help": "Story replies, regenerate and continue.",
        "timeout": 180,
    },
    "summary": {
        "label": "Story summary",
        "help": "Condenses older events. Automatic mode runs every N messages; "
                "manual mode only runs when you press a summary button in the chat menu.",
        "timeout": 120,
        "schedulable": True,
        "default_mode": TaskSetting.MODE_MANUAL,
    },
    "trackers": {
        "label": "Story trackers",
        "help": "Updates the trackers you turned on for a character (world, relationships, stats...). "
                "One call covers all of them, so a cheap fast model works well.",
        "timeout": 90,
        "schedulable": True,
        "default_mode": TaskSetting.MODE_AUTO,
        "default_interval": 2,
    },
    "emotion": {
        "label": "Emotion & speaker detection",
        "help": "Picks character sprites after every reply: one extra call per message, "
                "so a small cheap model is plenty. Turn it off to skip the call.",
        "timeout": 30,
        "toggleable": True,
    },
    "writing_tools": {
        "label": "Expand & spellcheck",
        "help": "The magic-expand and spellcheck buttons next to the chat input.",
        "timeout": 60,
    },
    "bulba": {
        "label": "Bulba",
        "help": "The setup assistant. Runs on a model we pick, through your OpenRouter key.",
        "timeout": 120,
        "hidden": True,  # not on the Connections page: the model is ours to choose
    },
    "voice_split": {
        "label": "Voice splitting",
        "help": "Splits replies into narrator and character lines before ElevenLabs voices them. "
                "Only runs if you have an ElevenLabs key.",
        "timeout": 60,
    },
}


class AIError(Exception):
    """A readable error that can be shown to the user as is."""


class NoConnection(AIError):
    pass


class LimitReached(AIError):
    """This month's subscription money is used up (settings.SUBSCRIPTION_MONTHLY_LIMIT)."""


def check_limit(user):
    """Stops chatting and Bulba once the month's subscription is used up. Resets on the 1st."""
    from django.conf import settings
    if not getattr(settings, "SUBSCRIPTION_LIMIT_ENFORCED", True) or user is None or not getattr(user, "pk", None):
        return
    s = spending(user)
    if s["spent"] >= s["limit"]:
        raise LimitReached(f"This month's ${s['limit']:.2f} is used up (${s['spent']:.2f} so far), so chatting "
                           "and Bulba are paused until the 1st.")


def get_task_setting(user, task):
    """The saved setting for a task, or an unsaved default one."""
    setting = TaskSetting.objects.filter(user=user, task=task).select_related("profile").first()
    if setting is None:
        info = TASKS.get(task, {})
        setting = TaskSetting(user=user, task=task,
                              mode=info.get("default_mode", TaskSetting.MODE_MANUAL),
                              interval=info.get("default_interval", 10))
    return setting


def main_profile(user):
    setting = get_task_setting(user, "chat")
    return setting.profile or ConnectionProfile.objects.filter(user=user).first()


def has_connection(user):
    profile = main_profile(user)
    return bool(profile and profile.model and (profile.api_key or profile.provider == ConnectionProfile.PROVIDER_CUSTOM))


def is_enabled(user, task):
    return get_task_setting(user, task).enabled


# Bulba's own model (the samples it shows always come from the user's chat model)
BULBA_MODEL = "xiaomi/mimo-v2.6-pro"


def resolve(user, task):
    """Returns (profile, model) for a task."""
    if task == "bulba":
        profile = main_profile(user)
        if profile is None:
            raise NoConnection("No AI connection is set up yet.")
        # Through OpenRouter Bulba uses our model; on a custom server (local testing) the server's own
        return profile, (BULBA_MODEL if profile.provider == ConnectionProfile.PROVIDER_OPENROUTER else profile.model)
    setting = get_task_setting(user, task)
    chat_setting = setting if task == "chat" else get_task_setting(user, "chat")
    profile = setting.profile or main_profile(user)
    if profile is None:
        raise NoConnection("No AI connection is set up yet. Add one on the Connections page.")

    if setting.model:
        model = setting.model
    elif setting.profile is None and chat_setting.model:
        model = chat_setting.model  # follows the main chat's model override
    else:
        model = profile.model
    if not model:
        raise NoConnection(f'Connection "{profile.name}" has no model selected.')
    return profile, model


def _headers(profile):
    headers = {"Content-Type": "application/json"}
    if profile.api_key:
        headers["Authorization"] = f"Bearer {profile.api_key}"
    if profile.provider == ConnectionProfile.PROVIDER_OPENROUTER:
        headers["X-Title"] = "NarrativeAI"
    return headers


def _error_text(resp):
    try:
        data = resp.json()
        err = data.get("error", data)
        if isinstance(err, dict):
            return str(err.get("message") or err)
        return str(err)
    except ValueError:
        return resp.text[:300] or resp.reason


def record_cost(user, task, model, cost):
    """Remembers what a request cost (for the spending meter). Never fails the request itself."""
    if not isinstance(cost, (int, float)) or cost <= 0 or user is None or not getattr(user, "pk", None):
        return
    try:
        from users.models import UsageRecord
        UsageRecord.objects.create(user=user, task=task, model=model or "", cost=float(cost))
    except Exception as e:  # e.g. the table isn't migrated yet
        print(f"Could not record usage: {e}")


def spent_this_month(user):
    from django.db.models import Sum
    from django.utils import timezone
    from users.models import UsageRecord
    start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    total = UsageRecord.objects.filter(user=user, time_create__gte=start).aggregate(s=Sum("cost"))["s"]
    return round(total or 0.0, 4)


def spending(user):
    """{"spent", "limit", "left"} for this calendar month, in dollars."""
    from django.conf import settings
    limit = float(getattr(settings, "SUBSCRIPTION_MONTHLY_LIMIT", 25.0))
    spent = spent_this_month(user)
    return {"spent": spent, "limit": limit, "left": round(max(0.0, limit - spent), 4)}


def _request(user, task, messages, timeout=None, **params):
    """Sends one chat completion request and returns (profile, the parsed JSON reply)."""
    check_limit(user)
    profile, model = resolve(user, task)
    if profile.provider == ConnectionProfile.PROVIDER_OPENROUTER:
        params.setdefault("usage", {"include": True})  # OpenRouter then reports the cost
    payload = {"model": model, "messages": messages}
    payload.update({k: v for k, v in params.items() if v is not None})
    timeout = TEST_TIMEOUT or timeout or TASKS.get(task, {}).get("timeout", 60)
    label = TASKS.get(task, {}).get("label", task)

    try:
        resp = requests.post(f"{profile.api_url}/chat/completions", headers=_headers(profile),
                             json=payload, timeout=timeout)
    except requests.Timeout:
        raise AIError(f"{label}: {profile.name} did not answer within {timeout} seconds.")
    except requests.RequestException as e:
        raise AIError(f"{label}: could not reach {profile.name} ({e.__class__.__name__}).")

    if resp.status_code >= 400:
        raise AIError(f"{label}: {profile.name} returned an error ({resp.status_code}): {_error_text(resp)}")

    try:
        data = resp.json()
    except ValueError:
        raise AIError(f"{label}: {profile.name} sent a reply that is not JSON.")
    if isinstance(data, dict) and data.get("error"):  # OpenRouter can report errors with HTTP 200
        raise AIError(f"{label}: {profile.name} returned an error: {_error_text(resp)}")
    if isinstance(data, dict):
        record_cost(user, task, model, (data.get("usage") or {}).get("cost"))
    return profile, data


def complete(user, task, messages, timeout=None, **params):
    """
    Sends a chat completion request for `task` and returns the reply text.
    Extra keyword arguments (temperature, max_tokens, response_format, ...) are
    passed to the API; None values are dropped. Raises AIError on any failure.
    """
    profile, data = _request(user, task, messages, timeout, **params)
    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        label = TASKS.get(task, {}).get("label", task)
        raise AIError(f"{label}: {profile.name} sent a reply without any text.")


def complete_message(user, task, messages, timeout=None, **params):
    """
    Like complete(), but returns (the whole reply message, cost in USD or None), so callers can
    read tool calls. Pass tools=[...] for function calling. OpenRouter reports the cost when asked.
    """
    profile, data = _request(user, task, messages, timeout, **params)
    try:
        message = data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        label = TASKS.get(task, {}).get("label", task)
        raise AIError(f"{label}: {profile.name} sent an empty reply.")
    cost = (data.get("usage") or {}).get("cost")
    return message, (float(cost) if isinstance(cost, (int, float)) else None)


def test_connection(provider, base_url, api_key, model):
    """Checks a key (and model, for OpenRouter). Returns (ok, message)."""
    probe = ConnectionProfile(provider=provider, base_url=base_url or "", api_key=api_key or "", model=model or "")
    if provider == ConnectionProfile.PROVIDER_CUSTOM and not probe.base_url:
        return False, "Enter the API base URL."
    try:
        if provider == ConnectionProfile.PROVIDER_OPENROUTER:
            if not api_key:
                return False, "Enter an API key."
            resp = requests.get(f"{probe.api_url}/key", headers=_headers(probe), timeout=15)
            if resp.status_code in (401, 403):
                return False, "OpenRouter rejected this key."
            if resp.status_code >= 400:
                return False, f"OpenRouter error ({resp.status_code}): {_error_text(resp)}"
            if model:
                models = requests.get(f"{probe.api_url}/models", timeout=15)
                if models.ok and model not in {m.get("id") for m in models.json().get("data", [])}:
                    return False, f'Key works, but OpenRouter has no model called "{model}".'
            return True, "Key works." + (f' Model "{model}" found.' if model else "")

        resp = requests.get(f"{probe.api_url}/models", headers=_headers(probe), timeout=15)
        if resp.status_code in (401, 403):
            return False, "The server rejected this key."
        if resp.status_code >= 400:
            return False, f"Server error ({resp.status_code}): {_error_text(resp)}"
        return True, "Connected."
    except requests.RequestException as e:
        return False, f"Could not reach the server ({e.__class__.__name__})."


THINKING = object()  # yielded by stream() while the model is thinking (its reasoning isn't shown)


def stream(user, task, messages, timeout=None, **params):
    """
    Like complete(), but yields the reply in pieces as the provider sends them
    (OpenAI-style server-sent events). Raises AIError on failure, including
    errors the provider reports in the middle of a stream.
    """
    import json

    check_limit(user)
    profile, model = resolve(user, task)
    if profile.provider == ConnectionProfile.PROVIDER_OPENROUTER:
        params.setdefault("usage", {"include": True})  # the cost arrives with the last piece
    payload = {"model": model, "messages": messages, "stream": True}
    payload.update({k: v for k, v in params.items() if v is not None})
    read_timeout = TEST_TIMEOUT or timeout or TASKS.get(task, {}).get("timeout", 60)  # max wait between two pieces
    label = TASKS.get(task, {}).get("label", task)

    try:
        resp = requests.post(f"{profile.api_url}/chat/completions", headers=_headers(profile),
                             json=payload, timeout=(15, read_timeout), stream=True)
    except requests.Timeout:
        raise AIError(f"{label}: {profile.name} did not answer within {read_timeout} seconds.")
    except requests.RequestException as e:
        raise AIError(f"{label}: could not reach {profile.name} ({e.__class__.__name__}).")

    with resp:
        if resp.status_code >= 400:
            raise AIError(f"{label}: {profile.name} returned an error ({resp.status_code}): {_error_text(resp)}")
        resp.encoding = "utf-8"
        try:
            # chunk_size=1: hand over every line as soon as it arrives. The default waits for 512 bytes,
            # and chunk_size=None waits for the whole reply on servers that don't use chunked encoding.
            for line in resp.iter_lines(chunk_size=1, decode_unicode=True):
                # Blank lines separate events; lines starting with ":" are keep-alive comments
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    event = json.loads(data)
                except ValueError:
                    continue
                if event.get("error"):
                    err = event["error"]
                    raise AIError(f"{label}: {profile.name} stopped with an error: "
                                  f"{err.get('message') if isinstance(err, dict) else err}")
                if isinstance(event.get("usage"), dict):
                    record_cost(user, task, model, event["usage"].get("cost"))
                choices = event.get("choices") or []
                delta = (choices[0].get("delta") or {}) if choices else {}
                text = delta.get("content")
                if text:
                    yield text
                elif delta.get("reasoning") or delta.get("reasoning_content") or delta.get("reasoning_details"):
                    yield THINKING  # the model is still thinking; nothing to show yet
        except requests.RequestException as e:
            raise AIError(f"{label}: the connection to {profile.name} broke off ({e.__class__.__name__}).")


_IMAGE_MODELS = {"at": 0, "list": []}


def image_models():
    """Models on OpenRouter that output pictures ({"id", "name"}), the list cached for an hour."""
    import time
    if _IMAGE_MODELS["list"] and time.time() - _IMAGE_MODELS["at"] < 3600:
        return _IMAGE_MODELS["list"]
    try:
        resp = requests.get(f"{ConnectionProfile.OPENROUTER_URL}/models", timeout=15)
        data = resp.json().get("data", []) if resp.ok else []
    except (requests.RequestException, ValueError):
        data = []
    found = []
    for m in data:
        if "image" in ((m.get("architecture") or {}).get("output_modalities") or []):
            found.append({"id": m.get("id", ""), "name": m.get("name") or m.get("id", "")})
    if found:
        _IMAGE_MODELS.update(at=time.time(), list=sorted(found, key=lambda m: m["name"]))
    return found or _IMAGE_MODELS["list"]


def default_image_model(models=None):
    """settings.SPRITE_IMAGE_MODEL if OpenRouter lists it, else the newest-looking Nano Banana."""
    from django.conf import settings
    wanted = getattr(settings, "SPRITE_IMAGE_MODEL", "google/gemini-3.1-flash-image")
    models = image_models() if models is None else models
    ids = [m["id"] for m in models]
    if not ids or wanted in ids:
        return wanted
    banana = [m for m in models if "nano banana" in m["name"].lower() and "preview" not in m["name"].lower()]
    return (banana or models)[0]["id"]


def generate_image(user, prompt, reference=None, reference_type="image/png", timeout=180, model=None):
    """
    One picture from an image model on OpenRouter (Nano Banana: settings.SPRITE_IMAGE_MODEL), optionally
    starting from a reference picture. Returns (PNG/JPEG bytes, cost or None). Uses the main connection's key.
    """
    import base64
    from django.conf import settings
    check_limit(user)
    profile = main_profile(user)
    if profile is None or profile.provider != ConnectionProfile.PROVIDER_OPENROUTER or not profile.api_key:
        raise AIError("Making pictures needs an OpenRouter key (set it on the welcome page).")
    model = model or default_image_model()
    content = [{"type": "text", "text": prompt}]
    if reference:
        url = f"data:{reference_type};base64,{base64.b64encode(reference).decode('ascii')}"
        content.append({"type": "image_url", "image_url": {"url": url}})
    payload = {"model": model, "messages": [{"role": "user", "content": content}],
               "modalities": ["image", "text"], "usage": {"include": True}}
    try:
        resp = requests.post(f"{profile.api_url}/chat/completions", headers=_headers(profile), json=payload,
                             timeout=TEST_TIMEOUT or timeout)
    except requests.Timeout:
        raise AIError(f"The picture took longer than {timeout} seconds. Try again.")
    except requests.RequestException as e:
        raise AIError(f"Could not reach OpenRouter ({e.__class__.__name__}).")
    if resp.status_code >= 400:
        raise AIError(f"OpenRouter returned an error ({resp.status_code}): {_error_text(resp)}")
    try:
        data = resp.json()
        message = data["choices"][0]["message"]
    except (ValueError, KeyError, IndexError, TypeError):
        raise AIError("The image model sent a reply I couldn't read.")
    cost = (data.get("usage") or {}).get("cost")
    record_cost(user, "sprites", model, cost)
    for image in message.get("images") or []:
        url = ((image or {}).get("image_url") or {}).get("url", "")
        if url.startswith("data:") and ";base64," in url:
            return base64.b64decode(url.split(";base64,", 1)[1]), (float(cost) if isinstance(cost, (int, float)) else None)
    raise AIError("The image model answered without a picture" +
                  (f": {message.get('content')[:200]}" if message.get("content") else "."))
