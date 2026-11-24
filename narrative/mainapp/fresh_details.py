"""
🔁 Fresh details: some models (MiMo above all) latch onto one concrete detail and bring it back reply after reply
(the street lamp from the first message, a lorebook's rain, "the smell of ozone"). This finds the details that keep
coming back in the recent replies, for free (no AI), and the reply request gets a short note to leave them out this
time unless the scene really turns on them.

Words only count when they keep returning in the character's replies and the person isn't talking about them
themselves (then it's the topic, not a tic). Names never count.
"""
import re

WINDOW = 5        # the last replies looked at
TIMES = 3         # a detail in this many of them is a tic
MOST = 4          # details named in one note

WORD = re.compile(r"[^\W\d_][^\W\d_'’-]{3,}", re.U)

# Common words that are never "a detail" (English, Ukrainian, Russian): function words and everyday verbs
STOP = set("""
about above after again against almost along already also although always among another anyone anything around
away back because been before behind being below between both came cannot could didn does doing done down during
each either else enough even ever every eyes face from gave give gives going gone good got have having head hear
heard here hers herself hand hands himself into itself just keep kept know knew last least left less like little
long look looked looking looks made make makes many maybe might mind more most much must myself near need never
next nothing once only onto other others ours over perhaps quite rather really right said same says seem seemed
seems should since some something still such sure take taken tell than that their them themselves then there these
they thing things think this those though thought through time told toward towards turn turned under until upon
very voice want wanted wants well went were what when where whether which while whom whose will with within
without word words would year years your yours yourself again moment moments slightly softly quietly little
still just even back away down said asks asked says tone gaze glance smile smiles smiled nods nodded
який яка яке які його її їхній цей ця це ці той та те ті тут там коли якщо тому того тобі тебе мене мені себе
собі вона воно вони його йому нього неї ними нами вами було були буде будуть може можна треба тільки вже ще
дуже трохи майже навіть просто лише саме також теж тоді потім знову зараз завжди ніколи щось нічого хтось
який какой какая какое какие этот эта это эти тот та те там тут когда если только уже ещё очень чуть почти
даже просто тоже потом снова сейчас всегда никогда что-то ничего кто-то было были будет может нужно себя тебя
""".split())


def _words(text):
    return [w.lower().strip("'’-") for w in WORD.findall(text or "")]


def _root(word):
    """A rough root, so forms of one word count together (ліхтар / ліхтарем, lamp / lamps)."""
    word = re.sub(r"['’]s$", "", word)
    if len(word) > 6:
        return word[:6]
    return word[:-1] if len(word) > 4 and word.endswith("s") and not word.endswith("ss") else word


def _units(text, names, seen):
    """The detail-like word roots and two-word pairs of a text (as sets): no common words, no names."""
    words = []
    for w in _words(text):
        if w in STOP or w in names or _root(w) in names:
            continue
        seen.setdefault(_root(w), w)  # root → the form first seen (shown in the note)
        words.append(_root(w))
    pairs = {f"{a} {b}" for a, b in zip(words, words[1:])}
    return set(words), pairs


def _shown(unit, seen):
    return " ".join(seen.get(p, p) for p in unit.split())


def repeated(replies, theirs=(), names=()):
    """The details that keep coming back: a list of words or two-word pairs found in TIMES of the last WINDOW
    `replies` (texts, oldest first), not used by the person in `theirs` (their recent messages), never a name.
    A pair ("street lamp") stands for its own words."""
    names = {w.lower() for n in names for w in _words(n)} | {_root(w.lower()) for n in names for w in _words(n)}
    recent = [r for r in replies if r and r.strip()][-WINDOW:]
    if len(recent) < TIMES:
        return []
    said, seen = set(), {}
    for t in theirs:
        w, p = _units(t, names, {})
        said |= w | p
    counts = {}
    for r in recent:
        w, p = _units(r, names, seen)
        for u in w | p:
            counts[u] = counts.get(u, 0) + 1
    hot = {u for u, n in counts.items() if n >= TIMES and u not in said}
    if not hot:
        return []
    newest = set().union(*_units(recent[-1], names, seen))
    pairs = sorted((u for u in hot if " " in u), key=lambda u: (-counts[u], u))
    out, covered = [], set()
    for p in pairs:  # pairs first: "street lamp" rather than "street" and "lamp"
        if p in newest and not set(p.split()) <= covered:
            out.append(p)
            covered |= set(p.split())
    for w in sorted((u for u in hot if " " not in u), key=lambda u: (-counts[u], u)):
        if w in newest and w not in covered:
            out.append(w)
    return [_shown(u, seen) for u in out[:MOST]]


def note(details):
    if not details:
        return ""
    listed = ", ".join(f"“{d}”" for d in details)
    return (f"[Fresh details: the recent replies keep coming back to {listed}. Leave them out of this reply unless "
            "the scene truly turns on them now; notice something else, or nothing.]")


def add_before_note(messages, text):
    """The request with `text` in its last turn, just before a director's note (which stays last), else at the end."""
    if not text:
        return messages
    messages = [dict(m) for m in messages]
    last = messages[-1] if messages else None
    if not last or last.get("role") != "user" or not isinstance(last.get("content"), str):
        return messages + [{"role": "user", "content": text}]
    body = last["content"]
    at = body.rfind("[Director's note for this reply")
    last["content"] = (body[:at] + text + "\n\n" + body[at:]) if at >= 0 else (body.rstrip() + "\n\n" + text)
    return messages
