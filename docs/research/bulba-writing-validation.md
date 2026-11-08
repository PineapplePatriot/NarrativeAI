# Bulba writing changes: validation cases

These cases exercise the revised MiMo starters and Watch instructions. They are a local
acceptance protocol, not evidence of live MiMo improvement. Automated tests use a fake reader;
they verify aggregation, evidence grouping and interaction behavior, not literary judgment.

## Compare on the same connection

Keep model, provider, reasoning mode, character, accepted history, language and generation
budget fixed. Compare the previous starter with the revised starter. Test Ukrainian as well
as English. Record the resolved request, including user taste, reminders and enabled blocks.
Do not treat the starter file alone as the user's active preset. Existing saved presets are
not rewritten when a starter changes; use a new copy or an explicit reviewed edit.

Generate several alternatives for each case using a configured test account and an approved
budget. Do not use a production user's credentials or send their private history elsewhere.
Record targeted patterns and preference separately: fewer matches does not prove better writing.

## Required cases

1. **Reversible gestures.** Several emotionally difficult exchanges, without an injury or physical
   task requiring hand movement. Watch should identify recurring clench/unclench or open/close
   reactions as `stock_reactions`, even when different body parts or wordings are used. The
   generation fix must not install compulsory cup handling or another replacement gesture.
2. **Vague expression.** Repeated descriptions such as «щось у погляді стає різкішим» or
   “something changes in his eyes,” without specifying a relevant perception. Expect
   `vague_emotion`; do not flag a precise, consequential observation merely for mentioning eyes.
3. **Dialogue recap.** The player describes their location and applying cream; the other character
   repeatedly lists those same facts in dialogue instead of answering. Expect `echoing_user`
   when the listing has no communicative purpose. A useful correction, disagreement or joke
   about an observed fact must remain possible.
4. **Several mechanisms together.** Include gesture filler, vague expression and dialogue recap
   in at least two read replies. The reader may report distinct labels for the same reply;
   aggregation must retain all qualifying findings. The UI lists findings with no expanded
   evidence until one is selected. Muting or correcting one must not act on the others.
5. **Repetition evidence.** Several different phrases each appearing in only two replies must
   not collectively satisfy the three-reply exact-phrase threshold. A notification must show
   occurrences of one qualifying phrase rather than pool unrelated phrases.
6. **Meaningful quiet.** A reserved character answers directly and leaves an unresolved decision
   to the player. The reply need not add an event, gesture, question or revelation. Watch must
   not diagnose stagnation solely because the conversation is quiet.

Also test actual counseling speech by an established counselor, urgent action after a slow
conversation, and meaningful repeated mannerisms. Preserve humor, interiority and imagery
when the user wants them. The plain-language requirement applies to preset instructions;
it does not prohibit those choices in generated fiction.

## Current verification boundary

Local regression tests cover distinct semantic labels qualifying together and exact-phrase
aggregation. A headless Chromium check exercises the mobile findings list, selecting evidence,
scoped mute, returning to the list and closing it. These do not establish live reader accuracy
or improved story generation. No paid model requests are required by the automated suite.
