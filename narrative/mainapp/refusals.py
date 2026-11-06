"""
A chat reply that is a refusal (a provider's filter, or the model declining) never goes into the story. The
first time, the page asks once which model should step in for refused replies; after that, a refused reply is
rewritten on that model, just that one reply (the chat model stays what it is). If the stand-in refuses too,
the page says so instead of trying again.
"""
import re

from mainapp import ai_client

STAND_INS = [("google/gemini-4-argon", "Gemini 4 Argon", "dependable with conventional adult content"),
             ("deepseek/deepseek-v4-flash", "DeepSeek V4 Flash", "cheapest, least filtered, less predictable"),
             ("anthropic/claude-opus-5.5", "Claude Opus 5.5", "the strongest writer, the priciest")]
MIMO = ("xiaomi/mimo-v2.6-pro", "MiMo v2.6 Pro", "cheap, routed to providers that don't filter")

# The model itself declining (not a provider's filter): a short reply that opens with it
DECLINE = re.compile(
    r"^\W*(?:I(?:'m| am) (?:sorry|unable|not able|not comfortable)|I can(?:'|no)t (?:help|continue|assist|write|create|"
    r"provide|engage|produce|do)|I won'?t (?:write|continue|create|produce)|Sorry, (?:but )?I can|As an AI|"
    r"I (?:must|have to) (?:decline|refuse)|This (?:request|content) (?:violates|goes against))", re.I)
TOPIC = re.compile(r"content|request|roleplay|role-play|guideline|polic|story|scenario|explicit|appropriate|write", re.I)


def is_refusal(text):
    text = str(text or "").strip()
    if not text:
        return False
    if len(text) < 400 and ai_client.MODERATION.search(text):
        return True
    return len(text) < 600 and bool(DECLINE.search(text)) and bool(TOPIC.search(text))


def options(chat_model):
    """Who can step in: the three, with MiMo in the place of whichever one is their chat model."""
    out = [s if s[0] != chat_model else MIMO for s in STAND_INS]
    return [{"id": i, "name": n, "note": note} for i, n, note in out]


def chosen(user):
    from mainapp.models import ChatSettings
    obj = ChatSettings.objects.filter(author=user).first()
    return (obj.appearance or {}).get("refusal_model", "") if obj else ""


def choose(user, model, chat_model):
    if model not in [o["id"] for o in options(chat_model)]:
        raise ValueError("Pick one of the models shown.")
    from mainapp.models import ChatSettings
    obj, _ = ChatSettings.objects.get_or_create(author=user)
    obj.appearance = {**(obj.appearance or {}), "refusal_model": model}
    obj.save(update_fields=["appearance"])


def stand_in_for(user, chat_model):
    """Their pick, if it still fits (it isn't their chat model now)."""
    pick = chosen(user)
    return pick if pick in [o["id"] for o in options(chat_model)] else ""


def name_of(model):
    return next((n for i, n, _ in STAND_INS + [MIMO] if i == model), model)
