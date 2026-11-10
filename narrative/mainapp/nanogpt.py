"""
NanoGPT (nano-gpt.com), the second hosted provider: OpenAI-compatible chat completions at /api/v1, reasoning as
`reasoning: {effort}` with the text back in `message.reasoning` (as on OpenRouter). Its model ids are also
"maker/model" but not always spelled like OpenRouter's, so every model name the app uses (the user's pick, Bulba's
model, the translator, fallbacks) is matched to NanoGPT's live list here, by the model profiles' own patterns.
"""
import logging
import re
import time

import requests

log = logging.getLogger(__name__)
_CATALOG = {"at": 0, "ids": []}
TTL = 6 * 3600


def model_ids(profile=None, refresh=False):
    """NanoGPT's model ids (cached for a few hours); [] when the list can't be read."""
    from users.models import ConnectionProfile
    if _CATALOG["ids"] and not refresh and time.time() - _CATALOG["at"] < TTL:
        return _CATALOG["ids"]
    headers = {"Authorization": f"Bearer {profile.api_key}"} if profile is not None and profile.api_key else {}
    try:
        resp = requests.get(f"{ConnectionProfile.NANOGPT_URL}/models", headers=headers, timeout=15)
        data = resp.json().get("data", []) if resp.ok else []
    except (requests.RequestException, ValueError) as e:
        log.warning("NanoGPT's model list couldn't be read: %s", e)
        data = []
    ids = [m.get("id") for m in data if isinstance(m, dict) and m.get("id")]
    if ids:
        _CATALOG.update(at=time.time(), ids=ids)
    return ids or _CATALOG["ids"]


def _plain(model_id):
    """A variant suffix (":thinking", ":reasoning-effort/high", ":online") makes an id less preferred."""
    return ":" not in model_id


def model_for(model, profile=None, ids=None):
    """The NanoGPT id for a model name the app uses (an OpenRouter-style id, or already NanoGPT's)."""
    from mainapp import model_profiles
    ids = model_ids(profile) if ids is None else ids
    if not model or not ids or model in ids:
        return model
    lower = {i.lower(): i for i in ids}
    if model.lower() in lower:
        return lower[model.lower()]
    tail = model.lower().split("/")[-1]
    same_tail = [i for i in ids if i.lower().split("/")[-1] == tail]
    if same_tail:
        return sorted(same_tail, key=lambda i: (not _plain(i), len(i)))[0]
    profile_of = model_profiles.for_model(model)
    if profile_of:
        found = [i for i in ids if any(rx.search(i) for rx in profile_of["_match"])]
        if found:
            return sorted(found, key=lambda i: (not _plain(i), len(i)))[0]
    loose = re.sub(r"[^a-z0-9]", "", tail)
    found = [i for i in ids if re.sub(r"[^a-z0-9]", "", i.lower().split("/")[-1]) == loose]
    return sorted(found, key=lambda i: (not _plain(i), len(i)))[0] if found else model
