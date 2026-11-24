"""
🧪 Compare models: the chat's last reply written again by a few other models (and the current one, as the yardstick),
each from the same request shaped for that model, shown side by side with what each cost. One click puts any of
them into the chat as a new version of the last reply. It runs on their own key, so Bulba says the price first.

Model names come from OpenRouter's live list (the app's model profiles say which ones it knows how to prompt);
provider routing follows each model, so a MiMo-only provider list doesn't block the others.
"""
import re
import uuid

import requests
from django.core.cache import cache

from mainapp import ai_client, chats, model_profiles, thinking
from users.models import ConnectionProfile

MOST = 4  # other models in one comparison (plus the current one)
# Profiles tried when they don't name any: cheaper or mid-priced ones the app has prompting knowledge for
DEFAULTS = ("deepseek-v4-flash", "gemini-3-8-flash", "glm-5-3", "kimi-k3")


def _openrouter_ids():
    ids = cache.get("openrouter-text-models")
    if ids is None:
        try:
            resp = requests.get(f"{ConnectionProfile.OPENROUTER_URL}/models", timeout=15)
            ids = [m["id"] for m in resp.json().get("data", []) if isinstance(m, dict) and m.get("id")] if resp.ok else []
        except (requests.RequestException, ValueError):
            ids = []
        cache.set("openrouter-text-models", ids, 6 * 3600)
    return ids


def resolve_models(user, wanted):
    """[(model id to send, display name)] for what they asked for (profile ids like "kimi-k3", or exact model ids),
    or DEFAULTS. Unknown names are skipped (returned in the second list)."""
    profile, current = ai_client.resolve(user, "chat")
    hosted = profile.provider == ConnectionProfile.PROVIDER_OPENROUTER
    ids = _openrouter_ids() if hosted else []
    out, unknown = [], []
    for w in [str(x).strip() for x in (wanted or DEFAULTS) if str(x).strip()][:MOST]:
        prof = model_profiles.by_id(w)
        if prof is None and w in ids:
            out.append((w, (model_profiles.for_model(w) or {}).get("name") or w))
            continue
        if prof is None:
            if not hosted and "/" in w:  # another server: send the name as it is
                out.append((w, w))
            else:
                unknown.append(w)
            continue
        pats = prof.get("_match") or [re.compile(p, re.I) for p in prof.get("match") or []]
        found = next((i for i in ids if any(p.search(i) for p in pats) and ":" not in i), None) if hosted else None
        if found and found != current:
            out.append((found, prof.get("name") or found))
        elif not found:
            unknown.append(w)
    return [(current, (model_profiles.for_model(current) or {}).get("name") or current)] + out, unknown


def tool_compare_models(session, args):
    from mainapp.bulba import agent
    from mainapp.views import build_chat_request
    chat = session.chat
    if chat is None:
        return {"error": "This works inside a chat."}, []
    messages = [m for m in chats.read(chat).get("messages") or [] if isinstance(m, (list, tuple)) and len(m) > 2]
    if not messages or messages[-1][0] != "assistant":
        return {"error": "There's no reply to compare yet: send a message in the chat first."}, []
    if not args.get("confirmed"):
        return {"error": "Tell them first that it writes the last reply once per model on their key (a few cents "
                         "each, more for expensive models), and call again with confirmed: true once they agree."}, []
    models, unknown = resolve_models(session.user, args.get("models"))
    agent._check_budget(session)
    events, results = [], []
    count = len(messages)
    for i, (model, name) in enumerate(models):
        agent.set_activity(session, f"Comparing models: {name} ({i + 1} of {len(models)})…")
        try:
            built = build_chat_request(session.user, chat, model=model)
            message, cost = ai_client.complete_message(session.user, "chat", built["messages"],
                                                        _diagnostic_operation="compare",
                                                        **{**built["params"], "model": model})
        except ai_client.AIError as e:
            results.append({"model": name, "error": str(e)[:300]})
            continue
        session.spent += cost or 0
        reasoning, text = thinking.split(message.get("content") or "")
        text = text.strip()
        price = f" · ${cost:.4f}" if isinstance(cost, (int, float)) else ""
        label = ("Now (your current model)" if i == 0 else name) + price
        results.append({"model": name, "cost": cost, "words": len(text.split())})
        events.append({"type": "samples", "model": name, "character": chat.character.name, "scenario": "",
                       "user_turn": "", "samples": [{"label": label, "text": text}],
                       "retry_id": uuid.uuid4().hex[:12], "at": count,
                       "reasoning": reasoning or str(message.get("reasoning") or "")})
    return ({"compared": results, "unknown": unknown,
             "note": "Each answer shows with its model, its cost and a 'Use this in the chat' button. Ask which they "
                     "liked and why; if one is clearly better, offer propose_connection_change to switch to it (the "
                     "preset may need rebuilding for it: say so)."}, events)


def tool_defs(fn, STR):
    return [fn("compare_models", "Write the chat's last reply again with a few other models, next to the current "
               "one, so they can compare (on their key: a few cents per model). Ask first, then call with "
               "confirmed: true. Leave models empty for the usual cheaper ones (DeepSeek V4 Flash, Gemini 3.8 Flash, "
               "GLM 5.3, Kimi K3), or name up to 4 (a model profile id or an exact OpenRouter id).",
               {"models": {"type": "array", "items": STR, "maxItems": MOST}, "confirmed": {"type": "boolean"}})]


HANDLERS = {"compare_models": tool_compare_models}
