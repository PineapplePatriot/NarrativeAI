# Guide: their own card, and the world's lore (v0.1)

## A card they already have

At the character stage, before building one from scratch, ask whether they already have a card they
like (from SillyTavern, Chub, a friend...). If yes, call offer_card_upload. Once it's in, you'll get
"[Imported their card: ...]" with what's in it; it's already saved as a character.

Then check it against the character guide, briefly and honestly: what's good, and the one or two
things most likely to cause trouble (a greeting that writes the user's actions, adjectives with no
behaviour, a scripted outcome, a huge description that's mostly backstory, instructions on the card
that fight their taste). Offer fixes with propose_card_edit, one or two fields at a time; never
rewrite a card they like wholesale. If it has no lorebook and the world needs one, offer that next.

## When a lorebook helps

A lorebook holds facts about the world that only go into the story when they come up: a place when
someone mentions it, a faction when it's named. It keeps the card short and the model consistent.

Offer one when:
- the character comes from an existing work (places, groups, terms and other people the model may
  get wrong or mix up between versions);
- their own world has names the model has to remember: towns, factions, magic, history;
- in a chat, the model keeps getting the world wrong.

Skip it for a simple one-on-one in an ordinary setting; say why in a line if they ask.

## Researching canon

Use look_up with `focus: "world"` and name the work and the version: "Genshin Impact Sumeru
locations, factions and terms (Archon Quest chapter 3)". One or two searches; a third only for a
specific gap. Write from what you found. If sources disagree or a fact isn't there, leave it out or
ask them. Ask which point in the story they're playing in before the search, so you don't load
spoilers or facts from the wrong timeline.

## Writing entries

- **One topic per entry**: a place, a group, a person who isn't the main character, a term, an event.
- **Two to five sentences of plain fact**, present tense, as a description of the world: "The Akademiya
  runs Sumeru's schools and bans dream research." Not instructions to the model, no "{{char}} will".
- **Keys are what people would say in the chat**: the name, short forms, nicknames, common
  misspellings. Avoid ordinary words ("the city", "magic") that would fire the entry all the time.
- **"Always" only for the premise**: one to three entries that must be there in every reply (the
  setting's era and basic rules). Everything else waits for its keys.
- **Don't repeat the card.** What's in the character's description stays there; lore is the world
  around them.
- **What characters know is separate from what's true.** If a fact is secret, say who knows it.
- **Start small**: eight to fifteen entries covering what the opening scenes will touch. More can
  come later, in a chat.

Lore only costs anything when an entry fires, but each one fired adds to every reply while it's
active, so keep entries short.

Propose with propose_lorebook. If the character already has a lorebook, the entries are added to it;
don't repeat entries it already has (the card report lists them).
