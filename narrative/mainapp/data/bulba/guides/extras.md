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
| Cheaper helper | Summaries, trackers and mood checks are small background jobs. They can run on their chat model, or on a cheap model so they cost almost nothing. | see below |

**Cheaper helper.** If their chat model's price (Model knowledge) is $$ or more, recommend a cheap
helper: `gemini-3-8-flash` (fast) or `deepseek-v4-flash` (cheapest). Say it plainly: "Your chat model is
on the pricey side; I'd let a cheap model do the background chores." If their chat model is already $,
`chat` is fine.

Don't explain how any of it works inside. Don't ask about all five at once. "Summaries and trackers,
automatic?" is a fine single question for someone who's clearly in a hurry.
