# Screen lore and VN episodes

Integration branch: `codex/vn-scene-continuity`, based on Gemini's
`feature/digital-screen-telechat` and master through `6c228d8`.

## Chat-specific lore

Each messenger chat can use its own lorebook, inherit character books, or disable lore.
A copy from the user's library becomes independent of the source. Local entries use the
existing lore matcher, including its settings, entry switches, keywords and token budgets.
The same chat selection is used in phone replies and VN requests.

Changing a modern character's setting immediately offers lore setup in each affected chat.
The existing local book is preserved for review, but lore is suspended until the user
chooses how to proceed. New chats for an already-modernized character also offer setup.
Existing modernized chats without a lore selection are initialized on access. In-flight
reply saves preserve later lore edits, and undoing a modernization restores its prior lore flags.
Appearance-only and voice-only changes do not retrigger it.

The phone's lore panel supports manual entries, copying a library book, reviewing a Bulba
draft, and inspecting matched entries. Bulba's messenger conversation can also propose a
chat lorebook through an Apply/Undo card. A generated draft does not apply itself. Neither
path changes original character cards or library books.

## VN writing and interaction

VN requests now use the normal preset assembler: enabled blocks, macros, generation
triggers, available character/persona/scenario/history slots, lore placement and samplers.
The VN character slot receives the full card rather than the phone's shorter card excerpt.
Its previous helper-writing baseline is not appended a second time: writing preferences
and model counters come from the selected preset, while approved polish remains optional.
The presentation contract supplies structured JSON and the explicit authorship/interaction
mode. Disabled preset blocks remain disabled. The scene retains a prepared-request trace
with model, preset, messages, parameters, source labels, lore matches and assembly notes.
Connection credentials are not included.

Interaction modes are independent of authorship:

- **Classic choices:** select suggested options.
- **Write yourself:** free input; suggested choices are suppressed.
- **Mixed:** either options or free input.
- **Roleplay authorship:** the model cannot speak or decide for the user's character.
- **Directing authorship:** the user's persona joins the cast as `user`, with the user's
  profile sprites; the model may write that character under the user's direction.

Writing length follows the preset and episode directions. Complete narrative blocks are
split into display pages after optional Bulba polish; there is no sentence or line quota.
Changed blocks retain their pre-polish text for inspection. Episode directions, interaction
mode and authorship can be changed under Episode preferences.

## Passage-level continuity and revision

Every generated passage has a visual state and a checkpoint before it. Changes to background,
music, location, outfits, positions or continuity apply at their passage, including when
reading backward. An ending summary is not applied to earlier passages. Unknown assets
retain the previous state; an unknown opening asset uses silence/no backdrop rather than
an arbitrary setting. Manual stage choices affect the selected passage.

The speaking character and the character shown on stage are independent. Outfit-specific
sprites use a separate cache and do not overwrite normal expressions. A custom expression
updates the selected passage. Illustrations receive participant reference identities,
including the user's character when a reference is available, within the provider's existing
five-reference limit. Image identity and composition remain best effort and need live evaluation.

Passage tools provide:

- **Edit:** retain the typed text, ask Bulba to update continuity from the retained prefix,
  and remove the old continuation. This uses Bulba tokens; the button states that explicitly.
- **Regenerate from here:** restore the preceding checkpoint and use the active preset's
  regeneration rules. This uses the chat model.
- **Branch after this passage:** create a separate episode and phone thread without a model call.
- **Versions:** recover the original before an edit, regeneration or branch. Restoring a
  version creates a separate phone branch.
- **Completed episodes:** reopen new-format episodes as a separate branch.

Operations apply to complete passages, which may span multiple display pages. Failed edits
or generations leave the original intact. Discarded future passages and their continuity
are not sent to the replacement generation. Branches copy the lore configuration in force
at the fork, independently, while phone history comes from the original transition snapshot.
Stale tab/revision requests are rejected.

Full transcripts are retained, and the former silent 60-episode gallery limit is removed.
Completing an episode does not require an image. An image-provider error still saves the
story and phone memory handoff, with a visible warning. Archive and handoff commit together.

## Verification without model spending

From `narrative`, run the affected backend tests:

```sh
../.venv-pinned/bin/python manage.py test mainapp.test_screen_lore mainapp.test_vn_workflow mainapp.test_vn_scenes mainapp.test_messenger mainapp.test_messenger_actions mainapp.tests.BulbaTextingTests
```

With Playwright and Chromium installed, the standalone production-renderer check is:

```sh
CHROMIUM_PATH=/usr/bin/chromium node scripts/check_vn_ui.cjs
```

An integrated browser check uses a dedicated fixture in a disposable database. From
`narrative`, create the data directory, migrate it, seed it, and run the local server:

```sh
mkdir -p /tmp/narrative-screen-check
NARRATIVE_DATA_DIR=/tmp/narrative-screen-check ../.venv-pinned/bin/python manage.py migrate --noinput
NARRATIVE_DATA_DIR=/tmp/narrative-screen-check ../.venv-pinned/bin/python manage.py shell -c 'exec(open("../scripts/seed_screen_workflow.py").read())'
NARRATIVE_DATA_DIR=/tmp/narrative-screen-check ../.venv-pinned/bin/python manage.py runserver 127.0.0.1:8765 --noreload
```

Then, from the repository root in another terminal:

```sh
VN_TEST_URL=http://127.0.0.1:8765 VN_TEST_SESSION_FILE=/tmp/narrative-screen-check/browser-session.json CHROMIUM_PATH=/usr/bin/chromium node scripts/check_screen_workflow.cjs
```

The browser check exercises chat-lore editing, passage visuals, interaction modes and
branching at 390px and 1280px. Model-generating actions are blocked by its request routes.
Backend model/image responses are mocked. These checks establish application behaviour,
not live model writing quality, lore authoring accuracy or visual fidelity.

## First small paid test

Keep automatic image generation off. Use one character and a short chat-local book with a
recognizable fact. Move phone → episode → phone, checking voice, remembered facts and lore.
Try a location/outfit change midway through a turn; then edit or regenerate an earlier
passage and inspect the request for discarded future facts. Test directing and multiple
characters after that. Add illustration generation last.

## Remaining boundaries

- Language/translation integration remains in the backlog for both phone and VN.
- Only one active episode per account is supported; versions can be switched explicitly.
- Episodes, transcripts, request traces and versions still live in `ChatSettings.appearance`.
  They need dedicated episode/asset storage before substantial account histories accumulate.
  Removing silent retention is not a storage-scaling solution.
- Earlier episodes without historical checkpoints remain readable. Unsafe historical edits
  are rejected instead of pretending a past state can be reconstructed. New passages have checkpoints.
- Scene changes select available backgrounds. Consistent generated locations and camera views
  still need a separate location-asset workflow.
- The small TeleChat JavaScript interface exports shared live state, formatting and rendering,
  plus `telechat-rendered`. New lore/editor UI lives in separate scripts to ease Claude's UI work.
- Subtext's knowledge boundaries and prescribed gossip/conflict tone are unchanged.
- No adult-content image provider has been selected or enabled. Provider policy lookups in the
  earlier pass failed with a proxy 403. A candidate must document permission for consensual adult
  erotica and restrictions on minors, nonconsensual sexual content and nonconsensual likenesses;
  policy wording alone does not establish reliable input/output safeguards. Provider blocks
  must remain visible and must not cause fallback to a less restrictive provider.
