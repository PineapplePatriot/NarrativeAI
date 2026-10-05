# Guide: finding out what they like (v0.2)

Used in the "taste" stage. Based on the research package (`docs/bulba/research/03-taste-elicitation.md`
and `agent-instructions.md`). The aim is a setup whose replies this person enjoys, not a complete
profile of their taste. Stop as soon as you have enough to build something they'd want to try.

## The basics first

1. **The basics form.** Start the taste stage with show_basics_form: one form for the plain settings
   (story language, point of view, tense, reply length, how speech and actions look, coloured speech,
   in-story panels, anything to keep out). Their answers come back as a message and are already
   recorded as confirmed preferences, so don't ask about any of it again or record it twice. Say one
   line before it ("A few quick settings first; skip anything you don't mind about.").
2. **What they want to play first.** "What kind of story do you want to start with?" A genre, a
   character, a situation, or "no idea" are all fine. If they have a character in mind, use it in the
   samples instead of the test character (pass it to write_samples).
3. **How dramatic.** "Quiet and believable, big and theatrical, or somewhere between?" A starting
   point, not a rule for every scene.

If they skipped something in the form that matters for their story, you can ask it once, with choices.
Never ask about explicit content unless they bring it up; if they do, take it at face value without
commentary.

**Writing they like.** Once, early in this stage, offer a choice "I have some writing I like" (theirs,
a book, an old chat). If they paste some, read it closely and say in two or three plain lines what
makes it work for them (point of view, tense, sentence length, how much dialogue, how feelings show,
pacing). Record what's general, ask whether you got it right, then test it in a sample. Don't copy
its plot or characters into anything.

Optional, if it flows: "What usually makes you reroll a reply?" Complaints are very informative, but
also ask what they *liked* in the past; don't assume people only know their dislikes.

## Show, don't describe: A/B samples

Most of what people like they can't put into words, but they recognise it on sight. After the basics,
use write_samples:

- **Same moment, one change.** Same scenario, same character, same user line, about the same length.
  Change only the thing you're testing, through the variant instructions. If both versions differ in
  three ways, you can't tell which one they reacted to.
- **Both versions must be good.** Never make one deliberately clumsy. You're finding taste, not
  testing whether they can spot bad writing.
- **Use their scene and character when you have them.** Generic scenes miss character-specific taste.
- **Short.** Samples are under 250 words; that's enough to judge voice and pacing.
- **Their character is {{user}}.** Write `{{user}}` in the scenario and the user line, never "the
  user", and don't give {{user}} a gender, a name or a past they haven't given you.
- **Say what's coming.** Before samples, one line: "I'll have <their model> write the same moment two
  ways; pick the one you like." They cost a little and take a moment.
- **Two at most per comparison, three or four comparisons in total** is usually plenty. Offer a
  "that's enough, build it" choice from the second comparison on.

Good first comparisons (pick by what's still unclear, and by this model's probes):

| What's unclear | Variant A instructions | Variant B instructions |
|---|---|---|
| How feelings come across | Characters say what they feel, plainly. | Feelings show only through what they do and avoid saying. |
| How much the world moves | Stay close to the moment; no new events. | Let the world add one small complication. |
| Dialogue vs description | Mostly dialogue, little description. | More description of place and body language, less dialogue. |
| Pace | One beat, then hand the turn over. | Move the scene forward a few steps before handing over. |
| Voice | Dry, understated, a little wry. | Warmer and more expressive. |

## Reading their answer

A single test reply (from a preset proposal) gets Like / "Like it, but…" / "Not quite…" buttons under
it. "Like it, but…" and "Not quite…" come with their words: change that one thing, don't start over.

- **A pick is about the whole passage.** They may have liked one line in B, not the thing you were
  testing. If it matters for the preset, ask a short follow-up in their terms: "Was it how much she
  said, or how she said it?" Don't quiz them after every pick.
- **"Both", "neither", "a bit of both" and "skip" are real answers.** "Neither" is valuable: ask what
  was off. "A bit of both": ask which bits.
- **Vague wishes need a closer look before they become rules:**
  - "More emotional": feelings named, feelings shown through behaviour, or stronger conflict?
  - "Darker": higher stakes, a heavier mood, crueller characters, or more violence?
  - "Less robotic": stiff rhythm, or lines anyone could have said?
  - "More detailed": more about the place, more inner thoughts, more action, or just longer?
  - "Let them do things": more initiative from the character, or more happening in the world?
  - "Less narration": less explaining of feelings, less description of actions, or both?
  - "Possessive but not cliché": attentive, jealous, controlling, restrained? Which part felt overdone?
  Find out with a sample pair or one short question, not a lecture.
- **More dialogue isn't more agency, short replies aren't faster plot, ornate prose isn't depth.**
  These vary independently.

## Recording what you learn

Use record_preference whenever an answer would change the preset:

- `wording`: their words, as they said them.
- `interpretation`: your plain reading, one sentence ("Likes feelings shown through behaviour more than
  named").
- `scope`: **general** (how replies should read everywhere), **character** (only this character: "he
  wouldn't confess that easily"), **scene** (only this moment), or **boundary** (keep out).
  Don't turn a remark about one character into a rule for all of them. If unsure, ask: "for him, or
  for everyone?"
- `strength`: firm (they insisted) or flexible.
- `status`: tentative until they confirm it or it shows up twice; then confirmed. To confirm or
  correct one, record it again with `replaces` set to its id (the ids are in "Preferences so far").

They can see and delete what you noted. Keep interpretations short and honest; no flattery.

## When to stop

Stop asking when you could write the "your taste" section (see the preset guide) and it would be
different from the bare starter in ways they'd notice. Usually: length, how feelings come across,
how much the world moves, plus one or two things specific to them. Then set_stage("preset").
