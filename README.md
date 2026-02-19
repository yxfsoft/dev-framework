# Dev-Framework — 多代理协作开发框架

统一的多代理协作开发框架，覆盖首次开发（init-mode）和多轮迭代开发（iterate-mode）。

---

## 快速开始

### 新项目初始化

```bash
python scripts/init-project.py \
    --project-dir "D:/my-new-project" \
    --requirement-doc "docs/requirements.md" \
    --tech-stack "python,react,fastapi"
```

### 已有项目迭代

```bash
python scripts/init-iteration.py \
    --project-dir "D:/my-existing-project" \
    --requirement "修复搜索超时；新增批量导入" \
    --iteration-id "iter-3"
```

### 运行基线测试

```bash
python scripts/run-baseline.py \
    --project-dir "D:/my-project" \
    --iteration-id "iter-3"
```

---

## 框架结构

```
dev-framework/
├── FRAMEWORK-SPEC.md           # 框架规格书（核心文档）
├── README.md                   # 本文件
│
├── agents/                     # Agent 定义
│   ├── analyst.md              # 需求分析 Agent
│   ├── developer.md            # 开发执行 Agent
│   ├── reviewer.md             # 审查验收 Agent
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
│   │   ├── CLAUDE.md.tmpl
│   │   ├── ARCHITECTURE.md.tmpl
│   │   └── progress.md.tmpl
│   ├── tasks/                  # 任务模板
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
│   └── run-config.yaml         # 运行配置格式
│
├── scripts/                    # 自动化工具
│   ├── init-project.py         # 初始化新项目
│   ├── init-iteration.py       # 初始化迭代轮次
│   ├── run-baseline.py         # 运行基线测试
│   ├── run-verify.py           # 运行验收脚本
│   ├── check-quality-gate.py   # 质量门控检查
│   ├── generate-report.py      # 生成迭代报告
│   └── session-manager.py      # Session 状态管理
│
└── examples/                   # 示例（参考用）
    ├── init-mode-example/
    └── iterate-mode-example/
```

---

## 核心原则

| 原则 | 说明 |
|------|------|
| **P1 行业最优标准** | 需求拆解必须达到资深工程师级别，不产出简陋版本 |
| **P2 默认禁 Mock** | 仅白名单场景允许 Mock，必须声明理由 |
| **P3 磁盘为真相源** | 所有关键信息立即写入磁盘，不依赖对话上下文 |
| **P4 不可自评通过** | Developer 不能标记 PASS，只有 Reviewer 可以 |
| **P5 垂直切片** | 深度优先，一条链路做完再做下一条 |
| **P6 交互式确认** | 接收需求后必须先确认成熟度和处理路径 |

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
Developer(s): 编码 → L0 验收 → L1 测试 → commit
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

## 质量门控

| 门控 | 触发时机 | 检查内容 |
|------|---------|---------|
| Gate 0 | 环境就绪 | git 干净、工具可用 |
| Gate 1 | 需求审批 | 规格书完整、用户确认 |
| Gate 2 | 任务审批 | CR 格式正确、verify 完整 |
| Gate 3 | L0 验收 | verify 脚本全 PASS |
| Gate 4 | L1 回归 | 测试 ≥ 基线 |
| Gate 5 | 集成检查 | L1+L2+Lint 通过 |
| Gate 6 | 代码审查 | Reviewer PASS |
| Gate 7 | 最终验收 | 全量通过 |

---

## 常用命令

```bash
# 查看当前 session 状态
python scripts/session-manager.py --project-dir "D:/project" status

# 写入检查点
python scripts/session-manager.py --project-dir "D:/project" checkpoint

# 恢复 session 摘要
python scripts/session-manager.py --project-dir "D:/project" resume

# 运行验收脚本
python scripts/run-verify.py --project-dir "D:/project" --iteration-id "iter-3" --all

# 质量门控检查
python scripts/check-quality-gate.py --project-dir "D:/project" --gate gate_7

# 生成迭代报告
python scripts/generate-report.py --project-dir "D:/project" --iteration-id "iter-3"
```
