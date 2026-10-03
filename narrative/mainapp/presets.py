"""
Presets: the ordered list of prompt blocks that becomes the request for the
main chat, plus samplers and a few utility prompts. Modelled on SillyTavern
chat-completion presets, and importable from / exportable to them.

A preset (stored in Preset.data) looks like:
{
  "blocks":   [block, ...]        # in prompt order
  "samplers": {...}               # see mainapp/samplers.py
  "utility":  {...}               # continue nudge, impersonation, prefill...
  "options":  {"post_processing": "none" | "merge" | "strict" | "single_user"}
  "extras":   {...}               # SillyTavern fields we keep for export (regex scripts...)
}

A block is a prompt (text the user wrote), a marker (a slot the app fills:
chat history, character description, lore, summary...) or a header (only
groups the list in the editor). Blocks are placed "relative" (where they are
in the list) or "in_chat" (inside the chat history, `depth` messages from the
end).

Macros ({{char}}, {{user}}, {{random: a, b}}, {{setvar::x::y}} ...) are
expanded on every request. Variables are recomputed each time: all setvars
from enabled blocks run first, so a {{getvar}} works wherever it is placed,
and switching a block off removes its variables straight away.
"""
import copy
import random as _random
import re
import uuid
from datetime import datetime

from mainapp import samplers as sampler_mod

FORMAT = "narrativeai-preset"
ROLES = ("system", "user", "assistant")
POST_PROCESSING = {
    "none": "As is",
    "merge": "Merge consecutive messages with the same role",
    "strict": "Strict: one system message first, then alternating user/assistant",
    "single_user": "Single user message: send everything as one big user message",
}

MARKERS = {
    "chat_history": "Chat history",
    "char_description": "Character description",
    "char_personality": "Character personality",
    "scenario": "Scenario",
    "persona": "Persona (you)",
    "lore_before": "Lore (before)",
    "lore_after": "Lore (after)",
    "examples": "Example chats",
    "summary": "Story summary",
    "trackers": "Story trackers",
    "world_context": "World state (manual notes)",
    "director_note": "Director's note",
}
ST_MARKERS = {
    "chatHistory": "chat_history", "charDescription": "char_description", "charPersonality": "char_personality",
    "scenario": "scenario", "personaDescription": "persona", "worldInfoBefore": "lore_before",
    "worldInfoAfter": "lore_after", "dialogueExamples": "examples",
}
ST_MARKERS_REVERSE = {v: k for k, v in ST_MARKERS.items()}

UTILITY_DEFAULTS = {
    "continue_nudge": "[Continue your last message without repeating its original content.]",
    "impersonation": "[Write your next reply from the point of view of {{user}}, using the chat history so far "
                     "as a guideline for the writing style of {{user}}. Don't write as {{char}} or system.]",
    "new_chat": "[Start a new chat]",
    "assistant_prefill": "",
    "assistant_impersonation": "",
}

UTILITY_LABELS = {
    "continue_nudge": ("Continue nudge", "Sent when you press Continue."),
    "impersonation": ("Impersonation", "Used when the AI writes your next message for you."),
    "new_chat": ("New chat", "Placed before the chat in strict mode, when the chat would otherwise start with the character."),
    "assistant_prefill": ("Assistant prefill", "Starts the AI's reply for it. Skipped on models that reject prefill (newest Claude)."),
    "assistant_impersonation": ("Impersonation prefill", "Starts the impersonated message."),
}

MACRO_HELP = [
    ("{{char}} / {{user}}", "Character name / your persona name"),
    ("{{description}} {{scenario}} {{personality}} {{persona}}", "Character and persona fields"),
    ("{{summary}}", "The story summary"),
    ("{{lastChatMessage}} {{lastUserMessage}} {{lastCharMessage}}", "Recent messages"),
    ("{{random: a, b, c}}  or  {{random::a::b}}", "A random pick, new every request"),
    ("{{roll: 2d6+1}}", "Dice roll"),
    ("{{setvar::name::text}} / {{getvar::name}}", "Store text in a variable / insert it anywhere"),
    ("{{#if .name}} … {{else}} … {{/if}}", "Only if the variable is set (use ! to negate)"),
    ("{{// note}}", "A comment, never sent"),
    ("{{trim}}", "Removes the blank lines around it"),
    ("{{time}} {{date}} {{weekday}}", "Current time and date"),
]

# Models that reject a final assistant message ("prefill") with an error
PREFILL_REJECTING_MODELS = re.compile(
    r"claude-(?:opus-(?:4[.-][678]|5)|sonnet-(?:4[.-]6|5)|fable|mythos)", re.I)


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

def _int(value, default, lo=None, hi=None):
    try:
        n = int(float(value))
    except (TypeError, ValueError):
        n = default
    if lo is not None:
        n = max(lo, n)
    if hi is not None:
        n = min(hi, n)
    return n


def normalize_block(raw):
    if not isinstance(raw, dict):
        return None
    kind = raw.get("kind") if raw.get("kind") in ("prompt", "marker", "header") else "prompt"
    marker = raw.get("marker") if raw.get("marker") in MARKERS else None
    if kind == "marker" and not marker:
        kind = "prompt"
    return {
        "id": str(raw.get("id") or uuid.uuid4().hex)[:64],
        "name": str(raw.get("name") or (MARKERS.get(marker) if marker else "Untitled"))[:200],
        "kind": kind,
        "marker": marker if kind == "marker" else None,
        "role": raw.get("role") if raw.get("role") in ROLES else "system",
        "content": str(raw.get("content") or "") if kind == "prompt" else "",
        "enabled": bool(raw.get("enabled", True)),
        "position": "in_chat" if raw.get("position") == "in_chat" else "relative",
        "depth": _int(raw.get("depth"), 0, 0, 1000),
        "order": _int(raw.get("order"), 100, -10000, 10000),
    }


def normalize(raw):
    raw = raw if isinstance(raw, dict) else {}
    blocks, seen = [], set()
    for b in raw.get("blocks") or []:
        block = normalize_block(b)
        if not block:
            continue
        while block["id"] in seen:
            block["id"] = uuid.uuid4().hex
        seen.add(block["id"])
        blocks.append(block)
    utility_raw = raw.get("utility") if isinstance(raw.get("utility"), dict) else {}
    utility = {k: str(utility_raw.get(k, v) or "") for k, v in UTILITY_DEFAULTS.items()}
    options_raw = raw.get("options") if isinstance(raw.get("options"), dict) else {}
    pp = options_raw.get("post_processing")
    return {
        "blocks": blocks,
        "samplers": sampler_mod.normalize(raw.get("samplers")),
        "utility": utility,
        "options": {"post_processing": pp if pp in POST_PROCESSING else "none",
                    "streaming": bool(options_raw.get("streaming", True))},
        "extras": raw.get("extras") if isinstance(raw.get("extras"), dict) else {},
    }


# ---------------------------------------------------------------------------
# SillyTavern import / export
# ---------------------------------------------------------------------------

def is_sillytavern(data):
    return isinstance(data, dict) and isinstance(data.get("prompts"), list) and "prompt_order" in data


def _st_order(data):
    """The prompt order SillyTavern actually uses: the global one (100001), else the longest."""
    orders = [o for o in data.get("prompt_order") or [] if isinstance(o, dict) and isinstance(o.get("order"), list)]
    if not orders:
        return []
    for o in orders:
        if str(o.get("character_id")) == "100001":
            return o["order"]
    return max(orders, key=lambda o: len(o["order"]))["order"]


ST_SAMPLERS = [
    # (ST key, our key, "neutral" value that means "not really set")
    ("temperature", "temperature", None), ("top_p", "top_p", 1), ("top_k", "top_k", 0), ("min_p", "min_p", 0),
    ("top_a", "top_a", 0), ("frequency_penalty", "frequency_penalty", 0),
    ("presence_penalty", "presence_penalty", 0), ("repetition_penalty", "repetition_penalty", 1),
]
ST_HANDLED_KEYS = {"prompts", "prompt_order"} | {k for k, _, _ in ST_SAMPLERS} | {
    "openai_max_tokens", "openai_max_context", "seed", "reasoning_effort", "verbosity",
    "impersonation_prompt", "new_chat_prompt", "continue_nudge_prompt", "assistant_prefill",
    "assistant_impersonation", "squash_system_messages", "custom_prompt_post_processing", "stream_openai"}


def from_sillytavern(data):
    prompts = {p.get("identifier"): p for p in data.get("prompts") or [] if isinstance(p, dict)}
    blocks, used = [], set()
    for entry in _st_order(data):
        ident = entry.get("identifier")
        p = prompts.get(ident)
        if p is None:
            continue
        used.add(ident)
        marker = ST_MARKERS.get(ident)
        content = p.get("content") or ""
        if marker:
            kind = "marker"
        elif p.get("marker"):
            continue  # a SillyTavern-only slot we have no equivalent for
        else:
            # Empty, named blocks are used as section headers ("🐈 ─+ Tracker Toggles")
            kind = "prompt" if content.strip() else "header"
        blocks.append({
            "id": ident, "name": p.get("name") or ident, "kind": kind, "marker": marker,
            "role": p.get("role") or "system", "content": content, "enabled": bool(entry.get("enabled", True)),
            "position": "in_chat" if p.get("injection_position") == 1 else "relative",
            "depth": p.get("injection_depth", 4), "order": p.get("injection_order", 100),
        })

    samplers = {}
    for st_key, key, neutral in ST_SAMPLERS:
        if st_key in data and data[st_key] is not None:
            samplers[key] = {"on": neutral is None or data[st_key] != neutral, "value": data[st_key]}
    if data.get("openai_max_tokens"):
        samplers["max_tokens"] = {"on": True, "value": data["openai_max_tokens"]}
    if data.get("openai_max_context"):
        samplers["context_size"] = {"on": True, "value": data["openai_max_context"]}
    if isinstance(data.get("seed"), (int, float)) and data["seed"] >= 0:
        samplers["seed"] = {"on": True, "value": data["seed"]}
    effort = {"min": "minimal", "minimum": "minimal", "minimal": "minimal", "low": "low",
              "medium": "medium", "high": "high", "max": "high", "maximum": "high"}.get(
        str(data.get("reasoning_effort") or "").lower())
    if effort:
        samplers["reasoning_effort"] = {"on": True, "value": effort}
    if data.get("verbosity") in ("low", "medium", "high"):
        samplers["verbosity"] = {"on": True, "value": data["verbosity"]}

    pp = {"merge": "merge", "semi": "strict", "strict": "strict", "single": "single_user"}.get(
        data.get("custom_prompt_post_processing") or "")
    if not pp:
        pp = "merge" if data.get("squash_system_messages") else "none"

    extras = {k: v for k, v in data.items() if k not in ST_HANDLED_KEYS}
    unused = [p for i, p in prompts.items() if i not in used]
    if unused:
        extras["unused_prompts"] = unused  # not in the order: kept only so export loses nothing

    return normalize({
        "blocks": blocks,
        "samplers": samplers,
        "utility": {
            "continue_nudge": data.get("continue_nudge_prompt", UTILITY_DEFAULTS["continue_nudge"]),
            "impersonation": data.get("impersonation_prompt", UTILITY_DEFAULTS["impersonation"]),
            "new_chat": data.get("new_chat_prompt", UTILITY_DEFAULTS["new_chat"]),
            "assistant_prefill": data.get("assistant_prefill", ""),
            "assistant_impersonation": data.get("assistant_impersonation", ""),
        },
        "options": {"post_processing": pp, "streaming": bool(data.get("stream_openai", True))},
        "extras": extras,
    })


def to_sillytavern(preset):
    """SillyTavern chat-completion preset. Our own slots (summary, trackers...) have no ST equivalent."""
    out = {k: copy.deepcopy(v) for k, v in preset["extras"].items() if k != "unused_prompts"}
    s = preset["samplers"]
    for st_key, key, neutral in ST_SAMPLERS:
        if s[key]["on"]:
            out[st_key] = s[key]["value"]
    if s["max_tokens"]["on"]:
        out["openai_max_tokens"] = s["max_tokens"]["value"]
    if s["context_size"]["on"]:
        out["openai_max_context"] = s["context_size"]["value"]
        out["max_context_unlocked"] = True
    if s["reasoning_effort"]["on"]:
        out["reasoning_effort"] = s["reasoning_effort"]["value"]
    if s["verbosity"]["on"]:
        out["verbosity"] = s["verbosity"]["value"]
    if s["seed"]["on"]:
        out["seed"] = s["seed"]["value"]
    u = preset["utility"]
    out.update({"continue_nudge_prompt": u["continue_nudge"], "impersonation_prompt": u["impersonation"],
                "new_chat_prompt": u["new_chat"], "assistant_prefill": u["assistant_prefill"],
                "assistant_impersonation": u["assistant_impersonation"],
                "squash_system_messages": preset["options"]["post_processing"] == "merge",
                "stream_openai": preset["options"]["streaming"]})

    prompts, order = [], []
    for b in preset["blocks"]:
        if b["kind"] == "marker":
            ident = ST_MARKERS_REVERSE.get(b["marker"])
            if not ident:
                continue
            prompts.append({"identifier": ident, "name": b["name"], "system_prompt": True, "marker": True})
        else:
            ident = b["id"]
            prompts.append({
                "identifier": ident, "name": b["name"], "system_prompt": False, "marker": False,
                "role": b["role"], "content": b["content"],
                "injection_position": 1 if b["position"] == "in_chat" else 0,
                "injection_depth": b["depth"], "injection_order": b["order"], "forbid_overrides": False,
            })
        order.append({"identifier": ident, "enabled": b["enabled"]})
    prompts.extend(preset["extras"].get("unused_prompts", []))
    out["prompts"] = prompts
    out["prompt_order"] = [{"character_id": 100001, "order": order}]
    return out


def to_native(preset, name):
    return {"format": FORMAT, "version": 1, "name": name, **copy.deepcopy(preset)}


def from_any(data):
    """(preset, suggested name) from our own export or a SillyTavern preset."""
    if is_sillytavern(data):
        return from_sillytavern(data), ""
    if isinstance(data, dict) and (data.get("format") == FORMAT or "blocks" in data):
        return normalize(data), str(data.get("name") or "")
    raise ValueError("This file is neither a NarrativeAI preset nor a SillyTavern chat-completion preset.")


# ---------------------------------------------------------------------------
# Macros
# ---------------------------------------------------------------------------

MACRO = re.compile(r"\{\{([^{}]*)\}\}")
TRIM = "\x00trim\x00"


class MacroContext:
    def __init__(self, values, rng=None):
        self.values = values      # lower-case macro name -> text ({{char}}, {{description}}...)
        self.vars = {}
        self.rng = rng or _random.Random()
        self.unknown = set()


def _roll(spec, rng):
    m = re.fullmatch(r"\s*(\d*)\s*d\s*(\d+)\s*([+-]\s*\d+)?\s*", spec, re.I)
    if not m:
        m2 = re.fullmatch(r"\s*(\d+)\s*", spec)
        return str(rng.randint(1, int(m2.group(1)))) if m2 and int(m2.group(1)) > 0 else None
    count, sides = int(m.group(1) or 1), int(m.group(2))
    if not (0 < count <= 100 and sides > 0):
        return None
    total = sum(rng.randint(1, sides) for _ in range(count))
    return str(total + int((m.group(3) or "0").replace(" ", "")))


def _choices(rest):
    rest = rest.lstrip(":").strip() if not rest.startswith("::") else rest[2:]
    parts = rest.split("::") if "::" in rest else rest.split(",")
    return [p.strip() for p in parts if p.strip()] or [""]


def _macro(body, ctx, collect):
    b = body.strip()
    low = b.lower()
    if b.startswith("//"):
        return ""
    if low == "trim":
        return TRIM
    if low == "noop":
        return ""
    if low == "newline":
        return "\n"
    if low in ctx.values:
        return ctx.values[low]

    head, _, rest = b.partition("::")
    head_low = head.strip().lower()
    if head_low == "setvar":
        name, _, value = rest.partition("::")
        if collect:
            ctx.vars[name.strip()] = value
        return ""
    if head_low == "getvar":
        return ctx.vars.get(rest.strip().rstrip(":").strip(), "")
    if head_low in ("addvar", "incvar", "decvar"):
        name, _, value = rest.partition("::")
        name = name.strip()
        if collect:
            current = ctx.vars.get(name, "")
            delta = 1 if head_low == "incvar" else -1 if head_low == "decvar" else value
            try:
                ctx.vars[name] = str(int(float(current or 0) + float(delta)))
            except (TypeError, ValueError):
                ctx.vars[name] = f"{current}{value}"
        return ""

    m = re.match(r"(random|pick)(?=\s*:|\s|$)\s*(.*)$", b, re.I | re.S)
    if m:
        return ctx.rng.choice(_choices(m.group(2)))
    m = re.match(r"roll\s*:?\s*(.*)$", b, re.I)
    if m:
        result = _roll(m.group(1), ctx.rng)
        if result is not None:
            return result

    ctx.unknown.add(b[:40])
    return "{{" + body + "}}"


IF_BLOCK = re.compile(r"\{\{#if\s+([^{}]*)\}\}((?:(?!\{\{#if\s).)*?)\{\{/if\}\}", re.S | re.I)


def _truthy(cond, ctx):
    cond = cond.strip()
    negate = cond.startswith("!")
    cond = cond.lstrip("!").strip()
    if cond.startswith((".", "$")):  # {{#if .name}}: a variable
        value = ctx.vars.get(cond[1:].strip(), "")
    else:                             # {{#if description}}: a macro value
        value = ctx.values.get(cond.lower(), ctx.vars.get(cond, ""))
    result = str(value).strip().lower() not in ("", "0", "false", "no")
    return result != negate


def _if_block(m, ctx):
    parts = re.split(r"\{\{else\}\}", m.group(2), maxsplit=1, flags=re.I)
    otherwise = parts[1] if len(parts) > 1 else ""
    return parts[0] if _truthy(m.group(1), ctx) else otherwise


def expand(text, ctx, collect=False):
    if not text or "{{" not in text:
        return text or ""
    # {{#if cond}} ... {{else}} ... {{/if}}, innermost first
    for _ in range(10):
        new = IF_BLOCK.sub(lambda m: _if_block(m, ctx), text)
        if new == text:
            break
        text = new
    for _ in range(10):  # innermost macros first, so {{getvar::{{user}}_x}} style nesting works
        new = MACRO.sub(lambda m: _macro(m.group(1), ctx, collect), text)
        if new == text:
            break
        text = new
    if TRIM in text:
        text = re.sub(r"\s*" + re.escape(TRIM) + r"\s*", "", text)
    return text


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def macro_values(names, slots, history):
    last_user = next((m["content"] for m in reversed(history) if m["role"] == "user"), "")
    last_char = next((m["content"] for m in reversed(history) if m["role"] == "assistant"), "")
    now = datetime.now()
    return {
        "char": names["char"], "user": names["user"], "group": names["char"],
        "persona": slots.get("persona", ""), "description": slots.get("char_description", ""),
        "scenario": slots.get("scenario", ""), "personality": slots.get("char_personality", ""),
        "creator_notes": slots.get("char_personality", ""), "summary": slots.get("summary", ""),
        "mesexamples": slots.get("examples", ""), "mesexamplesraw": slots.get("examples", ""),
        "lastchatmessage": history[-1]["content"] if history else "",
        "lastusermessage": last_user, "lastcharmessage": last_char,
        "time": now.strftime("%H:%M"), "date": now.strftime("%B %d, %Y"), "weekday": now.strftime("%A"),
        "isotime": now.strftime("%H:%M"), "isodate": now.strftime("%Y-%m-%d"),
    }


def _merge_same_role(messages):
    out = []
    for m in messages:
        if out and out[-1]["role"] == m["role"]:
            out[-1] = {**out[-1], "content": out[-1]["content"] + "\n\n" + m["content"],
                       "sources": out[-1]["sources"] + m["sources"]}
        else:
            out.append(dict(m))
    return out


def _post_process(messages, mode, names, new_chat):
    if mode == "single_user":
        parts = []
        for m in messages:
            if m.get("chat"):
                speaker = names["user"] if m["role"] == "user" else names["char"]
                parts.append(f"{speaker}: {m['content']}")
            else:
                parts.append(m["content"])
        sources = [s for m in messages for s in m["sources"]]
        return [{"role": "user", "content": "\n\n".join(parts), "sources": sources}]
    if mode == "strict":
        lead = []
        while messages and messages[0]["role"] == "system":
            lead.append(messages.pop(0))
        rest = [{**m, "role": "user"} if m["role"] == "system" else m for m in messages]
        if not rest or rest[0]["role"] != "user":
            rest.insert(0, {"role": "user", "content": new_chat or "[Start a new chat]", "sources": ["New chat prompt"]})
        out = _merge_same_role(lead) + _merge_same_role(rest)
        return out
    if mode == "merge":
        return _merge_same_role(messages)
    return messages


def assemble(preset, slots, history, names, model="", rng=None):
    """
    preset:  normalized preset
    slots:   marker id -> text ("lore" fills lore_before, or lore_after if only that one is on)
    history: chat turns [{"role": "user"/"assistant", "content": ...}], oldest first
    names:   {"char": ..., "user": ...}
    Returns {"messages": [...for the API...], "preview": [...with sources...], "params": {...}, "notes": [...]}
    """
    notes = []
    slots = dict(slots)
    enabled = [b for b in preset["blocks"] if b["enabled"] and b["kind"] != "header"]
    on_markers = {b["marker"] for b in enabled if b["kind"] == "marker"}
    if slots.get("lore"):
        target = "lore_before" if "lore_before" in on_markers or "lore_after" not in on_markers else "lore_after"
        slots[target] = slots.pop("lore")
        if target not in on_markers:
            notes.append("Lore matched, but both Lore blocks are switched off, so it was not sent.")

    ctx = MacroContext(macro_values(names, slots, history), rng)
    # Pass 1: run every setvar so getvar works wherever it is placed
    for b in enabled:
        if b["kind"] == "prompt":
            expand(b["content"], ctx, collect=True)
    for key in ("assistant_prefill",):
        expand(preset["utility"][key], ctx, collect=True)

    relative, in_chat, history_index = [], [], None
    for b in enabled:
        if b["kind"] == "marker":
            if b["marker"] == "chat_history":
                history_index = len(relative)
                continue
            text = expand(slots.get(b["marker"]) or "", ctx)
        else:
            text = expand(b["content"], ctx)
        if not text.strip():
            continue
        entry = {"role": b["role"], "content": text.strip(), "sources": [b["name"]]}
        if b["position"] == "in_chat":
            in_chat.append((b["depth"], b["order"], entry))
        else:
            relative.append(entry)

    # Fit the chat into the context size, counting everything else that will be sent
    chat = [{"role": m["role"], "content": m["content"]} for m in history]
    if history_index is None:
        if chat:
            notes.append("The Chat history block is switched off, so the AI does not see the conversation.")
        chat = []
    others = relative + [e for _, _, e in in_chat]
    chat, dropped = sampler_mod.trim_history(others, chat, preset["samplers"])
    if dropped:
        notes.append(f"{dropped} older message(s) left out to fit the context size.")

    # In-chat blocks: depth 0 = after the last message, 1 = before it, ...
    buckets = {}
    for depth, order, entry in sorted(in_chat, key=lambda x: x[1]):
        buckets.setdefault(max(0, len(chat) - depth), []).append(entry)
    with_injections = []
    for i in range(len(chat) + 1):
        with_injections += buckets.get(i, [])
        if i < len(chat):
            with_injections.append({**chat[i], "sources": ["Chat history"], "chat": True})

    if history_index is None:
        messages = relative + with_injections
    else:
        messages = relative[:history_index] + with_injections + relative[history_index:]

    prefill = expand(preset["utility"]["assistant_prefill"], ctx).strip()
    if prefill:
        messages.append({"role": "assistant", "content": prefill, "sources": ["Assistant prefill"]})

    messages = _post_process(messages, preset["options"]["post_processing"], names,
                             expand(preset["utility"]["new_chat"], ctx))

    if model and PREFILL_REJECTING_MODELS.search(model):
        # Only prefill-style blocks are removed, never the chat itself
        while messages and messages[-1]["role"] == "assistant" and "Chat history" not in messages[-1]["sources"]:
            dropped_msg = messages.pop()
            notes.append(f"Dropped a final assistant message ({', '.join(dropped_msg['sources'])}): "
                         f"{model} does not accept prefill.")

    params, skipped = sampler_mod.to_api_params(preset["samplers"], model)
    if skipped:
        notes.append(f"Not sent, because {model} doesn't use them: {', '.join(skipped)}.")
    if ctx.unknown:
        notes.append("Unknown macros left as they are: " + ", ".join("{{" + u + "}}" for u in sorted(ctx.unknown)))

    return {
        "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
        "preview": [{"role": m["role"], "content": m["content"], "sources": m["sources"],
                     "tokens": sampler_mod.approx_tokens(m["content"])} for m in messages],
        "params": params,
        "notes": notes,
        "variables": ctx.vars,
        "dropped": dropped,
    }


# ---------------------------------------------------------------------------
# Storage (Preset model) and the built-in default preset
# ---------------------------------------------------------------------------

DEFAULT_NAME = "NarrativeAI Default"
OLD_PROMPT_FIELDS = [
    # (old Chat Settings key, block name)
    ("system", "Main prompt"), ("character", "Character guidance"), ("scenario", "Scenario guidance"),
    ("style", "Writing style"), ("memory", "Memory"), ("safety", "Safety"), ("format", "Formatting"),
    ("antirepetition", "Anti-repetition"),
]


def _block(name, content="", enabled=True, **extra):
    return {"id": uuid.uuid4().hex, "name": name, "kind": "prompt", "content": content, "enabled": enabled, **extra}


def _header(name):
    return {"id": uuid.uuid4().hex, "name": name, "kind": "header", "enabled": True}


def _marker(marker, enabled=True, **extra):
    return {"id": marker, "name": MARKERS[marker], "kind": "marker", "marker": marker, "enabled": enabled, **extra}


def _read_json_file(path):
    import json
    import os
    try:
        if path and os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        pass
    return {}


def build_default(user):
    """
    The first preset for a user, built from what used to drive the chat:
    the old Chat Settings prompts, the Prompting Ground rules and the Samplers page.
    """
    import json
    import os
    from django.conf import settings
    from mainapp.models import ChatSettings

    chat_settings = ChatSettings.objects.filter(author=user).first()
    old = {}
    if chat_settings and chat_settings.json_file:
        try:
            old = _read_json_file(chat_settings.json_file.path)
        except (ValueError, NotImplementedError):
            old = {}
    old_saved = bool(old)  # before presets, old prompts were only sent once the page had been saved
    old_prompts = old.get("prompts") if isinstance(old.get("prompts"), dict) else {}

    ground = _read_json_file(os.path.join(settings.MEDIA_ROOT, "chat_settings2", f"chat_settings2_{user.id}.json"))
    with open(os.path.join(os.path.dirname(__file__), "data", "prompt_library.json"), encoding="utf-8") as f:
        library = json.load(f)

    blocks = []
    main = [(name, old_prompts.get(key)) for key, name in OLD_PROMPT_FIELDS
            if isinstance(old_prompts.get(key), str) and old_prompts.get(key).strip()]
    if main:
        blocks.append(_header("📜 Chat Settings prompts"))
        blocks += [_block(name, text, enabled=old_saved) for name, text in main]
        for key, item in (old_prompts.get("custom") or {}).items():
            if isinstance(item, dict) and str(item.get("prompt") or "").strip():
                blocks.append(_block(item.get("name") or key, item["prompt"], enabled=old_saved))

    for cat in library["categories"]:
        saved_cat = ground.get(cat["id"]) if isinstance(ground.get(cat["id"]), dict) else {}
        blocks.append(_header(f"{cat['icon']} {cat['label']}"))
        for rule in cat["rules"]:
            saved = saved_cat.get(rule["key"]) if isinstance(saved_cat.get(rule["key"]), dict) else {}
            if ground:
                enabled = bool(saved.get("enabled", False))
            else:
                # Fresh default: the library's own choices, except the AVI voices (long, an experiment)
                enabled = rule["enabled"] and cat["id"] != "avis"
            blocks.append(_block(saved.get("name") or rule["name"], saved.get("content") or rule["content"],
                                 enabled=enabled))

    nsfw = old.get("nsfw") if isinstance(old.get("nsfw"), dict) else {}
    styles = {**(nsfw.get("styles") or {}), **(nsfw.get("custom") or {})}
    styles = {k: v for k, v in styles.items() if isinstance(v, dict) and str(v.get("prompt") or "").strip()}
    if styles:
        blocks.append(_header("🔞 NSFW styles (turn on the one you want)"))
        blocks += [_block(v.get("name") or k, v["prompt"], enabled=False) for k, v in styles.items()]

    blocks += [
        _header("📖 Story context"),
        _marker("persona"), _marker("char_description"), _marker("char_personality"), _marker("scenario"),
        _marker("lore_before"), _marker("summary"), _marker("world_context"), _marker("trackers"),
        _marker("lore_after"),
        _marker("chat_history"),
    ]
    jailbreak = old_prompts.get("jailbreak")
    if isinstance(jailbreak, str) and jailbreak.strip():
        blocks.append(_block("Post-history instructions", jailbreak, enabled=old_saved))
    blocks.append(_marker("director_note", position="in_chat", depth=0))

    utility = {}
    if isinstance(old_prompts.get("continue"), str) and old_prompts["continue"].strip():
        utility["continue_nudge"] = old_prompts["continue"]
    if isinstance(old_prompts.get("impersonate"), str) and old_prompts["impersonate"].strip():
        utility["impersonation"] = old_prompts["impersonate"]

    return normalize({
        "blocks": blocks,
        "samplers": chat_settings.samplers if chat_settings else {},
        "utility": utility,
        "options": {"post_processing": "merge"},
    })


def unique_name(user, name, exclude_id=None):
    from mainapp.models import Preset
    base = (name or "Preset").strip()[:180] or "Preset"
    candidate, n = base, 2
    while Preset.objects.filter(user=user, name=candidate).exclude(id=exclude_id).exists():
        candidate, n = f"{base} ({n})", n + 1
    return candidate


def get_active(user):
    """The user's active Preset (created from their old settings the first time)."""
    from mainapp.models import Preset
    active = Preset.objects.filter(user=user, is_active=True).first()
    if active:
        return active
    active = Preset.objects.filter(user=user).first()
    if active is None:
        active = Preset(user=user, name=unique_name(user, DEFAULT_NAME), data=build_default(user))
    active.is_active = True
    active.save()
    return active


def activate(preset_obj):
    from mainapp.models import Preset
    Preset.objects.filter(user=preset_obj.user, is_active=True).exclude(id=preset_obj.id).update(is_active=False)
    preset_obj.is_active = True
    preset_obj.save(update_fields=["is_active"])
