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
