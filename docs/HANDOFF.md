# Handoff for the next Claude session (written 11 November 2026)

Read this first. It replaces the 13 October handoff; that version (`git show 6014b51:docs/HANDOFF.md`) has the long write-up of Bulba Watch, polish, director's notes, recall, story
systems and the older decisions. Those still hold; they're summarised briefly below.
`docs/ROADMAP.md` is the public to-do list; `docs/bulba/PLAN.md` is Bulba's original design; `docs/research/` holds
the research package, including the preset cookbook (`preset-instruction-cookbook.md`).

## Premise

**NarrativeAI** is a Django roleplay app (SillyTavern-style: presets, cards, lorebooks, trackers) built as a
university assignment ("Побудова AI продуктів", 2026). Its centre is **Bulba**, a sarcastic talking-potato agent
that sets people up (asks about taste in plain words, builds the preset, character, persona and look) and supports
them inside every chat. Every change Bulba makes is a proposal with Apply / Edit / Not this / Undo.
Hosted on **Railway** from `master` (see `docs/DEPLOY.md`); the Dockerfile runs `migrate`, then `seed_demo`, then
gunicorn. Graders use a demo account with **Il Dottore**. Testers are Ukrainian.

## How the user works (important)

- Business analyst who is vibecoding, not an engineer: **plain words**, clarifying questions, suggest next steps,
  **never reach a final conclusion without their input** (propose, then wait for their answer on design choices).
- English is the working language. The docs call the repo owner "Anya".
- They test on the live Railway site (often on a phone or tablet) with a teammate and send screenshots in batches.
  Live tests cost them money, so fix in batches and say clearly what was and wasn't checked.
- They know SillyTavern presets well (Sola, Pura, Celia, Evening-Truth, Realistic Frankenstein) and often point
  to how a community preset does something; prefer borrowing tested ideas, but write our own wording and names
  (they disliked copying Sola's palette names).
- Taste rules: normal fonts; story extras mid-text; no forced randomness; Bulba avoids AI-speak; plainer, never
  fancier (polish must not add metaphors); characters are people, not types or tropes.

## Rules for working in the repo

- Branch: **`claude/vigilant-hawking-ea4zwf`**. The user merges it to `master` through PRs themselves; **don't open
  a PR unless asked**. Push with `git push -u origin claude/vigilant-hawking-ea4zwf`.
- At handoff the branch is **14 commits ahead of `master`** (counting this handoff) (master = `5370638`, PR #34). Everything listed under
  "Not live yet" below is only on the branch until they merge.
- Latest migration: `0032_second_character_name`. Railway runs migrations on deploy.
- Commits end with the attribution lines from the session's system reminder. **No model identifiers** in commits,
  code comments or docs.
- Secrets only in Railway variables, never in chat, code or commits. The user's email is private.
- `.gitignore` ignores `*.json` except the listed data folders (`mainapp/data/...`).

## Dev environment

- venv: `python3 -m venv <scratchpad>/venv && pip install -r requirements.txt`. Tests from `narrative/`:
  `python manage.py test mainapp users --parallel 4` → **1544 tests, all passing** at handoff (~100 s).
  With `--parallel`, a failing test can show only as `TypeError: cannot pickle 'traceback'`; then run serially in
  the background and poll the log (`until grep -q "^done" log; do sleep 5; done`).
- Dev server **from `narrative/`**: `NARRATIVE_DATA_DIR=<scratchpad>/shots-data python manage.py runserver
  127.0.0.1:8766 --noreload` in the background. Restart it after template changes. Demo login `demo` /
  `demo12345!`; chat URL `/main/chat/demo-il-dottore?chat=1` (no trailing slash); Quick setup `/main/quick/`.
- Playwright: `require('/opt/node-tools/node_modules/playwright')`. Tours pop up on first visit: remove them in
  scripts with `document.querySelectorAll('[class*=tour],.preset-hint,#presetHint,.persona-hint').forEach(x=>x.remove())`.
  The pen menu opens with `toggleTools()`; its settings are on the "⚙ This chat" tab (`[data-pane="paneChat"]`).
- The build machine **can't reach** OpenRouter, NanoGPT, ElevenLabs or most wikis: every AI feature is tested with
  faked responses. Real runs happen only on the user's side.
- Static files carry `?v=N` cache numbers in templates: bump them when changing CSS (JS uses a timestamp).

## Map of the code (where things live)

- `mainapp/views.py`: the chat page and its JSON actions (one big `chat_page` view with `action == ...` branches),
  Quick setup, the theme preview, `_appearance`, `prompt_names` ({{user}} = chat persona → usual persona → account
  name → "Stranger", never the login).
- `mainapp/utils.py` `build_ai_request`: fills the preset's slots (lore, StoryState = trackers + story systems +
  speech colours + designed objects, summary, pinned note, director's note). Slots go through macros, so
  `{{user}}`/`{{char}}` work there.
- `mainapp/presets.py` (normalize, assemble), `experiences.py` (the two family bases, modules, contracts,
  reminders), `basics.py` (the "Basics" block both setup forms write), `data/bulba/basics_form.json` (the questions),
  `bulba/agent.py` (`BASICS` wording, stages, Bulba's tools), `data/bulba/instructions.md` (setup script for Bulba),
  `data/bulba/doctor.md` (in-chat Bulba), `data/bulba/guides/*.md`.
- `mainapp/ai_client.py`: requests, OpenRouter/NanoGPT, Bulba's fallback chain on refusals, light thinking for
  background jobs, `_fit_effort` (a thinking level a model refuses becomes the nearest one it takes).
- `mainapp/samplers.py`, `model_profiles.py`, `data/models/*.json` (per-model profiles: thinking choices, samplers).
- `bulba/watch.py` + `static/mainapp/js/watch.js` (Bulba Watch), `bulba/polish.py` (the desloppifier),
  `html_objects.py` (AI-designed in-story objects), `speaker_colors.py` (speech colours), `chats.py` (chat files).
- Front end: `templates/mainapp/chat_page.html`, `static/mainapp/js/chat_page.js` (`renderChatMessage` is the one
  renderer: designed objects → text rules → speech colour tags → thoughts → extras slots → quotes → markdown →
  DOMPurify), `static/mainapp/css/chat_page.css`, `chat_skins.css`; Bulba's page `bulba.html` / `bulba.js`;
  tours in `narrative/static/js/tour.js` (fires a `na-tour` event on start/end).

## Built before 13 October (short version; details in the old handoff)

Setup progress and fast route; Bulba Watch (free checks every reply, a paid read every few replies, habit notes,
taste learning, "getting the past wrong", reply pace, director-mode offer); Bulba's polish ("Fix this
automatically", 🧹, Show original / Undo, turned-down rewrites remembered); in-chat Bulba sees what the AI saw and
edits memory and text rules; director's notes; Condense; free recall; weather and time of day; music in the header
and music that follows the scene; voice input; story systems (meters, clock, events, tables).

## Built from 13 October to 9 November (all merged and live, PRs #12–#34)

- **Tours** in English and Ukrainian, "What's this?" with Bulba; one look across pages; pen menu in two tabs.
- **Trackers** as a rail with slide-out cards; tracker tiles page; Bulba-designed **custom trackers** for any story
  (look, colour, icon, what raises and lowers them, levels that steer the story, automatic escalation).
- **Accounts**: email verification and password reset (Brevo), login by email, delete account, encrypted keys,
  login limit, admin off unless `DJANGO_ADMIN=1`, usage stats page with backup download and `restore_backup`.
- **Bulba**: notebook page; looks at pictures; edits utility prompts; refusals retried on other models (Gemini 4
  Argon, then DeepSeek V4 Flash; MiMo stands in for the chat model); one action at a time.
- **Writing**: experience presets on two family bases with modules (adapted from Pura, Sola, Realistic
  Frankenstein; Heartstrings default; Storybook style); Quick setup page; thinking in plain words; read in another
  language (stories written in English, translated); chat styles (Parchment, Neon, Lab, Romance); chat memory
  slider with costs; NanoGPT as a second provider; Gemini safety settings as SillyTavern sends them.
- **Fun**: the 🍅 tomato to throw during waits, the secret Tomato Pit with skins and achievements.

## Built 10–11 November (this session; on the branch, **not live yet** unless noted)

Testing batches 2–5 (from the user's live tests) were merged earlier; these came after master `5370638`:

1. **Stuck replies recover**; log out moved to the profile; the tomato steps aside.
2. **Two characters in one card**: a name for the second, both pictures with the speaker highlighted (migration
   0032), Bulba support.
3. **Pictures of their own character**: on the profile, in the chat scene with their mood, offered by Bulba.
4. **Setup order**: Bulba's full setup makes the character first, then the persona ("who you are in that story").
   `STAGES = extras, taste, preset, character, persona, story, done`.
5. **Model confusion fixes**: the story AI only knows the persona (never the login, fallback "Stranger"); no
   phantom "continue"; a clear "write my character" rule; no "What will X do?" question endings.
6. **Consistency**: AI-designed objects keep their look (first design of each kind remembered per chat and shown to
   the AI; editing one replaces it); "woven" inner-thoughts option; polish says plainer, never fancier.
7. Bulba's panel tidies up after setup; **several pictures at once** with Add and Send.
8. **MiMo thinking fix**: its provider now refuses `reasoning.effort: "medium"` (only none/high). Profile and
   starters use "high"; `ai_client._fit_effort` maps any refused level to the nearest accepted one.
9. **Speech colours** (`speaker_colors.py`; replaces the old "Coloured speech" basics question, whose lines are
   removed from presets by `basics.drop_retired`):
   - Per character (`theme["speech"]`): **"story"** (the AI writes named tags from our 16-name palette,
     `<plum>"..."</plum>`; the cast list and the user's colour go into StoryState every request; side characters
     take a free colour; Write for me is told the user's colour) or **"app"** (one colour for all speech, the AI is
     never told; the app colour beats any colour the AI wrote). Old characters without the key stay on "app".
   - Each palette colour has a dark-style and a light-style shade (`body.light-style` on parchment/lab).
   - The user's own colour (`theme["you_color"]`) paints speech in their messages in both modes.
   - Optional **tone marks** (`<plum:whisper>`): whisper, shout, drawl, tremble, sharp.
   - Bulba's look step (`propose_theme`) sets story colours by default for new characters, and colours the greeting
     (written before the look) with the character's colour. The theme card shows one sample line per speaker.
   - Pen menu → This chat: Story colours / One colour chips, cast list with colour circles, your colour; no more
     native colour picker. A half-written tag stays hidden while streaming (no more colour flip at the closing quote).
10. **Quick setup**: boxes in a row line up (CSS subgrid); room under the "Let Bulba do it" buttons; **13 new
    genres** (Adventure, Mystery, Suspense, Horror, Drama, Action, Intrigue, Survival, Found family, Whimsical,
    Psychological, Grimdark, Dark romance), shown in two groups, **Mood** and **Kind of story**, in both forms.
11. **Music waits for the chat tour**: silent while the first-visit tour is open, starts when it ends or is closed;
    a tour opened later pauses and resumes it.
12. **🧹 on an already polished reply** runs another pass on the polished text (each pass has its own limits: 12
    fixes, 40% or 300 characters); fixes add up and the model's original stays for Undo.

## Decisions the user made recently

- Speech colours: two ways (app colour, or story colours done purely by the AI's tags); the user's colour in
  both; our own palette names; new characters start on story colours; small colour drift is fine (no app
  correction); tone marks yes.
- Genres split into Mood / Kind of story; more genres later when needed. Dark romance sits in the normal list
  (asked whether it should be behind 18+: no answer yet).
- 🧹 may run again on a polished reply.
- Setup: character before persona; the persona can belong to the story.

## Open questions (asked, no answer yet)

- Polish lost after a screen rotation: was it a translated chat, or a reload?
- "Could not open the panel during onboarding": which panel, which step?
- More mood pictures: how many and which?
- The "Stranger" fallback name: fine, or something else?
- DeepSeek / MiMo thinking: off or on by default? Offer light thinking for existing presets?
- A full Ukrainian interface?
- Should Dark romance be behind the 18+ switch?
- Speech colours: should colours belong to the character (now) or to each chat?

## Next steps

1. After the user merges: live checks of the setup order (character → persona), no login or "What will…?"
   endings, designed-object memory, speech colours with MiMo over 10+ replies (do tags stick? do side characters
   pick new colours?), the music/tour behaviour on a phone, MiMo thinking on "high".
2. If MiMo forgets colour tags: add a one-line reminder right before each reply (the way the 18+ rule works).
3. Planned: pictures for a chat's own persona; the user's picture dims while only the character talks.
4. Older leftovers: Storybook export; verify OpenRouter IDs for some model profiles; cookbook parts not in yet.

## Never run against real services (check in live tests)

Everything above from 10–11 November, plus: speech-colour tags with each model; tone marks; the greeting colouring
on a real Bulba setup; second 🧹 passes; the cost of Watch reads and polish passes; NanoGPT pictures and web search.
