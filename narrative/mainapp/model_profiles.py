"""
Model profiles: what each model actually does with the settings we could send.

One JSON file per model in mainapp/data/models/. A profile says, for every sampler:
  supported   sent as set
  unverified  sent as set, but no source confirms the model uses it
  fixed       never sent: the model uses its own value (sending another is ignored or an error)
  unused      never sent: not part of that model's API
A sampler can also be "fixed" only while the model is thinking ("when_reasoning": "fixed").
The profiles also carry style notes and onboarding questions for Bulba.

Models without a profile keep the old behaviour: everything is sent, except temperature,
top-p and top-k on the newest Claude models, which reject them.
"""
import json
import re
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data" / "models"

# Fallback for models without a profile (as of 2026: Opus 4.7+, Sonnet 5+, Fable, Mythos)
LEGACY_LOCKED = {"temperature", "top_p", "top_k"}
LEGACY_LOCKED_MODELS = re.compile(r"claude-(?:opus-(?:4[.-][78]|5)|sonnet-5|fable|mythos)", re.I)


@lru_cache(maxsize=1)
def all_profiles():
    profiles = []
    for path in sorted(DATA_DIR.glob("*.json")):
        with open(path, encoding="utf-8") as f:
            profile = json.load(f)
        profile["_match"] = [re.compile(p, re.I) for p in profile.get("match", [])]
        profiles.append(profile)
    return profiles


def for_model(model):
    """The profile for a model ID (e.g. "anthropic/claude-opus-5-5"), or None."""
    if not model:
        return None
    return next((p for p in all_profiles() if any(rx.search(model) for rx in p["_match"])), None)


def reasoning_on(profile, samplers):
    """Whether the model will think with these settings."""
    info = (profile or {}).get("reasoning", {})
    if info.get("always_on"):
        return True
    effort = samplers.get("reasoning_effort", {})
    if effort.get("on"):
        return effort.get("value") != "off"
    return info.get("default", "off") != "off"


def sampler_status(model, samplers):
    """{key: {"status", "why"}} for every sampler, for this model and these settings."""
    profile = for_model(model)
    out = {}
    if profile is None:
        locked = LEGACY_LOCKED if model and LEGACY_LOCKED_MODELS.search(model) else set()
        for key in samplers:
            out[key] = ({"status": "fixed", "why": "This model rejects it; it uses its own value."}
                        if key in locked else {"status": "unverified", "why": ""})
        return out
    thinking = reasoning_on(profile, samplers)
    for key in samplers:
        rule = profile.get("samplers", {}).get(key, {"status": "unverified"})
        status = rule.get("status", "unverified")
        if thinking and rule.get("when_reasoning"):
            status = rule["when_reasoning"]
        out[key] = {"status": status, "why": rule.get("why", "")}
    return out


def public(profile):
    """What the Samplers page shows about a profile."""
    if not profile:
        return None
    return {k: profile.get(k) for k in ("id", "name", "verified", "sources", "limits", "reasoning", "samplers")}


def known_names():
    return [p["name"] for p in all_profiles()]


# --- A model we have no profile for (an older GLM, Kimi K2...): its closest relative's style knowledge ---
# Starters and known habits carry over within a family (they come from the same lab's training); limits,
# samplers and reasoning levels don't, so those keep coming from for_model() alone (unknown = unverified).
FAMILIES = (
    (r"glm|zhipu|z-ai", "glm-5-3"),
    (r"kimi|moonshot", "kimi-k3"),
    (r"deepseek", "deepseek-v4-pro"),
    (r"mimo|xiaomi", "mimo-v2-6-pro"),
    (r"claude|anthropic", "claude-opus-5-5"),
    (r"gemini.*(pro|ultra|argon)", "gemini-4-argon"),
    (r"gemini|gemma", "gemini-3-8-flash"),
)


def relative(model):
    """The profile of an unknown model's closest relative, or None."""
    if not model or for_model(model):
        return None
    for pattern, pid in FAMILIES:
        if re.search(pattern, model, re.I):
            return next((p for p in all_profiles() if p["id"] == pid), None)
    return None


def for_style(model):
    """The profile whose starters and known habits fit this model: its own, else its closest relative's (marked
    "_borrowed" with the model they actually use), else the generic "Any model" one (marked "_generic")."""
    own = for_model(model)
    if own:
        return own
    rel = relative(model)
    if rel:
        return {**rel, "_borrowed": True, "_actual": model}
    return {**generic(), "_generic": True, "_actual": model} if model else None


# --- A model with no relative either: "Any model", plain ready presets that rely on no one model's quirks ---
GENERIC_FILE = Path(__file__).resolve().parent / "data" / "generic_model.json"


@lru_cache(maxsize=1)
def generic():
    with open(GENERIC_FILE, encoding="utf-8") as f:
        profile = json.load(f)
    profile["_match"] = []
    return profile


def by_id(pid):
    """A profile by its id, the generic "Any model" one included (it is never in the model list)."""
    if pid == generic()["id"]:
        return generic()
    return next((p for p in all_profiles() if p["id"] == pid), None)
