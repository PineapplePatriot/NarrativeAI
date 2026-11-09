# Primary-source preset audit — 9 November 2026

Status: partial primary-source verification. Reddit and Rentry are blocked by the current
network policy. The user's short Reddit link has not been resolved or read in this pass.
An older research file describes a fourteen-preset comparison; its table is not substituted
for the supplied live post or treated as fresh trend evidence. No model calls were made.

The accompanying artifact manifest records exact commits, paths and SHA256 values for seven
freshly retrieved creator artifacts. We inspected prompt text and order metadata, not only
research summaries. Order-enabled, prompt flags, macro evaluation and runtime model adherence
are different layers; no claim of a complete SillyTavern runtime replay is made.

## Findings relevant to MiMo and our baseline

### Pura 16.0: a specific ban, plus a potentially counterproductive replacement rule

Primary artifact: [creator repository](https://github.com/platberlitz/platberlitz.github.io/tree/d548baa41899fb0bdd22c8325bfba5af633afe5d).
Main prompt and Grounded Prose Rules were inspected. The latter is off in the 100001
prompt-order configuration; its presence is not evidence that a default import uses it.

The optional rule explicitly names mouth open-close cycling. This directly supports the user's
identification of a recognized pattern rather than a Ukrainian-specific defect. However, it
also says to replace unwanted material with one concrete observable detail. Its suggested
alternatives include grip, gaze, breath, voice and object handling. That is a plausible route
to substitution rather than omission, not demonstrated causation or a defect in Pura as a whole.

The creator's main prompt gives dialogue a communicative purpose and allows quiet interaction
and optional questions/complications. Those principles are more relevant to our baseline than
copying the optional exclusion module intact. The README lists MiMo V2.5 Pro, not specific
MiMo 2.6 validation. Its Kimi caution names K2.6 and must not automatically be applied to K3.

Fresh artifact comparison: all 59 block names shared with NarrativeAI's stored Pura library
have identical content. This supports the fidelity of that stored material. It does not
establish that NarrativeAI uses the same toggles or assembles the same request.

### Sola: anti-slop can coexist with instructions eliciting physical tells

Primary artifacts and README: [creator repository](https://github.com/pyrxpia/sola-hub/tree/eae025e76015345294bc2c59feeae3caaf842bab).
Kindling V2 and Flame V4 ST files were retrieved and inspected. Kindling's Oath contains
anti-slop guidance, including avoiding padding and repeated sentence starts, but also directs
attention to physical tells and gaze. Its Easel template asks for a sensory anchor and includes
physical-reaction examples. Whether those fields help or encourage recurring filler is an
experimental question; an anti-slop label alone does not resolve the interaction.

The current Kindling file has its Romanticism and Easel blocks enabled in both their own flags
and prompt-order metadata despite OPTIONAL in their names. Flame's README says Riot is enabled
on import, and Golden is selected by disabling it; the downloaded order confirms Riot selected.
A recommendation for Sola must therefore identify version, selected mind, modules, and review
procedure. This is not a measured recommendation for MiMo 2.6.

### DEM V3: model setup is part of the preset

Primary README and ST artifact: [creator repository](https://github.com/lsennn/Deus-ex-machina/tree/5fb7ad39de33f191a4aaf61d138f91e40d7b2526).
The README specifies low/off reasoning for most configurations, with different planning
requirements for GLM 5.3 and Argon. Its general setup lists MiMo 2.5 Pro, not MiMo 2.6 Pro.
This does not justify changing NarrativeAI's MiMo 2.6 reasoning setting without an endpoint-
and mode-controlled comparison. Scene Plan and Thinking FALLBACK are alternatives, not two
independent quality improvements to enable together. The downloaded artifact contains both
as separate choices.

The Undercurrents documentation explicitly distinguishes possible routes from accepted events
and allows quiet replies. This supports conditional initiative rather than mandatory changes.
The repository states CC BY-NC-SA 4.0; this audit records mechanisms and short observations,
not permission to bundle its implementation text. The artifact's a4ae6343 fingerprint matches
the earlier research extraction: fresh verification confirms those retrieved bytes.

### Nemo: optional anti-slop and story-state architecture are different decisions

Primary README and artifacts: [creator repository](https://github.com/NemoVonNirgend/NemoEngine/tree/986dd7f5395a81cef2b90c4de6d2c8bb13130edf).
Vivarium's README calls its anti-slop module optional and disabled by default. Its JSON agrees:
Slop and Friction have disabled flags. A favorable Vivarium experience cannot automatically
be attributed to either module. Magpie's README stresses ensemble continuity and choosing
alternatives deliberately, not enabling all ledger and planning modules. Neither README
inspected here establishes a MiMo 2.6 success rate. Both artifact fingerprints match the earlier
research extraction (7e55e6c1 and eb63f6bb), confirming those specific versions.

### Writer's Block: separate preference axes; recommendation scope matters

Primary README: [creator repository](https://github.com/deiomo/Writer-s-Block-Unlimited/tree/8b033e1393519d7aeb242334273ee1ea5e1d0047).
It exposes sentence rhythm, figurative-language frequency, show/tell, dialogue, and character
change resistance separately. Its model recommendations are explicitly about following its
CoTs and name GLM versions, Opus 4.6, Longcat, Gemma, and Kimi 2.5; they are not a MiMo 2.6
prose ranking. The README itself says to check the latest Reddit release for current news.
That release remains unread in this pass because of the network restriction. No current
Writer's Block JSON was downloaded or audited here.

## Consequences for NarrativeAI

Keep the baseline's permission to omit unnecessary text; do not force a replacement detail.
Inspect the actual resolved request, including optional modules, card, history and reasoning
route, before blaming MiMo or adding bans. Keep stylistic preference distinct from filler:
inner narration, humor and imagery can remain without generic emotional annotation.

These sources support the architectural choices in the candidate baseline. They do not prove
that its wording improves MiMo. No further changes to production prompts were made from this
partial audit. A full macro/default-resolution audit and matched generation comparisons remain
necessary before describing a particular assembled candidate as effective.

## Blocked research and next comparison

The environment draft now preserves openrouter.ai and proposes access for reddit.com,
www.reddit.com, rentry.org, platberlitz.github.io, pyrxpia.github.io, huggingface.co and
gist.github.com. It is saved, not applied or published. GitHub-hosted source retrieval worked.

After access is applied: resolve and read the supplied Reddit post and comments; follow its
MiMo recommendations to creator pages; retrieve the latest Evening-Truth and relevant RF/FF,
Chatfill, and Ancient Access artifacts; check exact model/mode/version claims and dependencies.
Do not call a preset popular or trending merely because it is listed in an older comparison.

For MiMo, compare original Evening-Truth, our lean base, base plus one semantic repair, and a
creator-configured modular candidate. Keep character/history/provider/reasoning fixed first,
then vary reasoning in a separate comparison. Use several turns and the user's Ukrainian case
plus meaningful exceptions. Score substitutions, dialogue purpose, actual response, rhythm,
character continuity and preference independently. Counts of banned strings are insufficient.
