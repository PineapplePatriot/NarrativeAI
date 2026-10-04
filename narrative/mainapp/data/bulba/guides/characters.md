# Guide: writing characters and personas (v0.1, draft)

Used in the "persona" and "character" stages. Draft until Anya's card-writing notes arrive; follows the
structure of SillyTavern character cards so cards can be exported and shared later.

## The persona (who they are)

- Ask what they want to be called and, in a sentence or two, who they are in the story. Many people
  want a light persona so they can improvise; that's fine.
- Write it in third person, short (40 to 120 words): name, look in a line, one or two traits that
  matter in scenes, anything characters should know about them. Nothing about how they *feel* about the
  character; that's for them to play.
- If they already have one (get_current_setup), offer to tidy it rather than replace it.

## The character (who they talk to)

Ask who they want, in their own words: an original character, someone from a book or game, or "you
pick". One question at a time: who they are, what they're like, how the two of them know each other
(or don't), and where the story starts. For a known fictional character, you can rely on the model
knowing the canon; write what makes *this* version specific.

### Description (propose_character `description`)

Third person, about 250 to 600 words. Cover, roughly in this order:
1. **One line that captures them** (a quote in their voice works well).
2. **Who they are now**: role, situation, what they want and what's in the way.
3. **Background** that actually matters in scenes. Skip trivia.
4. **Personality as behaviour**: how they act when annoyed, when cornered, when someone is kind to
   them. Contradictions are good ("cold in public, a sweet tooth in private"). Labels like ENTP or
   "tsundere" are fine as shorthand but always add what it looks like.
5. **How they talk**: vocabulary, rhythm, verbal habits, one or two sample lines.
6. **Appearance** in a few concrete lines.
7. **Relationships** to other characters, and to the user only if the user asked for one.

Write `{{user}}` for the user's character and `{{char}}` (or the name) for the character. Don't decide
the user's feelings, history or role unless they told you. Mature details (sexuality, violence) only
when the user brought them up or the canon character clearly needs them; plainly, without moralising.

### Scenario (`scenario`)

Two to four sentences: where and when the story starts, and what's going on. Leave the user's choices
open ("{{user}} has just arrived" rather than "{{user}} has decided to stay").

### Greeting (`greeting`)

The first message teaches the model how replies should look, so match their chosen reply length and
style. It sets the scene, shows the character in action and in their voice, and ends with an obvious
opening for the user without acting for them. Avoid a long summary of the backstory; let it come out
later.

## Pictures

Mention once that they can add pictures for different emotions on the character's page later (Nano
Banana in Gemini makes consistent sprites from one reference). Don't push it.
