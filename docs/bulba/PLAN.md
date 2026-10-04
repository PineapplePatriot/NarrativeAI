# Bulba: build plan (draft for discussion)

Status: agreed direction, 3 October 2026 (decisions below). Nothing here is built yet. Research lives in `research/`
(start with `research/research-summary.md`). This plan turns that research into pieces of this app.

## What Bulba is

An assistant inside NarrativeAI that sets up a person's roleplay so it writes the way they like,
without them needing to know what a preset, sampler or prompt role is.

- **Setup mode, once:** right after someone connects an AI. Two doors: *Quick start* (pick a
  ready-made setup and start chatting) or *Guided setup* (the six-stage interview from the research).
- **Afterwards, a panel with chat:** "my replies are too long", "she keeps sounding like a therapist",
  "make me a lorebook for this world". Bulba diagnoses and changes the setup.
- **What Bulba works on:** presets (its main job), connection settings, character cards, lorebooks
  and the user's persona.

## First-run flow (agreed 4 October 2026)

1. **Welcome page** (built): the OpenRouter key and one question, "Which model would you like to chat
   with?", with the 10 models from the research and a line on where each shines. The full Connections
   page stays available for advanced setups.
2. **Bulba pops up** (a slightly sarcastic talking potato; runs on MiMo v2.6 Pro for now, chosen by
   us) and loads the knowledge for the chosen model only. The MVP knowledge base covers these 10 models.
3. **"No thanks"**: pick a ready-made preset and set the feature checkboxes yourself.
   **"Yes"**: Bulba asks about the extras (voices, summary, trackers, sprites), then runs the
   writing-preferences loop (samples always from the chosen model), creates the preset, and finally
   settles the rest of the profile: persona touch-ups, connection profiles (e.g. a cheaper model for
   summaries) and a character to chat with. Then you just go and chat.

## The first models

Claude Opus 5.5 and MiMo v2.6 Pro. Everything is built per model so the rest (Kimi K3, Fable 5.1,
Gemini 3.8 Flash, GLM 5.3, DeepSeek, Opus 4.6/4.7) can be added by writing new model files, not code.

Facts from the research that already shape the starters:

| | Opus 5.5 (`claude-opus-5-5`) | MiMo v2.6 Pro (`xiaomi/mimo-v2.6-pro`) |
|---|---|---|
| Reasoning | Always on (adaptive); effort low → max, default medium | Thinking or non-thinking mode |
| Temperature / top-p / top-k | Not adjustable (only defaults accepted) | Fixed at 1 / 0.95 while thinking; adjustable without thinking |
| What a user can meaningfully tune | Reply length, reasoning effort | Reply length, thinking on/off, temperature only when thinking is off |
| Community base to link | Pura's Director 16.0 (author: platberlitz) | Evening-Truth MiMo 2.6 prompt (author: Evening-Truth) |
| Research note | No source establishes the best preset length; your observation that short presets and some negative rules work well is a hypothesis to test | Author recommends under-500-token replies with a larger output allowance; settings to verify against the endpoint |

## The pieces

### 1. Knowledge Bulba reads (files, no code)

Kept in the repo under `narrative/mainapp/bulba/` so they are versioned and reviewable:

- **Model profiles**, one file per model (`models/claude-opus-5-5.json`, `models/mimo-v2-6-pro.json`):
  - *capabilities*: exact IDs per provider, which settings are accepted/fixed/ignored, reasoning
    controls, context/output limits, sources and the date they were checked.
  - *temperament notes*: how the model tends to write, from `research/05-model-styles.md`
    (community reports with dates and links) and your first-hand notes (Opus 5.5: banter and
    emotional development; Fable 5.1 calmer with dark fiction in your setup), each labelled with its
    source and kept as a hypothesis until tested. Includes the model's *onboarding probes* (for MiMo:
    "Should affection make them easier to deal with, or should some of their difficult habits remain?").
  - *starters*: which preset implements each experience on this model (see 3).
- **Interview guide** (how to ask): condensed from `research/03-taste-elicitation.md` and
  `research/agent-instructions.md`: one question at a time, plain language, A/B pairs that change one
  thing, always allow both/neither/mix/skip/edit, preference records with scope and status.
- **Preset-writing guide** (how to write presets): new, not in the research. Our preset format
  (blocks, slots, placement, depth, macros, send-as modes), how much text each part should take,
  how to fix a complaint (find the conflicting instruction first, change one thing, keep a working
  version), when a short negative rule is fine, and what each model needs differently.
- **Test character**: `research/test-character.json` (Mara Voss), imported as a demo character.

### 2. Model capabilities in code (useful even without Bulba)

Replace today's single "locked samplers" pattern with a lookup of the model profile by the
connection's model ID. The Samplers page then shows only settings the model actually uses, with a
short reason for the hidden ones ("Opus 5.5 always uses its own temperature"), and requests never
send settings the model ignores. Unknown models keep today's behaviour, marked "not verified".

### 3. Starters: 3 experiences × 10 models (built 4 October 2026)

From the research's starter design, with the model-specific flavour you asked for:

| Experience | What the user gets | Opus 5.5 version | MiMo version |
|---|---|---|---|
| Back-and-forth | Short exchanges, an obvious opening for you | Short preset, leans into banter and emotional beats | Based on Evening-Truth MiMo, short replies |
| Rich scene | Atmosphere, subtext, room for feelings | Medium preset with interiority and pacing rules | Evening-Truth base plus scene-detail block |
| Director seat | You steer the cast, it writes fuller scenes | Based on Pura's Director modules | Evening-Truth base plus director permissions |

Each starter is a normal preset in our format (so it shows up on the Presets page and exports to
SillyTavern), plus its samplers and a "source" note linking the original author and version. We write
our own adapted text based on these presets; the authors are credited and linked, not redistributed
wholesale. You and I reword them after the MVP.

### 4. The agent itself

- **Two models, two jobs.** Bulba itself (the conversation, the questions, writing and editing the
  preset) runs on a model *we* pick and keep fixed. **Every writing sample** (A/B pairs, drafts, the
  final test) always comes from the model the user will chat with, through their own connection.
  No silent fallback for samples; if a call fails, the work is kept and you can retry. This differs
  from the research ("the selected model writes the setup") on purpose: it keeps Bulba consistent and
  cheaper, while the user still only ever judges real output from their own model.
- **All traffic through OpenRouter** (`xiaomi/mimo-v2.6-pro`, `anthropic/claude-opus-5-5`). The direct
  Xiaomi API is not recommended by the community for RP.
- **Tools** (function calling, which OpenRouter supports for both models). Bulba never sees API keys.
  - Read: presets, the active preset, model profile, characters, persona, lorebooks, connection
    settings (without keys), the last messages of a chat (only when you point it at one).
  - Generate: `try_setup(draft, scene, character)`: runs a draft preset through the real request
    builder with the target model, to produce live A/B samples and the final test.
  - Propose changes: create or edit a preset, samplers, persona, a character or lorebook entries.
    **Changes are proposals**: you see what changes (like a diff) and press Apply. Undo keeps the
    previous version.
- **Memory per user**: the conversation, the current stage, preference records (your wording, what
  Bulba thinks it means, scope, firm/flexible, tentative/confirmed, evidence) and draft versions.
  You can see, edit and delete every preference.
- **Costs visible**: show a running total per session, with a default **$5 limit** (adjustable)
  covering guided sessions on expensive models (Opus, Fable).
- **Voice**: friendly and plain, a little sarcastic, never trying too hard.

### 5. The Bulba page and panel

- `/bulba/`: setup mode with Quick start and Guided setup, the chat, A/B cards
  (A · B · both · neither · mix · skip · edit), your preference list, and the draft setup with
  an Apply button.
- Later: a Bulba button in the top bar and inside the chat page, opening the same conversation as a side
  panel with the current chat as context.

### 6. Handover and export

Apply makes the setup active (preset + samplers + connection choice). Export: our native bundle
(`research/native-setup.schema.json`) and the existing SillyTavern export, with a list of anything
that didn't transfer. Never any keys.

## Order of work (each step testable on its own)

1. Model profiles for Opus 5.5 and MiMo, plus the capability lookup and the Samplers page cleanup.
2. The six starters and a "Starters" section on the Presets page (Quick start works here already).
3. Agent runtime: the Bulba task, tool calling in the AI client, tools, stored state, proposals with
   Apply/Undo.
4. The Bulba page: setup mode, chat, A/B cards, preferences, draft setup.
5. The guided interview flow and the preset-writing guide wired into Bulba's instructions.
6. Handover: fresh test with the finished setup, apply, export.
7. A small pilot with you as judge (the research's protocol, scaled down), then more models.

## Decisions (3 October 2026)

1. **Voice:** a little sarcastic, mostly just not trying too hard.
2. **Apply:** Bulba proposes, you press Apply (a safeguard), with Undo.
3. **Model notes:** `research/05-model-styles.md` plus your first-hand notes above.
4. **Provider:** OpenRouter only.
5. **Spending limit:** $5 per guided session by default, adjustable.
6. **Models:** Bulba runs on a model we pick; writing samples always come from the user's chat model.
