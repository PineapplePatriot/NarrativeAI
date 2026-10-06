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
