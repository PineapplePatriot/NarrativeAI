"""
The episode's Watch: after each turn, Bulba reads the new passages against what's fixed and established and points
out where the story slipped (continuity), never style.

Established: the casting sheet (facts, the place card), the chat's memory, the record of the episode so far (summary,
open threads, story time), who is present, and what each person wears (their look, or the clothes the story changed
them into). A slip: someone knowing what they couldn't, a fact or promise contradicted, the wrong place, time or
objects, clothes that don't match, someone present who isn't there.

Each slip comes with Bulba's fix (the passage rewritten with only the slip changed). The user applies the fix (a
passage edit), regenerates from that passage with the slip named, or ignores it.
"""
import json

from mainapp import ai_client, messenger, vn_casting, vn_scenes

MAX_SLIPS = 3


def established(user, scene):
    """What the new passages must agree with, as lines for Bulba."""
    lines = []
    brief = vn_casting.brief(scene.get("casting"))
    if brief:
        lines.append(brief)
    memory = (scene.get("context") or {}).get("memory")
    if memory:
        lines.append("From the chat's memory: " + str(memory)[:1500])
    record = scene.get("continuity_before_turn") or scene.get("continuity") or {}
    for label, key in (("Story so far", "summary"), ("Story time", "time"), ("Open threads", "open_threads"),
                       ("Where they are", "location")):
        if record.get(key):
            value = record[key] if isinstance(record[key], str) else json.dumps(record[key], ensure_ascii=False)
            lines.append(f"{label}: {value[:1200]}")
    names = scene.get("character_names") or []
    before = ((scene.get("current_beats") or [{}])[0].get("stage_before") or {}).get("present")
    here = [n for s, n in zip(scene.get("character_slugs") or [], names) if not isinstance(before, list) or s in before]
    lines.append("Present when the turn began: " + ", ".join(here + [(scene.get("user_participant") or {}).get("name") or "the user"]))
    gone = [n for n in names if n not in here]
    if gone:
        lines.append("Gone when the turn began (not present unless the turn has them arrive): " + ", ".join(gone))
    looks = vn_scenes.scene_looks(user, scene)
    worn = record.get("outfits") if isinstance(record.get("outfits"), dict) else {}
    for slug, name in zip(scene.get("character_slugs") or [], names):
        outfit = worn.get(slug) or (looks[slug].outfit if slug in looks else "")
        if outfit:
            lines.append(f"{name} wears: {outfit}")
    return "\n".join(lines)


def _blocks(beats):
    """[(label, first beat id, speaker, whole passage text)] for the passages of one turn."""
    out, seen = [], {}
    for b in beats:
        group = b.get("block_id") or b.get("id")
        if group in seen:
            continue
        seen[group] = True
        text = b.get("block_text") or " ".join(x.get("text", "") for x in beats if (x.get("block_id") or x.get("id")) == group)
        out.append((f"p{len(out) + 1}", b["id"], b.get("speaker_name") or "Narrator", text))
    return out


def check(user, scene, beats):
    """Bulba's slips for `beats` (one turn's passages): [{"beat_id", "what", "fact", "fix"}], at most three."""
    blocks = [b for b in _blocks(beats) if b[3].strip()]
    if not blocks:
        return []
    prompt = (
        "You check one turn of an interactive visual novel for CONTINUITY only: not style, not quality, not taste.\n"
        "ESTABLISHED:\n" + established(user, scene) + "\n\n"
        "THE TURN, passage by passage:\n"
        + "\n".join(f"[{label}] {speaker}: {text[:1200]}" for label, _, speaker, text in blocks) + "\n"
        + "".join(f"(Note: {b.get('speaker_name')} speaks in this turn without an arrival being written.)\n"
                  for b in beats if b.get("auto_entered")) + "\n"
        "List each passage that clearly contradicts something established: someone knows something they couldn't "
        "know, a fact, plan or promise is contradicted, the place, time or objects are wrong, clothes don't match what "
        "they wear, someone acts as present who isn't there. Only clear contradictions; when in doubt, it's fine.\n"
        'Answer with JSON only: {"slips": []} or {"slips": [{"passage": "p2", "what": "the slip, in one short line", '
        '"fact": "the established fact it breaks", "fix": "that whole passage rewritten so the slip is gone, '
        'everything else word for word the same"}]}'
    )
    out = messenger.ask_json(user, prompt, need=("slips",), max_tokens=1800, task="summary", temperature=0.2) \
        if blocks else {}
    by_label = {label: (beat_id, text) for label, beat_id, _, text in blocks}
    slips = []
    for slip in out.get("slips") or [] if isinstance(out.get("slips"), list) else []:
        if not isinstance(slip, dict):
            continue
        label = str(slip.get("passage") or "").strip("[] ").lower()
        if label not in by_label or not str(slip.get("what") or "").strip():
            continue
        beat_id, original = by_label[label]
        fix = " ".join(str(slip.get("fix") or "").split())[:3000]
        slips.append({"beat_id": beat_id, "what": str(slip["what"]).strip()[:240],
                      "fact": str(slip.get("fact") or "").strip()[:240],
                      "fix": fix if fix and fix != " ".join(original.split()) else ""})
        if len(slips) == MAX_SLIPS:
            break
    return slips


def run(user):
    """Check the open episode's latest turn and keep the slips on it. Returns (scene, slips)."""
    scene = vn_scenes.get_vn_state(user).get("active_scene")
    if not scene:
        raise ai_client.AIError("No episode is open.")
    expected = (scene["id"], scene.get("revision", 0))
    beats = scene.get("current_beats") or []
    slips = check(user, scene, beats)
    scene["watch"] = {"turn": beats[0]["id"] if beats else "", "slips": slips}
    vn_scenes.save_vn_state(user, {"active_scene": scene}, expected=expected)
    return vn_scenes.get_vn_state(user)["active_scene"], slips


def dismiss(user, beat_id):
    scene = vn_scenes.get_vn_state(user).get("active_scene")
    if not scene:
        raise ai_client.AIError("No episode is open.")
    expected = (scene["id"], scene.get("revision", 0))
    watch = scene.get("watch") or {}
    watch["slips"] = [s for s in watch.get("slips") or [] if s.get("beat_id") != beat_id]
    scene["watch"] = watch
    vn_scenes.save_vn_state(user, {"active_scene": scene}, expected=expected)
    return vn_scenes.get_vn_state(user)["active_scene"]
