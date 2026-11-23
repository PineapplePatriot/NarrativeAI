"""Revision operations restore passage checkpoints before generating or continuing."""
import copy
import json
import uuid

from django.db import transaction

from mainapp import ai_client, messenger, vn_story, vn_support
from mainapp.models import MessengerThread


def current(user):
    from mainapp import vn_scenes
    state = vn_scenes.get_vn_state(user)
    if not state.get("active_scene"):
        raise ai_client.AIError("Open an episode first.")
    return state, copy.deepcopy(state["active_scene"])


def backup(state, scene, label):
    return list(state.get("drafts") or []) + [{"id": "vnd_" + uuid.uuid4().hex[:10],
        "label": label, "title": scene.get("title", "Episode"), "scene": copy.deepcopy(scene)}]


@transaction.atomic
def park(user):
    from mainapp import vn_scenes
    state, scene = current(user)
    vn_scenes.save_vn_state(user, {"active_scene": None, "drafts": backup(state, scene, "Unfinished episode")},
                           expected=(scene["id"], scene.get("revision", 0)))


def cut(scene, beat_id, include=False):
    beats = scene.get("beats") or []
    index = next((i for i, b in enumerate(beats) if b.get("id") == beat_id), None)
    if index is None:
        raise ai_client.AIError("That passage is not in the active episode.")
    selected = beats[index]
    group = selected.get("block_id") or selected["id"]
    indices = [i for i, b in enumerate(beats) if (b.get("block_id") or b.get("id")) == group]
    first, last = min(indices), max(indices)
    passage = copy.deepcopy(beats[first])
    text = passage.get("block_text") or " ".join(b["text"] for b in beats[first:last + 1])
    end = last + 1 if include else first
    stage = beats[last].get("stage") if include else passage.get("stage_before")
    if not isinstance(stage, dict):
        raise ai_client.AIError("This older passage has no historical checkpoint. Its text is intact; continue the episode to create new checkpoints.")
    stage = copy.deepcopy(stage)
    scene.update(beats=copy.deepcopy(beats[:end]), history=copy.deepcopy(beats[:end]), current_beats=[], current_stage=stage,
                 continuity=copy.deepcopy(stage.get("continuity") or {}), choices=[], choice_cache=[], handoff="user_turn")
    scene.update({k: stage.get(k) for k in ("background", "music", "location")})
    return scene, passage, text


def regenerate(user, beat_id, direction=""):
    from mainapp import vn_scenes
    state, original = current(user)
    base, passage, _ = cut(copy.deepcopy(original), beat_id)
    if (passage.get("speaker_slug") == "user" or passage.get("kind") == "direction") and not passage.get("generated"):
        raise ai_client.AIError("Edit your own input, or regenerate a character passage.")
    drafts = backup(state, original, "Before regeneration")
    return vn_scenes.step_scene(user, base_scene=base, generation="regenerate", turn_direction=(
        "Regenerate from this point. Discard the old continuation. " + direction), save_updates={"drafts": drafts})[0]


def edit(user, beat_id, text):
    from mainapp import vn_scenes
    state, original = current(user)
    base, passage, _ = cut(copy.deepcopy(original), beat_id)
    if not text.strip():
        raise ai_client.AIError("A passage cannot be empty.")
    chars = vn_support.scene_characters(user, base.get("character_slugs") or [])
    # Only the retained history and edited text are visible; discarded events cannot leak into the repair.
    if passage.get("kind") == "direction":
        result = {"stage": {}}  # An author instruction is not a fictional event.
    else:
        result = messenger.ask_json(user,
            "Update a scene's continuity after a manual edit. Do not rewrite the edited text. Return JSON {stage: "
            "{location, continuity: {summary, outfits, positions, time, open_threads}}}. Record only what the edited "
            "text establishes and retain relevant earlier facts. Do not infer new motives, intimacy, consent or events.\n"
            + json.dumps({"before": base.get("current_stage"), "edited_text": text,
                          "speaker": passage.get("speaker_name"), "earlier_text": [f"{b.get('speaker_name')}: {b['text']}" for b in base["beats"][-12:]]}, ensure_ascii=False),
            need=("stage",), max_tokens=1800)
    if not isinstance(result.get("stage"), dict):
        raise ai_client.AIError("Bulba returned invalid continuity. Your original passage is still saved.")
    patch = result["stage"]
    if (passage.get("speaker_slug") == "user" or passage.get("kind") == "direction") and not passage.get("generated"):
        stage = vn_story.advance_stage(base["current_stage"], patch,
                                       vn_scenes.available_music_tracks(chars), vn_scenes.available_backgrounds(chars))
        replacement = [{**passage, "id": "vnb_" + uuid.uuid4().hex[:8], "text": text, "stage": stage}]
    else:
        replacement = vn_scenes._enrich_beats(user, chars, [{**passage, "text": text, "original_text": "", "stage": patch}],
            initial_stage=base["current_stage"], looks=vn_scenes.scene_looks(user, base),
            authoring_mode=base.get("authoring_mode", "roleplay"), user_participant=base.get("user_participant"))
    base["beats"].extend(replacement)
    base.update(history=base["beats"], current_beats=replacement, current_stage=replacement[-1]["stage"],
                continuity=replacement[-1]["stage"].get("continuity") or {}, last_request=None)
    base.update({k: base["current_stage"].get(k) for k in ("background", "music", "location")})
    vn_scenes.save_vn_state(user, {"active_scene": base, "drafts": backup(state, original, "Before editing")},
                           expected=(original["id"], original.get("revision", 0)))
    return base


def clone_phone(user, scene):
    thread = vn_support.linked_thread(user, scene)
    if not thread:
        return None
    raw = copy.deepcopy(scene.get("phone_snapshot") or thread.data or {})
    # Lore definitions are editable chat configuration. Copy the selection in force at the fork,
    # while phone messages/memory remain at the episode's original transition checkpoint.
    from mainapp.screen_lore import FIELDS
    for field in FIELDS:
        if field in (thread.data or {}):
            raw[field] = copy.deepcopy(thread.data[field])
        else:
            raw.pop(field, None)
    raw.update(unread=0, regen_prev=[], last_auto_at=None,
               branch_of={"thread_id": thread.id, "title": thread.title, "episode_id": scene["id"]})
    branch = MessengerThread.objects.create(user=user, title=f"{thread.title} · episode branch"[:200],
                                             is_group=thread.is_group, data=raw)
    branch.characters.set(thread.characters.all())
    return branch


@transaction.atomic
def branch(user, beat_id):
    from mainapp import vn_scenes
    state, original = current(user)
    fork, _, _ = cut(copy.deepcopy(original), beat_id, include=True)
    phone = clone_phone(user, fork)
    fork.update(id="vns_" + uuid.uuid4().hex[:10], parent_scene_id=original["id"],
                thread_id=phone.pk if phone else None, title=original.get("title", "Episode") + " · branch")
    vn_scenes.save_vn_state(user, {"active_scene": fork, "drafts": backup(state, original, "Original before branch")},
                           expected=(original["id"], original.get("revision", 0)))
    return fork


@transaction.atomic
def resume(user, draft_id):
    from mainapp import vn_scenes
    state = vn_scenes.get_vn_state(user)
    draft = next((d for d in state.get("drafts", []) if d.get("id") == draft_id), None)
    if not draft:
        raise ai_client.AIError("Saved version not found.")
    active = state.get("active_scene") or {}
    drafts = backup(state, active, "Before switching versions") if active else state.get("drafts", [])
    scene = copy.deepcopy(draft["scene"])
    phone = clone_phone(user, scene)
    scene.update(resumed_from=scene["id"], id="vns_" + uuid.uuid4().hex[:10], thread_id=phone.pk if phone else None)
    vn_scenes.save_vn_state(user, {"active_scene": scene, "drafts": drafts},
                           expected=(active.get("id", ""), active.get("revision", 0)))
    return scene


@transaction.atomic
def reopen_completed(user, episode_id):
    from mainapp import vn_scenes
    state = vn_scenes.get_vn_state(user)
    entry = next((e for e in state["gallery"] if e.get("id") == episode_id), None)
    if not entry or not isinstance(entry.get("episode"), dict):
        raise ai_client.AIError("This older episode has no resumable checkpoint. Its transcript is still available.")
    original = state.get("active_scene") or {}
    drafts = backup(state, original, "Before reopening an episode") if original else state.get("drafts", [])
    scene = copy.deepcopy(entry["episode"])
    phone = clone_phone(user, scene)
    scene.update(id="vns_" + uuid.uuid4().hex[:10], thread_id=phone.pk if phone else None,
                 parent_scene_id=entry["id"], title=scene.get("title", "Episode") + " · reopened")
    vn_scenes.save_vn_state(user, {"active_scene": scene, "drafts": drafts},
                           expected=(original.get("id", ""), original.get("revision", 0)))
    return scene
