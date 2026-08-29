# codex-context

[English](README.en.md)

一个轻量、Git 原生的 Codex 上下文与编排层。

`codex-context` 帮助多代理编码工作流把正确的信息放入正确的推理上下文，同时避免把仓库变成 Agent Framework。

它提供：

* 按角色划分的上下文包；
* 由证据支撑的项目记忆；
* 瞬态任务状态；
* 调查与审查交接；
* freshness 跟踪；
* 里程碑状态；
* 保守路由；
* 确定性的验证与恢复。

Codex 仍然是 runtime 和 Controller。源代码、Git、测试、编译器和运行时行为仍然是 correctness core。

> **状态：** Alpha。当前实现有意保持小巧，仍在真实编码工作负载上进行评估。

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

`codex-context` 建立在一个简单理念之上：

> **保留有用信息，但不强迫每个角色携带每一条信息。**

因此，本项目把上下文边界视为工程架构的一部分。

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

因此，`codex-context` 不会尝试给每个代理提供相同的提示词。

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
结构化原始 findings
            ↓
有界的 curated snapshot
            ↓
Controller 选择
            ↓
小型 Decision Context
            ↓
高推理代理
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

### Controller — Sol mid

父级 Controller 负责：

* 任务路由；
* 任务状态；
* 上下文 promotion；
* 阶段转换；
* 集成；
* 最终验收。

只有 Controller 可以委派工作。

Controller 应基于有界任务视图工作，而不是读取原始调查 transcript。

---

### Luna investigator

用于聚焦调查和机械式证据收集：

* 仓库搜索；
* 符号发现；
* 引用查找；
* Git 检查；
* 定向验证；
* 结构化提取；
* 测试执行；
* 残留引用检查。

Luna 可以拥有较大的工作集。

它的持久输出是结构化 findings 和 evidence refs，而不是 transcript。

---

### Luna curator

一个 fresh Luna invocation 可以压缩累积的 investigation findings。

它可以：

* 合并重复项；
* 从活跃 snapshot 中移除已解决的 unknown；
* 整合相关证据；
* 替换过时的 snapshot 条目；
* 让当前调查状态保持有界。

它不能凭空制造比来源 findings 更强的确定性。

Curation 改变的是表达形式，而不是证据。

---

### Sol high

仅用于真正受益于更强推理上下文的问题：

* 架构；
* 生命周期行为；
* 并发；
* 跨模块语义；
* 模糊的根因；
* 困难的 migration 语义；
* provenance 或安全推理；
* 艰难的取舍。

Sol high 不维护任务状态，也不执行常规的证据 bookkeeping。

它的理想轨迹是：

```text
事实 → 推理 → 决策 → 退出
```

---

### Terra implementer

接收明确的实现边界，以及完成修改所必需的事实。

它的职责是实现，而不是扩大架构范围。

当假设不成立或所需范围发生实质性扩大时，控制权返回 Controller。

---

### Terra reviewer

高风险修改可以接受一次 fresh independent review。

Reviewer 会被刻意隔离于：

* 此前的 reviewer findings；
* implementer 的自我辩护；
* 原始调查历史；
* 评分 rubric；
* 不必要的调试历史。

它返回包含影响和证据的结构化问题。

Controller 决定这些 findings 是否应影响 Decision Context。

---

## 典型工作流

### Microtask

对于明显、局部且低风险的修改：

```text
Controller
    ↓
直接编辑
    ↓
确定性检查
    ↓
完成
```

无需子代理。

---

### 常规实现

```text
Controller
    ↓
Terra implementer
    ↓
确定性检查
    ↓
需要时由 Luna 验证
```

---

### 调查

```text
Controller
    ↓
Luna investigator
    ↓
需要时生成 curated findings
    ↓
Controller

        ├─ 解决方案明确 → Terra
        └─ 推理困难 → Sol high
```

---

### 复杂修改

```text
Luna 调查
        ↓
有界证据
        ↓
Sol high 推理
        ↓
Terra 实现
        ↓
确定性检查
        ↓
Luna 验证
```

对于风险足够高的修改：

```text
        ↓
fresh Terra review
        ↓
Controller 决策
```

默认并发数为一。

只对明确独立的工作使用并行。

---

## 安装

需要 Python 3.11 或更高版本，以及 Git。

直接从仓库安装：

```bash
uv tool install git+https://github.com/Iris0fTheValley/codex-context
```

接入现有 Git 仓库：

```bash
cd your-repository
context init
context doctor --pretty
```

用于本地开发：

```bash
git clone https://github.com/Iris0fTheValley/codex-context
cd codex-context

uv run --extra test pytest
uv run context version
```

---

## 快速开始

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
context prepare --role luna-investigator --pretty
```

当 investigation findings 需要压缩时准备 curator：

```bash
context prepare --role luna-curator --pretty
```

准备深度推理上下文：

```bash
context prepare --role sol-high --pretty
```

准备实现上下文：

```bash
context prepare --role terra-implementer --pretty
```

准备独立审查上下文：

```bash
context prepare --role terra-reviewer --pretty
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

其目标是保留可追溯性，同时避免把 `.context/state.json` 变成第二份对话历史。

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

正常路由是保守的 lexical routing。

当 audience 和 evidence 允许时，新鲜且作用于整个项目的 `HARD_CONSTRAINT` 条目可以绕过 lexical matching。

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

`context init` 会在仓库现有的 `AGENTS.md` 中维护一个带标记的小型区块。

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

`codex-context` 可以与下列优化工具共存：

| 工具        | 预期用途                       |
| ----------- | ------------------------------ |
| Serena      | 符号与引用导航                 |
| cachebro    | 未变化读取的缓存与 delta       |
| agentmemory | 显式 episodic recall           |

这些工具都是可选的。

`codex-context` 不会替代它们的数据库，也不会编排它们的生命周期。

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

`codex-context` 有意**不做**：

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

Luna：
调查
→ 结构化证据

Sol：
聚焦推理
→ 决策

Terra：
实现

Luna：
验证

Terra：
需要时进行 fresh review
```

第二种工作流会主动终止可丢弃的上下文，而不是让每个中间任务都留在最强模型的推理轨迹中。

本项目试图让这条边界变得明确且可测试。

它**不**假定代理越多越好。

它**不**假定上下文越少越好。

其原则更为克制：

> **为每个推理上下文提供其所需的信息，不要仅仅因为其他信息存在，就同时赋予它无关目标。**

---

## 当前限制

本项目仍处于早期阶段。

当前限制包括：

* 路由有意保持保守；
* 任务状态是本地的单任务状态，而不是任务数据库；
* evidence freshness 无法证明未声明的依赖；
* 角色执行仍由 Codex 完成，而不是由本 package 完成；
* 外部 adapter 的健康状态并非总能被直接观察；
* cognitive isolation 的收益仍需在真实编码工作负载上进行受控评估。

只有当真实任务证明增加复杂度能改善下游质量或可靠性时，才会增加复杂度。

---

## 开发

运行测试套件：

```bash
uv run --extra test pytest
```

CI 当前覆盖项目支持的 Python 版本。

修改应维持以下核心 invariant：

1. 正确性不依赖可选优化工具；
2. 原始探索内容不会自动向下游传播；
3. 证据不能仅因被总结就变得更强；
4. 高推理上下文保持聚焦；
5. 失败应先降低效率，而不是降低正确性；
6. 本项目仍是 Codex 周围的薄层，而不会变成另一个 Agent Framework。

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
