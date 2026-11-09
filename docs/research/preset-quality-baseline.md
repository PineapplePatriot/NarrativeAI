# Common writing safeguards and scoped repairs

## Problem found in the implementation

The authored starters used broad exclusions while sometimes requiring the behaviors those
exclusions were meant to prevent. Short variants imposed reaction/dialogue/action ordering.
Several rich variants required a change on every reply and associated emotion with physical
tells. That encourages recurring structure independently of vocabulary. The earlier MiMo edit
addressed one model but left similar instructions in other models' variants.

The preset guide also claimed starter coverage without verifying a distinct common baseline,
and its example for immersion required physical detail per reply. The implementation now
provides an actual Writing quality block and removes contradictory examples and prescriptions.

## Source synthesis and evidence limits

This is a synthesis of the supplied research and repository source artifacts, not a fresh
popularity survey or a claim that current leaderboards rank literary quality. The main inputs
are the original Evening-Truth MiMo JSON supplied in this conversation, Pura 16.0 and RF blocks
already in the repository, the preset instruction cookbook, the newer-rules extraction and
the November model-slop guide. The latter reports no live model evaluation; neither do we.

| Source mechanism | Adopted principle | Rejected automatic transfer |
| --- | --- | --- |
| Evening-Truth role/interaction/style scopes | Direct instructions with a defined purpose; sequential action | Identical content assumptions and tracker output for everyone |
| Pura continuity and grounded prose | Meaningful response, precise detail, independent motives | Mandatory detail or universal social friction |
| RF targeted repair modules | Diagnose mechanisms separately: rhythm, echo, dialogue, occupation | Full planning system, giant ban list, dependencies or a new replacement gesture |
| Kindling quiet turns and conditional characterization | Quiet interaction can be complete; traits depend on context | Requiring an event or trait performance every turn |
| Voyage expertise and motive restraint | Speaker-appropriate language, relevant observations | Universal prohibition on humor or interior thought |
| DEM knowledge and scale | Evidence for knowledge; response size fits circumstances | Mandatory new developments and visible procedural state |
| Vivarium/Writer's Block social behavior | Agreement and resistance need reasons; repair may be partial | Everyone resists or everyone reconciles |
| Magpie continuity | Preserve accepted events; interpretation is not a retcon | Extra ledgers without an actual state requirement |

The baseline and repair text are original formulations of these principles. Source references
identify conceptual provenance, not permission to redistribute a creator's whole work. Community
preset inclusion and reports of successful use do not establish effectiveness on a particular
model, provider, language, character or user preference.

## Assembly and scope

`mainapp/writing_quality.py` materializes an ordinary Writing quality prompt block when authored
starters load. All 33 back-and-forth, rich-scene and director starters receive it once. It is
included in fast setup, starter application, custom setup, samples and export through existing
preset assembly. Rewriting Roleplay or Style does not erase it. It can be explicitly disabled
or edited by the user; this is writing assistance, not a policy enforced against their choices.

Raw starter JSON contains the variant-specific instructions. `starters.get()` returns the
complete materialized preset, including this common block. Treat the assembled result as the
artifact to inspect and compare, rather than reading only the raw JSON file.

Existing saved presets are not migrated. Imported community presets keep their own modules;
we do not append overlapping rules to those artifacts without reviewing their dependencies.
No changes here touch translation, profile schema, language selection or bilingual storage.

## Bulba's repair process

The nine Writing repair records contain instruction, exception, test, provenance and an explicit
unverified-evidence label. Existing find_practice/read_practice tools make them available. Model
knowledge exposes only the model's priority candidates, using the supplied dossiers. The mapping
is a diagnostic shortlist, not an assertion that the model always has those defects.

Bulba should first inspect the baseline and current prompt. It then identifies the mechanism,
checks contradictory rules and user preferences, and proposes the smallest specific edit. It
must preserve the exception and compare outcomes rather than add the whole catalog. A scope
such as 'no repeated emotional filler' is different from banning all gestures or emotional text.

## Evaluation required before claiming literary improvement

Use the existing cases in bulba-writing-validation.md and each repair record's exception case.
Hold provider, model, reasoning, generation allowance, character, accepted history and language
constant. Compare old preset, baseline, then baseline plus one relevant repair. Include several
outputs and later turns: a fresh opening alone cannot expose recurring patterns.

Score independently: supported pattern occurrences per reply; meaningful paraphrase/substitution;
response to the player's actual contribution; character voice; agency; knowledge; continuity;
and the user's preference. Include a short, rich and director version, Ukrainian and English,
quiet conversation and urgent action. Do not substitute substring counts or a model's claim of
compliance for reading the generated result.

Automated coverage verifies all 33 assembly paths, baseline persistence through customization,
explicit opt-out, community preservation, complete model mappings, and repair metadata delivered
through the actual tool. Those tests establish integration, not creative-writing effectiveness.
