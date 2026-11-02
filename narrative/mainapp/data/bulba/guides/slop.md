# Slop: AI writing habits and how to counter them

"It sounds AI-written" is a complaint, not a diagnosis. Turn it into one named pattern you can quote from
their chat, check it against what they want (a habit one person hates is another's style), then propose the
smallest counter. Everything below is a list of things to check for, not a verdict: a model's dossier says what
to look at first, their actual replies decide what's wrong. Never paste this catalog into a preset.

## First: which layer is wrong

- **Words** (same phrases again): repeated words *and* their paraphrases. A scoped rule plus one edited sample.
- **Rhythm** (everything sounds dramatic): fragments, parallel clauses, the same sentence shapes. Describe the cadence they want; one example.
- **Dialogue** (everyone sounds like a therapist or a comedian): the character's voice and the situation, in the card.
- **Decisions** (they became nice/evil/stupid): motives and evidence. Fix behaviour, not adjectives.
- **Scene** (nothing happens / everything happens): where the reply stops, who acts next.
- **Knowledge** (they know what I thought): who saw or learned what. A clear rule on whose knowledge is whose.
- **Long-chat repetition** (same scene, new words): the next thing that should change.
- **Plumbing** (empty, garbled, cut off): the raw reply, length limit, text rules. Fix that before style.

A word ban never fixes a decision problem: removing "possessive" doesn't stop possessive behaviour.

## The patterns (ID, what it looks like, the counter to try)

- S01 Corrective contrasts: "It wasn't anger. It was something older." → State the feeling or action directly; keep contrasts for real misunderstandings.
- S02 Staccato intensity: "The key. His hand. Still." → Complete, varied sentences; a fragment earns emphasis in a specific moment.
- S03 Decorative threes, stacked synonyms → Pick the detail that carries the point.
- S04 Stock body language (jaw tightens, a beat) → Use a physical cue only when it reveals something; an unneeded beat can be left out.
- S05 Sensory confetti, random scents → Sensory detail needs a source and a role in the moment.
- S06 Metaphors that say little → One precise image or a plain observation.
- S07 Job eats the personality (the scientist talks in ledgers) → Work shapes knowledge, not every metaphor.
- S08 Dialogue labels repeating what's clear ("she said, coldly") → Let the line and the action carry it.
- S09 An emotion report after every line → Leave some implications to the reader.
- S10 Echoing their words and analysing them → Answer the substance; echo only for disbelief or clarification.
- S11 Therapist voice ("your feelings are valid") → Comfort in this person's own words; practical help, awkwardness or silence are fine too.
- S12 Compulsory comebacks → Characters may answer plainly or let someone else have the last good line.
- S13 Aphorism instead of an answer → Answer from the speaker's situation; an evasion can be specific.
- S14 Profound binary ending ("You're either very brave or very cruel") → End on the scene's action or opening.
- S15 Instant self-diagnosis and confession → Disclosure matches trust; people act on motives they can't name.
- S16 Positivity smoothing, quick reconciliation → Forgiveness and trust follow events; repair can be partial.
- S17 Anti-positivity overdone (everyone hostile) → Ordinary kindness and routine stay ordinary; resistance needs a stake.
- S18 One trait performed every turn → Traits are tendencies shown through relevant choices.
- S19 Everything flattened into dominance/submission → Keep motives, competence and limits across all scenes.
- S20 Omniscience (characters know what they couldn't) → Characters act on what they perceive or reasonably infer.
- S21 Writing for the player → Their dialogue, choices and thoughts stay theirs (check their authorship mode first).
- S22 Recap instead of a reply → Start with the effect or the answer.
- S23 Stalling with ceremony (about to answer, never does) → Preparation leads to an answer within the reply.
- S24 Rushing past the moment, time skips → Develop the exchange; stop when their response is needed.
- S25 A forced interruption or cliffhanger every reply → A quiet reply may end with an opening.
- S26 The same scene shape in different words → Carry forward what changed; don't replay the same outcome.
- S27 False closure, the moral of the scene → End at the relationship's actual scale.
- S28 Abstract status updates ("trust deepened") → Ground change in what someone does or withholds.
- S29 Spatial or bodily mistakes → Keep positions and held objects straight before adding flourish.
- S30 Mixed languages, broken text → Check the raw reply and text rules first; then a language line.
- S31 Instructions leaking into the story → Simplify contradicting rules; don't just hide the leak.
- S32 Every fix makes the prose beige → Keep voice and texture; remove ornament, not personality.

## What to check first, by model (reports, not verdicts)

- Opus 5.5: S01 S07 S18 S32 (cold-start voice, ledger metaphors, reinterpreting the character).
- Opus 4.6: S01 S02 S04 S10 (pause labels, chopped actions).
- Opus 4.7: S02 S28 S32 (minimal, thin scenes).
- Fable 5.1: S06 S09 S24 (dense, mannered prose; time skips).
- Kimi K3: S07 S23 S24 S31 (pacing extremes, profession fixation, checking leaks).
- MiMo v2.6 Pro: S16 S17 S26 S31 (repeated scene choreography; sensitive to contradicting instructions; inherited anti-positivity goes too far).
- Gemini 3.8 Flash: S12 S19 S20 S21 (one-upmanship, power flattening, knowledge and agency drift).
- Gemini 4 Argon: S18 S24 S28 S32 (rushing or flat short replies, trait overuse; it ignores sampler settings, so don't prescribe temperature).
- GLM 5.3: S07 S13 S20 S28 (corporate or aphoristic lines, "okay" loops, knowledge laundering).
- DeepSeek V4 Pro: S10 S14 S22 S26 (repeated room and action descriptions, binary closers).
- DeepSeek V4 Flash: S18 S26 S29 (repetition, persona and card traits crossing over).

## Choosing the counter

- A **scoped** rule names the unwanted *function* and allows leaving it out: "Avoid jaw tension or its paraphrases
  as automatic emotional punctuation; if no detail adds meaning, omit the beat." Not "never write 'jaw
  tightened'" (the model writes "his mandible locked"), and not "replace every jaw reaction with a unique gesture"
  (now everyone fidgets with objects).
- Never a blanket ban on normal language (contrast, metaphor, questions, pauses).
- Positive instruction for something missing; one short example for rhythm or register; a card line for the
  character's voice; editing a few early replies when the chat itself teaches the habit (models copy the history).
- Bulba's polish (the automatic fix) for leftover surface habits in otherwise good replies.
- Expression vs decision: "don't call him possessive" changes words; "don't turn every disagreement into an
  ownership claim" changes behaviour. If they *want* the dynamic, ask which part bothers them.
- Watch for overcorrection: removing all wit, making every sentence long, or a "no new events" rule that leaves
  an inert reply. After a fix, the voice, humour and tension they liked must survive.

## Workflow

1. Ask for (or find) a reply that shows it, and what effect they dislike.
2. Look for the cause in the preset, card, greeting and recent replies before adding anything. MiMo especially
   reacts badly to contradicting rules: remove a conflict before adding a fix.
3. One mechanism at a time, then rewrite the last reply to compare. Say a counter is worth trying, not that it
   works, until their replies show it.
