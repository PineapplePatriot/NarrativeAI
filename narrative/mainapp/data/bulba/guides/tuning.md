# Guide: fine-tuning (v0.1)

Settings beyond the preset's words. Read them first (read_settings), change one thing at a time, and
say in a line what it will feel like. Every change is a proposal with Apply and Undo.

## Model settings (propose_samplers)

Instructions come first; settings fix what words can't:
- **Replies cut off mid-sentence:** the reply length limit (max_tokens) is too low. Raise it (2,000
  to 4,000 is normal; thinking models need room for their thoughts too).
- **"Too long" after the length rule didn't help:** a lower max_tokens is a hard stop, so it can cut a
  reply off; prefer fixing the wording and the greeting first, then lower it with room to spare.
- **Rambling, odd words, losing the thread:** temperature down a little (0.1 to 0.2 at a time), or
  min_p 0.05 on open models. **Flat and predictable:** temperature up a little.
- **Repeats phrases:** frequency or presence penalty 0.1 to 0.3 (where the model uses them), after
  checking the preset isn't asking for the repetition.
- **Thinking models:** reasoning_effort decides how much they think before replying: lower is faster
  and cheaper, higher helps plots with many threads. On the newest Claude models it replaces
  temperature.
Never touch a setting read_settings marks "fixed" or "unused" for this model: it isn't sent. Leave
seed and stop sequences alone unless they ask.

## Trackers (propose_trackers)

Match the story, not everything at once; each tracker adds a little to every reply's cost.
- Slice of life, romance: World, Present characters, Relationships; Milestones and Scrapbook come
  with the story extras.
- Mystery, intrigue, court drama: Plot threads, Secrets, Favours & debts, Off-screen.
- Adventure, RPG: Quests, Stats, Conditions, Inventory (the dice-and-inventory extra keeps the last two
  itself), Reputation.
- Long chats: Memories keeps small details (a promise, a clue) that a summary drops.
- **Custom tracker** for what's particular to this story: a meter for Trust or Sanity, a list of
  Experiments, a text field for the Current disguise. Labels are short; the hint says what to note.
Turn off what they find noisy.

## Alternate greetings (propose_greetings)

Other first messages a new chat can swipe to: a different place, time or mood to start in. Two or
three that differ in situation, each following the greeting rules in the character guide. Give the
full list, keeping the ones they like word for word.

## The card's own text rules (propose_card_rules)

Imported cards sometimes bring regex scripts (status bars, hiding tags, formatting). If one makes
replies look broken or duplicates something the app does (trackers, coloured speech), switch it off;
don't delete it.

## Lorebook settings (propose_lore_settings)

- Lore entries not coming up when a name was mentioned a few messages ago: scan_depth up (4 to 8).
- Too much lore at once, replies drowning in facts: token_budget down; too little: up.
- Entries that mention each other (a city and its ruler): recursive_scan on.

## Mood pictures (offer_mood_pictures)

Only when they have a neutral picture and want the other moods made. It spends money on their key (a
few cents a picture), so say that first and let them press the button. Never offer it again in the same
conversation if they said no.
