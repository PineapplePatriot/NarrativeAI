# Guide: writing their preset (v0.1)

Used in the "taste" and "preset" stages. A preset is the set of instructions sent to their chat model
with every reply. You never write one from scratch: you start from this model's starter (see Model
knowledge), which already handles the basics, and adapt it to this person.

## What the starters already do

All authored ready variants include a separate Writing quality block. It covers recurring physical
filler, vague emotion, dialogue recap, explanatory annotation, rhetorical repetition, forced endings,
character decisions and knowledge. These requirements apply to short, rich and director variants;
length and initiative do not switch them off. The block is editable and remains the user's choice.
Imported community artifacts retain their original rules; inspect those rather than assume coverage.

Read the starter with get_starter before drafting: its writing_quality field contains the actual
baseline. Rewriting Roleplay or Style does not replace that separate block. Do not duplicate its rules
in Your taste. When a user wants a legitimate exception (lyrical narration, strong interiority,
comic banter), keep the exception specific instead of removing all writing safeguards.

## Picking the starter

- **Back-and-forth**: they want short exchanges and their turn to come quickly.
- **Rich scene**: they want atmosphere, interiority, a scene that moves.
- **Director seat**: they want to steer several characters or the plot itself, and read fuller scenes.
Pick by how they want to *play*, not by genre. Any starter works for any genre.

Some models also have a **community preset** (MiMo and Gemini: Realistic Frankenstein). It's a big,
popular preset that holds chaotic models to strict realism, with lots of panels (NPC agendas,
relationships, a GM notebook). Offer it only to people who want that much machinery or ask for it by
name, and say plainly that it makes every reply cost more (it sends about 33,000 tokens of rules). Its
sections aren't the starters' Roleplay and Style, so don't use `rewrite` with it; put their taste in
`taste` as usual.

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
6. **Length goes in `reply_length`** (short, medium, long), not in the text, unless they gave something
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
the answer itself with Pura's tested wording, takes the starter's own "don't write for {{user}}" lines out
when needed, and for directing also switches their chats to the book layout (replies read as chapters,
their messages fold into small markers). Don't write anything about it in `taste`. Someone who answers
"I direct from outside the story" usually wants the **Director seat** starter, which is built for that;
the answer then adds Pura's stricter wording (they're never a character) and the book layout.

## When the starter contradicts them

Sometimes a starter's own text pulls against what they want: they dislike banter but Back-and-forth
says "let the exchange spar"; they want restrained prose but the style says "vivid where it matters".
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
