# Dev-Framework — 多代理协作开发框架

> 版本: v3.0 | 更新日期: 2026-02-21

统一的多代理协作开发框架，覆盖首次开发（init-mode）和多轮迭代开发（iterate-mode）。

基于五角色制衡模型（Leader / Analyst / Developer / Verifier / Reviewer），
通过 10 层质量门控（Gate 0-7 + Gate 2.5/3.5）和磁盘状态持久化，确保开发质量和上下文连续性。

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

### 已有项目升级（v2.6 → v3.0）

如果你的项目已使用 v2.6 版本的框架，运行升级脚本迁移到 v3.0：

```bash
# 先预览变更
python dev-framework/scripts/upgrade-project.py --project-dir "<项目路径>" --dry-run

# 确认无误后执行升级
python dev-framework/scripts/upgrade-project.py --project-dir "<项目路径>"
```

v3.0 核心变化：Agent 协议 + 质量门控合并到 `.claude/CLAUDE.md`（系统提示层，永不压缩），新增滚动上下文快照和 AutoLoop 外围循环脚本。

详见 [USER-GUIDE.md § 十、从 v2.6 升级到 v3.0](USER-GUIDE.md#十从-v26-升级到-v30)。

### 新项目初始化

```bash
python dev-framework/scripts/init-project.py \
    --project-dir "<项目路径>" \
    --requirement-doc "docs/requirements.md" \
    --tech-stack "python,react,fastapi"
```

### 已有项目迭代

```bash
python dev-framework/scripts/init-iteration.py \
    --project-dir "<项目路径>" \
    --requirement "修复搜索超时；新增批量导入" \
    --iteration-id "iter-3"
```

### 运行基线测试

```bash
python dev-framework/scripts/run-baseline.py \
    --project-dir "<项目路径>" \
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
├── templates/                  # 模板文件
│   ├── project/                # 项目级模板
│   │   ├── CLAUDE.md.tmpl      # 项目配置模板（v3.0 精简版）
│   │   ├── CLAUDE-framework.md.tmpl  # v3.0 新增：合并版框架运行时手册模板
│   │   ├── context-snapshot.md.tmpl  # v3.0 新增：滚动上下文快照模板
│   │   ├── run-config.yaml.tmpl     # 运行配置模板（init-project.py 优先复制此文件）
│   │   ├── ARCHITECTURE.md.tmpl
│   │   ├── progress.md.tmpl         # (参考模板，由 Agent 手动创建)
│   │   └── session-ledger.md.tmpl   # (参考模板，由 Agent 手动创建)
│   ├── tasks/                  # 任务模板（按变更类型）
│   │   ├── feature.yaml.tmpl   # 也用作 infrastructure 类型的基础模板
│   │   ├── bug-fix.yaml.tmpl
│   │   ├── enhancement.yaml.tmpl
│   │   ├── hotfix.yaml.tmpl
│   │   └── refactor.yaml.tmpl
│   └── verify/                 # 验证脚本模板
│       ├── verify-task.py.tmpl       # (参考文档，实际由 run-verify.py 内置生成)
│       └── verify-integration.py.tmpl
│
├── schemas/                    # 数据格式定义（仅作格式参考文档，不在运行时进行自动校验）
│   ├── task-schema.yaml        # 任务 YAML 格式
│   ├── feature-checklist.json  # 特性清单 JSON 格式
│   ├── session-state.json      # Session 状态格式
│   ├── baseline.json           # 基线测试结果格式
│   ├── manifest.json           # 迭代清单 JSON 格式
│   ├── manifest-schema.json    # 迭代清单 JSON Schema（可选的自动校验）
│   └── run-config.yaml         # 格式定义 + 默认配置（init-project.py 优先从 templates/ 复制，回退时使用此文件）
│
├── scripts/                    # 自动化工具（跨平台）
│   ├── init-project.py         # 初始化新项目
│   ├── init-iteration.py       # 初始化迭代轮次
│   ├── run-baseline.py         # 运行基线测试
│   ├── run-verify.py           # 运行验收脚本 / 生成验收骨架
│   ├── check-quality-gate.py   # 质量门控检查（Gate 0-7）
│   ├── phase-gate.py           # Phase 转换门控检查（含 Gate 2.5/3.5）
│   ├── estimate-tasks.py       # 任务拆分规模估算
│   ├── generate-report.py      # 生成迭代报告
│   ├── session-manager.py      # Session 状态管理
│   ├── upgrade-project.py      # 升级已有项目（v2.6 → v3.0）
│   ├── auto-loop-runner.py     # v3.0 新增：AutoLoop 外围循环脚本
│   └── fw_utils.py             # 工具链检测 + 通用辅助函数
│
├── reports/                    # 迭代报告输出目录
│
└── examples/                   # 示例（参考用）
    └── iterate-mode-example/   # 包含完整的 CR 示例
        ├── README.md
        ├── manifest.json
        ├── tasks/CR-001.yaml
        └── verify/CR-001.py
```

---

## 核心原则

六大核心原则（P1 行业最优标准 / P2 默认禁 Mock / P3 磁盘为真相源 / P4 不可自评通过 / P5 垂直切片 / P6 交互式确认）详见 [FRAMEWORK-SPEC.md §二](FRAMEWORK-SPEC.md)。

---

## 五角色制衡模型

五角色制衡模型（Leader / Analyst / Developer / Verifier / Reviewer）和权限分离详见 [FRAMEWORK-SPEC.md §三](FRAMEWORK-SPEC.md)。

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

配置: `.claude/dev-state/run-config.yaml`（运行时配置，由 `init-project.py` 从 `templates/project/run-config.yaml.tmpl` 复制生成）

---

## 质量门控

10 层质量门控（Gate 0-7 + Gate 2.5/3.5）详见 [FRAMEWORK-SPEC.md §六](FRAMEWORK-SPEC.md)。

---

## 常用命令

### 项目管理

```bash
# 初始化新项目
python dev-framework/scripts/init-project.py \
    --project-dir "<项目路径>" \
    --requirement-doc "docs/requirements.md" \
    --tech-stack "python,react"

# 初始化新迭代
python dev-framework/scripts/init-iteration.py \
    --project-dir "<项目路径>" \
    --requirement "修复搜索超时" \
    --iteration-id "iter-3"
```

### 测试与验收

```bash
# 运行基线测试
python dev-framework/scripts/run-baseline.py \
    --project-dir "<项目路径>" \
    --iteration-id "iter-3"

# 运行单个 CR 的验收
python dev-framework/scripts/run-verify.py \
    --project-dir "<项目路径>" \
    --iteration-id "iter-3" \
    --task-id "CR-001"

# 运行所有验收脚本
python dev-framework/scripts/run-verify.py \
    --project-dir "<项目路径>" \
    --iteration-id "iter-3" \
    --all

# 从任务 YAML 生成 verify 脚本骨架
python dev-framework/scripts/run-verify.py \
    --project-dir "<项目路径>" \
    --iteration-id "iter-3" \
    --generate-skeleton "CR-001"
```

### 质量门控

```bash
# 检查特定门控
python dev-framework/scripts/check-quality-gate.py \
    --project-dir "<项目路径>" \
    --gate gate_4

# 检查 L0 验收（需要 iteration-id 和 task-id）
python dev-framework/scripts/check-quality-gate.py \
    --project-dir "<项目路径>" \
    --gate gate_3 \
    --iteration-id "iter-3" \
    --task-id "CR-001"

# 检查所有门控
python dev-framework/scripts/check-quality-gate.py \
    --project-dir "<项目路径>" \
    --all
```

### Session 管理

```bash
# 查看当前 session 状态
python dev-framework/scripts/session-manager.py \
    --project-dir "<项目路径>" status

# 写入检查点
python dev-framework/scripts/session-manager.py \
    --project-dir "<项目路径>" checkpoint

# 恢复 session 摘要
python dev-framework/scripts/session-manager.py \
    --project-dir "<项目路径>" resume

# 写入 Session Ledger（Team 并行台账）
python dev-framework/scripts/session-manager.py \
    --project-dir "<项目路径>" ledger
```

### 报告与估算

```bash
# 生成迭代报告
python dev-framework/scripts/generate-report.py \
    --project-dir "<项目路径>" \
    --iteration-id "iter-3"

# 任务拆分规模估算
python dev-framework/scripts/estimate-tasks.py \
    --modules 5 --risk high --complexity moderate --mode iterate
```

### AutoLoop 运行（v3.0 新增）

```bash
# 启动 AutoLoop 外围循环
python dev-framework/scripts/auto-loop-runner.py \
    --project-dir "<项目路径>" \
    --iteration-id "iter-3" \
    --max-restarts 10
```

### 项目升级

```bash
# 升级已有项目（v2.6 → v3.0）
python dev-framework/scripts/upgrade-project.py \
    --project-dir "<项目路径>" \
    --dry-run

# 确认无误后正式升级
python dev-framework/scripts/upgrade-project.py \
    --project-dir "<项目路径>"
```

---

## 文档索引

| 文档 | 内容 |
|------|------|
| [FRAMEWORK-SPEC.md](FRAMEWORK-SPEC.md) | 框架规格书（核心文档，完整流程定义） |
| [ARCHITECTURE.md](ARCHITECTURE.md) | 架构决策记录（12 条 ADR） |
| [USER-GUIDE.md](USER-GUIDE.md) | 使用指导手册（场景示例 + FAQ） |

---

## 示例

`examples/iterate-mode-example/` 目录包含一个完整的迭代示例：

- `README.md` — 示例说明文档
- `manifest.json` — 迭代元信息
- `tasks/CR-001.yaml` — 完整的 bug_fix 类型任务文件
- `verify/CR-001.py` — 对应的验收脚本

参考此示例理解任务文件的字段要求和验收脚本的编写规范。
