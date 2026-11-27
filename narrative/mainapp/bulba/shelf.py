"""
📚 Bulba and the rest of their presets: not just the active one.

- list_presets / read_preset: every preset they have saved (and the ones they sent Bulba as a file), its outline or one
  block's text, so Bulba can compare, switch or mix.
- propose_preset_switch: another saved preset becomes the active one (Apply; Undo switches back).
- Mixing goes through propose_preset_edit with from_preset + from_block (doctor.py): that block's text, word for word,
  into the active preset (a new block, or replacing the one with the same name).
- A preset sent as a file in Bulba's 📎 (our export or SillyTavern .json; a .docx, .txt or .md of written-out
  instructions) is saved but NOT switched on, so it can be looked at, mixed from, or switched to (from_file).
  A written-out one keeps the app's slots (card, chat history...) from their current preset, its own text blocks off,
  with the file's sections as the new blocks: usable if they switch, easy to mix from.
"""
import copy
import io
import json
import re
import zipfile
from xml.etree import ElementTree

from mainapp import presets

MAX_BLOCK = 8000
FILE_KINDS = (".json", ".docx", ".txt", ".md")


def _find(user, name):
    from mainapp.models import Preset
    name = str(name or "").strip()
    mine = Preset.objects.filter(user=user)
    return mine.filter(name=name).first() or mine.filter(name__iexact=name).first() or \
        next((p for p in mine if name.lower() in p.name.lower()), None) if name else None


def tool_list_presets(session, args):
    from mainapp.models import Preset
    from mainapp.bulba.doctor import _preset_outline
    rows = []
    for p in Preset.objects.filter(user=session.user).order_by("-is_active", "name"):
        data = presets.normalize(p.data)
        prompts = [b for b in data["blocks"] if b["kind"] == "prompt"]
        rows.append({"name": p.name, "active": p.is_active, "blocks": len(prompts),
                     "on": sum(1 for b in prompts if b["enabled"]),
                     "words": sum(len(b["content"].split()) for b in prompts if b["enabled"]),
                     "from_a_file": bool((data.get("extras") or {}).get("from_file"))})
    return {"presets": rows, "how": "read_preset for one's outline or a block; propose_preset_switch to make one "
            "active; propose_preset_edit with from_preset + from_block to mix a block into the active one"}, []


def tool_read_preset(session, args):
    from mainapp.bulba.doctor import _preset_outline
    obj = _find(session.user, args.get("preset"))
    if obj is None:
        return {"error": "No such preset; list_presets shows their names."}, []
    data = presets.normalize(obj.data)
    name = str(args.get("block") or "").strip()
    if not name:
        return {"preset": obj.name, "active": obj.is_active, "outline": _preset_outline(data),
                "samplers": {k: v for k, v in (data.get("samplers") or {}).items() if v not in (None, "")}}, []
    if name in presets.UTILITY_LABELS:
        return {"preset": obj.name, "utility": name, "content": data["utility"].get(name, "")}, []
    block = next((b for b in data["blocks"] if b["name"] == name), None) or \
        next((b for b in data["blocks"] if b["name"].lower() == name.lower()), None)
    if block is None:
        return {"error": f"No block called “{name}” in {obj.name}; read_preset without a block shows the outline."}, []
    return {"preset": obj.name, "block": block["name"], "on": block["enabled"], "kind": block["kind"],
            "content": block["content"][:MAX_BLOCK] if block["kind"] == "prompt" else "(a slot filled by the app)"}, []


def block_from(user, preset_name, block_name):
    """(block name, its text) from another of their presets, for mixing. Raises ValueError."""
    obj = _find(user, preset_name)
    if obj is None:
        raise ValueError(f"No preset “{preset_name}”; list_presets shows their names.")
    data = presets.normalize(obj.data)
    block = next((b for b in data["blocks"] if b["name"].lower() == str(block_name or "").strip().lower()
                  and b["kind"] == "prompt"), None)
    if block is None:
        raise ValueError(f"No text block “{block_name}” in {obj.name}.")
    return block["name"], block["content"]


def tool_propose_preset_switch(session, args):
    from mainapp.bulba.agent import _proposal
    obj = _find(session.user, args.get("preset"))
    if obj is None:
        return {"error": "No such preset; list_presets shows their names."}, []
    if obj.is_active:
        return {"result": f"“{obj.name}” is already the active preset."}, []
    data = presets.normalize(obj.data)
    on = [b["name"] for b in data["blocks"] if b["kind"] == "prompt" and b["enabled"]]
    summary = [f"Switch to “{obj.name}” for every chat.", "Its blocks that are on: " + (", ".join(on[:12]) or "none"),
               "Your current preset stays saved; Undo switches back."]
    if str(args.get("why") or "").strip():
        summary.insert(1, str(args["why"]).strip())
    p = _proposal(session, "preset_switch", f"Switch to preset: {obj.name}", summary,
                  {"preset_id": obj.id, "name": obj.name})
    return {"proposal": p["id"], "status": "waiting for Apply"}, [{"type": "proposal", "id": p["id"]}]


def apply_switch(session, p):
    from mainapp.models import Preset
    obj = Preset.objects.filter(user=session.user, id=p["payload"]["preset_id"]).first()
    if obj is None:
        raise ValueError("That preset was deleted since.")
    p["undo"] = {"previous": presets.get_active(session.user).id}
    presets.activate(obj)
    return f"“{obj.name}” is your active preset now."


def undo_switch(session, p):
    from mainapp.models import Preset
    prev = Preset.objects.filter(user=session.user, id=(p.get("undo") or {}).get("previous")).first()
    if prev:
        presets.activate(prev)


# --- A preset sent as a file ---

def _docx_sections(raw):
    """[(heading, text)] from a .docx: a Heading-styled paragraph starts a section."""
    w = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        root = ElementTree.fromstring(z.read("word/document.xml"))
    sections, head, lines = [], "", []
    for para in root.iter(w + "p"):
        style = para.find(f"{w}pPr/{w}pStyle")
        text = "".join(t.text or "" for t in para.iter(w + "t")).strip()
        is_head = style is not None and re.match(r"(?i)heading|title|заголов", style.get(w + "val") or "")
        if is_head and text:
            if lines or head:
                sections.append((head, "\n".join(lines).strip()))
            head, lines = text, []
        else:
            lines.append(text)
    sections.append((head, "\n".join(lines).strip()))
    return [(h, t) for h, t in sections if t]


def _text_sections(text):
    """[(heading, text)] from plain text or Markdown: '# Heading' lines (or a short line in [brackets]) start one."""
    sections, head, lines = [], "", []
    for line in text.splitlines():
        m = re.match(r"^\s*(?:#{1,4}\s+(.+?)|\[([^\]\n]{2,60})\])\s*$", line)
        if m:
            if lines or head:
                sections.append((head, "\n".join(lines).strip()))
            head, lines = (m.group(1) or m.group(2)).strip(), []
        else:
            lines.append(line.rstrip())
    sections.append((head, "\n".join(lines).strip()))
    return [(h, t) for h, t in sections if t]


def from_file(user, filename, raw):
    """(preset data, suggested name) from a sent file. Raises ValueError."""
    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    base = filename.rsplit(".", 1)[0] or "Preset from a file"
    if ext == ".json":
        try:
            preset, suggested = presets.from_any(json.loads(raw.decode("utf-8-sig")))
        except (ValueError, TypeError, AttributeError, UnicodeDecodeError) as e:
            raise ValueError(f"That .json isn't a preset this app can read: {e}")
        return preset, suggested or base
    if ext == ".docx":
        try:
            sections = _docx_sections(raw)
        except (zipfile.BadZipFile, KeyError, ElementTree.ParseError):
            raise ValueError("That .docx couldn't be opened.")
    elif ext in (".txt", ".md"):
        sections = _text_sections(raw.decode("utf-8-sig", errors="replace"))
    else:
        raise ValueError("A preset can come as .json (this app or SillyTavern), .docx, .txt or .md.")
    if not sections:
        raise ValueError("There's no text in that file.")
    # The app's slots (card, persona, chat history...) from their current preset; its own text blocks off
    data = copy.deepcopy(presets.normalize(presets.get_active(user).data))
    for b in data["blocks"]:
        if b["kind"] == "prompt":
            b["enabled"] = False
    at = next((i for i, b in enumerate(data["blocks"]) if b["kind"] == "marker"), 0)
    taken = {b["name"] for b in data["blocks"]}
    new = []
    for i, (head, text) in enumerate(sections, 1):
        name = (head or (base if len(sections) == 1 else f"{base} {i}"))[:60]
        while name in taken:
            name += " (file)"
        taken.add(name)
        new.append({"name": name, "kind": "prompt", "role": "system", "content": text[:20000], "enabled": True})
    data["blocks"][at:at] = new
    data["extras"] = {**(data.get("extras") or {}), "from_file": filename[:120]}
    return presets.normalize(data), base


def save_file(user, filename, raw):
    """The sent preset, saved and not switched on. Returns the Preset."""
    from mainapp.models import Preset
    from mainapp import mature
    data, name = from_file(user, filename, raw)
    data = presets.normalize(data)
    data["extras"] = {**(data.get("extras") or {}), "from_file": filename[:120]}
    return Preset.objects.create(user=user, data=mature.keep(user, data), name=presets.unique_name(user, name),
                                 is_active=False)


STR = {"type": "string"}


def tool_defs(fn):
    return [
        fn("list_presets", "All their saved presets (the active one first), including ones they sent you as a file.", {}),
        fn("read_preset", "Another preset's outline (no block), or one block's full text: to compare, before "
           "switching, or to find what to mix in.", {"preset": STR, "block": STR}, ["preset"]),
        fn("propose_preset_switch", "Make another of their saved presets the active one (Apply; Undo switches back).",
           {"preset": STR, "why": STR}, ["preset"]),
    ]


HANDLERS = {"list_presets": tool_list_presets, "read_preset": tool_read_preset,
            "propose_preset_switch": tool_propose_preset_switch}
KINDS = ("preset_switch",)
