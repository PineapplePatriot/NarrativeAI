"""
🥔 Expand on the worldbook page: Bulba suggests more keywords (other names, short names, nicknames), more lore
for an entry, and entries the book is missing. With a canon work ("Based on"), it looks it up on the web first
(OpenRouter or NanoGPT); for an own world it proposes additions that fit the book, marked as invented. Nothing is saved
here: the page shows the suggestions and they pick what to add.
"""
import json
import re

from mainapp import ai_client

MAX_ENTRIES_SENT = 60
MAX_NEW = 8

RESEARCH_PROMPT = (
    "You research a fictional world for someone filling in a roleplay lorebook. Prefer the work's wikis (Fandom and "
    "other fan wikis, Wikipedia, official sites). Using the web results, give facts about what they ask: every name, "
    "title, short form and nickname people use for each thing, and two or three factual lines about it, with the "
    "point in the story each fact belongs to (mark spoilers). Say plainly when sources disagree or something isn't "
    "known. If the work can't be found, say exactly: NOT FOUND. No speculation, no fan theories as fact.")

EXPAND_PROMPT = (
    "You improve a roleplay lorebook. An entry is added to the story when one of its keywords appears in the chat. "
    "The book's language is the language of its entries; write everything in it.\n"
    "Asked for: {asked}.\n"
    "- keywords: for each entry, other names people would really use in the chat: full and short names, titles, "
    "nicknames, common misspellings, the name in the story's language. Never ordinary words that would fire all the "
    "time (\"the city\", \"magic\"). The app already catches other word endings, so don't list those.\n"
    "- lore: for an entry whose text misses something important, one to three sentences to add (plain present-tense "
    "fact, not instructions to the model; don't repeat what it says). Leave out entries that are fine.\n"
    "- new: up to {max_new} entries the book is missing that the story is likely to touch (places, groups, people "
    "other than the main character, terms). Two to five sentences each, with keywords. Don't repeat existing ones.\n"
    "{source}\n"
    "Answer with JSON only: {{\"canon\": true or false, \"entries\": {{\"<entry id>\": {{\"keys\": [...], "
    "\"add\": \"...\"}}}}, \"new\": [{{\"title\": \"...\", \"keys\": [...], \"content\": \"...\"}}]}}. "
    "Leave out what has nothing to add.")

CANON_SOURCE = ("Research about the work is below. Use only facts it supports; if something isn't there, leave it out. "
                "Set canon to true.")
OWN_SOURCE = ("This is their own world (or the work couldn't be found): there are no outside facts. Suggest only "
              "what fits what the book already says, never contradicting it, and keep inventions modest. Set canon "
              "to false.")
NO_WEB_SOURCE = ("Web search isn't available here; use what you reliably know about the work. If you don't know it "
                 "well, treat it as their own world: suggest only what fits the book and set canon to false.")


def _brief(entry):
    return {"title": entry["comment"], "keys": entry["keys"], "text": entry["content"][:800]}


def _research(user, query):
    """Web findings about `query`, or "" when the work isn't found; None when web search isn't available."""
    from users.models import ConnectionProfile
    profile, _ = ai_client.resolve(user, "bulba")
    if profile is None or profile.provider not in ConnectionProfile.HOSTED:
        return None
    message, _cost = ai_client.complete_message(
        user, "bulba", [{"role": "system", "content": RESEARCH_PROMPT}, {"role": "user", "content": query}],
        plugins=[{"id": "web", "max_results": 5}], max_tokens=1500, timeout=150)
    text = (message.get("content") or "").strip()
    sources = [((a.get("url_citation") or {}).get("url") or "") for a in message.get("annotations") or []
               if isinstance(a, dict)]
    return ("" if "NOT FOUND" in text[:200] else text[:6000]), [u for u in sources if u][:5]


def _parse(text):
    match = re.search(r"\{.*\}", text or "", re.S)
    try:
        data = json.loads(match.group(0)) if match else None
    except ValueError:
        data = None
    if not isinstance(data, dict):
        raise ai_client.AIError("Bulba's answer wasn't readable. Try again.")
    return data


def _clean_keys(keys, have):
    seen = {k.lower() for k in have}
    out = []
    for k in keys if isinstance(keys, list) else []:
        k = str(k).strip()[:60]
        if k and not k.startswith("/") and k.lower() not in seen:
            seen.add(k.lower())
            out.append(k)
    return out[:8]


def expand(user, book, what=("keys", "lore", "new"), uid=None):
    """Suggestions for the book (or for one entry, `uid`): {"origin": web | memory | invented, "sources",
    "entries": {uid: {keys, add}}, "new": [...], "note"}."""
    based_on = (book.get("based_on") or "").strip()
    entries = [e for e in book["entries"] if e["content"].strip()]
    if uid is not None:
        entries = [e for e in entries if e["uid"] == uid]
        if not entries:
            raise ValueError("Save the entry first, then expand it.")
        what = tuple(w for w in what if w != "new")
    entries = entries[:MAX_ENTRIES_SENT]

    # Research: the work (and, for one entry, that entry) on the web
    work = based_on or book.get("title") or ""
    found = sources = None
    if work:
        topic = (f"{entries[0]['comment'] or ', '.join(entries[0]['keys'][:3])} in {work}" if uid is not None
                 else f"{work}: places, factions, people and terms")
        result = _research(user, topic)
        if result is not None:
            found, sources = result
    if found is None:
        source = NO_WEB_SOURCE if based_on else OWN_SOURCE
    elif found:
        source = CANON_SOURCE + "\n\nResearch:\n" + found
    else:
        source = OWN_SOURCE

    asked = {"keys": "keywords", "lore": "lore", "new": "new"}
    prompt = EXPAND_PROMPT.format(asked=", ".join(asked[w] for w in what), max_new=MAX_NEW, source=source)
    payload = {"book": book.get("title") or "", "based_on": based_on, "about": book.get("description") or "",
               "entries": {str(e["uid"]): _brief(e) for e in entries}}
    if uid is None and len(book["entries"]) > len(entries):  # the rest, by name only, so "new" doesn't repeat them
        payload["other_entries"] = [e["comment"] or ", ".join(e["keys"][:2]) for e in book["entries"][len(entries):]]
    text = ai_client.complete(user, "bulba", [{"role": "system", "content": prompt},
                                              {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
                              timeout=180, temperature=0.4)
    data = _parse(text)

    by_uid = {str(e["uid"]): e for e in entries}
    out_entries = {}
    for key, s in (data.get("entries") or {}).items():
        e = by_uid.get(str(key))
        if e is None or not isinstance(s, dict):
            continue
        keys = _clean_keys(s.get("keys"), e["keys"]) if "keys" in what else []
        add = str(s.get("add") or "").strip()[:1200] if "lore" in what else ""
        if add and add[:80].lower() in e["content"].lower():
            add = ""
        if keys or add:
            out_entries[e["uid"]] = {"keys": keys, "add": add}

    new = []
    titles = {(e["comment"] or "").lower() for e in book["entries"]}
    for n in (data.get("new") or [])[:MAX_NEW] if "new" in what else []:
        if not isinstance(n, dict):
            continue
        title = str(n.get("title") or "").strip()[:120]
        content = str(n.get("content") or "").strip()[:2500]
        keys = _clean_keys(n.get("keys"), [])
        if title and content and keys and title.lower() not in titles:
            titles.add(title.lower())
            new.append({"title": title, "keys": keys, "content": content})

    if found:
        origin, note = "web", ""
    elif found is None and based_on and data.get("canon"):
        origin, note = "memory", "Web search needs an OpenRouter or NanoGPT connection, so these come from what Bulba knows: check them."
    else:
        origin, note = "invented", ("Not found on the web, so these are invented to fit what the book says."
                                    if found == "" else "Your own world: these are invented to fit what the book says.")
    if not (out_entries or new):
        note = (note + " " if note else "") + "Nothing to add: the book already covers it."
    return {"origin": origin, "sources": sources or [], "entries": out_entries, "new": new, "note": note}
