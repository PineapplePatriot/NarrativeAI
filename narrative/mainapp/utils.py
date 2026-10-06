import logging
from mainapp.models import Character, Worldbook
import json
from users.models import ApiConfig
from mainapp import ai_client
from mainapp.lorebook import load_worldbook, activate, format_for_prompt
from mainapp.trackers import (normalize_config as normalize_tracker_config,
                              normalize_state as normalize_tracker_state,
                              format_for_prompt as format_trackers)


def build_ai_request(user, character: Character, chat=None, worldbook_slug=None, message: str = None,
                     guidance=None, persistent_guides=None, summary=None):
    """
    Collects the per-message context that fills a preset's slots: lore matches,
    story trackers, summary, the manual World State notes and the director's note.
    `message` is the user's new message; without it (regenerate) the last user
    message from the chat file is used.
    Returns {"SystemPrompts": {slot texts}, "LoreReport": {...} or None}.
    """
    system_prompts = {}

    # Recent chat from the chat's file (the new message is not saved yet)
    from mainapp import chats
    chat_file_data = chats.read(chat) if chat is not None else {}
    all_messages = chat_file_data.get("messages", [])

    last_user_message_text = message
    if message:
        chat_history = all_messages[-10:]
    else:
        user_messages = [msg for msg in all_messages if msg[0] == "user"]
        chat_history = []
        if user_messages:
            last_user_message_text = user_messages[-1][2]
            last_idx = all_messages.index(user_messages[-1])
            chat_history = all_messages[max(0, last_idx - 10):last_idx]

    # Lorebook (worldbook) activation
    lore_report = None
    if worldbook_slug:
        try:
            wb = Worldbook.objects.get(slug=worldbook_slug)
            # chat_history never contains the message being answered, so add it
            scan_messages = list(chat_history)
            if last_user_message_text:
                scan_messages.append(last_user_message_text)
            lore = activate(load_worldbook(wb), scan_messages)
            # Text rules placed on lore entries (SillyTavern's "World Info" placement)
            from mainapp import presets, regex_rules
            rules = [r for r in regex_rules.for_chat(presets.normalize(presets.get_active(user).data), character, user)
                     if r["mode"] in ("saved", "prompt")]
            if any(regex_rules.LORE in r["placement"] for r in rules):
                names = {"char": character.name, "user": getattr(user, "persona_name", "") or user.username}
                lore["entries"] = [{**e, "content": regex_rules.run(rules, "saved", regex_rules.run(
                    rules, "prompt", e["content"], "lore", names), "lore", names)} for e in lore["entries"]]
            world_info_text = format_for_prompt(lore["entries"])
            if world_info_text:
                system_prompts["WorldInfo"] = world_info_text
            lore_report = {"book": wb.title, "report": lore["report"],
                           "notes": lore["notes"], "tokens_used": lore["tokens_used"]}
        except Exception as e:
            logging.getLogger(__name__).warning("Lorebook activation error: %s", e)
            lore_report = {"book": worldbook_slug, "report": [], "notes": [f"Lorebook error: {e}"]}

    # Story trackers the user chose to add to the prompt
    from mainapp import game
    from mainapp import extras
    kinds = extras.kinds_for(user)
    tracker_config = normalize_tracker_config(character.tracker_config, game.mode_for(user, character),
                                              "milestones" in kinds, "keepsakes" in kinds)
    story_state = format_trackers(tracker_config, normalize_tracker_state(chat_file_data.get("trackers"), tracker_config))
    if story_state:
        system_prompts["StoryState"] = story_state

    if summary:
        system_prompts["StorySummary"] = f"PREVIOUS STORY SUMMARY: {summary}\n(Older messages are omitted. Rely on this context.)"
    if persistent_guides and isinstance(persistent_guides, dict):
        from mainapp.views import pinned_note
        note = pinned_note(persistent_guides)
        if note:
            system_prompts["WorldContext"] = f"Pinned note from the user, for every reply:\n{note}"

    if guidance:
        system_prompts["DirectorNote"] = f"Director's note for this reply: {guidance}"

    # LoreReport is not sent to the model; it's shown in the chat tools menu
    return {"SystemPrompts": system_prompts, "LoreReport": lore_report}



def get_elevenlabs_key(user):
    """ElevenLabs API key for the user, or None if they have not set one."""
    api_config = ApiConfig.objects.filter(user=user).first()
    return api_config.eleven_key if api_config and api_config.eleven_key else None
