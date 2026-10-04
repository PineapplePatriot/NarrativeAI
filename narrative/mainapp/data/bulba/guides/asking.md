# Guide: finding out what they like (v0.1)

Used in the "taste" stage. Based on the research package (`docs/bulba/research/03-taste-elicitation.md`
and `agent-instructions.md`). The aim is a setup whose replies this person enjoys, not a complete
profile of their taste. Stop as soon as you have enough to build something they'd want to try.

## The basics first (two or three messages, not a form)

Ask in everyday words, one at a time, skipping anything you already know:

1. **What they want to play first.** "What kind of story do you want to start with?" A genre, a
   character, a situation, or "no idea" are all fine. If they have a character in mind, use it in the
   samples instead of the test character (pass it to write_samples).
2. **How much they like to read before their turn.** Offer three choices: "a few lines", "a few
   paragraphs", "a proper chunk". This becomes the reply length.
3. **How dramatic.** "Quiet and believable, big and theatrical, or somewhere between?" A starting
   point, not a rule for every scene.
4. **Anything to keep out.** Ask once, plainly, and accept "nothing". This is a boundary, recorded with
   scope "boundary". Never ask about explicit content unless they bring it up; if they do, take it at
   face value without commentary.

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
- `status`: tentative until they confirm it or it shows up twice; then confirmed. If they correct
  you, record the new one with `replaces`.

They can see and delete what you noted. Keep interpretations short and honest; no flattery.

## When to stop

Stop asking when you could write the "your taste" section (see the preset guide) and it would be
different from the bare starter in ways they'd notice. Usually: length, how feelings come across,
how much the world moves, plus one or two things specific to them. Then set_stage("preset").
