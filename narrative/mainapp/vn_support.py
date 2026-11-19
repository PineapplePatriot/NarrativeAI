"""Context and display helpers for scenes; presentation never sets narrative length."""
import json
import re
import textwrap
from datetime import datetime

from django.db.models import Q
from django.utils import timezone

from mainapp import ai_client, messenger, writing_quality
from mainapp.models import Character, MessengerThread


def scene_characters(user, slugs):
    available = Character.objects.filter(Q(author=user) | Q(is_default=True), slug__in=slugs)
    by_slug = {c.slug: c for c in available}
    return [by_slug[s] for s in slugs if s in by_slug]


def linked_thread(user, scene):
    return MessengerThread.objects.filter(user=user, id=scene.get("thread_id")).first()


def split_display_text(text, width=420):
    """Wrap complete blocks for the screen, retaining every word and paragraph."""
    boxes = []
    for paragraph in re.split(r"\n\s*\n", str(text).strip()):
        boxes.extend(textwrap.wrap(paragraph, width=width, break_long_words=False,
                                   break_on_hyphens=False, replace_whitespace=False))
    return boxes


def model_rules(user):
    from mainapp import model_profiles
    profile = ai_client.main_profile(user)
    model = model_profiles.for_style(profile.model) if profile and profile.model else None
    counter = writing_quality.catalog().get("default_counters", {}).get((model or {}).get("id"), "")
    return "\n\n".join(p for p in (counter, writing_quality.helper_taste(user)) if p)


def scene_context(user, thread=None):
    """Freeze the chosen thread's identity, memory and story clock at the transition."""
    from mainapp.cards import user_name
    data = messenger.thread_data(thread) if thread else {}
    persona = data.get("persona") or {}
    name = persona.get("name") or user_name(user)
    now = messenger.chat_now(data)
    clock = timezone.localtime(datetime.fromtimestamp(now, tz=timezone.get_current_timezone()))
    lines = []
    for m in data.get("messages", [])[-data.get("context_size", 30):]:
        who = name if m.get("role") == "user" else m.get("sender_name") or m.get("role")
        text = m.get("text") or (m.get("voice") or {}).get("transcript") or ""
        photo = m.get("photo") or {}
        if photo:
            text += " [Photo: " + str(photo.get("seen") or photo.get("caption") or photo.get("prompt") or "") + "]"
        lines.append(f"{who}: {text}")
    return {
        "user_name": name,
        "persona": persona.get("description") or getattr(user, "persona_description", "") or "",
        "clock": clock.strftime("%A, %d %B %Y, %H:%M"),
        "memory": data.get("memory") or "",
        "scenario": data.get("scenario_override") or "",
        "share_memory": data.get("share_memory"),
        "conversation": "\n".join(lines),
    }


def continuity_update(previous, candidate):
    """Model-authored continuity stays explicit and bounded, separate from the transcript."""
    result = dict(previous or {})
    if isinstance(candidate, dict):
        for key in ("summary", "location", "time", "outfits", "positions", "open_threads"):
            if key in candidate and isinstance(candidate[key], (str, dict, list)):
                # A corrupt response cannot grow the prompt indefinitely.
                if len(json.dumps(candidate[key], ensure_ascii=False)) <= 12000:
                    if key in ("outfits", "positions") and isinstance(candidate[key], dict):
                        result[key] = {**(result.get(key) if isinstance(result.get(key), dict) else {}), **candidate[key]}
                    else:
                        result[key] = candidate[key]
    return result


def polish_blocks(user, blocks, context, enabled=False):
    """Use Bulba's approved repairs before splitting; preserve originals and metadata."""
    from mainapp.bulba import polish
    habits = polish.approved(user) if enabled else []
    if not habits:
        return blocks, ""
    descriptions = []
    dislikes = polish.watch.user_data(user).get("dislikes") or {}
    for habit in habits:
        if habit == polish.MODEL_KNOWN:
            descriptions.extend(polish.model_habits(user))
        else:
            descriptions.append(polish.MEANING.get(habit) or dislikes.get(habit) or habit)
    fields = {str(i): b.get("text", "") for i, b in enumerate(blocks) if isinstance(b, dict) and b.get("text")}
    payload = "\n\n".join(f"§§ {i} §§\n{text}" for i, text in fields.items())
    try:
        answer = ai_client.complete(user, "polish", [
            {"role": "system", "content": polish.INSTRUCTIONS.read_text(encoding="utf-8")},
            {"role": "user", "content": (
                "Repair only the user's approved habits: " + "; ".join(descriptions)
                + ". Preserve every §§ numbered section, speaker, fact, intention and paragraph. "
                "Do not shorten descriptive writing merely for being detailed. Return the usual fixes JSON.\n"
                + "Scene context:\n" + context + "\nScene blocks:\n" + payload)},
        ], max_tokens=4000, temperature=0, response_format={"type": "json_object"})
        new, fixes = polish.apply_fixes(payload, polish._parse(answer))
    except ai_client.AIError as exc:
        return blocks, f"Bulba could not polish this turn: {exc}"
    parts = re.split(r"(?m)^§§ (\d+) §§\n", new)
    found = {parts[i]: parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}
    if not fixes or parts[1::2] != list(fields) or not all(found.values()):
        return blocks, ""
    output = [dict(b) if isinstance(b, dict) else b for b in blocks]
    for i, original in fields.items():
        if found[i] != original:
            output[int(i)].update(text=found[i], original_text=original)
    return output, ""
