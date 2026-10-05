# Current preset landscape: evidence snapshot, 3 October 2026

Status: source research, not model testing. Current author pages, original Reddit releases, independent recommendation threads, and actual JSON excerpts were inspected. No defensible market-wide popularity ranking is available. Reddit engagement and recommendations show visibility, not quality or adoption counts.

## Shortlist and freshness

| Family | Current concrete artifact found | Why investigate | Main qualification |
|---|---|---|---|
| Freaky Frankenstein | **5.4 Internal States**, author archive dates release **1 September 2026**; accompanying **FF5 Regex 3.0** | Large current release discussion; independent recommendations; modular scene/world behavior | Dependencies and state management make full mode unsuitable as an unconfigured novice default |
| FF lightweight configurations | 5.2 Micro/BOLT/MAX; older standalone Micro remains recommended in 2026 | Baselines for decreasing complexity and token use | Do not assume all files named Micro are the same generation |
| FF forced reasoning / Marinara variants | 5.4 FR and agentic Marinara port | Evidence that provider behavior and frontend architecture change packaging | Native thinking and externally prompted reasoning must not be blindly combined |
| Evening-Truth | Live model-specific prompt index, edited **1 October 2026** | Short chat-completion prompts, explicit model distinctions and practical settings | Not a universal preset; author opinions and provider claims need independent checking |
| Pura's Director Preset | **16.0**, author site updated **28 September 2026** | Highly modular, actual downloadable ST JSON and documented toggles | Author taste is embedded; groups, macros, and optional extensions need inspection |

FF archive lists **6 Micro as COMING SOON**, not a released artifact. Do not recommend it as available. Archive includes dated older releases and separate FranKIMstein Kimi K2.5-era versions; their names alone establish no K3 compatibility. [S1]

## Freaky Frankenstein: what matters for this agent

FF5.4 release documents compulsory Regex 3.0, semi-strict alternating-role post-processing without tools, and disabling incomplete-sentence trimming. Its changes target distinct character vocabulary, user-agency mistakes, reduced stock therapeutic dialogue, and separate cinematic versus story prose. The author claims a 25% prompt-token reduction. These are release claims, not independent measurements. Download links are in the original release. [S2]

**Important incompatibility history:** FF5.2 initially advertised DeepSeek V4 Pro support, but its author added an **16 August** warning retracting that expectation after a model update. Its FR variant is explicitly for non-reasoning endpoints, with warnings about duplicate reasoning on native thinking models. Regex also affects retained context, rather than only presentation. [S3] FF5.4 still calls DeepSeek V4 performance inconsistent/provider-dependent. [S2]

Product implication: a starter pack requires an exact version + enabled modules + required regex + provider/model combination. Exporting only prose would lose behavior. The agent should be able to choose a lightweight configuration when a user wants conversation, and introduce simulation features only when wanted. Do not accept claims about time-of-day quantization, guaranteed cache percentages, or internal reasoning equivalence as established mechanisms.

The original MediaFire file is dated **1 September 2026, 01:20**, 140.66KB. Its actual JSON was inspected through the web retrieval service: `prompt_order` enables Main, Time/Place, Cinematic Realism and Hybrid POV, while Story Mode and individual first/second/third-person alternatives are disabled. Bundled `extensions.regex_scripts` includes prompt-only untagged-thought deletion and display transforms. Searches found no `temperature` or `openai_max` fields; sampler defaults should not be assumed from this file. Some prompt fields have their own enabled flags: resolve against `prompt_order`. Direct file download did not return valid JSON, so no raw asset was saved and no full parser/import validation is claimed. [S4, S14]

## Pura's Director Preset: source and actual-file observations

Author documentation describes a roughly 1,300-token main prompt and optional 600–700-token grounded-prose layer, with a simplified main alternative. It distinguishes full ST packaging from Neconyan agent-based packaging. Trackers are optional; formatting uses a Dialogue Colours macro that should be removed when its extension is absent. Randomisers can conflict, and optional prose voices encode specific styles rather than universally superior writing. The author recommends model-specific handling of the negative-instruction layer. These are useful design leads, not comparative proof. [S5]

The **actual 16.0 JSON** exposes context/output values of **256,000 / 32,000**, a disabled tool-reasoning setting, and logit-bias collections with **Default (none)** selected. Stored bias lists therefore must not be confused with active settings. It contains ST `setvar`/`getvar`/random macros and prompt injection metadata. Its group-chat nudge explicitly allows writing for the user, while the main prompt defaults to leaving user actions/dialogue to the user. This is a concrete conflict to resolve when promising agency preservation in group mode. The formatting module includes an English narrative-language instruction; localisation must change it. Its Gemini whitespace prefill carries a version restriction. [S6]

Product implication: parse actual enabled/order state; distinguish a stored option from a sent instruction; resolve macros; inspect group and continuation prompts as well as the headline main prompt. Never import large context/output limits as model-independent truth.

## Evening-Truth: current and useful for targeted setup

The index explicitly targets chat-completion APIs with basic samplers, short prompts, and version-specific wording. Its October update includes MiMo V2.6 and GLM5.3 pages; several older models remain listed. There is no Claude entry in the inspected index, and Kimi listings stop at K2.7 rather than K3. This is a **coverage gap**, not permission to relabel old prompts. [S7]

**MiMo V2.6 Pro:** the author's current page recommends output room above 5K, temperature 0.85–1, top-p 0.95, auto reasoning, no extra penalties/top-k/min-p, and provider-dependent processing (none versus merged/semi-strict) with squashed system messages. The same page questions whether sampler settings are hardcoded. Treat the numeric recommendations as proposed settings until checked against official endpoint support. Its prompt requests replies under 500 tokens despite larger generation allowance, showing the distinction between visible length and generation budget. It now links a JSON download at Illarin. [S8]

**GLM5.3:** author used Z.AI through OpenRouter and chat completion, recommends semi-strict without tools, 5K generation room, top-p 0.95, temperature 0.85–1 (possibly fixed at 1), and no penalties. Prompt structure covers roles, interaction, response constraints and post-history reminders; character knowledge and user agency are explicit. Claims about its training provenance are speculation, not evidence. [S9]

**DeepSeek V4:** a dated log accompanies base versus friction-enhanced prompts, with different intended character flexibility. The page recommends semi-strict/strict and squashed system messages; claims fixed samplers. It describes changes over time and provider differences. These cannot be transferred automatically to both Pro and Flash or treated as verified API facts. [S10]

The author's **Narrative Guide** argues for excluding unwanted tropes after a GLM4.7 character repeatedly slipped into an unwanted archetype. This is direct counterevidence to a universal "never use negative instructions" rule, but remains an author experiment on a specific model. Prefer testing semantic behavior, not merely prohibited words. [S11]

## Popularity, novice friction and alternatives

A **22 June 2026 independent favourites thread** repeatedly mentions FF Micro, Evening-Truth and Pura. Users also recommend Marinara, Chatfill II, Realistic Frankenstein, Kitty Lotus, Lucid Loom and Megumin Engine. Responses differ by scene and model; some users report deterioration in group chats and switching presets as context grows. This supports a candidate list and multiple starter profiles, not a universal winner. [S12]

A **16 June help thread** shows users unable to find Evening-Truth JSON, confused about Main/Post-History placement and accidentally using Text Completion. Current MiMo/GLM author pages now link JSON, so the old absence is not a current universal fact. Still, the thread directly supports bundling settings and hiding frontend jargon from novices. [S13]

## Reuse and outstanding work

Preserve author identity, original URL, retrieval date, version and modification diff. No explicit redistribution terms were found on the three inspected author index pages. Record that as an unresolved metadata field; it does not prevent comparing the sources or preparing attributed prototype modifications. This research report contains descriptions, not copied full preset text. GitHub-hosted Pura assets were inspected, but repository history/license retrieval failed; do not claim a GitHub commit audit.

Before shipping starter artifacts: download and fully parse FF JSON/regex, verify exact current APIs for every target model, resolve enabled-state conflicts, record dependency behavior, and run the agreed model-specific comparisons. The researched shortlist is ready; runtime quality and import round-trips remain untested.

## Source register

All accessed 2026-10-03. Author sources establish their instructions/claims; Reddit user statements are anecdotal.

- S1 — FF author archive, 5.4 release dated 2026-09-01; 6 Micro forthcoming: https://rentry.org/freaky-frankenstein-presets
- S2 — FF5.4 original release and current comments: https://www.reddit.com/r/SillyTavernAI/comments/1w49lyx/preset_update_freaky_frankenstein_54_the_second/
- S3 — FF5.2 original release, 2026-08-12, correction 2026-08-16: https://www.reddit.com/r/SillyTavernAI/comments/1vmc07f/preset_update_freaky_frankenstein_52_the_first/
- S4 — FF5.4 original download landing page: https://www.mediafire.com/file/9f70q840092j5lr/Freaky_Frankenstein_5.4_Internal_States_%25282%2529.json/file
- S5 — Pura author documentation, header update 2026-09-28: https://platberlitz.github.io/
- S6 — Pura actual ST16 JSON: https://platberlitz.github.io/preset/Pura%27s%20Director%20Preset%2016.0%20%28SillyTavern%29.json
- S7 — Evening-Truth index, published 2026-03-21, edited 2026-10-01: https://rentry.org/Evening-Truth-Roleplay-Prompts
- S8 — MiMo2.6 author prompt/settings: https://rentry.org/Evening-Truth-Xiaomi-MiMo-V26
- S9 — GLM5.3 author prompt/settings: https://rentry.org/evening-truth-glm-53-flash
- S10 — DeepSeek V4 author prompt/settings, dated update log: https://rentry.org/Evening-Truth-deepseek-v4
- S11 — Narrative Guide, published 2026-04-15, edited 2026-05-12: https://rentry.org/Evening-Truth-Narrative-Guide
- S12 — Independent favourites thread, 2026-06-22: https://www.reddit.com/r/SillyTavernAI/comments/1ucc8d2/favorite_presets/
- S13 — Evening-Truth import help thread, 2026-06-16: https://www.reddit.com/r/SillyTavernAI/comments/1u7ch3q/anyone_knows_where_i_can_download_eveningtruths/

- S14 — Actual FF5.4 JSON: follow **Download (140.66KB)** from S4 (temporary signed MediaFire URL); web reference `turn50view0` / `turn51view0`. No raw file retained.
