"""
Bulba looks at a picture someone attached: one call describes it, and Bulba gets the description as text (the
picture itself isn't kept in the conversation, so it isn't sent, and paid for, again with every message).

Who looks: Bulba's own model when OpenRouter lists it as taking pictures, else a cheap vision model. On a custom
server (local testing) its own model tries. Screenshots get their text copied out; characters their looks
described in detail (for the card); places and moodboards their setting and mood.
"""
import base64
import io
import time

import requests

from mainapp import ai_client

FALLBACK = "google/gemini-3.8-flash"   # cheap and sees pictures
MAX_SIDE = 1600                        # big enough to read a screenshot
THUMB_SIDE = 220
_INPUTS = {"at": 0.0, "models": {}}    # OpenRouter model id -> its input modalities, cached for six hours

PROMPT = (
    "Someone using a roleplay app (Narrative AI) showed this picture to its setup assistant, Bulba, who can't see "
    "it. Describe it for Bulba, in plain English, so Bulba can help. First say in one line what it is: a "
    "screenshot, character art, a place or scene, a moodboard, or something else.\n"
    "- A screenshot: copy out the text that matters exactly (a reply they dislike, a setting, an error), and say "
    "which page or app it looks like.\n"
    "- Character art: describe how the character looks, concretely enough to write a card from it: apparent age, "
    "build, face, hair, eyes, skin, outfit and colours, notable details, expression and pose, the art style. "
    "Don't guess a name unless it's written in the picture.\n"
    "- A place, scene or moodboard: the setting, light, colours, period or genre, and the mood it gives.\n"
    "Only what you can see; say so when something is unclear. At most 300 words. No preamble.")


def _input_modalities():
    if _INPUTS["models"] and time.time() - _INPUTS["at"] < 6 * 3600:
        return _INPUTS["models"]
    try:
        resp = requests.get("https://openrouter.ai/api/v1/models", timeout=15)
        data = resp.json().get("data", []) if resp.ok else []
    except (requests.RequestException, ValueError):
        data = []
    found = {m.get("id"): (m.get("architecture") or {}).get("input_modalities") or [] for m in data if m.get("id")}
    if found:
        _INPUTS.update(at=time.time(), models=found)
    return found or _INPUTS["models"]


def looker(user):
    """(model id, its name for people) that will look at the picture."""
    from users.models import ConnectionProfile
    profile, model = ai_client.resolve(user, "bulba")
    if profile.provider != ConnectionProfile.PROVIDER_OPENROUTER:
        return model, model
    if "image" in _input_modalities().get(model, []):
        return model, "Bulba's own model"
    return FALLBACK, "Gemini 3.8 Flash"


def prepare(raw):
    """(data URL for the model, small data URL thumbnail for the log). Raises ValueError for a non-picture."""
    from PIL import Image, UnidentifiedImageError
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except (UnidentifiedImageError, OSError, SyntaxError):
        raise ValueError("That file isn't a picture.")
    img = img.convert("RGB")

    def encoded(side, quality):
        copy = img.copy()
        copy.thumbnail((side, side))
        out = io.BytesIO()
        copy.save(out, "JPEG", quality=quality)
        return "data:image/jpeg;base64," + base64.b64encode(out.getvalue()).decode("ascii")

    return encoded(MAX_SIDE, 88), encoded(THUMB_SIDE, 70)


def describe(user, data_url, their_words=""):
    """(what the picture shows, in words; the model that looked, for people). Raises ai_client.AIError."""
    model, who = looker(user)
    text = [{"type": "text", "text": PROMPT + (f"\n\nWhat they said with it: {their_words}" if their_words else "")},
            {"type": "image_url", "image_url": {"url": data_url}}]
    answer = ai_client.complete(user, "bulba", [{"role": "user", "content": text}], model=model,
                                max_tokens=900, temperature=0.2)
    answer = (answer or "").strip()
    if not answer:
        raise ai_client.AIError("The picture came back with no description. Try again.")
    return answer, who
