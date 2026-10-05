# NarrativeAI: research findings and build decisions

3 October 2026 · research package v0.1

## What is ready

The package now provides a current preset shortlist, exact-model configuration research, an audit of the preference-elicitation evidence, an adaptive interview guide, draft agent operating instructions, starter-setup designs, a native export schema, a neutral test card, and SillyTavern adapter requirements. Four parallel research tracks contributed source-backed reports.

No paid model calls or user experiments were performed. Preset quality recommendations are candidates for testing, not measured winners. The draft agent and native schema are implementation materials; they are not a deployed product or verified SillyTavern importer.

## 1. Start from these current bases

| Candidate | Evidence of currency | Best initial use | What must travel with it |
| --- | --- | --- | --- |
| Freaky Frankenstein 5.4 | September release, current author archive and release discussion | Richer modular scene behavior; inspect a lightweight configuration first for conversational users | Exact enabled prompts, regex suite, role post-processing and mode choices |
| FF Micro configurations | Continued recommendations in a June 2026 independent favourites thread | Lower-complexity baseline and comparison against larger variants | Exact file/version, since standalone Micro and flagship Micro modes differ |
| Evening-Truth model-specific prompts | Index updated October 1; current MiMo2.6 and GLM5.3 guidance | Concise targeted bases for those models | Main/post-history placement, provider-compatible settings and selected formatting |
| Pura Director16.0 | Author page updated September28; actual JSON inspected | Modular narration, turn-taking, director options | Macro handling, enabled/order state, selected modes and optional dependencies |

These candidates have current sources and community visibility. That does not establish a market-wide popularity ranking or reliable superiority. The detailed preset report includes contrary experiences and secondary leads. Older artifacts enter the shortlist only with current evidence of use; unreleased FF6 Micro is excluded.

The project should curate an intact compatible base first and adapt it incrementally. Combining attractive fragments from different presets can introduce contradictions or destroy their dependencies. Pura's actual file, for example, needs localisation and inspection of group-mode agency rules. FF has operational dependencies beyond the prompt text. Evening-Truth's current index does not cover all requested newer models, so an old Kimi prompt must not be relabelled K3.

## 2. Settings depend on exact model, mode and provider

The model guide covers every requested model, including exact IDs and source links. The most consequential documented distinctions are:

- Later Claude versions in the requested set restrict direct-API sampling. Opus4.6 differs, particularly when thinking is disabled. Treat provider compatibility as a capability record, not an inherited family default.
- KimiK3 has fixed samplers and mandatory reasoning. MiMo2.6Pro fixes sampling during thinking, while its other mode exposes controls. GLM5.3 exposes sampling controls despite mandatory reasoning.
- Gemini3.8Flash has model-specific thinking levels; old Gemini prefill recipes require rechecking.
- Direct DeepSeek's legacy V4Flash alias now resolves to V4.1Flash. OpenRouter still catalogues an original V4Flash route; pin and verify the provider/version for exact comparisons. V4Pro is retained in current documentation despite an earlier retirement announcement.

The capability layer should decide which settings the agent may emit. A setting appearing in an ST preset or OpenAI-compatible request is not proof that an endpoint uses it. Avoid fake user-facing creativity controls when the chosen model does not support their underlying parameter.

Your observations about Opus5.5's short-preset performance and useful negative constraints remain valuable, explicitly recorded hypotheses. The public sources checked do not establish an optimal RP prompt length for it. Use a short candidate first, then test whether additional components help the user's scene.

## 3. Keep negative constraints as a tool

The research note's references are real, but several conclusions need narrower wording. Negative constraints can produce rebound in studied tasks. The studies do not show that every modern hosted model mishandles them, or that every prohibition should be rewritten positively.

The audit distinguishes constrained single-word tests, open-model circuit experiments, a training-level avoidance method, and a backtracking sampler. None constitutes a universal recipe for this chat-completion product. Antislop's sampler is not a generally available hosted chat control.

Literal compliance and semantic correction are separate outcomes. A model can obey “do not say ledger” while retaining accounting metaphors. Diagnose the undesirable decision, test a concise semantic instruction, and check for substitutions. Keep a successful negative rule when it works; do not automatically replace it with a longer positive passage.

## 4. Ask about concrete writing, adapt after each answer

Preserve the supplied six-stage flow. Base questions establish enough context to generate a useful sample. The selected model produces most comparisons live. Optional favourite writing supplies evidence. Draft feedback refines the candidate. Assembly reconciles components and settings. Handover tests and exports the final setup.

The agent should choose the next question because its answer will change a meaningful instruction or sample. It should not work through a fixed batch after the user's answers have already resolved those issues.

Pairs should keep scene, character and approximate length comparable, changing primarily the disputed feature. Allow both, neither, mixed preferences, no preference and direct edits. A choice does not identify why the user preferred it without adequate follow-up.

Separate taste from its implementation. “More emotional” may mean more explicit thought, more visible behavior, or stronger conflict. “Possessive” may mean attentive restraint rather than territorial speeches. More dialogue does not inherently mean more agency. Record uncertain interpretations, preserve original wording and ask about scope when necessary.

LiteraryTaste supports taking observed choices seriously, but its reported prediction result is not an onboarding-agent accuracy estimate. GATE and CIPHER support adaptive elicitation and learning from edits in adjacent tasks; the full RP workflow still needs its own evaluation.

## 5. The selected model authors the setup

If the user chooses Opus5.5, that model writes the preset and live calibration. Enforce routing in application code, record the actual served model, and avoid a silent cheap-model fallback. The operating-instructions draft describes how this constraint interacts with question selection, diagnosis, component assembly and handover.

After assembly, generate a fresh passage using the finished exported instructions and actual supported settings. An excellent onboarding sample produced with hidden extra coaching is not evidence that the final setup will behave the same way.

## 6. Quick start and export are first-class routes

The starter specification proposes three understandable experiences: Back-and-forth, Rich scene, and Director seat. Their names describe what users get, while each model can use a different researched implementation. Users may start without an interview and later ask for one specific adjustment.

Native export preserves the complete setup and provenance. SillyTavern export requires an adapter preserving definitions, activation/order, marker semantics, macros and required assets. Connection profiles reference other configurations; a profile alone is not the whole setup. Explicitly remove credentials and local secret bindings.

The included native schema is a proposal for our application. It intentionally is not presented as a valid ST preset. The neutral character fixture supports testing voice, agency and knowledge boundaries; its JSON structure was checked, but ST import has not been run.

## 7. Build sequence from here

1. Implement the exact-model capability registry and enforce target-model authoring.
2. Curate one lightweight base per primary model, using the shortlist and recorded coverage gaps.
3. Implement preference state and one-question-at-a-time calibration using `agent-instructions.md`.
4. Implement native export, then a pinned ST adapter with explicit conversion limits.
5. Run endpoint/import checks and a small matched-scene pilot before promoting starter defaults.
6. Add the remaining model/experience combinations once the initial path works.

All six steps are implementation work following this research deliverable. The package supplies requirements and test criteria rather than implying they have already been completed.
