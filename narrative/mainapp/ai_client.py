"""
The one place that talks to AI providers (OpenRouter or any OpenAI-compatible API).

Every feature calls `complete(user, task, messages, ...)` with a task name from
TASKS. Which connection profile and model a task uses is set per user on the
Connections page; tasks without their own setting use the main chat connection.
"""
import json
import hashlib
import logging
import os
import re

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
    "translation": {
        "label": "Translation",
        "help": "Translates the story into the language you read it in (Profile → Story language). The story is "
                "written in English and translated, faithfully, without rewriting it. Without a model of its own it "
                "uses Gemini 3.8 Flash through OpenRouter.",
        "timeout": 120,
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
        "help": "The setup assistant. Runs on a model we pick, through your OpenRouter or NanoGPT key.",
        "timeout": 120,
        "hidden": True,  # not on the Connections page: the model is ours to choose
    },
    "watch": {
        "label": "Bulba Watch",
        "help": "Every few replies, Bulba reads the latest ones for habits that keep repeating. Bulba's model.",
        "timeout": 90,
        "hidden": True,  # switched on the Extras page; the model is Bulba's
    },
    "polish": {
        "label": "Bulba's polish",
        "help": "Rewrites the sentences with habits you asked to have fixed. Bulba's model, or your chat model.",
        "timeout": 90,
        "hidden": True,  # chosen on the Extras page
    },
    "voice_split": {
        "label": "Voice splitting",
        "help": "Works out who says each line of a reply before ElevenLabs reads it aloud. "
                "Only runs when you press 🔊 on a reply.",
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
# Translation (profile → Story language) without a model of its own: cheap and strong in Ukrainian and other
# languages. Not the chat model, which is often the one weak in that language: that's why it writes English
TRANSLATION_MODEL = "google/gemini-3.8-flash"
# When a provider's filter refuses one of Bulba's requests ("considered high risk"), that one request is sent
# again down this chain, only on a refusal: Gemini 4 Argon first (dependable with conventional adult content),
# DeepSeek V4 Flash only if Argon refuses too
BULBA_FALLBACKS = ["google/gemini-4-argon", "deepseek/deepseek-v4-flash"]
BULBA_FALLBACK = BULBA_FALLBACKS[0]
MODERATION = re.compile(r"considered high risk|rejected because it|content (?:management|security) polic|"
                        r"data_inspection_failed|inappropriate content|violat\w* (?:our|the) (?:content|usage) polic|"
                        r"PROHIBITED_CONTENT|blocked (?:due to|by) safety|finish_reason.{0,6}(?:SAFETY|content_filter)",
                        re.I)
# Requested adjustable-filter settings, matching the ST example. Acceptance and forwarding depend
# on the model/provider; these fields do not establish that all safeguards are disabled.
GEMINI_SAFETY = [{"category": c, "threshold": "OFF"} for c in (
    "HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH", "HARM_CATEGORY_SEXUALLY_EXPLICIT",
    "HARM_CATEGORY_DANGEROUS_CONTENT", "HARM_CATEGORY_CIVIC_INTEGRITY")]


def _hosted(profile):
    """OpenRouter or NanoGPT (the app's own model names work there)."""
    return getattr(profile, "provider", "") in ConnectionProfile.HOSTED


def _for_provider(profile, payload):
    """NanoGPT: the model name as NanoGPT spells it, web search as its ":online" suffix; OpenRouter-only fields
    (cost reporting, routing, Gemini safety settings, plugins) aren't sent there."""
    if profile.provider != ConnectionProfile.PROVIDER_NANOGPT:
        return
    from mainapp import nanogpt
    payload["model"] = nanogpt.model_for(str(payload.get("model") or ""), profile)
    # OpenRouter's web plugin is NanoGPT's ":online" model suffix (stripped again on their side before routing)
    if any(isinstance(p, dict) and p.get("id") == "web" for p in payload.get("plugins") or []) \
            and ":online" not in payload["model"]:
        payload["model"] += ":online"
    for key in ("usage", "provider", "safety_settings", "plugins"):
        payload.pop(key, None)


def _route(profile, payload):
    """OpenRouter provider routing from the model's profile (MiMo: only hosts whose filters don't refuse ordinary
    adult fiction). Left alone when the request already says where to go."""
    if profile.provider != ConnectionProfile.PROVIDER_OPENROUTER or "provider" in payload:
        return
    from mainapp import model_profiles
    mp = model_profiles.for_model(str(payload.get("model") or ""))
    routing = (mp or {}).get("openrouter_provider")
    if routing:
        payload["provider"] = {k: v for k, v in routing.items() if not k.startswith("_")}


def _blocked(text):
    return bool(MODERATION.search(str(text or "")))


def resolve(user, task):
    """Returns (profile, model) for a task."""
    if task == "polish":  # Bulba's model unless they chose their chat model on the Extras page
        from mainapp.models import ChatSettings
        obj = ChatSettings.objects.filter(author=user).first()
        task = "chat" if obj and (obj.watch or {}).get("fix_model") == "chat" else "bulba"
        return resolve(user, task)
    if task in ("bulba", "watch"):
        profile = main_profile(user)
        if profile is None:
            raise NoConnection("No AI connection is set up yet.")
        # Through OpenRouter Bulba uses our model; on a custom server (local testing) the server's own
        return profile, (BULBA_MODEL if _hosted(profile) else profile.model)
    setting = get_task_setting(user, task)
    chat_setting = setting if task == "chat" else get_task_setting(user, "chat")
    profile = setting.profile or main_profile(user)
    if profile is None:
        raise NoConnection("No AI connection is set up yet. Add one on the Connections page.")

    if setting.model:
        model = setting.model
    elif task == "translation" and setting.profile is None and _hosted(profile):
        model = TRANSLATION_MODEL
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
    """The error in words. OpenRouter wraps a provider's own reason ("Provider returned error"): the real one, from
    metadata.raw, is added so it's visible (Gemini's 400s say exactly which field it didn't accept)."""
    try:
        data = resp.json()
        err = data.get("error", data)
        if isinstance(err, dict):
            text = str(err.get("message") or err)
            meta = err.get("metadata") if isinstance(err.get("metadata"), dict) else {}
            raw = meta.get("raw")
            if raw:
                if not isinstance(raw, str):
                    raw = json.dumps(raw, ensure_ascii=False)
                try:  # Google's own JSON: just its message
                    inner = json.loads(raw)
                    inner = inner[0] if isinstance(inner, list) and inner else inner
                    raw = str(((inner or {}).get("error") or {}).get("message") or raw) if isinstance(inner, dict) else raw
                except ValueError:
                    pass
                who = f" ({meta['provider_name']})" if meta.get("provider_name") else ""
                text += f"{who}: {raw[:400]}"
            return text
        return str(err)
    except ValueError:
        return resp.text[:300] or resp.reason


# Gemini explicitly rejected an invalid safety-settings field: try again with less (the civic-integrity category
# first, which newer models may not accept; then none). Do not assume rejected requests have no cost.
SAFETY_FALLBACKS = (
    ("without the civic-integrity filter setting",
     lambda p: {**p, "safety_settings": [s for s in GEMINI_SAFETY if s["category"] != "HARM_CATEGORY_CIVIC_INTEGRITY"]}),
    ("without safety settings", lambda p: {k: v for k, v in p.items() if k != "safety_settings"}),
)


def _diagnostic(profile, payload, task, operation, stage, response=None, data=None):
    """Comparable request metadata only: never prompts, output, keys, headers or raw errors."""
    messages = payload.get("messages") or []
    facts = {"stage": stage, "task": task, "operation": operation,
             "model": payload.get("model"), "connection_id": getattr(profile, "pk", None),
             "connection_type": profile.provider,
             "stream": bool(payload.get("stream")),
             "request_hash": hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=True,
                                                      default=str).encode()).hexdigest(),
             "messages": [{"role": m.get("role"), "characters": len(str(m.get("content") or ""))}
                          for m in messages if isinstance(m, dict)],
             "parameter_names": sorted(k for k in payload if k != "messages"),
             "safety_categories": len(payload.get("safety_settings") or []),
             "routing_configured": bool(payload.get("provider"))}
    if response is not None:
        facts["http_status"] = response.status_code
    if isinstance(data, dict):
        error = data.get("error") if isinstance(data.get("error"), dict) else {}
        meta = error.get("metadata") if isinstance(error.get("metadata"), dict) else {}
        for key, value in (("provider", meta.get("provider_name") or data.get("provider")),
                           ("request_id", data.get("id"))):
            if isinstance(value, str):
                facts[key] = value[:100]
        choices = data.get("choices") or []
        if choices and isinstance(choices[0], dict):
            facts["finish_reason"] = choices[0].get("finish_reason")
            facts["native_finish_reason"] = choices[0].get("native_finish_reason")
    logging.getLogger(__name__).warning("AI request diagnostic %s", json.dumps(facts, ensure_ascii=True, default=str))


def _invalid_safety_setting(resp):
    reason = _error_text(resp)
    return (resp.status_code == 400 and not MODERATION.search(reason)
            and bool(re.search(r"safety[_ ]?settings|safetySettings", reason, re.I))
            and bool(re.search(r"invalid|unsupported|unknown|unrecognized|not supported|not allowed", reason, re.I)))


def _post(profile, payload, *, diagnostic_task=None, diagnostic_operation=None, **kwargs):
    """Retry compatibility errors only when the provider names an invalid safety-setting field."""
    url = f"{profile.api_url}/chat/completions"
    resp = requests.post(url, headers=_headers(profile), json=payload, **kwargs)
    for how, change in SAFETY_FALLBACKS:
        if not (str(payload.get("model") or "").startswith("google/")
                and "safety_settings" in payload and _invalid_safety_setting(resp)):
            break
        _diagnostic(profile, payload, diagnostic_task, diagnostic_operation, "invalid_safety_setting", resp)
        logging.getLogger(__name__).warning("Retrying invalid safety-setting request %s", how)
        resp.close()
        payload = change(payload)
        resp = requests.post(url, headers=_headers(profile), json=payload, **kwargs)
    if resp.status_code >= 400:
        try:
            data = resp.json()
        except ValueError:
            data = None
        _diagnostic(profile, payload, diagnostic_task, diagnostic_operation, "http_error", resp, data)
    resp._narrative_payload = payload  # retain the effective compatibility-retry request for diagnostics
    return resp


def record_cost(user, task, model, cost):
    """Remembers what a request cost (for the spending meter). Never fails the request itself."""
    if not isinstance(cost, (int, float)) or cost <= 0 or user is None or not getattr(user, "pk", None):
        return
    try:
        from users.models import UsageRecord
        UsageRecord.objects.create(user=user, task=task, model=model or "", cost=float(cost))
    except Exception as e:  # e.g. the table isn't migrated yet
        logging.getLogger(__name__).warning("Could not record usage: %s", e)


def spent_this_month(user):
    from django.db.models import Sum
    from django.utils import timezone
    from users.models import UsageRecord
    start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    total = UsageRecord.objects.filter(user=user, time_create__gte=start).aggregate(s=Sum("cost"))["s"]
    return round(total or 0.0, 4)


def spent_total(user):
    """Everything this account has spent through the app (requests whose cost the provider reported)."""
    from django.db.models import Sum
    from users.models import UsageRecord
    total = UsageRecord.objects.filter(user=user).aggregate(s=Sum("cost"))["s"]
    return round(total or 0.0, 4)


def spending(user):
    """{"spent", "limit", "left"} for this calendar month, in dollars."""
    from django.conf import settings
    limit = float(getattr(settings, "SUBSCRIPTION_MONTHLY_LIMIT", 25.0))
    spent = spent_this_month(user)
    return {"spent": spent, "limit": limit, "left": round(max(0.0, limit - spent), 4)}


# Background jobs fill in JSON or short notes: a thinking model thinks as little as it allows there (the story reply
# keeps the Samplers page's setting; Bulba and polishing keep the model's own default, they're writing work)
LIGHT_TASKS = ("summary", "trackers", "emotion", "voice_split", "watch", "writing_tools", "translation", "polish")


def _light_reasoning(profile, task, payload, user=None):
    if task not in LIGHT_TASKS or "reasoning" in payload or not _hosted(profile):
        return
    if user is not None:
        from mainapp import samplers
        if samplers.background_thinking(user) == "model":  # they asked for the model's own default (Extras page)
            return
    from mainapp import model_profiles
    info = (model_profiles.for_model(payload["model"]) or {}).get("reasoning") or {}
    choices = info.get("choices") or {}
    if "off" in choices:
        payload["reasoning"] = {"enabled": False}
    else:
        lowest = next((c for c in ("minimal", "low", "medium") if c in choices), None)
        if lowest:
            payload["reasoning"] = {"effort": lowest}


EFFORT_ORDER = ("minimal", "low", "medium", "high", "xhigh")


def _fit_effort(payload):
    """A thinking level the model doesn't take becomes the nearest one it does (MiMo takes only "high" for on: a
    preset saved with "medium", or a "low" for a quick job, would otherwise be refused with a 400)."""
    effort = (payload.get("reasoning") or {}).get("effort")
    if effort not in EFFORT_ORDER:
        return
    from mainapp import model_profiles
    choices = ((model_profiles.for_model(payload.get("model")) or {}).get("reasoning") or {}).get("choices") or {}
    levels = [c for c in choices if c in EFFORT_ORDER]
    if not levels or effort in levels:
        return
    rank = EFFORT_ORDER.index(effort)
    payload["reasoning"] = {**payload["reasoning"],
                            "effort": min(levels, key=lambda c: (abs(EFFORT_ORDER.index(c) - rank), -EFFORT_ORDER.index(c)))}


def _request(user, task, messages, timeout=None, **params):
    """Sends one chat completion request and returns (profile, the parsed JSON reply)."""
    check_limit(user)
    operation = params.pop("_diagnostic_operation", task)
    profile, model = resolve(user, task)
    if profile.provider == ConnectionProfile.PROVIDER_OPENROUTER:
        params.setdefault("usage", {"include": True})  # OpenRouter then reports the cost
    payload = {"model": model, "messages": messages}
    payload.update({k: v for k, v in params.items() if v is not None})
    if profile.provider == ConnectionProfile.PROVIDER_OPENROUTER and str(payload["model"]).startswith("google/"):
        payload.setdefault("safety_settings", GEMINI_SAFETY)
    _route(profile, payload)
    _for_provider(profile, payload)
    from mainapp import mature
    payload["messages"] = mature.for_model(payload.get("messages") or [], payload.get("model"))
    _light_reasoning(profile, task, payload, user)
    _fit_effort(payload)
    timeout = TEST_TIMEOUT or timeout or TASKS.get(task, {}).get("timeout", 60)
    label = TASKS.get(task, {}).get("label", task)

    try:
        resp = _post(profile, payload, diagnostic_task=task, diagnostic_operation=operation, timeout=timeout)
    except requests.Timeout:
        raise AIError(f"{label}: {profile.name} did not answer within {timeout} seconds.")
    except requests.RequestException as e:
        raise AIError(f"{label}: could not reach {profile.name} ({e.__class__.__name__}).")

    # A provider's filter refused one of Bulba's requests: this request again on the next model in the chain
    chain = [BULBA_MODEL] + BULBA_FALLBACKS
    asked = str(params.get("model") or model)  # the app's name for it (NanoGPT's spelling may differ)
    if (task in ("bulba", "watch", "polish") and asked in chain[:-1]
            and _hosted(profile) and _blocked_reply(resp)):
        nxt = chain[chain.index(asked) + 1]
        logging.getLogger(__name__).info("%s refused one of Bulba's requests; trying %s", asked, nxt)
        return _request(user, task, messages, timeout, **{**params, "model": nxt})

    if resp.status_code >= 400:
        if "PROHIBITED_CONTENT" in _error_text(resp):
            raise AIError(f"{label}: {profile.name} " + block_explanation("PROHIBITED_CONTENT"))
        raise AIError(f"{label}: {profile.name} returned an error ({resp.status_code}): {_error_text(resp)}")

    try:
        data = resp.json()
    except ValueError:
        raise AIError(f"{label}: {profile.name} sent a reply that is not JSON.")
    if isinstance(data, dict) and data.get("error"):  # OpenRouter can report errors with HTTP 200
        _diagnostic(profile, payload, task, operation, "completion_error", resp, data)
        raise AIError(f"{label}: {profile.name} returned an error: {_error_text(resp)}")
    if isinstance(data, dict):
        record_cost(user, task, payload["model"], (data.get("usage") or {}).get("cost"))
        choices = data.get("choices") or []
        choice = choices[0] if choices and isinstance(choices[0], dict) else {}
        native = choice.get("native_finish_reason")
        reason = native if _blocking_stop(native) else choice.get("finish_reason")
        if _blocking_stop(reason):
            effective = getattr(resp, "_narrative_payload", None)
            _diagnostic(profile, effective if isinstance(effective, dict) else payload,
                        task, operation, "blocked_completion", resp, data)
            raise AIError(f"{label}: {profile.name} " + block_explanation(reason))
    return profile, data


def _blocked_reply(resp):
    """A provider filter's refusal, as an error or as the whole (short) reply text."""
    if resp.status_code >= 400:
        return _blocked(_error_text(resp))
    try:
        data = resp.json()
    except ValueError:
        return False
    if not isinstance(data, dict):
        return False
    if data.get("error"):
        return _blocked(json.dumps(data["error"]))
    try:
        message = data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        return False
    content = str(message.get("content") or "")
    if message.get("tool_calls"):
        return False
    finish = str((data["choices"][0] or {}).get("finish_reason") or "").lower()
    if finish in ("content_filter", "safety", "prohibited_content") and not content.strip():
        return True  # Gemini: stopped by its filter, nothing written
    return len(content) < 400 and _blocked(content)


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
        if provider == ConnectionProfile.PROVIDER_NANOGPT:
            if not api_key:
                return False, "Enter an API key."
            from mainapp import nanogpt
            resp = requests.get(f"{probe.api_url}/models", headers=_headers(probe), timeout=15)
            if resp.status_code in (401, 403):
                return False, "NanoGPT rejected this key."
            if resp.status_code >= 400:
                return False, f"NanoGPT error ({resp.status_code}): {_error_text(resp)}"
            ids = nanogpt.model_ids(probe, refresh=True)
            if model and ids and nanogpt.model_for(model, probe, ids) not in ids:
                return False, f"NanoGPT doesn't list {model} right now. Pick another model or try again later."
            return True, "NanoGPT accepted the key."
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


class Reasoning(str):
    """A piece of what a thinking model thinks before it replies (stream() yields these between text pieces)."""


class ToolCalls(list):
    """The tool calls a streamed reply ended with ([{"id", "type", "function": {"name", "arguments"}}]),
    plus the reasoning details some providers need back alongside them."""
    reasoning_details = None


def stream(user, task, messages, timeout=None, **params):
    """
    Like complete(), but yields the reply in pieces as the provider sends them
    (OpenAI-style server-sent events). Raises AIError on failure, including
    errors the provider reports in the middle of a stream.
    """
    import json

    check_limit(user)
    operation = params.pop("_diagnostic_operation", task)
    profile, model = resolve(user, task)
    if profile.provider == ConnectionProfile.PROVIDER_OPENROUTER:
        params.setdefault("usage", {"include": True})  # the cost arrives with the last piece
    payload = {"model": model, "messages": messages, "stream": True}
    payload.update({k: v for k, v in params.items() if v is not None})
    if profile.provider == ConnectionProfile.PROVIDER_OPENROUTER and str(payload["model"]).startswith("google/"):
        payload.setdefault("safety_settings", GEMINI_SAFETY)  # Gemini's adjustable filters off (see GEMINI_SAFETY)
    _route(profile, payload)
    _for_provider(profile, payload)
    from mainapp import mature
    payload["messages"] = mature.for_model(payload.get("messages") or [], payload.get("model"))
    _light_reasoning(profile, task, payload, user)
    _fit_effort(payload)
    read_timeout = TEST_TIMEOUT or timeout or TASKS.get(task, {}).get("timeout", 60)  # max wait between two pieces
    label = TASKS.get(task, {}).get("label", task)

    try:
        resp = _post(profile, payload, diagnostic_task=task, diagnostic_operation=operation, timeout=(15, read_timeout), stream=True)
    except requests.Timeout:
        raise AIError(f"{label}: {profile.name} did not answer within {read_timeout} seconds.")
    except requests.RequestException as e:
        raise AIError(f"{label}: could not reach {profile.name} ({e.__class__.__name__}).")

    with resp:
        if resp.status_code >= 400:
            raise AIError(f"{label}: {profile.name} returned an error ({resp.status_code}): {_error_text(resp)}")
        resp.encoding = "utf-8"
        calls, details = {}, []
        wrote, stop = False, ""  # any text at all; why it stopped (a provider's block often comes as just this)
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
                    _diagnostic(profile, payload, task, operation, "stream_error", resp, event)
                    err = event["error"]
                    msg = str(err.get('message') if isinstance(err, dict) else err)
                    if "PROHIBITED_CONTENT" in msg:
                        raise AIError(f"{label}: {profile.name} " + block_explanation("PROHIBITED_CONTENT"))
                    raise AIError(f"{label}: {profile.name} stopped with an error: {msg}")
                if isinstance(event.get("usage"), dict):
                    record_cost(user, task, model, event["usage"].get("cost"))
                choices = event.get("choices") or []
                if choices:
                    stop = str(choices[0].get("native_finish_reason") or choices[0].get("finish_reason") or stop)
                delta = (choices[0].get("delta") or {}) if choices else {}
                for tc in delta.get("tool_calls") or []:  # arrive in pieces: name first, arguments in bits
                    slot = calls.setdefault(tc.get("index", len(calls)), {"id": "", "type": "function",
                                                                        "function": {"name": "", "arguments": ""}})
                    slot["id"] = tc.get("id") or slot["id"]
                    fn = tc.get("function") or {}
                    slot["function"]["name"] += fn.get("name") or ""
                    slot["function"]["arguments"] += fn.get("arguments") or ""
                if isinstance(delta.get("reasoning_details"), list):
                    details.extend(d for d in delta["reasoning_details"] if isinstance(d, dict))
                text = delta.get("content")
                if text:
                    wrote = True
                    yield text
                else:
                    thought = delta.get("reasoning") or delta.get("reasoning_content")
                    if not thought and isinstance(delta.get("reasoning_details"), list):
                        thought = "".join(d.get("text", "") for d in delta["reasoning_details"] if isinstance(d, dict))
                    if thought:
                        yield Reasoning(thought)
        except requests.RequestException as e:
            raise AIError(f"{label}: the connection to {profile.name} broke off ({e.__class__.__name__}).")
        if not wrote and not calls and _blocking_stop(stop):  # blocked without an error: say so, not "empty"
            _diagnostic(profile, payload, task, operation, "blocked_stream", resp,
                        {"choices": [{"finish_reason": stop}]})
            raise AIError(f"{label}: {profile.name} " + block_explanation(stop))
        if not wrote and not calls and stop and stop.lower() not in ("stop", "end_turn", "eos"):
            # Nothing written for another reason (Gemini: a fumbled tool call, recitation, out of room): say which
            logging.getLogger(__name__).warning("%s sent no text (stop reason %s)", model, stop)
            raise AIError(f"{label}: {profile.name} " + empty_explanation(stop))
        if calls:
            result = ToolCalls(calls[i] for i in sorted(calls))
            result.reasoning_details = _merge_details(details) or None
            yield result


BLOCK_STOPS = ("content_filter", "safety", "prohibited_content", "blocklist", "spii", "image_safety")


def empty_explanation(reason):
    """Plain words for a reply that stopped before writing anything, by the provider's stop reason."""
    r = str(reason or "").upper()
    if "FUNCTION_CALL" in r or "TOOL" in r:  # contains "tool": game.stream_reply then retries without tools
        return (f"fumbled a tool call ({reason}) and wrote nothing. The app's tools are the story extras and dice; "
                "it tries again without them.")
    if "RECITATION" in r:
        return ("wrote nothing because the reply would have repeated published text word for word (Gemini's "
                "RECITATION check). It usually comes from canon text copied into the card or the lorebook (quotes, "
                "wiki descriptions): reword those in your own words, or press Regenerate.")
    if r in ("LENGTH", "MAX_TOKENS"):
        return ("used up the whole reply length thinking and wrote nothing. Raise the reply length limit (Samplers "
                "page) or set Thinking to Light (pen menu → This chat).")
    return f"wrote nothing (it stopped with \"{reason}\"). Press Regenerate to try again."


def _blocking_stop(stop):
    return str(stop or "").lower() in BLOCK_STOPS


def block_explanation(reason):
    """Plain words for a provider's block (Gemini's especially), for the chat's error line."""
    r = str(reason or "").upper()
    if "PROHIBITED" in r:
        return ("was blocked by the provider (PROHIBITED_CONTENT). This code alone does not identify the "
                "trigger. The provider can evaluate the whole request, including instructions and earlier context; "
                "adjustable filter settings do not guarantee acceptance. Check the request context and provider "
                "details before changing the preset or retrying.")
    return (f"blocked the reply with its content filter ({reason}). The code alone does not identify the "
            "trigger; inspect the submitted context and provider details before retrying.")


def _merge_details(details):
    """Streamed reasoning details come in pieces; join the pieces of each one (by index)."""
    merged = {}
    for d in details:
        key = d.get("index", len(merged))
        if key not in merged:
            merged[key] = dict(d)
            continue
        for field in ("text", "summary", "data"):
            if isinstance(d.get(field), str):
                merged[key][field] = (merged[key].get(field) or "") + d[field]
        for field, value in d.items():
            if field not in ("text", "summary", "data") and value is not None:
                merged[key][field] = value
    return [merged[k] for k in sorted(merged)]


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


def _nanogpt_image(user, profile, prompt, reference, reference_type, timeout):
    """One picture from NanoGPT's OpenAI-style image endpoint (Nano Banana: settings.NANOGPT_IMAGE_MODEL), with
    the reference picture as a data URL for consistent moods. Returns (bytes, cost or None)."""
    import base64
    from django.conf import settings
    model = getattr(settings, "NANOGPT_IMAGE_MODEL", "nano-banana-2")
    payload = {"model": model, "prompt": prompt, "n": 1, "response_format": "b64_json"}
    if reference:
        url = f"data:{reference_type};base64,{base64.b64encode(reference).decode('ascii')}"
        payload["imageDataUrl"] = url  # NanoGPT's own name for a reference picture
        payload["image"] = [url]       # the OpenAI-style edit field, for whichever it reads
    try:
        resp = requests.post(f"{profile.api_url}/images/generations", headers=_headers(profile), json=payload,
                             timeout=TEST_TIMEOUT or timeout)
    except requests.Timeout:
        raise AIError(f"The picture took longer than {timeout} seconds. Try again.")
    except requests.RequestException as e:
        raise AIError(f"Could not reach NanoGPT ({e.__class__.__name__}).")
    if resp.status_code >= 400:
        logging.getLogger(__name__).warning("NanoGPT image %s returned %s: %s", model, resp.status_code, _error_text(resp)[:600])
        raise AIError(f"NanoGPT's image model returned an error ({resp.status_code}): {_error_text(resp)}")
    try:
        data = resp.json()
        item = (data.get("data") or [{}])[0]
    except (ValueError, AttributeError, IndexError, TypeError):
        raise AIError("NanoGPT's image model sent a reply I couldn't read.")
    cost = data.get("cost") if isinstance(data.get("cost"), (int, float)) else (data.get("usage") or {}).get("cost")
    record_cost(user, "sprites", model, cost)
    cost = float(cost) if isinstance(cost, (int, float)) else None
    if item.get("b64_json"):
        return base64.b64decode(item["b64_json"]), cost
    url = item.get("url") or ""
    if url.startswith("data:") and ";base64," in url:
        return base64.b64decode(url.split(";base64,", 1)[1]), cost
    if url.startswith("https://"):
        try:
            img = requests.get(url, timeout=60)
            if img.ok and img.content:
                return img.content, cost
        except requests.RequestException:
            pass
    raise AIError("NanoGPT's image model answered without a picture.")


def generate_image(user, prompt, reference=None, reference_type="image/png", timeout=180, model=None):
    """
    One picture from an image model on OpenRouter (Nano Banana: settings.SPRITE_IMAGE_MODEL), optionally
    starting from a reference picture. Returns (PNG/JPEG bytes, cost or None). Uses the main connection's key.
    """
    import base64
    from django.conf import settings
    check_limit(user)
    profile = main_profile(user)
    if profile is not None and profile.provider == ConnectionProfile.PROVIDER_NANOGPT and profile.api_key:
        return _nanogpt_image(user, profile, prompt, reference, reference_type, timeout)
    if profile is None or profile.provider != ConnectionProfile.PROVIDER_OPENROUTER or not profile.api_key:
        raise AIError("Making pictures needs an OpenRouter or NanoGPT key (set it on the welcome page).")
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
