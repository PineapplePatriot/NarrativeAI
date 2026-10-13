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
current stage and skipped stages; a fast route in Bulba (the model's ready preset, then persona and character);
the ready presets on their own (no Bulba) on the welcome page; a Skip button with an always-visible note that
skipping leaves less tuned to you; "who writes your character" can change later in setup. **Bulba Watch**
(the "more agentic" feedback): free checks after every reply (same sentence starts, a phrase repeated word
for word across replies); every 5 replies MiMo reads the latest ones for slips it can quote
(same openings, overworked metaphors, forced callbacks, unearned depth, over-explaining, detail fixation,
out of character, echoing, writing for the user, pet phrases); a slip in 3 of the last 6 replies raises a
note (badge on 🥔), with its likely source (the model, the setup, or gently, their own messages); it learns
their taste from rewrites and edits, and notices a much slower or faster reply pace than usual. On by
default, with a first-time note to switch it off; off on the Extras page or per chat.

**Bulba's polish** (the desloppifier): "Fix this automatically" on a habit note approves that habit; every new
reply, swipe, regenerated or continued reply then gets a pass (MiMo by default, the chat model if chosen on
the Extras page) that sees the reply, the habits with quotes from the chat and the summary, and answers with
small find-and-replace fixes. Code drops fixes that would lose story-extra markers or colour tags, or change too
much. "Polishing…", then "Bulba fixed N things" with Show original / Undo fixes under the reply.

In a chat, Bulba can fix one message on request (polish_message: before/after, Apply replaces it in the chat,
original kept) and start fixing a habit automatically (fix_automatically, Apply to approve). "Write my
message" is polished too. Setup: the extras in one form (no AI), then the basics form (no AI); the story
extras in a second form with Bulba's picks pre-ticked.

Director's notes: the pen menu has the note on top (Send on its own or with a message, Word it for me, Be
creative: a logical and a creative note) and "Redo the last reply" below (shortcuts, its own wording, Rewrite).
Replies show the note that steered them (🎬). Bulba offers director mode once per chat when they steer more than
play (director's notes in 3 of the last 5 turns, or the Watch reader judging their messages as directions) or
switch to the book layout; one click, with Undo.

Bulba in a chat now sees what the AI saw for the last reply (summary, pinned note, trackers, lore that fired;
also a pen-menu panel) and can fix a summary piece or the pinned note; it reads and changes text rules in the
preset and in their own list (the card's stay on/off). Learned taste goes into the preset through a Watch note
("Your taste, in your preset?").

Story Keeper and continuity ride on the same Watch read (no extra call): the reader sees the summary, pinned
note, card scenario and lore titles; getting the past wrong (retelling events inaccurately, often in dialogue
to make a point, leaving out what mattered, inventing details) raises a note at once and counts as a habit
("Getting past events wrong", also fixable by the polish); new lasting facts pile up and, two or more, raise "Worth keeping?" (Bulba
proposes the card or lore addition). Single messages can be condensed for the AI (🗜).

Atmosphere (free unless noted): weather and time of day over the scene from the World tracker; the music's
play/pause in the header (and the double-press bug fixed); "Let the music follow the scene" (opt-in, a tiny pick on
the background model every 3 replies, built-in tracks, crossfade); voice input with the browser's speech-to-text.
Text reveal is covered by streaming.

Free recall (mainapp/recall.py): when messages were left out to fit the context, the ones sharing rare words with
the newest two messages come back under the summary ("Earlier in the story"), newest 3 at most; a word in more
than 30% of messages counts for nothing. Shown in "What the AI saw" and to Bulba. "Recounting and keeping score"
is a Watch habit, a cookbook entry (4.16) and a known Claude habit.

Open (Bulba Watch):
- **First real polish run**: is MiMo's rewrite faithful to the voice, and what does a pass cost? *Needs Anya.*
- **Tune the numbers** after real use: every 5 replies, 3 of the last 6, the pace thresholds. *Needs Anya.*
- Turn the learned taste into a preset change (Bulba proposes it, they Apply), once a few lines agree.

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

Built (13 October): **story systems** after Lattice (`mainapp/story.py`, Bulba's `propose_story_systems`):
slow meters with step, cooldown and drift; a story clock with events; opt-in weighted random tables (a tool like
the dice); only kept scenes count; deleting messages rewinds. Editable by hand on the tracker setup page too. Not yet: a
real run to see whether the tracker model's −1/0/+1 calls and time estimates are sensible.

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
