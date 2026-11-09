# Original experience family: implementation and handoff

The public catalog now contains 33 original configurations: three experiences for each of the eleven
supported models. Components are stored in data/bulba/experience_presets.json, based on the user's
original experience pack and the agreed design. It is a research-informed prototype, not a set of
live-validated model optimizations.

## Assembly

- Shared narrative foundation: one Writing quality block, without duplicating it in Roleplay.
- Explicit, overridable presentation defaults: present tense, third person, discreet narrator and
  textured prose; scope stops naturally rather than at a fixed count. No language policy is imposed.
- Model foundation: narrative organization for Claude/Gemini/MiMo; explicit knowledge/intention/state
  distinctions for Kimi/GLM/DeepSeek. These are original prose instructions, not hidden ledgers or CoT.
- One experience: Conversation & Chemistry, Character Drama, or Immersive Storytelling, in Style.
- One original Your character contract: player control, shared authorship, or directing.
- Existing model-specific corrective defaults: independently editable Model pattern counters.
- Optional Adventure & Ensemble and Continuity & Simulation blocks, both initially disabled.
- Existing taste, length, formatting and explicit-exclusion customization paths.

Experiences impose no new language or translation policy, fixed word count, dialogue ratio, sampler,
or compulsory state interface. Compatible technical settings and context markers are reused from
the prior authored model configuration; its narrative instructions and third-party blocks are not
copied into the new presets. A disabled, independently worded mature-content option is preserved.
No source scripts, UI assets or complete Pura/Sola modules are shipped by this new family.

## Entry points

The preset page and welcome page display experiences with a separate authorship selector and optional
extensions. The preset page initializes authorship from the selected saved preset. Server-side creation
also preserves the current mode when callers omit it; an explicit mode replaces it. Every use creates
an owned copy instead of rewriting an existing preset. Directing may use any experience.

Bulba's new quick-setup choices are the same three experiences. A confirmed authorship preference is
preserved; otherwise player control is the default. Custom setup can select extensions with the
propose_preset tool. get_starter returns enabled states and contents of all original prompt components
so Bulba can inspect the actual configuration before adding a command. Model knowledge recommends
only the original experience catalog to new sessions.

Original contracts are independent of the legacy Pura mode blocks. Switching modes preserves enabled
extensions and replaces one authorship contract, rather than stacking contradictory permissions.
Existing impersonation behavior excludes the Your character block for its special one-turn request.

## Compatibility

Legacy starter files and IDs remain resolvable for old proposals, links, imports and saved metadata.
They are not part of the new public catalog. Legacy quick links still work; their prior behavior is
retained. Existing user presets are never automatically migrated. Tests asserting the public catalog
were updated from three old experience categories plus community artifacts to three original
experiences per model. Legacy behavior tests remain.

No translation backend, profile schema or bilingual synchronization behavior changes in this commit.
Some shared views and welcome UI files necessarily overlap Claude's work; cherry-pick or merge those
changes carefully while preserving its language integration.

## Verification and limits

Tests cover all 33 configurations, supported request assembly, each experience with all three
contracts, independent extensions, switching modes, original/legacy lookup, preservation of old
saved data, and preset API submission. A headless Chromium fixture renders the actual preset page
and script to check labels, independent directing/extension selections and submitted request data.
Its POST is mocked; separate Django tests exercise persistence. No paid model samples were generated.

The user pack's experience samples can inform Bulba's existing taste conversation; this commit does
not add a new live three-way comparison wizard. Visible numbers and deterministic state mechanics
remain application features, not effects guaranteed by the Continuity & Simulation prose extension.
The provisional foundation mapping and creative quality still require later user feedback or live
comparisons; neither is claimed to follow from structural tests.
