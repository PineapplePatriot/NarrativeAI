# Gemini request-path audit — 10 November 2026

Audited current master 0b621cf, including the recent OFF/civic-integrity compatibility and mature-wording
changes, rather than the older Codex branch. No production user requests or provider dashboard logs were
available. No live completions, policy-circumvention experiments or changes to moderation thresholds,
model routes, age facts or story content were made in this pass.

## Confirmed paths

- Ordinary generation uses build_chat_request and the common AI client, often streaming.
- Bulba retry_reply also uses build_chat_request, with the proposed edit when pending, and sends a
  synchronous chat completion. It is not merely the polish prompt or an isolated passage. Applied
  proposals are not applied a second time. The audit found two omissions in this separate builder:
  the final English-generation note for translated-reading mode and restoration of old per-reply
  director notes. The patch adds those, including deduplication of a newer note message into its
  proper slot, matching Regenerate. No claim is made that either omission caused this user's block.
- Polish uses a separate system prompt plus character name, a clipped summary, habits and the passage.
  It does not inherit the whole chat preset or card. Model routing uses the user's polish choice.
- Translation uses a dedicated system prompt, text, language IDs and glossary, not the whole story
  preset. Before this patch, enabling mature content appended ADULT_NOTE with mature/violent/explicit
  and non-refusal instructions even if this passage contained only banter. This was removed in this
  patch: translation now uses its task-specific fidelity/format prompt regardless of the generation toggle.
- Both synchronous and streaming OpenRouter calls already request GEMINI_SAFETY for google/* models.
  The code uses OFF and the five categories shown in the user's ST screenshot. This proves what our
  payload requests, not what the upstream provider honors or what its nonconfigurable checks do.
- mature.for_model changes only the exact stored REMINDER_LINE. It does not transform translation's
  former ADULT_NOTE or arbitrary imported NSFW blocks. This is a prompt difference, not proven causation.

## What the screenshots cannot establish

Equal model IDs and filter settings do not establish equal final messages, provider endpoints,
reasoning modes, transforms or request paths. The ST screenshot is not the failed NarrativeAI payload.
PROHIBITED_CONTENT alone does not identify a triggering span, a particular character's age, the preset,
rewriting as a task, or whether changing an adjustable field could change the response. There is no
basis here to tell the user that the preset is uninvolved or that an unchanged retry will work.

Adult account confirmation and adult characters are distinct facts. Do not invent character ages,
add blanket all-characters-are-adults instructions to an inconsistent story, or silently remove
legitimate story context as a diagnostic fix. If age context is relevant, inspect the actual card,
lore, summary and history and preserve the user's intended consistent setting.

## Concrete changes

1. Rewrite assembly now preserves the final English-language directive and the saved per-reply
   director guidance, without duplicating a note already represented in the newest-note slot.
2. Synchronous blocked finish reasons now raise an explicit provider-block error rather than returning
   empty content to translation/polish. Usage is still recorded when returned. Finish/native reason
   metadata is preserved in diagnostics.
3. Safety-setting compatibility retries only happen when a 400 explicitly identifies an invalid or
   unsupported safety-settings field. An unrelated invalid parameter does not strip the settings.
   Moderation blocks are not treated as schema errors. Existing accepted filter settings are unchanged.
4. Error wording no longer claims the most common cause is minor-coded characters or tells users to
   retry an unchanged request. Bulba's chat guide distinguishes applied edits from a successful rewrite
   and prohibits unsupported claims about the cause or the next reply succeeding.
5. The translator no longer appends blanket adult-generation/non-refusal instructions based solely on
   the mature-content toggle. Its fidelity and formatting requirements remain; no source text or model
   settings are rewritten. Whether the removed note contributed to blocks is unverified.
6. Text-free warning diagnostics identify task, rewrite operation, requested model, connection ID,
   request fingerprint, message roles/lengths, parameter names, category count, stream mode and routing
   presence. Errors include provider/request identifiers and finish reasons when actually supplied.
   Raw errors, prompt text, outputs, keys and headers are not logged. A compatibility retry retains the
   effective payload for accurate fingerprints. Not every response includes an actual provider name.

No new request-fallback chain or refusal-bypass mechanism was introduced. Existing routing is unchanged.
The diagnostic operation tag is internal and is never sent to the model endpoint.

## Next evidence needed

After deployment, correlate the failed operation/time/connection with AI request diagnostic logs and
OpenRouter's request/provider metadata. Compare with a successful ST request using the same intended
scene and model route. Full payload review should be user-authorized and kept private; these text-free
logs cannot identify a triggering phrase. Compare roles/context, enabled modules, summary/card/lore,
translation glossary, reasoning, transforms and effective transport parameters before changing prompts.

Only isolate meaningful differences using an agreed, non-sensitive reproduction of the user's intended
benign interaction. A faithful translation shouldn't automatically receive the entire story-generation
preset; that could add unrelated instructions and does not guarantee acceptance. No claim is made that
this audit has identified the production block's cause or fixed provider behavior.
