from mainapp.models import Character, Worldbook
import json
from users.models import ApiConfig
from mainapp import ai_client
from mainapp.lorebook import load_worldbook, activate, format_for_prompt
from mainapp.trackers import (normalize_config as normalize_tracker_config,
                              normalize_state as normalize_tracker_state,
                              format_for_prompt as format_trackers)


def build_ai_request(user, character: Character, worldbook_slug=None, message: str = None, guidance=None,
                     persistent_guides=None, summary=None):
    """
    Collects the per-message context that fills a preset's slots: lore matches,
    story trackers, summary, the manual World State notes and the director's note.
    `message` is the user's new message; without it (regenerate) the last user
    message from the chat file is used.
    Returns {"SystemPrompts": {slot texts}, "LoreReport": {...} or None}.
    """
    system_prompts = {}

    # Recent chat from the file (the new message is not saved yet)
    all_messages = []
    if character.chat_log_file and hasattr(character.chat_log_file, "path"):
        try:
            with open(character.chat_log_file.path, "r", encoding="utf-8") as f:
                all_messages = json.load(f)
        except Exception:
            all_messages = []
    # Chat logs are saved as {"messages": [...], "summary": ..., ...}; very old ones as a bare list
    chat_file_data = all_messages if isinstance(all_messages, dict) else {}
    if isinstance(all_messages, dict):
        all_messages = all_messages.get("messages", [])

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
            world_info_text = format_for_prompt(lore["entries"])
            if world_info_text:
                system_prompts["WorldInfo"] = world_info_text
            lore_report = {"book": wb.title, "report": lore["report"],
                           "notes": lore["notes"], "tokens_used": lore["tokens_used"]}
        except Exception as e:
            print(f"Lorebook activation error: {e}")
            lore_report = {"book": worldbook_slug, "report": [], "notes": [f"Lorebook error: {e}"]}

    # Story trackers the user chose to add to the prompt
    tracker_config = normalize_tracker_config(character.tracker_config)
    story_state = format_trackers(tracker_config, normalize_tracker_state(chat_file_data.get("trackers"), tracker_config))
    if story_state:
        system_prompts["StoryState"] = story_state

    if summary:
        system_prompts["StorySummary"] = f"PREVIOUS STORY SUMMARY: {summary}\n(Older messages are omitted. Rely on this context.)"
    if persistent_guides and isinstance(persistent_guides, dict):
        context_block = []
        if persistent_guides.get("situation"): context_block.append(f"CURRENT SITUATION: {persistent_guides['situation']}")
        if persistent_guides.get("clothes"): context_block.append(f"OUTFIT: {persistent_guides['clothes']}")
        if persistent_guides.get("state"): context_block.append(f"PHYSICAL STATE: {persistent_guides['state']}")
        if persistent_guides.get("thinking"): context_block.append(f"INNER THOUGHTS: {persistent_guides['thinking']}")
        if context_block:
            system_prompts["WorldContext"] = "\n".join(context_block)

    if guidance:
        system_prompts["DirectorNote"] = f"URGENT INSTRUCTION FOR NEXT RESPONSE: {guidance}"

    # LoreReport is not sent to the model; it's shown in the chat tools menu
    return {"SystemPrompts": system_prompts, "LoreReport": lore_report}




import requests
import re
from pydub import AudioSegment
from io import BytesIO
from datetime import datetime
import os



def get_elevenlabs_key(user):
    """ElevenLabs API key for the user, or None if they have not set one."""
    api_config = ApiConfig.objects.filter(user=user).first()
    return api_config.eleven_key if api_config and api_config.eleven_key else None


# --- Функція для розбиття тексту на ролі ---
def split_text_roles(text, user, character_name, has_second_char=False):
    """
    Викликає LLM для маркування частин тексту за ролями.
    Повертає список словників: [{"role": "narrator", "text": "..."}, ...]
    Без використання json.loads на неперевірений JSON.
    """
    if has_second_char:
        # --- PROMPT FOR 2 CHARACTERS + NARRATOR ---
        prompt = f"""
You are an audio script analyzer. Split the narrative text into parts based on who is speaking.

Roles:
1. "narrator": Descriptions, actions, internal thoughts, and setting scenes.
2. "character": Dialogue spoken by the main character ({character_name}).
3. "character_2": Dialogue spoken by ANY other character (not {character_name}).

Output ONLY a JSON array of objects:
[
  {{"role": "narrator", "text": "..."}},
  {{"role": "character", "text": "..."}},
  {{"role": "character_2", "text": "..."}}
]

Rules:
- Preserve original text exactly.
- Do not summarize.
- "character_2" applies to any speaker who is NOT {character_name}.

Text to analyze:
{text}
        """
    else:
        # --- PROMPT FOR 1 CHARACTER + NARRATOR ---
        prompt = f"""
You are an audio script analyzer. Split the narrative text into parts.

Roles:
1. "narrator": Descriptions, actions, and inner thoughts.
2. "character": Dialogue spoken by {character_name}.

Output ONLY a JSON array:
[
  {{"role": "narrator", "text": "..."}},
  {{"role": "character", "text": "..."}}
]

Text to analyze:
{text}
        """
    llm_text = ai_client.complete(user, "voice_split", [{"role": "user", "content": prompt}])

    # видаляємо ```json або ```
    llm_text = re.sub(r"```(?:json)?\n?", "", llm_text)
    llm_text = llm_text.replace("```", "").strip()

    # --- regex для вилучення ролей і тексту ---
    pattern = r'\{\s*"role"\s*:\s*"([^"]+)"\s*,\s*"text"\s*:\s*"(.*?)"\s*\}'
    matches = re.findall(pattern, llm_text, flags=re.DOTALL)

    if not matches:
        # fallback: якщо regex нічого не знайшов, повертаємо весь текст як narrator
        return [{"role": "narrator", "text": llm_text}]

    # повертаємо список словників
    parsed = [{"role": role, "text": text.replace('\\"', '"')} for role, text in matches]
    return parsed

# --- Функція для озвучення через ElevenLabs ---
def synthesize_speech(text, voice_id, ELEVENLABS_API_KEY):
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json"
    }
    data = {"text": text, "voice_settings": {"stability": 0.7, "similarity_boost": 0.7}}

    response = requests.post(url, headers=headers, json=data)
    response.raise_for_status()
    return BytesIO(response.content)


from django.conf import settings


def narrate_text_backend(
        text,
        user,
        character_name,
        ELEVENLABS_API_KEY,
        narrator_voice_id,
        character_voice_id,
        second_character_voice_id,
        output_dir=None,
        is_mult=False):
    username = user.username
    if output_dir is None:
        output_dir = os.path.join(settings.MEDIA_ROOT, "audio_files")
    else:
        output_dir = os.path.join(settings.BASE_DIR, output_dir)

    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%H_%M_%S")
    filename = f"{username}_{character_name}_{timestamp}.mp3"
    output_file = os.path.join(output_dir, filename)

    parts = split_text_roles(text, user, character_name, has_second_char=is_mult)
    final_audio = AudioSegment.silent(duration=0)


    for part in parts:
        role = part["role"]
        voice_id = None

        if role == "narrator":
            voice_id = narrator_voice_id
        elif role == "character":
            voice_id = character_voice_id
        elif role == "character_2":
            voice_id = second_character_voice_id
            if not voice_id:
                voice_id = narrator_voice_id

        if not voice_id:
            continue

        try:
            audio_bytes = synthesize_speech(part["text"], voice_id, ELEVENLABS_API_KEY)
            audio_segment = AudioSegment.from_file(audio_bytes, format="mp3")
            final_audio += audio_segment
        except Exception as e:
            print(f"Audio chunk failed: {e}")
            continue

    final_audio.export(output_file, format="mp3")

    # Повертаємо URL відносно MEDIA_URL
    audio_url = os.path.join(settings.MEDIA_URL, "audio_files", filename)
    return audio_url
