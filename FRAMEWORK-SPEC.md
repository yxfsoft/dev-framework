# Dev-Framework 规格书

> 版本: v3.0 | 更新日期: 2026-02-21
> 统一多代理协作开发框架 — 覆盖首次开发与多轮迭代

---

## 一、框架目标

提供一套标准化、可复用的多代理协作开发框架，使得：

1. **新项目**：输入需求文档，经框架流程产出生产级代码
2. **老项目**：输入变更需求，经框架流程产出增量代码变更
3. **质量一致**：首次开发和迭代开发遵循相同的质量标准
4. **可持续**：会话中断、上下文压缩、人员切换均不丢失信息

---

## 二、核心原则（不可违反）

### P1: 需求拆解必须达到行业最优标准

需求拆解不是功能罗列。Analyst Agent 必须基于行业最佳实践，输出资深工程师级别的技术方案。
拆解结果必须是高完成度的最优方案，绝不产出简陋的"能用"版本。

每个需求必须经过八维度检查：

| 维度 | 必须回答的问题 |
|------|---------------|
| 功能完整性 | 正常流 + 异常流 + 边界情况全部覆盖了吗？ |
| 用户体验 | 操作流程是否符合直觉？反馈是否及时？错误提示是否有指导性？ |
| 健壮性 | 所有外部输入有校验？错误路径有处理？资源有释放？ |
| 可观测性 | 关键路径有日志？错误有上下文信息？有性能指标？ |
| 可配置性 | 硬编码参数是否抽到配置？开关是否可控？ |
| 性能意识 | 有 O(n²) 隐患吗？内存无限增长吗？阻塞主线程吗？ |
| 安全意识 | 输入可注入吗？权限最小化了吗？敏感数据暴露了吗？ |
| 可测试性 | 可独立测试吗？依赖可注入吗？ |

### P2: 默认禁止 Mock

Mock 仅在以下白名单场景允许使用（必须在代码中声明理由）：

- 付费外部 API（Claude API 等）— 但必须有一个对应的真实 API E2E 测试
- CI 环境无硬件（GPU、麦克风等）— 但真机测试必须用真实硬件
- 第三方不可控服务（Shizuku、Outlook COM 等）— 但真机测试必须用真实服务

以下场景禁止 Mock：

- 本地文件系统 → 使用 tmp_path 真实读写
- SQLite → 使用 :memory: 或临时文件
- Milvus → 使用真实实例 + 测试 Collection
- 自有 HTTP API → 使用 TestClient 真实启动
- 配置加载 → 使用临时配置文件

### P3: 磁盘状态为唯一真相源

对话上下文是短期工作记忆，磁盘状态文件是持久长期记忆。
任何关键信息必须在产生时立即写入磁盘。
任何 session 都可以仅通过读取磁盘文件完整恢复上下文。

### P4: Agent 不可自评通过

开发 Agent 只能将任务标记为 `ready_for_verify`，不能标记为 `PASS` 或 `ready_for_review`。
Verifier Agent 独立执行验收后可标记为 `ready_for_review` 或 `rework`。
只有 Review Agent 或质量门控脚本才能将任务标记为 `PASS`。
Review Agent 可以将任务打回 `rework`。

### P5: 垂直切片 + 基础设施分层

首次开发采用"基础设施层 + 垂直切片"策略：
- Phase 0 搭建所有共享基础设施（DB、配置、API 骨架等），此后冻结
- 后续每个切片是一条完整的端到端数据流
- 切片间通过独立验证脚本保证互不干扰

迭代开发按 Change Request 粒度执行，每个 CR ≤ 5 个文件改动。

### P6: 需求交互式确认

接收到需求后，必须先评估成熟度，然后询问用户：
- A) 需求已明确，直接进入拆分
- B) 需要协助完善后再拆分
- C) 用户补充信息

不可跳过此确认环节。

---

## 三、架构概览

### 3.1 两种运行模式

```
模式 A: init-mode（首次开发）
  空项目 + 需求文档 → 框架流程 → 完整项目代码

模式 B: iterate-mode（迭代开发）
  已有项目 + 变更需求 → 框架流程 → 增量代码变更
```

首次开发等同于 iter-0（在空项目上的首轮迭代）。
迭代 ID 统一使用 `iter-N` 格式（N 从 0 开始），状态文件目录：`.claude/dev-state/iter-N/`。

### 3.2 Agent 角色

| Agent | 权限 | 核心职责 |
|-------|------|---------|
| Leader | 全部 | 编排协调、任务分配、进度管控、用户交互 |
| Analyst | 只读代码 + 写文档/脚本 | 需求深化、影响分析、任务拆分、生成 verify 脚本 |
| Developer | 读写代码 | 编码实现 + L1 测试 + 基线回归 |
| Verifier | 只读代码 + 运行验证 + 写 evidence | 独立验收执行（L0）+ 证据收集 |
| Reviewer | 只读代码 + 运行测试 + 更新任务状态 | 独立审查 + L2 验证 + 打回权 |

**权限分离矩阵**：

```
           | 读代码 | 写代码 | 改 verify | 改任务 | 写 evidence | 标 PASS |
-----------|--------|--------|----------|--------|------------|---------|
Leader     |   ✓    |   ✓    |    ✓     |   ✓    |     ✓      |    ✓    |
Analyst    |   ✓    |   ✗    |    ✓     |   ✓    |     ✗      |    ✗    |
Developer  |   ✓    |   ✓    |    ✗     | status+notes+commits |     ✗      |    ✗    |
Verifier   |   ✓    |   ✗    |    ✗     | status+evidence |     ✓      |    ✗    |
Reviewer   |   ✓    |   ✗    |    ✗     |   ✓    |     ✗      |    ✓    |
```

### 3.3 工作流阶段

框架工作流分为 Phase 0（环境就绪）→ Phase 1（需求接收与深化）→ Phase 2（影响分析与任务拆分）→ Phase 3（开发执行）→ Phase 3.5（独立验收）→ Phase 4（审查验收）→ Phase 5（交付）共七个阶段。各阶段的详细步骤、门控条件和 Agent 行为协议，详见运行时 `.claude/CLAUDE.md`（由 `CLAUDE-framework.md.tmpl` 生成）。

---

## 四、状态管理与上下文连续性

### 4.1 状态文件体系

```
{project}/.claude/dev-state/
├── session-state.json       # 当前 session 运行状态
├── baseline.json            # 基线测试结果
├── context-snapshot.md      # 滚动上下文快照（跨会话恢复用）
├── run-config.yaml          # 运行模式配置
└── {iteration-id}/          # 每轮迭代独立目录（iter-0、iter-1 ...）
    ├── manifest.json        # 迭代元信息
    ├── requirement-raw.md   # 用户原始需求
    ├── requirement-spec.md  # 细化后的需求规格
    ├── impact-analysis.md   # 影响分析
    ├── tasks/CR-xxx.yaml    # 任务列表
    ├── verify/CR-xxx.py     # 验收脚本（Analyst 生成，不可修改）
    ├── checkpoints/         # 进度快照（每 2-3 CR）
    ├── ledger/              # Session Ledger（Team 并行记录）
    └── decisions.md         # 关键决策日志
```

### 4.2 Session 生命周期

**启动**：读 session-state.json + manifest.json + tasks/*.yaml + 最新 checkpoint + decisions.md + CLAUDE.md 坑点章节 → git log 确认代码状态 → 运行基线测试 → 输出恢复摘要，确认后继续。

**运行中**：需求确认写 requirement-spec.md，任务拆分写 tasks/*.yaml，技术决策写 decisions.md，任务状态写 CR-xxx.yaml + session-state.json，坑点写 CLAUDE.md，批次完成写 checkpoints/cp-xxx.md。

**结束/中断**：写入最终 checkpoint → 更新 session-state.json → 确保 git commit。

### 4.3 上下文压缩保护（三层防护）

1. **CLAUDE.md（系统提示层，永不压缩）**：Agent 协议 + 门控规则常驻系统提示，压缩不丢弃
2. **context-snapshot.md（磁盘层，可恢复）**：滚动快照记录进度和上下文，压缩后重新读取恢复
3. **磁盘状态文件体系（完整恢复层）**：P3 原则保证关键信息实时写入，`session-manager.py resume` 输出完整恢复摘要

### 4.5 context-snapshot.md 更新规则

`context-snapshot.md` 是滚动快照文件，用于跨会话快速恢复状态。更新规则如下：

**触发事件**（以下 7 个显著动作完成后必须更新）：

| # | 触发事件 | 说明 |
|---|---------|------|
| 1 | 任务状态变更 | CR status 变化时（如 pending→in_progress、ready_for_verify→rework） |
| 2 | 任务步骤推进 | CR current_step 变化时（如 reading_code→coding→testing） |
| 3 | Phase 转换完成 | phase-gate.py 通过后 |
| 4 | checkpoint 写入后 | session-manager.py checkpoint 执行后 |
| 5 | 关键技术决策记录后 | 写入 decisions.md 后 |
| 6 | 发现问题后 | 发现坑点或重大问题时 |
| 7 | 会话中断恢复时 | 新会话读取状态后 |

**更新方式**：用 Write 工具**整体覆盖**（非追加），确保文件大小恒定。

**格式说明**：
- Agent 手动更新使用完整模板格式（含所有 section）
- `session-manager.py checkpoint` 使用简化版格式（自动生成的进度摘要），不包含技术上下文等需要 Agent 判断的内容

### 4.4 用户退出再返回

新开 session 时执行标准启动流程，读取全部状态文件后输出恢复摘要。

---

## 五、运行模式

### 5.1 配置文件

运行配置为 `.claude/dev-state/run-config.yaml`，完整字段定义详见 `schemas/run-config.yaml`（同时作为格式定义文档和回退配置源）。
主要配置：`mode`（interactive/auto-loop）、`toolchain`（支持 auto 检测）、`iteration_mode`、`hooks`、`snapshot`（[v3.1 计划] 当前由 Agent 协议驱动）。

### 5.2 Interactive 模式（默认）

自动执行环境检查、编码、测试、验收、checkpoint 写入；需求审批、任务拆分审批、审查结果、迭代完成时暂停确认。

### 5.3 Auto Loop 模式

全自动执行 Phase 0→5，设置六重安全阀：连续 N 次失败、基线退化、单任务超时、git 冲突、磁盘空间不足、连续无进展。任一触发时停止。

**与 Phase 门控的关系**：
- `auto-loop-runner.py` 是外围循环脚本，负责会话重启和安全阀检查
- Phase 门控由 Agent 协议内部的 Leader 流程驱动，与 interactive 模式使用**相同规则**
- 即 auto-loop 模式下 Phase 转换前仍必须运行 `phase-gate.py`，不允许跳过
- `auto-loop-runner.py` 不直接调用 `phase-gate.py`，Phase 门控由 Claude 会话内的 Leader Agent 负责执行

---

## 六、质量标准

### 6.1 三层验证

```
L0 验收测试: 零 Mock，真实环境运行
  → 每个 CR 的 acceptance_criteria 对应一个 verify 脚本
  → 由 Analyst 生成，Developer 和 Verifier 不可修改
  → 由 Verifier Agent 独立执行（非 Developer 自行运行）
  → Verifier 同时收集 done_evidence（验收证据归档）

L1 单元测试: 最小 Mock（仅白名单场景）
  → 覆盖逻辑分支和边界条件
  → 使用真实轻量替代（tmp_path / :memory: / TestClient）

L2 集成测试: 零 Mock，完整链路
  → 端到端数据流验证
  → 由 Reviewer 运行
  → 每批 CR 完成后在集成检查点运行
```

框架采用 10 层质量门控（Gate 0-7 + Gate 2.5 + Gate 3.5），覆盖从环境就绪到最终验收的全流程：

| Gate | 名称 | 检查内容 | 自动化 |
|------|------|---------|--------|
| Gate 0 | 环境就绪 | 开发环境可用 + 基线测试通过 | 手动 |
| Gate 1 | 需求审批 | 需求规格书通过用户确认 | 手动 |
| Gate 2 | 任务拆分审批 | 任务列表 + verify 脚本通过确认 | phase-gate.py |
| Gate 2.5 | 开发→验收 | 所有 CR 开发完成 | phase-gate.py |
| Gate 3 | L0 验收 | 每个 CR 的 verify 脚本全部 PASS | check-quality-gate.py |
| Gate 3.5 | 验收→审查 | 所有 CR 验收通过 | phase-gate.py |
| Gate 4 | L1 回归 | 全量单元测试 ≥ 基线 | check-quality-gate.py |
| Gate 5 | 集成检查点 | 每批 CR 完成后集成验证 | 半自动 |
| Gate 6 | 代码审查 | Reviewer 独立审查 PASS | check-quality-gate.py |
| Gate 7 | 最终验收 | 全量测试 + lint + E2E | phase-gate.py |

**Phase 5 完成检查**（`phase-gate.py --check-completion`）：

Phase 5 交付前必须通过完成检查，验证以下条件：
1. 所有 CR status=PASS
2. 所有非 hotfix CR 的 review_result.verdict=PASS
3. checkpoints/ 目录非空（证明有进度记录）
4. verify/ 目录非空（证明有验收脚本）

```bash
python dev-framework/scripts/phase-gate.py \
    --project-dir "<项目路径>" \
    --iteration-id "iter-N" \
    --check-completion
```

各门控的详细规则和执行协议，详见运行时 `.claude/CLAUDE.md`（由 `CLAUDE-framework.md.tmpl` 生成）。

**脚本职责说明**：
- `phase-gate.py`：管 Phase 转换的**结构性前置条件**（文件存在、状态字段、目录非空）。只在 Phase N→N+1 时调用，检查"能不能进入下一阶段"。
- `check-quality-gate.py`：管**质量检查**（测试运行、lint、Mock 合规、基线对比）。可在任何时候调用，检查"质量达标了吗"。

### 6.2 任务状态机

```
pending → in_progress → ready_for_verify → ready_for_review → PASS
               ↑               │                    │
               │          [Verifier]            [Reviewer]
               │           rework ──┐          rework ──┐
               │                    │                    │
               └────────────────────┴────────────────────┘
                        Developer 修复后重新标记 ready_for_verify

执行者:
  Developer  → pending 到 ready_for_verify
  Verifier   → ready_for_verify 到 ready_for_review（或 rework）
  Reviewer   → ready_for_review 到 PASS（或 rework）

Rework 完整链条（不允许跳过）:
  rework → Developer 修复 → ready_for_verify → Verifier 重新验收
         → ready_for_review → Reviewer 重新审查 → PASS 或再次 rework
  每次 rework 时:
    - retries 自增 1
    - done_evidence 全部覆盖（非追加），确保证据与最终代码一致
    - 不允许从 rework 直接跳到 ready_for_review（必须重走 Verifier）

特殊状态:
  failed    — retries >= max_retries（默认 2），需 Leader 介入恢复
  blocked   — 等待外部依赖，Leader 在条件解除后重置为 pending
  timeout   — 执行超时，同 failed 处理
```

### 6.2.2 特殊状态恢复规则

当任务进入 `failed`、`blocked`、`timeout` 状态后，必须由 Leader 评估并决定恢复路径：

| 状态 | 触发条件 | 恢复路径 | 执行者 |
|------|---------|---------|--------|
| failed | retries >= max_retries（默认 2，可在 task YAML 或 run-config.yaml 中覆盖） | Leader 评估：① 重置 retries=0 + status=pending 重新分配，或 ② 标 blocked 等人工介入。必须记录 decisions.md | Leader |
| blocked | 外部依赖不可用 | 阻塞条件解除后 Leader 重置为 pending。记录 decisions.md | Leader |
| timeout | 单任务执行超时 | 同 failed 处理。Leader 分析超时原因，必要时拆分 CR 降低粒度 | Leader |

**铁律**：
- 恢复操作**必须由 Leader 执行**，其他角色不可自行恢复
- 每次恢复操作**必须记录 decisions.md**（包含原因、恢复路径、风险评估）
- `max_retries` 优先级：task YAML `max_retries` 字段 > run-config.yaml `max_retries_per_task` > 默认值 2

### 6.2.1 Hotfix 快速通道

Hotfix 是紧急修复的快速通道，用于线上紧急 bug 或实机调试场景。与标准任务流程相比，Hotfix 简化了部分环节：

| 环节 | 标准任务 | Hotfix |
|------|---------|--------|
| 需求分析 | Analyst 完整深化 | 简化，使用 `fix_description` 替代 `design` |
| verify 脚本 | Analyst 生成独立脚本 | 使用 `verification` 字段描述验证方式 |
| Reviewer 审查 | 完整代码审查 | 仍需审查，但可简化 |
| Phase 门控 | 严格状态检查 | Phase 3→3.5 和 3.5→4 跳过该 hotfix CR 的状态检查（`phase-gate.py` 中 `type=="hotfix"` 时 `continue`），Phase 4→5 仅检查 status=PASS + done_evidence 非空 |
| done_evidence | 必须填写 | 必须填写 |

**适用场景**：
- 线上紧急 bug，需要最短时间修复
- 实机调试中发现的阻断问题

**限制条件**：
- 不可滥用：非紧急修复禁止使用 hotfix 类型
- 基线回归不可跳过：hotfix 完成后仍需通过基线测试
- 必须在 `decisions.md` 中记录使用 hotfix 快速通道的原因
- 模板参见 `templates/tasks/hotfix.yaml.tmpl`

### 6.3 基线保护

iterate-mode 下，每次迭代开始时记录基线（测试通过数、lint 状态等）。

**铁律：改动后测试结果必须 ≥ 基线。退化则立即停止修复。**

---

## 七、需求处理标准

### 7.1 交互确认机制

接收到需求后，Analyst 评估成熟度（高/中/低），向用户展示评估并询问：A) 直接拆分、B) 协助完善、C) 用户补充信息。按用户选择进入对应路径。

成熟度评估对应路径：高成熟度 → A（直接拆分）、中成熟度 → B（协助完善）、低成熟度 → B/C（逐步引导）

需求深化维度（功能行为、用户体验、数据影响、性能要求、安全影响、集成影响）及详细确认流程，详见运行时 `.claude/CLAUDE.md` 中的 Analyst 协议（由 `CLAUDE-framework.md.tmpl` 生成）。

### 7.3 需求深化 6 维度与 CR 覆盖 8 维度的关系

框架使用两套维度体系，分别作用于不同阶段，容易混淆但用途完全不同：

| 对比项 | 需求深化 6 维度 | CR 覆盖 8 维度 |
|--------|---------------|---------------|
| 使用阶段 | Phase 1b（需求深化） | Phase 2（任务拆分后） |
| 目的 | 与用户逐维度确认需求细节，补全遗漏 | 验证 CR 拆分的覆盖完整性 |
| 执行者 | Analyst + 用户 | Analyst 自检 |
| 维度列表 | 功能行为、用户体验、数据影响、性能要求、安全影响、集成影响 | 功能完整性、用户体验、健壮性、可观测性、可配置性、性能、安全、可测试性 |
| 产出 | 补全后的 requirement-spec.md | 维度覆盖矩阵（每个维度关联到具体 CR） |

6 维度面向需求补全（输入完整性），8 维度面向 CR 覆盖验证（输出完整性）。

### 7.2 任务拆分标准

**原子性**: 每个 CR 只做一件事，改动 ≤ 5 个文件
**可验证性**: 每个 CR 有独立的 verify 脚本
**独立性**: 尽量可并行，依赖关系最小化
**专业性**: 技术方案要说明 why（为什么选这个方案而非其他）
**七路径审视**: 拆分前必须沿七条路径（Happy/Sad/Edge/Perf/UX/Guard/Ops）逐条审视，
每条路径要么产出 CR，要么标注不适用并说明原因（详见 ADR-008 及运行时 `.claude/CLAUDE.md` 中的 Analyst 协议）

---

## 八、垂直切片策略

### 8.1 基础设施层（Phase 0，先于切片）

- 数据库 schema + 迁移
- 向量数据库 Collection
- 配置加载框架
- API 骨架 + 认证
- 客户端 SDK 框架
- 开发环境验证脚本

Phase 0 完成后冻结。切片开发阶段只能扩展不能修改。
若必须修改基础设施，走独立 CR 审批。

### 8.2 切片定义

每个切片是一条完整的端到端数据流（采集 → 传输 → 处理 → 存储 → 查询），切片间共享基础设施但互不依赖。

### 8.3 调试环境保护

每个切片有独立 E2E 验证脚本（先清理再运行），使用独立 collection/table 前缀，Pipeline 采用注册式架构避免切片间干扰。

---

## 九、文件格式规范

各文件格式详见 `schemas/` 目录：

| 文件 | Schema |
|------|--------|
| 任务文件 CR-xxx.yaml | `schemas/task-schema.yaml` |
| 特性清单 feature-checklist.json | `schemas/feature-checklist.json`（init-mode 专用，跟踪垂直切片级别的特性验收状态） |
| Session 状态 session-state.json | `schemas/session-state.json` |
| 运行配置 run-config.yaml | `schemas/run-config.yaml` |
| 基线检测 baseline.json | `schemas/baseline.json` |
| 迭代清单 manifest.json | 迭代目录下的元信息文件 |

---

## 十、框架使用方式

框架通过脚本初始化和管理项目。完整命令参考请见 [README.md](README.md)。

- **新项目**：`python dev-framework/scripts/init-project.py --project-dir <path> --requirement-doc <path> --tech-stack <stack>`
- **迭代开发**：`python dev-framework/scripts/init-iteration.py --project-dir <path> --requirement <desc> --iteration-id iter-N`
- **AutoLoop**：`python dev-framework/scripts/auto-loop-runner.py --project-dir <path> --iteration-id iter-N --max-restarts 10`
- **框架更新**：重新运行 init 脚本即可更新（保留项目特定的定制部分）

---

## 附录 A：术语表

| 术语 | 定义 | 易混淆 |
|------|------|--------|
| **CR** | Change Request，任务基本单位 | Task（不推荐）。脚本参数使用 --task-id，值应传入 CR ID（如 --task-id CR-001） |
| **INF** | Infrastructure，基础设施类任务 | — |
| **F** | Feature，init-mode 功能特性 | — |
| **HF** | Hotfix，紧急修复类任务 | — |
| **Phase** | 开发阶段（0-5） | Stage（不使用） |
| **Gate** | 质量门控检查点（0-7 + 2.5 + 3.5，共 10 个） | Checkpoint（不同概念） |
| **L0 / L1 / L2** | 验收测试 / 单元测试 / 集成测试 | — |
| **Baseline** | 迭代开始时的测试快照 | — |
| **Checkpoint** | 开发过程中的进度快照 | 不等于 Gate |
| **Ledger** | Team 并行子任务记录 | Session Ledger |
| **Iteration** | 一轮迭代（iter-N） | Sprint（不使用） |
| **done_evidence** | 验收证据归档，由 Verifier 填写 | — |
| **verify 脚本** | 验收脚本（verify/CR-xxx.py），由 Analyst 生成 | L0 脚本 |
| **rework / PASS** | 返工 / 终态成功，由 Verifier/Reviewer 标记 | — |
| **轻量迭代模式 (lightweight)** | 合并 Phase 3.5+4（Verify+Review 由同一 Agent 执行）。启用条件：CR≤5 或全为 enhancement/bug_fix，且无 P0 任务。D/E 维度降级（详见 ADR-013）。需在 decisions.md 中声明 | standard 模式 |

> **Feature ID 命名空间说明**：feature-checklist 使用 `F001` 格式（init-mode 专用，无连字符），task ID 使用 `F-001` 格式（通用 CR，含连字符），两者命名空间独立。

---

## 附录 B：Mock 生命周期管理

使用 Mock 时必须同时声明三项注释：`MOCK-REASON`（原因）、`MOCK-REAL-TEST`（对应真实测试路径）、`MOCK-EXPIRE-WHEN`（移除条件）。

```python
# MOCK-REASON: Claude API 调用需要付费，CI 环境无 API Key
# MOCK-REAL-TEST: tests/e2e/test_claude_api.py::test_real_api_call
# MOCK-EXPIRE-WHEN: CI 配置了 CLAUDE_API_KEY 环境变量
```

**生命周期**：创建（Developer 添加 Mock + 三项声明）→ 审查（Reviewer 验证完整性）→ 定期审计（每轮 Phase 0 扫描到期条件）→ 移除（条件满足时创建 CR）。

永远无法移除的 Mock 使用 `permanent` 标记：`# MOCK-EXPIRE-WHEN: permanent: <原因>`

---

## 十一、架构决策记录

核心设计决策记录在 `ARCHITECTURE.md` 中（ADR 格式：决策、原因、替代方案、后果）。新增或修改设计决策时必须同步更新。

---

## 相关文档

- [README.md](README.md) — 快速入门与项目概览
- [ARCHITECTURE.md](ARCHITECTURE.md) — 架构决策记录（ADR）
- [USER-GUIDE.md](USER-GUIDE.md) — 详细使用指南
