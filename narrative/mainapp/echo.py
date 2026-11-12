"""
Cutting a repeat of their message out of a reply (no AI call). Some models (MiMo above all) open, or pad, a reply
with the user's own message copied word for word. The reply reminder forbids it; this is the backstop.

- A run of RUN or more words in a row that also stands in their last message counts as copied. "I"/"you" and the
  like count as the same word, since the copy often swaps the person ("I step closer" → "You step closer").
- A quoted line of theirs (QUOTE+ words) repeated exactly counts too, however short.
- A sentence that's mostly copied (SHARE of its words) is cut whole; a sentence that only borrows a phrase stays.
- Nothing is cut that would break the reply's markup (story-extra markers, designed objects, an unclosed colour
  tag), and nothing when the cut would leave less than KEEP of the reply: then the reply is mostly the copy, and
  cutting would leave scraps.
The cut is kept like a polish (the original stays, Show original / Undo work), see views and chats.with_polish.
"""
import re

RUN = 6
QUOTE = 3
SHARE = .6
KEEP = .35
MIN_LEFT = 25            # words that must remain
HABIT = "echoing_user"   # Bulba Watch's label for the same slip
WORD = re.compile(r"[^\W_]+(?:['’][^\W_]+)*", re.UNICODE)
QUOTED = re.compile(r"[\"“«]([^\"”»\n]{2,400})[\"”»]")
SENTENCE = re.compile(r"[^.!?…\n]*(?:[.!?…]+[\"”»*_)\]]*|\n|$)")
SAME_PERSON = {w: "·p" for w in ("i", "me", "my", "mine", "myself", "you", "your", "yours", "yourself",
                                  "я", "мене", "мені", "мій", "моя", "моє", "мої", "ти", "тебе", "тобі", "твій", "твоя",
                                  "твоє", "твої")}
TAG = re.compile(r"<(/?)([a-z]+)(?::[a-z]+)?>", re.I)


def _norm(w):
    w = w.lower().replace("’", "'")
    return SAME_PERSON.get(w, w)


def _words(text):
    return [(_norm(m.group(0)), m.start(), m.end()) for m in WORD.finditer(text or "")]


def _balanced(segment):
    count = {}
    for close, name in TAG.findall(segment):
        count[name.lower()] = count.get(name.lower(), 0) + (-1 if close else 1)
    return all(v == 0 for v in count.values())


def cut(reply, theirs):
    """(text without the copied sentences, [{"before": sentence, "after": "", "habit": HABIT}]); nothing to cut → (reply, [])."""
    if not reply or not theirs or "```" in reply:
        return reply, []
    mine = [w for w, _, _ in _words(theirs)]
    if len(mine) < QUOTE:
        return reply, []
    grams = {tuple(mine[i:i + RUN]) for i in range(len(mine) - RUN + 1)}
    words = _words(reply)
    norm = [w for w, _, _ in words]
    copied = [False] * len(words)
    for i in range(len(words) - RUN + 1):
        if tuple(norm[i:i + RUN]) in grams:
            for j in range(i, i + RUN):
                copied[j] = True
    for q in QUOTED.finditer(theirs):  # their spoken lines, repeated exactly
        line = [w for w, _, _ in _words(q.group(1))]
        if len(line) < QUOTE:
            continue
        n = len(line)
        for i in range(len(norm) - n + 1):
            if norm[i:i + n] == line:
                for j in range(i, i + n):
                    copied[j] = True
    if not any(copied):
        return reply, []

    drop = []  # (start, end) of sentences to cut
    for m in SENTENCE.finditer(reply):
        start, end = m.span()
        seg = reply[start:end]
        if not seg.strip():
            continue
        inside = [k for k, (_, s, e) in enumerate(words) if s >= start and e <= end]
        if not inside or "[[extra" in seg or not _balanced(seg):
            continue
        share = sum(copied[k] for k in inside) / len(inside)
        if share >= SHARE and (len(inside) >= 4 or all(copied[k] for k in inside)):
            drop.append((start, end))
    if not drop:
        return reply, []
    left = len(words) - sum(1 for _, s, e in words if any(a <= s and e <= b for a, b in drop))
    if left < MIN_LEFT or left < KEEP * len(words):
        return reply, []

    out, fixes, at = [], [], 0
    for a, b in drop:
        out.append(reply[at:a] if not at else reply[at:a].lstrip(" \t"))  # no stray space where a sentence went
        fixes.append({"before": reply[a:b].strip(), "after": "", "habit": HABIT})
        at = b
    out.append(reply[at:].lstrip(" \t"))
    text = "".join(out)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip(), fixes
