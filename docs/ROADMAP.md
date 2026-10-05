# What's left (5 October 2026)

Everything still open after the regex and Realistic Frankenstein work, grouped by area. The order inside
each group is a suggestion; nothing here is decided until Anya says so. "Needs Anya" marks what only she
can supply or judge.

## Next up (suggested)

1. **A real onboarding run with MiMo.** The first full run had Claude standing in for both models
   (OpenRouter isn't reachable from the build machine). Make a new account and go through Bulba with a
   real key, then download the transcript from Bulba's side panel so we can read what MiMo actually did.
   *Needs Anya.*
2. **Your rewording pass on Bulba.** Instructions, the four guides and the canned opening, in your voice
   (`narrative/mainapp/data/bulba/`). *Needs Anya.*
3. **Settle MiMo's temperature.** Realistic Frankenstein's authors set temperature 0.7 / top-p 0.8 for
   MiMo V2.6 Pro with thinking on; our MiMo profile says MiMo fixes both while thinking, so the app
   doesn't send them. One of the two is wrong. *Needs Anya* (or a test with a real key).

## Bulba

- **Bulba inside the chat page**: a side panel for "my replies are too long" moments, using the same
  conversation. The "later complaints" part of the preset guide exists but hasn't been exercised.
- **Offer card import** at the character stage, for people who already have a card they like.
- **Handover**: after setup, a short summary of what was set up and where to change it.
- **A small pilot** with you judging replies (the research package's protocol, scaled down).

## Presets and starters

- **Rebase the starters on the real Evening-Truth presets**: rentry.org is blocked from the build
  machine, so this needs the files or the domain allowed. *Needs Anya.*
- **The authors' own MiMo BOLT file** for Realistic Frankenstein: ours is rebuilt from the preset's toggle
  notes. If you send the MiMo V2.6 Pro BOLT file from their Drive folder, I'll compare and fix. Also the
  link you'd like the credit to point to (it currently opens a Reddit search). *Needs Anya.*
- **Verify OpenRouter model IDs** for the eight models where we guessed them (all but MiMo and DeepSeek V4
  Flash).
- **Function calling** in chats: presets can ask for it (Pura's does); tools the AI could use, like
  image generation or updating trackers.
- **Thinking display**: models that think (MiMo, Claude) can send their reasoning separately; showing it
  folded under the reply, as SillyTavern does, is what Realistic Frankenstein expects.

## Text rules (regex)

Built: preset and card rules, all three modes, the Text rules tab, SillyTavern import and export.
Still missing:
- Rules for lore entries and reasoning (SillyTavern placements 5 and 6) are kept but don't run.
- A way to see and switch a card's own rules (they run, but only the import message mentions them).
- Rules of your own that apply with every preset (SillyTavern's "global" scripts).
- Pictures in display rules: images are blocked for safety (no outside loading), so presets that draw
  pictures with regex (image prompts) show nothing there.

## Characters

- **Card extras we don't use yet**: the character's note (`depth_prompt`, an instruction inserted near
  the latest message) and group-only greetings.
- **Tags**: shown on the character tiles now; no filtering by tag yet.
- **Export with sprites**: a card exports with its neutral picture only.

## Chat

- **Continue** builds its own short prompt and ignores the preset, lore and summary. It should go
  through the preset like a normal reply.
- **Tracker panel on phones**: starts closed now, but its layout on small screens hasn't been checked.
- Leftover debug prints and comments from the original code (mostly in `mainapp/views.py`).

## Housekeeping

- **Revoke the old OpenRouter key** that's still readable in the git history (an old comment in
  `views.py`), if you haven't yet. *Needs Anya.*
- **A pull request** for `claude/focused-dijkstra-7tv1w1` when you want to merge this round. Remember
  `python manage.py migrate` afterwards (new migrations for card fields and Bulba). *Needs Anya.*
- Test output is noisy ("Classification failed" lines from the fake AI); harmless, could be quieted.
