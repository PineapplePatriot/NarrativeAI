"""The normal preset/lore machinery behind the VN presentation contract."""
import copy
import json

from mainapp import ai_client, messenger, presets, screen_lore, sprites, vn_support


INTERACTIONS = ("choices", "write", "mixed")
AUTHORING = ("roleplay", "director")


def user_participant(user, context):
    pictures = {}
    for emotion in sprites.BUILT_IN:
        field = getattr(user, "persona_photo_" + emotion, None)
        if field and getattr(field, "name", ""):
            pictures[emotion] = field.url
    return {"slug": "user", "name": context["user_name"], "persona": context["persona"],
            "sprites": pictures, "avatar_url": pictures.get("neutral") or messenger.user_profile(user).get("avatar_url", "")}


def mode_rules(scene):
    if scene.get("authoring_mode") == "director":
        authoring = ("DIRECTING: the user is directing the cast. Their persona is also a character, slug `user`, "
                     "with their own sprites. You may write that character's speech and actions consistently with "
                     "their persona and the user's directions. Treat user input as direction unless clearly a line of dialogue.")
    else:
        authoring = "ROLEPLAY: never decide the user's actions, speech, thoughts or consent. Do not generate dialogue with speaker_slug `user`."
    mode = scene.get("interaction_mode", "mixed")
    interaction = {"choices": "CLASSIC CHOICES: offer meaningful choices at input points. The user selects an option.",
                   "write": "FREE WRITING: do not suggest replies or choices. Return choices: []; the user writes their response.",
                   "mixed": "MIXED: offer choices as suggestions while allowing the user to write their own response."}[mode]
    return authoring + "\n" + interaction


def prepare(user, scene, prompt, generation="normal"):
    chars = vn_support.scene_characters(user, scene.get("character_slugs") or [])
    context = scene["context"]
    thread = vn_support.linked_thread(user, scene)
    history = [{"role": "user" if b.get("kind") == "direction" or b.get("speaker_slug") == "user" and not b.get("generated") else "assistant",
                "content": f"{b.get('speaker_name') or b.get('speaker')}: {b['text']}"}
               for b in scene.get("beats", []) if b.get("text")]
    if not history and context.get("conversation"):
        history = [{"role": "user", "content": "The preceding phone conversation:\n" + context["conversation"]}]
    latest_direction = prompt.partition("LATEST INPUT / DIRECTION FOR THIS STEP:")[2].partition("Return ONLY")[0]
    lore = screen_lore.activate_for(thread, history, scene.get("direction", "") + "\n" + latest_direction) if thread else {"text": "", "report": [], "notes": []}
    obj = presets.get_active(user)
    cfg = presets.normalize(copy.deepcopy(obj.data))
    names = {"char": ", ".join(c.name for c in chars), "user": context["user_name"]}
    roster = "\n\n".join(messenger._character_block(c, user, u_name=names["user"],
                         share=context.get("share_memory") if c.author_id == user.pk else False, card_limit=None) for c in chars)
    slots = {"char_description": roster, "char_personality": "\n".join(c.personality or "" for c in chars),
             "scenario": context.get("scenario", ""), "persona": context["persona"],
             "examples": "\n".join(c.example_dialogue or "" for c in chars),
             "summary": context.get("memory", "") + "\n" + json.dumps(scene.get("continuity") or {}, ensure_ascii=False),
             "world_context": scene.get("direction", ""), "lore": lore["text"]}
    # Context belongs in preset slots/history. The engine supplies format, catalogs and this turn's direction.
    start, found, tail = prompt.partition("USER PROFILE:")
    _, output_found, output = tail.partition("Return ONLY a valid JSON object")
    latest = tail.partition("LATEST INPUT / DIRECTION FOR THIS STEP:")[2].partition("Return ONLY")[0]
    engine = start + "\n" + latest + "\nReturn ONLY a valid JSON object" + output if found and output_found else prompt
    engine += "\n" + mode_rules(scene) + "\nUse the preset's writing guidance within this JSON presentation format."
    if thread:
        phone = messenger.thread_data(thread)
        engine += "\nSCREEN CONTINUITY: " + json.dumps({
            "scene": phone.get("scene"), "plans": phone.get("events"),
            "linked_memory": messenger.linked_block(user, thread, phone),
            "profiles": [messenger.char_profile(c) for c in chars],
        }, ensure_ascii=False)
    engine += ("\nWrite 6–10 complete beats per turn. The opening must bridge directly from the last phone "
               "conversation, respecting the agreed meeting, current place, clothing and story time.")
    cast = [{"slug": c.slug, "name": c.name, "display_name": messenger.char_profile(c)["display_name"]}
            for c in chars]
    engine += (
        "\nSCENE CAST (only these characters may speak, subject to the authorship mode above):\n"
        + json.dumps(cast, ensure_ascii=False)
        + "\nCopy the exact slug into speaker_slug. Use narrator for narration. "
          "Mention anyone outside the selected cast in narration only."
    )
    if scene.get("user_participant") and scene.get("authoring_mode") == "director":
        from mainapp.models import EpisodeLook
        player = scene["user_participant"]
        look = EpisodeLook.objects.filter(author=user, pk=(scene.get("looks") or {}).get("user") or 0).first()
        engine += "\nUSER CHARACTER MOODS:\n" + json.dumps({"slug": "user", "name": player["name"],
                   "available_emotions": sorted((look.moods if look else None) or {"neutral": {}})}, ensure_ascii=False)
    cfg["blocks"].append(presets.normalize_block({"name": "VN presentation contract", "role": "system",
                         "content": engine, "enabled": True, "kind": "prompt"}))
    _, model = ai_client.resolve(user, "chat")
    pack = presets.assemble(cfg, slots, history, names, model=model, generation=generation)
    trace = {"model": model, "preset_id": obj.pk, "preset_name": obj.name, "generation": generation,
             "messages": copy.deepcopy(pack["messages"]), "params": pack["params"],
             "notes": pack["notes"] + lore["notes"], "lore": lore["report"],
             "sources": [{"role": m["role"], "sources": m["sources"]} for m in pack["preview"]]}
    scene["last_request"] = trace
    return pack


def stage_of(scene):
    stage = copy.deepcopy(scene.get("current_stage") or {
        "background": scene.get("background") or {}, "music": scene.get("music") or {},
        "location": scene.get("location") or "", "continuity": scene.get("continuity") or {}})
    stage["continuity"] = copy.deepcopy(scene.get("continuity") or stage.get("continuity") or {})
    return stage


def finish_timeline(beats, reported):
    """A turn's ending summary belongs only at its end, never at the opening passage."""
    stage = copy.deepcopy(beats[-1]["stage"])
    ending = {k: v for k, v in (reported or {}).items() if k in ("summary", "open_threads")}
    stage["continuity"] = vn_support.continuity_update(stage.get("continuity"), ending)
    beats[-1]["stage"] = copy.deepcopy(stage)
    if beats[-1].get("left") and isinstance(stage.get("present"), list):
        # Someone left on the turn's last passage: still seen saying it, gone from the next turn on.
        stage["present"] = [k for k in stage["present"] if k not in beats[-1]["left"]]
    return stage


def advance_stage(stage, change, tracks, backgrounds):
    stage = copy.deepcopy(stage)
    if not isinstance(change, dict):
        return stage
    for key, catalog in (("background", backgrounds), ("music", tracks)):
        if key not in change:
            continue
        value = change[key]
        if value == "none":
            stage[key] = {"id": "none", "name": "Silence" if key == "music" else "No backdrop", "url": ""}
        else:
            match = next((x for x in catalog if value in (x["id"], x["name"])), None)
            if match:
                stage[key] = match
    if isinstance(change.get("location"), str):
        stage["location"] = change["location"][:240]
    stage["continuity"] = vn_support.continuity_update(stage.get("continuity"), change.get("continuity"))
    return stage
