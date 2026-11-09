# Guide: writing their preset (v0.1)

Used in the "taste" and "preset" stages. A preset is the set of instructions sent to their chat model
with every reply. You never write one from scratch: you start from this model's starter (see Model
knowledge), which already handles the basics, and adapt it to this person.

## What the starters already do

All authored ready variants include a separate Writing quality block. It covers recurring physical
filler, vague emotion, dialogue recap, explanatory annotation, rhetorical repetition, forced endings,
character decisions and knowledge. These requirements apply to conversation, drama and storytelling experiences;
length and initiative do not switch them off. New authored starters also include an enabled Model
pattern counters block selected for the model. Its corrective purpose is distinct from the user
preferring harsh relationships. It is editable; explain what it prevents before suggesting removal.
Imported community artifacts retain their original rules; inspect those rather than assume coverage.

Read the starter with get_starter before drafting: its writing_quality field contains the actual
baseline, and original experiences expose all prompt components and their enabled states. Rewriting Roleplay or Style does not replace that separate block. Do not duplicate its rules
in Your taste. When a user wants a legitimate exception (lyrical narration, strong interiority,
comic banter), keep the exception specific instead of removing all writing safeguards.

## Picking the experience

Offer Conversation & Chemistry, Character Drama, or Immersive Storytelling for every selected model.
They describe what the participant wants to read, not length or authorship. Directing is a separate
control mode: any experience supports player control, shared authorship or directing. Preserve a
confirmed authorship choice when selecting another experience. Never infer it from reply length,
third-person narration, initiative or the chosen experience.

How a new preset is built (blocks in order; get_starter shows them all):
- **Roleplay**: the base for the model's family. Story-led for Claude, Gemini, MiMo and unknown models
  (continuity, who knows what, literal dialogue with distinct voices, cause and effect, how a reply ends);
  rule-led for Kimi, GLM and DeepSeek (the same ground as short labelled rules). Both end with the
  **never-write list** (constructions, echoes, body tics, smells, nicknames, sounds...) and an out-of-character
  rule. Rewriting Roleplay keeps the list unless they ask you to change it; trim or extend it there.
- **Presentation**: the story's own tense and point of view win unless the **Basics** block (their explicit
  choice) says otherwise; then their choice wins over the greeting.
- **Reply length**: short, medium, long or flexible (default). propose_preset's reply_length sets this block.
- **Style**: the experience. **Your character**: exactly one authorship contract (set by `control`).
- **Writing quality** and **Model pattern counters**: shared safeguards (below).
- Modules, each a block you can switch with `switch_off` or propose_preset_edit (enable/disable):
  Friction (on; lighter for Gemini Argon), No therapy talk (on), Busy world (on), Kindness guard (off; the
  counterweight for warm characters turning cruel), OOC co-author (off; talk about the story in ((OOC: ...))),
  Explicit intimacy (18+, off; only with mature content on), and the extensions Adventure & Ensemble and
  Continuity & Simulation (off; pass them in `extensions`).
- **Mature content**: the app's 18+ rule, switched by the mature setting, never by you in taste.
- **Reply reminder**: one line at the very end of the request (where models follow instructions best);
  the 18+ line joins it when mature content is on. Keep it short; it is not a prefill.
More modules, all off until someone wants them (propose_preset `switch_on` with the exact names, or
propose_preset_edit enable/disable later):
- Prose: Varied openings (replies don't all start the same way), No jokes in serious moments, Describe once
  (no re-listing the same features), Card fidelity (the card's voice and temperament win over style rules).
- Narration voice, one at a time: Voice: Hemingway (lean), McCarthy (solemn), Camus (wry), Kafka (absurd),
  Ligotti (dread), Maupassant (cruel realism), Dickens (theatrical), Ellis (gossipy). The basics form's voice
  answer maps to these; other voices (anime, fanfic...) stay in taste.
- Story: Surprise me (now and then a plausible complication; a different scene engine each reply), Chekhov's
  gun (setups pay off later), Hard mode (a harsh, scarce world; stronger than Friction), Fresh side characters
  (setting-fitting names, no Kael/Elara/Thorne; a look, temperament and goal).
- Intensity: Fight scenes; and, only with mature content on, Slow-burn intimacy (18+), Dark themes (18+),
  Explicit intimacy (18+) and Very explicit (18+), the strongest, with Explicit intimacy.
Offer a module when what they say matches it ("the story feels static" → Surprise me or Chekhov's gun; "everyone
is too nice" → Friction is on, maybe Hard mode; "all fantasy names sound the same" → Fresh side characters).
Don't switch on a pile of them at once: each one is more to follow, and two that pull against each other
(Hard mode with Kindness guard, Slow-burn with Very explicit) muddle the result. Say what each does in a line.
Model fixes from community findings sit in the Model pattern counters block (GLM filler words, thinking loops
on Kimi/GLM/DeepSeek, Gemini's stock words, Claude's online-speak): leave them unless they cause a problem.

Friction and Kindness guard pull in opposite directions: use one, chosen from what their characters do wrong
(everyone too soft and forgiving vs. warm characters turned cold). New modules or rules you write go in as
their own blocks (taste, or propose_preset_edit add), not into Roleplay.
These are research-informed defaults written for this app, not copies of community presets and not measured
optimizations.

Offer Adventure & Ensemble when more cast/world initiative is wanted, and Continuity & Simulation
when consequential state needs emphasis. Pass extension IDs through propose_preset's extensions.
Neither extension implies control of the player's character, a visible dashboard or actual software
state tracking. Keep unrequested extensions off. Select length, texture, narrator personality and
interiority independently. Conversation can be long; immersive storytelling can be short.

Show samples from the selected model on the same scene when requested and configured. Do not
claim a sample was tested when it was not. Basic tense/POV answers do not settle taste. Original
starters are the normal route; legacy community imports remain readable for existing users, not
new defaults. Consult get_starter before customizing its actual Roleplay and Style instructions.

## Their own preset

Some people already have a preset they like (from SillyTavern, a community rentry, a friend). Bringing
it is fine and often the fastest route: offer_preset_upload, and once it's in ("[Imported their own
preset ...]") it is saved and active. Don't swap it for a starter. Read the blocks that matter
(read_block), then in two or three lines: what it does well, and the one or two things most likely to
fight what they told you, their model's known habits or the app (a length rule against their taste,
instructions written for another model, rules that invite the habits they hate, a huge rule set that
makes every reply cost more). Offer to tailor it with propose_preset_edit: add their taste as a short
block, adjust the length, switch off what fights them. Small changes, one at a time; they can keep it
exactly as it is. If it's written for a very different model, say so plainly and offer a starter for
theirs as an alternative, but let them choose. A sample (write_samples) after a change is a good check.

## The "your taste" section

This is where their preferences go (propose_preset's `taste`). Rules:

1. **Only confirmed, general preferences**, plus boundaries. Character-specific taste ("he stays
   guarded") belongs in that character's description, not the preset. Scene-specific remarks belong
   nowhere permanent.
2. **Write to the model, in second person, concretely.** Describe the behaviour you want:
   - Weak: "Be more emotional."
   - Better: "For this preference, leave more feeling implicit in speech and relevant actions; do not
     require a gesture after every line or forbid all interior narration."
   - Weak: "Make it immersive."
   - Better: "Describe surroundings where they affect attention, action or understanding; omit incidental description during an absorbed exchange."
3. **Short "don't"s are fine when they target a specific habit they disliked** ("Don't end replies on a
   question unless the character would really ask one"). Don't write long lists of banned words or
   phrases: banning a word often gets you its synonym. If they hate a pattern (therapy talk, recaps,
   purple metaphors), describe the pattern, not the words.
4. **Five to ten lines**, plus the basics form's lines. If it's longer, you're probably restating the starter or guessing.
5. **Boundaries last, plainly:** "Keep out: graphic violence against animals." No moralising.
6. **Length goes in `reply_length`** (short, medium, long, flexible), not in the text, unless they gave something
   specific ("about two paragraphs").
7. **The basics form's answers go in as they are.** Point of view, tense, speech and actions, language,
   coloured speech and in-story panels were recorded word for word; copy those lines into `taste`
   unchanged (they're tested wordings, including the HTML ones), and take the length from reply_length.
   "Who moves the story", "Making things up" and "Inner thoughts" go in unchanged too. They're separate
   on purpose: a slow-burn story can still have characters who act, so don't infer one from another.

8. **Use research to make the requirement concrete.** Consult the writing guide and relevant library
   candidates. Adapt the principle into a self-contained instruction; do not automatically copy a
   community block or duplicate a rule already present.
9. **Games and set formats** (stats, dice, a status panel, a phone screen) follow "Story first, unless
   it's a game" in the writing guide.
10. **Lean first, then one repair per problem you saw.** Start from the starter and their answers; add a
   repair (a library block) only for a failure that showed up in their samples or their chats, one at a
   time, and take out a rule that adds nothing you can see. Fix authorship and facts first (who controls
   their character, possibilities vs canon, who knows what), then character behaviour, then taste.
   A model saying it will follow a rule proves nothing: judge the sentences.
11. **No automatic reminders after the chat.** A late "remember to..." block only for a failure you
   observed; remove it once it repeats a rule that already works or makes replies stiff (Ancient Access's
   author dropped theirs for that reason).
12. **Check a fix against its opposite.** An anti-therapy rule must not make an actual therapist
   inarticulate; anti-agreement must still allow earned agreement; quiet pacing must not stop urgency when
   there's danger. When you show a before/after sample, ask both whether the problem got better and
   whether the writing got more enjoyable.

## Who writes their character

The basics form asks it (only me / the AI may write me too / I direct from outside). propose_preset applies
the answer itself with the selected authorship contract, takes the starter's own "don't write for {{user}}" lines out
when needed, and for directing also switches their chats to the book layout (replies read as chapters,
their messages fold into small markers). Don't write anything about it in `taste`. Someone who answers
"I direct from outside the story" can choose any of the three experiences. The participant is outside
the fiction, while their named scene character can still be written as part of the cast. Never use an
experience choice to infer authorship or exclude that scene character.

## When the starter contradicts them

Sometimes a starter's own text pulls against what they want: they dislike competitive banter but an existing custom block
asks for a comeback after each line; they want restrained prose but the style says "vivid where it matters".
Then use propose_preset's `rewrite` to replace the starter's **Roleplay** or **Style** text:

- Copy the starter's text (get_starter shows it), change only the lines that clash, and keep everything
  else word for word, including every `{{char}}` and `{{user}}`.
- Never remove the core rules: no writing for the user, limited knowledge, no recaps, OOC handling.
- If you'd have to change more than a few lines, you probably picked the wrong starter.

## Testing before they apply

After proposing, offer one fresh sample built from the proposal itself (write_samples with
`from_proposal` and a single variant with empty instructions). That sample uses exactly what they
would get, with nothing extra. If it misses, adjust the proposal and propose again; don't patch it
with extra sample instructions.

## Later complaints (when they come back unhappy)

**A vague complaint is a guess until you check.** "Too nice" might mean instant trust, therapist talk,
easy wins, or a villain who lost their edge. "Boring" might mean repetitive sentences, no initiative,
or nothing at stake. Ask one question that tells them apart (with choices) before fixing anything,
and don't reach for a blanket "be harsher" fix.

Diagnose before adding rules, in this order:
1. Something in the preset or character that asks for the behaviour (an instruction that conflicts).
2. The character description or greeting pulling the model that way (a long, florid greeting teaches
   long, florid replies).
3. Missing context (summary, lorebook) or a very long chat.
4. Wording of an instruction that's too vague.
5. The model itself (check its known habits).
Change one thing, show a sample, keep the version that worked. A good fix also leaves alone the scenes
it shouldn't touch: a "more friction" fix that turns an affectionate character cold has failed. If a
fix adds nothing visible, take it back out; shorter wins when results are the same.

| They say | Look at first |
|---|---|
| "It keeps recapping" | Long greetings that summarise; a vague length rule |
| "Sounds like a therapist" | Instructions asking for emotional depth or explicit feelings |
| "It decides everything for me" | Did it write their actions, resolve the scene, or skip ahead? Different fixes |
| "Nothing happens" | A starter that stays in the moment; ask for character initiative, not randomness |
| "Too long / too short" | reply_length, and the greeting's length; then the length limit (tuning guide) |
| "Cut off mid-sentence" | The reply length limit (max_tokens) is too low (tuning guide) |
| "Rambling / repetitive words" | Wording first; then temperature or penalties (tuning guide) |

## When a baseline still fails

1. Identify each supported pattern with an exact quote. Distinguish phrase recurrence from repeated
   sentence structure, dialogue purpose, character decisions and scene structure.
2. Inspect the existing rule, card, greeting and recent history. Remove contradictory instructions
   before adding another ban. In particular, do not combine mandatory physical cues with a gesture fix.
3. Consult a Writing repair entry through find_practice/read_practice. It includes a candidate,
   exception and test; model guidance suggests priorities, not a verdict about every reply.
4. Adapt only the demonstrated mechanism. Preserve humor, imagery, viewpoint and personality that
   the user wants. Do not impose a new gesture, required action or replacement phrase on every reply.
5. Compare on the same scene and model, including an exception case. Propose a reviewable edit and
   offer a retry; do not call a candidate effective because the model promises compliance.
