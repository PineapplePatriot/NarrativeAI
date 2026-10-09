"""
How far the setup has come, for the side panel: each stage with its small steps, which ones are done, which were
skipped, and roughly how many questions are left. Worked out from what happened in the session (proposals applied,
samples shown...), so it costs nothing and doesn't depend on Bulba remembering to report it.
"""

# stage: (label, what happens there, [(step, label, rough questions it takes, optional)])
STAGES = {
    "extras": ("Extras", "Voices, summaries, trackers, pictures",
               [("extras", "Pick your extras", 3, False)]),
    "taste": ("How replies read", "A short form, then A/B samples written by your model",
              [("basics", "The short form", 1, False), ("samples", "A/B samples", 3, False),
               ("noted", "Your taste noted", 1, False)]),
    "preset": ("Your preset", "Built from tested wording; one fresh sample to check it",
               [("preset_proposed", "Preset ready to look at", 1, False), ("preset", "Preset applied", 1, False)]),
    "persona": ("You in the story", "Who you are when you talk to the character",
                [("persona", "You in the story", 2, False)]),
    "character": ("Your character", "Import a card or describe one; lore and a look if you like",
                  [("character", "Character ready", 3, False), ("lore", "Lore", 1, True),
                   ("theme", "Look and music", 1, True)]),
    "story": ("Story extras", "Dice, letters, trackers that fit your story",
              [("story", "Dice and story extras", 2, False), ("trackers", "Trackers", 1, True)]),
    "done": ("Done", "A summary and where to change things later", [("done", "Summary", 0, False)]),
}
STORY_KEYS = {"game", "story_extras", "ideas"}


def _done_steps(session):
    """The steps the session shows are done."""
    applied = [p for p in session.proposals if p.get("status") == "applied"]
    kinds = {p["kind"] for p in applied}
    extras = [set((p.get("payload") or {})) - {"background"} for p in applied if p["kind"] == "extras"]
    done = set()
    if any(keys - STORY_KEYS or not keys for keys in extras):
        done.add("extras")
    if any(keys & STORY_KEYS for keys in extras):
        done.add("story")
    if any(ev.get("type") == "action" and ev.get("text") == "Sent the basics" for ev in session.events):
        done.add("basics")
    if any(ev.get("type") == "samples" for ev in session.events):
        done.add("samples")
    if len([p for p in session.preferences if p.get("status") not in ("rejected", "superseded")]) >= 3:
        done.add("noted")
    if any(p["kind"] == "preset" and p.get("status") != "replaced" for p in session.proposals):
        done.add("preset_proposed")
    if "preset" in kinds:
        done |= {"preset", "preset_proposed"}
    if "persona" in kinds:
        done.add("persona")
    if "character" in kinds or session.focus_id:
        done.add("character")
    if kinds & {"lorebook", "lore_edit"}:
        done.add("lore")
    if "theme" in kinds:
        done.add("theme")
    if "trackers" in kinds:
        done.add("trackers")
    if session.stage == "done":
        done.add("done")
    return done


def progress(session, order):
    """The panel's view of the setup. `order` is the list of stages (agent.STAGES)."""
    done = _done_steps(session)
    current = order.index(session.stage) if session.stage in order else 0
    stages, left = [], 0
    for i, stage in enumerate(order):
        label, hint, steps = STAGES[stage]
        shown = [{"label": s_label, "done": key in done, "optional": optional}
                 for key, s_label, _, optional in steps]
        if i < current:
            # Moved past without doing any of it: they (or Bulba) skipped it
            status = "done" if any(key in done for key, *_ in steps) else "skipped"
        elif i == current:
            status = "done" if stage == "done" else "current"
        else:
            status = "todo"
        if status in ("current", "todo"):
            left += sum(q for key, _, q, optional in steps if key not in done and not optional)
        stages.append({"id": stage, "label": label, "hint": hint, "status": status, "steps": shown})
    return {"stages": stages, "step": current + 1, "of": len(order), "questions_left": left,
            "can_skip": session.stage != "done"}
