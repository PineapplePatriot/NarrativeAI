"""
Voicing a reply with ElevenLabs: narration in the narrator's voice, every speaker in their own.

1. The reply is split into narration and quoted speech (by its quote marks, so the text is never changed).
2. One small call on the background model says who speaks each quote, adds a delivery cue where the
   narration describes one ("she whispered" -> [whispers]), and guesses gender and age for new speakers.
3. Speakers get voices: the character's own, the card's cast list (Pantalone -> a voice), then voices
   picked for this chat from the user's ElevenLabs voices (kept, so a guard keeps his voice).
4. ElevenLabs Text to Dialogue (eleven_v3) reads it as one recording; long replies go in pieces.
   If that endpoint refuses (plan or model), each line is read separately and joined.
"""
import io
import json
import logging
import re
import time

import requests

from mainapp import ai_client

log = logging.getLogger(__name__)
API = "https://api.elevenlabs.io/v1"
DIALOGUE_MODEL = "eleven_v3"
SINGLE_MODEL = "eleven_multilingual_v2"
REQUEST_LIMIT = 2800          # Text to Dialogue takes up to 3,000 characters per request
NARRATOR = "__narrator__"
CUES = ("whispers", "shouts", "laughs", "chuckles", "sighs", "exhales", "sarcastic", "curious", "excited",
        "crying", "nervous", "softly", "coldly", "amused", "angry", "hesitant", "mischievously")
QUOTE = re.compile(r"“[^”]+”|\"[^\"\n]+\"|«[^»]+»|„[^“”]+[“”]")


class VoiceError(Exception):
    """A readable problem with voicing, shown to the user as is."""


# ---------------------------------------------------------------------------
# The user's ElevenLabs voices
# ---------------------------------------------------------------------------

_voice_cache = {}

# Built-in 21 ElevenLabs premade voices served directly on OpenRouter's /api/v1/audio/speech endpoint
# (works with any OpenRouter API key, no separate ElevenLabs subscription required).
OPENROUTER_VOICES = [
    {"id": "sarah", "name": "Sarah", "gender": "female", "age": "young", "accent": "American", "description": "Soft, warm, conversational", "use": "conversational", "preview": ""},
    {"id": "alice", "name": "Alice", "gender": "female", "age": "middle_aged", "accent": "British", "description": "Confident, clear, articulate", "use": "narration", "preview": ""},
    {"id": "bella", "name": "Bella", "gender": "female", "age": "young", "accent": "American", "description": "Expressive, gentle, intimate", "use": "characters", "preview": ""},
    {"id": "jessica", "name": "Jessica", "gender": "female", "age": "young", "accent": "American", "description": "Playful, bright, expressive", "use": "conversational", "preview": ""},
    {"id": "laura", "name": "Laura", "gender": "female", "age": "young", "accent": "American", "description": "Upbeat, sassy, lively", "use": "characters", "preview": ""},
    {"id": "lily", "name": "Lily", "gender": "female", "age": "middle_aged", "accent": "British", "description": "Velvety, theatrical, raspy", "use": "characters", "preview": ""},
    {"id": "matilda", "name": "Matilda", "gender": "female", "age": "middle_aged", "accent": "American", "description": "Warm, friendly, composed", "use": "narration", "preview": ""},
    {"id": "river", "name": "River", "gender": "neutral", "age": "young", "accent": "American", "description": "Calm, relaxed, gender-neutral", "use": "conversational", "preview": ""},
    {"id": "george", "name": "George", "gender": "male", "age": "middle_aged", "accent": "British", "description": "Warm, resonant, rasp", "use": "narration", "preview": ""},
    {"id": "adam", "name": "Adam", "gender": "male", "age": "middle_aged", "accent": "American", "description": "Deep, steady, confident", "use": "narration", "preview": ""},
    {"id": "bill", "name": "Bill", "gender": "male", "age": "old", "accent": "American", "description": "Trustworthy, crisp, seasoned", "use": "narration", "preview": ""},
    {"id": "brian", "name": "Brian", "gender": "male", "age": "middle_aged", "accent": "American", "description": "Deep, resonant, comforting", "use": "narration", "preview": ""},
    {"id": "callum", "name": "Callum", "gender": "male", "age": "middle_aged", "accent": "Transatlantic", "description": "Gravelly, intense, edgy", "use": "characters", "preview": ""},
    {"id": "charlie", "name": "Charlie", "gender": "male", "age": "young", "accent": "Australian", "description": "Casual, natural, energetic", "use": "conversational", "preview": ""},
    {"id": "chris", "name": "Chris", "gender": "male", "age": "middle_aged", "accent": "American", "description": "Casual, down-to-earth", "use": "conversational", "preview": ""},
    {"id": "daniel", "name": "Daniel", "gender": "male", "age": "middle_aged", "accent": "British", "description": "Authoritative, composed", "use": "narration", "preview": ""},
    {"id": "eric", "name": "Eric", "gender": "male", "age": "middle_aged", "accent": "American", "description": "Friendly, smooth, grounded", "use": "conversational", "preview": ""},
    {"id": "harry", "name": "Harry", "gender": "male", "age": "young", "accent": "American", "description": "Fierce, dramatic, intense", "use": "characters", "preview": ""},
    {"id": "liam", "name": "Liam", "gender": "male", "age": "young", "accent": "American", "description": "Energetic, youthful, warm", "use": "conversational", "preview": ""},
    {"id": "roger", "name": "Roger", "gender": "male", "age": "middle_aged", "accent": "American", "description": "Laid-back, confident, smooth", "use": "conversational", "preview": ""},
    {"id": "will", "name": "Will", "gender": "male", "age": "young", "accent": "American", "description": "Friendly, optimistic, relaxed", "use": "conversational", "preview": ""},
]

OPENROUTER_VOICE_NAMES = {v["id"]: v for v in OPENROUTER_VOICES}
OPENROUTER_TTS_MODEL_DEFAULT = "elevenlabs/eleven-v4-turbo"
OPENROUTER_TTS_MODELS = (
    "elevenlabs/eleven-v4-turbo",
    "elevenlabs/eleven-v4",
    "elevenlabs/eleven-v3-conversational",
    "elevenlabs/eleven-v3",
    "elevenlabs/eleven-multilingual-v2",
    "elevenlabs/eleven-flash-v2.5",
)


def list_voices(key):
    """[{"id", "name", "gender", "age", "accent", "description", "preview"}], cached for ten minutes."""
    cached = _voice_cache.get(key)
    if cached and time.time() - cached[0] < 600:
        return cached[1]
    try:
        resp = requests.get(f"{API}/voices", headers={"xi-api-key": key}, timeout=20)
    except requests.RequestException as e:
        raise VoiceError(f"Couldn't reach ElevenLabs ({type(e).__name__}).")
    if resp.status_code == 401:
        raise VoiceError("ElevenLabs didn't accept the key. Check it on the Extras page.")
    if not resp.ok:
        raise VoiceError(f"ElevenLabs answered {resp.status_code}.")
    voices = []
    for v in resp.json().get("voices") or []:
        labels = v.get("labels") or {}
        voices.append({"id": v.get("voice_id"), "name": v.get("name") or "", "gender": (labels.get("gender") or "").lower(),
                       "age": (labels.get("age") or "").lower().replace(" ", "_"), "accent": labels.get("accent") or "",
                       "description": labels.get("description") or labels.get("descriptive") or v.get("description") or "",
                       "use": labels.get("use_case") or labels.get("use case") or "", "preview": v.get("preview_url") or ""})
    voices = [v for v in voices if v["id"]]
    _voice_cache[key] = (time.time(), voices)
    return voices


def list_voices_for_user(user):
    """
    Return the combined catalog of voices available to `user`:
    - Always includes the 21 built-in OpenRouter ElevenLabs voices (`OPENROUTER_VOICES`).
    - If the user also has a direct ElevenLabs API key configured, appends their account's voices (with preview URLs).
    """
    from mainapp.utils import get_elevenlabs_key
    catalog = [dict(v, source="openrouter") for v in OPENROUTER_VOICES]
    seen_names = {v["name"].lower(): i for i, v in enumerate(catalog)}
    key = get_elevenlabs_key(user)
    if key:
        try:
            direct = list_voices(key)
            for dv in direct:
                low_name = (dv.get("name") or "").strip().lower()
                if low_name in seen_names:
                    idx = seen_names[low_name]
                    if dv.get("preview") and not catalog[idx].get("preview"):
                        catalog[idx]["preview"] = dv["preview"]
                    catalog[idx]["eleven_id"] = dv["id"]
                else:
                    catalog.append(dict(dv, source="elevenlabs"))
        except VoiceError:
            pass
    return catalog


def synthesize_openrouter(user, text, voice_id="sarah", model=None):
    """
    Synthesize MP3 speech using ElevenLabs on OpenRouter (`POST /api/v1/audio/speech`).
    Accepts any of the 21 premade voice names (e.g. 'george', 'sarah') OR a custom 20-char ElevenLabs Voice ID.
    Supports inline audio delivery tags (`[whispering]`, `[laughing]`, `[sighs]`, `[curious]`) on v4, v4-turbo, and v3.
    """
    from mainapp.models import ConnectionProfile
    raw = str(text or "").strip()
    if not raw:
        raise VoiceError("Nothing to read aloud.")
    ai_client.check_limit(user)
    profile = ai_client.main_profile(user)
    if profile is None or profile.provider != ConnectionProfile.PROVIDER_OPENROUTER or not profile.api_key:
        raise VoiceError("OpenRouter voice synthesis needs an active OpenRouter connection key.")
    chosen_model = model if model in OPENROUTER_TTS_MODELS else OPENROUTER_TTS_MODEL_DEFAULT
    v_str = str(voice_id or "sarah").strip() or "sarah"
    # Normalize known premade names to lowercase as OpenRouter's llms.txt specifies
    if v_str.lower() in OPENROUTER_VOICE_NAMES:
        v_str = v_str.lower()
    payload = {
        "model": chosen_model,
        "input": raw[:4500],
        "voice": v_str,
        "response_format": "mp3",
    }
    try:
        resp = requests.post(
            f"{profile.api_url}/audio/speech",
            headers=ai_client._headers(profile),
            json=payload,
            timeout=120,
        )
    except requests.RequestException as e:
        raise VoiceError(f"Could not reach OpenRouter audio endpoint ({type(e).__name__}).")
    if resp.status_code >= 400:
        err_msg = ""
        try:
            err_data = resp.json()
            err_msg = (err_data.get("error") or {}).get("message") or str(err_data)[:200]
        except Exception:
            err_msg = (resp.text or "")[:200]
        raise VoiceError(f"OpenRouter voice synthesis returned {resp.status_code}: {err_msg}")
    if not resp.content:
        raise VoiceError("OpenRouter returned an empty audio stream.")
    return resp.content


def synthesize_single(user, text, voice_id="sarah", model=None):
    """
    Synthesize a single speaker's MP3 audio clip:
    1. If the user has an OpenRouter connection and `voice_id` is one of the 21 premade names (or no direct ElevenLabs key is set),
       uses OpenRouter's `/api/v1/audio/speech` (`elevenlabs/eleven-v4-turbo` by default).
    2. If the user has a direct ElevenLabs API key and `voice_id` is a custom ElevenLabs Voice ID (or OpenRouter fails),
       uses direct ElevenLabs synthesis (`synthesize`).
    """
    from mainapp.models import ConnectionProfile
    from mainapp.utils import get_elevenlabs_key
    raw = str(text or "").strip()
    if not raw:
        raise VoiceError("Nothing to read aloud.")
    v_str = str(voice_id or "sarah").strip() or "sarah"
    el_key = get_elevenlabs_key(user)
    profile = ai_client.main_profile(user)
    has_or = bool(profile and profile.provider == ConnectionProfile.PROVIDER_OPENROUTER and profile.api_key)

    # If the user picked a custom 20-char ElevenLabs ID and has a direct ElevenLabs key, try direct first, else OpenRouter
    is_premade_name = v_str.lower() in OPENROUTER_VOICE_NAMES
    if el_key and not is_premade_name:
        try:
            return synthesize(el_key, [{"text": raw[:2500], "voice_id": v_str}])
        except VoiceError:
            if has_or:
                return synthesize_openrouter(user, raw, voice_id=v_str, model=model)
            raise

    if has_or:
        try:
            return synthesize_openrouter(user, raw, voice_id=v_str, model=model)
        except VoiceError:
            if el_key:
                # Resolve premade name to an ID on their ElevenLabs account if needed
                target_vid = v_str
                if is_premade_name:
                    voices_list = list_voices(el_key)
                    matched = next((v["id"] for v in voices_list if v["name"].lower() == v_str.lower()), None)
                    target_vid = matched or (voices_list[0]["id"] if voices_list else v_str)
                return synthesize(el_key, [{"text": raw[:2500], "voice_id": target_vid}])
            raise

    if el_key:
        target_vid = v_str
        if is_premade_name:
            voices_list = list_voices(el_key)
            matched = next((v["id"] for v in voices_list if v["name"].lower() == v_str.lower()), None)
            target_vid = matched or (voices_list[0]["id"] if voices_list else v_str)
        return synthesize(el_key, [{"text": raw[:2500], "voice_id": target_vid}])

    raise VoiceError("Connect OpenRouter (or add an ElevenLabs API key on Extras) to generate voice notes.")


# ---------------------------------------------------------------------------
# Who says what
# ---------------------------------------------------------------------------

def clean(text):
    """The reply as it should be read: no story-extra markers, HTML, markdown marks or [OOC] notes."""
    from mainapp import extras
    text = extras.strip_markers(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\(\(?\s*OOC:.*?\)\)?", " ", text, flags=re.I | re.S)
    text = re.sub(r"[*_#`~]+", "", text)
    return text


def segments(text):
    """[{"kind": "narration"|"speech", "text"}] in order; speech without its quote marks."""
    text, out, pos = clean(text), [], 0
    for m in QUOTE.finditer(text):
        before = text[pos:m.start()].strip()
        if re.search(r"\w", before):
            out.append({"kind": "narration", "text": " ".join(before.split())})
        spoken = m.group(0)[1:-1].strip()
        if re.search(r"\w", spoken):
            out.append({"kind": "speech", "text": " ".join(spoken.split())})
        pos = m.end()
    rest = text[pos:].strip()
    if re.search(r"\w", rest):
        out.append({"kind": "narration", "text": " ".join(rest.split())})
    return out


ATTRIBUTE_PROMPT = """You prepare a roleplay reply to be read aloud by several voices. Below are its parts in order:
narration (N) and quoted speech (S). For every S part, say who speaks it, using the name the story uses.
The main character is {char}; the user's character is {user}. If a line is spoken by an unnamed person,
give a short label ("guard", "old woman"). Add a delivery cue only when the narration right around it
says how it is said (whispered, laughed, coldly...), choosing from: {cues}. For each speaker other than
{char} and {user}, guess gender (male, female or unknown) and age (young, middle_aged or old).
Known speakers so far: {known}.

Answer with JSON only:
{{"lines": {{"<number of each S part>": {{"speaker": "Name", "cue": "whispers or empty"}}}},
  "people": {{"Name": {{"gender": "...", "age": "..."}}}}}}

Parts:
{parts}"""


def attribute(user, segs, char_name, user_name, known):
    """Speakers and cues for the speech parts: ({index: {"speaker", "cue"}}, {name: {"gender", "age"}})."""
    if not any(s["kind"] == "speech" for s in segs):
        return {}, {}
    parts = "\n".join(f"{i} {'S' if s['kind'] == 'speech' else 'N'}: {s['text'][:600]}" for i, s in enumerate(segs))
    prompt = ATTRIBUTE_PROMPT.format(char=char_name, user=user_name, cues=", ".join(CUES),
                                     known=", ".join(known) or "none", parts=parts)
    try:
        text = ai_client.complete(user, "voice_split", [{"role": "user", "content": prompt}], max_tokens=1500,
                                  temperature=0)
        data = json.loads(re.search(r"\{.*\}", text or "", re.S).group(0))
    except (ai_client.AIError, AttributeError, ValueError) as e:
        log.info("Speaker attribution failed, all speech goes to %s: %s", char_name, e)
        return {}, {}
    lines = {}
    for k, v in (data.get("lines") or {}).items():
        if str(k).isdigit() and isinstance(v, dict) and str(v.get("speaker") or "").strip():
            cue = str(v.get("cue") or "").strip().strip("[]").lower()
            lines[int(k)] = {"speaker": str(v["speaker"]).strip()[:60], "cue": cue if cue in CUES else ""}
    people = {str(n).strip()[:60]: p for n, p in (data.get("people") or {}).items() if isinstance(p, dict)}
    return lines, people


# ---------------------------------------------------------------------------
# Voices for speakers
# ---------------------------------------------------------------------------

def _same(a, b):
    a, b = a.lower().strip(), b.lower().strip()
    return a == b or a.split()[0] == b.split()[0] if a and b else False


def pick(voices, taken, gender="", age="", prefer_use=""):
    """A voice from the user's list that fits and isn't used yet in this chat (or any, if all are)."""
    def score(v):
        return (4 * bool(gender in ("male", "female") and v["gender"] == gender) + 2 * bool(age and v["age"] == age)
                + 3 * bool(prefer_use and prefer_use in (v["use"] + v["description"]).lower()))
    free = [v for v in voices if v["id"] not in taken] or voices
    return max(free, key=score)["id"] if free else None


def assign(character, chat_voices, voices, speakers, people):
    """Voice id for each speaker name (and the narrator). Updates chat_voices with new picks."""
    cast = {str(k): str(v) for k, v in (character.voice_cast or {}).items() if v} if hasattr(character, "voice_cast") else {}
    taken = {v for v in chat_voices.values()} | set(cast.values()) | {character.eleven_voice_char_id,
                                                                     character.eleven_voice_narr_id}
    out = {}
    narrator = character.eleven_voice_narr_id or chat_voices.get(NARRATOR)
    if not narrator:
        narrator = chat_voices[NARRATOR] = pick(voices, taken, prefer_use="narrat")
        taken.add(narrator)
    out[NARRATOR] = narrator
    for name in speakers:
        if _same(name, character.name):
            vid = character.eleven_voice_char_id or chat_voices.get(character.name.lower())
            if not vid:
                vid = chat_voices[character.name.lower()] = pick(voices, taken)
        else:
            vid = next((v for n, v in cast.items() if _same(name, n)), None) or chat_voices.get(name.lower())
            if not vid:
                hint = people.get(name) or {}
                vid = chat_voices[name.lower()] = pick(voices, taken, str(hint.get("gender") or "").lower(),
                                                       str(hint.get("age") or "").lower())
        taken.add(vid)
        out[name] = vid
    return out


def script(segs, lines, voice_of, char_name):
    """[{"text", "voice_id"}] in order, with cues as v3 audio tags; neighbours with the same voice merged."""
    inputs = []
    for i, s in enumerate(segs):
        if s["kind"] == "narration":
            vid, text = voice_of[NARRATOR], s["text"]
        else:
            line = lines.get(i) or {"speaker": char_name, "cue": ""}
            vid = voice_of.get(line["speaker"]) or voice_of.get(char_name) or voice_of[NARRATOR]
            text = (f"[{line['cue']}] " if line["cue"] else "") + s["text"]
        if not vid:
            continue
        if inputs and inputs[-1]["voice_id"] == vid:
            inputs[-1]["text"] += " " + text
        else:
            inputs.append({"text": text, "voice_id": vid})
    return inputs


# ---------------------------------------------------------------------------
# ElevenLabs
# ---------------------------------------------------------------------------

def _chunks(inputs):
    """Split the script into requests under the size limit (a long line is cut at sentence ends)."""
    pieces = []
    for item in inputs:
        text = item["text"]
        while len(text) > REQUEST_LIMIT:
            cut = max(text.rfind(". ", 0, REQUEST_LIMIT), text.rfind("! ", 0, REQUEST_LIMIT),
                      text.rfind("? ", 0, REQUEST_LIMIT))
            cut = cut + 1 if cut > 0 else REQUEST_LIMIT
            pieces.append({"text": text[:cut].strip(), "voice_id": item["voice_id"]})
            text = text[cut:].strip()
        if text:
            pieces.append({"text": text, "voice_id": item["voice_id"]})
    batches, size = [[]], 0
    for p in pieces:
        if batches[-1] and size + len(p["text"]) > REQUEST_LIMIT:
            batches.append([])
            size = 0
        batches[-1].append(p)
        size += len(p["text"])
    return [b for b in batches if b]


def _post(url, key, body):
    try:
        resp = requests.post(url, headers={"xi-api-key": key, "Content-Type": "application/json",
                                           "Accept": "audio/mpeg"}, json=body, timeout=180)
    except requests.RequestException as e:
        raise VoiceError(f"Couldn't reach ElevenLabs ({type(e).__name__}).")
    if resp.status_code == 401:
        raise VoiceError("ElevenLabs didn't accept the key. Check it on the Extras page.")
    if resp.status_code == 402 or "quota" in resp.text[:300].lower():
        raise VoiceError("Your ElevenLabs credits for this month are used up.")
    return resp


def _join(parts):
    """One mp3 from several (pydub when ffmpeg is there; plain mp3 frames joined otherwise)."""
    if len(parts) == 1:
        return parts[0]
    try:
        from pydub import AudioSegment
        out = AudioSegment.silent(duration=0)
        for p in parts:
            out += AudioSegment.from_file(io.BytesIO(p), format="mp3") + AudioSegment.silent(duration=250)
        buf = io.BytesIO()
        out.export(buf, format="mp3")
        return buf.getvalue()
    except Exception:  # no ffmpeg: mp3 frames can simply follow each other
        return b"".join(parts)


def synthesize(key, inputs):
    """mp3 bytes for the script. Text to Dialogue first; one request per line if it's refused."""
    audio = []
    for batch in _chunks(inputs):
        resp = _post(f"{API}/text-to-dialogue?output_format=mp3_44100_128", key,
                     {"inputs": batch, "model_id": DIALOGUE_MODEL})
        if resp.ok:
            audio.append(resp.content)
            continue
        log.info("Text to Dialogue refused (%s); reading line by line", resp.status_code)
        for item in batch:
            text = re.sub(r"\[[a-z_ ]+\]\s*", "", item["text"])  # audio tags are v3 only
            single = _post(f"{API}/text-to-speech/{item['voice_id']}?output_format=mp3_44100_128", key,
                           {"text": text, "model_id": SINGLE_MODEL})
            if not single.ok:
                raise VoiceError(f"ElevenLabs answered {single.status_code}: {single.text[:160]}")
            audio.append(single.content)
    if not audio:
        raise VoiceError("Nothing to read aloud in this reply.")
    return _join(audio)


def voice_reply(user, character, text, chat_voices, user_name, key):
    """(mp3 bytes, the speakers and their voice names) for one reply. chat_voices is updated in place."""
    segs = segments(text)
    if not segs:
        raise VoiceError("Nothing to read aloud in this reply.")
    voices = list_voices(key)
    if not voices:
        raise VoiceError("Your ElevenLabs account has no voices yet.")
    known = [character.name] + list((getattr(character, "voice_cast", None) or {}).keys()) + \
        [n for n in chat_voices if n != NARRATOR]
    lines, people = attribute(user, segs, character.name, user_name, known)
    speakers = []
    for i, s in enumerate(segs):
        if s["kind"] == "speech":
            name = (lines.get(i) or {}).get("speaker") or character.name
            if name not in speakers:
                speakers.append(name)
    voice_of = assign(character, chat_voices, voices, speakers, people)
    inputs = script(segs, lines, voice_of, character.name)
    names = {v["id"]: v["name"] for v in voices}
    cast = {("Narrator" if k == NARRATOR else k): names.get(v, v) for k, v in voice_of.items()}
    return synthesize(key, inputs), cast
