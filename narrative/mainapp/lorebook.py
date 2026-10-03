"""
Lorebook (worldbook) engine, modelled on SillyTavern World Info.

How an entry gets into the prompt:
1. Constant entries are always included.
2. Keyword entries fire when one of their keys appears in the last
   `scan_depth` chat messages (optionally gated by secondary keys).
3. With `recursive_scan` on, content of fired entries is scanned again,
   so entries can trigger each other.
4. With `semantic_enabled` on, entries that did not fire by keyword can
   still be picked by meaning (needs the optional sentence-transformers
   package, see requirements-semantic.txt).
5. Everything is sorted by `order` and trimmed to `token_budget`.

Every decision is recorded in a report so the user can see why an entry
was (or was not) used.
"""
import hashlib
import json
import re
from functools import lru_cache

LOGIC_CHOICES = ("AND_ANY", "NOT_ALL", "NOT_ANY", "AND_ALL")
# SillyTavern stores selectiveLogic as an int
ST_LOGIC = {0: "AND_ANY", 1: "NOT_ALL", 2: "NOT_ANY", 3: "AND_ALL"}
ST_LOGIC_REVERSE = {v: k for k, v in ST_LOGIC.items()}

DEFAULT_SETTINGS = {
    "scan_depth": 4,            # how many recent messages are scanned for keys
    "token_budget": 1500,       # rough cap on lore size added to the prompt
    "case_sensitive": False,
    "match_whole_words": True,
    "recursive_scan": False,
    "max_recursion_steps": 3,
    "semantic_enabled": False,  # meaning-based fallback, off by default
    "semantic_threshold": 0.5,
    "semantic_top_k": 2,
}

DEFAULT_ENTRY = {
    "uid": 0,
    "comment": "",              # entry title, shown in the editor and reports
    "keys": [],
    "secondary_keys": [],
    "selective_logic": "AND_ANY",
    "content": "",
    "constant": False,
    "enabled": True,
    "order": 100,               # higher = more important, placed closer to the chat
    "case_sensitive": None,     # None = use book setting
    "match_whole_words": None,
    "scan_depth": None,
    "semantic": True,           # may be picked by the semantic fallback
    "exclude_recursion": False, # cannot be triggered by other entries
    "prevent_recursion": False, # its content does not trigger other entries
}

SEMANTIC_MODEL_NAME = "all-MiniLM-L6-v2"


# ---------------------------------------------------------------------------
# Normalisation / import
# ---------------------------------------------------------------------------

def _as_list(value):
    if value is None:
        return []
    if isinstance(value, str):
        return [k.strip() for k in value.split(",") if k.strip()]
    if isinstance(value, (list, tuple)):
        return [str(k).strip() for k in value if str(k).strip()]
    return [str(value)]


def _as_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def _as_int(value, default=None):
    if value is None or value == "":
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _as_float(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _pick(raw, ext, *names, default=None):
    """First present value among `names`, looking in the entry, then its extensions."""
    for source in (raw, ext):
        for name in names:
            if name in source and source[name] is not None:
                return source[name]
    return default


def normalize_entry(raw, uid):
    if not isinstance(raw, dict):
        return None
    ext = raw.get("extensions") if isinstance(raw.get("extensions"), dict) else {}

    logic = _pick(raw, ext, "selective_logic", "selectiveLogic", default="AND_ANY")
    if isinstance(logic, (int, float)) or (isinstance(logic, str) and logic.isdigit()):
        logic = ST_LOGIC.get(int(logic), "AND_ANY")
    if logic not in LOGIC_CHOICES:
        logic = "AND_ANY"

    if "disable" in raw:  # SillyTavern world info file
        enabled = not _as_bool(raw["disable"])
    else:
        enabled = _as_bool(raw.get("enabled"), True)

    case_sensitive = _pick(raw, ext, "case_sensitive", "caseSensitive")
    whole_words = _pick(raw, ext, "match_whole_words", "matchWholeWords")

    entry = {
        "uid": _as_int(_pick(raw, ext, "uid", "id"), uid),
        "comment": str(_pick(raw, ext, "comment", "name", "title", default="") or ""),
        "keys": _as_list(_pick(raw, ext, "keys", "key", "keyword", "keywords")),
        "secondary_keys": _as_list(_pick(raw, ext, "secondary_keys", "keysecondary")),
        "selective_logic": logic,
        "content": str(_pick(raw, ext, "content", "value", default="") or ""),
        "constant": _as_bool(raw.get("constant")),
        "enabled": enabled,
        "order": _as_int(_pick(raw, ext, "order", "insertion_order", "priority"), 100),
        "case_sensitive": None if case_sensitive is None else _as_bool(case_sensitive),
        "match_whole_words": None if whole_words is None else _as_bool(whole_words),
        "scan_depth": _as_int(_pick(raw, ext, "scan_depth", "scanDepth")),
        "semantic": _as_bool(raw.get("semantic"), True),
        "exclude_recursion": _as_bool(_pick(raw, ext, "exclude_recursion", "excludeRecursion")),
        "prevent_recursion": _as_bool(_pick(raw, ext, "prevent_recursion", "preventRecursion")),
    }
    return entry


def normalize_settings(raw):
    raw = raw if isinstance(raw, dict) else {}
    s = dict(DEFAULT_SETTINGS)
    s["scan_depth"] = max(0, _as_int(raw.get("scan_depth"), s["scan_depth"]))
    s["token_budget"] = max(0, _as_int(raw.get("token_budget"), s["token_budget"]))
    s["case_sensitive"] = _as_bool(raw.get("case_sensitive"), s["case_sensitive"])
    s["match_whole_words"] = _as_bool(raw.get("match_whole_words"), s["match_whole_words"])
    s["recursive_scan"] = _as_bool(raw.get("recursive_scan"), s["recursive_scan"])
    s["max_recursion_steps"] = max(1, _as_int(raw.get("max_recursion_steps"), s["max_recursion_steps"]))
    s["semantic_enabled"] = _as_bool(raw.get("semantic_enabled"), s["semantic_enabled"])
    s["semantic_threshold"] = _as_float(raw.get("semantic_threshold"), s["semantic_threshold"])
    s["semantic_top_k"] = max(0, _as_int(raw.get("semantic_top_k"), s["semantic_top_k"]))
    return s


def normalize_book(data):
    """
    Accepts our own format, a SillyTavern world info export, a Character Card
    V2/V3 (with an embedded character_book) or a bare character_book.
    Returns {"title", "description", "settings", "entries"}.
    """
    if isinstance(data, str):
        data = json.loads(data)
    if not isinstance(data, dict):
        data = {}

    # Character card: {"spec": "chara_card_v2", "data": {"character_book": {...}}}
    card_data = data.get("data") if isinstance(data.get("data"), dict) else None
    if card_data and isinstance(card_data.get("character_book"), dict):
        book = card_data["character_book"]
        title = book.get("name") or card_data.get("name") or ""
        return _normalize_book_body(book, title, book.get("description", ""), {})
    if isinstance(data.get("character_book"), dict):
        book = data["character_book"]
        return _normalize_book_body(book, book.get("name") or data.get("name", ""), book.get("description", ""), {})

    title = data.get("title") or data.get("name") or ""
    return _normalize_book_body(data, title, data.get("description", ""), data.get("settings"))


def _normalize_book_body(book, title, description, settings):
    raw_entries = book.get("entries", [])
    if isinstance(raw_entries, dict):  # SillyTavern: {"0": {...}, "1": {...}}
        raw_entries = list(raw_entries.values())
    if not isinstance(raw_entries, list):
        raw_entries = []

    settings = dict(settings or {})
    # character_book level fields map onto our settings
    if "scan_depth" in book and "scan_depth" not in settings:
        settings["scan_depth"] = book["scan_depth"]
    if "token_budget" in book and "token_budget" not in settings:
        settings["token_budget"] = book["token_budget"]
    if "recursive_scanning" in book and "recursive_scan" not in settings:
        settings["recursive_scan"] = book["recursive_scanning"]

    entries = []
    used_uids = set()
    for i, raw in enumerate(raw_entries):
        entry = normalize_entry(raw, i)
        if entry is None:
            continue
        if entry["uid"] in used_uids:
            entry["uid"] = max(used_uids) + 1
        used_uids.add(entry["uid"])
        entries.append(entry)

    return {
        "title": str(title or ""),
        "description": str(description or ""),
        "settings": normalize_settings(settings),
        "entries": entries,
    }


def to_sillytavern(book):
    """Export in SillyTavern world info format so the book can be used there."""
    st_entries = {}
    for i, e in enumerate(book.get("entries", [])):
        st_entries[str(e["uid"])] = {
            "uid": e["uid"],
            "key": e["keys"],
            "keysecondary": e["secondary_keys"],
            "comment": e["comment"],
            "content": e["content"],
            "constant": e["constant"],
            "selective": bool(e["secondary_keys"]),
            "selectiveLogic": ST_LOGIC_REVERSE.get(e["selective_logic"], 0),
            "order": e["order"],
            "position": 0,
            "disable": not e["enabled"],
            "excludeRecursion": e["exclude_recursion"],
            "preventRecursion": e["prevent_recursion"],
            "probability": 100,
            "useProbability": True,
            "scanDepth": e["scan_depth"],
            "caseSensitive": e["case_sensitive"],
            "matchWholeWords": e["match_whole_words"],
            "vectorized": False,
            "displayIndex": i,
        }
    return {"entries": st_entries}


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

@lru_cache(maxsize=2048)
def _key_pattern(key, case_sensitive, whole_words):
    # "/regex/flags" keys, as in SillyTavern
    m = re.fullmatch(r"/(.+)/([a-z]*)", key)
    if m:
        flags = re.IGNORECASE if "i" in m.group(2) else 0
        try:
            return re.compile(m.group(1), flags)
        except re.error:
            pass  # not a valid regex, treat it as plain text
    pattern = re.escape(key)
    if whole_words:
        pattern = rf"(?<!\w){pattern}(?!\w)"
    return re.compile(pattern, 0 if case_sensitive else re.IGNORECASE)


def _matching_keys(keys, text, case_sensitive, whole_words):
    return [k for k in keys if k and _key_pattern(k, case_sensitive, whole_words).search(text)]


def _message_text(msg):
    # chat logs store messages as [role, time, text, emotion, char_count]
    if isinstance(msg, (list, tuple)):
        return str(msg[2]) if len(msg) > 2 else ""
    if isinstance(msg, dict):
        return str(msg.get("content") or msg.get("text") or "")
    return str(msg or "")


def _check_entry(entry, text, settings):
    """Returns a reason string if the entry's keys fire on `text`, else None."""
    cs = settings["case_sensitive"] if entry["case_sensitive"] is None else entry["case_sensitive"]
    ww = settings["match_whole_words"] if entry["match_whole_words"] is None else entry["match_whole_words"]

    primary = _matching_keys(entry["keys"], text, cs, ww)
    if not primary:
        return None
    reason = f'keyword "{primary[0]}"'

    secondary = entry["secondary_keys"]
    if not secondary:
        return reason

    hits = _matching_keys(secondary, text, cs, ww)
    logic = entry["selective_logic"]
    if logic == "AND_ANY" and hits:
        return f'{reason} + "{hits[0]}"'
    if logic == "AND_ALL" and len(hits) == len(secondary):
        return f"{reason} + all secondary keys"
    if logic == "NOT_ANY" and not hits:
        return f"{reason}, no blocked keys present"
    if logic == "NOT_ALL" and len(hits) < len(secondary):
        return f"{reason}, not all blocked keys present"
    return None


def _approx_tokens(text):
    return max(1, len(text) // 4)


def entry_label(entry):
    return entry["comment"] or (entry["keys"][0] if entry["keys"] else f"Entry {entry['uid']}")


def activate(book, messages):
    """
    book: normalised book (see normalize_book)
    messages: recent chat messages, oldest first, newest last. Items can be
              strings, chat-log lists, or {"content": ...} dicts.

    Returns {"entries": [...included, in prompt order...],
             "report": [{uid, label, status, reason, ...}],
             "notes": [str]}
    """
    settings = book["settings"]
    texts = [_message_text(m) for m in messages]
    texts = [t for t in texts if t]

    def scan_text(depth):
        return "\n".join(texts[-depth:]) if depth > 0 else ""

    fired = {}   # uid -> {"entry", "reason", "score"}
    report = []
    notes = []

    for entry in book["entries"]:
        if not entry["content"].strip():
            continue
        if entry["constant"]:
            if entry["enabled"]:
                fired[entry["uid"]] = {"entry": entry, "reason": "always on (constant)"}
            continue
        depth = settings["scan_depth"] if entry["scan_depth"] is None else entry["scan_depth"]
        reason = _check_entry(entry, scan_text(depth), settings)
        if reason is None:
            continue
        if not entry["enabled"]:
            report.append({"uid": entry["uid"], "label": entry_label(entry),
                           "status": "disabled", "reason": f"{reason}, but entry is disabled"})
            continue
        fired[entry["uid"]] = {"entry": entry, "reason": reason}

    # Recursion: fired entries' content can trigger more entries
    if settings["recursive_scan"]:
        newly = list(fired.values())
        for _ in range(settings["max_recursion_steps"]):
            source = [f for f in newly if not f["entry"]["prevent_recursion"]]
            if not source:
                break
            newly = []
            for entry in book["entries"]:
                if (entry["uid"] in fired or not entry["enabled"] or entry["constant"]
                        or entry["exclude_recursion"] or not entry["content"].strip()):
                    continue
                for f in source:
                    reason = _check_entry(entry, f["entry"]["content"], settings)
                    if reason:
                        hit = {"entry": entry, "reason": f'{reason} in "{entry_label(f["entry"])}" (recursion)'}
                        fired[entry["uid"]] = hit
                        newly.append(hit)
                        break

    # Semantic fallback for entries that did not fire by keyword
    if settings["semantic_enabled"] and settings["semantic_top_k"] > 0:
        candidates = [e for e in book["entries"]
                      if e["enabled"] and e["semantic"] and not e["constant"]
                      and e["uid"] not in fired and e["content"].strip()]
        query = scan_text(settings["scan_depth"])
        if candidates and query:
            scores = semantic_scores(query, [_semantic_text(e) for e in candidates])
            if scores is None:
                notes.append("Semantic search is on, but the sentence-transformers package "
                             "is not installed (see requirements-semantic.txt).")
            else:
                ranked = sorted(zip(candidates, scores), key=lambda x: x[1], reverse=True)
                for entry, score in ranked[:settings["semantic_top_k"]]:
                    if score >= settings["semantic_threshold"]:
                        fired[entry["uid"]] = {"entry": entry, "score": round(score, 3),
                                               "reason": f"semantic match (score {score:.2f})"}

    # Budget: constants first, then by order (higher order = more important)
    ranked = sorted(fired.values(),
                    key=lambda f: (not f["entry"]["constant"], -f["entry"]["order"]))
    included = []
    used = 0
    budget = settings["token_budget"]
    for f in ranked:
        entry = f["entry"]
        tokens = _approx_tokens(entry["content"])
        row = {"uid": entry["uid"], "label": entry_label(entry), "reason": f["reason"],
               "tokens": tokens, "order": entry["order"]}
        if "score" in f:
            row["score"] = f["score"]
        if budget and used + tokens > budget:
            row["status"] = "over_budget"
        else:
            used += tokens
            row["status"] = "included"
            included.append(entry)
        report.append(row)

    included.sort(key=lambda e: e["order"])  # most important ends up closest to the chat
    order_of = {"included": 0, "over_budget": 1, "disabled": 2}
    report.sort(key=lambda r: order_of.get(r["status"], 3))
    return {"entries": included, "report": report, "notes": notes, "tokens_used": used}


def format_for_prompt(entries):
    if not entries:
        return ""
    blocks = [f"[{entry_label(e)}]\n{e['content'].strip()}" for e in entries]
    return "### World Information (Context):\n\n" + "\n\n".join(blocks)


# ---------------------------------------------------------------------------
# Optional semantic search
# ---------------------------------------------------------------------------

_semantic_model = None
_semantic_unavailable = False
_embedding_cache = {}  # sha1(text) -> embedding, so lore is only embedded once


def _semantic_text(entry):
    keys = ", ".join(entry["keys"])
    title = f"{entry['comment']}. " if entry["comment"] else ""
    return f"{title}{keys}: {entry['content']}"


def _get_semantic_model():
    global _semantic_model, _semantic_unavailable
    if _semantic_model is None and not _semantic_unavailable:
        try:
            from sentence_transformers import SentenceTransformer
            _semantic_model = SentenceTransformer(SEMANTIC_MODEL_NAME)
        except ImportError:
            _semantic_unavailable = True
    return _semantic_model


def semantic_scores(query, texts):
    """Cosine similarity of `query` to each text, or None if unavailable."""
    model = _get_semantic_model()
    if model is None:
        return None
    from sentence_transformers import util

    keys = [hashlib.sha1(t.encode("utf-8")).hexdigest() for t in texts]
    missing = [(k, t) for k, t in zip(keys, texts) if k not in _embedding_cache]
    if missing:
        vectors = model.encode([t for _, t in missing], convert_to_tensor=True)
        for (k, _), vec in zip(missing, vectors):
            _embedding_cache[k] = vec

    import torch
    corpus = torch.stack([_embedding_cache[k] for k in keys])
    query_vec = model.encode(query, convert_to_tensor=True)
    return [float(s) for s in util.cos_sim(query_vec, corpus)[0]]


# ---------------------------------------------------------------------------
# Storage helpers (Worldbook model keeps the book as a JSON file)
# ---------------------------------------------------------------------------

def load_worldbook(wb):
    data = {}
    if wb.json_file:
        try:
            with wb.json_file.open("rb") as f:
                data = json.loads(f.read().decode("utf-8"))
        except (OSError, ValueError):
            data = {}
    book = normalize_book(data)
    book["title"] = wb.title
    book["description"] = wb.description
    return book


def save_worldbook(wb, book):
    from django.core.files.base import ContentFile

    book = normalize_book(book)
    wb.title = book["title"] or wb.title
    wb.description = book["description"]
    book["title"], book["description"] = wb.title, wb.description
    content = json.dumps(book, ensure_ascii=False, indent=2)

    name = wb.json_file.name.rsplit("/", 1)[-1] if wb.json_file else f"{wb.slug}.json"
    if wb.json_file:
        wb.json_file.storage.delete(wb.json_file.name)
    wb.json_file.save(name, ContentFile(content.encode("utf-8")), save=False)
    wb.save()
    return book
