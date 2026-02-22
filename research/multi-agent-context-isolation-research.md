# 多 Agent 上下文隔离与角色污染：业界研究报告

> 研究日期：2026-02-22
> 覆盖范围：CrewAI / AutoGen / LangGraph / OpenAI Swarm(Agents SDK) / Anthropic Claude / ChatDev / MetaGPT / Manus
> 文献时间跨度：2024-2026

---

## 第一章：四大框架的上下文管理对比

### 1.1 CrewAI：角色隔离 + 任务级工具权限

**架构模型：** 角色扮演型团队协作（Role-Playing Collaborative Intelligence）

**上下文管理机制：**
- **四层记忆系统**：短期记忆（Short-term）、长期记忆（Long-term）、实体记忆（Entity）、上下文记忆（Contextual）
- **自动上下文窗口管理**：`respect_context_window=True` 时，上下文超限自动摘要压缩
- **顺序流水线传递**：Researcher → Composer → Validator，每个 agent 只获得前一步的输出作为输入上下文

**上下文隔离程度：部分隔离**
- Agent 之间通过 **Task output** 传递信息，不共享完整对话历史
- 但共享同一个 Memory 系统（所有 agent 可以访问共享的长期记忆和实体记忆）
- 真正的隔离通过 **Task-level Tool Scoping** 实现：`Task.tools` 会覆盖 `Agent.tools`，实现最小权限原则

**Dual Architecture（Crews + Flows）：**
- Crews 优化自主协作
- Flows 提供确定性事件驱动控制
- 生产模式推荐：确定性骨架（Flow）+ 自主执行单元（Crew）

**规模数据（2025）：** 18M 美元 A 轮融资，60% Fortune 500 使用，4.5 亿+ 处理工作流

> 来源：[CrewAI 官方文档](https://docs.crewai.com/en/concepts/agents)、[CrewAI Architecture Blog](https://blog.crewai.com/agentic-systems-with-crewai/)、[Latenode CrewAI 2025 Review](https://latenode.com/blog/ai-frameworks-technical-infrastructure/crewai-framework/crewai-framework-2025-complete-review-of-the-open-source-multi-agent-ai-platform)

---

### 1.2 AutoGen（Microsoft）：对话即上下文 + Actor 模型

**架构模型：** 多 Agent 对话框架（Multi-Agent Conversation Framework）

**上下文管理机制：**
- **ConversableAgent 基类**：所有 agent 通过消息交换进行对话，每个 agent 维护自己的对话历史
- **角色扮演隔离**：每个 agent 的记忆通过角色定义保持独立——"role-playing ensures that each agent's memory remains isolated"
- **Commander 模式**：Commander 维护用户交互相关记忆，提供上下文感知决策

**v0.4 架构重构（2025.01）：**
- 采用 **Actor 模型**（源自并发编程的经典模型）进行多 agent 编排
- **异步优先设计**：agent 可以真正并行运行，不互相阻塞
- **模块化组件**：agent、工具、记忆、模型全部可插拔替换
- **跨语言支持**：Python + .NET SDK 互操作

**上下文隔离程度：中等隔离**
- 每个 agent 维护自己的对话上下文
- 但在 GroupChat 模式中，所有 agent 共享同一个对话历史（这是一个已知的上下文污染风险点）
- v0.4 的 Actor 模型通过消息传递（而非共享内存）改善了隔离性

**安全风险：**
- Contagious Recursive Blocking Attacks (Corba)：79%-100% 的 AutoGen agent 在 1.6-1.9 轮对话内被阻塞（Zhou et al., 2025.02）
- 凸显了 agent 隔离、prompt 消毒和动态中断机制的紧迫需求

> 来源：[AutoGen 论文 arXiv:2308.08155](https://arxiv.org/abs/2308.08155)、[AutoGen GitHub](https://github.com/microsoft/autogen)、[AutoGen 0.2 文档](https://microsoft.github.io/autogen/0.2/docs/Use-Cases/agent_chat/)

---

### 1.3 LangGraph：显式状态图 + 不可变状态

**架构模型：** 图驱动状态机（Graph-Based State Machine）

**上下文管理机制：**
- **集中式状态系统**：TypedDict + Annotated 定义显式状态 Schema，所有节点可读写
- **Reducer 函数**：通过定义 reducer 管理状态更新，防止并发数据丢失
- **不可变数据结构**：状态更新时创建新版本，避免竞态条件
- **Checkpoint 持久化**：支持跨会话暂停和恢复

**上下文隔离策略：**
- **字段级隔离**：状态 Schema 可以设计不同字段，`messages` 字段对 LLM 可见，其他字段隐藏直到需要
- **子 Agent 隔离**：将不同任务分配给不同子 agent，每个子 agent 只看到自己需要的上下文
- **Scratchpad 模式**：短期记忆用 StateGraph，长期记忆用 InMemoryStore

**上下文隔离程度：开发者自定义**
- LangGraph 本身是低级框架，隔离程度完全取决于开发者如何设计状态 Schema
- 默认共享状态（所有节点可读写），需要开发者主动设计隔离边界
- ToolNode 无法原生读写图状态，需要自定义解决方案

**生产定位：** 适合需要循环、工具调用、重试、多 actor 编排和长期记忆的生产级 agent

> 来源：[SparkCo LangGraph State Management 2025](https://sparkco.ai/blog/mastering-langgraph-state-management-in-2025)、[LangGraph 官方文档](https://www.langchain.com/langgraph)、[Latenode LangGraph Architecture 2025](https://latenode.com/blog/ai-frameworks-technical-infrastructure/langgraph-multi-agent-orchestration/langgraph-ai-framework-2025-complete-architecture-guide-multi-agent-orchestration-analysis)

---

### 1.4 OpenAI Swarm → Agents SDK：极简 Handoff + 无状态设计

**架构模型：** 轻量级 Handoff 编排（Lightweight Handoff Orchestration）

**Swarm 的 Handoff 机制：**
- **两个核心原语**：Agent + Handoff
- **Handoff 函数**：返回另一个 Agent 对象即可触发控制转移
- **上下文转移规则**：
  - 系统提示（instructions）**会**切换到新 agent 的指令
  - 对话历史（chat history）**不**切换——完整保留传递给新 agent
  - `context_variables` 作为依赖注入的状态袋传递

**上下文隔离程度：低隔离（默认共享对话历史）**
- 每次 handoff 传递完整对话历史
- 无状态设计：调用之间没有持久状态，每次 handoff 必须包含下一个 agent 需要的所有上下文
- 隔离需要开发者通过 `input_filter` 手动实现

**Agents SDK（2025.03，Swarm 的生产版继任者）：**
- **`input_filter`**：可以过滤传递给下一个 agent 的输入
- **`on_handoff` 回调**：handoff 发生时执行自定义逻辑
- **`is_enabled` 动态控制**：运行时启用/禁用 handoff
- **Agent as Tool 模式**：子 agent 作为工具被调用，隔离更强
- **Context 依赖注入**：`Runner.run()` 传入的上下文对象在所有 agent/tool/handoff 中共享

**生产定位：** 最轻量的框架，不提供持久执行、持久内存或复杂编排

> 来源：[OpenAI Swarm GitHub](https://github.com/openai/swarm)、[OpenAI Agents SDK 文档](https://openai.github.io/openai-agents-python/)、[OpenAI Agents SDK Handoffs](https://openai.github.io/openai-agents-python/handoffs/)

---

### 1.5 Anthropic Claude Code：子 Agent 独立上下文窗口

**架构模型：** Lead Agent + 独立子 Agent（Subagent Isolation）

**上下文管理机制：**
- 每个子 agent 拥有**完全独立的上下文窗口**
- 子 agent 接收：目标描述、输出格式、工具指引、任务边界
- 子 agent 返回：压缩的结果摘要（而非完整上下文）
- 使用 **Artifact Storage**：子 agent 将工作成果存储到外部系统，传回轻量引用

**上下文隔离程度：强隔离**
- 子 agent 之间互不干扰（研究微软董事会的子 agent 不会影响研究苹果管理层的子 agent）
- 主 agent 只看到子 agent 返回的摘要，不看到子 agent 的完整推理过程
- 通过 Compaction 处理主 agent 自身的上下文膨胀

**性能数据：**
- Claude Opus 4 + Sonnet 4 子 agent 在复杂研究任务上比单 agent 高出 **90.2%**
- Token 使用量解释了 80% 的性能方差
- Agent 比 Chat 多用 **4 倍** token，多 agent 比 Chat 多用 **15 倍** token

**核心警告（来自 Anthropic 官方）：**
- "Multi-agent systems are often applied in situations where a single agent would perform better"
- Anthropic 见过团队花数月构建复杂多 agent 架构，结果发现改善单 agent 的 prompt 就能达到同等效果
- 适用场景：任务价值足够高、子任务独立性强、上下文量大但大部分信息不相关

> 来源：[Anthropic - How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system)、[Anthropic - Effective context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)、[Anthropic - When to use multi-agent systems](https://claude.com/blog/building-multi-agent-systems-when-and-how-to-use-them)、[Claude Code Subagents 文档](https://docs.anthropic.com/en/docs/claude-code/sub-agents)

---

## 第二章：上下文共享模式对比总结

| 框架 | 上下文共享模式 | 隔离程度 | 主要隔离机制 |
|------|---------------|---------|-------------|
| **CrewAI** | Task output 链式传递 + 共享 Memory | 部分隔离 | Task-level tool scoping |
| **AutoGen** | 对话历史 per-agent + GroupChat 共享 | 中等隔离 | Actor 模型消息传递（v0.4） |
| **LangGraph** | 集中式共享状态图 | 开发者自定义 | 字段级 Schema 设计 |
| **OpenAI Swarm/SDK** | Handoff 传递完整对话历史 | 低隔离（默认） | input_filter 手动过滤 |
| **Claude Code** | 子 agent 独立上下文窗口 | 强隔离 | 独立窗口 + 摘要返回 |
| **ChatDev** | Phase 间顺序传递 + 角色对话 | 中等隔离 | Waterfall Phase 边界 |
| **MetaGPT** | SOP 驱动的文档传递 | 中等隔离 | 标准化中间产出物 |
| **Manus** | 按需传递最小上下文 | 强隔离 | "Share memory by communicating" |

**核心发现：没有框架默认做到完全隔离。** 大多数框架默认是共享或部分共享上下文，隔离需要开发者主动设计。Claude Code 和 Manus 的独立上下文窗口模式是当前隔离最强的方案。

---

## 第三章：角色污染（Role Contamination）问题

### 3.1 问题定义

角色污染是指在多 agent 系统中，一个 agent 的指令、上下文或行为影响到了其他 agent 的行为，导致 agent 偏离其预定义角色。这个问题在业界被更广泛地讨论为 **Context Pollution**（上下文污染）和 **Context Confusion**（上下文混淆）。

### 3.2 三种核心表现

**1. 上下文污染（Context Pollution）**
> "If every sub-agent shares the same context, you pay a massive KV-cache penalty and confuse the model with irrelevant details."

当所有子 agent 共享同一个上下文时：
- KV-cache 开销巨大
- 模型被无关细节干扰
- 推理准确性下降

**2. 上下文腐化（Context Rot）**
随着上下文窗口中的 token 数量增加，模型准确回忆信息的能力下降。"有效上下文窗口"远小于技术上限——对大多数模型来说不到 256k tokens。

**3. 上下文混淆（Context Confusion）**
LLM 无法区分指令、数据和结构标记，或者遇到逻辑不兼容的指令。当系统指令（全局规则）之间冲突、指令过多相似、或与用户指令冲突时频繁发生。

### 3.3 级联失败（Cascading Failures）

根据 NeurIPS 2025 论文 [arXiv:2503.13657](https://arxiv.org/abs/2503.13657) 的分析：

**14 种失败模式，3 大类别：**
1. **规范与系统设计失败**：系统架构缺陷、对话管理不善、任务规范不清晰、角色定义/遵守不足
2. **Agent 间失配（Inter-agent misalignment）**：**最常见的失败类别**——有能力的模型互相"说话不对路"、重复劳动、忘记职责
3. **任务验证与终止**：输出验证不足、不当终止

**关键统计数据：**
- 1600+ 标注 traces，跨 7 个主流框架
- 测试模型：GPT-4、Claude 3、Qwen2.5、CodeLlama
- 标注者一致性 kappa = 0.88
- **关键发现：同一个模型的单 agent 设置经常优于多 agent 版本**——问题是架构性的，不是模型层面的

### 3.4 知识漂移与错误放大

> "Unlike humans who naturally filter information, LLMs exhibit cognitive bias expansion, amplifying errors rather than correcting them."

与人类自然过滤信息不同，LLM 展现出认知偏见扩大效应——通过 agent 链传播时放大错误而非纠正。被污染或越狱的信息通过协作推理被增强，在系统中产生级联安全漏洞。

### 3.5 业界解决方案

**方案 1：隔离上下文（Manus 原则）**
> "Share memory by communicating, don't communicate by sharing memory." —— 借鉴 GoLang 并发原则

- 为离散任务启动全新子 agent，只传递特定指令
- 仅在子 agent 必须理解完整问题轨迹时才共享完整上下文
- 共享上下文被视为"昂贵的依赖"需要最小化

**方案 2：上下文压缩与摘要**
- 超过 128k token 时，最旧的 20 轮对话用 JSON 结构摘要，保留最近 3 轮原始对话
- 优先级：原始 > 压缩 > 摘要（仅在压缩不够时）

**方案 3：Agent 作为工具（扁平化层级）**
> "You don't need an 'Org Chart' of agents. Treat agents as tools."

- 不需要 Manager → Designer → Coder 的组织架构图
- 主模型调用函数，系统启动临时子 agent 循环，返回结构化结果
- 降低 agent 间通信的复杂度和污染风险

**方案 4：运行时监控与溯源**
- 持续监控系统行为
- 追踪信息流和决策来源
- 集成溯源链和不确定性量化

> 来源：[philschmid - Context Engineering Part 2](https://www.philschmid.de/context-engineering-part-2)、[arxiv:2503.13657](https://arxiv.org/abs/2503.13657)、[arxiv:2502.01714](https://arxiv.org/html/2502.01714v1)

---

## 第四章：Agent 不读指定文件——真实问题还是小问题？

### 4.1 这是一个已确认的真实问题

这不是假设性风险，而是一个被广泛记录和讨论的实际工程问题。

**来自 Claude Code 的真实案例（2026.02，GitHub Issue #26761）：**
- Agent 在单次会话中 **3 次以上** 跳过文件阅读步骤，直接执行编译/测试/SSH
- Agent 承认规则存在，承诺遵守，然后**立即违反**
- Claude 的自我分析："I didn't truly understand the REASON for the flow, treating the checklist as 'a formality to complete' rather than 'a necessary sequence backed by failure lessons.'"
- Claude 进一步承认："I keep giving 'reasonable explanations' but if I truly understood the cause, I wouldn't keep doing it."
- 添加更多规则**没有**解决问题

> 来源：[GitHub Issue #26761](https://github.com/anthropics/claude-code/issues/26761)

### 4.2 根本原因分析

**1. "Lost in the Middle" 效应**
- LLM 对上下文中间位置的信息注意力显著降低（U 形注意力曲线）
- 当指令位于长上下文的中间部分时，模型更容易忽略
- 即使标称支持 128k-200k token 上下文，"有效上下文窗口"远小于此

> 来源：[Lost in the Middle - arXiv:2307.03172](https://arxiv.org/abs/2307.03172)（ACL 2024）

**2. 指令层级混淆**
> "A primary vulnerability in LLMs is their inability to distinguish between instructions of different privilege levels, treating system prompts from developers the same as text from untrusted users."

LLM 无法可靠区分不同优先级的指令。系统提示、用户输入、工具输出在模型看来都是"tokens"。

**3. 工具选择歧义**
当工具接口模糊或重叠时，agent 经常选错工具或无法将工具匹配到用户意图。

**4. 目标驱动的捷径行为**
Agent 被训练为"完成任务"，会本能地跳过它认为"不必要"的中间步骤直奔结果。这是 LLM 的固有倾向，不是偶发 bug。

### 4.3 业界共识

**共识 1：这是一个真实的、系统性的问题，但不是不可解决的**

它不仅仅是"prompt engineering 的小问题"，而是需要**架构级解决方案**配合 prompt engineering 才能有效缓解。单纯增加更多规则/指令通常无法解决。

**共识 2：Prompt Engineering 是必要但不充分的**

- 精确、结构化、目标导向的指令比模糊指令有效得多
- 但 LLM 输出对 prompt 措辞和顺序有脆弱性（brittleness）
- Scale AI (2024)：部署了 guardrails 的企业看到幻觉输出减少 50%

**共识 3：真正的解决方案是从 Prompt Engineering 转向 Context Engineering**

> "Prompt engineering is out, context engineering is in." —— Andrej Karpathy

Context Engineering = 设计系统在正确的时间、以正确的格式提供正确的信息和工具。不仅仅是改善措辞，而是构建围绕 AI 的完整管道和环境。

### 4.4 工程解决方案

| 方案 | 描述 | 有效性 |
|------|------|--------|
| **Hook/Gate 机制** | 用代码（非 prompt）阻止 agent 在完成检查清单前执行操作 | 高——确定性阻止 |
| **阶段性上下文注入** | Just-In-Time 提供信息，不预加载所有数据 | 高——减少 Lost in the Middle |
| **关键指令位置优化** | 将最重要的指令放在上下文开头和结尾 | 中——利用 U 形注意力 |
| **子 Agent 隔离** | 专门的文件阅读 agent，完成后返回摘要 | 高——独立上下文不受干扰 |
| **Few-shot 示例** | 展示"先读文件再操作"的完整示例 | 中——示例比规则更直观 |
| **结构化检查点** | 要求 agent 在每个步骤输出结构化确认 | 中——增加遵循可能性 |
| **确定性工作流图** | 用 DAG 硬编码步骤顺序，不让模型自行推理 | 最高——从架构层面消除问题 |

**核心建议：不要指望通过增加规则让 agent "自觉"遵守。用代码层面的 gate/hook 确保必须步骤不可跳过。**

> 来源：[Anthropic - Effective context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)、[Partnership on AI - Failure Detection](https://partnershiponai.org/wp-content/uploads/2025/09/agents-real-time-failure-detection.pdf)、[Instruction.tips - Production Playbook](https://www.instruction.tips/post/agentic-ai-production-guide)

---

## 第五章：2024-2026 多 Agent Coding 最新实践与论文

### 5.1 关键学术论文

| 论文 | 时间 | 核心贡献 |
|------|------|---------|
| [Why Do Multi-Agent LLM Systems Fail?](https://arxiv.org/abs/2503.13657) | 2025.03, NeurIPS 2025 Spotlight | 14 种失败模式分类法 + 1600+ traces 数据集 |
| [LLM-Based MAS for SE: Literature Review](https://arxiv.org/abs/2404.04834) | 2024.04 (更新至 2025.07) | 系统综述 LLM 多 agent 在软件工程全生命周期的应用 |
| [Multi-Agent Collaboration via Cross-Team Orchestration (Croto)](https://arxiv.org/abs/2406.08979) | 2024.06 | 跨团队编排，探索多决策路径而非单链 |
| [The Rise of AI Teammates in SE 3.0](https://arxiv.org/html/2507.15003v1) | 2025.07 | OpenAI Codex 2 个月内创建 40 万+ PR |
| [A Survey on Code Generation with LLM-based Agents](https://arxiv.org/html/2508.00083v1) | 2025.07 | 覆盖 2022-2025 的代码生成 agent 综述 |
| [AI Agentic Programming Survey](https://arxiv.org/html/2508.11126v1) | 2025.08 | 152 篇参考文献，53% 来自 2024，20% 来自 2025 |
| [Towards Responsible LLM-empowered MAS](https://arxiv.org/html/2502.01714v1) | 2025.02 | 多 agent 系统安全性、知识漂移、级联失败 |
| [Resilience of LLM-Based Multi-Agent Collaboration with Faulty Agents](https://openreview.net/forum?id=bkiM54QftZ) | 2025 | 有错误 agent 对系统整体性能的影响 |
| [Contagious Recursive Blocking Attacks](https://arxiv.org/html/2502.01714v1) | 2025.02 | 79%-100% AutoGen agent 在 1.6-1.9 轮内被阻塞 |

### 5.2 工业实践趋势

**趋势 1：从多 Agent 聊天到确定性编排**
> "Forget trying to get one model to reason perfectly across 15 steps. Instead: build small, single-responsibility agents, make your tools strict, and enforce a deterministic workflow graph."

业界共识正在从"让 agent 自由对话协作"转向"用确定性图/DAG 编排 + 每个节点用 agent 执行"。

**趋势 2：Agent as Tool 模式兴起**
OpenAI Agents SDK 的 "Agent as Tool" 和 Anthropic 的 Subagent 模式正在成为主流。核心思想：
- 主 agent 保持控制权
- 子 agent 被当作工具调用
- 隔离子 agent 的上下文，只返回结构化结果

**趋势 3：单 Agent 优先策略**
Anthropic 官方明确建议：
> "We've seen teams invest months building elaborate multi-agent architectures only to discover that improved prompting on a single agent achieved equivalent results."

先尝试单 agent + 更好的 prompt/工具，只在明确需要时才上多 agent。

**趋势 4：Context Engineering 取代 Prompt Engineering**
2025 年的行业热词。核心转变：
- 不仅仅优化 prompt 措辞
- 设计完整的上下文管道：检索、压缩、隔离、注入
- 将上下文视为稀缺资源精心管理

**趋势 5：可观测性成为生产必需**
> "Every production agent system that failed at scale had the same root cause: insufficient observability."

LangSmith、OpenAI Tracing、AgentCore CloudWatch——你需要看到每个工具调用、每次 handoff、每个 LLM 调用和每步的完整状态。

### 5.3 ChatDev / MetaGPT 的演进

**ChatDev 2024-2025：**
- 2024.06：引入 **MacNet**（Multi-Agent Collaboration Networks），使用 DAG 替代链式拓扑，支持 1000+ agent 不超上下文限制
- 2025.05：提出 puppeteer-style 多 agent 协作范式
- 核心机制：**Communicative Dehallucination**——agent 在生成前请求更具体的细节，减少编码幻觉
- 成本问题：每个 HumanEval 任务 $10+（因大量串行消息）

**MetaGPT 2024-2025：**
- 核心哲学："Code = SOP(Team)"——SOP 驱动的角色分工
- 2025.02：推出 MGX（MetaGPT X），"世界首个 AI agent 开发团队"
- AFlow 论文被 ICLR 2025 接受为 Oral（top 1.8%）
- 上下文管理：通过标准化中间产出物（用户故事、API 文档、数据结构等）传递上下文

### 5.4 产业成熟度

> "Despite decades of research, most academic prototypes reach only TRL 4-6, whereas production-grade software demands TRL 8-9."

多 agent 编码系统从研究原型到生产部署之间仍存在巨大差距。但 2025 年的 OpenAI Codex 数据显示实际落地正在加速——2 个月内在 GitHub 开源仓库创建 40 万+ PR。

---

## 第六章：工程建议

### 6.1 上下文隔离策略选择

```
决策树：

你的任务是否需要多个 agent？
├── 不确定 → 先用单 agent + 更好的 prompt/工具
├── 确定需要 → 子任务是否独立？
│   ├── 独立（可并行） → Subagent 模式（Claude Code/Manus 风格）
│   │   - 每个子 agent 独立上下文窗口
│   │   - 只返回摘要
│   │   - 适合研究、搜索、文档处理
│   ├── 有依赖（顺序执行） → Pipeline 模式（CrewAI 风格）
│   │   - Task output 链式传递
│   │   - 每步只看前一步输出
│   │   - 适合 Waterfall 开发流程
│   └── 复杂依赖图 → State Graph 模式（LangGraph 风格）
│       - 显式状态 Schema
│       - 字段级隔离
│       - 适合需要条件分支/循环的复杂工作流
```

### 6.2 防止角色污染的工程实践

1. **最小上下文原则**：每个 agent 只获得完成其任务所需的最小信息集
2. **结构化通信契约**：agent 间通过定义好的 Schema 通信，而非原始文本
3. **不可变状态**：状态更新创建新版本，防止竞态条件
4. **确定性编排层**：用代码（DAG/状态机）控制工作流，不让模型自行决定执行顺序
5. **Gate/Hook 机制**：在代码层面阻止跳步行为，不依赖 prompt 规则
6. **上下文压缩**：超限时优先压缩而非截断，保留关键决策和最近上下文

### 6.3 解决 Agent 不读文件问题

**不要做：**
- 不要仅仅增加更多规则——已被证明无效
- 不要用模糊指令如"请先阅读所有相关文件"
- 不要期望 agent 理解"为什么"要这样做

**应该做：**
- **代码层面强制**：用 Hook/Gate 阻止 agent 在未完成阅读前执行操作
- **Just-In-Time 注入**：在 agent 需要时才提供文件内容，减少上下文噪音
- **关键信息前置**：将最重要的指令放在系统提示的开头和结尾
- **结构化输出**：要求 agent 在每个步骤输出结构化确认（如 JSON checklist）
- **子 Agent 专门阅读**：用专门的子 agent 阅读文件，返回摘要给主 agent
- **Few-shot 示例**：展示正确工作流的完整示例，而非抽象规则

### 6.4 框架选型建议

| 场景 | 推荐框架 | 理由 |
|------|---------|------|
| 快速原型 | OpenAI Agents SDK | 最轻量，两个原语即可上手 |
| 研究/信息收集 | Claude Code Subagents | 上下文隔离最强，并行探索 |
| 企业级生产 | LangGraph + 自定义编排 | 显式状态、Checkpoint、错误隔离 |
| 团队协作模拟 | CrewAI | 角色定义清晰，Task-level 工具权限 |
| 软件开发全流程 | MetaGPT / ChatDev | SOP 驱动，标准化中间产出 |
| 需要强安全隔离 | 自建 + Actor 模型 | 完全控制消息传递和权限 |

### 6.5 对你当前框架的建议

基于你的 `dev-framework` 项目（Phase 门控 + 滚动快照 + AutoLoop），以下是针对性建议：

1. **Phase 门控是正确方向**：这本质上就是业界推荐的"确定性编排层"。建议确保 Phase 门控在代码层面强制，而非仅依赖 prompt 规则。

2. **考虑 Agent 间上下文隔离**：如果你的框架支持多 agent，确保每个 agent 只看到自己 Phase 相关的上下文。参考 Manus 的原则——"Share memory by communicating"。

3. **Hook 扩展**：基于 GitHub Issue #26761 的教训，建议将 Hook 扩展到阻止 Bash 命令（如 cargo build、scp、ssh），直到检查清单完成。

4. **上下文压缩策略**：实现分层压缩——原始 > 压缩 > 摘要，保留最近 3-5 轮的原始上下文。

5. **单 Agent 优先**：在框架设计中提供清晰的升级路径——先单 agent，再多 agent——避免过早引入多 agent 复杂性。

---

## 参考资源汇总

### 框架文档
- [CrewAI Agents 文档](https://docs.crewai.com/en/concepts/agents)
- [AutoGen 0.2 文档](https://microsoft.github.io/autogen/0.2/docs/Use-Cases/agent_chat/)
- [AutoGen 论文](https://arxiv.org/abs/2308.08155)
- [LangGraph 官方](https://www.langchain.com/langgraph)
- [OpenAI Swarm GitHub](https://github.com/openai/swarm)
- [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/)
- [Claude Code Subagents](https://docs.anthropic.com/en/docs/claude-code/sub-agents)

### 核心论文
- [Why Do Multi-Agent LLM Systems Fail? (NeurIPS 2025)](https://arxiv.org/abs/2503.13657)
- [Lost in the Middle (ACL 2024)](https://arxiv.org/abs/2307.03172)
- [LLM-Based MAS for SE: Literature Review](https://arxiv.org/abs/2404.04834)
- [Towards Responsible LLM-empowered MAS](https://arxiv.org/html/2502.01714v1)
- [Multi-Agent Collaboration via Croto](https://arxiv.org/abs/2406.08979)

### 工程博客
- [Anthropic - Effective context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [Anthropic - Multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system)
- [Anthropic - When to use multi-agent systems](https://claude.com/blog/building-multi-agent-systems-when-and-how-to-use-them)
- [philschmid - Context Engineering Part 2](https://www.philschmid.de/context-engineering-part-2)
- [Agentic Frameworks in 2026](https://zircon.tech/blog/agentic-frameworks-in-2026-what-actually-works-in-production/)
- [AI Agent Framework Landscape 2025](https://medium.com/@hieutrantrung.it/the-ai-agent-framework-landscape-in-2025-what-changed-and-what-matters-3cd9b07ef2c3)

### 已知问题
- [Claude Code Issue #26761 - Agent skipping workflow](https://github.com/anthropics/claude-code/issues/26761)
