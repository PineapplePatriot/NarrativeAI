"""What's this? Bulba explains one thing someone clicked on a page (one small call on Bulba's model)."""
from pathlib import Path

from mainapp import ai_client

APP_MAP = Path(__file__).resolve().parent.parent / "data" / "bulba" / "guides" / "app.md"

PROMPT = (
    "You are Bulba, a dry, friendly potato who helps people use a roleplay app. Someone pressed \"What's this?\" "
    "and clicked something on a page, or asked about it. Explain it in two to four short, plain sentences: what it "
    "is, what it's for, and when they'd use it. Use the map below; if the thing isn't in it, say what it most "
    "likely does from its label and the page, and say you're not certain. No headings, no lists, no 'ensure', "
    "'immersive', 'seamless'. Keep button names exactly as the app shows them, in English.\n\n")
LANGS = {"uk": "Answer in Ukrainian.", "en": "Answer in English."}


def explain(user, data):
    """The answer as plain text. Raises ai_client.AIError when the model can't be reached."""
    def field(key, limit):
        return " ".join(str(data.get(key) or "").split())[:limit]

    lines = [f"Page: {field('page_title', 120)} ({field('page', 200)})",
             f"Section: {field('heading', 160)}" if field("heading", 160) else "",
             f"What they clicked: <{field('tag', 20) or 'element'}> {field('label', 300)!r}",
             f"Its tooltip: {field('title', 300)}" if field("title", 300) else "",
             f"Its placeholder: {field('placeholder', 200)}" if field("placeholder", 200) else "",
             f"The app's own short help for it: {field('known', 600)}" if field("known", 600) else "",
             f"Their question: {field('question', 400)}" if field("question", 400) else
             "Their question: what is this, and when would I use it?"]
    system = PROMPT + LANGS.get(data.get("lang"), LANGS["en"]) + "\n\n" + APP_MAP.read_text(encoding="utf-8")
    text = ai_client.complete(user, "bulba", [{"role": "system", "content": system},
                                              {"role": "user", "content": "\n".join(filter(None, lines))}],
                              max_tokens=1500, temperature=0.4)
    text = (text or "").strip()
    if not text:
        raise ai_client.AIError("Bulba drew a blank. Try again.")
    return text[:1500]
