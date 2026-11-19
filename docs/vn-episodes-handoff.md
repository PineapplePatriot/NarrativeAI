# VN episode integration

Work branch: `codex/vn-scene-continuity`, based on Gemini's
`feature/digital-screen-telechat` and master through `6c228d8`.
TeleChat's current code and controls are retained. Subtext is carried over unchanged.
The small addition to `messenger.js` exports live state, escaping/formatting and the
chat renderer for other Screen apps, and emits `telechat-rendered`. VN previously
expected those exports, but they did not exist on either source branch. VN notices
have their own status area rather than depending on a nonexistent `TG.toast`.

## What this pass changes

- Mount the missing Scenes screen and audio element; fix generated choice clicks.
- Write complete narrative blocks without sentence or line quotas, then split them into
  display boxes without dropping words. The launch form accepts episode writing preferences.
- Carry the originating thread's persona, scenario, earlier memory, recent messages and
  story clock into the episode. Include the core character cards and honour memory sharing.
  VN uses general model counters and the user's writing tastes, without phone-only rules.
- Retain the full transcript. A cumulative continuity record carries setting, time,
  outfits, positions, unresolved matters and earlier events into later generation.
- Keep dialogue attribution separate from the character shown on stage, so a listener's
  reaction does not turn into their dialogue. Reject generated speech for the user or
  unknown participants rather than silently attributing it to the first character.
- Optional Bulba polish uses existing approved habits and checked find/replace repairs
  before display splitting. Preserve the original changed block for inspection.
- Use a separate sprite cache for scene outfits and shared/default characters. A costume
  change cannot overwrite a regular character expression. Finale illustrations receive
  primary references for each participant before extra references, within the existing
  five-image provider limit, plus explicit outfit and setting information.
- Resume at the saved reading position. Reject replacing an open episode and reject
  stale scene-generation results after another request changes the episode.
- Save an episode without an image. An image-provider error still archives the episode
  and returns its summary to TeleChat, with a visible warning. Archive and phone handoff
  commit in one database transaction.

## Verification

```sh
cd narrative
../.venv-pinned/bin/python manage.py test mainapp.test_messenger mainapp.test_messenger_actions mainapp.test_vn_scenes
```

With Playwright and Chromium installed, from the repository root:

```sh
CHROMIUM_PATH=/usr/bin/chromium node scripts/check_vn_ui.cjs
```

The browser check uses local fixtures and production renderer/CSS at phone and desktop
widths. Backend tests mock model and image calls. These checks establish application
behaviour, not live model writing quality or image identity fidelity.
The integrated Screen page was also checked in a local Django server with a disposable
database and seeded episode at both widths: the Scenes tab, dialogue and choices render
without JavaScript errors or horizontal page overflow.

## Remaining work

- Continuity records and reference instructions improve conditioning; image identity,
  anatomy, composition and compliance still need live provider evaluation. Multi-character
  scenes exceeding five participants cannot give every character an image reference.
- Only one active episode per user is currently supported. State and gallery still use
  `ChatSettings.appearance`; a dedicated episode/asset model is the next storage step.
  The existing gallery retains at most 60 entries; this pass removes transcript truncation
  within an episode, not the gallery retention limit.
- Bulba's existing approved polish and taste instructions are connected. A dedicated VN
  conversation/tool interface for changing directions or repairing earlier turns is future work.
- Scene changes select existing backgrounds; custom generated backgrounds and consistent
  camera views of a location still need a location asset workflow.
- Subtext's character knowledge boundaries and its prescribed gossip/conflict tone are
  not changed by this VN pass.

## Adult-content image provider

No new provider or safety bypass is installed. Public provider-policy lookups failed
with a cloud network proxy 403 during this pass, so no provider was verified or selected.

Before selecting one, verify both its API and its published policy: consensual adult
erotica must be permitted; sexual depictions of minors, nonconsensual sexual content,
and nonconsensual sexual likenesses must be prohibited. Distinguish fictional characters
from identifiable real people. Check reference-image handling, retention, moderation
behaviour and reporting mechanisms. A published prohibition is not evidence of reliable
automatic detection: input and output safeguards need separate validation.

Provider blocks should remain visible and should not trigger a fallback to a less
restrictive provider. Saving the episode independently of its illustration avoids making
a block or an outage destructive to story progress.
