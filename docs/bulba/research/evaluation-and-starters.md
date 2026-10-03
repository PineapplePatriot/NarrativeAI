# Starter setups and evaluation protocol

Status: design specification, not a claim of tested model performance. 2026-10-03.

## Starter collection

Begin with three experiences per verified compatible model; avoid multiplying presets into dozens of indistinguishable options. Labels below are product proposals, not community preset names.

| Starter | Intended experience | Configuration intent | Key check |
| --- | --- | --- | --- |
| Back-and-forth | Shorter character exchanges with an obvious opening to respond | Preserve character voice and user agency; limited action per turn; flexible length | Does it avoid answering for the user without ending every reply in a question? |
| Rich scene | More atmosphere, subtext, and room for emotion | Add relevant detail and interiority where consistent with POV; preserve forward movement | Does detail enrich the scene without recap, forced symbolism or therapy speeches? |
| Director seat | User guides the cast and reads a fuller scene | Explicit permission boundaries for writing the cast; appropriate scene progression | Does the system follow direction without confusing OOC instructions with canon? |

Use research-shortlisted community bases as candidate implementations. The same display label may use a different base, prompt length and settings on each model. Content preference is separate from prose style; choosing a style should not covertly force romance, sexual content, hostility or constant danger.

A starter record needs exact model/provider identity, source preset version, enabled components, dependency manifest, parameter support evidence, test character, sample, export mapping, last validation date, and limitations. Where author licensing is unresolved, link and inspect the original rather than represent redistribution permission as established.

One-click means one click to apply a complete setup after account/connection access exists. It cannot create access to a paid model from nothing. For the eventual product's managed endpoint, authentication can already be handled by the app.

## Model validation ladder

1. Verify metadata and payload: correct exact model, supported parameters, no unresolved macros, no contradictory modes, no credentials in export.
2. Import/export round trip: compare normalized enabled prompts, order, roles, settings and dependencies. Record anything not preserved. A native JSON schema is not proof of ST import compatibility.
3. Endpoint smoke test: confirm accepted payload and actual served model/provider, finish reason, visible output, reasoning/output token allocation and usage. Not performed in this research package.
4. Writing evaluation: compare minimal baseline, unchanged curated starter, and personalised configuration on matched scenes. Not performed in this research package.

## Practical pilot design

Proposed small engineering pilot: six scene types, three generations per condition, three conditions, for 54 outputs per model. This is a screening budget, not a powered scientific study. Begin with one chosen primary model, fix failures, then expand to the remaining requested models. Do not infer statistical superiority from this sample.

Scene types: everyday banter; restrained emotional conflict; nonromantic teamwork; action with a clear handoff; a disclosure involving asymmetric knowledge; a longer conversation resumed with memory. Include short and long user turns. For director mode, replace user-agency scoring with adherence to the permission granted to write the cast.

Keep model, provider route, card, history and supported settings fixed when testing prompt changes. Evaluate sampler changes separately to identify their contribution. Record every response, not just the best. Use fresh generations for the final configuration, not the same examples used during calibration.

For taste fit, the user is the primary judge. Blind and randomize the presentation when possible. Ask for preference plus a reason and offer ties/neither. An automatic judge may flag factual continuity or format errors, but it should not define an objective ideal prose style.

## Scorecard

| Dimension | Concrete evidence |
| --- | --- |
| Taste fit | Which reply the user would keep; why |
| Character fidelity | Distinctive voice and behavior consistent with the supplied card |
| Agency | No unrequested control of the user's decisions or inner state |
| Subtext/register | Emotional expression and humor appropriate to the scene |
| Continuity | Correct speaker, knowledge, events, objects and relationships |
| Repetition | Recap, echoed phrases, repeated reply shapes and semantic substitutions |
| Pacing/handoff | A useful opening for the user; no gratuitous plot escalation |
| Configuration reliability | Accepted fields, route stability and exported behavior |
| Usability | Time to first acceptable setup, abandoned onboarding, assistance needed |

Separate corrections from creative edits. A swipe may mean exploration rather than failure. Ask the user which it was on a small sample, rather than inferring dissatisfaction from every regeneration.

## Promotion and refresh rules

A candidate becomes a product default only after endpoint and export checks pass and users find it acceptable in its intended use. Label the tested model/version/provider and date. A model release, alias change, preset update or provider behavior change triggers targeted revalidation. Preserve the old preset version so users can roll back. Monthly source review is a proposed maintenance interval, not an automation created by this task.

## Research-stage completion boundary

This package provides evidence and implementation materials. Live paid calls, novice user trials, a running onboarding agent and production ST adapters require the application and model access. Their absence must remain visible; no research recommendation is described as an experimentally validated setup.
