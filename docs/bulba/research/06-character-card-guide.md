# A small guide to writing character cards

For SillyTavern and the NarrativeAI preset assistant · 4 October 2026

A useful card gives the model enough information to make this person's next choice, speak in their voice, and preserve their relationships. Start with a readable core; add detail when it solves a specific failure. The writing advice below is a practical starting point, not a universally optimal formula for every model.

## 1. What deserves the most attention

Prioritise **identity, motives, behavioral personality, voice, and the relationship to the user**. Appearance and biography support these; they should not crowd them out.

| Include | What makes it useful |
| --- | --- |
| Identity | Name, age where relevant, role/occupation, setting, and the version of a canon character you mean |
| Motives | What they want now, what they protect, what they fear losing, and what they will not compromise |
| Personality in action | How traits affect decisions, conflict, affection, embarrassment, or pressure |
| Voice | Register, rhythm, directness, humor, vocabulary, and how speech changes with different people |
| Relationship | What they know about the user, history, current trust, friction, and what has not happened yet |
| Relevant background | Events that explain present behavior; facts that must remain consistent |
| Appearance | Distinctive and scene-relevant features; enough to avoid basic continuity mistakes |
| Knowledge and abilities | What they can do, what they know, and important limitations |

**Translate adjectives into behavior.** “Proud, guarded, caring” permits many interpretations. “Accepts practical help reluctantly; redirects personal questions; quietly repairs things for people he cares about” is more specific.

Give important traits conditions. “Never shows emotion” can flatten a character. “Keeps his composure in public; becomes blunt rather than eloquent when frightened” leaves room for different situations.

Complexity needs logic: explain when a contradiction emerges. A character can be affectionate and distrustful, or cruel and loyal. Specify to whom, under what circumstances, and at what cost. Do not require every trait to appear in every reply.

## 2. Where to put it in SillyTavern

These field functions are documented in SillyTavern [1]; the priorities are practical writing recommendations.

| Field | Use |
| --- | --- |
| Description | Stable essentials and defining behavior; make this your core |
| Personality summary | Optional brief reminder, rather than a duplicated biography |
| Scenario | Starting circumstances and relationship context |
| First message | A playable opening demonstrating the intended voice and presentation |
| Example dialogue | Short samples of distinctive speech and reactions |
| Creator's Notes | Reader-facing notes; not a reliable place for model instructions |
| Advanced prompt overrides | Use deliberately; they can replace preset instructions depending on settings |

Description, Personality and Scenario ordinarily remain in context. The greeting becomes chat history; examples can be displaced unless retained by settings. Essential facts therefore belong in the core, not only in an example. Custom prompt configuration can alter inclusion. [1]

Keep a starting event distinct from permanent facts: “they are meeting at a station” should not make every future scene occur there. Update stale context when the story moves on.

## 3. Syntax: readable text is enough

Use plain prose, headings, or labelled bullets. There is no required special personality notation. W++-style strings, JSON-looking lists, XML and brackets are formatting choices, not guarantees of better characterization. Avoid elaborate structure unless it helps the selected model or your workflow.

SillyTavern's dialogue-example syntax is [1]:

```text
<START>
{{user}}: "You could have asked for help."
{{char}}: "I could have." He pushes the repaired lamp toward you. "It works now."

<START>
{{user}}: "Are you worried?"
{{char}}: "I'm checking the exits. Call it what you like."
```

`{{char}}` and `{{user}}` are placeholders. Quotation marks and `*action text*` are presentation choices. `[Voice]` is an ordinary label, not a special command. An exported JSON card is a container format; its text fields can still contain natural language. [1–2]

## 4. A copyable core template

Paste this into Description and remove unneeded headings. It is an original writing scaffold, not an importable JSON file.

```text
Identity:
{{char}} is [name, age if relevant, role, setting/version].

Appearance:
[Two or three distinctive details that matter during scenes.]

Motives and limits:
[What they want; what they protect; what they will not compromise.]

Behavior:
[How they act normally and under pressure.]
[How they disagree, show care, and respond to vulnerability.]
[When apparently contradictory traits emerge.]

Voice:
[Register, sentence rhythm, humor, vocabulary.]
[How speech changes with intimacy, anger, or uncertainty.]

Background:
[Only history that changes present choices or must stay consistent.]

Relationship with {{user}}:
[Existing history, roles, trust, tensions, and assumptions.]
[What is unresolved; leave future development open.]

Knowledge and abilities:
[Relevant skills, limits, secrets, and who knows what.]
```

Avoid scripting a predetermined romance or redemption unless that is the intended premise. “Distrusts the user after a broken promise” supplies playable tension; “will forgive them on turn five” fixes the outcome before play.

For canon characters, specify timeline, portrayal and deliberate deviations. Do not assume the model's knowledge will preserve your particular interpretation.

## 5. Greeting and examples

A greeting should establish a situation, demonstrate the character, and leave something meaningful for the user to do. Avoid choosing the user's response or private feelings unless the premise explicitly authorises this.

For example:

> The last train has gone. Viktor folds the timetable once and slips it into his coat. “Excellent planning.” His gaze moves to the lit café across the street. “We can wait there. Unless you've arranged a second miracle.”

Write an opening in the density and format you actually enjoy. A long descriptive greeting is a poor demonstration of brisk exchanges.

Start with two or three short examples of different situations: disagreement, relaxed conversation, and a moment of vulnerability. This is a manageable starting suggestion, not a proven optimum. Show the voice rather than asking the character to recite their personality. Do not fill every example with the same catchphrase; imitation can become repetition.

## 6. Keep character and preset responsibilities clear

The **card** defines this person's identity, motives, voice, and relationships. The **preset** carries broader writing preferences, interaction rules and supported model configuration. Character-specific narration can live in the card when intentional; avoid accidentally embedding an entire incompatible preset.

Detailed world lore can go into a lorebook. Keep facts essential to understanding this character in the core instead of assuming a triggered entry will always appear.

Length has no universal sweet spot. Begin with enough detail to distinguish the character. Cut repeated information and irrelevant facts before cutting defining motives. More context capacity does not make every extra paragraph useful.

## 7. A quick check before expanding the card

Try ordinary conversation, disagreement, and a stressful event. Check:

- Would this reply still fit five unrelated characters? Strengthen motive or voice.
- Does the model repeat a listed trait every turn? Rewrite it as conditional behavior.
- Does affection erase the character's difficult habits? Explain what changes and what persists.
- Does the character know something they could not know? Clarify the knowledge boundary and check supplied context.
- Is the opening doing too much for the user? Leave their next decision open.
- Does a rule conflict with the preset or example dialogue? Resolve the conflict before adding another prohibition.

Change one relevant section, then try a fresh scene. A good card creates consistent possibilities; it should still allow surprise.

## Sources

[1] SillyTavern, Character Design, checked 2026-10-04: https://docs.sillytavern.app/usage/core-concepts/characterdesign/

[2] Character Card V2 specification, checked 2026-10-04: https://github.com/malfoyslastname/character-card-spec-v2/blob/main/spec_v2.md

Technical field/syntax details come from these sources. The template, examples, priorities and testing suggestions are proposed writing guidance; they have not been benchmarked across the project's target models.
