# Handoff for the next Claude session (written 9 October 2026)

Read this first. It's what the previous long session knew: the premise, how the user works, how the
project is built, what's done and what's open. `docs/ROADMAP.md` is the public to-do list;
`docs/bulba/PLAN.md` is Bulba's design.

## Premise

**NarrativeAI** is a Django web app for roleplay with AI characters (SillyTavern-style: presets,
character cards, lorebooks, trackers), built as a university assignment ("Побудова AI продуктів", 2026)
on a two-week MVP deadline. Its centre is **Bulba**, a sarcastic talking-potato agent that:
- **onboards** people: asks about their taste in plain words, shows A/B samples written by *their own*
  chat model, and builds the preset, persona, character, lore, theme and extras;
- **supports** them inside any chat: finds why replies feel off and proposes one fix at a time.

Every change is a proposal with Apply / Edit / Not this / Undo. Bulba never sees API keys.

One-liner (EN): "NarrativeAI is a roleplay app where Bulba, an AI setup assistant, tunes the AI to how you
like stories told, so you never have to touch a technical setting."
(UA): «NarrativeAI — застосунок для рольових ігор з ШІ, де помічник Бульба налаштовує модель під ваш
смак, тож вам не доведеться торкатися жодного технічного налаштування.»

It's hosted on **Railway** (Docker, gunicorn 1 worker / 8 threads, SQLite with WAL on a `/data` volume,
WhiteNoise). Graders use a **demo account** whose character is **Il Dottore** (Genshin Impact, Omega
segment, after version 6.6). See `docs/DEPLOY.md`.

## How the user works (important)

- They're a business analyst who is vibecoding, not an engineer. Explain in plain words, ask
  clarifying questions, suggest next steps proactively, and **never reach a final conclusion without
  their input**.
- Their English is the working language; the course and slides are Ukrainian (video script and slide
  text in Ukrainian on request). The repo owner is referred to as "Anya" in the docs.
- They test on the live site and send screenshots of bugs; fix them small and fast.
- Test runs cost them money, so they prefer batching fixes before testing.
- Taste rules they've stated: normal fonts (no stylistic serif); story extras placed mid-text; no
  randomness for people who don't want it; Bulba borrows tested community wording before writing
  its own, and avoids AI-speak; long cards (up to ~6k tokens) must be possible; Dottore's lore is
  behaviour and facts, not a retelling (no Columbina, Sandrone or Nod-Krai entries); **no Traveler** in
  demo lore (the user may be the MC).

## Rules for working in the repo

- Branch: `claude/focused-dijkstra-7tv1w1`. **Open PR: [PineapplePatriot/NarrativeAI#8](https://github.com/PineapplePatriot/NarrativeAI/pull/8)**
  into `master` (the default branch; `main` is stale). The user merges; earlier PRs #1–#7 are done.
  If #8 is merged, restart the branch from `master` for new work.
- Don't open PRs unless asked. Never put model identifiers in commits or PRs.
- Commits end with the attribution lines the session's system reminder gives
  (`Co-Authored-By: …` and `Claude-Session: …`).
- **Secrets** (DEMO_PASSWORD, DEMO_OPENROUTER_KEY, DJANGO_SECRET_KEY, any keys) go only into Railway
  variables, never into chat, code, transcripts or Bulba. The old OpenRouter key was revoked long ago.
- The `.gitignore` ignores `*.json` with exceptions (data/library, data/demo/**, catalog.json,
  incoming/). New JSON data folders need an exception.

## Dev environment (rebuild it each session)

- `pip install -r requirements.txt` in a venv (the old one was in the old session's scratchpad).
  Django 5.2. Run tests from `narrative/`: `python manage.py test mainapp users` (**~770 tests, all
  passing** at handoff). Run `migrate` on the dev DB after new migrations (latest:
  `0030_character_voice_cast`).
- Dev server: `exec python manage.py runserver 127.0.0.1:8765 --noreload` in the background; restart
  after code or template edits. Stop it with `pkill -f "manage.py runserver 127.0.0.1:876[5]"` **in
  its own command** (combined with a start, pkill kills its own shell).
- Seed the local demo: `DEMO_PASSWORD='demo12345!' python manage.py seed_demo` (login demo / demo12345!,
  local only).
- Browser checks: Playwright at `/opt/node-tools/node_modules/playwright`, Chromium at
  `/opt/pw-browsers/chromium-1194/chrome-linux/chrome`. Use `page.route` to fake AI responses.
- **The build machine can't reach** OpenRouter, ElevenLabs, fandom wikis, tvtropes or rentry. Every
  AI feature is tested with faked responses; real runs only happen on the user's side.
- When a test command is chained with `&&`, check the test result itself (a failing suite once got
  committed because `tail` succeeded).

## Architecture map (`narrative/`)

- `mainapp/views.py`: the chat view (one big POST handler with `action`s: chat, swipes, edit,
  expand = "Write my message", ideas, voice, word_note, trackers, appearance…), the Bulba API (`bulba_api`),
  presets, worldbooks, cards, media, exports.
- `mainapp/presets.py`: preset format (blocks, triggers, utility prompts, samplers), assembly
  (`assemble(..., generation=)`), and SillyTavern import/export. `samplers.py`, `model_profiles.py`
  plus `data/models/*.json` (10 model profiles, with style notes and the cookbook's trial table),
  `starters.py` plus `data/starters/` (33 starters).
- `mainapp/chats.py`: chat files (JSON on disk) and message versions (swipes). `VERSION_KEYS =
  reasoning, game, audio`.
- `mainapp/game.py` (dice and inventory, function calling), `extras.py` (story extras, `[[extra N]]`
  markers placed mid-text, the ideas setting), `trackers.py` (Marinara-style trackers plus custom
  fields), `lorebook.py`, `cards.py` (V1–V3 cards), `regex_rules.py` (text rules), `thinking.py`
  (folds `<thinking>`), `voice.py` (ElevenLabs), `media_library.py` plus `static/defaults/`
  (20 backgrounds, 20 tracks, `catalog.json`).
- `mainapp/bulba/`: `agent.py` (the loop, setup tools, stages), `doctor.py` (in-chat Bulba),
  `actions.py` (Apply/Undo), `lore.py` (cards, lorebooks, themes, downloads), `tune.py` (samplers,
  trackers, greetings, card rules, lore settings, voices, mood pictures), `control.py` (who writes
  the user's character plus layout), `library.py` (tested wording from Realistic Frankenstein, Pura,
  Celia and the cookbook candidates), `editing.py` (Edit on proposal cards).
- `mainapp/data/bulba/`: `instructions.md` (setup), `doctor.md` (in-chat), `guides/` (asking,
  characters, extras, lore, presets, tuning, writing), `candidates.json` (the cookbook's 15 wording fixes).
- `mainapp/management/commands/seed_demo.py` plus `mainapp/data/demo/dottore/` (card.json, lorebook.json,
  theme.json with tagline, 9 transparent webp sprites).
- Templates: `mainapp/templates/mainapp/` (chat_page, bulba, presets, add_character…),
  `templates/guide.html` (`/main/guide/`). JS and CSS in `mainapp/static/mainapp/`.

## The agent (Bulba)

**Loop** (`agent.run_turn`): the context (instructions, stage guides, model knowledge, and a session line
with the real current state: stage, budget, who writes the character, layout, preferences, proposals)
→ the model calls tools (up to 8 rounds) → the turn ends on a "turn-ending" tool (choices, samples,
proposal) → the user answers or presses Apply/Edit/Undo → repeat. The stage moves forward automatically
when proposals show progress (`advance_stage`). Each session has a budget (default $5).

**Setup stages:** extras → how replies read (basics form plus A/B samples) → preset → you in the story →
your character (card import or writing, compact/detailed/all out; lore from wiki research; theme;
pictures) → story extras (dice, extras, ideas, trackers) → done (summary, where to change things,
downloads).

**Tools (35):**
- Talking: offer_choices, show_basics_form, set_stage.
- Taste: write_samples, record_preference.
- Knowledge: get_current_setup, get_starter, find_practice, read_practice, look_up (web search).
- Setup: propose_extras, propose_preset, propose_persona, propose_character, propose_control.
- Cards and lore: offer_card_upload, work_on_character, propose_card_edit, read_lorebook,
  propose_lorebook, propose_lore_edit, propose_greetings.
- Look and sound: propose_theme, read_voices, propose_voices, offer_mood_pictures.
- Tuning: read_settings, propose_samplers, propose_trackers, propose_card_rules, propose_lore_settings.
- Chat only: read_block, propose_preset_edit, retry_reply (its rewrite has "Use this in the chat").
- Handover: offer_downloads.

**Chat-model functions:** roll_dice, change_inventory, change_conditions; show_document,
show_messages, show_news, note_milestone, note_keepsake, suggest_actions.

**Goals.** Onboarding: find taste without jargon, build from tested wording, make persona and character
(canon-accurate), offer fitting extras, hand over. Support: understand the complaint, find the cause first
(preset → card → context → wording → model), make the smallest fix, preview it, keep what works.

## Platform features (built)

Chat with swipes, branches, edit/delete; a book layout for director mode; streaming with a thinking
display; the pen menu (director's note plus "Word it for me", pinned note, story memory, actions,
per-chat settings); "Write my message" (impersonate through the preset); Bulba's ideas button (an extra);
story extras; dice and inventory; trackers (HUD plus panel; custom fields); summaries; sprites with an
emotion picker (transparent sprites stand in the scene); character themes (background, music,
dialogue colour, tagline); built-in media; voices (🔊 per reply, ElevenLabs Text to Dialogue with a
narrator and per-speaker voices, cast list, auto-picked voices kept per chat, saved per version);
presets and samplers pages with ST import/export; text rules; worldbooks; card import/export; a tag
filter; in-place rename; the guide page; $25/month spend cap; phone layout checked.

## Open gaps

- **Never run against real services:** Bulba's newer tools, the ideas button, voices (also: is
  Text to Dialogue allowed on the free ElevenLabs plan? exact v3 credit cost?), the mood-picture maker,
  and the "Write my message" fix. The user tests live.
- **Unresolved question:** the book layout didn't switch on after a director-mode setup. Is the cause
  the preset apply path (control preference from the basics form) or that director was chosen later
  in conversation? Asked the user, no answer yet. Bulba now sees the real layout and can propose it.
- Verify OpenRouter IDs for 8 of the 10 model profiles (`openrouter_id_verified: false`).
- Rebase starters on the Evening-Truth presets (needs the files; rentry is blocked).
- Cookbook parts not in yet: the three original bundles (character-focused / scene-driving /
  state-assisted), the keepsake ending / epilogue extra, recurring rituals, the stable-prefix (caching)
  advice, and a per-fix instruction record.
- Export a card with its sprites; a picture mid-scene as a story extra; images in display rules
  (needs a safety design); group-only greetings (delayed until groups exist).
- An Edit option on settings-like proposals (extras, trackers, theme, voices): offered, not decided.
- Leftover comments from the original code in `views.py`.
- Later: their own endpoint, keys and wallet instead of per-user OpenRouter keys.

## Presentation materials already made (in the old chat)

- Video (60 s: user's pain 0–10, main scenario 10–45, result 45–55, limitation 55–60) with a Ukrainian
  voice-over script. The limitation they chose: «Кожен крок Бульби коштує трохи з вашого ключа
  OpenRouter. Ми радимо найкращі моделі, але ідеальних немає.»
- The agentic loop and goals text (above). Not made yet but offered: a loop diagram image, Ukrainian
  slide text, and an .srt subtitle file for the video.
