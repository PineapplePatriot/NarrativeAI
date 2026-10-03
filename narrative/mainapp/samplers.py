"""
Sampler settings for the main chat (temperature, top-p, response length...).

Each sampler has an on/off switch. Off means "not sent": the model uses its own
default. Some models reject certain samplers outright (the newest Claude models
return an error for temperature/top_p/top_k), so those are skipped for them.

Stored per user in ChatSettings.samplers. When presets arrive they will carry
the same structure.
"""
import re

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
     "choices": ["minimal", "low", "medium", "high"],
     "help": "How hard thinking models think before replying. On the newest Claude models this "
             "replaces temperature as the main control."},
    {"key": "verbosity", "label": "Verbosity", "kind": "choice", "default": "medium",
     "choices": ["low", "medium", "high"], "help": "Asks supporting models for shorter or longer replies."},
]
SAMPLERS_BY_KEY = {s["key"]: s for s in SAMPLERS}

# Samplers that are settings for the app, not API parameters
APP_ONLY = {"context_size"}

# Models that reject these samplers with an error (as of 2026): the newest
# Claude models (Opus 4.7+, Sonnet 5+, Fable, Mythos) only accept their defaults.
SAMPLING_LOCKED = {"temperature", "top_p", "top_k"}
SAMPLING_LOCKED_MODELS = re.compile(r"claude-(?:opus-(?:4[.-][78]|5)|sonnet-5|fable|mythos)", re.I)


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


def locked_for_model(model):
    return set(SAMPLING_LOCKED) if model and SAMPLING_LOCKED_MODELS.search(model) else set()


def to_api_params(samplers, model):
    """API parameters to send for this model, and the samplers skipped because the model rejects them."""
    params, skipped = {}, []
    locked = locked_for_model(model)
    for key, item in samplers.items():
        if not item["on"] or key in APP_ONLY:
            continue
        if key in locked:
            skipped.append(key)
            continue
        if key == "reasoning_effort":
            params["reasoning"] = {"effort": item["value"]}
        elif key == "stop":
            if item["value"]:
                params["stop"] = item["value"]
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
    # Chat must start with a user turn for some providers
    while len(kept) > 1 and kept[0]["role"] == "assistant":
        kept.pop(0)
    return kept, len(chat_messages) - len(kept)


def for_user(user):
    from mainapp.models import ChatSettings
    settings_obj = ChatSettings.objects.filter(author=user).only("samplers").first()
    return normalize(settings_obj.samplers if settings_obj else {})
