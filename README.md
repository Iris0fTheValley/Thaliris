# Thaliris

主仓库现在发布 Host 无关的 Core、共享语义文档和 ABCD 基准协议/历史证据。`thaliris-core` 仅提供 Core 操作；Codex 集成位于 [Thaliris-codex](https://github.com/Iris0fTheValley/Thaliris-codex)，DSH 集成位于 [Thaliris-dsh](https://github.com/Iris0fTheValley/Thaliris-dsh)。安装与 API 边界见 [分包说明](docs/host-neutral-packaging.md)。

[English](README.en.md)

一个轻量、Git 原生的 AI 编程上下文与编排层。


项目理念是用大量可丢弃的低成本认知工作，保护少量不可替代的前沿推理注意力；让强模型自己做专家，而不是让搜索、流程和审查占据专家的脑子

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

## 设计理念

### 每个推理上下文只保留一个主导目标

强模型已经具备大量从训练中获得的工程知识。

目标不是告诉它们应当执行每一个推理步骤，而是向它们提供：

* 问题；
* 已确认事实；
* 相关证据；
* 硬约束；
* 未解决的问题。

然后让模型自行推理。

系统会尽量避免在同一个上下文中明确组合互不相关的认知角色。

例如，更推荐：

```text
调查 → 汇总证据 → 推理 → 实现 → 验证
```

而不是：

```text
一个代理负责调查
        + 设计
        + 实现
        + 评判自己的设计
        + 验证一切
        + 重读此前的全部日志
```

---

### 弱模型需要流程，强模型需要证据

不同能力的模型适合不同程度的脚手架。

可以近似理解为：

```text
较弱模型
    → 做什么 + 怎么做 + 检查清单

中等能力模型
    → 做什么 + 边界 + 部分方法

强推理模型
    → 做什么 + 事实 + 硬约束
```

因此，`Thaliris` 不会尝试给每个代理提供相同的提示词。

调查和机械验证可以使用明确的 schema 与流程。

高推理角色会收到小得多、以证据为核心的上下文。

---

### 工作集不等于交接集

调查者可能需要检查数百个文件、搜索结果、符号和中间假设。

这并不意味着下一个代理应该收到全部内容。

预期流程是：

```text
大型调查工作集
            ↓
压缩后的 findings + evidence refs
            ↓
被选中的 Controller / Executor / Reviewer 上下文
            ↓
聚焦推理、实现或审核
```

原始探索内容仍可用于追溯，但它不会自动获得进入每个下游上下文的权限。

---

### 证据优先于记忆

项目记忆很有用，但记忆不等于事实。

实际优先级是：

```text
当前源代码 / Git / 测试 / runtime
                ↓
新鲜且已验证的项目记忆
                ↓
里程碑状态
                ↓
历史记忆
```

当支撑证据发生变化时，已保存的解释可能会变得 stale。

hash 未变化只能证明被引用的证据没有变化，**不能**证明此前的解释是正确的。

---

### 优化不能成为正确性依赖

可选工具可以减少重复读取或加快导航。

它们绝不能成为保证正确性的必要条件。

如果 Serena、cachebro、agentmemory 或其他优化层失效，工作流应该只是变慢，而不是变得不正确。

---

## 架构

默认角色有意保持职责狭窄。

### Controller / Control Plane

Core 只定义语义角色；具体 runtime 和模型选择属于 adapter。

父级 Controller 负责：

* 任务路由；
* 任务状态；
* 上下文 promotion；
* 阶段转换；
* 集成；
* 最终验收。

Controller 拥有顶层任务路由和任务所有权。具体 adapter 可以显式允许执行或审核角色把有界的大规模调查委派给 Investigator；这种子委派只返回压缩事实与证据，不转移任务所有权。

Controller 应基于有界任务视图工作，而不是读取原始调查 transcript。

---

### Investigator

具体 runtime 和模型选择属于 adapter。

用于大 working set 调查、仓库扫描和机械式证据收集：

* 仓库搜索；
* 符号发现；
* 引用查找；
* Git 检查；
* 定向验证；
* 结构化提取；
* 测试执行；
* 残留引用检查。

Investigator 可以拥有很大的工作集，并负责把搜索、调用点、测试和中间探索压缩成事实、位置、证据与未知项。

其输出是 task-local 的结构化 findings 和 evidence refs，而不是 transcript。只有 Controller 作出显式 retention 决定并运行 `task-promote` 后，内容才可能进入 `.agent-memory/` 或 `.milestones/`。

---

### Curator

具体 runtime 和模型选择属于 adapter。

Curator 是按需的知识增强角色，而不是调查流水线中的压缩工位。只有当 Controller 已经明确选出值得复用的材料时，才让 Curator 对这些材料做去任务化、压缩、去重或重组，使其适合进入长期项目知识。

Curator 不负责决定什么重要、选择下一角色或替 Controller 路由；它也不能凭空制造比来源材料更强的确定性。

Curation 改变的是表达和可复用性，而不是证据。

---

### Reasoning Specialist

具体 runtime 和模型选择属于 adapter。

Reasoning Specialist 是按需的元认知角色。它不因为“实现很难”就自动介入；复杂的具体实现仍应由合适的执行角色自己完成推理和修改。

仅当问题定义、抽象层级、目标或前提本身不清楚时使用它，例如：

* 当前方案始终别扭，怀疑问题被错误建模；
* 多个候选方案其实在解决不同的问题；
* 用户或 Controller 还不清楚真正需要决定什么；
* 需要显式挑战隐藏假设或重新表述核心矛盾。

它不维护任务状态，也不执行大规模仓库调查或常规证据 bookkeeping。它的输出应帮助 Controller 重新定义问题、决策依据和仍需确认的未知项。

---

### Implementer

具体 runtime 和模型选择属于 adapter。

接收明确的实现边界，以及完成修改所必需的事实。

它的职责是理解、实现和验证，而不是扩大任务所有权。复杂实现可以由 adapter 选择更聚焦、更高能力的执行绑定，让推理与修改留在同一个 working set 中。

Implementer 可以直接读取少量关键文件；当需要大范围仓库搜索、调用点枚举或其他巨大机械 working set 时，支持该能力的 adapter 可以让它把这部分调查委派给 Investigator，再基于压缩后的事实继续实现。

当关键假设失效、问题定义需要重开或所需范围发生实质性扩大时，控制权返回 Controller。

---

### Independent Reviewer

具体 runtime 和模型选择属于 adapter。

Reviewer 按风险和独立判断价值调用；高风险修改仍应接受 fresh independent review。

Review findings 是独立证据，不会自动触发另一轮实现：P0/P1，或直接违反请求 completion criteria 的 finding 必须解决；P2/lower 只有在实质影响 correctness、requested behavior、regression safety 或已接受的 Modification Boundary 时，Controller 才会安排另一轮实现。Review 不是迭代式 cleanup loop。

Reviewer 会被刻意隔离于：

* 此前的 reviewer findings；
* implementer 的自我辩护；
* 原始调查历史；
* 评分 rubric；
* 不必要的调试历史。

它返回包含影响和证据的结构化问题。需要大范围机械核查时，支持该能力的 adapter 可以让 Reviewer 委派 Investigator 做扫描，而 Reviewer 保留独立判断。

Controller 决定这些 findings 是否应影响 Decision Context。

---

## 典型工作流

### Microtask

对于明显、局部且低风险的修改：

```text
Controller
    ↓
Implementer
    ↓
deterministic verification
    ↓
done
```

即使是 microtask，persistent Controller 也不直接编辑源文件。

---

### 常规实现

```text
Controller
    ↓
Implementer
    ↓
确定性检查
    ↓
需要时由 Investigator 验证
```

---

### 调查

```text
Controller
    ↓
Investigator
    ↓
压缩后的 findings + evidence
    ↓
Controller

        ├─ 问题和边界明确 → Implementer
        └─ 问题定义/抽象本身不清楚 → Reasoning Specialist
```

---

### 复杂修改

```text
Controller
        ↓
适合该复杂度的执行角色
        ├─ 直接读取少量关键文件
        └─ 需要时 → Investigator 大规模扫描
                       ↓
                 压缩事实与证据
                       ↓
             返回同一执行 working set
        ↓
推理 + 实现 + 确定性检查
```

对于风险足够高的修改：

```text
        ↓
fresh Independent Review
        ↓
Controller 决策
```

默认并发数为一。

只对明确独立的工作使用并行。

---

## 安装

本文中的旧版 `context` 命令示例描述 Codex adapter 的行为，并作为设计背景保留。Core 不再提供 prepare/recall、doctor、migrate 或原生角色包。Core 与 Host 边界见[分包说明](docs/host-neutral-packaging.md)；当前命令见 [Codex adapter 指南](https://github.com/Iris0fTheValley/Thaliris-codex/blob/main/README.md) 与 [DSH adapter 指南](https://github.com/Iris0fTheValley/Thaliris-dsh)。

需要 Python 3.11 或更高版本，以及 Git。

直接从仓库安装：

```bash
uv tool install git+https://github.com/Iris0fTheValley/Thaliris
```

接入现有 Git 仓库：

```bash
cd your-repository
context init
context doctor --pretty
```

用于本地开发：

```bash
git clone https://github.com/Iris0fTheValley/Thaliris
cd Thaliris

uv run --extra test pytest
uv run context version
```

---

## Agent 接入

在已有 Git 仓库中开始实质性工作前，先显式检查并初始化 Thaliris 控制层：

Git repository
      ↓
Thaliris ready?
      ├─ no  → context init
      ├─ old → context migrate
      └─ yes → continue
      ↓
context doctor --pretty
      ↓
normal task routing

上面的初始化流程由 [Codex adapter](https://github.com/Iris0fTheValley/Thaliris-codex/blob/main/README.md) 提供。Core 不会自动初始化 Git、安装 Host hooks 或自行 bootstrap runtime；这些能力属于具体 adapter。非 Git 工作区不会仅为了启用 Thaliris 而执行 git init。



## 快速开始

以下 `context prepare` 示例是 Codex adapter 的历史用法，当前 Core CLI 不提供；当前支持的命令见 [Codex adapter 指南](https://github.com/Iris0fTheValley/Thaliris-codex/blob/main/README.md)。

启动一个任务：

```bash
context task-start "fix request cancellation"
```

查看 Controller 视图：

```bash
context prepare --role controller --pretty
```

准备调查上下文：

```bash
context prepare --role investigator --pretty
```

当 investigation findings 需要压缩时准备 curator：

```bash
context prepare --role curator --pretty
```

准备深度推理上下文：

```bash
context prepare --role reasoning-specialist --pretty
```

准备实现上下文：

```bash
context prepare --role implementer --pretty
```

准备独立审查上下文：

```bash
context prepare --role reviewer --pretty
```

检查诊断状态：

```bash
context doctor --pretty
context stale --pretty
context milestone-check --pretty
```

使用当前 revision 关闭当前任务：

```bash
context task-close --base-revision <revision>
```

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

任务保存的是结构化状态，而不是对话 transcript。

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

最小顺序和 JSON 示例：

```bash
context task-start "adopt request policy"
# ...Controller receives task-local evidence and decides retention...
context task-promote --role controller --base-revision <revision> --input promote.json
context task-close --base-revision <revision>
```

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

旧版 Codex adapter 的 `context recall` 命令用于显式、保守的 lexical retrieval。durable memory 默认不会进入普通 role pack；recall 返回 candidates，既不自动接受进 task state，也不自动向下游传播。Core-only CLI 不提供此命令；当前支持的命令见 [Codex adapter 指南](https://github.com/Iris0fTheValley/Thaliris-codex/blob/main/README.md)。

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

[Codex adapter](https://github.com/Iris0fTheValley/Thaliris-codex/blob/main/README.md) 的 `context init` 会在仓库现有的 `AGENTS.md` 中维护一个带标记的小型区块。Core-only CLI 不提供此 Host 初始化命令。

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

运行：

```bash
context doctor --pretty
```

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

回滚：

```bash
context rollback <backup-id>
```

迁移：

```bash
context migrate
```

卸载：

```bash
context uninstall
```

用户修改过的项目记忆会被保留，而不会被静默覆盖。

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

## 研究背景

下列工作为 side-constraint retention、异质状态、外置上下文、handoff continuity、陈旧探索干扰和 evidence-grounded checking 提供经验动机；它们不证明 Thaliris 本身有效，也不证明 task purity 必然优于 context length 或 role projection 必然改善 SWE 表现。

* [Lost in Compaction: Evaluating Side-Constraint Loss under Context Compaction](https://arxiv.org/abs/2608.11242)
* [The Compaction Cliff in Long-Running AI Agent Memory](https://arxiv.org/abs/2608.22752)
* [SKILL.state: Scalable Long-Horizon Agent Skills](https://arxiv.org/abs/2608.26263)
* [Context as an Environment: Programmatic Context Management for Long-Horizon Agents](https://arxiv.org/abs/2608.21690)
* [Handoff Debt: The Rediscovery Cost When Coding Agents Take Over Interrupted Tasks](https://arxiv.org/abs/2606.02875)
* [Harness-of-Harness: Multi-Day Autonomous Software Development with Continual Improvement](https://arxiv.org/abs/2609.01481)
* [AutoCompact: Learning When to Compact Context in Long-Horizon Coding Agents](https://autocompact.github.io/)
* [Adversarial Review: Structured Disagreement for Grounded Agentic Code Review](https://arxiv.org/abs/2608.18167)

实现细节、证据契约和迁移策略见 [DESIGN.md](DESIGN.md)。

---

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
