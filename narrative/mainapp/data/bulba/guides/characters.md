# Guide: writing characters and personas (v0.2)

Used in the "persona" and "character" stages. Adapted from Anya's card-writing guide
(`docs/bulba/research/06-character-card-guide.md`); cards follow the SillyTavern card fields so they
can be exported and shared.

A useful card gives the model enough to make this person's next choice, speak in their voice, and
keep their relationships straight. Start with a readable core; add detail only when it fixes a
specific problem.

## The persona (who they are)

- Ask what they want to be called and, in a sentence or two, who they are in the story. Many people
  want a light persona so they can improvise; that's fine.
- Write it in third person, short (40 to 120 words): name, a line on how they look, one or two traits
  that matter in scenes, and anything other characters would plainly know about them. Nothing about
  how they *feel* about the character or what they'll decide: that's theirs to play.
- If they already have one (get_current_setup), offer to tidy it rather than replace it.

## The character (who they talk to)

Ask who they want, in their own words: an original character, someone from a book or game, or "you
pick". One question at a time, and only what you need: who they are, what they want, what they're
like when things get hard, how the two of them know each other (or don't), and where the story starts.

**Canon characters:** ask which version (timeline, route, ending) and whether they want anything
changed. Don't assume the model's memory of the canon will match *their* version; write what makes
this version specific.

### What matters most

Spend the words on **identity, motives, personality as behavior, voice, and the relationship to the
user**. Appearance and biography support these; they don't crowd them out.

- **Turn adjectives into behavior.** "Proud, guarded, caring" can mean anything. "Accepts practical
  help reluctantly; changes the subject when asked personal questions; quietly fixes things for people
  he cares about" can't.
- **Give traits conditions.** Not "never shows emotion" but "keeps composure in public; gets blunt,
  not eloquent, when frightened". A trait without conditions gets repeated every reply.
- **Contradictions need logic.** Affectionate and distrustful, cruel and loyal: say to whom, when, and
  at what cost. Not every trait has to show up in every reply.
- **Don't script the outcome.** "Distrusts {{user}} after a broken promise" is playable tension;
  "forgives them eventually" decides the story before it starts. No predetermined romance or
  redemption unless that's the premise they asked for.
- **Knowledge boundaries.** Say what they know, what they don't, and any secrets (and who knows them).

### Fields (propose_character)

| Field | What goes in it |
|---|---|
| `description` | The core. Stable essentials and defining behavior, written with the template below. |
| `personality` | Optional: one or two lines as a reminder. Never a second biography. Usually leave empty. |
| `scenario` | Where and when the story starts, and the situation. Two to four sentences. |
| `greeting` | The first message (see below). |
| `example_dialogue` | Optional: two or three very short exchanges showing their voice. |

The description and scenario are sent with every reply; the greeting just becomes the first message
of the chat, and examples can get pushed out in long chats. So **anything essential goes in the
description**, never only in an example or the greeting.

Keep the starting situation in the scenario, not the description: "they're meeting at a station"
in the description makes every future scene happen at a station.

### Description template

Third person, plain labelled text (no special formats; W++, brackets or JSON-looking lists don't make
cards better). Drop headings that don't apply. Usually 250 to 600 words.

```text
Identity:
{{char}} is [name, age if relevant, role, setting/version].

Appearance:
[Two or three distinctive details that matter in scenes.]

Motives and limits:
[What they want; what they protect; what they will not compromise.]

Behavior:
[How they act normally and under pressure.]
[How they disagree, show care, and respond to vulnerability.]
[When the apparently contradictory traits come out.]

Voice:
[Register, sentence rhythm, humor, vocabulary.]
[How their speech changes with closeness, anger, or uncertainty.]

Background:
[Only history that changes present choices or must stay consistent.]

Relationship with {{user}}:
[Existing history, roles, trust, tensions, assumptions.]
[What's unresolved; leave where it goes open.]

Knowledge and abilities:
[Relevant skills, limits, secrets, and who knows what.]
```

Write `{{user}}` for the user's character and `{{char}}` (or the name) for the character. Don't decide
the user's feelings, history or role unless they told you. Mature details (sexuality, violence) only
when the user brought them up or the canon character clearly needs them; plainly, without moralising.

### Greeting

It sets up a situation, shows the character in their voice, and leaves the user something real to
do. Don't choose the user's reply or their private feelings. Match the reply length and style they
picked in the taste stage: a long descriptive greeting teaches long descriptive replies.

> The last train has gone. Viktor folds the timetable once and slips it into his coat. "Excellent
> planning." His gaze moves to the lit café across the street. "We can wait there. Unless you've
> arranged a second miracle."

No backstory summary in the greeting; let it come out in play.

### Example dialogue

Only if it helps (a distinctive voice is the usual reason). Two or three short exchanges in different
situations: a disagreement, something relaxed, a vulnerable moment. Show the voice, don't have them
recite their personality, and don't reuse one catchphrase in every example (models copy it). Format:

```text
<START>
{{user}}: "You could have asked for help."
{{char}}: "I could have." He pushes the repaired lamp toward you. "It works now."
<START>
{{user}}: "Are you worried?"
{{char}}: "I'm checking the exits. Call it what you like."
```

### Card vs preset

The card is this person: identity, motives, voice, relationships. Their general taste in replies
(length, how feelings come across, pacing) lives in the preset. Character-specific taste you recorded
(scope "character") goes in the description as behavior. Don't put writing rules in the card.
Detailed world lore belongs in a worldbook, but facts essential to understanding the character stay
in the description.

### Checking it

After they apply, if they want to try it, suggest an ordinary exchange, a disagreement and a
stressful moment. If replies feel off:

- Could this reply belong to five other characters? Strengthen motive or voice.
- Is a trait repeated every turn? Rewrite it as conditional behavior.
- Did affection erase their difficult habits? Say what changes and what stays.
- Do they know things they couldn't? Clarify the knowledge boundary.
- Is the greeting doing too much for the user? Leave the next decision to them.
- Does something in the card fight the preset or the examples? Fix the conflict before adding a rule.

Change one section at a time.

## Pictures

Mention once that they can add pictures for different emotions on the character's page later (Nano
Banana in Gemini makes consistent sprites from one reference). Don't push it.
