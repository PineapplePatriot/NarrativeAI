# Model-specific research checkpoint — 3 October 2026

Status: primary documentation checked; no paid model calls or RP experiments performed. Model identity is verified separately from subjective writing quality. Provider adapters still require smoke tests.

## Critical implementation findings

- Claude models released after Opus 4.6 do not accept adjustable temperature/top-p/top-k on the direct API. Default-compatible temperature 1 and top-p ≥0.99 are accepted; other values error, and any top-k errors. Do not provide pretend creativity sliders for Opus 4.7, Opus 5.5, or Fable 5.1. Source: https://platform.claude.com/docs/en/api/php/messages/create
- Kimi K3 always reasons. Its official endpoint fixes temperature=1, top_p=.95, n=1, frequency/presence penalties=0; omit those fields. Effort low/high/max (default max). Source: https://platform.kimi.ai/docs/guide/kimi-k3-quickstart
- MiMo v2.6 Pro thinking mode forces temperature=1 and top_p=.95 even when other values are supplied. Non-thinking advertised ranges are temperature 0–1.5, top_p .01–1. Source updated September 20: https://mimo.mi.com/docs/en-US/api/guidance/model-hyperparameters
- DeepSeek's direct endpoint no longer serves original V4 Flash: even the legacy `deepseek-v4-flash` identifier is routed to **V4.1 Flash**. Do not silently label it V4 Flash. V4 Pro remains `deepseek-v4-pro`, currently Pro-0813. Source: https://api-docs.deepseek.com/quick_start/pricing/

## Model registry

| Requested model | Verified direct identifier | Verified behavior / configuration | Evidence |
|---|---|---|---|
| Claude Opus 5.5 | `claude-opus-5-5` | Always-on adaptive reasoning; default medium effort; 1M context, 128K output. Released September 22. | https://platform.claude.com/docs/en/models/opus-5-5/overview |
| Claude Fable 5.1 | `claude-fable-5-1` | Always-on adaptive reasoning; default high; 1M context, 128K output. Released September 1. | https://platform.claude.com/docs/en/models/fable-5-1/overview |
| Claude Opus 4.6 | `claude-opus-4-6` | Adaptive thinking supported, default effort high; thinking is off unless requested. In thinking mode omit temperature/top_k; top_p .95–1 allowed. Non-thinking permits sampling controls. | https://platform.claude.com/docs/en/models/opus-4-6/overview |
| Claude Opus 4.7 | `claude-opus-4-7` | Official April 16 announcement and model-ID reference confirm exact ID; introduces xhigh effort. Thinking optional; later-than-4.6 sampler restrictions apply even with thinking off. | https://www.anthropic.com/news/claude-opus-4-7 |
| Kimi K3 | `kimi-k3` | Always-on thinking; low/high/max effort; fixed samplers above. | https://platform.kimi.ai/docs/guide/kimi-k3-quickstart |
| MiMo v2.6 Pro | `mimo-v2.6-pro`; OpenRouter `xiaomi/mimo-v2.6-pro` | Mode-dependent sampling above. | https://mimo.mi.com/docs/en-US/api/chat/openai-api ; https://openrouter.ai/xiaomi/mimo-v2.6-pro |
| Gemini 3.8 Flash | `gemini-3.8-flash` | Stable September release, 1,048,576 input / 65,536 output; thinking low/medium/high; minimal errors. | https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash |
| GLM 5.3 | `glm-5.3` | Always-on reasoning, low/high/max (default max); temperature 0–1 default1; top_p .01–1 default .95; do_sample=false disables both controls. | https://docs.z.ai/guides/llm/glm-5.3 |
| DeepSeek V4 Pro | `deepseek-v4-pro` | Current direct version Pro-0813; reasoning on/off; 1M context. | https://api-docs.deepseek.com/quick_start/pricing/ |
| DeepSeek V4 Flash | Legacy ID accepted but no longer exact model on direct API | Direct API replaced by V4.1 Flash. OpenRouter lists original 0423 as `deepseek/deepseek-v4-flash` with several providers; pin provider and validate snapshot before tests. | https://api-docs.deepseek.com/quick_start/pricing/ |

## Prompting evidence, without RP overclaims

**Opus 5.5:** Anthropic recommends measuring effort rather than copying settings from older models; lowering effort is more dependable for latency than a no-thinking instruction. Thinking uses the output budget even if hidden. Existing Opus 5 prompts are a starting point, not a guarantee. None of this establishes an optimal RP preset length. The user's observation that short presets work and some negative constraints help remains a specific hypothesis to test. Source: https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5-5

**Fable 5.1:** Official guidance explicitly describes possible long, dense sentences and fewer paragraph breaks. It gives both detailed anti-pattern explanations and a short instruction as possible interventions. This is evidence against a universal ban on negative instructions, but it is not an RP benchmark. Guidance also says old anti-formatting constraints can overcorrect the new default. Preserve thinking blocks only with compatible conversation history: rewriting a preset/history while replaying bound blocks can fail. Source: https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5-1

**Opus 4.7:** Official announcement describes more literal instruction following, new tokenizer and greater high-effort token usage. Coding claims should not be treated as prose-quality evidence. Source: https://www.anthropic.com/news/claude-opus-4-7

**Other models:** Provider documentation establishes request compatibility, not taste. No controlled evidence yet supports universal model-specific claims such as 'Kimi needs long presets' or 'Gemini needs bans.' They must be tied to named preset versions, firsthand reports, and ultimately matched RP tests.

## Proposed tests (not completed)

For each exact model/provider/version, compare minimal baseline, the selected community preset, and personalised adaptation. Vary prompt length separately from instruction content; test a short semantic constraint against a token blacklist and positive behavioral direction. Score absence of the disliked behavior as well as synonyms that preserve it, character fidelity, user agency, dialogue/subtext, pacing, and user preference. Re-run across multiple scenes and turns; do not let one flattering sample define the profile. Record effort, supported samplers, prefix/history, output cap, preset version, and retries. A capability error should revise the adapter, not be disguised as a taste failure.

## Narrow-gap verification and provider implications

**Opus 4.6 versus 4.7:** The shared thinking reference explicitly names both as thinking-off by default, enabled with `thinking: {"type":"adaptive"}`. On 4.6, thinking mode prevents temperature/top-k adjustment but permits top-p .95–1. With thinking off, the Messages API permits temperature 0–1, top-p, and top-k, subject to model request constraints; use one sampling intervention at a time in experiments. Opus 4.7 remains sampling-restricted even with thinking off. Manual budgeted thinking is deprecated for 4.6; build new profiles around adaptive effort. Sources: https://platform.claude.com/docs/en/build-with-claude/thinking ; https://platform.claude.com/docs/en/api/php/messages/create ; exact IDs: https://platform.claude.com/docs/en/about-claude/models/model-ids-and-versions

**GLM 5.3 contract:** Direct Chat Completion schema explicitly gives temperature 0–1 (default1), top-p .01–1 (default .95), and `do_sample` (default true; false makes those controls ineffective). Reasoning cannot be disabled; only low/high/max are supported for 5.3 despite broader enum values shown for other GLM versions. Historical reasoning is cleared by default (`thinking.clear_thinking=true`); preserving it requires complete unmodified history. These are documented controls, not evidence that changing them improves RP. Source: https://docs.z.ai/api-reference/llm/chat-completion

**Original DeepSeek V4 Flash remains a provider-specific option:** OpenRouter's catalog explicitly labels `deepseek/deepseek-v4-flash` **0423** and lists active providers including Relace, StreamLake, DeepInfra, Venice, SiliconFlow and others. It documents high and xhigh reasoning, with xhigh mapped to max. This is evidence of catalog availability, not proof that every provider serves identical weights or honors every parameter. Pin an endpoint/provider and record its version rather than using the direct DeepSeek legacy alias. Source: https://openrouter.ai/deepseek/deepseek-v4-flash

**DeepSeek documentation chronology:** An earlier V4.1 announcement said V4 Pro would be replaced; the later change log says user demand led DeepSeek to retain V4 Pro beyond September 14, and the current pricing page lists Pro-0813 separately. Use the current contract and preserve this contradiction in provenance. Sources: https://api-docs.deepseek.com/updates/ ; https://api-docs.deepseek.com/quick_start/pricing/

**Direct DeepSeek sampling:** Current Chat Completions docs say temperature 0–2 (default1) has no effect during thinking. Top-p only operates in thinking mode, clamped to .95–1; non-thinking fixes it at1. This is an important counterexample to treating OpenAI-compatible syntax as equivalent parameter semantics. Source: https://api-docs.deepseek.com/api/create-chat-completion/
