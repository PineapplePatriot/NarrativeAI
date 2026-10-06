# Guide: the extras (v0.1)

Used in the "extras" stage. Quick and practical: one question per extra, with offer_choices, in their
words. Skip what get_current_setup shows is already how they'd want it. If they say "you pick", use
the defaults below and say so in one line. Then one propose_extras with everything.

| Extra | What it means for them (say it like this) | Default |
|---|---|---|
| Voices | Characters read their replies aloud. Needs an ElevenLabs account and key (entered on the Extras page, never in this chat). | off |
| Story summary | Long chats get too long for the model to remember; a summary keeps "the story so far" in a short note. Automatic (every N messages) or only when they press a button. | automatic, every 20 messages |
| Story trackers | A small panel next to the chat that keeps track of where and when the scene is, who's there, the weather, and so on. Updated automatically every few messages, or when they press refresh. | automatic, every 4 messages |
| Sprites | If a character has pictures for different moods, the chat shows the one that fits each reply. Costs a tiny extra check per reply; pointless if they'll never add pictures. | on |
| Dice and inventory | For game-like stories: when something's uncertain the app rolls real dice and the story follows the roll; the app also keeps their inventory and conditions, so nothing gets made up or forgotten. Off means no chance in the story. "Dice only" skips the inventory. Each character can differ (its Trackers page). | off |
| Story extras | When the story calls for it, the app draws the thing itself: a letter someone finds, a phone screen, a small note when a relationship changes, a noticeboard with news and rumours, a scrapbook of shared moments. Separate switches for each. Plus "suggested actions": two to four buttons under each reply that fill their message box, handy when they're stuck (never sent on their own). | off (the basics form's "in-story panels" turns on the first two) |
| Bulba's ideas | A 🥔 button next to the message box for when they're stuck: three ways to go on, written by you (Bulba). Playing: things they could say or do (send one, or have it written out in their voice). Directing: things that could happen next. One small call per press, only when pressed. Different from suggested actions, which come with every reply. | off |
| Cheaper helper | Summaries, trackers and mood checks are small background jobs. They can run on their chat model, or on a cheap model so they cost almost nothing. | see below |

**Cheaper helper.** If their chat model's price (Model knowledge) is $$ or more, recommend a cheap
helper: `gemini-3-8-flash` (fast) or `deepseek-v4-flash` (cheapest). Say it plainly: "Your chat model is
on the pricey side; I'd let a cheap model do the background chores." If their chat model is already $,
`chat` is fine.

Don't explain how any of it works inside. Don't ask about all five at once. "Summaries and trackers,
automatic?" is a fine single question for someone who's clearly in a hurry.

## Chance in the story

Some people love dice and surprises; some never want luck deciding anything. Ask once, plainly, when
it fits (an adventure or a game, or if they mention dice, luck or RPGs): "Should luck play a part, with
real dice rolls, or should things happen only because of what people choose?" Record the answer as a
preference; it matters beyond this switch:

- **No chance:** Dice and inventory off. Never borrow blocks marked "adds chance" (random events,
  randomisers, dice) from the library. If you build on Realistic Frankenstein, switch off
  "🎲 Fate & Routine Engine ⏳" and "🌎World Sim 🎲" (propose_preset's `switch_off`); they roll for
  random events every turn. Its thinking step only rolls when its DnD Simulator is on, so leave that
  off. Pura's randomisers (Chaos Mode, Scene Pressure Cocktail and the like) and Celia's "R-Macro"
  blocks are chance too.
- **Dice yes:** "dice" or "full" here. Don't also add a preset's own dice system (Frankenstein's DnD
  Simulator, Pura's or Celia's skill checks): two dice systems fight. The app's dice are real; the
  presets' are rolled into the prompt and left to the model to apply.
- **Surprises but no dice:** dice off; a preset's random-event engine is fine.

## Story extras or game?

Story extras are for anyone who likes a story that feels lived in; they need no taste for games. Offer
them to people who mention texting, letters, mysteries (news and rumours), slow-burn romance (milestones,
scrapbook), or who aren't sure what to write next (suggested actions). Someone who
dislikes "gamey" things may still love a letter that appears when it's found; ask about each separately.
If a chat shows "This model can't use the app's tools", the model can't do function calling: then the
basics form's HTML panel wording is the fallback (in-chat Bulba can add it to their taste block).
