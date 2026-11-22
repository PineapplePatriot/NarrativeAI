"""
Bulba and the Connections page: people had trouble finding where to switch models, so Bulba can do it.

- read_connections: their connections (name, provider, model; never a key: whether there is one, and its last
  four characters, as the Connections page shows), which connection and model each job uses (the chat, the
  summary, story memory...), and the models the app knows with their price and what they're good at.
- propose_connection_change, as a card they Apply (Undo puts it back):
  - "use": a job (the chat, or a background one) runs on this connection, with this model;
  - "new": a new connection that reuses an existing one's key (the key is copied here, on the server; Bulba never
    sees it and never asks for one), with another model; it can be used for a job at once;
  - "model": change the model a connection itself uses (everything that runs on it follows).
A key they don't have yet is entered on the Connections page only, never in a chat.
"""
from django.db import transaction

JOBS = ("chat", "summary", "memory", "trackers", "translation", "emotion", "writing_tools", "voice_split")


def _connections(user):
    from users.models import ConnectionProfile
    return list(ConnectionProfile.objects.filter(user=user))


def _by_name(user, name):
    name = str(name or "").strip().lower()
    return next((c for c in _connections(user) if c.name.lower() == name), None)


def tool_read_connections(session, args):
    from mainapp import ai_client
    from users.views import _welcome_models
    user = session.user
    conns = [{"name": c.name, "provider": c.get_provider_display(), "model": c.model, "has_key": bool(c.api_key),
              "key_ends": c.key_hint} for c in _connections(user)]
    jobs = {}
    for job in JOBS:
        info = ai_client.TASKS.get(job, {})
        try:
            profile, model = ai_client.resolve(user, job)
            jobs[job] = {"label": info.get("label", job), "connection": profile.name, "model": model,
                         "own_setting": bool(ai_client.get_task_setting(user, job).pk)}
        except ai_client.AIError as e:
            jobs[job] = {"label": info.get("label", job), "error": str(e)}
    catalog = [{"name": m["name"], "id": m["openrouter"], "price": m["price"], "best_for": m["best_for"],
                "watch_out": m["watch_out"], "recommended": m["recommended"]} for m in _welcome_models()][:30]
    return {"connections": conns, "jobs": jobs, "models_we_know": catalog,
            "note": "Keys are never shown and never asked for in a chat: a new key goes on the Connections page "
                    "(top menu → Connections). 'new' reuses an existing connection's key."}, []


def _check_model(conn, model):
    from users.models import ConnectionProfile
    model = str(model or "").strip()[:256]
    if not model:
        raise ValueError("Which model?")
    if conn is not None and conn.provider in ConnectionProfile.HOSTED and "/" not in model:
        raise ValueError(f"“{model}” isn't a model id this provider knows: use the full id, like "
                         "“anthropic/claude-sonnet-4.5” (models_we_know lists them).")
    return model


def tool_propose_connection_change(session, args):
    from mainapp import ai_client
    from mainapp.bulba.agent import _proposal
    user, action = session.user, args.get("action")
    job = args.get("job") or ("chat" if action == "use" else "")
    if job and job not in JOBS:
        return {"error": f"Unknown job; use one of: {', '.join(JOBS)}."}, []
    label = ai_client.TASKS.get(job, {}).get("label", job) if job else ""
    try:
        if action == "use":
            conn = _by_name(user, args.get("connection"))
            if conn is None:
                return {"error": "No connection by that name (read_connections lists them)."}, []
            model = _check_model(conn, args.get("model")) if args.get("model") else ""
            summary = [f"{label}: connection “{conn.name}”, model {model or conn.model}"]
            payload = {"action": "use", "job": job, "connection_id": conn.id, "model": model}
        elif action == "new":
            source = _by_name(user, args.get("copy_key_from"))
            if source is None:
                return {"error": "copy_key_from must name one of their connections (read_connections)."}, []
            name = str(args.get("name") or "").strip()[:100]
            if not name or _by_name(user, name):
                return {"error": "Give the new connection a name none of theirs has."}, []
            model = _check_model(source, args.get("model"))
            summary = [f"New connection “{name}”: {source.get_provider_display()}, model {model}, "
                       f"with the key of “{source.name}”"] + ([f"{label} uses it"] if job else [])
            payload = {"action": "new", "name": name, "source_id": source.id, "model": model, "job": job}
        elif action == "model":
            conn = _by_name(user, args.get("connection"))
            if conn is None:
                return {"error": "No connection by that name (read_connections lists them)."}, []
            model = _check_model(conn, args.get("model"))
            summary = [f"Connection “{conn.name}”: model {conn.model} → {model} (everything that runs on it)"]
            payload = {"action": "model", "connection_id": conn.id, "model": model}
        else:
            return {"error": "action must be use, new or model."}, []
    except ValueError as e:
        return {"error": str(e)}, []
    if args.get("why"):
        summary += ["Why:", str(args["why"])[:400]]
    p = _proposal(session, "connections", "Connections", summary, payload)
    return {"proposal": p["id"], "status": "waiting for Apply"}, [{"type": "proposal", "id": p["id"]}]


def _task_state(user, job):
    from mainapp import ai_client
    ts = ai_client.get_task_setting(user, job)
    return {"job": job, "existed": bool(ts.pk), "profile_id": ts.profile_id, "model": ts.model}


@transaction.atomic
def apply(session, p):
    from mainapp import ai_client
    from users.models import ConnectionProfile
    user, data = session.user, p["payload"]
    undo = {"tasks": [], "created": None, "models": {}}
    conn = None
    if data["action"] == "new":
        source = ConnectionProfile.objects.filter(user=user, id=data["source_id"]).first()
        if source is None:
            raise ValueError("The connection to copy the key from is gone.")
        if ConnectionProfile.objects.filter(user=user, name__iexact=data["name"]).exists():
            raise ValueError(f"There's already a connection called “{data['name']}”.")
        conn = ConnectionProfile.objects.create(user=user, name=data["name"], provider=source.provider,
                                                base_url=source.base_url, api_key=source.api_key, model=data["model"])
        undo["created"] = conn.id
    elif data["action"] == "model":
        conn = ConnectionProfile.objects.filter(user=user, id=data["connection_id"]).first()
        if conn is None:
            raise ValueError("That connection is gone.")
        undo["models"][conn.id] = conn.model
        conn.model = data["model"]
        conn.save(update_fields=["model"])
    else:
        conn = ConnectionProfile.objects.filter(user=user, id=data["connection_id"]).first()
        if conn is None:
            raise ValueError("That connection is gone.")
    if data.get("job"):
        undo["tasks"].append(_task_state(user, data["job"]))
        ts = ai_client.get_task_setting(user, data["job"])
        ts.profile = conn
        ts.model = data.get("model", "") if data["action"] == "use" else ""
        ts.save()
    p["undo"] = undo
    return {"use": f"{ai_client.TASKS.get(data.get('job'), {}).get('label', 'It')} now runs on “{conn.name}”.",
            "new": f"Connection “{conn.name}” is made" + (" and in use." if data.get("job") else "."),
            "model": f"“{conn.name}” now uses {conn.model}."}[data["action"]] + " The Connections page shows it."


@transaction.atomic
def undo(session, p):
    from users.models import ConnectionProfile, TaskSetting
    user, before = session.user, p.get("undo") or {}
    for t in before.get("tasks", []):
        ts = TaskSetting.objects.filter(user=user, task=t["job"]).first()
        if ts is None:
            continue
        if not t["existed"]:
            ts.delete()
        else:
            ts.profile = ConnectionProfile.objects.filter(user=user, id=t["profile_id"]).first()
            ts.model = t["model"]
            ts.save()
    for cid, model in (before.get("models") or {}).items():
        ConnectionProfile.objects.filter(user=user, id=int(cid)).update(model=model)
    if before.get("created"):
        ConnectionProfile.objects.filter(user=user, id=before["created"]).delete()


def tool_defs(fn, STR):
    return [
        fn("read_connections", "Their AI connections (never the keys), which connection and model each job uses "
           "(chat, summary, story memory, trackers...), and the models the app knows with price and strengths. "
           "Read before proposing a connection change.", {}),
        fn("propose_connection_change", "Switch models or connections for them, as a card they Apply (Undo puts it "
           "back). Any job can have its own model: the chat, or a background job (summary, story memory, trackers, "
           "translation, emotion/sprites, writing tools, voice split), e.g. a cheaper model for the summary. "
           "action 'use': `job` (default chat) runs on `connection`, optionally with `model`; 'new': a new "
           "connection called `name` that reuses the key of `copy_key_from`, with `model` (and `job` to use it at "
           "once); 'model': `connection` itself uses `model` (everything on it follows). Never ask for or mention "
           "a key's value: a new key goes on the Connections page.",
           {"action": {"type": "string", "enum": ["use", "new", "model"]},
            "job": {"type": "string", "enum": list(JOBS)}, "connection": STR, "model": STR, "name": STR,
            "copy_key_from": STR, "why": STR}, ["action"]),
    ]


def after_model_change(user):
    """🔁 What Bulba should offer once the chat's model changed: the same check the chat page makes (is their preset
    made for another model?), said as a next step. "" when the preset fits."""
    from mainapp import preset_upgrade
    try:
        hint = preset_upgrade.pending(user)
    except Exception:
        return ""
    if not hint:
        return ""
    if hint["kind"] == "offer_rebuild":
        return (f"NEXT: their preset “{hint['preset']}” was made for {hint['from']}, and the chat now runs on "
                f"{hint['to']}. Offer it with offer_choices: rebuild it for {hint['to']} (the same feel, tuned for the "
                f"new model: get_starter and propose_preset), or keep it as it is. The chat page offers the same.")
    if hint["kind"] == "offer_upgrade":
        return (f"NEXT: their preset “{hint['from']}” is an older one; for the new model there's a ready setup "
                f"(“{hint['to']}”). Offer it with offer_choices (get_starter and propose_preset), or keeping theirs.")
    if hint["kind"] == "switched":
        return f"(Their untouched preset was switched to “{hint['to']}”, made for the new model: tell them.)"
    return ""


HANDLERS = {"read_connections": tool_read_connections, "propose_connection_change": tool_propose_connection_change}
TURN_ENDING = {"propose_connection_change"}
