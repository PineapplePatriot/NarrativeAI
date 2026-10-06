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
