# Thaliris

[English](README.en.md)

**注意力才是最贵的资源。**

Thaliris 是一个面向 AI 编程 Agent 的**认知编排层**。它不负责把上下文压短，它要解决的是长程任务里的两个问题：

- **强模型的注意力被噪声稀释。** 探索、调试和日志不应留在负责关键判断的那条推理轨迹里。
- **原始需求和反证在交接中消失。** 一个局部“完成”的报告，不应悄悄覆盖掉此前已经发现的问题。

> **Protect the reasoning. Isolate the noise. Isolation without amnesia.**

Thaliris 不另造 Agent Runtime，而是建在 Codex、DeepSeek Harness、Claude Code 这些 Host 的原生 Agent 能力之上，补上隔离、交接和证据连续性这一层。

> **状态：Beta。** 在真实的复杂重构任务上，已经观察到实现者自主派发调查、Controller 发起独立审查、反证推动修复的完整链路。样本量还小，不足以证明普遍的质量或成本优势。见[实测观察](#实测观察)。

## 为什么不止于上下文管理

常见做法是在同一个 Agent 里管理更多上下文：压缩、检索、记忆。Thaliris 认为更大的问题不是 token 多，而是**同一条推理轨迹里互相竞争的目标太多**：既要调查又要设计、实现、调试、自审，还得记住此前的失败。

所以 Thaliris 管的是**谁来推理、带着什么推理**：

> **为每个推理上下文提供它需要的信息，不因为别的信息存在，就把它也塞进去。**

名字取自 Thalamus（丘脑，筛选并路由信息）与 Iris（虹膜，调节进入的光量）。

## 三根支柱

### 1. 认知隔离：把强模型的注意力用在刀刃上

一个长期的 **Controller** 持有用户目标、硬约束和验收标准。短期角色在全新的上下文里完成局部工作，不继承父级对话，只交回结论、来源、验证结果和会改变决策的未知项。

| 角色 | 做什么 |
| --- | --- |
| Investigator | 在选定范围内调查事实，返回来源、矛盾与未知项 |
| Implementer | 实现已确定的方向并完成验证 |
| Focused Implementer | 处理设计与实现高度耦合的问题，直到核心语义收敛 |
| Reviewer | 可选的独立只读挑战，用证据检验候选方案 |

角色按需选用，不是固定流水线。单 Agent、Controller 直接执行或委派都合法。不同角色可以配不同能力的模型：强模型只放在真正需要它的关键节点上。

### 2. Evidence Continuity：隔离，但不遗忘

隔离最大的风险是：审查者发现的反例，经过几轮交接和修复后，被一句“测试通过”悄悄淹没。Thaliris 用这几条规则防止这件事：

1. **反证会被登记。** 子角色发现的事实如果改变了局部结论、局部验收或关键未知项，就记录为一条 observation，附带来源、交接链路和它关联的用户需求。
2. **反证保持可见，直到被明确处置。** 在 Controller 针对当前候选，把每条相关需求明确判定为 *已满足 / 未知 / 需修复 / 已不再相关（并说明理由）* 之前，这条 observation 会在后续交接中持续出现。读过、转发过、确认收到都不算处置。
3. **新的好消息不能顶掉旧的坏消息。** 之后出现测试 `PASS`、Reviewer `READY`、子代理 `Completed` 或 Core `DONE`，都不能让此前的“需修复 / 未知”自动退场；Controller 必须显式引用并回应那条旧依据。
4. **在下判断之前重新呈现。** Adapter 在把子代理结果交给 Controller 时，同时附上仍未处置的关键证据，赶在它做下一次“是否完成”的判断之前。这一步不需要额外的 Agent、固定阶段或轮询。
5. **历史只追加，不改写。** 旧的观察和判断保留为历史，但不会自动被当作当前事实。

Core 只负责保存这些链接和只追加的历史，不判断什么重要；“重要不重要、是否满足需求”始终由 Controller 判断。

```text
Reviewer 发现反例 ──► observation（来源 + 关联需求）
                          │
     后续修复、测试 PASS、子代理 Completed …   ← 都不能让它消失
                          │
Controller 明确处置：已满足 / 未知 / 需修复 / 已不再相关
```

### 3. 语义归模型，机械归 Thaliris

机械层负责身份、来源、版本、连续性和有界检索；语义判断交给模型。结论都带来源（文件 hash、Git blob、测试观察）；freshness 只说明这些来源没变，不说明所有依赖都没变。证据不足时保持 `UNKNOWN`，不把推测升级为确认。

## 组成

| 部分 | 职责 |
| --- | --- |
| **Thaliris Core**（本仓库） | Task ID 与任务记录、observation / judgment 链接、证据与 freshness、项目记忆、里程碑、项目身份、CAS 写入与回滚 |
| [Thaliris-codex](https://github.com/Iris0fTheValley/Thaliris-codex) | Codex 原生集成：Fresh Child、角色 profiles、身份与生命周期、证据重新呈现 |
| [Thaliris-dsh](https://github.com/Iris0fTheValley/Thaliris-dsh/blob/main/README.md) | DeepSeek Harness 插件：Workspace/Session/Agent 集成、可选 Memory |
| [Thaliris-claude](https://github.com/Iris0fTheValley/Thaliris-claude/blob/main/README.md) | Claude Code 插件：Controller skill、角色子代理、Hooks 身份绑定与证据重新呈现 |

只有一套共享 Core。Core 不运行模型、不调度 Agent、不认证调用者；原生执行由各 Adapter 负责。

**项目身份**（Core 0.5.0 起，可选）：受 Git 跟踪的 `.project-identity/` 保存项目级、跨任务的身份基线（身份、不变量、原则、方向、非目标），带版本，只能通过记录了人类所有者决定的显式 amendment 修改；证据对身份的质疑记为 challenge，重要决策的目的关系可以登记并追溯。Core 只记录、版本化、校验引用并观察偏离，不做语义判断，也不自动传播；没有身份的项目行为完全不变。见 [项目身份](docs/thaliris-project-identity.md)。

## 角色能力与推荐模型

> **绝对不要用小模型或低能力模型做控制层（Controller）。** 省钱应当来自把窄任务交给更便宜的子角色，而不是降级 Controller。Controller 的失误不会被子代理纠正，只会被放大：实测中，弱 Controller 会跳过受管流程、在隔离拒绝后退回单代理，或在审查反证仍未处置时就判定完成。

Controller 必须同时具备以下能力，每一项都很重要：

| 能力 | Controller 要回答的问题 |
| --- | --- |
| Global Coherence 全局一致性 | 做了几十上百步以后，是否还记得为什么要做这件事？ |
| Strategic Planning 战略统筹 | 能不能从最终目标反推路径、识别依赖、分配资源，而不是只看下一步？ |
| Retrospective Reasoning 回溯推理 | 能不能从历史决策中定位根本错误，而不是反复修补表象？ |
| Metacognitive Monitoring 元认知监控 | 能不能发现自己正在跑偏、重复劳动，或者陷入不可能完成的任务？ |
| Prospective Reasoning 前瞻推理 | 能不能预测当前决定对后续阶段的影响，主动避免未来的结构性问题？ |
| Adaptive Replanning 动态重规划 | 当原计划失效、条件变化时，能否重新组织全局工作，而不是机械延续旧计划？ |

各角色需要的能力与推荐模型：

| 角色 | 需要的能力 | GPT（Codex） | Claude（Claude Code） |
| --- | --- | --- | --- |
| Controller | 上述六项；整合原始目标、验收标准与证据，判定产品验收 | gpt-6.1-sol（high 或以上）；用户授权时可用 gpt-6-astra | Opus |
| Investigator | 在选定范围内广泛、准确地收集事实与来源，说明已覆盖与未覆盖范围 | gpt-6-luna（max） | Sonnet |
| Implementer | 在已确定的方向内实现、验证并修复普通缺陷，直到确定性收敛 | gpt-6-luna（max） | Sonnet |
| Focused Implementer | 对耦合的不变量持续推理，吸收运行反馈直到语义收敛 | gpt-6.1-sol（high）；用户授权时可用 gpt-6-astra | Sonnet 或 Opus，由 Controller 按任务难度选择 |
| Reviewer | 独立挑战已收敛的候选，跨边界寻找反证，不被作者的框架带偏 | gpt-6.1-sol（high） | Opus |
| Reasoning Specialist | 质疑问题框架、因果模型和决策依据 | gpt-6.1-sol（high）；用户授权时可用 gpt-6-astra | Opus |
| Curator | 依据选定材料精确整理长期知识与 INDEX | gpt-6-luna（max） | Sonnet |
| Verifier（Codex 兼容角色） | 只读检查验收证据、修改边界与同步 | gpt-6-luna（max） | — |

推荐值是起点，不是质量保证。角色身份与执行模型相互独立；实际运行的模型以 Host 的观测为准，而不是配置文件。

这些只是推荐。为每个角色选择模型是 Controller 的职责，在用户写入任务的约束之内可以自由选择；在 Adapter 支持时（如 Claude Code 的 `register-role`），Controller 也可以注册新角色。用户也可以让 Controller 独自完成全部工作：是否委派、委派多少，由用户决定。

## 实测观察

**这项基准测什么：** 我们有意挑了一个很难的单轮重构任务：桌面与 WebUI 共享 Live2D 行为，涉及模型选择、语音/动作队列和退出生命周期。比较的不是候选还剩几个 bug，而是原始需求能否持续约束调查、方案收敛、实现和验证，尤其是检查是否覆盖真实消费者路径、反证是否推动方案修正。A/B 是单代理样本，C/D 提供协作执行对照。

**结果要这样读：** 冻结候选接受独立产品后审；表中把原运行内的独立审查/修复与冻结后的后审分开。A/B 的原运行没有独立 Reviewer；它们后来接受 GPT-6.1 Sol/high 独立后审，不能算作组内自审或修复。A/B 保留原报告的高/中严重度标签和 V3 覆盖不足结论，不换算为本表的 P1/P2。各样本都有未闭合的需求，其中一些在起始代码里已经存在；缺陷数量不是质量总分。

| 样本（原执行日期） | 执行方式 | 原运行内独立审查/修复 | 冻结后独立后审结果 | P1 | P2 | 用时 | API 等价费 |
|---|---|---|---|---:|---:|---:|---:|
| A · 10/03 | 单代理 Sol/medium | 无 | 10/14–15：NOT_READY；1 高、2 中，另有 V3 renderer 覆盖不足 | — | — | 21.6 分 | $0.88 |
| B · 10/03 | 单代理 Luna/xhigh | 无 | 10/14–15：NOT_READY；2 高、3 中 | — | — | 54.1 分 | $0.23 |
| C · 10/14 | Luna 多代理 | 有，局部 | NOT_READY | 2 | 3 | 57.1 分 | $0.46 |
| D · 10/14 | Sol + Luna 多代理 | 有 | NOT_READY | 1 | 2 | 40.4 分 | $2.62 |
| C · 10/19 | Luna（派发被拒，回退单代理） | 无 | NOT_READY | 3 | 3 | 19.8 分 | $0.22 |
| **D · 10/19** | **Sol + Luna 原生多代理** | **有，两个反证触发修复** | **PARTIALLY SUPPORTED / NOT_READY** | **0** | **3** | **34.4 分** | **$2.91** |

表中费用是 API 等价参考值，用于比较，不是实际账单。A/B 的原执行日期是 2026-10-03，冻结后才于 10/14–15 接受 GPT-6.1 Sol/high 独立后审；表中的高/中标签沿用原报告，没有换算为 P1/P2。

A 在 16:46 UTC 已形成共享行为策略加渲染器适配的跨端方向，随后把桌面音频等待和 WebUI 片段调度问题纳入实现；其最终相关 Python 套件报告 92 passed/1 deselected，前端 7 files/20 tests，build 和 lint 均退出成功。后审仍发现桌面转换入口会用 Sakiko costume 覆盖显式选择的自定义模型，Web 无音频呈现只保留最新动作。这说明较早形成整体方向、完成局部验证，仍可能遗漏实际消费者路径。B 花了更长时间做广泛调查，16:59 UTC 才明确列出缺口和共享目标/renderer 方案；之后修正测试夹具与 lint，并完成 84 个 Python、16 个前端测试和 build/lint。后审仍复现角色状态与取消 ingress 未完整消费、bye 未停止正在播放的音频，显示更多投入和通过的局部测试也没有闭合事件链与生命周期一致性。两次后审都是独立评估，不是 A/B 原运行中的 Reviewer。

因此，A/B 与 C/D 对照的是调查、方案收敛、原始需求保持、验证方案和反证后的修正；不是比较冻结后剩下多少个 bug。

**D · 10/19 发生了什么：**

```text
Controller 把耦合的设计与实现交给 Sol
  → Sol 自主派 Luna 调查运行时支持与测试边界
  → Sol 交回局部候选
  → Controller 没有把“局部完成”当作结束，发起独立审查
  → Reviewer 找到两个推翻局部结论的反例：
      · 用户显式选择的模型会被桌面旧规则覆盖
      · 退出告别指令可能在事件通道关闭后才发出
  → Controller 采纳反证，派修复与回归
```

D · 10/19 的独立外部后审没有发现 P0/P1，但报告了三类 P2，结论为 PARTIALLY SUPPORTED / NOT_READY，不构成完整产品验收。三类反例是：取消后到达的预入队片段仍可恢复播放；shutdown bye 后在途 producer 仍能发布，独立前端复现也会接受之后的片段；Web 按版本选择嘴型参数名，无法驱动拼写与版本默认值不同但实际受支持的别名，桌面按实际 parameter IDs 选择。过程中的原生代理状态冲突按 Codex 原生生命周期异常处理。

这正是 Thaliris 要验证的能力：**局部成功不等于全局结束，反证会实际改变后续工作。**

**C · 10/19 不是一次成功的多代理运行：** Luna 请求把整段对话历史传给子代理，被 Fresh Context 规则正确拒绝；它没有改用独立上下文重新派发，后续退回单代理完成。这个结果说明隔离保护在起作用，也显示关键调度节点需要足够强的模型。

**目前还不能证明的：** 每行都是单次运行，各批次的 Host 与模型 effort 不完全一致，不是单变量实验；混合配置总成本更高；D · 10/19 中审查与修复阶段的反证虽然实际推动了修复，但没有全部登记为正式 observation，Evidence Continuity 的持久化链路仍在完善中。详见 [ABCD 基准](benchmarks/abcd) 与[基准协议](docs/thaliris-benchmark-protocol.md)。

## 快速开始

需要 Python 3.11+。Git 可选；使用下方 Git URL 安装需要 Git。

```bash
uv tool install git+https://github.com/Iris0fTheValley/Thaliris
cd your-repository
thaliris-core --root . init
TASK_ID=$(thaliris-core --root . task-start "example task" | python -c 'import json,sys; print(json.load(sys.stdin)["task_id"])')
thaliris-core --root . --task-id "$TASK_ID" task-status
thaliris-core --root . --task-id "$TASK_ID" task-status --view compact --since-revision 1
```

失败时输出 `{"ok": false, "error": ...}`；结构化错误另带稳定的 `code`、`recovery` 提示和有界的 `details`（`TASK_REVISION_CONFLICT` 会列出 base revision 之后追加的内容）。

每个任务有独立的 Task ID，后续操作显式传入 `--task-id`。只安装 Core 不会启用多代理；需要原生集成时，按 [Codex](https://github.com/Iris0fTheValley/Thaliris-codex/blob/main/README.md)、[DSH](https://github.com/Iris0fTheValley/Thaliris-dsh) 或 [Claude Code](https://github.com/Iris0fTheValley/Thaliris-claude/blob/main/README.md) 指南安装。

初始化后的仓库：

```text
.agent-memory/   # 经选择、可跨任务复用的项目知识（可纳入版本控制）
.milestones/     # 长期进度：scope / decisions / progress / verification
.context/tasks/<task-id>/state.json   # 单个任务的状态与证据（默认被 Git 忽略）
```

任务状态保存结构化的事实、observation 和判断，不保存对话 transcript。持久化和交接是两个独立选择：记录下来的东西不会自动塞给每个角色。

## 不是什么

不是 Agent runtime、工作流引擎、固定多代理流水线、向量数据库或 RAG 系统、全仓自动总结器，也不能替代源码、测试、编译器和运行时行为。

删除 Thaliris，底层开发流程也不应因此变得不正确。

## 延伸阅读

- [DESIGN.md](DESIGN.md) — Core 架构与契约
- [路由协议](docs/thaliris-routing-protocol.md) — 路由、交接、Evidence Continuity、等待与验收
- [任务授权契约](docs/thaliris-task-authority.md)
- [项目身份](docs/thaliris-project-identity.md) — 版本化项目身份基线、challenge 与目的关系
- [提示词归属与研究动机](docs/thaliris-prompt-design.md) — 含相关文献
- [角色说明](docs/thaliris-role-packs.md) · [分包与 API 边界](docs/host-neutral-packaging.md)

## 开发与贡献

```bash
git clone https://github.com/Iris0fTheValley/Thaliris
cd Thaliris
uv run --extra test pytest
```

欢迎小而有证据的修改：可复现的路由失败、反证在交接中丢失的案例、provenance 或 freshness bug、角色隔离泄漏、真实 benchmark 结果，以及保持行为不变的简化。新增复杂度需要一个现有架构解决不了的具体失败案例来证明。

MIT License，见 [LICENSE](LICENSE)。
