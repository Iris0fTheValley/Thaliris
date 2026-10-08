# Runtime prompt ownership

Runtime prompts are part of the working context. Context quality is not its quantity:
the goal is dense, low-noise evidence for high-capability reasoning without losing
necessary invariants. Each invariant should have one authoritative normal expression
and a meaningful boundary, rather than an old rule followed by overrides/exceptions.

| Layer | Runtime responsibility | Canonical source |
| --- | --- | --- |
| Codex global/project | Cross-role authority/isolation boundaries, one-shot startup entry and canonical procedure pointers | `_global_agents_block()` and `render_managed()` in the Codex adapter |
| Codex Controller bootstrap response | Resident normal orchestration delivered through already-required startup; exceptional recovery/maintenance retrieved only when needed | `controller_instructions.md` rendered by `codex_bootstrap.controller_guidance()` |
| Codex native role | Own responsibility/style/delegation/endpoint/output | `thaliris_codex.roles`; native TOMLs are generated |
| Core documents | Shared semantic explanation, rationale and protocol | Shared routing/role/task-authority documents |
| DSH native policy | User-editable Controller/role records, model/tool/context grants | `policy.mjs`, `role-templates.mjs`; bundle patch is generated |

Normal routing, decision-complete handoffs, evidence reuse, waiting, Focused convergence,
ordinary autonomous closure, acceptance/review selection and causal diagnosis stay
resident for Controller use through the normal bootstrap response, without another
procedure get or full Controller-routine injection into every fresh child. Rare
Host maintenance, exceptional recovery and historical
migration steps are retrieved on demand. Compare total normal task context and retrieval
cost with delivered quality; fewer prompt bytes alone do not establish savings.

Full mechanical design stays in protocol docs; runtime retains consequences the model
must act upon. Controller determines acceptance and handoff boundaries, not the executor's
implementation algorithm. Ordinary execution closes deterministic local loops. Focused
execution includes runtime feedback and revision until the core semantic candidate converges,
then releases that working context for fresh ordinary closure. Independent review uses evidence
against accepted criteria; lack of blockers alone is insufficient evidence.

Use a stable language per matrix/narrative and preserve established semantic islands where
translation loses meaning. Selective multilingual treatment optimizes representation; it is
not random switching or a claim that more languages improve every task.

## Research motivation and limits

These papers motivate design choices; they do not validate Thaliris or its compression ratios.
[Liu et al. (2024), Lost in the Middle](https://doi.org/10.1162/tacl_a_00638) examines positional
and structural context utilization. [Jiang et al. (2024), LongLLMLingua](https://doi.org/10.18653/v1/2024.acl-long.91)
reports information-density/efficiency and performance effects on its tested tasks.
[Mondshine, Paz-Argaman and Tsarfaty (2025), Beyond English](https://doi.org/10.18653/v1/2025.findings-naacl.73)
supports task-dependent language treatment; [Kim et al. (2025)](https://doi.org/10.18653/v1/2025.findings-emnlp.1215)
examines English-Korean language-specific nuances and knowledge cues, not a universal benefit.
[Park et al. (2026)](https://arxiv.org/abs/2606.19668) motivates caution about random switching
and anchoring. These supplied references are motivation, not newly reproduced experiments.
ABCD results remain historical evidence for their original setups; prompt normalization was
not benchmarked here, and byte/token estimates are sizing observations only.
