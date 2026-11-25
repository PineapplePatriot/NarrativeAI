"""
Bulba's check of a drawn picture, and "draw, check, redraw once if it's wrong".

Image models still slip: a third arm, merged hands, six fingers, a face that isn't the reference's, people in a
picture of an empty room. After a picture is drawn, Bulba looks at it (with the reference pictures when there are
any) and lists what's wrong in plain sentences. When something is, the picture is drawn once more and the one
with fewer problems is kept. The check is a text call with pictures attached; only the redraw costs a picture.

Kinds: "sprite" (one person, knees up, an outfit), "scene" (an illustration of named people), "place" (a backdrop
with nobody in it), "photo" (a phone photo of a character).
"""
import logging

from mainapp import ai_client, messenger

log = logging.getLogger(__name__)

CHECKLISTS = {
    "sprite": ("It must show ONE person from the knees up, standing with both arms at the sides, wearing: {outfit}. "
               "Leave out of the outfit check anything that would be below the knees."),
    "scene": ("It must show exactly these people: {people}. Nobody else except people in the far background. "
              "What happens: {what}"),
    "place": ("It must show this place with NOBODY in it: {what}"),
    "photo": ("It is a phone photo of {people}. What it shows: {what}"),
}

PROMPT = (
    "{refs_line}The LAST picture is a new drawing. {checklist}\n"
    "Check only the LAST picture, carefully, and list what is wrong with it. Look for: any person with more than two "
    "arms, more than two hands or legs, limbs that merge or come from nowhere, wrong numbers of fingers, a face that "
    "doesn't match its reference, people who shouldn't be there, and anything in the description above that is "
    "missing or plainly different.\n"
    "Return ONLY JSON: {{\"problems\": [\"one short plain sentence per problem\"]}}. An empty list if it's right. "
    "Don't list matters of taste or style."
)


def check(user, kind, drawn, refs=(), outfit="", people="", what=""):
    """{"ok": True/False/None, "issues": [...]}: None when Bulba couldn't look at it."""
    from mainapp.bulba import vision
    refs = list(refs or [])[:3]
    try:
        model, _ = vision.looker(user)
        refs_line = (f"The first {'picture is' if len(refs) == 1 else f'{len(refs)} pictures are'} references for "
                     "how the people look. " if refs else "")
        text = PROMPT.format(refs_line=refs_line, checklist=CHECKLISTS[kind].format(
            outfit=outfit or "as in the reference", people=people or "the person in the reference", what=what or ""))
        content = [{"type": "text", "text": text}]
        for raw, _mime in [*refs, drawn]:
            data_url, _ = vision.prepare(raw)
            content.append({"type": "image_url", "image_url": {"url": data_url}})
        answer = ai_client.complete(user, "bulba", [{"role": "user", "content": content}], model=model,
                                    max_tokens=2000, temperature=0.1)
    except (ValueError, ai_client.AIError) as exc:
        log.info("picture check skipped: %s", exc)
        return {"ok": None, "issues": ["Bulba couldn't look at this picture to check it."]}
    raw = messenger._read_json(answer or "")
    if not isinstance(raw.get("problems"), list):
        return {"ok": None, "issues": ["Bulba couldn't read this picture to check it."]}
    issues = [" ".join(str(p).split())[:200] for p in raw["problems"] if str(p).strip()][:6]
    return {"ok": not issues, "issues": issues}


def draw_checked(user, prompt, references=None, kind="scene", outfit="", people="", what="", checker=None, draw=None):
    """Draw, have Bulba check it, and draw once more if something is wrong; keep the picture with fewer problems.

    `checker(drawn) -> review` replaces the generic check (looks use their own, which counts arms and hands).
    Returns (picture bytes, total cost, review), where review also says whether it was redrawn.
    """
    from django.conf import settings
    refs = list(references or [])
    draw = draw or (lambda p, r: messenger.make_picture(user, p, references=r))
    if not getattr(settings, "PICTURE_CHECKS", True):
        data, cost = draw(prompt, references)
        return data, float(cost or 0.0), {"ok": None, "issues": [], "redrawn": False}
    look = checker or (lambda drawn: check(user, kind, drawn, refs, outfit=outfit, people=people, what=what))
    data, cost = draw(prompt, references)
    cost = float(cost or 0.0)
    result = look((data, "image/png"))
    if result.get("ok") is not False:
        return data, cost, {**result, "redrawn": False}
    try:
        again, spent = draw(prompt, references)
    except ai_client.AIError:
        return data, cost, {**result, "redrawn": False}
    cost += float(spent or 0.0)
    second = look((again, "image/png"))
    if second.get("ok") is True or len(second.get("issues") or []) < len(result.get("issues") or []):
        return again, cost, {**second, "redrawn": True}
    return data, cost, {**result, "redrawn": True}
