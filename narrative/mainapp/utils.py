from mainapp.models import Character, Worldbook, ChatSettings
import json
from users.models import ApiConfig
from mainapp.lorebook import load_worldbook, activate, format_for_prompt


def build_ai_request(user, character: Character, chat_settings: ChatSettings, worldbook_slug=None, message: str = None, guidance=None, impersonate=None, persistent_guides=None, summary=None):
    """
    Формує JSON-запит для моделі ШІ (структурований і читабельний).
    Використовує message як останнє повідомлення користувача.
    Якщо message=None, підвантажує останнє повідомлення з файлу чату.
    """

    # 1. Завантажуємо ChatSettings JSON
    settings_data = {}
    if chat_settings and chat_settings.json_file and hasattr(chat_settings.json_file, "path"):
        try:
            with open(chat_settings.json_file.path, "r", encoding="utf-8") as f:
                settings_data = json.load(f)
        except Exception:
            settings_data = {}

    # Витягуємо ядро (core) і системні промпти
    core_keys = {"max_tokens", "seed", "sampling"}
    core_data = {k: settings_data[k] for k in core_keys if k in settings_data}
    system_prompts = {k: v for k, v in settings_data.items() if k not in core_keys}

    # 2. Character description
    character_data = {
        "name": character.name,
        "description": character.description,
        "scenario": character.scenario,
        "initial_message": character.initial_message,
        "creator_notes": character.creator_notes,
    }


    # 3. Chat history та останнє повідомлення користувача
    chat_history = []
    last_user_message = None
    last_user_message_text = message

    # Load full chat log once (used in both paths)
    all_messages = []
    if character.chat_log_file and hasattr(character.chat_log_file, "path"):
        try:
            with open(character.chat_log_file.path, "r", encoding="utf-8") as f:
                all_messages = json.load(f)
        except Exception:
            all_messages = []

    if message is not None and message != "":
        # Real-time chat: use recent file history + current message as "now"
        chat_history = all_messages[-10:]  # keep last N turns
        last_user_message = ["user", "now", message, "neutral"]
    else:
        # Continue/regenerate: last user message comes from file
        user_messages = [msg for msg in all_messages if msg[0] == "user"]
        if user_messages:
            last_user_message = user_messages[-1]
            last_user_message_text = last_user_message[2]

            last_idx = all_messages.index(last_user_message)
            chat_history = all_messages[max(0, last_idx - 10):last_idx]


    # 4. User persona
    user_persona = {
        "persona_name": getattr(user, "persona_name", None),
        "persona_description": getattr(user, "persona_description", None),
        "name": getattr(user, "name", user.username),
        "date_birth": user.date_birth.isoformat() if getattr(user, "date_birth", None) else None,
    }

    # 5. Lorebook (worldbook) activation
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

    # 3. Director's Note (Guidance) Injection
    if guidance:
        system_prompts["DirectorNote"] = f"URGENT INSTRUCTION FOR NEXT RESPONSE: {guidance}"
    # Формуємо фінальний JSON
    ai_request = {
        "Core": core_data,
        "SystemPrompts": system_prompts,
        "CharacterDescription": character_data,
        "ChatHistory": chat_history,
        "LastUserMessage": last_user_message,
        "UserPersona": user_persona,
        # Not sent to the model; shown in the chat tools menu
        "LoreReport": lore_report,
    }


    engagement_settings = {}
    try:
        base_dir = os.path.join(settings.MEDIA_ROOT, "chat_settings2")
        file_path = os.path.join(base_dir, f"chat_settings2_{user.id}_active.json")
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                engagement_settings = json.load(f)
    except Exception as e:
        print(f"Failed to load chat_settings2 for user {user.id}: {e}")
        engagement_settings = {}

    ai_request["PromptingGroundSettings"] = engagement_settings
    # -------------------------------------------------------------------------------

    # print(ai_request)
    return ai_request




import requests
import re
from pydub import AudioSegment
from io import BytesIO
from datetime import datetime
import os



def get_openrouter_key(user):
    """
    Повертає OpenRouter API ключ для заданого користувача.
    """
    try:
        api_config = user.api_config
    except ApiConfig.DoesNotExist:
        raise ValueError(f"API configuration not found for user {user.username}")

    if not api_config.chat_key:
        raise ValueError(f"OpenRouter API key is missing for user {user.username}")

    return api_config.chat_key


def get_elevenlabs_key(user):
    """
    Повертає ElevenLabs API ключ для заданого користувача.
    Якщо ключ порожній, повертає None.
    """
    try:
        api_config = user.api_config
    except ApiConfig.DoesNotExist:
        raise ValueError(f"API configuration not found for user {user.username}")

    # eleven_key може бути порожнім
    return api_config.eleven_key if api_config.eleven_key else None


# --- Функція для розбиття тексту на ролі ---
def split_text_roles(text, OPENROUTER_API_KEY, model_name, character_name, has_second_char=False):
    """
    Викликає LLM для маркування частин тексту за ролями.
    Повертає список словників: [{"role": "narrator", "text": "..."}, ...]
    Без використання json.loads на неперевірений JSON.
    """
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
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
    data = {"model": model_name, "messages": [{"role": "user", "content": prompt}]}

    response = requests.post(url, headers=headers, json=data)
    response.raise_for_status()
    llm_text = response.json()["choices"][0]["message"]["content"]

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
        username,
        character_name,
        OPENROUTER_API_KEY,
        ELEVENLABS_API_KEY,
        narrator_voice_id,
        character_voice_id,
        second_character_voice_id,
        MODEL_NAME,
        output_dir=None,
        is_mult=False):

    print("OPENROUTER_API_KEY", OPENROUTER_API_KEY)
    print("ELEVENLABS_API_KEY", ELEVENLABS_API_KEY)
    if output_dir is None:
        output_dir = os.path.join(settings.MEDIA_ROOT, "audio_files")
    else:
        output_dir = os.path.join(settings.BASE_DIR, output_dir)

    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%H_%M_%S")
    filename = f"{username}_{character_name}_{timestamp}.mp3"
    output_file = os.path.join(output_dir, filename)

    parts = split_text_roles(text, OPENROUTER_API_KEY, MODEL_NAME, character_name, has_second_char=is_mult)
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
