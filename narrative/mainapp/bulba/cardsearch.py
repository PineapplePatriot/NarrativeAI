"""
🔎 Cards from the big card sites, found and brought in by Bulba (in any Bulba chat).

- Chub (chub.ai / characterhub.org): search by words (find_card), or a link. A card comes in as its PNG (picture
  and card together) when the site gives one, else as the card's text. Its lorebook comes with it.
- Janitor AI (janitorai.com): a link only (it has no public search). Many bots hide their definitions: then
  there's nothing to bring in, and Bulba says so (they can paste the text instead).
- RisuRealm (realm.risuai.net): its rules ask for downloads from the person's own browser, not a server, so Bulba
  asks them to press Download there and send the file with 📎 (the usual card import).

Adult cards only when mature content is switched on (mainapp/mature.py). One request per search or card, made
when the person asks; the sites' own endpoints may change, so every failure ends in a plain sentence and the
other ways in (a link, a file, pasted text).
"""
import json
import re

import requests

from mainapp.bulba import lore

CHUB_API = "https://api.chub.ai"
JANITOR = "https://janitorai.com"
HEADERS = {"User-Agent": "NarrativeAI card import", "Accept": "application/json"}
TIMEOUT = 20


class CardSiteError(ValueError):
    pass


def _mature(user):
    from mainapp import mature
    return mature.wanted(user)


def _get(url, **params):
    try:
        resp = requests.get(url, params=params or None, headers=HEADERS, timeout=TIMEOUT)
    except requests.RequestException:
        raise CardSiteError("The card site didn't answer. Try again in a moment, or send the card as a file.")
    if resp.status_code in (401, 403):
        raise CardSiteError("The card site turned the request away (it may need you to be logged in there). "
                            "Download the card there and send it with 📎, or paste its text.")
    if resp.status_code == 404:
        raise CardSiteError("The card site doesn't know that card (check the link).")
    if resp.status_code >= 400:
        raise CardSiteError(f"The card site returned an error ({resp.status_code}). Try again later, or send the file.")
    return resp


# ---------------------------------------------------------------------------
# Chub
# ---------------------------------------------------------------------------

def _chub_nodes(data):
    """The list of cards in a Chub answer, whichever shape it comes in."""
    if isinstance(data, dict):
        for key in ("nodes", "data", "characters", "results"):
            v = data.get(key)
            if isinstance(v, list):
                return v
            if isinstance(v, dict):
                inner = _chub_nodes(v)
                if inner:
                    return inner
    return data if isinstance(data, list) else []


def search_chub(user, query, limit=8):
    """[{source, id, name, tagline, tokens, stars, image, nsfw, url}] for words like "dottore genshin"."""
    query = str(query or "").strip()[:120]
    if not query:
        raise CardSiteError("What should I look for?")
    adult = _mature(user)
    resp = _get(f"{CHUB_API}/search", search=query, first=limit * 2, page=1, sort="download_count", asc="false",
                nsfw="true" if adult else "false", nsfl="false", include_forks="true", venus="false",
                require_images="false", require_custom_prompt="false")
    try:
        nodes = _chub_nodes(resp.json())
    except ValueError:
        nodes = []
    out = []
    for n in nodes:
        if not isinstance(n, dict) or not n.get("fullPath"):
            continue
        nsfw = bool(n.get("nsfw") or n.get("nsfw_image") or "NSFW" in (n.get("topics") or []))
        if nsfw and not adult:
            continue
        out.append({"source": "chub", "id": n["fullPath"], "name": str(n.get("name") or "")[:100],
                    "tagline": str(n.get("tagline") or n.get("description") or "")[:200],
                    "tokens": int(n.get("nTokens") or 0), "stars": int(n.get("starCount") or 0),
                    "image": str(n.get("avatar_url") or n.get("max_res_url") or ""), "nsfw": nsfw,
                    "url": f"https://chub.ai/characters/{n['fullPath']}"})
        if len(out) >= limit:
            break
    return out


def _chub_card(user, path):
    """(bytes, filename) of a Chub card: its PNG when there is one (picture and card together), else its text."""
    resp = _get(f"{CHUB_API}/api/characters/{path}", full="true")
    try:
        node = (resp.json() or {}).get("node") or {}
    except ValueError:
        node = {}
    if not node:
        raise CardSiteError("Chub sent back something that isn't a card.")
    nsfw = bool(node.get("nsfw") or node.get("nsfw_image") or "NSFW" in (node.get("topics") or []))
    if nsfw and not _mature(user):
        raise CardSiteError("That card is marked as adult. Switch mature content on first (pen menu → This chat → "
                            "🔞 Mature content) if you want it.")
    for key in ("max_res_url", "avatar_url"):
        png_url = node.get(key) or ""
        if png_url.lower().split("?")[0].endswith(".png") and "chara_card" in png_url:
            try:
                png = requests.get(png_url, headers=HEADERS, timeout=TIMEOUT)
                if png.ok and png.content[:8] == b"\x89PNG\r\n\x1a\n":
                    return png.content, f"{node.get('name') or 'card'}.png"
            except requests.RequestException:
                pass
    d = node.get("definition") or {}
    card = {"spec": "chara_card_v2", "spec_version": "2.0", "data": {
        "name": d.get("name") or node.get("name") or "Character",
        "description": d.get("personality") or d.get("description") or "",
        "personality": d.get("tavern_personality") or "",
        "scenario": d.get("scenario") or "",
        "first_mes": d.get("first_message") or "",
        "mes_example": d.get("example_dialogs") or "",
        "alternate_greetings": d.get("alternate_greetings") or [],
        "system_prompt": d.get("system_prompt") or "",
        "post_history_instructions": d.get("post_history_instructions") or "",
        "creator_notes": node.get("description") or "",
        "creator": (path.split("/") or [""])[0],
        "tags": node.get("topics") or [],
        **({"character_book": d["embedded_lorebook"]} if isinstance(d.get("embedded_lorebook"), dict) else {}),
    }}
    if not (card["data"]["description"] or card["data"]["first_mes"]):
        raise CardSiteError("That Chub card came back empty.")
    return json.dumps(card, ensure_ascii=False).encode("utf-8"), f"{card['data']['name']}.json"


# ---------------------------------------------------------------------------
# Janitor
# ---------------------------------------------------------------------------

def _janitor_card(user, char_id):
    resp = _get(f"{JANITOR}/hampter/characters/{char_id}")
    try:
        c = resp.json() or {}
    except ValueError:
        raise CardSiteError("Janitor answered with a page instead of the card (it may be blocking automated "
                            "requests). Copy the card's text there and paste it to me instead.")
    if (c.get("is_nsfw") or c.get("nsfw")) and not _mature(user):
        raise CardSiteError("That card is marked as adult. Switch mature content on first if you want it.")
    personality = c.get("personality") or ""
    if c.get("showdefinition") is False or not (personality or c.get("first_message")):
        raise CardSiteError("Its creator hid this card's definition on Janitor, so there's nothing to bring in. "
                            "If you have the text some other way, paste it and I'll set it up.")
    card = {"spec": "chara_card_v2", "spec_version": "2.0", "data": {
        "name": c.get("chat_name") or c.get("name") or "Character",
        "description": personality, "personality": "", "scenario": c.get("scenario") or "",
        "first_mes": c.get("first_message") or "", "mes_example": c.get("example_dialogs") or "",
        "creator_notes": re.sub(r"<[^>]+>", "", str(c.get("description") or ""))[:4000],
        "creator": str((c.get("creator_name") or "")), "tags": [t.get("name") for t in c.get("tags") or [] if isinstance(t, dict)],
    }}
    return json.dumps(card, ensure_ascii=False).encode("utf-8"), f"{card['data']['name']}.json"


# ---------------------------------------------------------------------------
# Links, and bringing a card in
# ---------------------------------------------------------------------------

def parse_link(text):
    """(site, id) from a link or a Chub path, or (None, None)."""
    text = str(text or "").strip()
    m = re.search(r"(?:chub\.ai|characterhub\.org)/characters/([\w.-]+/[\w.-]+)", text)
    if m:
        return "chub", m.group(1)
    m = re.search(r"janitorai\.com/characters/([0-9a-f-]{36})", text)
    if m:
        return "janitor", m.group(1)
    if "realm.risuai.net" in text:
        return "risu", text
    if re.fullmatch(r"[\w.-]+/[\w.-]+", text):
        return "chub", text
    return None, None


def bring_in(session, where):
    """A card from a link (or a Chub result's id) into a character, recorded like an import (Undo works).
    Returns (character, proposal)."""
    site, ident = parse_link(where)
    if site == "risu":
        raise CardSiteError("RisuRealm asks for cards to be downloaded from your own browser: open the card there, "
                            "press Download (PNG), and send me the file with 📎.")
    if site == "chub":
        raw, name = _chub_card(session.user, ident)
    elif site == "janitor":
        raw, name = _janitor_card(session.user, ident)
    else:
        raise CardSiteError("I can bring in Chub and Janitor cards by their link (or a Chub search result). "
                            "For anything else, send the card file with 📎.")

    class _File:
        def __init__(self, data, filename):
            self._d, self.name = data, filename

        def read(self):
            return self._d
    try:
        character, p = lore.import_card(session, _File(raw, name))
    except ValueError as e:
        raise CardSiteError(f"The card didn't read as a character card: {e}")
    p["title"] = f"Character: {character.name} (from {'Chub' if site == 'chub' else 'Janitor'})"
    p["summary"] = [f"Brought in from {where}. Bulba can suggest changes; nothing else was touched."]
    return character, p


def tool_find_card(session, args):
    try:
        found = search_chub(session.user, args.get("query"))
    except CardSiteError as e:
        return {"error": str(e) + " (A Chub or Janitor link works too.)"}, []
    if not found:
        return {"results": [], "note": "Nothing found on Chub for that. Try other words, or ask for a link."
                + ("" if _mature(session.user) else " Adult cards are hidden while mature content is off.")}, []
    return {"results": found, "note": "Show them the best few (name, a line, tokens) with offer_choices; "
                                      "bring_in_card with the one they pick."}, []


def tool_bring_in_card(session, args):
    try:
        character, p = bring_in(session, args.get("where") or args.get("id") or "")
    except CardSiteError as e:
        return {"error": str(e)}, []
    return {"done": True, "character": character.name, "slug": character.slug,
            "has_lorebook": bool(character.worldbook_id),
            "next": "Offer, with offer_choices: use it as it is, change it (a Modern AU, shorter, a different "
                    "scenario…: propose the edits), or set it up now (its lorebook if it has one, and a persona: "
                    "just for this story or their usual one)."}, [{"type": "proposal", "id": p["id"]}]


def tool_defs(fn, STR):
    return [
        fn("find_card", "Search Chub (the biggest card site) for character cards by words (a name, a fandom, a "
           "trope). Adult cards only show when mature content is on. Janitor has no search: ask for a link.",
           {"query": STR}, ["query"]),
        fn("bring_in_card", "Bring a card in from a Chub or Janitor link (or a Chub result's id) as a new "
           "character, with its picture and lorebook when it has them. Undo removes it.",
           {"where": {"type": "string", "description": "The link, or a Chub result's id (creator/card)"}}, ["where"]),
    ]


HANDLERS = {"find_card": tool_find_card, "bring_in_card": tool_bring_in_card}
