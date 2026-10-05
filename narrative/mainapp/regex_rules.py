"""
Text rules ("regex scripts"), as in SillyTavern: find-and-replace rules that clean or decorate messages.

A rule runs on the user's messages, the AI's replies, or both (`placement`), and in one of three ways:
    - "saved"   (neither flag in SillyTavern): changes the message itself when it's sent or received.
    - "display" (markdownOnly): changes only what's shown on screen. Runs in the browser
                 (static/mainapp/js/regex_rules.js) with the browser's own regex engine.
    - "prompt"  (promptOnly): changes only what's sent to the AI, e.g. dropping old tracker blocks.
`min_depth` / `max_depth` limit a rule to messages that many places from the newest (0 = the newest).

Rules come from the active preset (SillyTavern presets carry them in extensions.regex_scripts) and from
the character card (card_data.extensions.regex_scripts). SillyTavern writes them as JavaScript regexes
("/pattern/flags"); this module translates the few syntax differences so Python can run them. A rule
that still can't run here is reported by `check()` and skipped on the server.
"""
import re
import uuid

USER_INPUT, AI_OUTPUT = 1, 2
PLACEMENT_NAMES = {1: "your messages", 2: "AI replies", 3: "slash commands", 5: "lore entries", 6: "reasoning"}
MODES = ("saved", "display", "prompt")
MAX_INPUT = 200_000  # characters per message a rule will look at


# ---------------------------------------------------------------------------
# Format
# ---------------------------------------------------------------------------

def _depth(value):
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n if n >= 0 else None


def normalize_rule(raw):
    if not isinstance(raw, dict):
        return None
    if "findRegex" in raw or "scriptName" in raw:  # SillyTavern format
        mode = "display" if raw.get("markdownOnly") else "prompt" if raw.get("promptOnly") else "saved"
        raw = {"id": raw.get("id"), "name": raw.get("scriptName"), "find": raw.get("findRegex"),
               "replace": raw.get("replaceString"), "trim": raw.get("trimStrings"),
               "placement": raw.get("placement"), "enabled": not raw.get("disabled", False), "mode": mode,
               "macros_in_find": raw.get("substituteRegex"), "min_depth": raw.get("minDepth"),
               "max_depth": raw.get("maxDepth"), "run_on_edit": raw.get("runOnEdit", False)}
    find = str(raw.get("find") or "")  # may be empty: such a rule does nothing, but is kept
    placement = [p for p in (raw.get("placement") or [AI_OUTPUT]) if isinstance(p, int) and p in PLACEMENT_NAMES]
    return {
        "id": str(raw.get("id") or uuid.uuid4())[:64],
        "name": str(raw.get("name") or "Untitled rule")[:200],
        "find": find[:20000],
        "replace": str(raw.get("replace") or "")[:50000],
        "trim": [str(t) for t in (raw.get("trim") or []) if isinstance(t, str) and t][:50],
        "placement": placement or [AI_OUTPUT],
        "enabled": bool(raw.get("enabled", True)),
        "mode": raw.get("mode") if raw.get("mode") in MODES else "saved",
        "macros_in_find": raw.get("macros_in_find") if raw.get("macros_in_find") in (0, 1, 2) else 0,
        "min_depth": _depth(raw.get("min_depth")),
        "max_depth": _depth(raw.get("max_depth")),
        "run_on_edit": bool(raw.get("run_on_edit", False)),
    }


def normalize_rules(raw_list):
    rules, seen = [], set()
    for raw in raw_list if isinstance(raw_list, list) else []:
        rule = normalize_rule(raw)
        if rule:
            while rule["id"] in seen:
                rule["id"] = str(uuid.uuid4())
            seen.add(rule["id"])
            rules.append(rule)
    return rules


def to_sillytavern(rule):
    return {"id": rule["id"], "scriptName": rule["name"], "findRegex": rule["find"],
            "replaceString": rule["replace"], "trimStrings": rule["trim"], "placement": rule["placement"],
            "disabled": not rule["enabled"], "markdownOnly": rule["mode"] == "display",
            "promptOnly": rule["mode"] == "prompt", "runOnEdit": rule["run_on_edit"],
            "substituteRegex": rule["macros_in_find"], "minDepth": rule["min_depth"], "maxDepth": rule["max_depth"]}


def from_import(data):
    """A SillyTavern regex export (one script or a list), or our own list, -> rules."""
    if isinstance(data, dict) and isinstance(data.get("regex_scripts"), list):
        data = data["regex_scripts"]
    if isinstance(data, dict):
        data = [data]
    return normalize_rules(data)


# ---------------------------------------------------------------------------
# JavaScript regex -> Python
# ---------------------------------------------------------------------------

_SLASHED = re.compile(r"^/([\s\S]+)/([a-z]*)$")


def _translate(pattern, unicode_flag):
    """The JavaScript-only bits of a pattern, in Python syntax. Walks the pattern so escapes stay intact."""
    out, i, n, in_class = [], 0, len(pattern), False
    while i < n:
        c = pattern[i]
        if c == "\\" and i + 1 < n:
            nxt = pattern[i + 1]
            if nxt == "k" and pattern.startswith("<", i + 2):  # \k<name> backreference
                end = pattern.find(">", i + 3)
                if end > 0:
                    out.append(f"(?P={pattern[i + 3:end]})")
                    i = end + 1
                    continue
            if nxt == "u" and pattern.startswith("{", i + 2) and unicode_flag:  # \u{1F600}
                end = pattern.find("}", i + 3)
                if end > 0:
                    out.append(f"\\U{int(pattern[i + 3:end], 16):08x}")
                    i = end + 1
                    continue
            if nxt == "d" and not in_class:
                out.append("[0-9]")  # JavaScript's \d is ASCII only
                i += 2
                continue
            if nxt.isalpha() and nxt not in "dDwWsSbBnrtfvuxcpPk0" and not nxt.isdigit():
                out.append(nxt)  # JavaScript ignores unknown letter escapes like \e; Python refuses them
                i += 2
                continue
            out.append(pattern[i:i + 2])
            i += 2
            continue
        if in_class:
            if c == "]":
                in_class = False
            elif c == "[":
                out.append("\\[")
                i += 1
                continue
            out.append(c)
            i += 1
            continue
        if c == "[":
            if pattern.startswith("[^]", i):
                out.append(r"[\s\S]")  # JavaScript: any character
                i += 3
                continue
            if pattern.startswith("[]", i):
                out.append("(?!)")  # JavaScript: never matches
                i += 2
                continue
            in_class = True
            out.append(c)
            i += 1
            if i < n and pattern[i] == "^":
                out.append("^")
                i += 1
            if i < n and pattern[i] == "]":  # "]" right after "[" or "[^" is a literal in Python, not in JS
                out.append("\\]")
                i += 1
            continue
        if c == "(" and pattern.startswith("(?<", i) and not pattern.startswith(("(?<=", "(?<!"), i):
            out.append("(?P<")  # named group
            i += 3
            continue
        out.append(c)
        i += 1
    return "".join(out)


def compile_find(find, macros=None, macros_mode=0):
    """'/pattern/flags' (or a bare pattern) -> (compiled regex, replace-all?). Raises re.error."""
    if macros_mode and macros:
        def sub(m):
            value = macros.get(m.group(1).strip().lower())
            if value is None:
                return m.group(0)
            return re.escape(value) if macros_mode == 2 else value
        find = re.sub(r"\{\{([^{}]+)\}\}", sub, find)
    m = _SLASHED.match(find)
    pattern, flags = (m.group(1), m.group(2)) if m else (find, "")
    py_flags = 0
    if "i" in flags:
        py_flags |= re.IGNORECASE
    if "m" in flags:
        py_flags |= re.MULTILINE
    if "s" in flags:
        py_flags |= re.DOTALL
    return re.compile(_translate(pattern, "u" in flags or "v" in flags), py_flags), "g" in flags


def check(rule):
    """None if the rule can run on the server, else a short reason."""
    if not rule["find"]:
        return "There's nothing to find yet."
    try:
        compile_find(rule["find"], {"char": "x", "user": "x"}, rule["macros_in_find"])
    except (re.error, ValueError, OverflowError) as e:
        return f"Can't run on the server: {e}"
    return None


# ---------------------------------------------------------------------------
# Running rules
# ---------------------------------------------------------------------------

_GROUP_REF = re.compile(r"\$(\d+)|\$<([^>]+)>")
_NAME_MACROS = re.compile(r"\{\{\s*(char|user)\s*\}\}", re.I)


def _fill(text, names):
    return _NAME_MACROS.sub(lambda m: names.get(m.group(1).lower(), m.group(0)), text)


def run_rule(rule, text, names):
    """One rule over one text, as SillyTavern does it: {{match}} is $0, groups are $1 / $<name>, a group's
    text loses the rule's trim strings, and {{char}}/{{user}} in the result become names."""
    if not text or not rule["find"]:
        return text
    try:
        regex, every = compile_find(rule["find"], names, rule["macros_in_find"])
    except (re.error, ValueError, OverflowError):
        return text
    template = re.sub(r"\{\{match\}\}", "$0", rule["replace"], flags=re.I)
    trims = [_fill(t, names) for t in rule["trim"]]

    def replace(m):
        def group(ref):
            num, name = ref.group(1), ref.group(2)
            try:
                value = m.group(int(num)) if num is not None else m.group(name)
            except (IndexError, KeyError, re.error):
                value = None
            if not value:
                return ""
            for t in trims:
                value = value.replace(t, "")
            return value
        return _fill(_GROUP_REF.sub(group, template), names)

    return regex.sub(replace, text[:MAX_INPUT], count=0 if every else 1) + text[MAX_INPUT:]



def applies(rule, mode, role, depth):
    if not rule["enabled"] or rule["mode"] != mode:
        return False
    if (USER_INPUT if role == "user" else AI_OUTPUT) not in rule["placement"]:
        return False
    if depth is not None:
        if rule["min_depth"] is not None and depth < rule["min_depth"]:
            return False
        if rule["max_depth"] is not None and depth > rule["max_depth"]:
            return False
    return True


def run(rules, mode, text, role, names, depth=None):
    for rule in rules:
        if applies(rule, mode, role, depth):
            text = run_rule(rule, text, names)
    return text


def run_on_history(rules, history, names):
    """The "prompt" rules over chat turns [{"role", "content"}], oldest first; depth 0 is the newest."""
    if not any(r["enabled"] and r["mode"] == "prompt" for r in rules):
        return history
    last = len(history) - 1
    return [{**m, "content": run(rules, "prompt", m["content"], m["role"], names, depth=last - i)}
            for i, m in enumerate(history)]


# ---------------------------------------------------------------------------
# Which rules apply to a chat
# ---------------------------------------------------------------------------

def for_chat(preset, character):
    """The active preset's rules, then the character card's."""
    rules = list((preset or {}).get("regex") or [])
    card = getattr(character, "card_data", None) or {}
    ext = card.get("extensions") if isinstance(card.get("extensions"), dict) else {}
    rules += normalize_rules(ext.get("regex_scripts"))
    return rules
