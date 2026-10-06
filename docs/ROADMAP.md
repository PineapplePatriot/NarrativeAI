# What's left (updated 5 October 2026, after the first real Bulba run)

Everything still open after the regex and Realistic Frankenstein work, grouped by area. The order inside
each group is a suggestion; nothing here is decided until Anya says so. "Needs Anya" marks what only she
can supply or judge.

## Next up (suggested)

1. **A second real run with MiMo** after the fixes from the first one (choices on every question,
   POV and tense, web lookup for canon characters, pictures step, Start chatting button). Download the
   transcript again. *Needs Anya.*
2. **Your rewording pass on Bulba.** Instructions, the four guides and the canned opening, in your voice
   (`narrative/mainapp/data/bulba/`). *Needs Anya.*
3. **First real picture run.** The picture maker lists OpenRouter's image models and defaults to Nano Banana
   2 (`google/gemini-3.1-flash-image`, setting `SPRITE_IMAGE_MODEL`). Untested against OpenRouter itself.
   *Needs Anya.*
4. **The subscription** stops chatting, Bulba and background jobs at $25 a month for now. Later: our own
   endpoint and keys, with a wallet. *Later.*

## Bulba

- **Bulba inside the chat page** (built): the 🥔 Bulba button in a chat opens a side panel (full screen on
  phones). Bulba sees the last messages, the model's thoughts, the card and the preset, proposes one fix
  at a time, can rewrite your last reply with it as a preview, and every change has Apply and Undo.
  Each chat has its own Bulba conversation. Not yet tried against a real model. *Needs Anya.*
- **Writing rules** (built, `guides/writing.md`): borrow before writing (their preset's own toggles,
  then a tested Realistic Frankenstein block word for word, then the starter's wording, then new text);
  no AI-speak; story first unless it's a game, where templates and fixed formats take over. Bulba can
  search and borrow the Frankenstein blocks in setup and in a chat. Not yet tried against a real model.
- **Offer card import** at the character stage, for people who already have a card they like.
- **Handover**: after setup, a short summary of what was set up and where to change it.
- **A small pilot** with you judging replies (the research package's protocol, scaled down).

## Presets and starters

- **Rebase the starters on the real Evening-Truth presets**: rentry.org is blocked from the build
  machine, so this needs the files or the domain allowed. *Needs Anya.*
- **Realistic Frankenstein for MiMo**: the starter is the authors' MiMo V2.6 Pro file switched to BOLT.
  Their pico setup (thinking off, temperature 0.7 / top-p 0.8) is a second MiMo option.
- **Verify OpenRouter model IDs** for the eight models where we guessed them (all but MiMo and DeepSeek V4
  Flash).
- **Function calling** in chats: presets can ask for it (Pura's does); tools the AI could use, like
  image generation or updating trackers.
- **Thinking display** (built): reasoning the model sends separately is shown live while it thinks, then
  kept in a folded "Thoughts" box above the reply (each swipe keeps its own). Presets that make the model
  write its thinking inside the reply (in tags) aren't folded yet; that needs a reasoning text rule.

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

- **Streaming after a guided regenerate**: couldn't reproduce with the current code; the chat now
  says "thinking" while a thinking model reasons, which may be what looked like a stall. Tell me if
  it happens again.
- **Tracker panel on phones**: starts closed now, but its layout on small screens hasn't been checked.
- Leftover debug prints and comments from the original code (mostly in `mainapp/views.py`).

## Housekeeping

- **Revoke the old OpenRouter key** that's still readable in the git history (an old comment in
  `views.py`), if you haven't yet. *Needs Anya.*
- **A pull request** for `claude/focused-dijkstra-7tv1w1` when you want to merge this round. Remember
  `python manage.py migrate` afterwards (new migrations for card fields and Bulba). *Needs Anya.*
- Test output is noisy ("Classification failed" lines from the fake AI); harmless, could be quieted.
