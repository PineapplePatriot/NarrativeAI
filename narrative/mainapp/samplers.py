"""
Sampler settings for the main chat (temperature, top-p, response length...).

Each sampler has an on/off switch. Off means "not sent": the model uses its own
default. What each model actually does with them comes from its profile
(mainapp/model_profiles.py): settings a model fixes or doesn't have are never sent.

Stored per user in ChatSettings.samplers. When presets arrive they will carry
the same structure.
"""
from mainapp import model_profiles

SAMPLERS = [
    # key, label, kind, default, min, max, step, help
    {"key": "max_tokens", "label": "Response length (tokens)", "kind": "int", "default": 2048,
     "min": 16, "max": 128000, "step": 1,
     "help": "Upper limit for one reply. Too low cuts replies off mid-sentence."},
    {"key": "context_size", "label": "Context size (tokens)", "kind": "int", "default": 32000,
     "min": 1024, "max": 2000000, "step": 1024,
     "help": "How much the app sends per request. The oldest messages are dropped to fit "
             "(the summary and trackers keep the story). Off = send the whole chat."},
    {"key": "temperature", "label": "Temperature", "kind": "float", "default": 1.0,
     "min": 0, "max": 2, "step": 0.01, "help": "Higher = more surprising word choices, lower = more predictable."},
    {"key": "top_p", "label": "Top-p", "kind": "float", "default": 1.0, "min": 0, "max": 1, "step": 0.01,
     "help": "Only pick from the most likely words that add up to this probability."},
    {"key": "top_k", "label": "Top-k", "kind": "int", "default": 0, "min": 0, "max": 500, "step": 1,
     "help": "Only pick from the k most likely words (0 = no limit)."},
    {"key": "min_p", "label": "Min-p", "kind": "float", "default": 0.0, "min": 0, "max": 1, "step": 0.01,
     "help": "Drop words much less likely than the top choice. Popular with open models."},
    {"key": "top_a", "label": "Top-a", "kind": "float", "default": 0.0, "min": 0, "max": 1, "step": 0.01,
     "help": "Like min-p, but scales with how confident the model is."},
    {"key": "frequency_penalty", "label": "Frequency penalty", "kind": "float", "default": 0.0,
     "min": -2, "max": 2, "step": 0.01, "help": "Penalizes words the more often they were already used."},
    {"key": "presence_penalty", "label": "Presence penalty", "kind": "float", "default": 0.0,
     "min": -2, "max": 2, "step": 0.01, "help": "Penalizes any word that already appeared, nudging new topics."},
    {"key": "repetition_penalty", "label": "Repetition penalty", "kind": "float", "default": 1.0,
     "min": 0, "max": 2, "step": 0.01, "help": "Above 1 discourages repeating (open models; 1 = off)."},
    {"key": "seed", "label": "Seed", "kind": "int", "default": 42, "min": 0, "max": 2 ** 31 - 1, "step": 1,
     "help": "Same seed + same prompt = same reply, on models that support it."},
    {"key": "stop", "label": "Stop sequences", "kind": "list", "default": [],
     "help": "Comma-separated. The reply stops when one of these appears (e.g. \\nUser:)."},
    {"key": "reasoning_effort", "label": "Reasoning effort", "kind": "choice", "default": "medium",
     "choices": ["off", "minimal", "low", "medium", "high"],
     "help": "How hard thinking models think before replying (off = don't think, where the model allows it). "
             "On the newest Claude models this replaces temperature as the main control."},
    {"key": "verbosity", "label": "Verbosity", "kind": "choice", "default": "medium",
     "choices": ["low", "medium", "high"], "help": "Asks supporting models for shorter or longer replies."},
]
SAMPLERS_BY_KEY = {s["key"]: s for s in SAMPLERS}

# Samplers that are settings for the app, not API parameters
APP_ONLY = {"context_size"}



def _coerce(spec, value):
    kind = spec["kind"]
    if kind == "list":
        if isinstance(value, str):
            value = value.split(",")
        if not isinstance(value, list):
            return []
        # Allow "\n" written literally in the box
        # Trim spaces around commas (but keep newlines), and allow "\n" typed literally
        return [str(v).strip(" ").replace("\\n", "\n") for v in value if str(v).strip()][:8]
    if kind == "choice":
        return value if value in spec["choices"] else spec["default"]
    try:
        n = float(value)
    except (TypeError, ValueError):
        return spec["default"]
    n = max(spec["min"], min(spec["max"], n))
    return int(round(n)) if kind == "int" else round(n, 3)


def normalize(raw):
    """{key: {"on": bool, "value": ...}} for every sampler. Everything starts off."""
    raw = raw if isinstance(raw, dict) else {}
    out = {}
    for spec in SAMPLERS:
        item = raw.get(spec["key"]) if isinstance(raw.get(spec["key"]), dict) else {}
        out[spec["key"]] = {
            "on": bool(item.get("on", False)),
            "value": _coerce(spec, item.get("value", spec["default"])),
        }
    return out


def to_api_params(samplers, model):
    """API parameters to send for this model, and the switched-on samplers it doesn't use."""
    params, skipped = {}, []
    status = model_profiles.sampler_status(model, samplers)
    profile = model_profiles.for_model(model)
    for key, item in samplers.items():
        if not item["on"] or key in APP_ONLY:
            continue
        if status.get(key, {}).get("status") in ("fixed", "unused"):
            skipped.append(key)
            continue
        rule = (profile or {}).get("samplers", {}).get(key, {})
        if key == "reasoning_effort":
            choices = (profile or {}).get("reasoning", {}).get("choices")
            if choices and item["value"] not in choices:
                skipped.append(key)  # e.g. "minimal" on a model without that level
            elif item["value"] == "off":
                params["reasoning"] = {"enabled": False}
            else:
                params["reasoning"] = {"effort": item["value"]}
        elif key == "stop":
            if item["value"]:
                params["stop"] = item["value"]
        elif "max" in rule and isinstance(item["value"], (int, float)):
            params[key] = min(item["value"], rule["max"])
        else:
            params[key] = item["value"]
    return params, skipped


def approx_tokens(text):
    # ~3 characters per token: a little pessimistic for English, closer for other scripts
    return len(text or "") // 3 + 4


def trim_history(system_messages, chat_messages, samplers):
    """
    Drop the oldest chat turns so the request fits the context size.
    System messages and the newest turn are always kept. Returns (kept, dropped_count).
    """
    ctx = samplers.get("context_size", {})
    if not ctx.get("on"):
        return chat_messages, 0
    reply_room = samplers["max_tokens"]["value"] if samplers.get("max_tokens", {}).get("on") else 0
    budget = ctx["value"] - reply_room - sum(approx_tokens(m["content"]) for m in system_messages)

    kept, used = [], 0
    for msg in reversed(chat_messages):
        cost = approx_tokens(msg["content"])
        if kept and used + cost > budget:
            break
        kept.append(msg)
        used += cost
    kept.reverse()
    return kept, len(chat_messages) - len(kept)


# Background jobs (summary, trackers): what one request may hold. Room is kept for the answer (and thinking).
JOB_ANSWER_ROOM = 8192
DEFAULT_WINDOW = 128000  # nothing set: the models take a million, but a million-token request costs a fortune


def job_window(user, task):
    """Tokens one request for a background job may send: the job's own window if set (Connections page),
    else the chat's context size (when it's on), else 128k; never more than the job's model can take, minus
    answer room."""
    from mainapp import ai_client
    _, model = ai_client.resolve(user, task)
    limit = ((model_profiles.for_model(model) or {}).get("limits") or {}).get("context")
    own = ai_client.get_task_setting(user, task).context
    if not own:
        ctx = for_user(user).get("context_size", {})
        own = ctx.get("value") if ctx.get("on") else None
    window = min([w for w in (own or DEFAULT_WINDOW, limit) if w])
    return max(2048, window - JOB_ANSWER_ROOM)


def cut_to(text, tokens, keep="end"):
    """The text shortened to about `tokens`, keeping its end (or start), marked where it was cut."""
    chars = max(0, (tokens - 4) * 3)
    if len(text or "") <= chars:
        return text
    return ("[…] " + text[-chars:]) if keep == "end" else (text[:chars] + " […]")


def for_user(user):
    """Samplers of the user's active preset."""
    from mainapp import presets
    return normalize(presets.get_active(user).data.get("samplers"))


# --- Thinking, in plain words (the pen menu, the Extras page and Bulba) ---
# The story reply's level is the active preset's "reasoning_effort" sampler; background jobs (trackers, summaries...)
# think as little as the model allows unless they asked for the model's own default (ai_client.LIGHT_TASKS).
THINKING = {"default": "Model's default", "off": "Off", "light": "Light", "full": "Full"}
THINKING_HELP = {"default": "however the model normally thinks",
                 "off": "fastest and cheapest, a little less careful",
                 "light": "a quick think before writing",
                 "full": "slowest and priciest, the most careful"}


def _effort_for(level, choices):
    """The reasoning_effort value for a level on a model with these choices (None = it can't)."""
    if level == "off":
        return "off" if not choices or "off" in choices else None
    if level == "light":
        return next((c for c in ("low", "minimal") if not choices or c in choices), None)
    if level == "full":
        return next((c for c in ("high", "medium") if not choices or c in choices), None)
    return None


def thinking_options(model):
    """The levels this chat model can do: [{"id", "label", "help"}]; just the default for a model that doesn't think."""
    from mainapp import model_profiles
    profile = model_profiles.for_model(model) or {}
    info = profile.get("reasoning")
    if profile and not info:
        return [{"id": "default", "label": THINKING["default"], "help": "this model doesn't think before writing"}]
    choices = (info or {}).get("choices") or {}
    levels = ["default"] + [lv for lv in ("off", "light", "full") if _effort_for(lv, choices)]
    if "light" in levels and "full" in levels and _effort_for("light", choices) == _effort_for("full", choices):
        levels.remove("light")
    return [{"id": lv, "label": THINKING[lv], "help": THINKING_HELP[lv]} for lv in levels]


def thinking_now(user):
    """The story reply's thinking level, from the active preset."""
    item = for_user(user).get("reasoning_effort") or {}
    if not item.get("on"):
        return "default"
    value = item.get("value")
    return "off" if value == "off" else "light" if value in ("low", "minimal") else "full"


def set_thinking(user, level, model):
    """Sets the story reply's thinking on the active preset. Raises ValueError for a level the model can't do."""
    from mainapp import model_profiles, presets
    if level not in [o["id"] for o in thinking_options(model)]:
        raise ValueError("That model can't think at that level.")
    obj = presets.get_active(user)
    data = dict(obj.data or {})
    s = normalize(data.get("samplers"))
    choices = ((model_profiles.for_model(model) or {}).get("reasoning") or {}).get("choices") or {}
    if level == "default":
        s["reasoning_effort"] = {**s["reasoning_effort"], "on": False}
    else:
        s["reasoning_effort"] = {"on": True, "value": _effort_for(level, choices)}
    data["samplers"] = s
    obj.data = data
    obj.save(update_fields=["data"])


def background_thinking(user):
    """'light' (background jobs think as little as the model allows; the default) or 'model' (its own default)."""
    from mainapp.models import ChatSettings
    obj = ChatSettings.objects.filter(author=user).first()
    return "model" if obj and (obj.appearance or {}).get("background_thinking") == "model" else "light"


def set_background_thinking(user, value):
    from mainapp.models import ChatSettings
    obj, _ = ChatSettings.objects.get_or_create(author=user)
    obj.appearance = {**(obj.appearance or {}), "background_thinking": "model" if value == "model" else "light"}
    obj.save(update_fields=["appearance"])
