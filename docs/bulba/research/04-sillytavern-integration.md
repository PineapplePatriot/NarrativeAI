# SillyTavern integration and export specification

Research date: 3 October 2026. Status: source inspection and proposed adapter design; no model API calls or import round-trip testing performed.

## Verified baseline and source register

Public release source inspected during this research identifies **SillyTavern 1.19.0**, commit **06bde939fb1e9c4c8d8641d810f0a916b5bce127**, committed **14 September 2026, 19:01:34 UTC**. Pin adapter work to this revision rather than the moving release branch. The initial downloaded source files disappeared when the execution environment reset; observations below distinguish inspected behavior from proposed implementation.

Primary sources:

- [Connection Profiles documentation](https://docs.sillytavern.app/usage/core-concepts/connection-profiles/)
- [Prompt Manager documentation](https://docs.sillytavern.app/usage/prompts/prompt-manager/)
- [Pinned chat-completion frontend and preset exporter](https://github.com/SillyTavern/SillyTavern/blob/06bde939fb1e9c4c8d8641d810f0a916b5bce127/public/scripts/openai.js)
- [Pinned Connection Manager](https://github.com/SillyTavern/SillyTavern/blob/06bde939fb1e9c4c8d8641d810f0a916b5bce127/public/scripts/extensions/connection-manager/index.js)
- [Pinned chat-completion backend](https://github.com/SillyTavern/SillyTavern/blob/06bde939fb1e9c4c8d8641d810f0a916b5bce127/src/endpoints/backends/chat-completions.js)
- [Default chat-completion preset](https://github.com/SillyTavern/SillyTavern/blob/06bde939fb1e9c4c8d8641d810f0a916b5bce127/default/content/presets/openai/Default.json)

The official documentation explains user-facing behavior. Source inspection supplies the exact persisted names and identifies implementation differences: the inspected Connection Manager includes `regex-preset`, although the opened documentation's saved-selections list did not mention it.

## What a complete setup contains

A chat-completion preset is one component of a working setup. The native product bundle should additionally contain the model/provider identity, supported generation settings, test character, optional persona, required dependencies, and credential requirements. A connection profile largely records **selections of existing configurations**, not copies of their complete contents. Shipping a profile without its referenced preset is insufficient.

For novices, the product should install a researched setup, request or reuse their credential, and offer a test conversation. They should not need to understand temperature or prompt roles before starting. Calling this one-click setup does not mean credentials or a provider account can be silently supplied.

The native bundle schema is **our proposed format**, not an existing SillyTavern import format. It should contain `schema_version`, `setup_id`, `display_name`, `model`, `connection`, `generation`, `prompts`, `assets`, `dependencies`, `provenance`, and `compatibility`. Record both requested and effective settings; carry a validation report indicating unsupported or unmapped features. Store a credential requirement/reference, never the credential value.

## Prompt and settings mapping

SillyTavern's persisted chat-completion preset uses `prompts` for definitions and `prompt_order` for activation/order. The inspected default contains order records with `character_id` values `100000` and `100001`, each containing an `order` array of `{identifier, enabled}` entries. Preserve the pinned version's template records rather than inventing character IDs. A definition's presence alone does not ensure it is activated.

Prompt definitions use `identifier`, `name`, `role`, `content`, and flags such as `system_prompt` and `marker`. Marker entries represent built-in assembled content, including `chatHistory`, `dialogueExamples`, `charDescription`, `charPersonality`, `personaDescription`, `scenario`, and world-info sections. They must not be converted into ordinary literal-text prompts. `main`, `nsfw`, and `jailbreak` are historical identifiers for Main, Auxiliary, and Post-History prompts; the identifiers do not determine our product's content categories.

| Product concept | SillyTavern persisted field or component |
|---|---|
| Temperature | `temp_openai` |
| Frequency penalty | `freq_pen_openai` |
| Presence penalty | `pres_pen_openai` |
| Top-p / top-k | `top_p_openai` / `top_k_openai` |
| Context limit / output limit | `openai_max_context` / `openai_max_tokens` |
| Streaming | `stream_openai` |
| Prompt definitions / enabled order | `prompts` / `prompt_order` |
| Chat-completion source | `chat_completion_source` |
| Reasoning preference | `reasoning_effort`, plus relevant backend-specific controls |
| OpenRouter preferred providers | `openrouter_providers` |
| Connection selection | Connection Manager profile; not embedded credential |

These are persisted UI settings, not necessarily outgoing API parameter names. The backend translates and conditionally deletes values. Do not treat this table as proof that every model accepts every row.

The Prompt Manager supports System, Assistant, and User roles. Relative prompts follow the manager order; In-Chat prompts use their depth instead. Depth zero places the instruction after the latest message. Same-depth behavior also depends on role and order. Preserve the pinned PromptManager implementation's exact depth, position and trigger fields in the adapter; those serialized field names were not verified in this pass. Check Normal, Continue, Swipe and Regenerate separately because prompt triggers can differ.

Macros such as `{{char}}` and `{{user}}` must remain macros in an ST export. The product's own preview needs equivalent expansion or an explicit incompatibility result. Do not expand them permanently using the onboarding test character. Regex scripts require separate dependency handling: a regex preset reference is not the script itself, and a display-only transformation must not be mistaken for a transformation of model input. Exporting plain prompt text loses these semantics.

## Connection profiles and sensitive data

The inspected ConnectionProfile definition includes `id`, `mode`, `name`, `api`, `preset`, `model`, `proxy`, `api-url`, `stop-strings`, `start-reply-with`, `reasoning-template`, `prompt-post-processing`, `secret-id`, `regex-preset`, and `exclude`, alongside text-completion-only fields. For chat completion the command sequence applies API, preset, then API again because applying a preset may change the API. Preserve this dependency order when building an importer.

`secret-id` is a local secret reference, not an API key. It is still unsuitable as a portable credential binding. Omit it from shared bundles and let the destination user bind a local secret. Avoid copying source-instance profile IDs as meaningful portable identities.

The frontend explicitly classifies these as sensitive preset fields: `reverse_proxy`, `proxy_password`, `custom_url`, `custom_include_body`, `custom_exclude_body`, `custom_include_headers`, `vertexai_region`, `vertexai_express_project_id`, `azure_base_url`, `azure_deployment_name`, and `workers_ai_account_id`. Its export flow offers connection-related choices; therefore an arbitrary ST export must not be assumed credential-free.

Use an allowlist export adapter, followed by a secret scan. Keep standard public provider URLs where needed, but inspect custom URLs, query strings, headers and bodies for embedded credentials. Never export raw application settings or the secrets store. Preserve author attribution and component versions independently of sensitive fields.

## Provider-dependent settings, reasoning and caching

The inspected backend has model-dependent branches that remove sampling parameters. For Claude, some branches choose between temperature and top-p; others delete temperature, top-p and top-k. Adaptive reasoning removes top-k. The current code contains specific handling for Fable and Claude 5 model families. This is evidence that universal sampler recipes are inappropriate, not a substitute for each model provider's documentation or endpoint tests.

The Gemini adapter translates to `temperature`, `topP`, and `topK` and handles reasoning budgets; model-dependent removal also exists. The OpenRouter path exposes provider routing/fallback behavior and reasoning transformation. A visible slider does not establish that the selected route accepts or honours its value.

Build a capability record per exact model/provider route: parameter support, permitted combinations, omission/default behavior, output accounting, reasoning controls, and last verification date. Prefer omitting an unsupported setting over silently claiming it worked. Where model metadata is unavailable, mark the capability unverified.

The inspected backend supports Claude ephemeral cache controls with a configurable five-minute or one-hour TTL, system/tool caching and caching at depth. It also checks OpenRouter model metadata for cache-writing support. Cache performance depends on the constructed request and route; a preset alone cannot guarantee a cache hit. Keep stable instructions and character material stable where appropriate, but never freeze a preference merely to preserve caching. Reasoning text embedded in a prompt is also distinct from provider reasoning settings and from display formatting of returned reasoning.

## Export package and acceptance checks

Deliver a native complete bundle plus an ST adapter package containing the chat-completion preset JSON, test character asset, dependency files where permitted, and a plain connection manifest. Do not label the manifest an ST-importable profile until its installation path is implemented and verified. Current documented profile commands include `/profile`, `/profile-create`, `/profile-list`, `/profile-get`, and `/profile-update`; the reviewed documentation does not establish a portable whole-setup importer.

Before shipping an adapter: validate unique identifiers and prompt-order references; import into a clean pinned ST instance; inspect the assembled request with a controlled character and scene; confirm roles, macros, markers, context placement and effective parameters; test re-export; and confirm no secrets appear. Exercise Continue and Regenerate if supported. Verify that referenced regex and reasoning templates exist and that missing dependencies produce a clear result. No such runtime checks have yet been performed here.

The critical novice-facing outcome is one complete, reproducible configuration. If an export loses a feature, report the exact loss and retain it in the native bundle rather than claiming equivalence.
