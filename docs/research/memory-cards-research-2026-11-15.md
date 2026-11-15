# Research: story memory, structured cards, knowledge and relationships (15 November 2026)

Input for `docs/PLAN.md` (phases B and C). What other roleplay engines and community practice do, and what we
take from each. Ideas only: Molfar.Vertep is AGPL-3.0, so nothing is copied from its code.

**Limits of this pass.** This build machine's network allows GitHub but not most community sites (rentry.co,
Janitor guide pages, docs.sillytavern.app, arXiv, inworld, personal blogs): those pages were not read, only
their search-result summaries. Field-level details below come from GitHub READMEs and change logs. Worth a second
pass if those hosts get allowed: the JanitorAI "Chatbot Book" (multi-character blocks, trigger matrix, a
simulator case study), NicholasCS's bot-making guide (scenario bots), the Generative Agents paper (memory
stream, importance, reflection), Inworld's relationship docs.

## 1. Story memory

| Source | Unit | Shape | Injected as | Worth taking |
|---|---|---|---|---|
| Molfar.Vertep "Litopys" (GitHub change log) | a scene | short chapter + facts with **who knows them**; arcs over old chapters; turning points kept nearly word for word, with how each character feels; lies become "Belief" facts; group/faction knowledge | chapters stay in the prompt when old messages leave it ("a long chat still fits a small model's window") | almost all of it, renamed for us: milestones, facts, beliefs, arcs |
| MemoryBooks (SillyTavern extension, GitHub) | a scene range, marked by hand or every N messages | JSON `title`, `content`, `keywords`; consolidation tiers (arc, chapter, book…) | as lorebook entries (keyword activation, budget, priority) | the group-chat rule: keep **who did each action, who said it, who learned or revealed it, who decided, who believed or misunderstood**; regenerate never overwrites without approval; catch-up for old chats |
| Qvink MessageSummarize (GitHub) | each message | free text | two tiers with token budgets: rolling short-term, pinned long-term | summaries tied to their messages (edit/delete updates them); a "mark important" pin; a **cache-aware injection point** that moves only on triggers; low temperature, short prompt |
| "Recursively Summarizing…" (Wang et al., arXiv 2308.15022, abstract via search) | small chunks, then memory + new context → new memory | running memory | memory, then the reply | consolidation works, but a single running summary degrades over time (Qvink's README says the same): keep milestones fixed and add arcs on top |
| Talemate (GitHub) | separate agents: summarizer, world-state manager, director | world state "to reinforce character and world truths"; time passage | per agent | split jobs: the milestone writer, the world/people register, the relationship judge |

**Our gap today:** one running summary text (summary pieces), free recall by rare words, Watch's "getting the past
wrong". No who-knows-what, no per-scene units, no people register.

**The prompt requirement (Anya's):** a milestone must make sense to a model that has never seen the chat.
"They meet Ivan" is useless; "they meet Ivan, Dottore's new guard on the third sublevel" is the standard. Small
details stay when the story may come back to them (a name, a number, a promise, an object handed over, an
injury, a lie). Nobody else documents this rule clearly; it becomes our prompt's first instruction and a test.

## 2. What characters know

- Molfar.Vertep: facts carry who knows them; "characters know less than the player"; scenes a character missed
  are cut from replies written from their view; a warning under a reply when a character acts on a secret it
  shouldn't know; a lie heard by others becomes their belief; `group:` / `faction:` tags spread knowledge.
- Lorealm: a realm is a stage "where every actor only sees what it's given" (visibility by design).
- MemoryBooks: participants come from who actually took part, not from guessing over the prose; per-character
  copies of a memory are "not a security boundary".
- A research write-up on "perspective-bounded memory" for book-based role-play (search summary only) points the
  same way: each character's memory limited to what they witnessed.

**Our design:** facts with `known_by`, `believed_by` (with what they believe instead), `hidden_from`, plus where
it came from (which milestone). Present characters get the facts they know; the narrator (the model) gets the
truth plus a line on who doesn't know it. The knowledge guard rides on Watch's existing read.

## 3. Relationship progression

Common pattern in hobby systems and commercial docs (search summaries: an affection-system write-up, Inworld,
Shapes "Love Life", an RPG prompt pack):
- a few dimensions (trust, affection/warmth, respect, tension…), small numbers;
- a named **stage ladder** decided from them (stranger → acquaintance → friend → close; romance ladders when the
  story is one);
- crossing a threshold changes what the prompt says ("unlocks new behaviours");
- updates by the model judging the scene (one write-up gives the character an `update_evaluation` tool), saved
  between sessions;
- a warning from the community: emotional labels written into a card make the character *always* that; drive
  change through the mechanic, not fixed adjectives.
- Molfar.Vertep's "Soul": per character, how fast they warm up, what hurts them, where their attitude starts.

**What we already have:** story systems (meters that move at most a step per scene, cooldown, drift, kept scenes
only), the Relationships tracker (affection/trust/tension), milestones in story extras. **Our design:** one
relationship record per ordered pair (A's view of B ≠ B's view of A), stage + 2–3 dimensions + "what changed it"
history, moved only by kept scenes and capped per milestone, the stage's note steering the writing; the card's
temperament section sets the starting point and speed.

## 4. Cards

- Molfar.Vertep: the card split into switchable fields ("identity, appearance, personality, behavior, goals,
  background, relationships and more"), each off costs nothing; it "still saves as plain text, so every other app
  reads it"; "Structure it" sorts old text into fields; "Fill empty"; "Read from picture" (appearance from the
  portrait); one profile can describe several characters; personas get the same fields "plus five short
  questions"; a separate temperament ("Soul").
- Our own guide (`docs/bulba/research/06-character-card-guide.md`): identity, motives, personality as behaviour,
  voice, relationship to the user first; plain labelled text beats W++/JSON; essentials in the description.
- Community (search summaries): scenario bots need guidance so the model doesn't act for {{user}}; NPCs and places
  usually live in the lorebook, "things that should always be in context" in the description; in multi-character
  worlds "relationships matter more than traits"; nobody documents NPCs created during play: our memory's people
  register would be new.

**Our design:** sections stored separately, composed into the description text (so SillyTavern import/export and
every existing prompt path keep working), each switchable and token-counted; several characters per card, each
with its own sections; three card types (character, ensemble, simulation); personas with the same sections.

## Sources

- Molfar.Vertep: https://github.com/MolfarWav/Molfar.Vertep (README, CHANGELOG)
- Lorealm: https://github.com/Lorealm/Lorealm (README, docs/weaver-hosts.md)
- Qvink MessageSummarize: https://github.com/qvink/SillyTavern-MessageSummarize
- MemoryBooks: https://github.com/aikohanasaki/SillyTavern-MemoryBooks (README, USER_GUIDE.md)
- Talemate: https://github.com/vegu-ai/talemate
- Wang et al., "Recursively Summarizing Enables Long-Term Dialogue Memory in LLMs": https://arxiv.org/abs/2308.15022
- Tavernary listing of Molfar.Vertep: https://tavernary.org/
- Search summaries only (pages blocked here): https://rentry.co/nicholascsbigassbotmakingguide,
  https://fcgod.github.io/JanitorAI-Scripts-Centralized-Repository/ChatbotBookSite/book/print.html,
  https://blog.meganova.ai/building-multi-character-worlds-advanced-techniques/,
  https://waifustack.pages.dev/posts/building-an-affection-system-for-ai-characters,
  https://docs.inworld.ai/docs/runtime-character-attributes/relationships,
  https://themodelwire.com/article/staying-in-character-perspective-bounded-memory-for-book-based-role-playing-agen-01KVY96CANFG5DJPNWQH320YX7
