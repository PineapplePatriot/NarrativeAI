# Adaptive taste elicitation: evidence audit and implementable guide

Research checked 3 October 2026. This document separates verified research results from proposed product behavior. No RP-model generation experiments were performed in this research pass.

## 1. Corrections to the supplied research note

The cited papers exist and are relevant. The main problem is overgeneralization, rather than invented references. Replace “Negative instructions backfire, and the mechanism is now documented” with “Negative constraints can fail or produce rebound in studied settings; effectiveness must be tested on the selected model.” Negative instructions are a technique to evaluate, not a prohibited category.

| Source | Verified finding and practical limit |
|---|---|
| GATE, ICLR 2025 [S1] | LM-led open-ended questioning produced informative preference specifications. Tasks were content recommendation, moral reasoning, and email validation; gains were not uniform across tasks. Supports adaptive interviews as a design direction, not a demonstrated RP-onboarding success rate. |
| LiteraryTaste, 2025 preprint [S2] | 60 participants each evaluated 100 pairs. Reported 75.8% personal-preference prediction came from fine-tuning a transformer encoder. Self-reports had limited predictive utility in this setup. The number is not expected accuracy of a few-question onboarding agent, and reading preferences are not identical to interactive RP preferences. |
| PRELUDE/CIPHER, 2024 [S3] | Learns contextual, readable preferences from edits. The reported 31% summarization and 73% email edit-cost reductions are present in the paper's experimental results, primarily using GPT-4 simulated users. A small human evaluation also exists; describing the entire paper as simulation-only is incomplete. Its seven-evaluator summary comparison does not establish live RP performance. |
| Ironic Negation, 2025 preprint [S4] | Tests nine open models and varying distractors; circuit analysis uses Llama-3-8B-Instruct. Supports investigating token rebound and context interference. It does not test the requested Opus models and cannot prove that their negative instructions fail. |
| Semantic Gravity Wells, 2026 preprint [S5] | Studies Qwen2.5-7B-Instruct on constrained single-word completions, with 40,000 samples from 2,500 prompts. The author explicitly disclaims universality. Activation effects in this task are not evidence that a detailed modern RP preset should contain no prohibitions. |
| Suppressing Pink Elephants, 2024 [S6] | Direct Principle Feedback is a training method. A fine-tuned 13B Llama 2 model improved on the paper's controlled avoidance task. This is neither a chat-preset recipe nor proof that a hosted user can implement the same intervention. |
| Antislop, 2025 preprint, v1/v2 [S7] | Confirms the reported 8,000+ pattern stress test versus degradation from token banning around 2,000. Its sampler detects patterns, backtracks and resamples. The API implementation specifies a completion endpoint supporting top_logprobs and has substantial throughput costs. It is not a generally available chat-completion control. |

The original note's metaphor-substitution observation is useful project evidence, but should not be called the same experimentally established mechanism as these papers. “Ledger” becoming “transaction” demonstrates a surface-level fix leaving the unwanted semantic framing intact. That can happen even when the explicit word ban succeeds perfectly.

Similarly, “pairwise comparison is the cheapest way” is an untested product assumption. Cost includes generation, reading effort and latency. The right question is whether a comparison resolves a meaningful ambiguity more efficiently than one short question.

The supplied interview conclusions and Reddit snapshot remain project inputs, not independently revalidated evidence in this audit. Avoid claiming that all users naturally describe only dislikes. Invite both complaints and liked examples.

## 2. Product contract

The end user is a casual roleplayer, potentially arriving from Character.AI with minimal LLM knowledge. They should never need to name temperature, prompt roles, repetition penalties, reasoning budgets, regex, or “subtext density” to complete onboarding.

The chosen target model authors the preset and live calibration samples. If the user selected Opus 5.5, call that model for these tasks; do not silently replace it with a cheap drafting model. A service outage should preserve the work and offer retry or an explicitly chosen alternative. These are proposed runtime requirements, not claims that this research session accessed those models.

Store human preferences independently of model instructions. Switching models should reuse confirmed taste, retrieve the new model's verified construction rules, and run a small confirmation sample rather than restarting the interview.

One-click starter setups are an equally valid entry. A user can select a model-specific ready-made setup, start immediately, and later describe a single dissatisfaction. The assistant then performs focused diagnosis instead of forcing the full questionnaire.

## 3. Preference record and decision policy

Each inferred preference needs these fields:

- Human wording and short plain-language interpretation.
- Scope: general writing taste, current scene, character, relationship, or content boundary.
- Evidence: explicit statement, pair selection, highlighted passage, direct edit, or later correction.
- Status: tentative, confirmed, superseded, or conflicting.
- Strength: firm requirement or flexible preference.
- Applicability: context in which it should activate.
- Model implementation: generated separately with exact model/provider/settings version.

Example: “He wouldn't confess that so easily” initially belongs to this character in this scene. Do not infer “the user dislikes introspection everywhere.” Ask “Should he stay guarded here, or do you generally prefer feelings to show through actions?” only if that distinction affects the next draft.

Select the next question from the highest-impact uncertainty. Ask when the answer is likely to change a prompt component or next sample. Skip questions already answered by reliable evidence. Keep a user-facing “ready to try” exit after an initial useful draft; reaching an arbitrary confidence score is not a prerequisite.

Numerical confidence can aid internal bookkeeping, but must not imply statistically calibrated probabilities unless evaluated. A simple tentative/confirmed distinction is sufficient initially.

## 4. Stage 1: base questions

Ask a small set in ordinary language, progressively. Proposed starting set:

1. “Which model would you like to use?” Include a short recommended-model route for users who do not know; recommendations come from the separately maintained model research.
2. “What language should the characters use?” Ask about mixed-language dialogue only if relevant.
3. “How much do you like reading before your next turn?” Show compact visual lengths such as a few lines, a few paragraphs, or a long reply; let samples calibrate the exact target.
4. “What sort of scene would you enjoy trying?” Let the user supply their own character or choose a neutral test scene.
5. “Anything you want kept out, or any content preferences we should know?” Boundaries should be stored separately from literary style.
6. “What usually makes you reroll a reply?” Optional; also accept “I don't know yet.”

Dramatic intensity can use everyday phrasing: “Quiet and believable, heightened and theatrical, or somewhere between?” This sets a tentative starting point, not a permanent global rule. Model type is a setup choice; users do not need architecture vocabulary.

## 5. Stage 2: adaptive A/B comparisons

Most comparisons should be generated live by the chosen model. Prewritten examples can explain a distinction, but cannot demonstrate that the selected model and assembled settings can reproduce it.

Use the same scene, character facts, perspective and approximate length. Change one main dimension where feasible. Avoid deliberately making one option clumsy: both should be plausible writing that different people might like. Randomize the displayed order and record which variant was shown on each side.

Always offer: A, B, parts of both, neither, no preference, and direct editing. Ask for a reason only where it resolves ambiguity. A user may like B because of a single line rather than the experimental dimension.

| Ambiguous cue | Useful live contrast | Follow-up in everyday language |
|---|---|---|
| “More emotional” | Feelings named directly versus revealed by speech and action | “Did you like knowing what he felt, or how his behavior gave it away?” |
| “More atmospheric” | Sensory setting detail versus tension communicated through pacing | “Was it the surroundings or the feeling that something was about to happen?” |
| “Less robotic” | More varied rhythm versus more character-specific intent | “Was the wording stiff, or did it feel like anyone could have said it?” |
| “More possessive” | Attentive, restrained jealousy versus overt territorial dialogue | “Which behavior fits this character, and which part felt overdone?” |
| “Let the character do things” | An action that invites a response versus multiple resolved events | “Is this enough initiative while still leaving you a turn?” |
| “Less narration” | Similar scene with less explanation versus less physical description | “Which part do you want less of: explaining feelings, describing actions, or both?” |

Do not equate more dialogue with more agency, short replies with fast plot, or elaborate prose with emotional depth. These dimensions can vary independently. If a comparison changes several dimensions, log the choice as a holistic preference and use a focused follow-up before extracting a narrow rule.

Question wording stays human-friendly across models. What changes with model choice is the generator prompt, supported settings, known failure probes, and whether to use concise rules, examples, or modular instructions. A model's common weaknesses should guide useful tests without forcing its users into one taste category.

## 6. Stage 3: optional liked writing

Invite a short excerpt the user owns or is able to share, or ask them to highlight a liked part of a generated reply. Ask “What do you like here?” but allow “I'm not sure.” Offer two or three tentative observations, not a literary essay.

Separate transferable craft from content: voice, sentence rhythm, emotional disclosure, detail selection, dialogue purpose, scene progression, and room for the user's action. Character identity and plot events stay with the example unless deliberately requested.

Create a new scene that implements the inferred features without reproducing distinctive lines. Ask whether it carries the same appeal. One liked excerpt is not permission to apply every detectable feature everywhere. A user can like tenderness in one passage and hostile banter in another.

Keep examples available as evidence, while including only the amount of example text justified by the chosen model's guide. “Never use examples verbatim” is too absolute; an authorized short example can be an effective steering component. The decision should consider copying risk, prompt cost and observed benefit.

## 7. Stage 4: drafting and feedback loop

Generate a short continuation with the current candidate setup. Collect reactions through highlighting, editing, a free response, or simple controls: keep this, too much, too little, wrong for the character, wrong direction, try another version.

Before adding instructions, inspect the current preset, character card and examples for contradictory causes. A prompt that repeatedly demands exhaustive emotional explanation cannot be repaired reliably with an ever-longer “no therapy language” list.

Translate complaints cautiously:

| Complaint | Candidate interpretation and next action |
|---|---|
| “They keep recapping” | Test a continuation that assumes shared events are known; check whether the user instead needs less narrator summary. |
| “He sounds like a therapist” | Test less explicit self-analysis for this character; do not impose silence on every character. |
| “I banned ledger and got transaction” | Revise the relationship's framing, not merely the vocabulary; test for semantically equivalent clichés. |
| “It decides everything for me” | Identify whether the model wrote the user's actions, resolved the encounter, or skipped too far ahead. These need different changes. |
| “Nothing happens” | Test a concrete character initiative that leaves the user's reaction open. Do not simply increase randomness. |

Interpret edits as evidence, not unambiguous labels. A deletion can fix length, canon, repetition or mood. A reroll alone has low diagnostic value: it can mean exploration, dissatisfaction, or curiosity. Do not silently update long-term taste from every reroll.

Keep one accepted version as an anchor. Revise the smallest relevant part, show another sample, and preserve unrelated preferences. Stop when the user is satisfied; offer future adjustment during ordinary use. Briefly ask whether an inferred rule is “for this scene” or “usually” when its scope matters.

## 8. Stages 5–6: assembly, test and export

Assemble from current, attributable preset components whose model compatibility is documented. The target model edits the combined instruction set. Remove duplicates, reconcile contradictions, and ensure optional modules are genuinely off when excluded. Record source versions and modifications.

Negative constraints are allowed when useful. Compare baseline, positive target, concise negative constraint, and combined instruction where evidence is uncertain. Measure both literal compliance and semantic substitution. Keep successful concise prohibitions rather than automatically expanding them into verbose explanations.

Separate model-level sampler settings from user taste. The agent should only emit parameters verified for that provider and endpoint. Antislop backtracking is an optional future capability, not a requirement of the chat-completion MVP. Output regex that deletes a phrase is not equivalent to changing what the model generated and can damage meaning.

Run the actual assembled preset through the actual selected endpoint with the test character, without hidden drafting-only coaching. Confirm the approved behavior on a fresh continuation and a different scene. Test a longer interaction to detect accumulating repetition, prompt drift and loss of turn-taking. Preserve the request settings and model ID so the result is reproducible in configuration, even though sampled text varies.

Handover includes the preset, supported connection profile, test character, readable taste summary, model/provider/version metadata, source attribution and supported import/export formats. Never export API secrets. An import test should establish that enabled prompts, ordering and supported settings survive the round trip. Settings that cannot transfer need a clear fallback or short explicit setup instruction.

## 9. Evaluation and acceptance criteria

Compare minimal baseline, researched one-click setup and personalized setup under matched scenes and model/provider settings. Randomize pair order and include repeated generations; otherwise a lucky sample can decide the result.

Measure user preference, character fit, scene progression, user agency, emotional fit, unwanted repetition, and ability to make a satisfying next move. Keep time-to-first-satisfying-sample and onboarding abandonment alongside quality. Distinguish corrective edits from enjoyable creative edits.

Initial acceptance criteria: a novice finishes without editing technical controls; the selected model generates both preset and samples; every inferred global preference has explicit or repeated evidence; unsupported settings are excluded; the finished setup reproduces the approved direction; export/import preserves supported behavior; users can inspect, undo and revise learned preferences.

This is a testable product proposal informed by adjacent research. It is not a claim that the published studies already validate the complete six-stage RP workflow.

## Sources

- [S1] Li et al., Eliciting Human Preferences with Language Models, ICLR 2025: https://proceedings.iclr.cc/paper_files/paper/2025/hash/c9867d5a22653ce98b02595061e40f12-Abstract-Conference.html
- [S2] Chung et al., LiteraryTaste, preprint: https://arxiv.org/abs/2511.09310
- [S3] Gao et al., Aligning LLM Agents by Learning Latent Preference from User Edits, v3: https://arxiv.org/html/2404.15269v3
- [S4] Mann et al., Don't Think of the White Bear, preprint: https://arxiv.org/html/2511.12381v1
- [S5] Rana, Semantic Gravity Wells, preprint: https://arxiv.org/html/2601.08070v1
- [S6] Castricato et al., Suppressing Pink Elephants with Direct Principle Feedback: https://arxiv.org/abs/2402.07896
- [S7] Paech et al., Antislop: https://arxiv.org/pdf/2510.15061v1 and https://arxiv.org/html/2510.15061v2
