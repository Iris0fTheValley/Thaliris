# Thaliris

主仓库现在发布 Host 无关的 Core、共享语义文档和 ABCD 基准协议/历史证据。`thaliris-core` 提供 Host-neutral 记录与证据操作；Codex 原生集成位于 [Thaliris-codex](https://github.com/Iris0fTheValley/Thaliris-codex)，DSH 集成位于 [Thaliris-dsh](https://github.com/Iris0fTheValley/Thaliris-dsh)。Core 不安装 Host hooks，也不负责原生任务准入或角色执行。安装与 API 边界见 [分包说明](docs/host-neutral-packaging.md)。

[English](README.en.md)

一个轻量、Git 原生的 AI 编程上下文与编排层。


项目理念是通过选择必要事实、约束和证据，保护高能力模型在聚焦上下文中的有效推理。上下文质量不等于数量，运行时提示词本身也是工作上下文的一部分。

无关信息，竞争目标和历史轨迹越多，真正需要推理的信息越容易被稀释或干扰

注意力才是最贵资源（指的是最强模型在一个干净、聚焦的上下文中用于解决困难问题的有效认知预算）

`Thaliris` 帮助多代理编码工作流把正确的信息放入正确的推理上下文，同时避免把仓库变成 Agent Framework。

它管理的是信息进入推理路径的条件，而不是通用 Agent 生命周期；证据、freshness、memory 和 adapter 防护都只是在防止错误、过时、无关或角色不匹配的信息被错误传播。节省调用成本是结果之一，但不能以丢失必要上下文为代价。

它提供：

* 面向不同语义角色的共享指导文档；
* 由证据支撑的项目记忆；
* 瞬态任务状态；
* 调查与审查交接；
* freshness 跟踪；
* 里程碑状态；
* 保守路由；
* 确定性的验证与恢复。

使用 Codex adapter 时，Codex 是 runtime 和 Controller。无论使用何种 adapter，源代码、Git、测试、编译器和运行时行为仍然是 correctness core。

> **状态：** Beta。当前实现有意保持小巧，仍在真实编码工作负载上进行评估。

---

## 为什么要做这个项目

长时间的编码任务往往会不断积累上下文。

单个代理最终可能同时携带：

* 仓库探索；
* 失败的搜索路径；
* 实现细节；
* 测试输出；
* 调试轨迹；
* 架构推理；
* 审查标准；
* 旧决策；
* 无关的历史上下文。

更多上下文并不自动意味着更好的上下文。

对于强推理模型，更大的风险往往不是 token 的绝对数量，而是同一条推理轨迹中相互竞争的目标数量。

如果要求一个代理同时：

* 调查，
* 设计，
* 实现，
* 验证，
* 审查自己的设计，
* 记住此前的失败，
* 并满足一份庞大的流程检查清单，

那么它所解决的问题，已经不同于让代理根据必要证据专注回答一个推理问题。

`Thaliris` 建立在一个简单理念之上：

> **保留有用信息，但不强迫每个角色携带每一条信息。**

因此，本项目把上下文边界视为工程架构的一部分。

---

## 名字由来

Thaliris 由 Thalamus（丘脑） 与 Iris（虹膜） 组合而来。

丘脑负责筛选与路由进入认知系统的信息，虹膜调节进入视野的光量。Thaliris 借用这一意象来处理 Agent 上下文：控制什么进入推理路径，保留有依据的信息，并隔离彼此无关的工作集。

---

## 上下文与运行时契约

上下文质量不等于上下文数量。运行时提示词本身也是工作上下文的一部分：重复规则、无关历史和相互竞争的目标会稀释推理所需的证据。保留必要事实和硬不变量，同时为高能力模型提供信息密集、噪声较低的工作上下文。每项不变量在常规运行时提示词中只有一个权威表达，并有清晰边界；解释和历史背景放在文档中。选择性地使用多语言内容片段，以保留语言特有的含义并优化表达；目标不是随机切换语言或单纯增加语言种类。

正常 Controller 的路由、交接、证据复用、等待、终点、验收与因果诊断应直接常驻；异常恢复、Host 维护与历史迁移步骤按需检索。每个必要依赖有一个观察 owner：执行角色等待自己的测试、process 与 CI，Controller 等待必要 child 结果，不重复查同一作业。工具最长等待是 capacity，高层时长限制优先；成本评价包含正常任务上下文、检索重建与交付质量。

Controller 负责方向、范围、验收和后续路由，执行角色负责实现方案。决策完备的交接应复用已选择的证据和既有清单。普通 Implementer 负责收敛稳定方向；Focused Implementer 负责完整的推理、实现、运行时反馈和修订循环，直到核心语义收敛，然后把工作上下文释放给新的普通 Implementer 完成确定性收尾。Reviewer 独立且只读；关键验收需要支持证据。Core 记录机械事实，但不判定角色适用性或语义完成状态。

这些边界见[路由协议](docs/thaliris-routing-protocol.md)和[提示词归属与研究动机](docs/thaliris-prompt-design.md)。全局、项目及角色提示词的生成和原生运行时执行由 Host adapters 负责。ABCD 结果只适用于各自原有的实验设置；本次规范化没有经过基准测试，提示词变短也不能证明质量提升。

## 安装

Core CLI 需要 Python 3.11 或更高版本以及 Git。安装本仓库提供的 Host-neutral `thaliris-core` 命令：

```bash
uv tool install git+https://github.com/Iris0fTheValley/Thaliris
thaliris-core version
```

在现有 Git 仓库中初始化或检查 Core 记录：

```bash
cd your-repository
thaliris-core --root . init
thaliris-core --root . task-status
```

Core 安装和初始化不会安装或启用 Host hooks、生成 Codex profiles、启动 Agent、创建原生任务会话，也不证明当前 Host 已加载任何配置。需要 Codex 或 DSH 原生集成时，请按各自 adapter 指南安装并启动：[Codex](https://github.com/Iris0fTheValley/Thaliris-codex/blob/main/README.md) 与 [DSH](https://github.com/Iris0fTheValley/Thaliris-dsh)。Core/Host API 边界见[分包说明](docs/host-neutral-packaging.md)。

本地开发：

```bash
git clone https://github.com/Iris0fTheValley/Thaliris
cd Thaliris
uv run --extra test pytest
uv run thaliris-core version
```

---

## Core-only 快速开始

Core CLI 提供 Host-neutral 记录、显式检索、freshness 与里程碑操作。`task-status` 是有界路由观察；只有在明确需要诊断细节时才运行 `task-show`：

```bash
cd your-repository
thaliris-core --root . task-status
thaliris-core --root . task-show
thaliris-core --root . stale
thaliris-core --root . milestone-check
```

这些输出记录机械事实，不选择 Investigator、Implementer、Reviewer 等语义角色，也不决定任务是否在语义上完成或验收。Host adapter 与 Controller 负责原生准入、执行关联、路由和语义验收。

### 旧版 Codex `context` 命令示例

本文其他保留的 `context` 命令是旧版 Codex adapter 命令面，不能当作当前 Core CLI 使用说明。`context prepare`、`context recall`、`context doctor` 和 `context migrate` 不属于 Core CLI；旧版 `context init` 与 Host/Hook 设置也属于 Codex adapter。Core 中仍存在的机械记录操作需使用 `thaliris-core` 命令名及其参数。Adapter 提供的命令与实际启动/恢复流程见 [Codex 指南](https://github.com/Iris0fTheValley/Thaliris-codex/blob/main/README.md)。

---

## 仓库布局

初始化后，仓库中可能包含：

```text
AGENTS.md

.agent-memory/
├── INDEX.md
├── operator.md
├── prompt-policy.md
├── project-conventions.md
├── decisions/
│   ├── INDEX.md
│   └── ...
└── lessons/
    ├── INDEX.md
    └── ...

.milestones/
├── INDEX.md
└── M001-name/
    ├── INDEX.md
    ├── scope.md
    ├── decisions.md
    ├── progress.md
    └── verification.md

.context/
├── config.json
├── state.json
└── backups/
```

`.context/state.json` 是瞬态文件，Git 会忽略它。

项目记忆和里程碑文档由 Git 管理。

---

## 任务状态

Core 保存结构化事实和证据，而不是对话 transcript。它可验证记录字段、source freshness、provenance、CAS 和已选择持久意图的一致性；它不验证 Host actor 身份，不决定语义角色是否适用，也不作最终任务验收。Core CLI 的 `task-start` 只是记录操作；Codex/DSH adapter 才负责各自原生的准入与生命周期边界。

从概念上看，它分为：

```text
调查历史
    ↓
Curated 调查状态
    ↓
由 Controller promotion 的 Decision Context

Review findings
    ↓
相关时由 Controller promotion
```

典型的 Decision Context 包含：

* 已确认事实；
* 有支撑的证据；
* unknowns；
* contradictions；
* constraints；
* decisions；
* 相关文件与符号；
* 修改边界；
* verification target；
* architectural intent。

任务状态拒绝原始 transcript 和 tool-log 字段。

其目标是保留可追溯性，同时避免把 `.context/state.json` 变成第二份对话历史。语义记录具有稳定 ID 和显式状态转换；verification target 存在时，关闭任务需要受信 runtime observation 绑定当前 target、source identity 和 task surface。模型写下“测试通过”本身不是证明。

### 有界 durable promotion

task-end 的顺序是：`task-local state -> Controller 判断是否值得长期保留 -> 最小 durable promotion -> task-close`。这不是自动总结；没有 durable knowledge 就不写 durable 内容。只有 Controller 可以运行 `task-promote`，且只能提交显式的 `decision`、`invariant`、`failure_mode`、`constraint`，或当前 milestone 的 `progress`/`verification`。连续 feature 且有 current milestone 时，优先保留实际进度和验证到该 milestone；`.agent-memory/` 只保留跨任务可复用的 decision、constraint、invariant、failure mode。Repository task 除非用户明确要求，不主动读取或写入 `~/.codex/memories`、`MEMORY.md` 等个人/global Codex memory；项目连续性走 `.agent-memory/`、`.milestones/`、`task-promote` 和 tracked-document maintenance。输入只能使用当前 ACTIVE task 的 evidence refs，并且必须通过 fresh native file/git evidence，或带 fresh native `source_refs` 的 test/runtime evidence；CONFIRMED promotion 还必须直接引用 fresh CONFIRMED file/git evidence。raw findings、transcript、log 和未知字段都会被拒绝。Promotion 使用 base revision 的 CAS，但不修改 task revision。每个 task 最多消耗 16 个 promotion units（每个 memory record 及每个 milestone progress/verification 字段各 1）；计数器只是有界 task-local bookkeeping，不是长期 memory 或 framework。

Core-only 的机械记录示例（不构成 Host task admission 或语义验收）：

```bash
thaliris-core --root . task-start "adopt request policy"
# ...Controller receives task-local evidence and decides retention...
thaliris-core --root . task-promote --actor controller --base-revision <revision> --input promote.json
thaliris-core --root . task-close --base-revision <revision>
```

`--actor` 是 adapter 提供的标签，不是身份凭证；Core CLI 单独运行不能证明调用者是 Controller。通过 Host adapter 时，adapter 会在允许的边界内执行授权检查。

```json
{"records":[{"type":"decision","id":"D-001","title":"Use X","text":"Adopt X.","evidence_refs":["e1"],"confidence":"SUPPORTED"}]}
```

Memory 只追加新 entry，并在现有 INDEX 中追加单条 router link；milestone 只更新显式提供的字段并使用 atomic backup。大型历史读取、去重、stale cleanup、冲突判断、INDEX 重构或批量 milestone 整理必须缩小范围后交给 fresh child。

### Child lifecycle epistemic/control policy

尚未观察到结果不等于失败；timeout、slow 或 incomplete observation 也不等于 capability limitation。没有明确证据时 child 状态保持 `UNKNOWN`。`RUNNING` 只能 wait/re-observe；`UNKNOWN` 只能 keep `UNKNOWN`/re-observe，不能因为一次等待窗口结束就关闭、替换或 takeover。只有明确的 `FAILED`、`CANCELLED`、`UNAVAILABLE` 或 deterministic spawn failure 才能 narrower fresh delegation。只有 objective capability unavailable 才允许最小 capability fallback，且不能借机由 Controller 自行调查或实现；child failure 后优先缩小范围重新委派 fresh child。这是针对 Codex-native observations 的 managed Controller policy，不是 Thaliris runtime、scheduler、heartbeat、retry state machine 或 agent framework；Thaliris 只确定性执行自身的字段校验、evidence/freshness、CAS、role projection 和 capture filtering。

---

## 证据模型

本项目使用四种有效证据状态：

| 状态         | 含义                                             |
| ------------ | ------------------------------------------------ |
| `CONFIRMED`  | 有足够强且当前有效的原生证据支撑                 |
| `SUPPORTED`  | 存在证据，但证据较弱或间接                       |
| `UNVERIFIED` | 尚未建立                                         |
| `STALE`      | 此前记录的证据不再与当前状态匹配                 |

原生证据可以包括：

```text
file:path/to/file#sha256
git:path/to/file#blob-id
```

测试和 runtime observation 可以引用它们观察时对应的 source snapshot。

其 freshness 只能证明那些明确声明的 source 尚未变化。

它不能证明每一个可能的依赖项都保持不变。

---

## 项目记忆

`.agent-memory/` 保存持久的项目知识。

例如：

* 项目约定；
* operator constraints；
* 已采纳决策；
* 经验证的重复性 failure mode。

Memory entry 使用如下 metadata：

```yaml
Evidence: file:src/example.py#...
Revision: 1
Status: ACTIVE
Applicability: src/example.py
Confidence: SUPPORTED
Kind: MEMORY
Audience: ["sol-high", "terra-implementer"]
Topics: ["request cancellation"]
Symbols: ["Request.cancel"]
```

INDEX 文件是 router，而不是总结文档。

旧版 Codex adapter 的 `context recall` 命令用于显式、保守的 lexical retrieval；它不是 Core-only CLI 命令。Durable memory 是可选择的知识来源，不等于完整 task context：记录存在或被索引，不代表会自动注入每个角色、进入当前任务，或随 handoff 向下游传播。Controller 选择实际相关内容并决定是否显式 promotion。当前 Codex adapter 命令见 [Codex 指南](https://github.com/Iris0fTheValley/Thaliris-codex/blob/main/README.md)。

---

## 里程碑

`.milestones/` 将持久的项目进度与瞬态任务上下文分开保存。

一个里程碑包含：

```text
scope.md
decisions.md
progress.md
verification.md
```

这些文件分别回答不同问题：

* **scope** — 哪些内容属于这个里程碑；
* **decisions** — 里程碑特定的选择；
* **progress** — 当前状态和下一步工作；
* **verification** — 实际检查过哪些内容。

里程碑文档是项目状态，而不是代理 transcript。

---

## 托管的 `AGENTS.md`

[Codex adapter](https://github.com/Iris0fTheValley/Thaliris-codex/blob/main/README.md) 的初始化流程会在仓库现有的 `AGENTS.md` 中维护一个带标记的小型区块。Core-only CLI 不安装 Hooks，也不维护 Codex 的 Host 指令。

它被有意保持简短。

托管区块作为以下内容的 router：

* Controller ownership；
* 角色隔离；
* 调查/curation；
* Decision Context promotion；
* 默认顺序委派；
* microtask fast path；
* 原生 correctness fallback。

托管标记以外的现有用户内容会被保留。

---

## 可选工具

`Thaliris` 可以与下列优化工具共存：

| 工具        | 预期用途                       |
| ----------- | ------------------------------ |
| Serena      | 符号与引用导航                 |
| cachebro    | 未变化读取的缓存与 delta       |
| agentmemory | 显式 episodic recall           |

这些工具都是可选的。

`Thaliris` 不会替代它们的数据库，也不会编排它们的生命周期。

如果它们不可用，请使用原生的源代码检查、Git、搜索、编译器、测试和运行时行为。

---

## 诊断

Core-only 诊断可使用：

```bash
thaliris-core --root . task-status
thaliris-core --root . task-show
thaliris-core --root . stale
thaliris-core --root . milestone-check
```

Codex adapter 的 `context doctor` 是历史 adapter 命令，当前诊断与原生身份/Hook 状态见 [Codex 指南](https://github.com/Iris0fTheValley/Thaliris-codex/blob/main/README.md)。Core 输出不能证明 authorization、Host health、runtime activation 或 subagent lifecycle；无法由对应 adapter 观察证明的状态保持 `UNKNOWN`。

诊断会刻意区分以下状态：

```text
configured
enabled
installed
version observed
version validated
```

当工具无法实际证明 authorization、health、runtime state 或 subagent state 时，这些状态会保持为 `UNKNOWN`。

诊断层不应凭空制造信心。

---

## 恢复与卸载

初始化和托管修改使用：

* 跨进程锁；
* 原子文件替换；
* 本地备份；
* hash guard rollback。

Core-only 恢复操作：

```bash
thaliris-core --root . rollback <backup-id>
```

卸载：

```bash
thaliris-core --root . uninstall
```

`context migrate` 是旧 Codex adapter 示例，不是当前 Core 命令。Core rollback/uninstall 只处理其管理的项目记录，并保留用户修改的项目记忆；它们不会维护或恢复 Host 安装、Hooks、profiles 或活动会话。相关 adapter 恢复按 [Codex](https://github.com/Iris0fTheValley/Thaliris-codex/blob/main/README.md) 或 [DSH](https://github.com/Iris0fTheValley/Thaliris-dsh) 指南执行。

---

## 本项目不是什么

`Thaliris` 有意**不做**：

* Agent runtime；
* 工作流引擎；
* 递归代理 scheduler；
* 数据库支持的记忆平台；
* 图存储；
* embeddings-first RAG 系统；
* Web UI；
* 自动的全仓库总结器；
* 源代码检查或测试的替代品。

本项目应保持足够小巧，即使删除它，底层开发工作流也不会因此变得不正确。

---

## 研究假设

本项目背后最核心的主张仍然只是一项假设：

> 即使可用上下文总量或算力不变，保护强推理模型的任务纯度也可能提升编码表现。

换句话说，计算量大致相同的两个工作流可能呈现不同表现：

```text
工作流 A

Sol：
搜索
→ 检查
→ 推理
→ 实现
→ 调试
→ 重读日志
→ 验证
→ 自我审查
→ 修订
```

与：

```text
工作流 B

Investigator：
大规模扫描
→ 压缩事实与证据

Focused Executor：
读取少量关键材料
→ 聚焦推理
→ 实现
→ 验证

Independent Reviewer：
需要时进行 fresh review
```

第二种工作流会主动终止可丢弃的上下文，而不是让每个中间任务都留在最强模型的推理轨迹中。

本项目试图让这条边界变得明确且可测试。

它**不**假定代理越多越好。

它**不**假定上下文越少越好。

其原则更为克制：

> **为每个推理上下文提供其所需的信息，不要仅仅因为其他信息存在，就同时赋予它无关目标。**

---

## 研究动机与适用边界

这些论文为设计选择提供动机依据，但不能验证 Thaliris 或其压缩比例。
[Liu 等人（2024）的 Lost in the Middle](https://doi.org/10.1162/tacl_a_00638)研究上下文的位置和结构如何影响利用效果。[Jiang 等人（2024）的 LongLLMLingua](https://doi.org/10.18653/v1/2024.acl-long.91)报告了其测试任务中的信息密度、效率和性能影响。
[Mondshine、Paz-Argaman 与 Tsarfaty（2025）的 Beyond English](https://doi.org/10.18653/v1/2025.findings-naacl.73)支持按任务处理语言；[Kim 等人（2025）](https://doi.org/10.18653/v1/2025.findings-emnlp.1215)研究英语和韩语中的语言特有细节与知识线索，并未声称这种处理普遍有益。
[Park 等人（2026）的研究](https://arxiv.org/abs/2606.19668)提示应谨慎对待随机语言切换和锚定效应。这里列出的文献仅作为动机依据，并非本次重新复现的实验。
ABCD 结果只适用于各自原有的实验设置；本次没有对提示词规范化进行基准测试，字节数和 token 数估算也仅用于观察长度。

## Host adapters

Core 保持 runtime-neutral，不安装 Host hooks，也不执行 agents。[Thaliris-codex](https://github.com/Iris0fTheValley/Thaliris-codex) 与 [Thaliris-dsh](https://github.com/Iris0fTheValley/Thaliris-dsh) 在共享 Core 之上提供原生集成。verification target 表达 requirement，不是 shell authority：只有 adapter 观察到明确的执行完成状态时，才可向 Core 提交受信结果；具体 runtime payload 无法提供该状态时结果保持 `UNKNOWN`。
---

## 当前限制

本项目仍处于早期阶段。

当前限制包括：

* 路由有意保持保守；
* 任务状态是本地的单任务状态，而不是任务数据库；
* evidence freshness 无法证明未声明的依赖；
* 角色执行由 Host adapter 提供，而不是由 Core 提供；
* 外部 adapter 的健康状态并非总能被直接观察；
* cognitive isolation 的收益仍需在真实编码工作负载上进行受控评估。

只有当真实任务证明增加复杂度能改善下游质量或可靠性时，才会增加复杂度。

---

## 开发

运行 Core 测试：

```bash
uv run --extra test pytest tests/test_core_authority.py tests/test_mechanical_core.py tests/test_core_cli.py
```

ABCD 源码测试另外显式安装 Codex adapter；步骤见[分包与验证说明](docs/host-neutral-packaging.md)。它们验证协议和工具，不启动 benchmark。

验证按改动范围、风险和已有的新鲜证据分层：开发中先运行最小针对性测试；多个相关修复完成后合并运行相关回归；最后只运行一次足以覆盖本轮改动的完整相关验证。纯文档调整、低风险 P2 修复，或未改变已验证行为代码的 merge/conflict，不自动重复昂贵检查。这不会降低完成标准；用户明确要求真实 runtime 或 visible behavior 验证时，不能以静态测试替代。

CI 当前覆盖项目支持的 Python 版本。

修改应维持以下核心 invariant：

1. 正确性不依赖可选优化工具；
2. 原始探索内容不会自动向下游传播；
3. 证据不能仅因被总结就变得更强；
4. 高推理上下文保持聚焦；
5. 失败应先降低效率，而不是降低正确性；
6. 本项目仍是围绕共享 Core 的精简、Host 无关层，而不会变成另一个 Agent Framework。

---

## Related projects / Integrations

* [Thaliris-codex](https://github.com/Iris0fTheValley/Thaliris-codex)：Codex hooks、原生身份与生命周期、profiles、安装及恢复。
* [Thaliris-dsh](https://github.com/Iris0fTheValley/Thaliris-dsh)：DeepSeek Harness 插件，复用原生 Settings、模型目录、Workspace、Session、Subagent，以及共享 Web/Desktop client。
* [Benchmark](benchmarks/abcd)：ABCD 实现、历史证据索引与[协议](docs/thaliris-benchmark-protocol.md)继续由本主仓维护。

两个 adapter 依赖同一个 Host-neutral Core，不是另两个 Core 实现。DSH 已提供可编辑的 role/persona、模型与 tools/context 权限；内置角色只是模板。Memory capability 和默认 provider 为可卸载的独立组件，支持替换或多个 provider 并存；关闭 memory 不影响 task/routing。read/write 与长期写入策略由用户明确配置，provider 负责自己的 RAG/embedding 等实现，Core 不依赖这些实现。

## ABCD 基准测试结果

我们运行了一项受控的单任务基准测试，以区分**模型能力**、**编排**和**异构智能分配**。A/B/C 使用相同任务、BASE 修订、Codex 版本、隔离的工作区/CODEX_HOME 和环境；D 是此前封存的生产架构运行，没有重新运行。

四个已完成的实验组检验两个主要假设：

**编排收益 — B → C：** 对 Luna-only 系统而言，角色拆分和隔离的多 Agent 执行是否比单个 Luna Agent 更好？

**智能分配收益 — C → D：** 已有编排后，在语义实现、评审和收尾环节有选择地使用更强模型，是否会实质改善结果？

### 结果

| 实验组 | 配置 | 覆盖度 | 正确性 | 兼容性 | 实现 | 验证 | 均值 | 完成情况 | 墙钟时间 | 成本代理值 |
|---|---|---:|---:|---:|---:|---:|---:|---|---:|---:|
| **A** | Sol medium，单 Agent | 6 | 4 | 6 | 6 | 7 | **5.8** | 部分 | **21m36s** | **$0.883** |
| **B** | Luna xhigh，单 Agent | 6 | 5 | 6 | 6 | 4 | **5.4** | 部分 | **54m09s** | **$0.232–0.235** |
| **C** | Thaliris，Luna-only | 4 | 6 | 7 | 6 | 4 | **5.4** | Managed DONE / 产品部分完成 | **41m11s** | **$0.272** |
| **D** | Thaliris，异构路由 | **9** | **8** | **8** | **8.5** | **8** | **8.3** | 基本完成；仍有一个 P2 | **64m47s** | **$2.475** |
| **E?** | D 拓扑，**全 Sol 工作节点** | **9?** | **8?** | **8?** | **8.5?** | **8?** | **8.3?** | 类似 D？ | **64m47s?** | **~$3.67 预测** |
| **F?** | D + **语义收敛切换** | **9?** | **8?** | **8?** | **8.5?** | **8?** | **8.3?** | 类似 D？ | **64m47s?** | **~$2.06–2.07 预测** |

A/B/C 的独立评分、运行时间和成本测量来自新一轮基准评估。D 最初封存的评估将五个维度都评为 GOOD；上表 8.3/10 是后来用 A/B/C 评分标准对同一个冻结候选做的只读重评。D 的原始运行仍保持封存且未修改。它的生产路由为 Luna Investigator → Sol Focused Implementer → Sol Reviewer → Luna repair → Sol Reviewer → Luna repair。

### Token 结构

cached input 是 input 的子集，不是额外 token。

| 实验组 | 输入 | 缓存 | 新鲜输入 | 输出 | 推理输出 | 模型分布 |
|---|---:|---:|---:|---:|---:|---|
| **A** | **3.104M** | 2.962M | 0.142M | 30.3k | 7.1k | 100% Sol medium |
| **B** | **16.70M** | 16.39M | 0.309M | 79.8k | 46.8k | 100% Luna xhigh |
| **C** | **15.73M** | 15.03M | 0.695M | 105.0k | 66.3k | 100% Luna xhigh |
| **D** | **15.22M** | 14.51M | 0.706M | 108.2k | 44.2k | Sol：9.96M 输入 / 64.3k 输出；Luna：5.26M / 43.9k |
| **E? 全 Sol** | **~15.22M?** | ~14.51M? | ~0.706M? | **~80.9k 预测** | ? | 相同 D 拓扑，Luna 节点替换为 Sol |
| **F? 语义切换** | **~14.05–14.65M 预测** | ? | ? | **~100.9–108.9k 预测** | ? | Sol ~8.09M 输入；Luna ~5.96–6.56M |

D 的实际用量为 15.219M 输入，其中 14.513M 为缓存。Luna 消耗 5.260M 输入 / 43.9k 输出；Sol 消耗 9.959M 输入 / 64.3k 输出。

### 各实验组的表现

| 实验组 | 优点 | 主要弱点 |
|---|---|---|
| **A — Sol 单 Agent** | 运行最快；实现能力强，并自行生成了广泛的验证。 | 单条执行轨迹形成了连贯但不完整的语义模型。测试大多验证了自身假设，遗漏跨表面的所有权、重放和关闭缺陷。 |
| **B — Luna 单 Agent** | 成本极低。投入更多计算和时间后，Luna 的总分几乎与 A 相同。 | 输入量约为 A 的 5.4 倍，墙钟时间约为 2.5 倍；全局语义收敛和验证较弱。大量计算仍未消除生命周期/authority 缺口。 |
| **C — Luna 编排** | 角色分工清楚，managed lifecycle 完整；比 B 快约 13 分钟，正确性/兼容性略好。 | **总质量没有比 B 提升。** 覆盖度从 6 降到 4。Treatment review 错误地判定可以关闭，managed task 已到 DONE，但产品验收仍未完成。 |
| **D — Thaliris 异构模型** | 这是唯一实现了显著更高完成度的配置。独立评审 → 修复 → 再评审确实改变了候选并关闭了缺陷。 | 在已观测实验组中耗时和成本最高。Sol 累积了大量缓存上下文重放；之后仍有一个 P2 presentation-lifecycle 缺陷，真实 GPU/audio/UI 行为也未验证。 |

A/B/C 各自的主要独立缺陷记录在评估材料中：它们分别实现了不同的部分正确方案，并非都以完全相同的方式失败。

### 假设 1 — 编排收益

**方法：** 在实际执行能力固定为 Luna xhigh 时比较 **B 与 C**。B 是单个 Luna Agent；C 使用 Thaliris 角色、隔离的子 Agent 上下文和 managed lifecycle，但所有已观测工作节点都是 Luna xhigh。

**观测结果：**

5.4 → 5.4

没有观察到产品质量提升。C 快了约 **13 分钟**，总 token 略少，但因为未缓存输入更多，估算成本**高约 16–18%**。质量分布发生变化，却没有总体改善：覆盖度 −2，正确性 +1，兼容性 +1。<br>

**结论：** 在这个样本中，单靠编排没有实质增强较弱模型。它展示了工作流/lifecycle 和吞吐量方面的好处，但没有提高总质量。

### 假设 2 — 智能分配收益

**方法：** 比较 **C 与 D**。两者都使用 Thaliris 编排；D 有选择地将 Sol 分配给 Controller、核心语义实现和独立评审，同时保留 Luna 处理调查和有界修复。

**观测结果：**

5.4 → 8.3

评分变化最大的维度为：

覆盖度：4 → 9（+5）<br>
验证：4 → 8（+4）<br>
实现：6 → 8.5（+2.5）<br>
正确性：6 → 8（+2）<br>
兼容性：7 → 8（+1）<br>

D 的成本约为 C 的 **9.1 倍**，时间约为 **1.57 倍**，但它是唯一显著越过产品完成门槛的实验组。D 没有并行执行；主要可观测机制是反复的 **Reviewer → 有界修复 → 再评审**，而不是 Agent 数量或并行计算。

**结论：** 结果支持的是**选择性智能分配**，而不是“Agent 越多越好”。

### 接下来要验证的两个成本假设

**E — 全 Sol 反事实。** 保持 D 的任务、拓扑、角色顺序和 lifecycle 不变，仅把 Luna Investigator/Implementer 节点替换成 Sol。输入/上下文重放量近似不变；仅按 A/B 输出效率比（79.8k / 30.3k ≈ 2.64×）调整输出。这预测全 Sol 的 D 型运行成本约为 **$3.67**，相对于**观测到的 $2.475**，若保持 D 级质量，异构执行约可节省 **32.6%**。不做输出效率调整时，简单的同 token 估算约为 **$3.94**。这仍是反事实，尚未运行。

**F — 语义收敛切换。** 保留 D 的架构和高能力语义节点，但在 Sol Focused Implementer 建立核心实现和硬不变量后结束其执行。广泛测试、构建/lint 收尾、确定性的兼容问题和小修复交给新的 Luna Implementer；新的 Sol Reviewer 仍负责语义验收。基于 trace 的估算移除约 **1.87M Sol 输入 / 15.3k Sol 输出**，增加约 **0.7–1.3M Luna 输入 / 8–16k 输出**，预测成本为 **~$2.06–2.07**，比 D 低约 **16–17%**，目标是同样的 8.3 水平。实际测试前，质量仍明确未知。

### 结语

当前基准支持一个比“多 Agent 更好”更窄的结论：

> **弱模型编排本身没有改善总质量。把更强智能有选择地放在语义实现、评审和收尾环节，确实带来了提升。**

目前已经修正为了缩短昂贵上下文的生命周期。高能力模型应继续用于执行期间确实需要其推理的工作；语义方案收敛后，可以把确定性的收尾交给成本更低的新工作节点，避免反复重放庞大的 Sol 上下文。
但我没钱继续跑基准测试了

## Benchmark 边界

`benchmarks/abcd/` 可以包含复杂 collector、formal authority 与离线评分。
生产 Core Python 包 `thaliris` 不依赖 D11、formal registry、capture authority 或
benchmark receipt issuer。Benchmark 观察 production；它不定义 production 架构。

完整契约见 [DESIGN.md](DESIGN.md) 与
[docs/thaliris-routing-protocol.md](docs/thaliris-routing-protocol.md)。

---

## 许可证

MIT License。参见 [`LICENSE`](LICENSE)。

---

## 贡献

本项目仍处于实验阶段，因此更倾向于小型、由证据支撑的修改。

有价值的贡献包括：

* 可复现的路由失败；
* provenance 或 freshness bug；
* migration 与恢复失败；
* 角色隔离泄漏；
* 真实世界的 benchmark 结果；
* 保持行为不变的简化。

大型框架扩展应由一个无法通过现有小型架构解决的具体 failure mode 来证明其必要性。

Core 0.4.3 also transports an optional nonempty `execution_constraint` string in
the immutable authority contract. Adapters interpret supported values; Core
does not select models or alter semantic roles. See
[authority contracts](docs/thaliris-task-authority.md).
