# Guide: writing their preset (v0.1)

Used in the "taste" and "preset" stages. A preset is the set of instructions sent to their chat model
with every reply. You never write one from scratch: you start from this model's starter (see Model
knowledge), which already handles the basics, and adapt it to this person.

## What the starters already do

Every starter already tells the model to: stay in character, never write the user's words or
thoughts, keep characters' knowledge limited to what they saw or were told, avoid recaps, answer
out-of-character notes out of character, and keep a sensible reply length. The model-specific
starters also cover that model's known habits (see "Habits to check for"). **Don't repeat any of
this** in their taste section; repeating instructions makes models overdo them.

## Picking the starter

- **Back-and-forth**: they want short exchanges and their turn to come quickly.
- **Rich scene**: they want atmosphere, interiority, a scene that moves.
- **Director seat**: they want to steer several characters or the plot itself, and read fuller scenes.
Pick by how they want to *play*, not by genre. Any starter works for any genre.

## The "your taste" section

This is where their preferences go (propose_preset's `taste`). Rules:

1. **Only confirmed, general preferences**, plus boundaries. Character-specific taste ("he stays
   guarded") belongs in that character's description, not the preset. Scene-specific remarks belong
   nowhere permanent.
2. **Write to the model, in second person, concretely.** Describe the behaviour you want:
   - Weak: "Be more emotional."
   - Better: "Let feelings show through what characters do and avoid saying; they rarely name their
     emotions outright."
   - Weak: "Make it immersive."
   - Better: "Ground each reply in one or two physical details of the place: light, sound, temperature."
3. **Short "don't"s are fine when they target a specific habit they disliked** ("Don't end replies on a
   question unless the character would really ask one"). Don't write long lists of banned words or
   phrases: banning a word often gets you its synonym. If they hate a pattern (therapy talk, recaps,
   purple metaphors), describe the pattern, not the words.
4. **Five to ten lines.** If it's longer, you're probably restating the starter or guessing.
5. **Boundaries last, plainly:** "Keep out: graphic violence against animals." No moralising.
6. **Length goes in `reply_length`** (short, medium, long), not in the text, unless they gave something
   specific ("about two paragraphs").

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

Diagnose before adding rules, in this order:
1. Something in the preset or character that asks for the behaviour (an instruction that conflicts).
2. The character description or greeting pulling the model that way (a long, florid greeting teaches
   long, florid replies).
3. Missing context (summary, lorebook) or a very long chat.
4. Wording of an instruction that's too vague.
5. The model itself (check its known habits).
Change one thing, show a sample, keep the version that worked.

| They say | Look at first |
|---|---|
| "It keeps recapping" | Long greetings that summarise; a vague length rule |
| "Sounds like a therapist" | Instructions asking for emotional depth or explicit feelings |
| "It decides everything for me" | Did it write their actions, resolve the scene, or skip ahead? Different fixes |
| "Nothing happens" | A starter that stays in the moment; ask for character initiative, not randomness |
| "Too long / too short" | reply_length, and the greeting's length |
