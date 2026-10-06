# Second pass: preset tricks and interactive story elements

NarrativeAI research addendum • 6 October 2026 • Chat completion

## What the first cookbook missed

The first guide covered behavioral wording, architecture, macros and basic regex. It did not sufficiently cover **presentation as part of the roleplay**, conditional assistance, relationship routes, event delivery, or the interaction between context cleanup and format reliability. Celia and Realistic Frankenstein add useful examples in those areas.

This guide has two parts: observed techniques from named presets, then original designs the onboarding agent can offer. “Observed” means source inspection or a labeled author/user report. Original recipes are proposed instructions and implementation contracts, not copied preset modules or tested model benchmarks.

## 1. Current sources and version traps

| Family | Artifact inspected or documented | Relevant new material | Qualification |
|---|---|---|---|
| Celia | Public author-site JSON labeled 5.4; March 2026 release 5.3 also retrieved | HTML objects, disclosures, assistance, routes, variable reset, context transforms | Public 5.4 readme principally targets Opus4.6. A May 2026 user mentions 5.8; newest overall version remains unresolved |
| Realistic Frankenstein | 2.1, 2.2/Douyin and 2.2.1 author release posts | Event/routine engine, two-stage repairs, state layout, model-specific packages | Linked Drive files were not inspectable; these findings are author reports, not an actual JSON audit |
| Freaky Frankenstein | Current 5.4 archive and previously inspected release | Off-screen agendas, expression typography, inherited state machinery | Shares ancestry and some modes with Realistic; neither name establishes a universal writing style |
| Pura | Director16.0 JSON and separate regex file | In-world HTML, relationship stages, choices/directions, selective context pruning | Actual module/regex inspection; quality claims remain author claims |
| Microcot | Public GitHub repository | Optional meta-interface features and separate cleanup assets | Additional implementation lead; README statements are not controlled effectiveness evidence |

Celia is relevant to 2026 research: the March launch and May discussion establish current-year use. They do not resolve which public artifact matches a later Discord release. Preserve filename/version and source date; do not silently call 5.4 the latest. [C1–C4]

RF2.2.1 is a material addition to the earlier shortlist. Its release describes model/effort-specific configurations, a new MiMo2.6 custom-reasoning path, optional native reasoning for Pro, leak-cleanup fallbacks, and random rolls moved toward the prompt end. Its sampler, latency and provider claims are endpoint-specific reports, not universal API rules. A notice asking the user to swipe after a reasoning-only reply is error handling, not successful storytelling. [R3]

## 2. Concrete tricks worth retaining

### Celia: separate writing, assistance and visual context

The inspected 5.4 JSON includes simple versus elaborate HTML, in-world documents/screens, native disclosures and CSS interactions, mood typography, a writer persona, optional assistance, an epilogue trigger and dating routes. Its relationship ledger covers up to three interests, affection/trust out of ten, route stages and off-screen activity.

A reset block clears mode/style variables before selected options populate them. Bundled regex separates display from outgoing context: the enabled tag hider removes markup from depth3+ history while retaining text; a different whole-element remover is disabled. Assistance can be shown as expandable advice yet removed from the outgoing prompt. Hidden-block display can expose comments as a ledger. These are presentation/text-processing mechanisms, not trusted state execution. Simple and elaborate HTML should be alternative modes. [C2]

**Product inference:** a writer helper can be useful without becoming an in-world narrator. Give users an optional “Help me respond” panel whose contents are kept separate from canon. Explicitly distinguish player-writing suggestions from actions the player actually took.

### Realistic Frankenstein: targeted repairs and a living world

RF2.2's author describes a two-stage repair: define the unwanted behavior, a better alternative and a legitimate exception, then use a short nearby reminder referring to that rule. Douyin incorporates reminders into its reasoning template. The author also separates generation order from display order: state is requested first, but display regex moves it below the prose. A legacy FF4.2 pruning regex reportedly broke FF5 counters. Lean state depends on Fate & Routine, rather than on a visual section header. [R2]

**Original candidate wording:**

```text
VOICE RULE: Do not turn the character's profession into their whole personality.
Use specialist vocabulary when the situation calls for it; let relationships,
interests and ordinary habits shape their speech elsewhere.
```

Optional short reminder:

```text
Apply VOICE RULE where relevant; keep this speaker specific to the situation.
```

Trial the single rule first. A second placement is useful only if it improves the observed failure without making the prose rigid. Do not assume depth0, assistant role, or duplication is universally superior across chat APIs.

RF2.1's Fate & Routine explanation distinguishes uninterrupted routine, contextual versus random interruptions, and world news delivered through an encountered, era-appropriate medium. Its author says this replaced a tempo design that made scenes circular and reduced player involvement. The release required a modern ST installation and Experimental Macro Engine; verify current compatibility before export. [R1]

**Product inference:** randomness should decide whether an opportunity appears, not automatically decide the player's response. A newspaper, rumor or message can make the world feel active without combat statistics or mandatory plot twists.

### Freaky: expression and off-screen continuity

The FF archive describes off-screen NPC agendas and regex-driven typography for expressions such as whispering and shouting. Its state machinery can include relationships, locations, inventory and status. Both forks have realism/freaky options: “Realistic” does not simply mean mild content, and “Freaky” does not mean every setup uses the same exaggerated prose. The archive warns that dense state machinery can compete with prose quality and discourages MAX for Claude/Kimi. [F1]

**Product inference:** offer expression typography or an off-screen agenda independently. A user who wants readable text messages should not have to adopt a complete simulation engine.

### Pura: meaning first, decoration second

Director16.0 supports HTML for objects whose layout carries meaning. Its relationship feature uses stages and milestones rather than only a score. The JSON includes optional trackers and distinct player-action choices versus plot-direction menus. Its regex file turns compact tracker blocks into visual cards; older unchosen choices/directions are removed from outgoing context at configured depths. Rendering and pruning are separate operations. [P1–P3]

**Product inference:** keep the chosen action and its consequences; prune abandoned suggestions. Otherwise, a later reply can confuse things the player could have done with things they actually did.

Microcot's README also offers optional meta-interface material, including HTML, diary/assistant elements and infotabs, while warning against using visual structures constantly. Its GitHub tree contains dedicated formatting and cleanup assets. Treat its wider model-intelligence and anti-censorship statements as author opinions. [M1]

## 3. Three kinds of interaction—do not confuse them

| Kind | Example | Changes story state? | Needs extra generation? |
|---|---|---|---|
| Visual disclosure | Open a letter or expand a panel | No, by itself | No |
| Narrative choice | Select “Ask about the missing page” | Yes, if the app submits and accepts that action | Usually one normal reply |
| Mechanical/state operation | Advance a clock after a qualifying event | Only through an accepted update | Not necessarily; host logic can do it |

Opening `<details>` reveals content already present. CSS tabs or checkboxes change local presentation; they do not tell the model what the player selected. A progress bar displays a value; it does not compute it. Actual buttons need an implemented action handler or a supported frontend extension/script. [H1–H2]

An HTML comment, closed disclosure or CSS-hidden element is not private storage. Separate three audiences: what the player may read, what the model receives, and what an in-world character knows. Hiding content from the screen does not remove it from the prompt or saved export.

## 4. Original interactive recipes beyond RPG modes

All prompts and setups below are original candidates. The aim is engaging storytelling with user-controlled intensity. None should become a compulsory end-of-turn checklist.

| Feature | What it adds | Trigger | State owner | Best fit |
|---|---|---|---|---|
| In-world letter/receipt | Tangible evidence and personality | A document is encountered | Accepted story facts | Mystery, romance, slice of life |
| Phone/messages screen | Parallel conversation and timing | A character checks a device | Canon message log | Modern settings, social drama |
| Rumor board/news clipping | Wider world without scene interruption | An information source is encountered | World events plus attributed reports | Political stories, campus life, exploration |
| Discovery scrapbook | A record of shared memories | A meaningful discovery or shared event | Accepted memory entries | Travel, friendship, slow burn |
| Relationship milestones | Visible development without exact emotion math | Qualifying relational evidence | Accepted stage with reason | Optional dating/friendship routes |
| Suspicion/deadline clock | Tension with a readable cause | A declared qualifying event | Host-managed counter | Mystery, heist, social intrigue |
| Favor/debt ledger | Social consequences instead of levels | Favor promised, fulfilled or called in | Accepted obligations | Court intrigue, workplace drama |
| Recurring ritual card | A callback users can influence | An agreed routine occurs | Ritual history | Cozy RP, domestic relationships |
| Scene focus choices | Easier continuation when the user is stuck | Requested, not forced | No canon until selected | Newcomers, low-energy sessions |
| Off-screen postcard | Evidence of another character's life | Time passes and contact is plausible | Accepted external event | Long-distance relationships, ensemble cast |
| End-of-session keepsake | A satisfying artifact of the session | User explicitly ends it | Snapshot of canon | Any genre |
| Optional writing helper | Suggestions without taking over | User requests help | Non-canon assistance | Technically inexperienced users |

### A. An in-world document, not a decorative wall of HTML

Candidate instruction:

```text
When the scene genuinely includes a readable object, you may present that object
as one compact panel. Its wording, date, damage or layout should supply relevant
information. Keep ordinary narration outside the panel. Do not invent a document
merely to satisfy this feature, and do not add one to every reply.
```

A minimal illustrative template:

```html
<details class="nai-document">
  <summary>Folded note · found beneath the door</summary>
  <div>
    <p>Meet me after the last train. Bring the blue notebook.</p>
    <p><small>The signature has been crossed out.</small></p>
  </div>
</details>
```

`details`/`summary` provide native disclosure in a browser. Whether a specific chat renderer retains these tags must be tested. Expanding the note is not proof the character read it; if reading it should affect the story, use an explicit submitted action. [H1]

### B. A phone screen that respects time and knowledge

Candidate instruction:

```text
Show a message panel only when a character consults a device or receives a
notification the scene would notice. Include sender, relevant fictional timestamp
and concise text. Distinguish sent, received and unsent messages. Other characters
know the contents only if they see or are told them.
```

Store whether the message was accepted as canon. Avoid using real wall-clock time for fictional timestamps unless requested. An unsent draft must not become dialogue another character heard.

### C. A rumor board with disagreement

Candidate instruction:

```text
When the player encounters a news source, offer up to two relevant items. Attribute
each to a source and distinguish confirmed facts, claims and rumors. Information
may matter later without interrupting the current exchange.
```

Original compact data example:

```json
{
  "id": "rumor-12",
  "source": "station noticeboard",
  "claim": "The last train has been cancelled.",
  "status": "unconfirmed",
  "known_to": ["player", "station_attendant"]
}
```

This lets an unreliable world coexist with reliable state. “The newspaper says X” does not mean X is objectively true.

### D. Counters tied to meaningful events

A clock can track a train departure, a detective's suspicion, an unfinished promise or a secret becoming public. Define **what increments it**, what can reduce it, and what the threshold means.

Example contract:

```text
Suspicion clock: 0–4.
+1: a new accepted public event provides evidence implicating the player.
-1: accepted credible evidence resolves a previously counted suspicion.
No change: another message, a reroll, a private thought, or the same evidence repeated.
At 4: the investigator requests an explanation; the player's response remains open.
```

Use an evidence ledger so the same clue cannot be counted twice. The threshold causes an opportunity or consequence, not forced guilt or a forced confession. Call the value **suspicion**, not “objective probability the player is guilty.”

Illustrative display:

```html
<div class="nai-clock">
  <p>Investigator's suspicion: 2 of 4</p>
  <progress value="2" max="4" aria-label="Investigator's suspicion"></progress>
  <p><small>Latest cause: the station camera placed you near the office.</small></p>
</div>
```

A native progress element displays supplied values; it does not persist or increment them. [H2] For a reliable product, render this template from host state. A prompt-managed counter can be offered as approximate bookkeeping, but should not be advertised as deterministic.

### E. Milestones and discoveries instead of emotion scores

Candidate instruction:

```text
Show a relationship update only after a meaningful change. State the current
relationship in ordinary language and name the event supporting the change. Keep
unknown preferences unknown until discovered. Affection, trust and compatibility
can move differently; do not reward every reply with automatic progress.
```

Possible visible card: “Trust: growing cautiously · Shared memory: repaired the station roof · Still unresolved: why she left last winter.”

For users who dislike metrics, show discovered preferences and memories only. If stages are enabled, allow reversal and mixed relationships. A stage is a narrative summary, not an entitlement to another character's behavior.

### F. A favor ledger with actual narrative consequences

Candidate instruction:

```text
Record an obligation only when a character explicitly promises or incurs it in
the accepted scene. Include who owes whom, what was promised, and whether any
deadline exists. A later request may invoke the promise; fulfillment, refusal and
renegotiation remain character choices with consequences.
```

This supports rich social interaction without a currency system. Do not convert every kindness into debt unless that is the chosen setting/dynamic.

### G. A scrapbook and recurring rituals

Candidate instruction:

```text
When an event becomes a meaningful shared memory, offer a brief keepsake entry.
Use the established event and one specific detail. Recurring rituals may recall
these entries when relevant; do not invent a sentimental callback every turn.
```

Example: “First terrible attempt at pancakes · kept the scorched recipe card.” Let the user rename, pin or delete entries. That is lightweight app interactivity; the model need not generate elaborate HTML every time.

### H. Choices as support, not a cage

Candidate instruction:

```text
When the user asks for help continuing, offer three distinct plausible actions
and leave free-form input available. Mark suggestions as possibilities. Do not
perform them or add them to canon until the user chooses or writes an action.
```

Separate “what my character does” from “what direction I want the story to take.” An action choice can enter the scene; a direction choice is an OOC steering request. Either can be offered without requiring the player to learn prompt terminology.

### I. A keepsake ending or optional epilogue

Candidate instruction:

```text
When the user explicitly ends the session, offer either a short recap, an
in-world keepsake, or an epilogue. Ask which if it is not already selected. An
epilogue may develop the chosen ending, but do not close unresolved storylines
merely because the user paused or stopped replying.
```

A receipt from the disastrous date or a final train ticket can be more memorable than a generic summary. This should be triggered by intention, not inactivity.

## 5. How to implement the tricks without damaging the writing

### Prefer stable templates over new code every turn

For letters, messages and clocks, let the model provide content or structured fields while the app supplies a reusable template. This reduces layout drift and leaves more generation budget for prose. Free-form HTML can remain an advanced, optional creative mode.

Choose a tested set of tags/styles, scoped classes such as `nai-document`, responsive widths and a plain-text fallback. Avoid whole-page selectors, fixed overlays and assumptions about the surrounding app. Do not ask the model to emit executable JavaScript, external embeds or inline event handlers for ordinary story objects. These are product implementation recommendations, not promises about what every ST fork permits.

ST user settings document HTML-related display controls and external-media controls; the exact rendering result depends on the installed renderer, settings and extensions. Verify an example in the intended host rather than assuming a browser-valid snippet is a working chat widget. [T1]

### Keep two representations of visual objects

Recommended storage: canonical content/facts plus an optional rendered view. The outgoing context can include a compact semantic version such as:

```text
Document note-07: found beneath the door; asks for a meeting after the last train
and the blue notebook; signature crossed out. Player has not established reading it.
```

Preserve a small format example separately if the model needs one. One May2026 DeepSeekV4 user report describes HTML omissions and reduced consistency after prior HTML is stripped. This is a test lead, not a verdict on current V4 Pro/Flash. [C4]

Do not use a broad HTML regex as a general parser or sanitizer. Removing tags can leave styles, code or ambiguous concatenated text; removing whole elements can erase clues. Prefer a parser and a deliberate content schema in NarrativeAI. ST regex has distinct display/outgoing/stored-text behavior; test the actual transformed prompt. [T2]

### Define the counter's event semantics before writing its prompt

Every reliable counter needs:

- Scope: session, scene, character, relationship or branch.
- Trigger: accepted qualifying event, not generic message generation.
- Bounds and reset rules.
- A reason/evidence field and duplicate-event detection.
- Behavior for edits, swipes, retries and branching.
- Which audience can see it, and what a threshold authorizes.

Incrementing a macro whenever a prompt is assembled can count previews, retries or extra generations. Commit counters with accepted story events. Preserve alternate swipes as separate branches; do not let discarded replies advance the canonical clock.

### Separate configuration resets from story-state resets

Clearing mode flags during prompt assembly helps prevent stale options. Clearing inventory, memories or relationship progress on every generation destroys persistence. Keep the two namespaces and lifecycles separate. A preset import should initialize configuration; it should not overwrite a continuing story unless the user explicitly starts anew.

### Make optional helpers explicit about cost

A regex rendering pass needs no extra LLM call; a proofreader or companion generating its own text does. If an auxiliary model edits the final prose, that changes authorship. Preserve this project's chosen-model requirement for live drafts and comparison passages, and show costs for optional passes. Disable recursion: a helper's output should not trigger itself again.

### Preserve the stable prefix

Keep static rules and templates stable; place changing state and one-time results in an appropriate later section. Moving random macros out of a shared prefix may improve cache reuse, but caching remains provider-specific. Record actual usage/cache data rather than promising a percentage. A display-only change does not inherently change the prompt; an outgoing-context transform does.

## 6. User and model fit

Ask: “Would you enjoy occasional letters and screens?”, “Do you want visible progress, or would that spoil the feeling?”, “Should other characters have lives you hear about later?”, and “Would suggestions help when you're stuck?” Let users preview one feature at a time.

| User signal | Offer first | Leave off initially |
|---|---|---|
| Wants banter and emotional nuance | Occasional messages, optional keepsakes | Forced counters, frequent event rolls |
| Wants mystery and consequences | Evidence board, suspicion clock, attributed rumors | Revealing NPC private thoughts |
| Wants cozy routines | Scrapbook, recurring rituals, gentle messages | Universal adversity and deadline pressure |
| Wants a busy ensemble | Off-screen updates with clear knowledge boundaries | Every NPC's full internal ledger each turn |
| Wants the model to surprise them | Contextual news and occasional complications | Mandatory random disruption every reply |
| Dislikes “gamey” presentation | In-world documents and qualitative milestones | Exact affection scores and achievement spam |
| Gets stuck writing replies | On-demand action suggestions | Automatic impersonation without permission |

For every target model, start with a short behavioral baseline plus **one** visual or progression module. Test HTML validity separately from narration quality. A model can format perfectly while flattening characters; it can write beautifully while dropping a tracker.

Celia's public Opus4.6 tuning is useful provenance, not evidence for Opus5.5/Fable5.1. RF's MiMo/Gemini/GLM claims justify exact-endpoint trials, not identical settings across models. KimiK3 and DeepSeek variants also need independent checks for constraint overload, output-format omission and native-reasoning interactions. Let a stronger host renderer reduce model formatting demands rather than adding ever-longer corrective instructions.

## 7. Evaluation and export checklist

Test relevant cases once a feature is selected:

1. Ordinary reply with no trigger: the feature stays absent.
2. Triggered reply: one relevant object/update appears without swallowing the prose.
3. Display versus outgoing context: facts survive, abandoned suggestions do not become canon.
4. Knowledge: a private message does not become public character knowledge.
5. Retry/edit/swipe: counters and commitments stay consistent with the accepted branch.
6. Failure: malformed output produces a readable fallback and no invalid state update.
7. Mobile and accessibility: content fits, text explains colors/bars, disclosure is usable.
8. Export/import: required templates, regex/scripts, configuration and accepted state travel with the setup; secrets do not.

Offer an honest dependency manifest: preset/version, model/provider, enabled modules, macro-engine requirement, regex version and purpose, frontend actions, templates, state schema and fallback. Do not label CSS-only controls as connected story actions.

**Recommended next product addition:** an optional “Story extras” step with three groups—objects and screens, memories and relationships, living-world events. Each feature should be independently selectable and removable. This extends the onboarding without turning every user into an RPG player.

## Source register and limits

Accessed 6 October2026. No live paid generations, full preset import, or browser-render integration tests were performed. Source inspections support the feature audit; recipes and architecture are original proposals.

- **C1:** [Celia author page](https://leafcanfly.neocities.org/presets).
- **C2:** [Public Celia5.4 JSON](https://leafcanfly.neocities.org/RE%20(%C2%B4%EF%BD%A1%E2%80%A2%20%E1%B5%95%20%E2%80%A2%EF%BD%A1%60)%20Celia%20V5.4.json), readme, modes, variables and bundled regex inspected.
- **C3:** [Celia5.3 March2026 release](https://www.reddit.com/r/SillyTavernAI/comments/1rm95rf/celia_preset_53/).
- **C4:** [DeepSeekV4 and HTML tags, May2026](https://www.reddit.com/r/SillyTavernAI/comments/1th13p8/deepseek_v4_and_html_tags/), user account; includes unresolved Celia5.8 reference.
- **R1:** [Realistic Frankenstein2.1](https://www.reddit.com/r/SillyTavernAI/comments/1w3m9bb/realistic_frankenstein_21_karma_is_absolute/).
- **R2:** [RF2.2 and Douyin discussion](https://www.reddit.com/r/SillyTavernAI/comments/1wjzj1k/introducing_realistic_frankenstein_22_nuts_bolts/).
- **R3:** [RF2.2.1 release](https://www.reddit.com/r/SillyTavernAI/comments/1wuzlnj/introducing_realistic_frankenstein_221_limitless/).
- **F1:** [Freaky Frankenstein archive](https://rentry.org/freaky-frankenstein-presets).
- **P1:** [Pura author documentation](https://platberlitz.github.io/).
- **P2:** [Director16.0 JSON](https://platberlitz.github.io/preset/Pura%27s%20Director%20Preset%2016.0%20%28SillyTavern%29.json).
- **P3:** [Director regex JSON](https://platberlitz.github.io/preset/Pura%27s%20Director%20Regexes.json), rendering and pruning fields inspected.
- **M1:** [Microcot GitHub repository](https://github.com/aimicrocot/microcot-preset).
- **T1:** [ST user settings](https://docs.sillytavern.app/usage/user-settings/).
- **T2:** [ST regex documentation](https://docs.sillytavern.app/extensions/regex/).
- **H1:** [MDN: details](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/details).
- **H2:** [MDN: progress](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/progress).

Some presets bundle moderation-bypass claims with writing and UI features. Those claims were not validated and are not a prerequisite for the interactive designs here. RF's full downloadable JSON remains unaudited; exact instruction text, active order and dependency flags must be inspected before turning it into a one-click starter.
