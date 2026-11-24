# Handoff for the next Claude session (written 24 November 2026)

## Episodes (visual novels), rebuilt in session `claude/trusting-sagan-d1tl6k`

The branch starts from Codex's `codex/screen-integration` (Screen home, Drive, Mail, Pulse, Wave, Subtext, VN v1) and
reworks episodes. Not merged to `master` yet; the user merges by PR. Migrations `0044_episode_looks`,
`0045_episode_places`, `0046_look_identity_review`. Venus University (AGPL) was the inspiration: ideas only, no code.

Words that matter (the user cares): **consistency** = things look and sound the same every time (looks, places);
**continuity** = what happened stays true as the story moves (facts, who knows what, who is present, clothes).

- **Three kinds of character pictures, never mixed:** chat-page stage sprites (`photo_*`, `extra_sprites`), phone
  pictures (`messenger_profile`), and **episode looks** (`EpisodeLook`, `episode_looks.py`): one outfit per look,
  canon or modern by how the episode was entered. Bulba reads the reference picture (`identity`) instead of the
  card's prose; the neutral picture is drawn once on a key colour; every mood is an edit of it (face only). The
  browser cuts them out (`static/.../episode_looks.js`, flood fill + spill removal) and compares each mood's outline
  with the neutral's (>3% = "body changed", one automatic redraw, then flagged and kept off the stage).
- **Checked pictures:** `picture_checks.draw_checked` = draw, Bulba looks (vision model with references), redraw
  once if wrong, keep the better. Used by look bases, outfit changes, places, the end illustration, phone photos.
  Off in tests (`settings.PICTURE_CHECKS`).
- **Casting** (`vn_casting.py`, `static/.../vn_casting.js`): Bulba proposes cast, place (time, light, weather,
  layout, details), outfits item by item, facts, opening, optional detail; Apply / Edit / Not this. Applied parts
  are fixed and sent with every turn. Drawn places are kept (`EpisodePlace`) and join the backdrop list.
- **Stage** (`vn_scenes.js` renderStageOnly): one 16:9 frame (full height on phones), whole cast on the floor, name
  tab, typewriter, tap to go on, keys, backlog, auto, hide, menu sheet (passage tools from `vn_editor.js`, looks,
  music, preferences, versions, finish). Curtain over the opening and place changes.
- **Story state per passage** (`beat.stage`): background, music, place, `looks` (who wears which look), `faces`,
  `present` (enter/leave), continuity. Outfit changes are passage events (`outfit_change`) with draw / edit / keep.
- **Watch** (`vn_watch.py`): after each turn when Bulba Watch is on (or from the menu), checks the turn against the
  casting, memory, the record from before the turn, who is present and what they wear; slips with fix, regenerate,
  ignore.
- **Phone:** a finished episode leaves a card in the chat and updates "📍 Right now" (place, clothes).
- **Language:** written in English, shown translated (`vn_support.translate_turn`, `beat.shown`). **Voices:**
  `vn_scenes.voice_line`, kept on the page. **Cost:** from casting on, from `UsageRecord`.

### First live run (nothing above has met a real model yet)

1. A chat with one character who has a neutral sprite or phone portrait. Scenes → Ask Bulba to cast it: are the
   place, outfits and facts concrete and true to the chat?
2. Make one look: does Bulba's "what it saw" match the picture? Does its check agree with your eyes? Do the
   moods keep the body (is 3% too strict or too loose)? How does the browser cut-out handle hair?
3. Draw the place; play 3–4 turns with Bulba Watch on; try a slip on purpose (someone knowing a secret).
4. An outfit change, someone leaving and coming back, finish with an illustration; check the chat card, Right now
   and the cost line. Then the same with the reading language set to Ukrainian, and one line read aloud.


## Before that (21 November 2026)

Read this first. It replaces the 11 November handoff (`git show 61d8986:docs/HANDOFF.md` for that one, which has
the longer history up to then). `docs/PLAN.md` is the working plan with every list the user sent and what was
built; `docs/DEPLOY.md` covers Railway; `docs/ROADMAP.md` is the public to-do list.

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

- They keep notes in Telegram and send screenshots in batches of 5–10 items; work through a batch with a task list,
  commit and push after each group, and end with a plain report (what changed, what was and wasn't checked, and
  the questions that are theirs to answer).

## Rules for working in the repo

- Branch: **`claude/zen-feynman-ta1yra`** (this session's). The user merges it to `master` through PRs themselves;
  **don't open a PR unless asked**. At handoff `master` = `3650ea9` (PR #50) and the branch is 3 commits ahead
  (the last three batches below); they were about to merge.
- Latest migrations: `mainapp 0040_bulba_texting`, `users 0016_persona_pictures`. Nothing in the last batches
  needed a migration. Railway runs migrations on deploy.
- Commits end with the attribution lines from the session's system reminder. **No model identifiers** in commits,
  code comments or docs. Secrets only in Railway variables (`TELEGRAM_BOT_TOKEN` for Telegram sticker packs,
  `STATS_USERS` for who sees the stats page). The user's email is private.
- Commit only after the full suite passes (`... test --parallel 4 && git commit`), never chained with `;`.
- Static files: CSS/JS links carry `?v=N`; bump them when you change a file (some use a timestamp instead).
- Molfar.Vertep is AGPL: ideas only, never its code. No Gemini safety workarounds.

## Dev environment

- venv: `python3 -m venv <scratchpad>/venv && pip install -r requirements.txt`. Tests from `narrative/`:
  `python manage.py test mainapp users --parallel 4` → **1758 tests, all passing** at handoff (~2 min).
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
- Second test database for browser checks: `NARRATIVE_DATA_DIR=<scratchpad>/data python manage.py migrate`, then a
  small server script that seeds the demo user and starts `runserver 127.0.0.1:8765 --noreload` (run it **from
  `narrative/`**: the templates path is relative). Give the demo user a dummy `ConnectionProfile`, or the chat page
  sends it to the welcome page.

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
- **The Screen (TeleChat):** `mainapp/messenger.py` (thread data, prompts, turns, photos, stickers, memory, reminders,
  scene tracking "📍 Right now", continuity check, stories, worldbook for texting, gallery, linked chats),
  `views.messenger_api` (one endpoint, `action` switch), `static/mainapp/js/messenger.js` (the `TG` object),
  `messenger.css`, `templates/mainapp/messenger.html`; Bulba's messenger mode `bulba/texting.py`.
  `thread_data()` keeps **only known keys**: add a new field there or it's dropped on save.
- Garden/cottage: `tomato_garden.py`, `tomato_house.py`, `static/mainapp/js/tomato_garden.js`.
- Card search: `bulba/cardsearch.py` (Chub search + links, Janitor links; RisuRealm by file). Look contrast:
  `chat_looks.readable()`. Uploaded backgrounds/music: `media_library.py` (`library/` on the volume) and the stats
  page (`users/views.stats_library`).

## Built in this session (12–21 November), all on the branch, most merged

The full lists are in `docs/PLAN.md` (iteration 2 and 3 sections). In short:
- **Screen / TeleChat:** Bulba setup for texting (Modern AU or "As they are"), ideas, worldbook step, a persona
  step, new pictures; replies typed at the character's pace, typos, leave on read, reactions as replies, several
  messages before a reply, live "typing…" status; photos read by a vision model; photo moods (Daily, Sweet,
  Playful, Flirty, Bold) and picture styles; expression references; a +1 in photos; scene tracking with
  remembered places; reminders that fire; stories with posting habits, replies and reactions, memos after 48 h;
  Gallery; stickers (packs, custom, Telegram packs, emoji panel); memory with "out of view / all"; linked chats;
  a chat clock locked to the last message; the browser's time zone; the continuity check (with Bulba Watch);
  profile pictures (the user's choice, and characters changing theirs rarely); translation; Bulba suggestions
  everywhere (replies, pictures, statuses, bio, plans, art style).
- **Chat page:** lore highlights with tooltips; tracker rewind on regenerate/swipe; summary "N of M"; picture
  sizes (−/+); persona picture sized next to a cut-out sprite; loose colour tags fixed; readable custom looks.
- **Bulba:** card focus, one person / several / a world, story- and chat-specific personas (in seven parts), card
  search, web search in the messenger panel, the app map updated.
- **Platform:** analytics (weekly from Sunday or Monday, minutes split at midnight, browser time zone), uploads
  of backgrounds and radio music from the stats page, a ⚙ Setup menu in the top bar, the garden shelf and orders
  given by hand, a calmer cottage, a winter banner, 429 retries, thinking settings dropped when refused.

## Next (the user's words: "send it off with GPT's work on VN for the next chat")

1. **Plan E: story systems with story memory.** See "Next: story systems with story memory" in `docs/PLAN.md`
   (one trust instead of two, gates, knowledge triggers, scene clocks, promises coming due, familiar faces,
   chapter cards). Ask which to build first; nothing is built yet.
2. **Visual Novel mode:** another assistant (GPT) is working on it in a separate branch; the user will bring it.
   Its "moments" were meant to go into Moments; parked until then.
3. **Background cut-out on picture generation:** undecided. Green screen is risky for sprites (contrast); rembg
   costs roughly 200–400 MB of memory while it works; a plain white background is the cheap middle way. Ask.

## Never run against the real services yet (check on live, they're where things may break)

- Card search on Chub (its search address isn't documented and may have moved) and Janitor links (may be blocked
  for servers, or the card hidden). From the build machine both answered 403.
- Reminders firing (only while some page of the site is open), the continuity check, story replies, Telegram
  sticker packs (`TELEGRAM_BOT_TOKEN`), uploads on the stats page (`STATS_USERS` or staff), status pictures.
- Everything AI-driven was tested with faked responses only.
