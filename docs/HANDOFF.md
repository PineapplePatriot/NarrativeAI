# Handoff for the next Claude session (written 13 October 2026)

Read this first. It replaces the 9 October handoff: that one's premise, working style and architecture still
hold (summarised again below); everything built since the post-demo feedback is listed in detail.
`docs/ROADMAP.md` is the public to-do list; `docs/bulba/PLAN.md` is Bulba's original design;
`docs/research/` holds the research package, including the preset cookbook.

## Premise (unchanged)

**NarrativeAI** is a Django roleplay app (SillyTavern-style: presets, cards, lorebooks, trackers) built as a
university assignment ("Побудова AI продуктів", 2026). Its centre is **Bulba**, a sarcastic talking-potato agent
that onboards people (asks about taste in plain words, shows A/B samples from *their* model, builds the setup) and
supports them inside every chat. Every change Bulba makes is a proposal with Apply / Edit / Not this / Undo.
Hosted on **Railway** (see `docs/DEPLOY.md`); graders use a demo account with **Il Dottore**.

## How the user works (unchanged, important)

- Business analyst who is vibecoding, not an engineer: plain words, clarifying questions, suggest next steps,
  **never reach a final conclusion without their input**. The docs call the repo owner "Anya".
- English is the working language; course material is Ukrainian.
- Live tests cost them money, so batch fixes; they test on Railway with a teammate and send screenshots.
- Taste rules: normal fonts; story extras mid-text; no randomness forced on people who don't want it; Bulba borrows
  tested community wording before writing its own and avoids AI-speak; long cards possible; Dottore's lore is
  behaviour and facts; no Traveler in demo lore.
- They know Claude models well: the "Recounting and keeping score" habit below came from them.

## Rules for working in the repo

- Branch this session: **`claude/vigilant-hawking-ea4zwf`**, 18 commits on top of `master` (PR #9 was merged
  before this session). **No PR opened yet**; the user said Railway "a little later". Don't open one unless asked.
- One new migration: **`0031_watch`** (`Chat.watch`, `ChatSettings.watch`). Railway must run migrations on deploy.
- Commits end with the attribution lines from the session's system reminder. No model identifiers in commits.
- Secrets only in Railway variables. `.gitignore` ignores `*.json` except listed data folders.

## Dev environment

- venv: `python3 -m venv <scratchpad>/venv && pip install -r requirements.txt`. Tests from `narrative/`:
  `python manage.py test mainapp users --parallel 4` → **1020 tests, all passing** at handoff (~3 min).
- Dev server **must be started from `narrative/`** (templates resolve relative to it):
  `cd narrative && exec python manage.py runserver 127.0.0.1:8765 --noreload` in the background; stop with
  `pkill -f "manage.py runserver 127.0.0.1:876[5]"` in its own command.
- Local demo: `DEMO_PASSWORD='demo12345!' python manage.py seed_demo`; the demo profile needs a fake key for local
  page checks (`ConnectionProfile.api_key='sk-or-fake'`). Locally the demo Dottore has the World tracker on and some
  seeded Watch/polish/condense data (local DB only).
- Playwright: `/opt/node-tools/node_modules/playwright`, Chromium at `/opt/pw-browsers/chromium-1194/chrome-linux/chrome`.
- The build machine **can't reach** OpenRouter, ElevenLabs, SillyTavern docs or most wikis: every AI feature is
  tested with faked responses. Real runs happen only on the user's side.

## What this session built (in order)

### 1. Setup: progress, fast route, ready presets, skipping (`bulba/progress.py`, `agent.py`)
- The setup panel shows "Step N of 7 · about N questions left", a line per upcoming stage, the small steps inside the
  current one (ticked from what happened, no AI), and skipped stages crossed out. A slim bar keeps it visible on phones.
- **Skip this step** button, with an always-visible note that skipping leaves less of the setup tuned to them.
- Bulba's opening offers **Full setup** or **Fast route**. Fast route: pick a feel (back-and-forth, rich scene,
  director seat) → the model's ready preset is applied (Undo) → persona → character. All canned, no AI.
- **Welcome page**: after picking a model, its three ready presets can be applied as they are, **without Bulba**
  (`starters.apply_ready`; the director seat adds Pura's wording and the book layout).
- **Extras in one form**: the full setup opens with one form (summaries, trackers, pictures, Bulba Watch,
  background model, a voices link), applied at once, then the basics form; neither needs AI. The story stage uses
  `show_extras_form` (dice, story extras, ideas) with Bulba's picks pre-ticked and a one-line reason.
- Bug fixed: setup Bulba lacked `propose_control`, so choosing director mode *later* in the conversation never
  switched the book layout on. Setup Bulba now has it and sees the current mode and layout.

### 2. Bulba Watch (`bulba/watch.py`, `data/bulba/watch.md`, `static/mainapp/js/watch.js`)
The professor's "not agentic enough" feedback. On by default, with a first-time note in the chat (Keep it on /
Turn it off / Off in this chat); switch on the Extras page. Nothing is collected while it's off.
- **Free checks after every reply** (code): sentences starting the same way; a phrase repeated word for word.
- **Paid read every 5 replies** on Bulba's model (MiMo): slips it can quote, by label: same_openings,
  overworked_metaphor, forced_callback, unearned_depth, overexplaining, detail_fixation, out_of_character,
  echoing_user, writing_for_user, **recounting** ("Recounting and keeping score instead of talking"), pet_phrase,
  misremembered_past, other. Each slip notes its likely cause (model / setup / their own messages, said gently).
- A slip in **3 of the last 6** replies (per check's own window) raises a habit note: a number on 🥔 and a card
  with quotes: *Look at it with Bulba* / *Fix this automatically* / *I don't mind this* (muted for good) / *Not now*.
- The same read also: learns **taste** from rewrites and edits; flags **getting the past wrong** (retelling events
  inaccurately, often in dialogue, leaving out what mattered, inventing details; logged as a habit *and* a note
  right away); collects **facts worth keeping** (2+ → "Worth keeping?", Bulba proposes card/lore additions); and,
  while director mode is off, judges whether their messages are directions (`they_direct`). The read sees the
  summary, pinned note, card scenario and lore titles.
- **Reply pace** (no AI): their usual reply time (only aggregates kept); much slower 3 times running, or quick and
  short, → an offer of help.
- **Taste on the Extras page**: reword or remove learned lines; un-mute habits; lines already in the preset are
  marked. 3+ new lines → "Your taste, in your preset?" note → Bulba writes them as a preset change (`from_taste`).
- **Director mode offer** (once per chat): director's notes in 3 of the last 5 turns, the reader's `they_direct`, or
  switching to the book layout while the preset isn't in director mode. One click switches (Pura's wording + book
  layout), with Undo.

### 3. Bulba's polish, the "desloppifier" (`bulba/polish.py`, `data/bulba/polish.md`)
- Habits approved with *Fix this automatically* (or Bulba's `fix_automatically`, Apply) are rewritten in every new
  reply, regenerated reply, swipe, Continue, and "Write my message" (minus habits that can't apply to their own
  message). The page shows "Polishing…", then "Bulba fixed N things" with before/after, *Show original*, *Undo fixes*.
- The rewriter sees the reply, the habits with quotes from this chat and the summary (not the chat); answers with
  find/replace fixes; code drops fixes that lose story-extra markers, colour tags or {{char}}/{{user}}, or change
  more than 40% (or 300 characters). Free-only habits skip the call when the reply doesn't have them.
- Who rewrites: Bulba's model by default, their chat model if chosen on the Extras page.
- In a chat, Bulba's `polish_message` fixes one message on request (habit names or their own words); Apply
  replaces it in the chat, original kept.

### 4. In-chat Bulba gaps closed (`bulba/memory.py`, `bulba/rules.py`, `doctor.py`)
- Bulba sees **what the AI saw** for the last reply: summary (clipped; `read_memory` for every piece), pinned note,
  trackers, lore that fired, old messages recall brought back. `propose_memory_edit` fixes a summary piece or the
  pinned note (Apply/Undo). The pen menu has the same as **👁 What the AI saw**.
- **Text rules**: `read_text_rules` / `propose_text_rules` (setup and chat) switch, add, edit or remove rules in the
  preset or their own list; patterns checked first. The card's rules stay on/off only.
- Bulba sees what Watch learned (taste, muted habits, habits noticed, habits being polished).

### 5. Director's notes (`chat_page.html` pen menu, `views.py`)
- Pen menu split in two: **🎬 Director's note** (▶ Send: on its own or with their message; 🥔 Word it for me;
  ✨ Be creative: Bulba writes a logical note and a twist to pick from) and **↻ Redo the last reply** (shortcut
  chips, its own Word it for me, Rewrite last reply).
- A note sent alone continues the story with no user message. Each reply keeps the note that steered it (🎬 line).

### 6. Chat memory and atmosphere
- **🗜 Condense** a message: the AI gets a short version (summary model), the chat shows all of it; Show / Edit /
  Redo / Undo under it; kept per swipe; editing the message drops it. Lives on the message, not in summary pieces
  (the summary doesn't remove messages from the prompt; only the context limit does).
- **Free recall** (`mainapp/recall.py`): when messages were left out to fit the context, ones sharing rare words
  with the newest two messages (two such words, or one said at most twice) come back under the summary as
  "Earlier in the story", **newest 3 at most**; a word in >30% of messages counts for nothing.
- **Weather and time of day** over the scene from the World tracker (night/dusk/dawn tints; rain, storm, snow,
  fog), free; toggle in pen menu → This chat; tints only with reduced motion (`static/mainapp/js/atmosphere.js`).
- **Music player** moved into the header (▶/❚❚ that follows the real audio state; fixes the "press twice" bug);
  track name, volume and None in the music picker; the chat's track starts on the first click (browser rule).
- **Music follows the scene** (opt-in in the picker): every 3 replies a tiny pick on the background model among the
  built-in tracks; crossfade.
- **🎤 voice input** with the browser's speech-to-text (hidden where unsupported).

### 7. Cookbook and model knowledge
- New cookbook section **4.16 "Recounting and keeping score instead of talking"** (docs/research and the
  `candidates.json` library Bulba borrows from); added to the Claude model profiles' habits to check for.

### 8. Story systems after Lattice (`mainapp/story.py`, `bulba/tune.py` → `propose_story_systems`)
- Kept in `Character.tracker_config["systems"]` (no migration; the tracker setup page keeps them when it saves);
  values per chat in the chat file's `"story"`.
- **meter** (min/max/start, step, cooldown in replies, baseline + drift_days), **clock** (start day/time),
  **event** (at_day/at_time, once or every_days; needs the clock), **table** (weighted entries + when; the chat
  model calls `draw_from_table`, shown as 🃏 like the dice).
- Meters and the clock ride on the tracker call (a `"_story"` key: change −1/0/+1 with why, elapsed_minutes): no
  extra cost; `trackers_due` fires for them even with no trackers on. What it finds is **pending** until they
  reply; it counts only if the reply it read is still on screen unchanged (swipe, regenerate, edit → nothing).
  Snapshots per message count; delete rewinds. Events reached go into the next reply until that reply is kept.
- With a clock, the World tracker's date and time follow it (unless locked).
- Prompt: "Story systems:" lines appended to the StoryState slot (so What the AI saw shows them too).
- UI: dashed pills in the HUD (🕰 clock, meters) and a "Story systems" card on top of the ▤ panel (values, coming
  up, lately, the kept-scenes note). Edited by Bulba (setup story stage, in-chat, tuning guide section) or by hand
  in a "Story systems" section on the tracker setup page (save refuses events without a clock or empty tables).

### 9. Onboarding covers more (user's request: "for a full overview")
- The first extras form has **Fixing habits**: Bulba's model (cheaper) or their chat model (`fix_model`, applied
  with the form, undone with it).
- After the preset is applied, Bulba asks once about **text rules** (says what the preset's own rules do, offers
  common fixes like stripping asterisks; proposals go in their own list). Optional step "Formatting clean-up".
- The done stage ends with **what's waiting in the chat** (pen menu: director's note and Redo, Condense, What the AI
  saw, Watch's number on the potato, the microphone, trackers and story systems), and on the fast route offers what
  it skipped. Story systems are an optional step in the story stage's progress.

### 10. After the second live test
- Director mode frames every direction (and director's notes): write the scene in full, their own character
  included (Pura's "never treat {{user}} as a character" made models leave it out). The offer comes once per user.
- Watch reads every 3 replies and judges what the model wrote (a polished reply by its original): a habit Bulba
  keeps polishing away raises a "still writes it" note that points to the preset.
- "Fix this automatically" polishes the latest reply right away; 🧹 on any AI reply (shown only while some habit
  is being fixed, its tooltip says which) polishes that reply. Quotes in notes show as written (colours rendered).
- Small calls on Bulba's model have room to think (Be creative came back empty); the mic is an icon, not an emoji.

## Decisions the user made this session

- Progress counts questions; skip hint always visible with the quality warning; fast route = preset → persona →
  character; welcome page = ready preset only, no Bulba.
- Watch on by default with a first-time note; MiMo reads; free checks every reply, paid every 5; greeting counts as a
  reply; only summaries of reply pace are kept.
- Polish: MiMo by default, their choice on the Extras page; automatic once they approve a habit; all habit types;
  swipes, regenerations, Continue and Write my message count.
- Director mode switch applies at once with Undo; the paid read judges directive messages (no word lists).
- Continuity isn't stark: it's the subtle "getting the past wrong", both a mistake and a pattern; recounting itself
  is a bad Claude habit.
- Recall: limit to the newest 2–3 out-of-context matches; frequent RP terms mustn't flood it.
- Not for this demo: "the character writes first" (saved for a future messenger-style mode); new chat / branch /
  sprite export from Bulba. Lattice systems only if time allows.

## Open: next steps

1. **Storybook export** (the last Phase 3 item). Asked, not answered: start with the character's picture and the
   summary? Their own messages in full, or folded like the book layout?
2. **Story systems**: built (section 8), with hand editing. Open: a real run. Storybook export: later (the user's call).
3. Older leftovers: verify OpenRouter IDs for 8 model profiles; rebase starters on Evening-Truth (needs the files);
   cookbook parts not in yet (three bundles, keepsake ending / epilogue, recurring rituals, prompt-caching advice,
   a per-fix record); Edit on settings-like proposals; leftover comments in `views.py`.

## Never run against real services (check in the live test)

Everything from this session, plus the older list (voices, mood pictures, ideas button). In particular: the cost of a
Watch read (now with more context) and of a polish pass; whether MiMo's habit notes are fair and its rewrites keep
the voice; Be creative quality; a director's note sent alone on the demo model (the request then ends without a user
message); the 3-of-5 and 3-of-6 thresholds; music picks; speech recognition language.
