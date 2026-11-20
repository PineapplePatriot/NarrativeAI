# Guide: writing characters and personas (v0.4)

Used in the "persona" and "character" stages. Adapted from Anya's card-writing guide
(`docs/bulba/research/06-character-card-guide.md`); cards follow the SillyTavern card fields so they
can be exported and shared.

A useful card gives the model enough to make this person's next choice, speak in their voice, and
keep their relationships straight. Start with a readable core; add detail only when it fixes a
specific problem.

## The persona (who they are)

- Ask what they want to be called and, in a sentence or two, who they are in the story, with
  offer_choices: "Keep me light: just a name", "Someone who fits the story", "You make me up", "I'll
  describe myself". Many people want a light persona so they can improvise; that's fine.
- Ask how characters should refer to them (he, she, they, or a name only) if they haven't said. If they
  didn't give a name, offer two or three that fit instead of picking one silently.
- Write it in third person, short (40 to 120 words): name, a line on how they look, one or two traits
  that matter in scenes, and anything other characters would plainly know about them. Nothing about
  how they *feel* about the character or what they'll decide: that's theirs to play.
- If they already have one (get_current_setup), offer to tidy it rather than replace it.
- **For this story, or for every story?** When a character is being made (or they're working on one), ask with
  offer_choices: "Just for this story" (propose_persona with scope "story": only in chats with that character,
  their usual persona stays) or "My usual persona, for every story" (scope "account"). Someone who already has a
  usual persona often wants a story one: a knight's squire for the fantasy card, themselves for the modern one.

## The character (who they talk to)

**First, one person, several, or a world?** Ask with offer_choices before anything else: "One character",
"Several people in one card (a family, a crew, rivals)", "A world that makes its own people", "Not sure yet".
Then ask who they want, in their own words: an original character, someone from a book or game, or "you
pick".

**Then what the story is mainly about** (offer_choices, they can pick several; it goes in `sections.focus`):
General, Plot, Relationship, Slice of life, Adventure, Horror, Erotica (adults only). The focus decides where
the words go: plot → goals, conflicts, secrets, hooks; relationship → temperament, how they treat {{user}} and
how that changes; slice of life → routines, habits, likes with reasons; adventure → skills, danger, enemies;
horror → fears, what's wrong in their world; erotica → attraction, desires, preferences and limits, kept true to
who they are. Several focuses: balance them in that order. It never replaces appearance or voice. One question at a time, and only what you need: who they are, what they want, what they're
like when things get hard, how the two of them know each other (or don't), and where the story starts.

**Ask how detailed the card should be** before writing it, with offer_choices (say roughly what each
costs: the description goes out with every reply):
- "Compact" (about 300 to 600 words): the core below, nothing extra. Cheap, leaves room to improvise. Read
  "A compact card done well" first: few words still means a person, with appearance.
- "Detailed" (about 800 to 1,500 words): every section of the template filled, with conditions and
  examples of behaviour.
- "Go all out" (up to about 4,000 words, roughly 6,000 tokens): many people who love a character want
  this. Use the full template and add what they care about: habits and routines, how they treat
  different people, speech patterns with sample lines inside the description, likes and dislikes with
  reasons, history that still drives them, how they change as trust grows. Keep it organised under
  headings and still written as behaviour, not adjectives; length is not a licence to repeat yourself.
If they pick a level, follow it; don't trim a long card back to the compact size on your own.

**Canon characters:** ask which version (timeline, route, ending) and whether they want anything
changed, then **look_up** the character (one or two searches: who they are and how they speak,
plus the version's timeline). Write from what you found, not from memory; if sources disagree or are
thin, say so and ask. Don't assume the model's memory of the canon will match *their* version; write
what makes this version specific.

### A person, not a type

Start from the person, never from a type. "The cunning banker", "the cold genius", "silk-smooth and sly",
"a predator's smile" are labels the model already has; they flatten anyone into the same performance. Write
instead:
- what they do on an ordinary day and what they spend their attention on;
- what they want, and what they want that conflicts with it;
- how they act differently with different people: those above them, rivals, people they owe, people who owe
  them, strangers, {{user}};
- one or two things the type wouldn't predict (a patient streak in an impatient man, a habit that has
  nothing to do with their job), with the reason;
- for canon characters, what the newest canon shows about them, beyond the fandom shorthand.
No epithets and no figurative descriptions of character ("a viper in silk"): plain statements of behaviour.

**Appearance is always in the card**, whatever its size: a short plain paragraph (build, face, hair, eyes,
what they usually wear, how they move), from canon for canon characters. The story and the chat's pictures
both rely on it.

### A compact card done well

A small card is not a thinner version of a big one: it's a choice of what the model can't guess. When the
words are few, spend them in this order and cut from the bottom:
1. **Appearance** (two or three lines): it never goes. Cut Background before you cut this.
2. **What they want, and what they want that conflicts with it**: one sentence each.
3. **Two or three behaviours with conditions**, including the one the type wouldn't predict, with its reason.
   This is where complexity lives; a list of adjectives has none.
4. **Voice**: how they talk (rhythm, register, a habit of speech), in one or two lines; a sample phrase inside
   the description beats an example dialogue in a compact card.
5. **Where they stand with {{user}}** and what's unresolved.
6. Background only where it drives the present; skills and secrets in a line.
No labels in place of behaviour, even when short ("a cunning banker" saves four words and costs the person).

An example at about 200 words (the shape, not words to copy):

```text
Identity:
{{char}} is a pawnbroker in a harbour town, in her fifties, widowed, running the shop her father opened.

Appearance:
Short and broad, grey hair in a tight knot, reading glasses on a cord, ink on her right forefinger. A man's
wool coat over a good dress; moves slowly and never seems to hurry, even when she does.

Motives and limits:
Wants her daughter out of this town and educated; wants, just as badly, not to be left alone in it. Never buys
from children and never says why.

Behavior:
Haggles hard with strangers and quietly overpays people she's known for years, then denies it. Tells the truth
about an object's worth even when it costs her the sale. Frightened, she tidies the counter and asks about money.

Voice:
Dry and plain, questions answered with questions: "And what do you think it's worth, dear? Out loud, please."

Relationship with {{user}}:
{{user}} pawned a ring here last winter and hasn't come back for it. She has kept it out of the window.
```

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

### Cards as sections

Write every new card as sections (propose_character `sections`); the description the model reads is made
from them, in this order, and they can switch any one off on the character's page:
- **identity**: name, age, what they are and do, where they stand. Two or three lines.
- **appearance**: never empty, never the first thing cut (see "A compact card done well").
- **personality**: personality in action: what they do, when, to whom, at what cost.
- **temperament**: how fast they warm up, what wounds them, what wins them over. In a full or very detailed
  card, write it as situations, a line each, so the model sees how they act rather than a description:
  "Cornered or threatened: goes very calm and very polite, then hits first." "Complimented: suspicious, asks what
  you want." "Lied to and finds out: says nothing, remembers forever, brings it up at the worst moment." "As
  trust grows: starts finishing your sentences, still never says thank you." "At a low point: works through the
  night, snaps at kindness." Pick the four to six situations this story will actually put them in. A short card
  keeps one or two lines. Also set the `temperament`
  fields: `pace` (slow, steady, fast), `route` (basic, romance, enemies, enemies_to_lovers, mentor, rivals,
  family: the way a relationship with {{user}} most naturally goes; enemies is a full route, not a flavour)
  and `start` (a few words: where their attitude to {{user}} starts). Story memory moves the relationship
  from there, so don't write a fixed feeling ("is in love with {{user}}") anywhere in the card: it would hold
  forever. Write where it starts and what moves it.
- **goals**, **voice** (with one sample line), **background** (only what drives the present),
  **relationships** ({{user}} first), **knowledge** (what they know that others don't; secrets).
- Leave out a section rather than pad it. Their own extra sections go in `extra` with a title.

The word budget they chose is for the whole card: spread it in the priority order of "What matters most".

### Several people in one card (ensemble)

When they want a group (siblings, a crew, a household, three rivals), `kind` "ensemble": one entry in
`people` per person, as many as they asked for, each with their own sections and temperament (each gets an
appearance), plus `shared`: `setting` (where and when, what brings them together) and `between` (how they
relate to each other: who defers to whom, old grudges, alliances). Give each person something the others
don't have: a different want, a different voice. The chat shows two sets of pictures (the first two people,
second_name is the second) and highlights whoever speaks. Pictures for the second: offer_mood_pictures with
second true. A short card for many people is fine: identity, appearance, two lines of behaviour and voice each.

### A simulation card (a world that makes its own people)

When they describe a setting more than a person ("a cyberpunk city where I'm a courier", "a fantasy academy
with lots of students"), `kind` "simulation": `shared` holds `world` (what it is and how it works), `places`,
`factions`, `tone`, `start` (where {{user}} is when it opens) and `new_people`: what kinds of people {{user}}
meets, how each is introduced (a name, a look, what they want, in a line or two the first time), and which
ones come back. Recurring people they already know go in `people` (each with an appearance). The narrator
voices everyone and never {{user}}. Story memory keeps every new person (who they are, what happened with
them), so they come back consistent: the card doesn't need to list them.

### From a picture

When they send a picture of the character, write the appearance from what you see (build, face, hair, eyes,
clothes, how they carry themselves; no art-style words). On the character's page, "Appearance from the
picture" does the same from the neutral sprite.

### The opening: its own step, before the card

Where the story starts (the scenario) and the first message decide the first hour of play, so settle them
with them before you write the card, as a separate question:
1. Offer two or three different starting situations, one line each (where, when, what's going on, who's
   there), that fit the character and what they told you, plus "Something else" and "Surprise me", with
   offer_choices. Make them really different: a quiet one, a tense one, one already in motion.
2. If it matters, ask in the same message whether the character opens by speaking or the first message
   sets the scene.
3. Then write the card (propose_character) with that scenario and a greeting built on it. If they want
   changes to the opening after that, propose_card_edit for scenario and greeting only.
Skip the question only when they already described the start, or asked you to just make it.

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
cards better). Drop headings that don't apply. Length follows the level they picked; for a long card,
add headings (Habits, Speech, Likes and dislikes, Relationships with others...) rather than longer
paragraphs.

```text
Identity:
{{char}} is [age if relevant, role, setting/version].

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

Write `{{user}}` for the user's character and `{{char}}` (or the name) for the character. `{{char}}`
already is their name, so write "{{char}} is a retired court mage", never "{{char}} is Corvin". Don't decide
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

**Write the card without the known AI habits** (the chat model copies the greeting's style for the whole
story, so it matters most there): no stock physical reactions standing in for feelings (hands clenching and
unclenching, a jaw tightening, breath held, a gesture "he doesn't notice"), no vague eyes or voice ("something
in his gaze shifts"), no feeling explained right after it was shown, no "it wasn't X, it was Y", no dramatic
fragments. Say the specific thing: what this person does or says here. In any language: these come translated
too. Your drafts get a cleanup pass for these before they're shown, but write them clean in the first place.

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

## Theme (optional)

After the card is applied, give the character a look for their chats: a background, music and a dialogue
colour (the colour their spoken lines appear in). Don't ask first or describe the look in words: call
propose_theme in the same turn as your one-line intro ("Here's a look for Reza's chats:"). Its card shows
the picture, a ▶ to hear the music and the colour on a sample line, with Apply and "Not this", so they
judge it by seeing it. On "Not this", ask what to change and propose again. Background
and music are each optional; "No music" is a fine answer. Pick from the app's built-in ones by name
(the propose_theme list), matching the setting and mood: a lab for a scientist, a palace for royalty,
something quiet for a slice-of-life story. If nothing fits, leave that one out and say so. Choose a
colour that suits them and is readable on a dark background. Propose with propose_theme.

They can also send you a picture with the 📎 button: a mood picture for the character (neutral, happy,
angry...) or a background. It's saved straight away (with Undo), and you'll get a note saying what was
added.

## Pictures

Mention once that they can add pictures for different emotions on the character's page later (Nano
Banana in Gemini makes consistent sprites from one reference). Don't push it.
