# Plan for the next chapter (15 November 2026)

Everything still open, in the order we'd build it. Anya's answers (15 November, second round) are under
**Decided** in each phase. Research behind phases B and C: `docs/research/memory-cards-research-2026-11-15.md`.
`docs/ROADMAP.md` keeps the older list; this file is the working plan.

## Done since 11 November (for context)

Tomato chapter (leaderboard, gallery, Sauce-o-Matic, garden, radio and sounds); replies and Write my message
survive leaving the page; MiMo's copies of their message cut out; director's notes always last and first in
priority; Gemini block message in plain words; tracker looks and Bulba's designed-tracker looks; story colours
fixed (fallback colour, cast from the start, reminder); typed `[[extra: …]]` markers removed; card check
(appearance, no stock labels) and "A compact card done well" in Bulba's guide.

## Bugs from 15 November (done first)

- **Try again on every red error** (a busy or rate-limited provider): in a chat and with Bulba, even when the error
  came after a proposal or an Apply.
- **Menu**: Guide moved up with the plain entries; the emoji ones (Bulba, Notebook, Pit, Garden) together below.
- **Music on every page**: the Pit radio or a chat's music keeps playing on the other pages (▶ 🎶 in the top bar);
  a chat with its own music plays that; the Pit picks a radio track back up.
- **Question: can Bulba change connections?** Not yet: Bulba knows the chat model but can't switch it, pick another
  connection or make one. Proposed below (A4).

## Phase A: small, grounded (no blockers) — done 15 November (A4 waits for a yes)

1. **Every story-writing helper follows their writing direction.** Write my message already uses the preset and the
   polish. Redo, 🥔 Word it for me, ✨ Be creative and the ideas button get the writing-quality baseline and the
   habits they approved, wherever they write story text.
2. **Utility prompts**: in-chat Bulba already edits all of them (summaries, Write for me, director wording,
   ideas); check setup Bulba can too. A user-made extra background prompt: parked (no need seen yet).
3. **Gemini blocks** (that user is on OpenRouter): no app-side difference found; the source-teen check remains the
   likely cause. Optional: compare their setup with Anya's.
4. **Bulba switches models and connections** (proposed): in-chat and setup Bulba can show the connections, switch the
   chat model (on the current connection or another), and make a new connection from an existing one's key. Every
   change is a proposal card they apply; Bulba never sees or asks for a key.

## Phase B: structured cards and personas (the foundation) — built 15 November

**B1. Sections instead of one text box.** A card is stored as sections; the description text the model reads is
composed from them, with headings, so SillyTavern import/export and every prompt path keep working.
- Sections (each can be switched off, with its token cost shown): **Identity · Appearance · Personality in action
  · Temperament** (how fast they warm up, what hurts them, where their attitude to {{user}} starts) **· Goals and
  conflicts · Voice** (with a sample line) **· Background** (only what drives the present) **· Relationships**
  (with {{user}} and others) **· Knowledge and secrets ·** custom sections.
- **Structure it**: an existing card (or an import) is sorted into sections, by its headings first, by Bulba where
  it has none; nothing is lost (unsorted text stays in a "More" section).
- **Fill empty** (Bulba drafts the blanks) and **Appearance from the picture** (from the neutral sprite).

**B2. As many characters as they ask for in one card.** Each character has its own sections; one shared part holds
what they have in common (setting, how they relate to each other). The chat still shows two pictures: the two
speaking (the current rule: two only when the card has several characters, else one, or one plus their own).

**B3. Card types.** *Character* (one) · *Ensemble* (several, B2) · **Simulation**: a setting rather than a person.
Sections: World and rules, Places, Factions, Tone, Starting situation, Recurring people (optional), and **how new
people are made** (what kinds appear, how they're introduced, which come back). New people met in play are kept
by the story memory's people register (C4), so they stay consistent; {{user}} is never written for.

**B4. Personas** get the same sections (lighter) plus a few quick questions that write them.

**B5. Bulba writes into sections.** The card check works per section (appearance present, no stock labels, behaviour
not adjectives); the word budget they chose is spread over the sections by the priority in "A compact card done
well"; ensembles and simulations get their own guide sections.

**Decided:**
- Our own take, not a copy: our section names and wording, our composition, our editor.
- **Temperament works together with relationship progression** (C5): it sets where each relationship starts, how
  fast it moves, and which route it leans to.
- Everything editable. Old cards and SillyTavern uploads get an **Upgrade this card** button (Structure it).
- **Describe from a picture**: Bulba writes a character from an image (appearance first), and offers it during
  onboarding.
- Simulation's cast is visible and editable (folded).

## Phase C: story memory, on by default — built 15 November

**C1. Milestones** (not "chapters"): one per scene, written after it on the background model.
- A scene ends: every N messages, or when the place or time changes (World tracker, story clock), or when they mark
  it (✂ on a message). A message range per milestone, like MemoryBooks.
- Each milestone: a title, **what happened, written so a model that never saw the chat understands it**, who was
  there, where and when, turning points quoted nearly word for word with how each person took them, keywords.
- **The prompt's rules** (the heart of it):
  1. Introduce every person, place and thing on first mention with who or what they are: not "they meet Ivan" but
     "they meet Ivan, Dottore's new guard on the third sublevel".
  2. Keep small details the story may return to: names, numbers, promises, objects handed over, injuries,
     deadlines, lies, things said that someone will remember.
  3. Who did each thing, who said it, who learned or revealed it, who decided, who believed or misunderstood.
  4. Plain past tense, no interpretation, no "the tension rises".
  5. Short where little happened; nothing invented.
- **A cold-reader check** while we tune the prompt: a fresh model gets only the milestones and answers questions
  about the chat; a test set of chats with known answers ("who is Ivan?", "what did she promise?").
- Edited messages, swipes and deleted messages: the milestone covering them is marked stale, redone on request
  (or automatically). Regenerating never overwrites without them seeing it.

**C2. Arcs.** Once there are many milestones, older ones roll into an arc (a few lines each), the milestones stay
saved and searchable; the prompt carries arcs + the latest milestones, newest in full.

**C3. Facts and who knows them.** Each milestone also yields facts: the fact, who knows it, who believes something
else (and what), who it's hidden from, and where it came from. A lie told in front of others is a belief for those
who heard it; group or faction knowledge from card tags. The prompt says, for the characters present, what each
knows; the narrator gets the truth plus who doesn't know it.

**C4. People and places register.** Every named person, place and important thing, with a one-line identity,
kept up to date from the milestones; the same identity everywhere (memory, trackers, Bulba). Simulation cards
draw their recurring people from here.

**C5. Relationship progression.** One record per ordered pair (how A sees B; B's view is its own): a named stage
on a **route**: the basic one (stranger → acquaintance → friend → close), romance, and others such as **enemies /
rivals** (the most important one), mentor and student, and custom routes from the card; a pair can change route,
two or three dimensions (trust, warmth, tension), and a short history of what changed it. It moves only with kept
scenes, at most a step per milestone (the story systems' rules), from the card's Temperament starting point. The
stage's note steers how they behave ("guarded, tests promises", not "is in love").

**C6. In the prompt.** A "Story so far" block (arcs, then milestones), "Who knows what" for the people present,
"Where things stand" (relationships among the people present), each with a token budget, placed so the start
of the prompt stays cacheable (it changes only when a milestone is added).

**C7. Knowledge guard.** Bulba Watch's existing read also checks a reply against the facts: someone acting on
something they couldn't know raises a note (and can be polished).

**C8. Where it lives in the app.** The Summary panel gets a **Milestones** tab next to the current summary (which
stays as it is, with its own button). Memory is on by default for new chats; old chats get "Build milestones for
this chat" (catch-up in chunks). Every milestone, fact and relationship is readable and editable; "What the AI
saw" shows them; Bulba can read and fix them.

**C9. Cost.** About one small call per scene on the background model (milestone + facts + register +
relationships in one structured answer); shown on the spending line.

**Decided:**
- **Two summary modes** on the Summary panel: **Manual** (what we have: summaries of a few messages each, or one
  general summary; it must add to what's there, never replace it) and **Story memory** (milestones, knowledge,
  relationships), switched by its own button.
- Trackers stay as they are: simple pictures for the user, separate from memory.
- A milestone every **4 messages** by default (and when the place or time changes); they set their own number in
  onboarding or by asking in-chat Bulba.
- Routes as in C5.

## Phase D: custom chat looks, made with Bulba — built 16 November

Inspired by Molfar.Vertep's per-chat looks, without letting an AI rewrite the app: Bulba fills a **theme recipe**
(colours, a font from an approved list, bubble shapes, text effects, a light effect, the speech palette) per chat
or per character; preview, apply, undo; shareable as a file. No raw code, so it can't break the page.

Built: a look is a recipe Bulba fills from their words or an inspiration picture (colours, 26 approved fonts,
bold, bubble shape/outline/shadow, name tags, picture frames, background, texture, a light effect, an optional
sound); every value checked, turned into the chat page's styles by the app (mainapp/chat_looks.py). It's the
character's chat style "✨ <name>", switchable per chat. Also from 16 November: personas from seven core
elements (with a parts editor on the profile page), Bulba switching models and connections (A4), the
Characters page cards in each character's colour, and the quick view of the card in a chat.

## Phase E: Tomato Pit and garden — banners built 16 November

Featured **banners** on the Sauce-o-Matic (a rate-up legendary for a week, with its own look and countdown), new
prizes; garden weather and seasons, rare plant mutations, visiting critters, small orders from the gardeners.

Built: banners over the Sauce-o-Matic (tabs). 🏮 Lantern Night (September to November): Lantern tomato and Mr. Death
(gardener: every third harvest +3 compost) as featured legendaries, Monstrous flower seeds, a will-o'-wisp cursor
trail and a corner lantern companion as featured rares; 50% rate-up with a guarantee after a miss, its own pity,
Bulba's Promise picks the featured legendary. Everything else is the standard banner.

Decided 17 November: each seasonal banner lasts one month (Lantern Night is now November only).
Built 17 November: ❄️ **First Snow** (December): the Snow globe tomato (the first skin drawn from a picture,
static/img/tomato/snow_globe.png, also the banner's art) and Babbo Natale (gardener: once a day a present of seeds
in the shed) as featured legendaries; the Snowman (garden decoration), a snowflake cursor trail and a corner snow
globe (tap it: it snows over the page) as featured rares.
Next in Phase E: **orders** (they pay tomatoes) and **mutations** (rare ones give spins), then maybe the house
quest (below).

## Next: story systems with story memory (ideas, 18 November, to choose from)

1. **One trust, not two.** A slow meter can be tied to a relationship in story memory (Rose → Sam, trust): the
   meter is then a view of it, moved by the same rules (a step per scene at most, the card's temperament pace).
2. **Gates: what the story can't rush.** "Not past *rival* before 4 scenes", "not *together* before she knows
   the secret". The relationship (or a meter) stops at the gate until it opens; the model is told it can't cross
   yet.
3. **Knowledge triggers.** An event that fires when a fact reaches someone ("when Rose learns the pass is forged,
   she confronts Sam") or when a secret has been kept too long ("someone starts asking questions").
4. **Scene clocks.** Countdowns in scenes instead of minutes ("3 scenes until the ship leaves"), ticked when a
   milestone closes; shown in the tracker strip.
5. **Promises come due.** A promise memory recorded gets a due time; when it's overdue, an event nudges the story.
6. **Familiar faces.** A random table that draws from memory's people ("someone you haven't seen in a while"), so
   people come back consistent.
7. **In the chat:** a small chapter card when a scene closes ("Scene 5: The third sublevel") and a banner when a
   relationship changes stage ("Dottore → Sam: wary → rival"), with an Undo for the user.

## Phase E ideas: the garden (18 November, to choose from)

1. **Orders from the crew:** each gardener at work posts small orders ("3 carrots by Sunday"); rewards: compost,
   spins, decorations only orders give. Makes picking the three meaningful.
2. **Weather and seasons:** the garden's season follows the real one, the weather changes daily (rain waters,
   sun speeds blooms, frost slows); seasonal crops grow faster in their season.
3. **Mutations:** a small chance on harvest of a rare variant (golden tomato: a spin; giant pumpkin: triple
   compost; a glowing monstrous flower), collected in an almanac; their seeds can be replanted.
4. **Critters:** decorations bring visitors (pond: frogs; lantern: night moths; scarecrow keeps crows off the
   sprouts); tap one for a small bonus.
5. **Crew pairs:** two gardeners who work well together get a small extra (Basil + Mr. Death: the night shift).
6. **A bigger plot** after enough harvests.
7. ~~The winter banner~~ built: First Snow (December).
8. **A house by the garden** (musing, 17 November): a quest line to build a cottage in stages (foundation, walls,
   roof, chimney, porch), each paid in crops and order tomatoes, each unlocking something (a bigger plot, shed
   space, a kitchen that turns crops into dishes, a mailbox where orders arrive). Mechanics only, our own design.
   Undecided; after orders and mutations.

## Phase F: messenger mode

A separate page imitating Telegram/Discord: casual one-on-one chats with the characters, voice messages
(ElevenLabs), the occasional picture (Nano Banana); shares the character and the story memory. Group chats
(several separate characters) come with it, if wanted.

## Later / parked

- The guided tours in more languages.
- Editable in-story attachments (a phone handed over, notes the character writes in), building on designed objects.
- Group chats of separate characters (parked: B2 covers several characters in one card).
- User-made background prompts (parked).

## What was built on 15 November, and what's still open

- **B**: sections, three kinds of card, temperament with routes, Upgrade this card (headings first, Bulba for the
  rest, nothing lost), Fill empty, Appearance from the picture, back to one box; Bulba writes and edits cards as
  sections and offers to start from a picture; personas from five quick questions (as sections in the text; the
  profile page still has one box for them).
- **C**: milestones per scene (updated every 4 messages, or their own number), arcs, facts with who knows them,
  who is who, relationships per pair with routes and stages that start from the card's temperament and move a
  step at a time; the Summary panel's Story memory tab (switch, edit everything, redo a milestone, build memory
  for an older chat); it also runs when they've left the page; Bulba Watch and in-chat Bulba see it; the
  `memory_check` command for the cold-reader check.
- Still open from B and C: a sectioned persona editor on the profile page; relationships for a simulation's new
  people shown on the card page; a cold-reader test set from real chats (needs Anya's chats or permission to use
  one); tuning the milestone prompt on real chats.

## Suggested order

A (a few days) → B1–B5 → C1–C9 (the big one; the prompt gets tuned with the cold-reader tests before it's the
default) → D → E → F. Each phase ends with a push and a list of what to check live.
