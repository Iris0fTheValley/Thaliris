# T4 external benchmark survey

This is a benchmark-design survey, not a claim that Thaliris has been
evaluated on every benchmark below.  The selection criterion is whether a
benchmark exposes a large, discardable investigation working set while
preserving a bounded, testable decision boundary.

| Benchmark | Relevant mechanism | Candidate task quality | Reproducibility | Evaluator quality | Thaliris use |
| --- | --- | --- | --- | --- | --- |
| [SWE-EVO](https://github.com/SWE-EVO/SWE-EVO) | Versioned histories and high-level software requirements; multi-step, long-horizon work on large repositories. | High for T3/T4: realistic investigation volume and cross-version context. | Medium: public data and scaffolds, but long runs are expensive. | High when the supplied tests apply. | Primary source for noisy, history-sensitive candidates; retain only tasks with a narrow final patch. |
| [SWE-bench-Live](https://github.com/microsoft/SWE-bench-Live) | Continuously updated, multi-language/multi-OS tasks, automated curation, and executable Docker sandboxes; rollout sees the problem statement and task image rather than hidden evaluator hints. | High: broad candidate pool and explicit task metadata. | High for Python/Linux subsets; Windows and multi-language images add cost. | High: FAIL_TO_PASS/PASS_TO_PASS tests and reproducible task images. | First screener source and current xarray candidate source. |
| [SWE-rebench V2](https://github.com/SWE-rebench/SWE-rebench-V2) and its [paper](https://arxiv.org/abs/2602.23866) | Dataset builder/evaluator, interactive setup-agent filtering, Dockerfile generation, and scripted golden evaluation. | High: useful for filtering out visible-solution or unstable tasks before model runs. | High when the image builds; setup-agent generation is an additional cost. | High: task-level Docker evaluation and golden patches. | Secondary candidate source and reproducibility cross-check. |
| [SWE-Lancer](https://openai.com/index/swe-lancer/) with the [official eval repo](https://github.com/openai/frontier-evals/blob/main/project/swelancer/README.md) | End-to-end freelance engineering tasks plus managerial proposal selection; engineer-verified tests and a public offline Diamond subset. | High but heterogeneous; managerial tasks are not directly comparable to code repair. | Medium: task images are large and time-consuming, while the offline subset is narrower. | High for independent engineering tasks; mixed for managerial judgment. | Optional external validity check after a coding T4 is established, not the first screener. |
| [Dasein Code-Compression Bench](https://github.com/daseinlabs/code-compression-bench) | Fixed agent/model/grader with only the compression/context layer varied; cache-aware cost per solved task. | High for measuring context/token economics, not for discovering new bug classes. | High: fixed headless agent, official Docker grader, and reproduce commands. | High for SWE-bench Verified tasks. | Adopt its cache-aware accounting discipline; do not treat cached input as free. |
| [Letta Recovery-Bench](https://github.com/letta-ai/recovery-bench) | Replays failed commands in a fresh corrupted Docker environment and compares full/summary/none message histories. | High for context recovery/ablation, not ordinary bug fixing. | High: shared failure set and Docker replay. | High for recovery-rate comparison. | Optional independent probe for bounded packet versus raw trajectory. |
| [SliceAgent](https://github.com/TT-Wang/sliceagent) | Bounded deterministic slices, task-elastic focus, history-bounded cost, and live-state recovery. | Medium: mechanism is close to Thaliris, but task mix and claims are project-controlled. | Medium: public code, but reported savings are not an independent replication. | Medium: use as a mechanism reference, not an evaluator baseline. | Inform packet-size and recovery measurements; do not use its headline numbers as evidence. |
| [Magentic-One](https://www.microsoft.com/en-us/research/articles/magentic-one-a-generalist-multi-agent-system-for-solving-complex-tasks/?lang=ko-kr) | Orchestrator plans, tracks, and replans across specialist agents; AutoGenBench uses repetition/isolation controls. | Medium for routing studies; tasks are general and often tool-heavy. | Medium/high for the published harness. | Medium/high depending on task family. | Method reference for routing controls, not a direct Thaliris task source. |
| [LongMemEval-V2](https://github.com/xiaowu0162/LongMemEval-V2) | Long trajectories/haystacks, compact evidence retrieval, and accuracy/latency frontiers across memory abilities. | Medium for memory/context isolation; low for code repair. | High for the public question set, but not a repository fixture. | High for question-answer scoring. | Auxiliary packet-recovery/context ablation only. |
| LoCoMo (conversation-memory benchmark) | Multi-turn conversations and QA categories test temporal and multi-session memory. | Low for code investigation. | Medium; canonical packaging is less uniform than the coding benchmarks. | Medium for QA but not patch correctness. | Do not use for the primary T4. |
| [GAIA](https://huggingface.co/gaia-benchmark) | Tool-using, attachment-bearing general questions with deterministic answer matching. | Low for code-repair context isolation. | Medium: external tools and attachments vary. | High for exact answers, low for patch scope. | Auxiliary only if a non-coding tool-control probe is needed. |
| [WebArena](https://github.com/web-arena-x/webarena) | Self-hosted web environments and long-horizon browser tasks. | Low for repository investigation. | Medium/high with local services, but expensive. | High for task-specific web checks. | Out of scope for T4; no code-repair isolation signal. |

## Method conclusions

1. SWE-bench-Live is the best first source because its task image/problem
   statement boundary is explicit and its Python subset is reproducible on the
   current host. SWE-EVO and SWE-rebench V2 are the best follow-up sources for
   long-horizon/history-sensitive candidates.
2. Dasein supplies the accounting rule we need: report cached and uncached
   input separately and use cost-per-solved-task style comparisons rather than
   declaring cached tokens free.
3. Recovery-Bench and SliceAgent motivate an independent ablation of full
   trajectory versus bounded packet versus no history. That ablation is not a
   substitute for a real Sol-needed coding task.
4. The first T4 must be selected by observed A-lite/B-lite separation. A task
   with both models passing is a valid negative result, not evidence that the
   architecture is unnecessary.
