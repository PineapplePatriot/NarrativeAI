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
Built 17 November: the **order board** (neighbours post one order a day, at most 3 open, each for 3 days; harvests
count toward them by themselves and still make compost; a filled order pays 100-300 tomatoes toward spins, not the
leaderboard) and **mutations** (1 harvest in 20; most triple the compost, the rare one of each crop is a free spin;
all collected in the garden's almanac). Each mutation gives its seed: planted, it comes out as itself half the time
(a rare one a quarter of the time) with its seed back, otherwise as an ordinary harvest. Next: the house quest (below).

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
8. ~~A house by the garden~~ built 17 November: **the cottage quest** (mainapp/tomato_house.py). Il Dattore (a
   scientist who over-engineers everything) builds it with Pantaleone's money (a banker who reads every receipt),
   a cameo nod in small pixel art. Five stages, each a pinned builder's order (its seeds bought for you; harvests go
   to it first) plus compost, then some hours of building: foundation → mailbox (4 orders), walls → a 6th row,
   roof → rain barrel (+25% watering), chimney and kitchen → dish orders (several crops, paid double), porch (3
   different mutations) → the cottage dresses for the seasons. Under budget (3 days): Pantaleone tips 100 tomatoes.
   A short scene between the two after each stage. Later, maybe: a second building (a mill), house paint colours.

## Phase F: messenger mode (the Screen Hub's TeleChat), in progress

First built elsewhere (feature/digital-screen-telechat), merged 18 November and made to work: uploads and voice
preview crashes fixed, purple, phones (one panel at a time), ↻ Try again with a note, Bulba's setup card for
characters not yet set up for texting (Modern AU or their own world, the user's directions binding, "What's off?"
corrections, new pictures in the texting look), Bulba's answers surviving thinking models, MiMo's leash for
replies, 🥔 Bulba in a side panel per chat (cards for the texting profile, the chat's scenario and events, new
pictures, retries), drawer fixes (save feedback, pictures that fit, a big view of any picture).

### The user's iteration-2 list (18 November), in batches

Done 18 November:
- (1) Voice notes cut at ~2 seconds: `[VOICE: [sighs] ...]` was read up to the first `]` (only "[sighs]" was
  voiced). Tags are now read with nested brackets; photos the same.
- (4) Old pictures after new ones: the new look now replaces the old reference pictures (stickers are still the
  roleplay moods: with the sticker packs, below).
- (5) Bulba's panel and the setup drawer squeezed the chat: one side panel at a time.
- (16) Bulba didn't know the Tomato Pit, Garden or Screen: in its app guide now, and the messenger's Bulba reads it.

Batch A, the chat itself: done 18 November (one by one arrival, typos at speed, leave-on-read per chat, ↻ on any
message or photo, photos seen and real voice notes heard, one check-in per silence, the card preview). Still open
from it: characters texting first while the browser is closed (a scheduled job on Railway + push notifications).

Batch A as planned:
- (11) Try again on any of the characters' new messages (each of a burst of 4), photos included (regenerate one
  picture).
- (7) Texting rhythm: a burst arrives as typing → bubble → pause → typing, not all at once; typos only when they
  text fast (bursts); a per-chat switch "they can leave you on read": up to 5 real minutes, only when it fits (they
  were busy doing something, or for emotional reasons: teasing, angry, petty), decided 18 November.
- (20) The model reads what the user sends: pictures (a vision description) and voice notes (transcribed).
- (22) Check: characters texting first while the user is on another page or away.
- (23) Card preview: tap the name or picture → the texting profile on top, the roleplay card below.

Batch B: done 18 November: chat files (💬 Chats: new chat, branches ⑂ from any message, rename, delete); Bulba's
setup describes the look for the setup, lists what changed from the card and asks about what's central (a mask, a
title); Before you start (memory sharing per chat, leave-on-read, a persona for this chat only); a card with
several people split into characters + a group chat; a group's shared scenario by Bulba once everyone is set up.

Batch B as planned:
- (6) Two strictly separate profiles: Bulba's setup also proposes the look for this setup (a modern Dottore
  without the mask) and asks before changing lore; it says what it changed.
- (7.2) Right away in a new chat: share memory with the roleplay chats (now on by default and hidden: ask), and
  the leave-on-read switch.
- (15) A chat-specific persona, offered at the start.
- (13) Cards with several people: offered a split into separate characters + a group chat.
- (14) Group chats: every member set up (Bulba walks through each), then a shared scenario.
- ~~(2) Custom voice ids~~ checked 18 November: OpenRouter's ElevenLabs models take only the 21 premade voices
  (their `supported_voices`); custom ids need the user's own ElevenLabs key (Extras → Voices). The drawer says so.
  Later, maybe: OpenRouter's voice cloning from a short recording (HeyGen Voice and others), no ElevenLabs account.

Batch C: done 19 November: 🎨 the user makes pictures to send (their persona picture, up to 5 references, make it
again, a caption); one picture at a time (✨ Make this one / ↻ Redo this one for moods; ✨/↻ per messenger
reference slot); 🎨 sticker packs in the texting look (one at a time) and 📥 Telegram packs by link
(TELEGRAM_BOT_TOKEN); the picture model really used (MAI-Image), no-people photos. Uploading moods beyond neutral
worked in tests: waiting for the user's details on what fails live.
Also done 19 November, the user's small list: reactions as replies, failed replies retried, edits noticed, text
files read whole with tables, text with attachments, presence dots, voice check-ins, statuses with pictures in a
story viewer, characters' own statuses.

Batch C as planned:
- (21) The user sends generated pictures: a small window (prompt, up to 5 references, regenerate) for "proof" or
  what's going on in their life; more variety in the characters' photos.
- ~~(3) Image model choice~~ done 18 November: MAI-Image-2.7 and 2.7 Flash take reference pictures
  (text+image → image); a picture model choice in the messenger's profile tab (Nano Banana stays the default);
  image-only models are asked for an image only.
- (9) Main app too: generate or regenerate one emotion (not all at once); uploading beyond neutral is broken.
- (8) Stickers: Telegram/Discord-style packs; generated custom packs (a character's texting look, one style);
  real Telegram packs by link through a bot token in a Railway variable (decided 18 November).

Batch D: done 19 November: the chat's memory (a running summary of what fell out of view, editable, "update it
now") and how many recent messages are read (20/30/60/100); Bulba Watch for texts (free checks on their latest
text, short chats included, with a one-tap rewrite); four ready themes per chat (classic, forest, rose, sepia).
Trackers: not in the messenger (the user checks with a few users).
Later, maybe: sound effects (Lyria ambient beds through OpenRouter; ElevenLabs sound effects with the user's own
key); characters texting while the browser is closed (a scheduled job + push notifications).

Batch D as planned:
- (12) Context window and story memory for messenger chats (the chat page's panel, per chat).
- (10) Bulba Watch in short chats.
- (18) Characters post their own statuses now and then; the user's button posts only theirs.
- (19) A few ready chat themes (no custom ones yet).
- (17) Trackers: not in the messenger (relationship and mood live in memory); the user checks with a few users.

### The user's iteration-3 list (19 November, after onboarding a user), first 5

1. Attachments: check text files are read; the characters' photos should be described from the actual picture
   (not the prompt it was made from), for consistency.
2. Older requests that didn't land: typing speed (single messages too), leaving on read (rarely happens),
   the user's reaction to a message counting as their reply (the character responds), editing earlier messages
   of a burst, a live status dot (typing…), translation of messages.
3. Bulba: suggest the photo description from the scene; suggest replies when the user is stuck; ask about the
   look after modernizing (old references stay otherwise); the setup card and the Bulba panel out of sync (the
   card shows a stale draft); Bulba can't change the chat persona (and points to a pen menu that isn't there);
   Bulba should offer answer options (and help with setup) in the messenger; check elsewhere too.
4. Continuity monitoring (not only slop; slop never seen triggering); tease photos far too explicit; "Botox"
   faces in realistic anime style (expressions too flat).
5. Scene and clothes tracking for pictures on both sides; a modern lorebook for the texting setup.
Backgrounds: the green screen is risky for sprites (contrast); maybe the rembg cut-out tool later.

Done so far (pushed): 1 (photos read by the vision model; txt/md files), 2 (reactions count as a reply, typing
pace, leave-on-read nudge, 🌐 translate, "typing…" in the header and a quiet 90 s refresh).

Added on 19 November (second message):
- Character bursts couldn't be edited or rewritten past the last one: on phones the actions bar covered the next
  message (fixed: a strip at the bottom of the screen). Open question: should rewriting one message of a burst
  touch the ones around it?
- The user couldn't send several messages in a row (fixed: the reply waits a few seconds after the last one).
- Moments: status pictures weren't shown, statuses couldn't be deleted (fixed). Open: should chat photos go to
  Moments, and what happens to them when the chat message is deleted? Moments on a phone (only in the chat list's
  bottom bar; hidden inside a chat).
- Memory after deletion (fixed: a remembered message deleted/edited → the memory is rebuilt).
- Attachments: txt/md + photos/screenshots are enough (no PDF/Word).
- Reminder: the worldbook (lorebook) as a step of the texting setup; scene tracking for pictures (place and
  surroundings + clothes, both sides).

Done on 20 November: Gallery; photo mood (daily / sweet / playful / flirty / bold) and livelier faces (expression
references from mood pictures); picture styles with anime realism as the default; Bulba suggestions (reply, both
picture windows, status, bio, plans → reminders, art style from their picture); real reminders texted when due;
a +1 in photos (on by default in groups); the continuity check (with Bulba Watch); the texting worldbook (a setup
step, adapted from the roleplay lorebook); "📍 Right now" scene tracking used by every photo and the replies.
Visual Novel moments: parked (another branch).

### 21 November: last batches before the hand-off (all built)
Picture sizes and the persona picture height; sticker packs as tabs; "As they are" setup with a persona step; the
⚙ Setup menu; uploads from the stats page; readable custom looks; Screen memory "out of view / all"; My own object
on the Extras page; chat personas in seven parts (and Bulba setting one for just a chat); status pictures; the
model pill removed. The ElevenLabs voice id on the Screen already existed. Next: see `docs/HANDOFF.md` → Next.

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
