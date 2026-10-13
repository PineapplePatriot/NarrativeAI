"""
Free recall: in a long chat, old messages that fell out of the AI's context can come back when the current scene
brings them up again (no AI call, just word matching).

- Only messages already left out to fit the context size are candidates.
- Words come from the newest two messages; a word counts only when it's rare in the chat: anything that shows up in
  a big share of the messages (a name said all the time, a running in-joke, a setting's own term) carries nothing.
- A message qualifies with two such words in common, or one very rare one (seen at most twice in the whole chat).
- Of the ones that qualify, the newest few come back (LIMIT), as "Earlier in the story", under the summary.
"""
import math
import re

LIMIT = 3
COMMON = 0.3        # a word in more than this share of the messages is too common to mean anything
CLIP = 700          # characters of each recalled message
WORD = re.compile(r"[^\W\d_]{4,}", re.UNICODE)
STOP = set("""
that this with from they them their there then than what when where which while will would could should about
after again also been before being both each even ever into just like more most much must never once only other
over same some such sure take than that these those through under very want well were your yours have here
""".split())


def words(text):
    return {w for w in (m.group(0).lower() for m in WORD.finditer(str(text or ""))) if w not in STOP}


def pick(history, dropped, limit=LIMIT):
    """Indexes (into `history`, oldest first) of the left-out messages to bring back; [] when none."""
    if not dropped or len(history) < 4:
        return []
    texts = [h["content"] for h in history]
    bags = [words(t) for t in texts]
    n = len(bags)
    df = {}
    for bag in bags:
        for w in bag:
            df[w] = df.get(w, 0) + 1
    query = set().union(*bags[-2:])
    useful = {w: math.log(n / df[w]) for w in query if df[w] / n <= COMMON and df[w] < n}
    if not useful:
        return []
    chosen = []
    for i in range(min(dropped, n - 2)):
        common = useful.keys() & bags[i]
        if len(common) >= 2 or any(df[w] <= 2 for w in common):
            chosen.append(i)
    return chosen[-limit:]  # the newest of them


def block(history, indexes, names):
    """The text that goes under the summary."""
    if not indexes:
        return ""
    lines = ["Earlier in the story (older messages the current scene brings up again):"]
    for i in indexes:
        who = names.get("user") if history[i]["role"] == "user" else names.get("char")
        text = str(history[i]["content"])
        lines.append(f"- {who}: {text if len(text) <= CLIP else text[:CLIP].rsplit(' ', 1)[0] + ' …'}")
    return "\n".join(lines)


def assemble_with_recall(assemble, preset, slots, history, names, *args, **kwargs):
    """presets.assemble, plus recall when it had to leave messages out. Returns (built, recalled texts)."""
    built = assemble(preset, slots, history, names, *args, **kwargs)
    indexes = pick(history, built.get("dropped") or 0)
    if not indexes:
        return built, []
    extra = block(history, indexes, names)
    slots = dict(slots)
    slots["summary"] = (slots.get("summary", "") + "\n\n" + extra).strip()
    rebuilt = assemble(preset, slots, history, names, *args, **kwargs)
    who = lambda i: names.get("user") if history[i]["role"] == "user" else names.get("char")
    return rebuilt, [{"who": who(i), "text": str(history[i]["content"])[:CLIP]} for i in indexes]
