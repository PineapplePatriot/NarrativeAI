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

## Phase A: small, grounded (no blockers)

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

## Phase B: structured cards and personas (the foundation)

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

## Phase C: story memory, on by default

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

## Phase D: custom chat looks, made with Bulba

Inspired by Molfar.Vertep's per-chat looks, without letting an AI rewrite the app: Bulba fills a **theme recipe**
(colours, a font from an approved list, bubble shapes, text effects, a light effect, the speech palette) per chat
or per character; preview, apply, undo; shareable as a file. No raw code, so it can't break the page.

## Phase E: Tomato Pit and garden

Featured **banners** on the Sauce-o-Matic (a rate-up legendary for a week, with its own look and countdown), new
prizes; garden weather and seasons, rare plant mutations, visiting critters, small orders from the gardeners.

## Phase F: messenger mode

A separate page imitating Telegram/Discord: casual one-on-one chats with the characters, voice messages
(ElevenLabs), the occasional picture (Nano Banana); shares the character and the story memory. Group chats
(several separate characters) come with it, if wanted.

## Later / parked

- The guided tours in more languages.
- Editable in-story attachments (a phone handed over, notes the character writes in), building on designed objects.
- Group chats of separate characters (parked: B2 covers several characters in one card).
- User-made background prompts (parked).

## Suggested order

A (a few days) → B1–B5 → C1–C9 (the big one; the prompt gets tuned with the cold-reader tests before it's the
default) → D → E → F. Each phase ends with a push and a list of what to check live.
