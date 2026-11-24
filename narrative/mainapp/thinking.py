"""
Thinking written inside the reply: some presets have the model open its reply with <thinking> ... </thinking>
(Realistic Frankenstein's pico setup) or <think> ... </think> (some open models). SillyTavern folds that away
with its reasoning parser; here it goes into the same "Thoughts" box as thinking a model sends separately.

Only a block at the very start of the reply counts, so a tag mentioned later in the story is left alone.
"""
import re

TAGS = ("thinking", "think", "reasoning")
OPENING = re.compile(r"^\s*<(" + "|".join(TAGS) + r")>", re.I)


def split(text):
    """(thoughts, reply) for a finished reply."""
    m = OPENING.match(text or "")
    if not m:
        return "", text
    close = re.search(r"</" + m.group(1) + r">", text[m.end():], re.I)
    if not close:  # never closed: all of it was thinking (the reply got cut off)
        return text[m.end():].strip(), ""
    return text[m.end():m.end() + close.start()].strip(), text[m.end() + close.end():].lstrip()


class Splitter:
    """The same while streaming: feed() pieces, get back ("thinking" | "text", piece) parts."""

    def __init__(self):
        self.state, self.buf, self.tag = "start", "", None

    def feed(self, piece):
        self.buf += piece
        out = []
        while self.buf:
            if self.state == "start":
                stripped = self.buf.lstrip()
                m = OPENING.match(self.buf)
                if m:
                    self.tag, self.state, self.buf = m.group(1), "inside", self.buf[m.end():]
                    continue
                if not stripped or any(f"<{t}>".startswith(stripped.lower()) for t in TAGS):
                    return out  # could still become an opening tag: wait for more
                self.state = "after"
                continue
            if self.state == "inside":
                close = f"</{self.tag}>"
                i = self.buf.lower().find(close.lower())
                if i >= 0:
                    if i:
                        out.append(("thinking", self.buf[:i]))
                    self.buf, self.state = self.buf[i + len(close):].lstrip(), "after_think"
                    continue
                keep = next((k for k in range(min(len(close) - 1, len(self.buf)), 0, -1)
                             if close.lower().startswith(self.buf[-k:].lower())), 0)  # a closing tag split in two
                if len(self.buf) > keep:
                    out.append(("thinking", self.buf[:len(self.buf) - keep]))
                    self.buf = self.buf[len(self.buf) - keep:]
                return out
            if self.state == "after_think":  # drop the blank lines between the thinking and the reply
                self.buf = self.buf.lstrip()
                if not self.buf:
                    return out
                self.state = "after"
            out.append(("text", self.buf))
            self.buf = ""
        return out

    def finish(self):
        """Whatever is still held back when the reply ends."""
        rest, self.buf = self.buf, ""
        if not rest:
            return []
        return [("thinking" if self.state == "inside" else "text", rest)]


# MiMo (Xiaomi) thinks in one of two bad ways unless told how: not at all, or an essay that spends the whole
# reply budget and leaves no story. With its thinking on, every story request ends with this short leash (our own
# wording, after the idea in Realistic Frankenstein 2.2.1's MiMo 2.6 "thinking leash"), and the reply budget gets
# room for the thinking on top.
LEASH = ("[How to think before this reply: one short forward pass, then write. Plan in at most eight numbered "
         "fragments, one line each: what just happened and what each person present wants now; what they do next; "
         "anything to keep straight (names, places, who knows what, promises, the time); the reply's beats in order. "
         "Fragments only: no sentences of the reply, no re-reading, no 'wait' or 'let me reconsider', no second pass. "
         "After the last fragment, stop thinking and write the whole reply. A turn with thinking and no reply is a "
         "failure.]")
LEASH_ROOM = 3000  # tokens of thinking on top of the reply length


def needs_leash(model, level):
    """MiMo with its thinking on (its default)."""
    return bool(model) and ("mimo" in model.lower() or "xiaomi" in model.lower()) and level != "off"


def without_thinking(model, params):
    """Params for one more try with thinking off, after a reply that was all thinking and no text (MiMo now and
    then thinks through its whole budget). None when the model can't switch thinking off: then more room instead."""
    from mainapp import model_profiles
    choices = ((model_profiles.for_model(model) or {}).get("reasoning") or {}).get("choices") or {}
    params = dict(params or {})
    if "off" in choices:
        params["reasoning"] = {"enabled": False}
        return params
    params["max_tokens"] = int(params.get("max_tokens") or 1200) + LEASH_ROOM
    return params


def leash(messages, params):
    """The request with LEASH at the end of its last turn (before a director's note, which stays last) and the
    reply budget raised so the thinking can't eat the story."""
    messages = [dict(m) for m in messages]
    last = messages[-1] if messages else None
    if last and last.get("role") == "user" and isinstance(last.get("content"), str):
        text = last["content"]
        at = text.rfind("[Director's note for this reply")
        last["content"] = (text[:at] + LEASH + "\n\n" + text[at:]) if at >= 0 else (text.rstrip() + "\n\n" + LEASH)
    else:
        messages.append({"role": "user", "content": LEASH})
    params = dict(params or {})
    if params.get("max_tokens"):
        params["max_tokens"] = int(params["max_tokens"]) + LEASH_ROOM
    return messages, params
