# Guide: writing instructions (v0.1)

Used whenever you write or change text the chat model will read: the taste section, a rewrite, a new
block, a card. The short version: **borrow tested wording first, write your own last, and write it
plainly.**

## Borrow before you write

Community presets (Realistic Frankenstein, Pura's Director, Celia) were tuned over hundreds of
chats; a block from them beats anything you'd improvise. So, in this order:

1. **What's already in their preset.** Switch a block on or off, or change a line in it. In a
   community preset most fixes already exist as a toggle that's off.
2. **A tested block from the library** (find_practice, read_practice), added word for word with
   `borrow` (setup) or `from_library` (in a chat). Don't paraphrase it or "tidy it up": its odd
   wording is often the part that works. Tell them where it's from in a few words ("the anti-echo
   block from Realistic Frankenstein").
   - Read it first. If its author's note says it pairs with another block ("keep ON with", "works in
     tandem with", "pair with"), bring that one too or don't use it.
   - Skip blocks meant for a different model ("Gemini", "GLM Edition") unless it's their model, and
     blocks that only work with Realistic Frankenstein's thinking steps (they mention the scratchpad,
     a CoT or `{{getvar}}` templates) unless that's their preset.
   - Mind the size: a 20,000-character engine makes every reply cost more. Say so if you suggest one.
   - Some blocks are adult content, jailbreaks or prefills (NSFW, Gooner, Dead Dove, "JB", "Prefill").
     Only when they ask for that content or that model trick, never as a quality fix.
   - Blocks with `{{random::...}}` or `{{roll...}}` put chance into the story. Check their taste for
     randomness first (extras guide).
3. **The research cookbook's wording** (library entries starting "Cookbook:"). It's untested, so it comes
   after the presets. Each problem has a story wording and a rule wording: pick one, never both.
   Story wording suits story-first setups; rule wording suits game setups, or a model that ignored
   the story version. Fill in any [bracketed] part yourself.
4. **The starter's own wording**, when what they want is close to a line it already has.
5. **Your own text**, only when nothing above covers it. Match the style of the blocks around it, and
   keep it as short as it can be while staying concrete.

## No AI-speak

The model copies the register of its instructions. Instructions that read like a chatbot get replies
that read like one. When you write:

- **Say what happens, not what it should feel like.** Not "create an immersive, emotionally rich
  experience" but "let one physical detail of the room carry the mood".
- **None of these:** "ensure", "it is crucial/essential", "delve", "tapestry", "nuanced", "vibrant",
  "dynamic", "rich", "immersive", "authentic", "seamless", "elevate", "foster", "a testament to",
  "strive to", "make sure to", "remember to", "always strive". Also no stacked adjectives ("vivid,
  evocative, layered prose"), no "Not only X but Y", no closing summaries of the rules you just gave.
- **No shouting.** One "never" where it matters works better than CAPITALS, "MUST", "CRITICAL" and
  "IMPORTANT!!!" everywhere. Emphasis that's everywhere stops meaning anything.
- **No praise or pep talk to the model** ("You are a brilliant storyteller"). It changes nothing but
  the tone.
- **Examples beat adjectives.** A bad/good pair like the anti-echo block's ("Your name is, Dan?"
  versus "Nice to meet you. My name is Jess.") teaches more than a paragraph of description.
- Read it back as a person who writes for a living would. If a line could sit in any preset for any
  story, it's filler; cut it or make it specific.

## "Don't" rules that work

A "don't" is fine when it targets a habit they actually saw. Give it a scope, and either an
alternative or permission to leave the beat out: "Don't use a tightened jaw as automatic emotional
punctuation; leave the beat out when it adds nothing." Don't name a replacement to use every time
(clenched hands in every reply is the same problem). Banned words come back as synonyms, so name the
habit, not the word. No threats, no piles of "always" and "never".

## What text can and can't do

- **Text rules (regex) change formatting, not meaning.** Use them for a fixed marker the model is told
  to write (hide a panel, colour a tag). Never for therapist talk, positivity or metaphors: swapping
  words after the fact can't make the character choose differently.
- **A formula in a prompt is a figure of speech.** "trust = respect + history" only means something if
  the app calculates it. Don't tell them something is tracked unless it really is (the story trackers
  on the Extras page are; numbers the model keeps in its replies are its best guess).
- **Hidden isn't secret.** A folded panel or an HTML comment is still sent to the model and saved in
  the chat. Don't use it to keep secrets from a character.

## Story first, unless it's a game

By default the narrative leads: instructions describe how scenes, characters and prose behave, in
plain sentences, and the starters' prose rules stay in charge.

Some requests change that: an RPG with stats and dice, a game with rules and scores, a phone or chat
interface, a status panel every turn, a very specific layout. Then **the format is the point**, and
the narrative steps back:

- **Formulaic is right here.** Tags, fixed labels, numbered steps, if/then triggers and a literal
  template of the output, the way Realistic Frankenstein's DnD Simulator or Pop in Graphics are
  written. The model follows a template far better than a description of one.
- **Give one exact example of the output** (with placeholders in brackets) and say where it goes
  (start or end of the reply, folded or not).
- **Say what's tracked and how it changes**: what counts, when it goes up or down, the limits, and
  that it carries over between replies.
- **Keep numbers out of the prose** unless they ask otherwise: stats live in the panel, the story
  describes what happens.
- **Look for conflicts with the prose rules** (a length limit that leaves no room for the panel, "no
  lists", "no meta"). Loosen or switch those off as part of the same proposal, and say so.
- Dialogue and the format carry the scene: fewer instructions about atmosphere and interiority.
- The core rules still hold: never writing for them, limited knowledge, out-of-character handling.

Check the library first here too: dice, inventories, relationship meters, internal states, a GM's
notebook, in-story graphics, a social feed and coloured dialogue all exist already. If the panel
shows HTML, the app displays it; plain text works everywhere.

### Story extras without a game

Letters, phone screens, a rumour board, relationship milestones, a scrapbook of shared moments: these
make a story feel alive without stats (ideas in `docs/research/preset-second-pass-interactive.md`).

- **Only when the scene calls for it.** A letter appears because someone finds one, not every reply.
  Say so in the instruction: "Do not invent a document just to show one."
- **One feature at a time**, and ask before adding a second.
- **The panel holds the object; the narration stays outside it.**
- **What characters know still holds**: a text message is known to whoever saw it, not everyone.
- **Milestones over scores** for people who dislike numbers: "Trust: growing cautiously · after she
  fixed the roof" instead of "Trust 6/10".
- Folding panels (`<details><summary>`) work in the chat.

Show a sample before they apply. Formats break in ways a description can't show.
