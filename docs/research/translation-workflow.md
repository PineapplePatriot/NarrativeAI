# English generation and translated display

## Status, 8 November 2026 (integration done; live quality still to test)

On: Profile → You in stories → Story language. Any language but English turns the workflow on.

- Chat, regenerate and continue end with an English-writing instruction (translation.english_note).
- Order on the page: stream (hidden behind "✍️ Writing…") → polish if due ("🧹 Revising…") →
  translate ("🌐 Translating…") → show. A reply cut short (Stop, error) is translated too.
- `translate` action translates one reply and writes only that message back (trackers or a summary
  saved meanwhile are kept). Each swipe keeps its own translation (chats.VERSION_KEYS).
- 🌐 on a translated reply shows the English and back; 🌐 on an untranslated one translates it. On
  load the newest reply (a new chat's greeting) is translated by itself; older ones on 🌐.
- Editing a translated reply: "Bulba is updating the English version…", synchronize_edit, saved only
  on success; on failure the draft stays and nothing is saved.
- Summary panel: 🌐 <language> shows the pieces translated (read-only, cached per piece in the chat
  file's translation_cache); the pieces stay English for the AI.
- Trackers write their values in the reading language (no extra call).
- Profile save offers to remove the basics form's "Write the whole story in X." from the active
  preset; the setup's Story language answer now sets the profile setting instead of a preset rule.
- Translation task is on the Connections page; without its own model it uses
  ai_client.TRANSLATION_MODEL (google/gemini-3.8-flash) through OpenRouter.
- User messages are not translated (the model reads them as written).

Still open: story extras (letters, phone screens) stay English; exports show the English; live
comparison of translators and of English-then-translate vs direct Ukrainian.


## Implemented foundation

`users.User.display_language` defaults to `en`. It is not yet exposed in the profile form;
changing it currently does not activate translation. Migration 0014 adds the preference.
Existing accounts, presets, persona, lorebooks and message text remain unchanged.

`mainapp.translation` uses the existing AI client through a separate `translation` task.
The task is hidden until workflow integration is complete. It can have its own TaskSetting
profile/model; otherwise it inherits the main connection. No default translator has been
selected or quality-tested. English-to-English requests bypass the provider entirely.

English stays in message[2]; message metadata stores translation text, language and a SHA256
of its source. Existing reasoning and polish metadata are retained. A stale translation is
neither displayed nor scanned. Lore activation joins a valid translation to its source inside
one message, preserving scan depth and supporting both language keyword sets.

`synchronize_edit` returns a new pair only after successful reverse translation. It does not
save data or overwrite the input. Translation errors must preserve the edited draft in the UI.
Functional tags, macros and markers are checked before accepting translated output. This is
not a semantic fidelity check, a detector of partial translations, or a quality benchmark.

## Remaining integration before enabling

1. Profile control and separately selectable translation model. Keep interface language distinct.
2. Final English instruction in chat assembly and English instructions authored by Bulba;
   review existing user language rules rather than silently deleting custom instructions.
3. Generate English -> finish/stop handling -> English polish -> translate -> persist pair.
   Use clear progress stages, including translation errors/retry. Never expose partial English
   as if it were a completed Ukrainian reply. Retain interrupted generations safely.
4. Display translated text and a message-panel Show original action. Generation, Watch, summaries
   and tracker inputs consume the source. The browser's displayed text is not canonical history.
5. Edit synchronization with an explicit saving state. Re-read and compare source/version before
   committing; reject a concurrent change instead of overwriting it. Block subsequent generation
   while synchronization is pending. Retry preserves the user's draft.
6. Regenerate, Continue, swipes, branches, undo polish, manual polish and exports must preserve
   or invalidate pairs correctly. Old chats have no assumed English counterpart; preserve them.
7. Summary translations on demand, cached by source fingerprint. Translate descriptive tracker
   values and in-story prose without changing schema keys, counters, IDs or application logic.
8. Live translation evaluation, including gender, politeness, consistent names, emotional register,
   explicit language where present, HTML, literal quoted instructions and adversarial source text.

Do not automatically translate the entire persona or lorebook. Existing Ukrainian material remains
available to the generator; dual-language keyword scanning addresses activation separately.

## OpenRouter source check, 7 November 2026

- https://openrouter.ai/docs/guides/overview/models
- https://openrouter.ai/api/v1/models

Both endpoints were fetched successfully. The public catalog lists text models including
`google/gemini-3.8-flash`, `qwen/qwen3.8-flash`, and `deepseek/deepseek-v4.1-flash-1017`.
These are availability candidates, not recommendations or measured Ukrainian quality rankings.
Use the ordinary chat-completions client and its existing usage accounting. JSON output support
must be verified for the selected connection; unsupported or malformed output fails safely.
No paid completions or user credentials were used for this source check.
