"""
The one place that talks to AI providers (OpenRouter or any OpenAI-compatible API).

Every feature calls `complete(user, task, messages, ...)` with a task name from
TASKS. Which connection profile and model a task uses is set per user on the
Connections page; tasks without their own setting use the main chat connection.
"""
import requests

from users.models import ConnectionProfile, TaskSetting

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


def resolve(user, task):
    """Returns (profile, model) for a task."""
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


def complete(user, task, messages, timeout=None, **params):
    """
    Sends a chat completion request for `task` and returns the reply text.
    Extra keyword arguments (temperature, max_tokens, response_format, ...) are
    passed to the API; None values are dropped. Raises AIError on any failure.
    """
    profile, model = resolve(user, task)
    payload = {"model": model, "messages": messages}
    payload.update({k: v for k, v in params.items() if v is not None})
    timeout = timeout or TASKS.get(task, {}).get("timeout", 60)
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
    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        raise AIError(f"{label}: {profile.name} sent a reply without any text.")


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
