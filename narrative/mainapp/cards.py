"""
Character cards: import and export in the SillyTavern formats.

Reads Character Card V1 (flat JSON), V2 ("chara_card_v2") and V3 ("chara_card_v3"), either as
JSON or embedded in a PNG (tEXt chunk "ccv3" preferred, then "chara", base64 JSON). Exports
V3 JSON, and PNG with both chunks so older tools can still read it.

Field mapping (card -> Character):
    name, description, scenario, creator_notes  -> same names
    personality                                 -> personality (sent as "Character personality")
    first_mes                                   -> initial_message
    mes_example                                 -> example_dialogue (sent as "Example chats")
    alternate_greetings                         -> alternate_greetings (extra swipes on the greeting)
    system_prompt, post_history_instructions    -> same names (see presets.assemble)
    creator, character_version                  -> card_creator, card_version
    character_book                              -> a new Worldbook attached to the character
    tags                                        -> tags
    everything else (extensions, assets, ...)   -> card_data, kept for export
"""
import base64
import io
import json
import re
import struct
import zlib

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
KNOWN = {"name", "description", "personality", "scenario", "first_mes", "mes_example",
         "alternate_greetings", "system_prompt", "post_history_instructions", "creator_notes",
         "creator", "character_version", "character_book", "tags"}
MAX_TEXT = 200_000  # per field; a card bigger than this is almost certainly broken


class CardError(ValueError):
    pass


# ---------------------------------------------------------------------------
# PNG chunks
# ---------------------------------------------------------------------------

def _chunks(data):
    if not data.startswith(PNG_SIGNATURE):
        raise CardError("This isn't a PNG file.")
    pos = len(PNG_SIGNATURE)
    while pos + 8 <= len(data):
        length, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + length]
        yield kind, body, pos, pos + 12 + length
        pos += 12 + length
        if kind == b"IEND":
            return


def png_text(data):
    """{keyword: text} for the tEXt/zTXt/iTXt chunks of a PNG."""
    out = {}
    for kind, body, _, _ in _chunks(data):
        try:
            if kind == b"tEXt":
                key, _, text = body.partition(b"\x00")
                out[key.decode("latin-1")] = text.decode("latin-1")
            elif kind == b"zTXt":
                key, _, rest = body.partition(b"\x00")
                out[key.decode("latin-1")] = zlib.decompress(rest[1:]).decode("latin-1")
            elif kind == b"iTXt":
                key, _, rest = body.partition(b"\x00")
                compressed = rest[0] == 1
                rest = rest[2:]
                _, _, rest = rest.partition(b"\x00")  # language tag
                _, _, text = rest.partition(b"\x00")  # translated keyword
                out[key.decode("latin-1")] = (zlib.decompress(text) if compressed else text).decode("utf-8")
        except (ValueError, IndexError, zlib.error, UnicodeDecodeError):
            continue
    return out


def _chunk(kind, body):
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)


def embed_png(png, chunks):
    """Copy of `png` with tEXt chunks {keyword: text}, replacing any with the same keyword."""
    keys = {k.lower() for k in chunks}
    out = [PNG_SIGNATURE]
    for kind, body, start, end in _chunks(png):
        if kind == b"tEXt" and body.partition(b"\x00")[0].decode("latin-1").lower() in keys:
            continue
        if kind == b"IEND":
            for key, text in chunks.items():
                out.append(_chunk(b"tEXt", key.encode("latin-1") + b"\x00" + text.encode("latin-1")))
        out.append(png[start:end])
    return b"".join(out)


def _decode_b64_json(text):
    try:
        return json.loads(base64.b64decode(text).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        try:  # some tools store plain JSON
            return json.loads(text)
        except ValueError:
            return None


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def read(raw, filename=""):
    """
    Bytes of a .json or .png card -> (card, image_bytes or None).
    `card` is the normalized dict described in normalize().
    """
    if raw.startswith(PNG_SIGNATURE):
        texts = {k.lower(): v for k, v in png_text(raw).items()}
        data = None
        for key in ("ccv3", "chara"):
            if key in texts:
                data = _decode_b64_json(texts[key])
                if data:
                    break
        if not data:
            raise CardError("This picture has no character card inside it. Images that went through a chat "
                            "app or an image editor often lose it: try the original .png or a .json export.")
        return normalize(data), raw
    if raw[:4] == b"RIFF" or raw[:3] == b"\xff\xd8\xff":
        raise CardError("This is a WEBP/JPEG picture. Character cards are .png or .json files; "
                        "a converted picture loses the card data.")
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError):
        raise CardError("Couldn't read this file as a character card (.png or .json).")
    return normalize(data), None


def _text(value):
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    return value.replace("\r\n", "\n")[:MAX_TEXT]


def normalize(data):
    """Any card version -> {"name", "description", ..., "character_book", "tags", "extra", "spec"}."""
    if not isinstance(data, dict):
        raise CardError("This file isn't a character card.")
    spec = data.get("spec") or "chara_card_v1"
    body = data.get("data") if isinstance(data.get("data"), dict) else data
    if not any(k in body for k in ("name", "description", "first_mes", "char_name")):
        raise CardError("This file doesn't look like a character card (no name, description or greeting).")

    card = {
        "spec": spec,
        "name": _text(body.get("name") or body.get("char_name")).strip()[:255] or "Unnamed",
        "description": _text(body.get("description") or body.get("char_persona")),
        "personality": _text(body.get("personality")),
        "scenario": _text(body.get("scenario") or body.get("world_scenario")),
        "first_mes": _text(body.get("first_mes") or body.get("char_greeting")),
        "mes_example": _text(body.get("mes_example") or body.get("example_dialogue")),
        "system_prompt": _text(body.get("system_prompt")),
        "post_history_instructions": _text(body.get("post_history_instructions")),
        "creator_notes": _text(body.get("creator_notes") or data.get("creatorcomment")),
        "creator": _text(body.get("creator")).strip()[:255],
        "character_version": _text(body.get("character_version")).strip()[:64],
    }
    greetings = body.get("alternate_greetings") or []
    card["alternate_greetings"] = [_text(g) for g in greetings if isinstance(g, str) and g.strip()][:50]
    tags = body.get("tags") or data.get("tags") or []
    card["tags"] = [t.strip()[:100] for t in tags if isinstance(t, str) and t.strip()][:30]
    book = body.get("character_book")
    card["character_book"] = book if isinstance(book, dict) and book.get("entries") else None
    card["extra"] = {k: v for k, v in body.items() if k not in KNOWN
                     and k not in ("char_name", "char_persona", "world_scenario", "char_greeting", "example_dialogue")}
    return card


# ---------------------------------------------------------------------------
# Creating a character
# ---------------------------------------------------------------------------

def _unique_slug(model, base):
    slug, n = base, 2
    while model.objects.filter(slug=slug).exists():
        slug, n = f"{base}-{n}", n + 1
    return slug


def create_character(user, card, image=None, slug_base=None):
    """Save a normalized card as a new Character of `user` (with its worldbook and picture)."""
    from django.core.files.base import ContentFile
    from django.utils.text import slugify

    from mainapp.lorebook import normalize_book, save_worldbook
    from mainapp.models import Character, TagPost, Worldbook

    character = Character(
        author=user, name=card["name"], description=card["description"], personality=card["personality"],
        scenario=card["scenario"], initial_message=card["first_mes"], example_dialogue=card["mes_example"],
        alternate_greetings=card["alternate_greetings"], system_prompt=card["system_prompt"],
        post_history_instructions=card["post_history_instructions"], creator_notes=card["creator_notes"],
        card_creator=card["creator"], card_version=card["character_version"], card_data=card["extra"],
    )
    character.slug = _unique_slug(Character, slug_base or f"{user.username}-{slugify(card['name']) or 'character'}")

    if card["character_book"]:
        book = normalize_book({"spec": "chara_card_v2", "data": {"name": card["name"],
                                                                 "character_book": card["character_book"]}})
        if book["entries"]:
            title = book["title"] or f"{card['name']}'s lore"
            book["title"] = title
            wb = Worldbook(title=title, slug=_unique_slug(Worldbook, slugify(title) or "worldbook"),
                           description=book["description"], author=user)
            save_worldbook(wb, book)
            character.worldbook = wb

    if image:
        character.photo_neutral.save(f"{slugify(card['name']) or 'card'}.png", ContentFile(image), save=False)
    character.save()

    for name in card["tags"]:
        tag_slug = slugify(name)[:255]
        if not tag_slug:
            continue
        tag, _ = TagPost.objects.get_or_create(slug=tag_slug, defaults={"tag": name})
        character.tags.add(tag)
    return character


def import_file(user, raw, filename=""):
    card, image = read(raw, filename)
    return create_character(user, card, image)


# ---------------------------------------------------------------------------
# Exporting
# ---------------------------------------------------------------------------

def to_card(character):
    """Character -> Character Card V3 dict."""
    from mainapp.lorebook import load_worldbook

    data = dict(character.card_data or {})
    data.update({
        "name": character.name,
        "description": character.description,
        "personality": character.personality,
        "scenario": character.scenario,
        "first_mes": character.initial_message,
        "mes_example": character.example_dialogue,
        "alternate_greetings": list(character.alternate_greetings or []),
        "system_prompt": character.system_prompt,
        "post_history_instructions": character.post_history_instructions,
        "creator_notes": character.creator_notes,
        "creator": character.card_creator,
        "character_version": character.card_version,
        "tags": [t.tag for t in character.tags.all()],
    })
    data.setdefault("extensions", {})
    data.setdefault("group_only_greetings", [])
    if character.worldbook_id:
        data["character_book"] = to_character_book(load_worldbook(character.worldbook))
    else:
        data.pop("character_book", None)
    return {"spec": "chara_card_v3", "spec_version": "3.0", "data": data}


def to_character_book(book):
    entries = []
    for i, e in enumerate(book.get("entries", [])):
        entries.append({
            "id": e["uid"], "keys": e["keys"], "secondary_keys": e["secondary_keys"],
            "comment": e["comment"], "content": e["content"], "constant": e["constant"],
            "selective": bool(e["secondary_keys"]), "insertion_order": e["order"],
            "enabled": e["enabled"], "case_sensitive": e["case_sensitive"],
            "use_regex": False, "extensions": {},
        })
    return {"name": book.get("title", ""), "description": book.get("description", ""),
            "scan_depth": book.get("settings", {}).get("scan_depth"),
            "token_budget": book.get("settings", {}).get("token_budget"),
            "recursive_scanning": book.get("settings", {}).get("recursive_scan", False),
            "extensions": {}, "entries": entries}


def _as_png(image_bytes):
    from PIL import Image

    out = io.BytesIO()
    if image_bytes:
        try:
            img = Image.open(io.BytesIO(image_bytes))
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGBA")
            img.save(out, "PNG")
            return out.getvalue()
        except (OSError, ValueError):
            pass
    Image.new("RGB", (400, 600), (58, 52, 70)).save(out, "PNG")
    return out.getvalue()


def to_png(character):
    """PNG bytes: the neutral picture (or a plain one) with the card in "ccv3" and "chara"."""
    image = None
    if character.photo_neutral:
        try:
            with character.photo_neutral.open("rb") as f:
                image = f.read()
        except OSError:
            image = None
    png = image if image and image.startswith(PNG_SIGNATURE) else _as_png(image)
    v3 = to_card(character)
    v2 = {"spec": "chara_card_v2", "spec_version": "2.0", "data": {**v3["data"]}}
    v2["data"].pop("group_only_greetings", None)
    enc = lambda d: base64.b64encode(json.dumps(d, ensure_ascii=False).encode("utf-8")).decode("ascii")
    return embed_png(png, {"chara": enc(v2), "ccv3": enc(v3)})


# ---------------------------------------------------------------------------
# Prompt helpers
# ---------------------------------------------------------------------------

_NAME_MACROS = re.compile(r"\{\{\s*(char|user)\s*\}\}|<(BOT|USER)>", re.IGNORECASE)


def user_name(user):
    if user is None:
        return "You"
    return getattr(user, "persona_name", None) or getattr(user, "name", None) or user.username


def fill_names(text, char_name, user_name_):
    """{{char}}/{{user}} (and the old <BOT>/<USER>) -> names, for text shown on screen or saved."""
    def repl(m):
        which = (m.group(1) or m.group(2)).lower()
        return char_name if which in ("char", "bot") else user_name_
    return _NAME_MACROS.sub(repl, text or "")

def format_examples(text):
    """mes_example with <START> separators -> the "Example chats" text sent to the model."""
    text = (text or "").strip()
    if not text:
        return ""
    blocks = [b.strip() for b in text.replace("<start>", "<START>").split("<START>")]
    blocks = [b for b in blocks if b]
    return "\n\n".join("[Example chat]\n" + b for b in blocks)
