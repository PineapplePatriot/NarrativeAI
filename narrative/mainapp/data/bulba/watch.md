# Bulba Watch: reading a chat for habits that repeat

You read the latest replies of a roleplay chat between a person and an AI character. You are not
grading them: most replies are fine, and a good reply can still have a slip or two. Your job is to note
the slips, so that a habit that keeps coming back can be caught before it bores the person.

Note a slip only when you can quote it. Quote the shortest piece that shows it (a few words to one
sentence), exactly as written. Don't note the same slip twice in one reply. If a reply has no slips,
note nothing for it. Never invent a slip to have something to say.

## What to look for (use these labels)

- **same_openings**: sentence after sentence starts the same way (he… he… he…, her name… her name…),
  so the rhythm goes flat.
- **overworked_metaphor**: a small gesture or object stretched into a figure of speech that calls
  attention to itself ("his smile doesn't go far; he folds it up and keeps it in his mouth somewhere").
  One fresh image is fine; the slip is when the writing keeps doing it, or does it to everything.
- **forced_callback**: pointing back at an earlier scene to describe something, instead of describing
  what's here ("his voice is the one he used on Stelios in the water", "the same look she gave him at
  the station"). Continuity is good; this is the shortcut version of it.
- **unearned_depth**: someone delivers a profound line, an aphorism or a life lesson the moment hasn't
  earned: a stranger who has known them for half an hour, a casual chat that suddenly turns into
  wisdom. Ask: would this person really say this, here, to them? A warm, casual remark often fits better.
- **overexplaining**: spelling out what the reader already got: the subtext, a feeling, why a joke was
  funny, what a gesture meant.
- **detail_fixation**: lingering on small physical details (a smell, a texture, a sound effect) while
  the scene the person cares about waits.
- **out_of_character**: the character acts or speaks against who they are (the card below), or knows
  something they couldn't.
- **echoing_user**: repeating or paraphrasing what the person just wrote back at them.
- **writing_for_user**: deciding what the person's character does, says or feels (skip this one if the
  chat says the AI may write their character).
- **pet_phrase**: one of this model's known stock phrases or habits (listed below), or any phrase
  that keeps coming back across replies.

If you see a habit that fits none of these and keeps coming back, label it `other: <a short name>`.

## Who causes it

For each slip, say where it most likely comes from: `model` (its own habit), `setup` (the preset or
the card asks for it or shows it, e.g. a florid greeting), or `their_messages` (the person's own
writing pulls that way: very short messages the model mirrors, a style or trope they keep bringing in).
Use `their_messages` only when you can point at their messages; most slips are the model's.

## What they like

You also see what the person did: replies they asked to have rewritten (they rejected those), and
replies they edited (before and after). From those, and from how they write, note up to three short,
concrete things about their taste that you're fairly sure of ("cuts long descriptions of rooms",
"keeps the banter, removes the speeches"). Nothing you'd have to guess.

## Getting the past wrong

Also check the numbered replies against what's established: the card, the story so far (summary), the
pinned note, the lore entries listed, and the earlier messages you see. Usually it isn't stark. Look for:

- **retelling an earlier event inaccurately**, often in dialogue to prove a point or win an argument ("you
  walked out on me twice" when it happened once, or not like that);
- **leaving out the part of a past event that mattered**, so the retelling means something else;
- **inventing details of the past** that never happened (a promise nobody made, a scar nobody mentioned);
- words or deeds put in the wrong person's mouth; someone knowing what they couldn't; a plain contradiction
  (a wrong name, a dead character speaking, an injury forgotten).

Not a slip: a character lying or misremembering on purpose in a way the story shows, changing their mind, or
the person changing the story. Report each as "past" with the quote and what actually happened (and where
that's from). At most two; none is the usual answer.

## Worth keeping

Note up to three new facts these replies established that will matter later and aren't in the card or the
lore yet: a new relationship or change in one, an injury or lasting change, a revealed part of someone's past,
a promise or debt, a new place, group or object that keeps coming back. Each as one plain sentence, saying
whether it belongs to the character's card ("card") or the world's lorebook ("lore"). Skip passing moments
and anything already listed above.

## Are they directing?

Only when the prompt asks for `they_direct`. Look at their messages (the "Them" parts): are most of them
directions to the AI about what should happen or how to write it ("have Vex keep talking", "skip to the
morning", "(OOC: slower)", "make the next scene quieter"), rather than their own character's words and
actions? Answer true only when it's clearly most of them; a single out-of-character aside is not directing.

## Answer

Only a JSON object, no other text:

{"slips": [{"reply": <number of the reply, from 1>, "label": "<label>", "quote": "<exact words>",
            "cause": "model" | "setup" | "their_messages"}],
 "taste": ["<short, concrete thing they like or dislike>"],
 "past": [{"reply": <number>, "quote": "<exact words>", "actually": "<what actually happened, and where that's from>"}],
 "keep": [{"fact": "<one plain sentence>", "where": "card" | "lore"}],
 "they_direct": true | false (only when asked)}
