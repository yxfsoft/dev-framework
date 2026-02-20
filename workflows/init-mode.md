# Init-Mode 工作流（首次开发）

> 适用于：从零开始的新项目开发
> 输入：需求文档 + 技术栈选择
> 输出：完整项目代码

---

## 概述

首次开发等同于 iter-0。与 iterate-mode 的区别：
- 无基线测试（基线为空）
- 任务类型全部为 new_feature
- 需要先建立项目骨架和基础设施

---

## Phase 0: 项目初始化

### Step 0.1: 创建项目结构

运行初始化脚本（`<框架路径>` 指 dev-framework 仓库的根目录，可通过环境变量或绝对路径指定）：

```bash
python <框架路径>/scripts/init-project.py \
    --project-dir "<目标项目目录>" \
    --requirement-doc "<需求文档路径>" \
    --tech-stack "<技术栈，逗号分隔>"
```

生成的目录结构：

```
{project}/
├── .claude/
│   ├── agents/              # 从框架复制的 Agent 定义（所有 *.md）
│   ├── dev-state/           # 开发状态目录
│   │   ├── session-state.json
│   │   ├── baseline.json    # 空基线
│   │   ├── experience-log.md    # v2.6 已废弃，保留空壳以兼容旧版本
│   │   ├── run-config.yaml  # 从 schemas/run-config.yaml 复制
│   │   └── iter-0/
│   │       ├── manifest.json
│   │       ├── requirement-raw.md  # 指向需求文档
│   │       ├── tasks/
│   │       ├── verify/
│   │       ├── checkpoints/
│   │       └── decisions.md
│   └── CLAUDE.md            # 项目宪法（从模板生成，需手动定制）
├── ARCHITECTURE.md          # 架构决策记录（从模板生成）
├── docs/                    # 用户提供的需求文档
├── config/
│   └── default.yaml
├── scripts/
│   └── verify/              # 验收脚本目录
├── tests/
│   ├── unit/
│   └── integration/
├── .gitignore               # 自动追加框架文件排除规则
└── .git/hooks/              # 自动生成 pre-commit / commit-msg / pre-push
```

> 注意：如果项目根目录已有 CLAUDE.md，脚本会采用追加模式，将框架配置写入 `.claude/CLAUDE.md`，不覆盖原有文件。

### Step 0.2: CLAUDE.md 定制

基于模板生成项目 CLAUDE.md，包含：
- 项目概述（从需求文档提取）
- 技术栈声明
- 代码规范
- 目录结构
- 测试策略
- Agent 工作协议引用

### Step 0.3: 环境验证

确认开发环境可用：
- 编程语言版本正确
- 包管理器可用
- 数据库/中间件可启动
- 写入 session-state.json

---

## Phase 1: 需求接收与深化

### Step 1.1: 读取需求文档

Analyst Agent 读取用户提供的需求文档，进行全局理解。

### Step 1.2: 需求交互确认

按 `workflows/requirement-intake.md` 执行：
- 评估需求成熟度
- 询问用户 A/B/C
- 按选择路径处理

### Step 1.3: 生成特性清单

init-mode 特有步骤：生成 `feature-checklist.json`，存放于 `.claude/dev-state/iter-0/feature-checklist.json`

```json
{
  "project": "{project-name}",
  "mode": "init",
  "features": [
    {
      "id": "F001",
      "name": "{Feature 名称}",
      "status": "FAIL",
      "priority": "{critical / high / medium / low}",
      "slice": "{切片标识}",
      "criteria": [
        {"id": "F001-C1", "desc": "{验收条件 1}", "status": "FAIL"},
        {"id": "F001-C2", "desc": "{验收条件 2}", "status": "FAIL"},
        {"id": "F001-C3", "desc": "{验收条件 N}", "status": "FAIL"}
      ]
    }
  ]
}
```

所有 Feature 初始为 FAIL。Agent 逐个攻克。

### Step 1.4: 输出需求规格书

写入 `iter-0/requirement-spec.md`，等待用户审批。

---

## Phase 2: 架构设计 + 任务拆分

### Step 2.1: 基础设施层拆分

优先拆分 Phase 0 的基础设施任务：

```
基础设施 CR（必须先完成）:
  INF-001: {基础设施组件 1，如数据库 schema / ORM / 迁移}
  INF-002: {基础设施组件 2，如配置加载框架}
  INF-003: {基础设施组件 3，如 API 骨架 + 认证}
  INF-00N: {根据项目实际需求拆分}
```

### Step 2.2: 垂直切片拆分

按照特性清单中的切片，每个切片拆分为多个 CR：

```
切片 "{slice-name}" 的 CR 序列:
  CR-001: {核心功能实现}
  CR-002: {辅助功能实现}
  CR-003: {边界条件处理}
  ...
  CR-00N: {切片端到端验证}
```

每个 CR 带完整的 design + acceptance_criteria + verify 脚本。

### Step 2.3: 依赖关系

```
INF-001~00N → 无依赖，可并行
CR-001~00X → 依赖 INF 完成
CR-00Y → 依赖 CR-001~00X
...
CR-最终 → 依赖全部（端到端验证）
```

依赖关系由 Analyst 根据实际项目结构确定，需满足：无循环依赖、可并行的任务已标注。

### Step 2.4: 用户审批

展示完整的任务列表和依赖关系图，等待用户确认。

### Step 2.5: Phase 转换检查

用户审批通过后，运行 phase-gate.py 确认前置条件满足：

```bash
python <框架路径>/scripts/phase-gate.py \
    --project-dir "." \
    --iteration-id "iter-0" \
    --from phase_2 --to phase_3
```

- 返回码 0 → 允许进入 Phase 3
- 返回码非 0 → 修复阻断项后重试
- 紧急情况可使用 `--force` 跳过，但必须在 decisions.md 中记录原因

> 所有 Phase 转换均须运行此检查（见 `agents/leader.md` "Phase 转换检查"章节）。

---

## Phase 3: 开发执行

### 团队组建（强制角色分离）

无论 CR 数量多少，必须组建包含全部五角色的完整团队：

| CR 数量 | 团队配置 |
|---------|---------|
| 1-3 | 1 Leader + 1 Analyst + 1 Developer + 1 Verifier + 1 Reviewer |
| 4-8 | 1 Leader + 1 Analyst + 1-2 Developer + 1 Verifier + 1 Reviewer |
| > 8 | 1 Leader + 1 Analyst + 2-3 Developer + 1 Verifier + 1 Reviewer |

角色分离是质量保障的底线，不因 CR 数量少而妥协。详见 `agents/leader.md` "团队管理"章节。

### 基础设施批次

```
Batch 0: INF-001 ~ INF-00N（可并行，最多 3 Agent）
  → 完成后运行基础设施验证脚本
  → 基础设施冻结（冻结后只能扩展，不能修改）
```

### 切片批次

```
Batch 1: 切片 1 的 CR 序列（按依赖顺序执行）
  → 可并行的 CR 并行执行
  → 切片完成后运行切片 E2E 验证

Batch 2: 切片 2 的 CR 序列
  → 同上

...
```

### 每个切片完成后

1. 运行切片 E2E 验证脚本
2. 运行全量回归测试
3. 更新 feature-checklist.json 中对应 Feature 的 criteria 状态
4. 如果所有 criteria 为 PASS，将 Feature 标记为 PASS
5. 写入 checkpoint

---

## Phase 3.5: 独立验收

Phase 3 开发完成后，进入独立验收阶段。此阶段由 Verifier Agent 独立执行，Developer 不参与。

### Step 3.5.1: L0 验收

Verifier 对每个 `ready_for_verify` 状态的 CR 执行：
1. 运行 `verify/CR-xxx.py` 验收脚本
2. 收集 done_evidence（测试结果、日志、截图等）
3. 验证 acceptance_criteria 全部满足

### Step 3.5.2: 处理结果

- **验收通过** → 标记 `ready_for_review`，进入 Phase 4 审查
- **验收失败** → 标记 `rework`，通知 Developer 修复后重新提交（回到 Phase 3）
- 超过 `max_retries` 次重试仍失败 → 标记 `failed`

### Step 3.5.3: Phase 转换检查

所有 CR 验收完成后，运行门控检查：

```bash
python <框架路径>/scripts/phase-gate.py \
    --project-dir "." \
    --iteration-id "iter-0" \
    --from phase_3.5 --to phase_4
```

---

## Phase 4: 审查验收

### Step 4.1: 审查

Reviewer 按 `agents/reviewer.md` 审查每个 ready_for_review 的 CR。

### Step 4.2: 处理结果

- PASS → 标记完成
- REWORK → 通知 Developer，回到 Phase 3

### Step 4.3: Feature Checklist 更新（init-mode 特有）

每个 CR 审查通过后：
1. Reviewer 同步更新 `.claude/dev-state/iter-0/feature-checklist.json` 中对应 criteria 的状态
2. 当某个 Feature 的所有 criteria 全部 PASS 时，将该 Feature 标记为 PASS

### Step 4.4: 全量验收

所有 CR 为 PASS 后：
1. 运行全量 L1 + L2 测试
2. 结果 ≥ baseline
3. Lint 通过
4. 无新增 TODO/FIXME
5. **所有 Feature 必须为 PASS**（而非仅检查 CR 状态）

---

## Phase 5: 交付

基本流程与 `iterate-mode.md` Phase 5 相同（全量测试 → 报告 → git push），但 init-mode 有以下差异：

1. **交付物是完整项目**：包含完整的项目代码、ARCHITECTURE.md（含所有 ADR）、测试套件
2. **Feature Checklist 归档**：最终的 `feature-checklist.json` 作为项目验收清单归档
3. **基线建立**：首次迭代的测试结果成为后续 iterate-mode 的基线（写入 `baseline.json`）

---

## Init-Mode 特有规则

1. **基础设施冻结**：Phase 2 基础设施批次完成后（即 Batch 0 全部通过验证），基础设施代码只能扩展不能修改
2. **Feature Checklist 为主导**：任务状态追踪以 feature-checklist.json 为准
3. **切片顺序**：按优先级执行，高优先级切片先做
4. **跨切片依赖**：如果切片 B 需要切片 A 的基础设施，切片 A 必须先完成
5. **渐进交付**：每完成一个切片就是一个可运行的增量
