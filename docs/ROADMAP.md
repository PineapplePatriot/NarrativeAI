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
- **Card import and lorebooks in Bulba** (built): at the character stage Bulba asks for a card you
  already have (upload box), reviews it and suggests fixes; it can write lore entries from wiki research
  (web search aimed at the work's wikis), in setup or from a chat. Not yet tried against a real model.
- **Research cookbook** (in `docs/research/`): its wording library is searchable by Bulba as untested
  candidates, ranked below the Frankenstein blocks; its lessons are in the asking, preset and writing
  guides. Not used yet: the "Story extras" step (letters, phone screens, rumours, milestones as their own
  setup step) and the function-calling design (see Presets and starters).
- **Handover**: after setup, a short summary of what was set up and where to change it.
- **A small pilot** with you judging replies (the research package's protocol, scaled down).

## Presets and starters

- **Rebase the starters on the real Evening-Truth presets**: rentry.org is blocked from the build
  machine, so this needs the files or the domain allowed. *Needs Anya.*
- **Realistic Frankenstein for MiMo**: the starter is the authors' MiMo V2.6 Pro file switched to BOLT.
  Their pico setup (thinking off, temperature 0.7 / top-p 0.8) is a second MiMo option.
- **Verify OpenRouter model IDs** for the eight models where we guessed them (all but MiMo and DeepSeek V4
  Flash).
- **Function calling** (built): dice, inventory and conditions kept by the app; story extras drawn by the
  app (letters/notes/signs, phone screens, relationship milestones). All opt-in on the Extras page. Next
  candidates: a picture mid-scene; rumour board, scrapbook and favour ledger (`docs/research/`).
- **Generation triggers** (fixed): blocks marked for Impersonate, Continue or Swipe only now fire only then
  (Frankenstein's Impersonation Turn was going out with every reply).
- **Thinking display** (built): reasoning the model sends separately, or writes at the start of its reply
  in <thinking>/<think> tags (Frankenstein's pico), is shown live and kept in a folded "Thoughts" box.

## Text rules (regex)

Built: preset and card rules, all three modes, the Text rules tab, SillyTavern import and export, your
own rules for every preset, switching a card's rules off, lore-entry and thinking placements.
Still missing:
- Pictures in display rules: images are blocked for safety (no outside loading), so presets that draw
  pictures with regex (image prompts) show nothing there.

## Characters

- **Card extras we don't use yet**: group-only greetings. (The character's note, `depth_prompt`, is now
  sent near the latest message and shown on the character page.)
- **Tags**: shown on the character tiles now; no filtering by tag yet.
- **Export with sprites**: a card exports with its neutral picture only.

## Chat

- **Director mode and the book layout** (built): the basics form asks who writes your character; directing
  switches chats to a book where replies read as chapters and your messages fold into markers.
- **Write my message** (rebuilt): the old magic expand, now an impersonate through the preset and lore.

- **Pen menu** (rebuilt): director's note for the next reply (Bulba can word it; "rewrite last reply" uses
  it), a pinned note for the whole chat (replaces the four World State boxes, which overlapped the
  trackers and never showed their saved values), story memory, actions, and the chat's settings folded.

- **Streaming after a guided regenerate**: couldn't reproduce with the current code; the chat now
  says "thinking" while a thinking model reasons, which may be what looked like a stall. Tell me if
  it happens again.
- **Tracker panel on phones**: starts closed now, but its layout on small screens hasn't been checked.
- Leftover comments from the original code (mostly in `mainapp/views.py`); the debug prints are gone.

## Housekeeping

- **Revoke the old OpenRouter key** that's still readable in the git history (an old comment in
  `views.py`), if you haven't yet. *Needs Anya.*
- **A pull request** for `claude/focused-dijkstra-7tv1w1` when you want to merge this round. Remember
  `python manage.py migrate` afterwards (new migrations for card fields and Bulba). *Needs Anya.*
