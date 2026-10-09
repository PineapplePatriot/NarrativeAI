# What's left (updated 9 October 2026)

Everything still open, grouped by area, with what's built for context. The order inside each group is a
suggestion; nothing here is decided until Anya says so. "Needs Anya" marks what only she can supply or judge.

## Next up (suggested)

0. **A real run of the post-demo batch**: the fast route and Skip in setup, choosing to direct the story
   later in the conversation (the book layout should now switch on), and Bulba Watch in a long chat (the
   first-time note, a habit note after a few reads, "Look at it with Bulba", "I don't mind this").
   Watch the cost of a read on the Spending line, and whether MiMo's notes are fair. *Needs Anya.*
1. **A real run** of the newest Bulba pieces against a real model: Bulba in a chat, card and lore editing,
   a long "go all out" card, the story extras step, fine-tuning (model settings, trackers) and the ideas
   button. Download the transcript. *Needs Anya.*
2. **Your rewording pass on Bulba**: instructions, the seven guides and the canned opening, in your voice
   (`narrative/mainapp/data/bulba/`). *Needs Anya.*
3. **First real picture run**: the mood-picture maker (character page, or Bulba's button) against
   OpenRouter. *Needs Anya.*
4. **First real voice run**: 🔊 on a reply reads it with ElevenLabs Text to Dialogue (narrator plus every
   speaker in their own voice, side characters keep theirs per chat). Built and tested with ElevenLabs faked;
   needs a real key to hear it. *Needs Anya.*

## Bulba

Built: setup in seven stages (extras, how replies read, preset, you, character, story extras, done) with
a summary and downloads at the end; Bulba in every chat; card import, writing (compact, detailed or "all
out" up to ~6k tokens) and editing; lorebooks from wiki research, and editing them later; themes from the
built-in backgrounds and music; pictures sent with 📎; fine-tuning with Apply/Undo (model settings,
trackers and custom trackers, alternate greetings, a card's text rules, lorebook settings) and a button that
makes mood pictures on the user's key; preferences you can reword or remove; the ideas button by the
message box (what to write next, or what happens next when directing); wording a director's note.
After the demo: the setup panel shows the step, roughly how many questions are left, the small steps of the
current stage and skipped stages; a fast route (the model's ready preset, then straight to the character),
also from the welcome page; a Skip button; "who writes your character" can change later in setup. **Bulba
Watch** (the "more agentic" feedback): every 5 replies MiMo reads the latest ones for slips it can quote
(same openings, overworked metaphors, forced callbacks, unearned depth, over-explaining, detail fixation,
out of character, echoing, writing for the user, pet phrases); a slip in 3 of the last 6 replies raises a
note (badge on 🥔), with its likely source (the model, the setup, or gently, their own messages); it learns
their taste from rewrites and edits, and notices a much slower or faster reply pace than usual. On by
default, with a first-time note to switch it off; off on the Extras page or per chat.

Open (Bulba Watch):
- **Tune the numbers** after real use: every 5 replies, 3 of the last 6, the pace thresholds. *Needs Anya.*
- Show what it learned about their taste (and let them reword or remove it), like Bulba's notes in setup.
- Feed the learned taste into the in-chat Bulba's context, and into the preset when they agree.

Open:
- **A small pilot** with you judging replies (the research package's protocol, scaled down). *Needs Anya.*
- Bulba can't (on purpose): keys, connections, its own budget.

## Presets and starters

- **Rebase the starters on the real Evening-Truth presets**: rentry.org is blocked from the build machine,
  so this needs the files. *Needs Anya.*
- **Verify OpenRouter model IDs** for the eight profiles marked unverified (all but MiMo and DeepSeek V4
  Flash). Needs network access to OpenRouter.
- Built: function-calling dice, inventory and story extras; Marinara-style trackers; generation triggers;
  the thinking display; director mode with the book layout.

## Characters

- **Export with sprites**: a card exports with its neutral picture only.
- **Group-only greetings**: kept from imports, unused until groups exist (delayed).
- Built: tag filter on the Characters page; character themes (background, music, dialogue colour, a
  short tagline); sprites with a transparent background stand in the scene.

## Chat

- **A picture mid-scene** as a story extra. Medium.
- **Pictures in display rules**: images are blocked for safety, so presets that draw pictures with regex
  show nothing there. Needs a safety design.
- Leftover comments from the original code (mostly in `mainapp/views.py`).
- Built and checked on a phone: the message box, the pen menu, the tracker panel, the Bulba panel; the
  music player shrinks to a small pill.

## Hosting and the demo

- Railway with a volume (`docs/DEPLOY.md`); the demo account gets Il Dottore (card, lorebook, nine
  sprites, theme). Built-in backgrounds and music ship with the app.
- **Merge** `claude/focused-dijkstra-7tv1w1` to deploy this round. Migrations run on start. *Needs Anya.*

## Later

- Our own endpoint, keys and a wallet instead of each person's OpenRouter key.
