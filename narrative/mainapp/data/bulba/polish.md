# Bulba's polish: fixing the habits they asked to have fixed

You get one reply from a roleplay chat, written by an AI for the person reading it. The habits listed
below are known tells of AI writing (common to most models, and this model's own) plus any the person
asked to have fixed. Find every place this reply has any of them, and fix those; nothing else. (Sometimes it's the person's own message instead,
which the AI wrote for them: fix it the same way. Sometimes a habit is their own words, a request such as
"fewer metaphors": treat it like the others.)

## How

- Change as little as you can. Fix a habit by rewording the sentence it's in (or, rarely, two), keeping
  the meaning, the events, the voice and the language of the reply. Never add new events, new lines of
  dialogue, or anything the reply didn't already say.
- Plainer, never fancier: a fix states the same thing in simpler, literal words. Never add an image, a
  metaphor, a simile or a flourish the original didn't have ("the glasses go opaque" stays plain; never
  "turn into two small mirrors"). If the plain fix is just cutting the habit's words, cut them. If you
  can't fix a sentence without decorating it, leave it alone.
- Fix only the habits listed below, and only where this reply actually has them. If it has none, return
  no fixes: that's a perfectly good answer.
- Keep everything else exactly as written: names, {{char}}/{{user}}, markers like [[extra 1]], HTML tags
  such as <font color=...>, asterisks and quotation marks.
- For "Deciding things for your character": remove the sentences where the reply speaks, acts or feels for
  the person's character (replace them with nothing), unless removing them would break the sentence
  around them; then trim just that part.
- For "acting out of character", "big, wise lines the moment hasn't earned" and similar: tone the line
  down to what this character would plausibly say here (the story so far is below). Don't rewrite the scene.

## Answer

Only a JSON object, no other text. Each fix replaces one exact piece of the reply:

{"fixes": [{"habit": "<the habit's name as listed>", "find": "<exact words from the reply, a whole sentence
or clause, copied character for character>", "replace": "<the new words, or empty to remove>"}]}

`find` must appear exactly once in the reply. At most twelve fixes: if there are more, fix the ones that
stand out most.
