# NarrativeAI preset-agent research package

Prepared 3 October 2026. Version 0.1: source-backed research and implementation drafts.

Start with `research-summary.md`, then consult the detailed reports. The package combines current community evidence, provider documentation, an audit of the supplied preference-elicitation research, and proposed operating materials for the agent. It is a research deliverable; live model generation, endpoint smoke tests, and SillyTavern import round trips have not been performed.

## Contents

- `01-current-presets.md`: current versions, community evidence, dependencies and candidate bases.
- `02-model-guides.md`: exact requested model identities and endpoint-specific controls.
- `03-taste-elicitation.md`: research audit, adaptive questions, examples and decision rules.
- `04-sillytavern-integration.md`: current source-code/documentation findings and adapter requirements.
- `agent-instructions.md`: reusable draft operating instructions for the onboarding/preset agent.
- `evaluation-and-starters.md`: one-click setup designs and a practical validation protocol.
- `native-setup.schema.json`: proposed NarrativeAI export contract, not a SillyTavern preset format.
- `test-character.json`: neutral character-card fixture for testing turn-taking, voice and knowledge boundaries.
- `source-register.md`: deduplicated source links collected from the reports.

## Decisions preserved from Anya's brief

Audience: technically inexperienced roleplayers, including Character.AI casuals. Chat completion is the priority. Guided onboarding is optional; ready-made complete setups are equally valid. Presets, supported samplers and connection settings travel together. Export is required. The chosen model writes its preset and live comparisons; runtime routing must enforce this. Model-specific constraints override generic prompting folklore. Existing community bases can be adapted for this university prototype with attribution and source tracking.

Primary models: Claude Opus 5.5, Opus 4.6, Fable 5.1, Kimi K3, MiMo v2.6 Pro, Gemini 3.8 Flash. Additional: Opus 4.7, GLM 5.3, DeepSeek V4 Pro and Flash. Exact versions and aliases must be checked when connecting.

The workflow is preserved: base questions → adaptive comparisons → optional own writing → drafting loop → assembly → handover. A fresh test of the finished assembled setup belongs before final handover.

## Evidence policy

Official documentation supports request compatibility. Author pages establish intended settings and design choices. Reddit reports supply useful experiences and counterexamples, not controlled rankings. Papers support adjacent elicitation methods with task/model-specific limitations. Product rules and starter designs are proposals until evaluated. Where direct inspection was incomplete, the detailed report names the gap.

The two supplied context MDs were used as inputs and have not been overwritten. Source assets may contain third-party material; original sources and versions remain authoritative.
