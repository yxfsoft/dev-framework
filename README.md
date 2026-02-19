# Dev-Framework — 多代理协作开发框架

统一的多代理协作开发框架，覆盖首次开发（init-mode）和多轮迭代开发（iterate-mode）。

基于五角色制衡模型（Leader / Analyst / Developer / Verifier / Reviewer），
通过 8 层质量门控和磁盘状态持久化，确保开发质量和上下文连续性。

---

## 平台兼容性

本框架支持 **Windows** 和 **macOS** 两个开发平台：

| 要求 | 说明 |
|------|------|
| Python | 3.10+ |
| 依赖 | `pip install -r requirements.txt` |
| Git | 2.30+ |
| Shell | Windows: PowerShell / Git Bash；macOS: bash / zsh |

> 所有脚本使用 Python 标准库 + PyYAML，不依赖平台特定命令（如 grep/sed）。
> 路径处理使用 `pathlib.Path`，自动适配不同操作系统。

---

## 快速开始

### 安装依赖

```bash
pip install -r dev-framework/requirements.txt
```

### 新项目初始化

```bash
python dev-framework/scripts/init-project.py \
    --project-dir "D:/my-new-project" \
    --requirement-doc "docs/requirements.md" \
    --tech-stack "python,react,fastapi"
```

### 已有项目迭代

```bash
python dev-framework/scripts/init-iteration.py \
    --project-dir "D:/my-existing-project" \
    --requirement "修复搜索超时；新增批量导入" \
    --iteration-id "iter-3"
```

### 运行基线测试

```bash
python dev-framework/scripts/run-baseline.py \
    --project-dir "D:/my-project" \
    --iteration-id "iter-3"
```

---

## 框架结构

```
dev-framework/
├── FRAMEWORK-SPEC.md           # 框架规格书（核心文档）
├── ARCHITECTURE.md             # 架构决策记录（ADR）
├── README.md                   # 本文件
├── requirements.txt            # Python 依赖声明
├── .gitignore                  # Git 忽略规则
│
├── agents/                     # Agent 角色定义
│   ├── analyst.md              # 需求分析 Agent
│   ├── developer.md            # 开发执行 Agent
│   ├── verifier.md             # 独立验收 Agent
│   ├── reviewer.md             # 代码审查 Agent
│   └── leader.md               # 编排协调 Agent
│
├── workflows/                  # 工作流定义
│   ├── init-mode.md            # 首次开发流程
│   ├── iterate-mode.md         # 迭代开发流程
│   ├── requirement-intake.md   # 需求接收与深化
│   └── quality-gate.md         # 质量门控规则
│
├── templates/                  # 模板文件
│   ├── project/                # 项目级模板
│   │   ├── CLAUDE.md.tmpl      # 项目宪法模板
│   │   ├── ARCHITECTURE.md.tmpl
│   │   ├── progress.md.tmpl
│   │   └── session-ledger.md.tmpl
│   ├── tasks/                  # 任务模板（按变更类型）
│   │   ├── feature.yaml.tmpl
│   │   ├── bug-fix.yaml.tmpl
│   │   ├── enhancement.yaml.tmpl
│   │   ├── new-feature.yaml.tmpl
│   │   └── refactor.yaml.tmpl
│   └── verify/                 # 验证脚本模板
│       ├── verify-task.py.tmpl
│       └── verify-integration.py.tmpl
│
├── schemas/                    # 数据格式定义
│   ├── task-schema.yaml        # 任务 YAML 格式
│   ├── feature-checklist.json  # 特性清单 JSON 格式
│   ├── session-state.json      # Session 状态格式
│   ├── baseline.json           # 基线测试结果格式
│   └── run-config.yaml         # 运行配置格式 + 默认值
│
├── scripts/                    # 自动化工具（跨平台）
│   ├── init-project.py         # 初始化新项目
│   ├── init-iteration.py       # 初始化迭代轮次
│   ├── run-baseline.py         # 运行基线测试
│   ├── run-verify.py           # 运行验收脚本 / 生成验收骨架
│   ├── check-quality-gate.py   # 质量门控检查（Gate 0-7）
│   ├── estimate-tasks.py       # 任务拆分规模估算
│   ├── generate-report.py      # 生成迭代报告
│   └── session-manager.py      # Session 状态管理
│
└── examples/                   # 示例（参考用）
    └── iterate-mode-example/   # 包含完整的 CR 示例
        ├── manifest.json
        ├── tasks/CR-001.yaml
        └── verify/CR-001.py
```

---

## 核心原则

| 原则 | 说明 |
|------|------|
| **P1 行业最优标准** | 需求拆解必须达到资深工程师级别，不产出简陋版本 |
| **P2 默认禁 Mock** | 仅白名单场景允许 Mock，必须声明理由 |
| **P3 磁盘为真相源** | 所有关键信息立即写入磁盘，不依赖对话上下文 |
| **P4 不可自评通过** | Developer 只能标记 `ready_for_verify`，Verifier 验收后标记 `ready_for_review`，只有 Reviewer 可标记 `PASS` |
| **P5 垂直切片** | 深度优先，一条链路做完再做下一条 |
| **P6 交互式确认** | 接收需求后必须先确认成熟度和处理路径 |

---

## 五角色制衡模型

| Agent | 核心职责 | 关键权限 |
|-------|---------|---------|
| **Leader** | 编排协调、任务分配、进度管控、用户交互 | 全部权限 |
| **Analyst** | 需求深化、影响分析、任务拆分、生成 verify 脚本 | 只读代码 + 写文档/脚本 |
| **Developer** | 编码实现 + L1 测试 + 基线回归 | 读写代码，不可改 verify |
| **Verifier** | 独立验收执行（L0）+ 证据收集 | 只读代码 + 运行验证 + 写 evidence |
| **Reviewer** | 独立审查 + L2 验证 + 最终裁决 | 只读代码 + 运行测试 + 标 PASS/REWORK |

**任务状态流转**:
```
pending → in_progress → ready_for_verify → ready_for_review → PASS
  Developer 编码        Verifier 验收       Reviewer 审查
```

---

## 工作流概览

```
用户需求 → 成熟度评估 → 交互确认(A/B/C)
    │
    ▼
Analyst: 需求深化 → requirement-spec.md
    │
    ▼
Analyst: 影响分析 → 任务拆分 → verify 脚本
    │
    ▼
Developer(s): 编码 → 自检 → L1 测试 → commit → ready_for_verify
    │
    ▼
Verifier: L0 验收 → done_evidence 收集 → ready_for_review
    │
    ▼
Reviewer: 代码审查 → L2 集成 → PASS/REWORK
    │
    ▼
交付: 全量测试 → 迭代报告 → git push
```

---

## 运行模式

### Interactive（默认）

关键决策点暂停确认，其余全自动。适合日常开发。

### Auto Loop

全自动执行 Phase 0→5，仅在安全阀触发时停止。
适合大批量任务或夜间运行。

配置: `.claude/dev-state/run-config.yaml`

---

## 质量门控（8 层）

| 门控 | 触发时机 | 检查内容 | 自动化 |
|------|---------|---------|--------|
| Gate 0 | 环境就绪 | git 干净、工具可用 | ✓ 脚本 |
| Gate 1 | 需求审批 | 规格书完整、用户确认 | 部分（文件存在性检查） |
| Gate 2 | 任务审批 | CR 格式正确、verify 完整 | 部分（完整性检查） |
| Gate 3 | L0 验收 | verify 脚本全 PASS | ✓ 脚本 |
| Gate 4 | L1 回归 | 测试数 ≥ 基线，无新失败 | ✓ 脚本 |
| Gate 5 | 集成检查 | L1+L2+Lint 通过 | ✓ 脚本 |
| Gate 6 | 代码审查 | Reviewer PASS | 部分（review_result 检查） |
| Gate 7 | 最终验收 | 全量通过 + 无空实现 | ✓ 脚本 |

---

## 常用命令

### 项目管理

```bash
# 初始化新项目
python dev-framework/scripts/init-project.py \
    --project-dir "D:/project" \
    --requirement-doc "docs/requirements.md" \
    --tech-stack "python,react"

# 初始化新迭代
python dev-framework/scripts/init-iteration.py \
    --project-dir "D:/project" \
    --requirement "修复搜索超时" \
    --iteration-id "iter-3"
```

### 测试与验收

```bash
# 运行基线测试
python dev-framework/scripts/run-baseline.py \
    --project-dir "D:/project" \
    --iteration-id "iter-3"

# 运行单个 CR 的验收
python dev-framework/scripts/run-verify.py \
    --project-dir "D:/project" \
    --iteration-id "iter-3" \
    --task-id "CR-001"

# 运行所有验收脚本
python dev-framework/scripts/run-verify.py \
    --project-dir "D:/project" \
    --iteration-id "iter-3" \
    --all

# 从任务 YAML 生成 verify 脚本骨架
python dev-framework/scripts/run-verify.py \
    --project-dir "D:/project" \
    --iteration-id "iter-3" \
    --generate-skeleton "CR-001"
```

### 质量门控

```bash
# 检查特定门控
python dev-framework/scripts/check-quality-gate.py \
    --project-dir "D:/project" \
    --gate gate_4

# 检查 L0 验收（需要 iteration-id 和 task-id）
python dev-framework/scripts/check-quality-gate.py \
    --project-dir "D:/project" \
    --gate gate_3 \
    --iteration-id "iter-3" \
    --task-id "CR-001"

# 检查所有门控
python dev-framework/scripts/check-quality-gate.py \
    --project-dir "D:/project" \
    --all
```

### Session 管理

```bash
# 查看当前 session 状态
python dev-framework/scripts/session-manager.py \
    --project-dir "D:/project" status

# 写入检查点
python dev-framework/scripts/session-manager.py \
    --project-dir "D:/project" checkpoint

# 恢复 session 摘要
python dev-framework/scripts/session-manager.py \
    --project-dir "D:/project" resume

# 写入 Session Ledger（Team 并行台账）
python dev-framework/scripts/session-manager.py \
    --project-dir "D:/project" ledger
```

### 报告与估算

```bash
# 生成迭代报告
python dev-framework/scripts/generate-report.py \
    --project-dir "D:/project" \
    --iteration-id "iter-3"

# 任务拆分规模估算
python dev-framework/scripts/estimate-tasks.py \
    --modules 5 --risk high --complexity moderate --mode iterate
```

---

## 状态管理

所有开发状态持久化到磁盘，支持会话中断恢复：

```
{project}/.claude/dev-state/
├── session-state.json          # 当前 session 运行状态
├── baseline.json               # 基线测试结果
├── experience-log.md           # 经验教训累积
├── run-config.yaml             # 运行模式配置
└── {iteration-id}/             # 每轮迭代独立目录
    ├── manifest.json           # 迭代元信息
    ├── requirement-raw.md      # 用户原始需求
    ├── requirement-spec.md     # 细化后的需求规格
    ├── tasks/                  # 任务 YAML 文件
    ├── verify/                 # 验收脚本（不可被 Developer 修改）
    ├── checkpoints/            # 检查点快照
    ├── ledger/                 # Session Ledger（Team 并行记录）
    └── decisions.md            # 关键决策日志
```

---

## 文档索引

| 文档 | 内容 |
|------|------|
| [FRAMEWORK-SPEC.md](FRAMEWORK-SPEC.md) | 框架规格书（核心文档，完整流程定义） |
| [ARCHITECTURE.md](ARCHITECTURE.md) | 架构决策记录（7 条 ADR） |
| [agents/leader.md](agents/leader.md) | Leader Agent 协议 |
| [agents/analyst.md](agents/analyst.md) | Analyst Agent 协议 |
| [agents/developer.md](agents/developer.md) | Developer Agent 协议 |
| [agents/verifier.md](agents/verifier.md) | Verifier Agent 协议 |
| [agents/reviewer.md](agents/reviewer.md) | Reviewer Agent 协议 |
| [workflows/init-mode.md](workflows/init-mode.md) | 首次开发工作流 |
| [workflows/iterate-mode.md](workflows/iterate-mode.md) | 迭代开发工作流 |
| [workflows/requirement-intake.md](workflows/requirement-intake.md) | 需求接收与深化 |
| [workflows/quality-gate.md](workflows/quality-gate.md) | 质量门控规则 |

---

## 示例

`examples/iterate-mode-example/` 目录包含一个完整的迭代示例：

- `manifest.json` — 迭代元信息
- `tasks/CR-001.yaml` — 完整的 bug_fix 类型任务文件
- `verify/CR-001.py` — 对应的验收脚本

参考此示例理解任务文件的字段要求和验收脚本的编写规范。
