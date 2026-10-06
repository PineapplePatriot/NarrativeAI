# Preset instruction cookbook for NarrativeAI

Research addendum • 6 October 2026 • Chat completion • Novice-facing onboarding

This file adds a wording library, architecture choices, and implementation rules to the existing research package. Its purpose is to help the agent select and adapt instructions rather than imitate a preset creator's taste wholesale.

**Evidence boundary:** source-observed patterns and author/user reports are separated from original candidate wording below. No paid model calls or controlled RP comparisons were performed for this addendum. “Try first” means a sensible experiment, not proven superiority. There is no reliable dataset establishing the most frequent fixes in successful presets for every exact target model.

## 1. Classify components, not just preset families

A narrative preset explains desired behavior in natural prose: how characters notice things, speak, pursue motives, and leave room for the player. A formulaic preset encodes behavior as named rules, compact labels, state fields, priorities, or turn procedures. A stateful preset additionally relies on software-managed values or transformations. These are independent dimensions: natural prose can contain macros; structured instructions can produce fluid prose.

Pura 16.0 combines prose guidance with variable-based modes and optional trackers. Its current JSON defaults to preserving user control in Main, but the group nudge permits narration for the user; resolve that conflict. Its Friction block requires “heavy defensive skepticism and social friction,” stronger than the website's gentler description. Grounded Prose contains a concrete-detail replacement rule and extensive exclusions; a comment about Kimi K2.6 is not K3 evidence. [P1–P2]

FF5.4 advertises persona, agency and dialogue fixes and depends on accompanying regex. Its public discussion also documents anti-echo/pacing tradeoffs. These are useful examples of interacting modules, not proof that a longer rule system improves every model. The archive describes Micro, BOLT and MAX as increasingly elaborate configurations; its author discourages MAX for Claude/Kimi and reports excessive checking with K3 word bans and exact output counts. Those are author observations, not independently measured limits. [F1–F2]

| Dimension | Natural prose approach | Structured approach | Decision signal |
|---|---|---|---|
| Behavioral instruction | Contextual explanation | Short explicit rule with scope | Which version changes the actual failure more reliably? |
| Prose style | Describe voice and illustrate it | Specify POV, formatting, length | User likes texture versus requires consistency; both can coexist |
| Turn planning | Follow scene opportunities | Conditional priority list | Structure helps if replies lose relevant actions; hurts if every turn feels identical |
| World state | Narrative continuity | External ledger or explicit state | Add machinery when persistent facts or numerical rules matter |
| Presentation | Plain dialogue/narration | Trackers, menus, tagged blocks | User must want the interface, independently of model ability |

**Do not infer architecture from genre.** Dark romance can need a short character-focused preset. Cozy adventuring can need an inventory system. Strong models may execute complex instructions while producing prose the user dislikes.

## 2. Determine user fit in plain language

Ask concrete choices, then show brief passages from the selected model. Avoid asking whether they prefer “formulaic prompting.”

| Ask the user | Preference revealed | Possible configuration |
|---|---|---|
| “Should the scene stay with this conversation, or should the world bring in new trouble?” | Initiative and event frequency | Quiet scene focus / conditional world initiative |
| “Should they explain how they feel, or should you work it out from what they do?” | Explicit interiority versus inference | Reflective narration / subtext-focused narration |
| “Would you enjoy seeing relationship numbers and inventory, or just reading the story?” | Visible mechanics | Optional interface / plain prose |
| “Should a disagreement be easy to repair, or can it remain unresolved?” | Friction tolerance | Warm cooperation / motive-based resistance |
| “Who decides what your character does—you, or both of you?” | Agency permissions | Player-only / explicitly shared authorship |
| “Does this feel too polished, too flat, too slow, or too busy?” | Specific revision target | Voice, detail, pace, or initiative change |

Interpret ambiguous cues as hypotheses. “Too nice” might mean instant trust, therapist dialogue, easy victories, or loss of a villain's personality. “Boring” might mean repetitive sentences, no initiative, or no emotional stakes. Ask one discriminating follow-up instead of applying a universal harshness module.

Run two separate comparisons when needed: **same behavior, different wording architecture** to assess model fit; **same architecture, different scene behavior** to assess taste. Otherwise, a user preferring more conflict could be mistaken for a preference for structured prompts.

## 3. Patterns observed in current sources

| Source and scope | Observed fix or construction | What the agent should learn | Evidence limit |
|---|---|---|---|
| Pura 16.0, Main and optional modes | Continuity, contextual characterization, controllable friction, optional prose restrictions | Inspect the actual module and resolved prompt; friendly labels can hide forceful instructions | Source inspection; broad author testing claims do not isolate exact model/version effects |
| FF5.4, release and comments | Distinct voices, less therapy talk, internal state, anti-echo and regex dependencies | Diagnose interactions: preventing recap can also omit responses to earlier actions | Author report plus anecdotal user reports |
| Evening-Truth GLM5.3 | Separate role, interaction and response rules; agency, knowledge limits, independent goals, avoidance of premature closure | Short headings can make rule scope easy to inspect without building a simulator | Author-specific setup, Z.AI via OpenRouter; not a controlled comparison |
| Evening-Truth Narrative Guide, GLM4.7 | Exclude an unwanted archetype and its associated behaviors | A semantic prohibition can be more useful than a word ban | Older model observation; transfer to GLM5.3 requires testing |
| Official Opus5.5 guidance | Remove unnecessary think-carefully scaffolding in chat; use effort control; specific exclusions can steer defaults | Stronger prompting does not mean more reasoning instructions; watch substitute defaults | Official general/chat evidence, not a roleplay benchmark |

A useful exact GLM5.3 clause is “Characters are not omniscient.” The guide's exact archetype exclusion is “Omegaverse, Power Play, Alpha Male.” Another exact GLM5.3 clause is “Avoid pre-emptive resolutions, instant completion, favoritism or closure.” These target different problems: character knowledge, genre drift and premature resolution. Do not transplant the guide's threatened penalties or the preset's adult-content assumptions into a novice default. [E1–E2]

**Frequency rule:** record these as recurring candidate themes across the inspected shortlist. Do not report percentages, claim a model-specific top ranking, or call a wording proven effective merely because it appears in a popular preset.

## 4. Wording library: problem → instruction → tradeoff → test

Everything in quotation marks in this section is **original candidate wording**, not a copied source passage. Select only the observed problems. The two forms are alternatives, not blocks to stack together. The structured form is a concise behavioral specification; it is not executable code.

### 4.1 Automatic agreement, instant trust, easy forgiveness

Natural: “Let each character respond from their own priorities and existing relationship. Agreement, trust and forgiveness depend on what happened and what matters to them; sincere cooperation remains possible.”

Structured: “SOCIAL RESPONSE: use motives + relationship history + current stakes. Agreement and refusal both require a character-consistent reason. Change trust when the scene supplies evidence.”

Use for users who want earned emotional development. Overcorrection creates universal suspicion and ruins affectionate characters. Test a reasonable request, an unfair accusation, and a genuine apology: the model should distinguish all three.

### 4.2 Villains softened into helpful companions

Natural: “Keep established goals and flaws consequential. A charming interaction may change a tactic without erasing a character's ambition, prejudice or conflicting loyalty.”

Structured: “CHARACTER CONTINUITY: preserve established goals and flaws. Revise them through demonstrated development; friendliness alone does not reset them.”

Apply to characterization drift, not every dark scenario. Test whether a pleasant exchange changes the villain's strategy without making them abandon their objective.

### 4.3 Therapy dialogue and premature emotional insight

Natural: “Let care and conflict sound like this person. They may offer practical help, deflect, misread, joke or hesitate. Emotional explanations should fit their insight and the relationship.”

Structured: “EMOTIONAL VOICE: character-specific language; insight limited by characterization. Use explicit reassurance or self-analysis when plausible, rather than as the default response.”

Do not ban empathy. Test a distressed scene with a reserved mechanic and an emotionally articulate counselor; the voices should differ.

### 4.4 Taking control of the player's character

Natural: “Portray the other characters and the world. Leave {{user}}'s new dialogue, voluntary actions, decisions and private thoughts for them to supply. Respond to actions they have already established.”

Structured: “AUTHORSHIP: model = NPCs/world; player = {{user}} dialogue, decisions, voluntary actions, inner experience. Resolve established external effects without inventing the player's next choice.”

Physical consequences and voluntary choices are separate. A thrown ball can hit a player character under agreed rules; the model need not decide that they forgive the thrower. Test ordinary roleplay, a group exchange, and a continuation. Audit group nudges and cards for conflicting permissions.

### 4.5 Omniscience and leaking secrets

Natural: “A character reacts to what they witnessed, learned or can reasonably infer. Keep private information private until the story gives them a route to it.”

Structured: “KNOWLEDGE: distinguish world facts from each character's evidence. Unknown secrets remain unknown; suspicion is not confirmed knowledge.”

Use when mystery or deception matters. Test an overheard conversation versus a private off-screen conversation. Omniscient narration, if requested, does not make every character omniscient.

### 4.6 Repeating the user, or skipping their earlier actions

Natural: “Continue from the current endpoint. Show the consequences of relevant actions without restating the message. If several actions matter, respond to them in their established order.”

Structured: “CONTINUATION: no recap. COVERAGE: address consequential unresolved actions. ORDER: preserve chronology; compress minor transitions.”

A blanket ban on revisiting prior material can suppress necessary reactions. Test a message with three actions where the first changes the third. Removing repeated words with regex does not fix missing causality.

### 4.7 Every turn introduces an interruption or plot twist

Natural: “Let an active exchange develop. Introduce a new event when the situation supports it or momentum has genuinely stalled; quiet attention can carry a scene.”

Structured: “INITIATIVE: resolve the active beat first. Add complications when justified by existing causes or requested pacing. No mandatory event quota.”

Use for users who want banter or emotional development. A highly proactive adventure profile can raise initiative separately. Test a simple conversation: an unrelated explosion should not be required to make it count as progress.

### 4.8 Scenes stall despite the user asking for adventure

Natural: “Let characters act on their goals and let unresolved pressures produce opportunities or consequences. Offer something the player can engage with while leaving their response open.”

Structured: “WHEN STALLED: advance an established goal, pressure or opportunity. Create an actionable opening; preserve player choice.”

Stalling and quiet intimacy are different. Test a waiting scene with a known deadline, then a deliberate reflective scene; only the former necessarily needs external movement.

### 4.9 Stock gestures and synonym substitution

Natural: “Do not use a tightened jaw as automatic emotional punctuation, including renamed versions of that gesture. Omit the beat when it adds nothing; otherwise choose a response specific to this person and situation.”

Structured: “EXCLUDE: generic jaw-tension emotion cue, including paraphrases. REPLACEMENT: meaningful character-specific response or omission. Do not install a recurring replacement gesture.”

This targets a semantic habit, not just a phrase. Test several emotional turns. If jaw tension becomes clenched hands in every reply, the fix has failed despite passing a string check.

### 4.10 Unwanted romance archetype or possessive shorthand

Natural: “Keep this relationship [mutual and non-possessive / awkward and tentative / another chosen dynamic]. Avoid ownership claims and predatory romantic framing unless the character and agreed dynamic specifically call for them.”

Structured: “RELATIONSHIP DYNAMIC: [chosen dynamic]. EXCLUDE: [unwanted archetype and behaviors]. Preserve attraction, warmth and disagreement within that dynamic.”

Ask what the user dislikes before excluding a trope. Slow-burn, possessive fantasy and equal partnership are different tastes; one should not be treated as the universal repair.

### 4.11 Purple prose, flat prose, or irrelevant sensory detail

Natural: “Use details the viewpoint would notice and that affect this moment. Let concrete action carry most of the passage; use imagery where it sharpens the chosen mood.”

Structured: “DETAIL FILTER: viewpoint relevance + scene function. IMAGERY: [sparse/moderate/lush]. Remove decorative details that obscure the action.”

Do not turn “grounded” into an inventory of surfaces and smells. Compare the same scene at two imagery levels; a user may prefer lush prose without accepting vague clichés.

### 4.12 Everyone speaks in the same witty voice

Natural: “Give each speaker their own vocabulary, rhythm and social habits. Humor belongs to characters and moments where it fits; serious lines may remain straightforward.”

Structured: “VOICE: derive vocabulary and cadence from the card and examples. HUMOR: conditional on speaker and context. No universal banter requirement.”

Test three speakers responding to the same awkward news. A profession should inform vocabulary without making every sentence a workplace metaphor.

### 4.13 Replies are too long, too clipped, or cut off

Natural: “Usually write [chosen range] paragraphs. Give the current interaction enough room, then hand the scene back at a meaningful opening.”

Structured: “VISIBLE LENGTH: [chosen range]. PRIORITY: relevant interaction + complete ending. Compress background recap before cutting active dialogue.”

Preference ranges are soft writing guidance. Provider output limits are hard request settings and may include reasoning; diagnose truncation separately. Test an action scene and a short social reply rather than demanding identical lengths.

### 4.14 The card's traits become repetitive performances

Natural: “Let traits shape choices when relevant. A reserved character can speak, a jealous character can discuss other things, and a nervous character need not visibly tremble every turn.”

Structured: “TRAITS: contextual tendencies, not turn quotas. Show them through relevant choices; preserve variation across situations.”

Use when a character is recognizable but exhausting. Test different contexts, not five versions of the same trigger.

### 4.15 Too much planning or visible procedural output

Natural: “Return the in-world reply in the requested format. Keep scene-management instructions out of the narration.”

Structured: “OUTPUT: narrative/dialogue only, except explicitly enabled interface elements.”

This governs visible output, not native reasoning duration. For Opus5.5 specifically, first remove inherited instructions to think carefully and calibrate supported effort. Official guidance supports that chat intervention; it does not establish an RP quality score. [C1]

## 5. Original bundles to trial

### A. Character-focused baseline

Use for conversation, banter, emotional development, and users who want little interface.

```text
Portray {{char}} and relevant supporting characters from their established motives,
voice and knowledge. Leave {{user}}'s new choices, dialogue and private thoughts to
them. Continue from the current moment, responding to consequential actions without
recapping. Let trust, disagreement and affection develop from the relationship and
what happens. Quiet exchanges can carry the scene. Use [chosen prose texture],
usually [length range], and leave a natural opening for the player.
```

Add one demonstrated repair, such as therapist voice or omniscience. Avoid importing a complete anti-slop blacklist before seeing a failure.

### B. Scene-driving baseline

Use when the user wants an active world and opportunities, while retaining player control.

```text
AUTHORSHIP: portray NPCs and the world; leave player decisions and private thoughts
open. CONTINUITY: preserve established facts, consequences and knowledge limits.
CHARACTERS: pursue individual goals; cooperate or resist for plausible reasons.
PACE: develop the active beat. When momentum stalls, advance an established pressure
or opportunity rather than introducing unrelated trouble. STYLE: [selected voice
and detail level]. ENDING: an actionable opening without resolving the player's
response. Visible trackers and choices: [off / explicitly selected features].
```

This is structured but has no variable or regex dependency.

### C. State-assisted adventure

Start with A or B and add only the following responsibility split:

```text
The supplied state lists accepted facts and resolved mechanical results. Narrate
within those results. Propose consequential state changes through the supported
state interface; do not silently rewrite inventory, health or established secrets.
Character beliefs may differ from world facts. Display only the trackers the player
selected, and keep calculations out of ordinary dialogue.
```

This requires an implemented state interface. Do not paste it into plain SillyTavern and pretend persistence exists.

## 6. Model-specific trial routing

These are **initial experiments**, not rankings of proven wording effectiveness. Every repair remains conditional on the user's taste and an observed failure. Use exact model/provider identifiers from the existing model guide; the family name is insufficient.

| Target | First architecture comparison | Repair candidates to observe | Evidence boundary |
|---|---|---|---|
| Claude Opus5.5 | Short natural baseline vs equally short rule baseline; remove inherited planning scaffolding | Automatic social accommodation, excessive explanation, substitute clichés | Official chat prompting supports less redundant thinking scaffolding; RP repairs remain candidates |
| Claude Opus4.6 | Natural baseline vs a small explicit agency/knowledge block | User control, instant trust, emotional overexplanation | Do not assume a newer Opus clause transfers unchanged |
| Claude Fable5.1 | Short baseline vs a few conditional scene rules | Voice, pacing, visible procedural habits if observed | No controlled preset comparison for this exact model in this addendum |
| Claude Opus4.7 | Repeat 4.6 comparison on the exact endpoint | Same failure categories, only if reproduced | Separate version record; no automatic inherited score |
| KimiK3 | Character/scene prose vs explicit conditional pacing and state-free rules | Overactivity, tonal overshoot, premature character decisions | K2.x preset comments do not validate K3; darkness is a user choice |
| MiMo v2.6 Pro | Lean baseline vs concise rule block, adding one repair at a time | Pacing and characterization; instruction conflicts | Prior research reports support investigating lean wording; no measured optimum |
| Gemini3.8 Flash | Natural baseline vs explicit POV, authorship and output contract | Format drift, control boundaries, genre/voice consistency | Older Gemini prefills are not automatically compatible |
| GLM5.3 | Evening-Truth-style scoped rules vs compact narrative rewrite of the same requirements | Knowledge leakage, agency, premature closure, archetype drift | GLM5.3 author prompt is directly relevant; trope-exclusion report was GLM4.7 |
| DeepSeekV4 Pro | Concise behavioral baseline vs small structured equivalent | Continuity, overly rigid compliance, pacing | FF compatibility has changed; pin model snapshot and provider |
| DeepSeekV4 Flash | Repeat Pro experiment independently | Same categories if observed; prioritize missing constraints | Flash is not merely Pro with a lower quality score; routing aliases can change |

Do not solve an ignored prompt with unsupported sampler settings. Do not promise “disable thinking” when the endpoint cannot do so. A live onboarding draft and comparisons must be generated by the user's chosen model, as required by the project.

## 7. Variables, regex and functions: choose the smallest necessary mechanism

### Four distinct mechanisms

| Mechanism | What it actually does | Appropriate example | Poor substitute for |
|---|---|---|---|
| Instruction label or fictional formula | Text the model interprets | Priority list for handling unresolved actions | Deterministic calculation |
| SillyTavern macro | Frontend substitution/operation | Insert character name or selected style text | Reliable inferred relationship state |
| Regex | Pattern-based text transformation | Format a predictable status block | Semantic characterization repair |
| Script/function | Executed software logic | Validate state, resolve a roll, compile selected modules | Guessing the user's preferred prose |

A line such as `trust = respect + shared_history` in a prompt is a metaphorical rule unless software actually calculates it. The agent must label it accordingly. Prefer observable relationships and reasons when the user does not want numerical mechanics.

### Macro setup: configuration, not invented memory

Official docs specify `{{setvar::name::value}}` and `{{getvar::name}}`; local and global variants are distinct. Macro-engine behavior differs across installations. Use `/? macros` to inspect supported syntax. [T1]

Example configuration block, placed before its consumption:

```text
{{setvar::nai_style::restrained, concrete narration with character-specific dialogue}}
{{setvar::nai_length::usually 2–4 paragraphs}}

Writing style: {{getvar::nai_style}}
Reply length: {{getvar::nai_length}}
```

This intentionally rewrites these **configuration values** whenever the block runs. Do not use it to initialize live trust or inventory every generation. For persistent state, initialize once through an explicit new-chat action and update through a controlled mechanism.

Implementation recommendations: namespace variables; separate immutable configuration from accepted story state; rebuild selected modules cleanly when a toggle changes; inspect the resolved outgoing prompt for stale values. A disabled setter can leave a previously saved value behind. A language model describing `setvar` in its reply does not itself prove the frontend executed it.

A simple manual Quick Reply/STscript action is:

```text
/setvar key=nai_length usually 2–4 paragraphs |
/echo Length preference saved.
```

STscript supports command pipelines and variables; Quick Replies can store scripts. This example saves configuration and reports it. It does not trigger a paid generation. Do not place slash-command scripts in a system prompt and expect execution. [T2]

Current macro docs list some flags as planned rather than implemented. Never generate syntax from a wish list. Older complex presets should be tested on the installed macro engine, especially literal separators, nested values and evaluation order. An FF5.4 commenter reports literal pipes inside variable templates disrupting internal-state output under the experimental engine, with engine changes or encoded pipes as attempted workarounds. This is a version-specific community report, not a reason to disable the engine globally or encode all pipes blindly. Reproduce the issue and inspect the resolved template first. [F2]

### Regex setup: keep meaning and presentation separate

Use regex when the output has a stable, deliberately designed marker. Prefer an optional display transformation before changing saved history. SillyTavern distinguishes display-only, outgoing-prompt, and stored-text edits; with neither ephemerality option selected it modifies saved text. Its editor includes Test Mode. [T3]

Small optional example: hide a closed presentation-only tag from **AI Response display**.

```text
Find Regex: /<nai_ui>[\s\S]*?<\/nai_ui>/g
Replace With: [empty]
Affects: AI Response only
Ephemerality: Alter Chat Display on; Alter Outgoing Prompt off
Macros in Find Regex: Don't Substitute
```

Use only when `<nai_ui>` is an agreed presentation wrapper. This is not a reasoning extractor, state parser, or a general rule for hiding arbitrary content. It leaves source text available to the outgoing prompt; if that is undesirable, design the state/presentation separation explicitly rather than assuming display hiding deletes it.

Expected string behavior: removes complete multiline wrappers, removes two wrappers independently, preserves ordinary prose, and leaves an unclosed wrapper untouched. Nested wrappers are unsupported. Test in the installed UI too; the standalone pattern check does not validate ST integration.

Avoid regex replacements for “positive bias,” possession, metaphors or therapist dialogue. They alter words after generation, can break meaning, and cannot make the character choose differently. If names are interpolated into a regex, use escaped macro substitution rather than raw regex metacharacters. [T3]

### Functions: deterministic work belongs outside prose

Introduce executed functions when the user needs reliable inventories, arithmetic, dice, branching state, or validations that prose alone repeatedly fails. A NarrativeAI service can provide these independently of whether the generation endpoint supports native tool calling.

Recommended application flow:

1. Load accepted state and selected configuration.
2. Resolve any required mechanical result once, recording its event ID.
3. Supply only relevant facts and results to the selected model.
4. Receive narration and, if supported, a separate proposed state update.
5. Validate updates against a schema and the agreed rules.
6. Commit only the chosen reply and its accepted update; alternate swipes remain separate branches.

Example application interface—not a claimed SillyTavern built-in:

```json
{
  "event_id": "turn-17-choice-a",
  "operation": "consume_item",
  "item_id": "brass_key",
  "quantity": 1,
  "expected_state_version": 16
}
```

The host checks existence, quantity, authorization under game rules, version and duplicate event IDs. Retrying a request must not consume the same key twice. Do not derive trusted state by regex-scanning arbitrary dialogue. Store facts, character beliefs and proposed changes separately.

For ordinary conversation, these functions are unnecessary. Add them when the desired experience requires mechanics, not because a preset has impressive technical notation.

## 8. Assembly and evaluation rules for the agent

Maintain an instruction record with: `issue_id`, scope, candidate wording, source/provenance, evidence level, exact model/provider, user preference, enabled dependencies, observed improvement, regression and last-tested date.

For each revision:

1. Confirm the failure in a saved example; distinguish model behavior from card, history or prompt-assembly conflict.
2. Select one repair or a tightly related bundle. Preserve all other settings for the first comparison.
3. Generate comparisons on the chosen model using the same card, history and user message. Randomize display order.
4. Check the targeted behavior and ask whether the writing feels better. Both matter.
5. Repeat across contrasting scenes and several generations. Include a scene where the repair should remain inactive.
6. Remove clauses that add no observed value; retain the shorter version when results are comparable.

Useful probe set: harmless request, unfair accusation, sincere apology, secret known to only one NPC, three-action user turn, deliberate quiet scene, deadline-driven adventure scene, multi-character exchange, long-context continuation. Add a player-authorship check after every structural change.

**Negative instructions:** permit specific behavioral exclusions when they address an observed failure. Pair them with scope and either a meaningful alternative or permission to omit the unnecessary beat. Test semantic substitutions. Do not require a replacement detail every time: that can create a new stock habit. Repeated threats, “always/never” proliferation and universal mandatory beat lists need evidence, not faith.

**Export:** bundle the enabled instructions, actual order, required regex/scripts and configuration defaults alongside the connection setup and test card. Declare dependencies, regenerate resolved prompts after import, and verify a round trip. Do not export runtime API secrets. A simplified starter must either remove dependency-based modules or include working dependencies; disabled modules and empty variables do not constitute a complete setup.

**Quick-start profiles:** offer a small selection based on experiences—character conversation, active adventure, optional mechanics—with model-specific implementations. Users can try a complete setup immediately and refine taste later. Keep technical controls behind understandable options such as “more initiative” or “show inventory.”

## Sources and verification status

Accessed 6 October 2026 unless noted. Source links establish constructions and reported behavior, not universal success. The accompanying prior report contains the broader sampler/provider audit; its 3 October snapshot should be rechecked before producing live connection profiles.

- **P1:** [Pura author documentation](https://platberlitz.github.io/), 16.0, site update 28 September 2026.
- **P2:** [Actual Pura16.0 ST JSON](https://platberlitz.github.io/preset/Pura%27s%20Director%20Preset%2016.0%20%28SillyTavern%29.json), Main, Friction, Grounded Prose, group nudge and variable construction inspected.
- **F1:** [FF archive](https://rentry.org/freaky-frankenstein-presets), current family/version packaging.
- **F2:** [FF5.4 release and discussion](https://www.reddit.com/r/SillyTavernAI/comments/1w49lyx/preset_update_freaky_frankenstein_54_the_second/), author claims and user reports.
- **E1:** [Evening-Truth GLM5.3 prompt](https://rentry.org/evening-truth-glm-53-flash), scoped rules and author setup.
- **E2:** [Evening-Truth Narrative Guide](https://rentry.org/Evening-Truth-Narrative-Guide), GLM4.7 trope-exclusion account, updated 12 May 2026; retained because it supplies a specific wording experiment, not a current GLM5.3 result.
- **C1:** [Official Opus5.5 prompting guidance](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5-5), chat thinking instructions and default substitution guidance.
- **T1:** [Official ST macros](https://docs.sillytavern.app/usage/core-concepts/macros/).
- **T2:** [Official STscript reference](https://docs.sillytavern.app/usage/st-script/).
- **T3:** [Official ST regex extension](https://docs.sillytavern.app/extensions/regex/).

The MiMo2.6 Evening-Truth page could not be reopened for this addendum. Model routing beyond the directly inspected sources is explicitly proposed experimentation, informed by the existing research package rather than new exact-version effectiveness claims. No complete preset import, API generation, or state-function implementation was performed. Regex string fixtures are the only executable verification included here.
