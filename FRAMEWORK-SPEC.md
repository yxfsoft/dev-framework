# Dev-Framework 规格书

> 版本: 1.1
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

首次开发等同于 iteration-0（在空项目上的首轮迭代）。

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
Developer  |   ✓    |   ✓    |    ✗     |  部分  |     ✗      |    ✗    |
Verifier   |   ✓    |   ✗    |    ✗     |  部分  |     ✓      |    ✗    |
Reviewer   |   ✓    |   ✗    |    ✗     |   ✓    |     ✗      |    ✓    |
```

### 3.3 工作流阶段

```
Phase 0: 环境就绪
  ├── 读取项目文档和状态文件
  ├── git pull --rebase
  ├── 运行基线测试（iterate-mode）/ 确认环境可用（init-mode）
  └── 写入 baseline.json

Phase 1: 需求接收与深化
  ├── 接收用户需求
  ├── 评估成熟度 → 交互确认
  ├── Analyst 细化需求 → requirement-spec.md
  └── 用户审批

Phase 2: 影响分析与任务拆分
  ├── Analyst 分析受影响文件/模块
  ├── 拆分为原子 CR（每个 ≤ 5 文件改动）
  ├── 生成 verify 脚本（不可被 Developer 修改）
  ├── 确定依赖关系和并行策略
  └── 用户审批任务列表

Phase 3: 开发执行
  ├── Developer Agent(s) 按依赖顺序认领 CR
  ├── 每个 CR: 读代码 → 编码 → 自检 → L1 测试 → 回归 → commit
  ├── Developer 标记 ready_for_verify
  ├── 并行度 ≤ 3
  └── 每批完成后运行集成检查点

Phase 3.5: 独立验收
  ├── Verifier Agent 对 ready_for_verify 的 CR 执行 L0 验收
  ├── 运行 verify 脚本 + 收集 done_evidence
  ├── 通过 → 标记 ready_for_review
  └── 失败 → 标记 rework

Phase 4: 审查验收
  ├── Reviewer Agent 独立审查每个 CR
  ├── 检查: 代码质量 + 回归安全 + 集成正确 + 需求覆盖 + 证据完整性
  └── PASS / REWORK

Phase 5: 交付
  ├── 全量测试 ≥ 基线
  ├── 所有 CR 为 PASS
  ├── 生成迭代报告
  └── 更新进度文件 + git push
```

---

## 四、状态管理与上下文连续性

### 4.1 状态文件体系

```
{project}/.claude/dev-state/
├── session-state.json              # 当前 session 运行状态
├── baseline.json                   # 基线测试结果
├── experience-log.md               # 经验教训累积
├── run-config.yaml                 # 运行模式配置
│
└── {iteration-id}/                 # 每轮迭代独立目录（如 iter-3 或 iteration-0）
    ├── manifest.json               # 迭代元信息（阶段/进度/时间戳）
    ├── requirement-raw.md          # 用户原始需求
    ├── requirement-spec.md         # 细化后的需求规格
    ├── impact-analysis.md          # 影响分析
    ├── tasks/                      # 任务列表
    │   ├── CR-001.yaml
    │   └── ...
    ├── verify/                     # 验收脚本（不可修改）
    │   ├── CR-001.py
    │   └── ...
    ├── checkpoints/                # 检查点快照（全局进度，每 2-3 CR）
    │   └── cp-001.md
    ├── ledger/                     # Session Ledger（Team 并行记录，由 session-manager.py 按需创建）
    │   └── session-20260219-01.md
    └── decisions.md                # 关键决策日志
```

### 4.2 Session 生命周期

**启动（恢复上下文）：**
1. 读 session-state.json → 获取上次所在阶段
2. 读 manifest.json → 获取当前迭代信息
3. 扫描 tasks/*.yaml → 获取任务列表和状态
4. 读最新 checkpoint → 获取上次中断点
5. 读 decisions.md → 获取历史决策
6. 读 experience-log.md → 获取已知坑点
7. git log --oneline -10 → 确认代码状态
8. 运行基线测试（如配置要求）
9. 输出恢复摘要，确认后继续

**运行中（持续写入）：**

| 事件 | 写入目标 |
|------|---------|
| 需求方向确认 | requirement-spec.md |
| 任务拆分完成 | tasks/*.yaml |
| 关键技术决策 | decisions.md |
| 任务开始/完成 | tasks/CR-xxx.yaml + session-state.json |
| 发现坑点/经验 | experience-log.md |
| 批次完成 | checkpoints/cp-xxx.md |

**结束/中断：**
- 写入最终 checkpoint
- 更新 session-state.json
- 确保所有改动已 git commit

### 4.3 上下文压缩保护

Claude Code 的自动上下文压缩不会导致信息丢失，因为：
- 所有关键信息在产生时已写入磁盘
- 压缩后 Agent 通过读取磁盘文件完全恢复
- checkpoint 机制确保有完整的中间状态快照

### 4.4 用户退出再返回

用户新开 session 时，Agent 执行标准启动流程，读取全部状态文件后输出恢复摘要：
> "上次进行到 iter-3 Phase 3, 5/12 CR 完成，正在做 CR-006。继续？"

---

## 五、运行模式

### 5.1 配置文件

```yaml
# .claude/dev-state/run-config.yaml

mode: "interactive"   # interactive | auto-loop

interactive:
  auto_verify: true          # 编码后自动运行 verify
  auto_test: true            # 自动运行测试
  auto_commit: false         # git commit 需用户确认
  pause_points:
    - requirement_approval
    - task_plan_approval
    - review_result
    - iteration_complete

auto_loop:
  max_retries_per_task: 2
  max_parallel_agents: 2
  stop_on_review_fail: true
  checkpoint_frequency: "per_task"
  max_consecutive_failures: 3
  timeout_per_task: 1800
  report_interval: 300
```

### 5.2 Interactive 模式（默认）

自动执行：环境检查、编码、测试、验收脚本、checkpoint 写入
暂停确认：需求审批、任务拆分审批、审查结果、迭代完成

### 5.3 Auto Loop 模式

全自动执行 Phase 0→5，仅在以下条件停止：
- 连续 N 次任务失败
- 基线测试退化
- 单任务超时
- 全部完成

详细流程见 `workflows/quality-gate.md`。

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

### 6.2 任务状态机

```
pending → in_progress → ready_for_verify → ready_for_review → PASS
               ↑                                    │
               └────────────── rework ──────────────┘

执行者:
  Developer  → pending 到 ready_for_verify
  Verifier   → ready_for_verify 到 ready_for_review（或 rework）
  Reviewer   → ready_for_review 到 PASS（或 rework）

特殊状态:
  failed    — 超过最大重试次数
  blocked   — 等待外部依赖
  timeout   — 执行超时
```

### 6.3 基线保护

iterate-mode 下，每次迭代开始时记录基线：
```json
{
  "iteration": "iter-3",
  "timestamp": "2026-02-19T14:00:00",
  "test_results": {
    "l1_passed": 2381,
    "l1_failed": 0,
    "l2_passed": 102,
    "l2_failed": 0
  },
  "lint_clean": true
}
```

**铁律：改动后测试结果必须 ≥ 基线。退化则立即停止修复。**

---

## 七、需求处理标准

### 7.1 交互确认机制

```
Step 1: Analyst 评估需求成熟度
  高: 明确描述期望行为 + 包含边界条件 + 有量化指标
  中: 描述了期望行为但缺少边界条件或指标
  低: 仅描述大方向（如"优化搜索"）

Step 2: 向用户展示评估并询问
  A) 需求已明确，直接进入拆分
  B) 需要协助完善后再拆分
  C) 我补充一些信息

Step 3: 按用户选择执行
  路径 A: 直接拆分（仍需应用八维度专业标准补全）
  路径 B: 交互式细化（逐维度确认）
  路径 C: 接收补充后重新评估
```

### 7.2 需求深化维度

Analyst 按以下维度逐一深化：

1. **功能行为**：正常流程 + 异常流程 + 边界条件
2. **用户体验**：操作流程 + 反馈机制 + 错误提示 + 可访问性
3. **数据影响**：数据模型变更 + 迁移方案 + 兼容性
4. **性能要求**：响应时间 + 吞吐量 + 资源占用
5. **安全影响**：认证/授权 + 数据暴露 + 输入校验
6. **集成影响**：API 兼容 + 配置兼容 + 下游影响

### 7.3 任务拆分标准

**原子性**: 每个 CR 只做一件事，改动 ≤ 5 个文件
**可验证性**: 每个 CR 有独立的 verify 脚本
**独立性**: 尽量可并行，依赖关系最小化
**专业性**: 技术方案要说明 why（为什么选这个方案而非其他）

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

每个切片是一条完整的端到端数据流：
```
采集 → 传输 → 处理 → 存储 → 查询
```

切片间共享基础设施但互不依赖。

### 8.3 调试环境保护

- 每个切片有独立的 E2E 验证脚本
- 验证脚本先清理测试数据再运行
- 测试使用独立的 collection/table 前缀
- Pipeline 采用注册式架构，切片注册自己的处理器不干扰已有处理器

---

## 九、文件格式规范

### 9.1 任务文件 (CR-xxx.yaml)

详见 `schemas/task-schema.yaml`。

### 9.2 特性清单 (feature-checklist.json)

init-mode 使用，所有特性初始标记 FAIL。
详见 `schemas/feature-checklist.json`。

### 9.3 Session 状态 (session-state.json)

详见 `schemas/session-state.json`。

### 9.4 运行配置 (run-config.yaml)

详见 `schemas/run-config.yaml`。

---

## 十、框架使用方式

### 10.1 新项目

```bash
python dev-framework/scripts/init-project.py \
  --project-dir "/path/to/new-project" \
  --requirement-doc "/path/to/requirements.md" \
  --tech-stack "python,react"
```

### 10.2 迭代开发

```bash
python dev-framework/scripts/init-iteration.py \
  --project-dir "/path/to/existing-project" \
  --requirement "修复搜索超时；新增批量导入" \
  --iteration-id "iter-3"
```

### 10.3 框架更新

框架自身的更新不影响已有项目。已有项目中的 Agent 定义是框架的副本，
可以通过重新运行 init 脚本更新（保留项目特定的定制部分）。

---

## 十一、架构决策记录

框架的核心设计决策记录在 `ARCHITECTURE.md` 中。
每条 ADR（Architecture Decision Record）包含：决策、原因、替代方案、后果。

新增或修改设计决策时，必须同步更新 ARCHITECTURE.md。
