# Visual Novel (Meet-Up) mode: what to fix, and how

For Codex, on `codex/screen-integration` (checked on 22 Nov 2026). Feedback from testing it live. Main files:
`mainapp/vn_scenes.py`, `vn_story.py`, `vn_support.py`, `messenger.py` (`load_character_references`),
`static/mainapp/js/vn_scenes.js`.

Order: 1 and 2 first (they damage data and block play), then 3, 4, 5.

---

## 1. The modern look gets mixed with the main chat's pictures (data bug: fix first)

**What happens.** A Screen character has a modern look (outfit, phone avatar). The VN mixes it with the
character's main-chat pictures (the canon / fantasy look), in both directions:

- **Wrong references going in.** `messenger.load_character_references()` falls back to `character.photo_neutral`,
  then to the character's mood sprites, when the Screen profile has no `neutral_url` / `extra_refs`. So the
  canon-look sprites become the identity reference for a modern scene.
- **VN pictures overwrite the main chat's sprites.** In `resolve_or_generate_sprite()`, when `scoped` is false,
  a generated picture is written into `Character.photo_<emotion>` (or `sprites.save`). A VN expression in a
  modern outfit then replaces the main chat's sprite for that mood, permanently. `finish_scene_with_cg()` uses
  the same references.

**How to fix.**
- Keep the VN's pictures completely apart from the main chat's: VN pictures belong to the Screen profile
  (or to the episode). Never write `Character.photo_*` or call `sprites.save` from VN code. Always take the
  `scoped` path; save under `messenger/vn_sprites/...` and record them on the Screen profile
  (for example `prof["vn_sprites"][emotion]`), so later episodes reuse them.
- References: use the Screen profile's own pictures only (`neutral_url`, `extra_refs`, its avatar, and VN
  sprites already made). If a character has none, don't silently use the main chat's sprites: make a modern
  neutral picture first, from the Screen profile's description and outfit, and ask the user to approve it once.
  At most, use the main chat's picture for the face only, with the prompt saying so explicitly, and only when
  the user ticks "use their main-chat picture for the face".
- One-off repair: find `photos/vn/*` files currently set on `Character.photo_*` fields and offer to restore the
  previous sprite. If the previous one is gone, at least list the affected characters and moods on the
  character page.
- Tests: a VN sprite/CG run must leave every `Character.photo_*` field unchanged; references must come only from
  the Screen profile when it has pictures.

## 2. Generation errors: one bad line throws away the whole turn

**What happens.** `_enrich_beats()` raises an error for the entire turn when one beat is off:
- a line spoken by anyone outside the picked cast (a barista, a passer-by, a named side character),
- a line spoken as the user (often the model writes the user's *name* instead of `"user"`),
- a JSON answer that doesn't parse (`_call_vn_json`): `max_tokens` 4500 plus the reasoning budget, and a long
  scene gets cut off mid-JSON.

There is no retry and no repair, so the user just sees "Try again", often over and over.

**How to fix.**
- Repair instead of failing:
  - **Side characters:** an unknown speaker becomes a side character (narrator box with their name, no
    sprite), not an error.
  - **Lines for the user:** a beat spoken as the user, or with the user's persona name, is dropped (or turned
    into narration) and the turn ends at the last beat before it, handing control to the user. Error only if
    nothing is left.
- JSON: try to repair cut-off JSON first (close open strings, arrays and objects, keep the complete beats).
  If it still fails, retry once automatically with a shorter target ("at most 8 beats"). Only then show an
  error, and show the actual reason (cut off / not JSON / provider error) plus a **Retry** button that keeps
  everything.
- Ask for fewer beats per call (6–10). Ask for the next part when the user clicks on, instead of one huge
  answer.
- Log the raw model answer on failure (server log, trimmed) so the cause can be seen.
- Tests: an answer with an extra speaker, one with the user's name as speaker, and a JSON answer cut off halfway
  must each still give a playable turn.

## 3. Meet-ups feel disjointed from the texting before them

**What happens.** The texting stops, and a scene starts that doesn't feel like the same evening: the place,
time, mood and what was just said don't carry over. Afterwards, coming back to the phone doesn't feel like it
continued either.

**How to fix.**
- **Before the scene:** a bridge. Read the last 20–30 texts and the Screen chat's memory, and let the model
  write one short opening beat that picks up exactly from them ("Twenty minutes after his last text, the café
  door opens..."). Use the place, time and plans from the texts (who is coming, where, why), the Screen clock,
  and each character's Screen look and outfit.
- **The cue:** `MEETUP_CUE_RE` is English-only and fires on small words ("downstairs", "lobby", "I'm here").
  Make it an offer the user accepts ("📍 They're at the door. Switch to the scene?"), never an automatic jump.
  Let the model confirm it's really a meet-up. Support Ukrainian too.
- **During the scene:** the same voice as in the texts. Give the scene prompt the Screen texting profile (how
  they talk) along with the card, and the relationship state from the chat.
- **After the scene:** a return bridge. The episode summary goes into the Screen chat's memory (already done),
  and the character's next text refers to what just happened ("got home. still thinking about what you said
  at the door"). The episode shows as a card in the chat ("📖 Episode: Coffee at Zolnyy · 24 lines ·
  Re-read").
- Bulba (the Screen's Bulba) should know VN mode exists: how to start one, change the place, redo a picture.

## 4. No way to redo pictures

**What happens.** Sprites, backgrounds and CGs can't be made again, and there's no way to say what was wrong.

**How to fix.**
- A ↻ on every picture: the current sprite, the background, the CG in the gallery. It opens a small box,
  "What should change?" (optional), and that note goes into the image prompt as an instruction that fixes the
  last try. The main chat already does this; see `_make_sprite(..., note)` in `mainapp/views.py` on
  `claude/zen-feynman-ta1yra`.
- Keep the previous version until the new one is accepted ("Use this one / Keep the old one").
- Let the user upload their own picture for a mood, background or CG in the same place.
- The cost shows before each make (it's on their key).

## 5. It feels bare-bones

Ideas, smallest first:
- **Presentation:**
  - name plate in the character's colour;
  - text that types out, with click to finish and click to advance;
  - auto-advance and skip;
  - a backlog / history (scroll back through the scene);
  - a soft transition when the background or sprite changes;
  - sprite position (left / centre / right) when two people are on stage.
- **Sound:** music fades between tracks. Optional voice per line, using the ElevenLabs voices the Screen
  already has.
- **Choices that matter:** 2–3 choices at real decision points (not every turn), with a small hint of the
  relationship change after one is picked. A free-text "say something else".
- **Episode menu:** save / load points inside an episode, the episode list with its CGs, and "replay from
  here".
- **Scene controls:** change place mid-scene ("go somewhere quieter"), add or remove a character, a time skip.
- **End of episode:** a title card ("Episode 3: The Café"), the CG, a short "what changed" (relationship,
  memory), and back to the phone.
- **Mobile:** the text box above the browser bar, big tap targets, a sprite that fits the screen height.

## Checks before handing it back

- Play one meet-up end to end on a phone and on a 13-inch laptop, with a character whose Screen look differs
  from the main chat's. Afterwards, the main chat's sprites must be unchanged.
- 10 turns in a row without a "Try again" error, including a scene with a side character.
- Redo a sprite and a background with a note; the note visibly changes the result.
- Afterwards, the next text from the character refers to the scene.
