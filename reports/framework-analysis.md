# Dev-Framework v3.0 全景分析报告

## 一、项目总览

Dev-Framework 是一套**多 Agent 协作开发框架**，用于规范化管理 AI Agent（如 Claude Code）的软件开发全流程。它不是一个可运行的应用程序，而是一套**流程规范 + 工具脚本 + 模板系统**。

核心目标：让 AI Agent 按照工程化流程完成从需求分析到代码交付的全过程，同时保证质量可控。

---

## 二、目录结构与文件作用

```
dev-framework/
│
├── FRAMEWORK-SPEC.md          ← 核心规范书（23KB，框架的"宪法"）
├── ARCHITECTURE.md            ← 架构决策记录（13条ADR）
├── README.md                  ← 快速入门指南
├── USER-GUIDE.md              ← 详细使用手册（场景走读）
├── requirements.txt           ← Python 依赖（PyYAML）
├── .gitignore
│
├── scripts/                   ← 工具脚本（框架的"引擎"）
│   ├── init-project.py        ← 新项目初始化
│   ├── init-iteration.py      ← 迭代初始化
│   ├── run-baseline.py        ← 基线测试运行
│   ├── run-verify.py          ← 验收脚本执行
│   ├── check-quality-gate.py  ← 质量门控检查（Gate 0-7）
│   ├── phase-gate.py          ← Phase 转换门控
│   ├── session-manager.py     ← 会话状态管理
│   ├── auto-loop-runner.py    ← AutoLoop 自动循环
│   ├── generate-report.py     ← 迭代报告生成
│   ├── estimate-tasks.py      ← 任务规模估算
│   ├── upgrade-project.py     ← v2.6→v3.0 升级
│   └── fw_utils.py            ← 公共工具函数库
│
├── schemas/                   ← 数据格式定义
│   ├── task-schema.yaml       ← 任务 YAML 格式规范
│   ├── manifest.json          ← 迭代清单格式
│   ├── manifest-schema.json   ← 清单 JSON Schema
│   ├── session-state.json     ← 会话状态格式
│   ├── baseline.json          ← 基线测试格式
│   ├── run-config.yaml        ← 运行配置格式
│   └── feature-checklist.json ← 特性清单格式
│
├── templates/                 ← 模板文件
│   ├── project/               ← 项目级模板
│   │   ├── CLAUDE.md.tmpl              ← 项目配置模板
│   │   ├── CLAUDE-framework.md.tmpl    ← 框架手册模板（核心）
│   │   ├── context-snapshot.md.tmpl    ← 上下文快照模板
│   │   ├── run-config.yaml.tmpl        ← 运行配置模板
│   │   ├── session-ledger.md.tmpl      ← 并行台账模板
│   │   ├── progress.md.tmpl            ← 进度模板
│   │   └── ARCHITECTURE.md.tmpl        ← 架构文档模板
│   ├── tasks/                 ← 任务模板
│   │   ├── feature.yaml.tmpl           ← 新功能任务
│   │   ├── bug-fix.yaml.tmpl           ← Bug修复任务
│   │   ├── enhancement.yaml.tmpl       ← 增强任务
│   │   ├── hotfix.yaml.tmpl            ← 紧急修复任务
│   │   └── refactor.yaml.tmpl          ← 重构任务
│   └── verify/                ← 验收脚本模板
│       ├── verify-task.py.tmpl         ← 单任务验收
│       └── verify-integration.py.tmpl  ← 集成验收
│
├── examples/                  ← 示例
│   └── iterate-mode-example/  ← 迭代模式示例
│       ├── manifest.json
│       ├── tasks/CR-001.yaml
│       ├── verify/CR-001.py
│       └── README.md
│
└── reports/                   ← 报告输出目录
```

---

## 三、文件之间的关系图

```
┌─────────────────────────────────────────────────────────────────────┐
│                        文 档 层（规范定义）                           │
│                                                                     │
│  FRAMEWORK-SPEC.md ◄──── 核心规范，所有流程/规则的权威定义             │
│        │                                                            │
│        ├─► ARCHITECTURE.md    架构决策记录（ADR），解释"为什么"         │
│        ├─► README.md          快速入门，引用 SPEC 和 USER-GUIDE       │
│        └─► USER-GUIDE.md      使用指南，引用 SPEC 的具体操作方法       │
└────────────────┬────────────────────────────────────────────────────┘
                 │ 规范 → 实现
                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        脚 本 层（流程引擎）                           │
│                                                                     │
│  fw_utils.py ◄──── 公共工具库，被所有其他脚本 import                   │
│       ▲                                                             │
│       │ import                                                      │
│  ┌────┼─────────────────────────────────────────────────┐           │
│  │    │                                                 │           │
│  │  init-project.py ──► 读取 templates/ ──► 生成项目骨架  │           │
│  │  init-iteration.py ──► 创建迭代目录                    │           │
│  │  run-baseline.py ──► 写入 baseline.json               │           │
│  │  phase-gate.py ──► 读取 tasks/*.yaml 检查门控          │           │
│  │  run-verify.py ──► 执行 verify/*.py 脚本               │           │
│  │  check-quality-gate.py ──► 综合质量检查                │           │
│  │  session-manager.py ──► 管理 session-state.json       │           │
│  │  auto-loop-runner.py ──► 调用 Claude CLI 循环执行      │           │
│  │  generate-report.py ──► 汇总任务数据生成报告            │           │
│  │  estimate-tasks.py ──► 预估任务数量                    │           │
│  │  upgrade-project.py ──► 读取旧版本 + templates 升级     │           │
│  └──────────────────────────────────────────────────────┘           │
└────────────────┬────────────────────────────────────────────────────┘
                 │ 生成 / 操作
                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   数据层（目标项目中生成的状态文件）                    │
│                                                                     │
│  {project}/.claude/                                                 │
│  ├── CLAUDE.md ◄──── 合并版（框架手册+项目配置），Claude 自动加载       │
│  └── dev-state/                                                     │
│      ├── session-state.json ◄──── 实时进度/状态                      │
│      ├── baseline.json ◄──── 基线测试结果                            │
│      ├── context-snapshot.md ◄──── 跨会话恢复快照                     │
│      ├── run-config.yaml ◄──── 运行模式配置                          │
│      └── iter-N/                                                    │
│          ├── manifest.json ◄──── 迭代元信息                          │
│          ├── tasks/CR-*.yaml ◄──── 任务状态+验收标准+证据              │
│          ├── verify/CR-*.py ◄──── 验收脚本                           │
│          ├── checkpoints/ ◄──── 进度快照                             │
│          └── decisions.md ◄──── 技术决策日志                          │
└─────────────────────────────────────────────────────────────────────┘
```

**模板 → 脚本 → 数据的生成关系：**

```
templates/project/CLAUDE-framework.md.tmpl ──┐
templates/project/CLAUDE.md.tmpl ────────────┼──► init-project.py ──► .claude/CLAUDE.md
                                             │
templates/project/run-config.yaml.tmpl ──────┼──► init-project.py ──► run-config.yaml
templates/project/context-snapshot.md.tmpl ──┘──► init-project.py ──► context-snapshot.md

templates/tasks/feature.yaml.tmpl ──► Analyst Agent 参考 ──► tasks/CR-001.yaml
templates/verify/verify-task.py.tmpl ──► run-verify.py --generate-skeleton ──► verify/CR-001.py

schemas/task-schema.yaml ──► 定义 tasks/CR-*.yaml 的合法字段和取值
schemas/session-state.json ──► 定义 session-state.json 的字段格式
```

---

## 四、五角色制衡模型

框架的核心设计是 **5 个 Agent 角色**的权限分离，防止"自己写代码自己验收"：

```
                        ┌──────────┐
                        │  Leader  │  总指挥：任务分配、进度管控、用户沟通
                        └────┬─────┘
                             │ 分配任务
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
        ┌──────────┐  ┌──────────┐  ┌──────────────┐
        │ Analyst  │  │Developer │  │   Verifier   │
        │ 需求分析  │  │ 编码实现  │  │  独立验收     │
        └────┬─────┘  └────┬─────┘  └──────┬───────┘
             │              │               │
             │ 拆分任务      │ 提交代码       │ 运行验收脚本
             │ 生成verify   │ ready_for_     │ 填写evidence
             │ 脚本         │ verify         │ ready_for_review
             │              │               │
             └──────────────┼───────────────┘
                            ▼
                     ┌──────────────┐
                     │   Reviewer   │  终审判决：PASS 或 rework
                     └──────────────┘

  关键制衡：
  ✗ Developer 不能运行自己的 verify 脚本
  ✗ Verifier 不能修改代码
  ✗ 只有 Reviewer 有权标记 PASS
  ✗ Analyst 不能写代码，只能写文档和脚本
```

---

## 五、完整业务流程（Phase 0 → Phase 5）

```
╔═══════════════════════════════════════════════════════════════╗
║ Phase 0: 环境初始化                                          ║
║  init-project.py / init-iteration.py                         ║
║  → 检查工具链（Python, pytest, Git）                          ║
║  → 运行基线测试 (run-baseline.py → baseline.json)             ║
║  → 生成项目骨架 / 迭代目录                                    ║
║  Gate 0: 环境就绪 ✓                                          ║
╚══════════════════════════════╤════════════════════════════════╝
                               │
                               ▼
╔═══════════════════════════════════════════════════════════════╗
║ Phase 1: 需求接收与深化 (Analyst)                             ║
║  1. 评估需求成熟度（高/中/低）                                 ║
║  2. 路径选择：                                                ║
║     A: 成熟度高 → 直接拆分                                    ║
║     B: 成熟度中 → 协助完善                                    ║
║     C: 成熟度低 → 补充信息                                    ║
║  3. 8维度补全：功能、UX、健壮性、可观测、配置、性能、安全、测试    ║
║  4. 输出: requirement-spec.md                                 ║
║  Gate 1: 需求审批 ✓ (Interactive 模式暂停等用户确认)            ║
╚══════════════════════════════╤════════════════════════════════╝
                               │
                               ▼
╔═══════════════════════════════════════════════════════════════╗
║ Phase 2: 影响分析与任务拆分 (Analyst)                         ║
║  1. 七路径审视：                                              ║
║     Happy → Sad → Edge → Perf → UX → Guard → Ops            ║
║  2. 为每个 CR 生成：                                          ║
║     tasks/CR-001.yaml  ← 任务定义 + 验收标准                   ║
║     verify/CR-001.py   ← 零 Mock 验收脚本                     ║
║  Gate 2: 任务拆分审批 ✓                                       ║
╚══════════════════════════════╤════════════════════════════════╝
                               │
                               ▼
╔═══════════════════════════════════════════════════════════════╗
║ Phase 3 + 3.5 + 4: 开发 → 验收 → 审查（循环）                 ║
║                                                              ║
║  详见下方「开发循环流程图」和「任务状态机」                       ║
║                                                              ║
║  Gate 2.5: 所有 CR ≥ ready_for_verify（进入验收）              ║
║  Gate 3.5: 所有 CR ≥ ready_for_review（进入审查）              ║
║  Gate 4→5: 所有 CR = PASS + evidence + review_result          ║
╚══════════════════════════════╤════════════════════════════════╝
                               │
                               ▼
╔═══════════════════════════════════════════════════════════════╗
║ Phase 5: 交付                                                ║
║  1. 全量测试 ≥ 基线 (Gate 4: L1 回归)                         ║
║  2. Lint 通过                                                 ║
║  3. 生成迭代报告 (generate-report.py)                          ║
║  4. git push                                                  ║
║  Gate 7: 最终验收 ✓ (phase-gate.py --check-completion)        ║
╚═══════════════════════════════════════════════════════════════╝
```

---

## 六、开发循环流程图

> 出处：`FRAMEWORK-SPEC.md` §6.2 + `run-verify.py:99`

```
                    ┌──────────────────────────────────┐
                    │          Developer 修复           │
                    │          (retries+1)             │
                    │                                  │
                    ▼                                  │
             ready_for_verify                          │
                    │                                  │
                    ▼                                  │
            ┌──────────────┐     失败                   │
            │ Verifier 验收 ├──────────► rework ────────┘
            └──────┬───────┘
                   │ 通过
                   ▼
            ready_for_review
                   │
                   ▼
            ┌──────────────┐     打回
            │ Reviewer 审查 ├──────────► rework ────────┘
            └──────┬───────┘                (同一个rework,
                   │ 通过                    回到最上方)
                   ▼
                 PASS
```

**要点：**
- 两条打回路径（Verifier 失败、Reviewer 打回）汇入同一个 rework
- rework 只有一条出路：回到最上方的 `ready_for_verify`，完整重走 Verifier → Reviewer
- 不允许从 rework 直接跳到 `ready_for_review`（SPEC §6.2 明确禁止）
- 每次 rework 时 retries+1，达到 max_retries（默认 2）则转为 failed

---

## 七、任务状态机

> 出处：`FRAMEWORK-SPEC.md` §6.2 + `schemas/task-schema.yaml:160-177`

```
                         Developer        Verifier        Reviewer
                         ─────────        ────────        ────────

  pending ──► in_progress ──► ready_for_verify ──► ready_for_review ──► PASS
                                   │  ▲                 │
                              失败  │  │ Developer修复    │ 打回
                                   ▼  │                 │
                                  rework ◄──────────────┘
                                   │
                               ≥max_retries
                                   ▼
                                 failed


  另外两个特殊状态（可从任意过程态进入）:
    blocked  — 外部依赖阻塞
    timeout  — 单任务执行超时
```

**每条边的执行者和代码出处：**

| 转换 | 执行者 | 出处 |
|------|--------|------|
| pending → in_progress | Developer | SPEC §6.2 |
| in_progress → ready_for_verify | Developer | SPEC §6.2 |
| ready_for_verify → ready_for_review | Verifier（验收通过）| `run-verify.py:99` |
| ready_for_verify → rework | Verifier（验收失败）| `run-verify.py:99` |
| ready_for_review → PASS | Reviewer（审查通过）| SPEC §6.2 |
| ready_for_review → rework | Reviewer（审查打回）| SPEC §6.2 line 66 |
| rework → ready_for_verify | Developer（修复后）| SPEC: "不允许从 rework 直接跳到 ready_for_review" |
| rework → failed | Leader | retries ≥ max_retries（默认 2）|

---

## 八、10 层质量门控系统

```
Phase 0 ──► Gate 0 (环境就绪)
              │ 检查: 工具链 + 基线测试
              ▼
Phase 1 ──► Gate 1 (需求审批)
              │ 检查: requirement-spec.md 存在
              ▼
Phase 2 ──► Gate 2 (任务拆分审批)
              │ 检查: tasks/*.yaml + verify/*.py 完整 + 脚本质量
              ▼
Phase 3 ──► Gate 2.5 (开发→验收)
              │ 检查: 所有 CR ≥ ready_for_verify
              ▼
Phase 3.5 ─► Gate 3 (L0验收) + Gate 3.5 (验收→审查)
              │ 检查: verify 脚本 PASS + 所有 CR ≥ ready_for_review
              ▼
Phase 4 ──► Gate 4 (L1回归) + Gate 5 (集成) + Gate 6 (代码审查)
              │ 检查: 单元测试≥基线 + E2E + Reviewer PASS
              ▼
Phase 5 ──► Gate 7 (最终验收)
              │ 检查: 全量测试 + lint + 所有 CR=PASS
              ▼
            交付完成 ✓
```

---

## 九、两种运行模式

```
┌─────────────────────────────────────┬──────────────────────────────────────┐
│        Interactive 模式（默认）       │        Auto Loop 模式（全自动）        │
├─────────────────────────────────────┼──────────────────────────────────────┤
│                                     │                                      │
│  Phase 0 ──► Phase 1                │  Phase 0 ──► Phase 1                 │
│              ⏸ 暂停: 需求审批         │              (无暂停)                  │
│  Phase 1 ──► Phase 2                │  Phase 1 ──► Phase 2                 │
│              ⏸ 暂停: 方案审批         │              (无暂停)                  │
│  Phase 2 ──► Phase 3 ──► 3.5 ──► 4  │  Phase 2 ──► Phase 3 ──► 3.5 ──► 4  │
│              ⏸ 暂停: 审查结果         │              (无暂停)                  │
│  Phase 4 ──► Phase 5                │  Phase 4 ──► Phase 5                 │
│              ⏸ 暂停: 交付确认         │              (无暂停)                  │
│                                     │                                      │
│  适合: 日常开发、初次使用              │  适合: 需求明确、大批量任务              │
│                                     │                                      │
│                                     │  6 重安全阀:                           │
│                                     │  1. 连续失败 N 次                      │
│                                     │  2. 基线退化                           │
│                                     │  3. 磁盘空间不足                       │
│                                     │  4. Git 冲突                          │
│                                     │  5. 单任务超时                         │
│                                     │  6. 连续无进展                         │
└─────────────────────────────────────┴──────────────────────────────────────┘
```

---

## 十、脚本调用关系

**项目生命周期中的脚本调用顺序：**

```
新项目:
  init-project.py ──► run-baseline.py ──► [Claude Agent 开发] ──► generate-report.py

迭代开发:
  init-iteration.py ──► run-baseline.py ──► [Claude Agent 开发] ──► generate-report.py

                                            开发过程中调用:
                                            ├── session-manager.py (checkpoint/resume)
                                            ├── phase-gate.py (每次 Phase 转换)
                                            ├── run-verify.py (Phase 3.5 验收)
                                            └── check-quality-gate.py (各 Gate 检查)

Auto Loop:
  auto-loop-runner.py ──► 循环调用 Claude CLI ──► 检查安全阀 ──► 重启或停止

升级:
  upgrade-project.py ──► 读取旧版本文件 + templates/ ──► 生成新版本文件
```

**每个脚本与其操作的数据文件：**

| 脚本 | 读取 | 写入 |
|------|------|------|
| `init-project.py` | `templates/*` | `.claude/CLAUDE.md`, `session-state.json`, `baseline.json`, `run-config.yaml`, `manifest.json` |
| `init-iteration.py` | `session-state.json` | `iter-N/manifest.json`, `requirement-raw.md`, `decisions.md` |
| `run-baseline.py` | `run-config.yaml` | `baseline.json` |
| `phase-gate.py` | `tasks/*.yaml`, `verify/*.py`, `manifest.json` | `manifest.json`(更新 phase) |
| `run-verify.py` | `tasks/*.yaml`, `verify/*.py` | `tasks/*.yaml`(更新 status/evidence) |
| `check-quality-gate.py` | `baseline.json`, `tasks/*.yaml` | 无（只输出检查结果） |
| `session-manager.py` | `session-state.json`, `tasks/*.yaml` | `session-state.json`, `checkpoints/*.md`, `resume-summary.md` |
| `auto-loop-runner.py` | `session-state.json`, `run-config.yaml`, `tasks/*.yaml` | `session-state.json` |
| `generate-report.py` | `tasks/*.yaml`, `baseline.json` | `reports/*.md` |

---

## 十一、核心设计原则

| 原则 | 含义 | 为什么 |
|------|------|--------|
| **P1** 需求拆解最优标准 | 8 维度审查每个需求 | 防止"遗漏需求导致返工" |
| **P2** 默认禁止 Mock | 验收脚本用真实环境运行 | 防止"Mock 通过但真实失败" |
| **P3** 磁盘为真相源 | 所有状态写磁盘文件 | Claude 会话中断后可完整恢复 |
| **P4** 不可自评通过 | Developer→Verifier→Reviewer 三层 | 防止"自己写自己过" |
| **P5** 垂直切片 | 基础设施先行，后续功能可并行 | 减少任务间依赖 |
| **P6** 需求交互确认 | 成熟度评估后选择路径 | 防止"理解偏差导致全部返工" |

---

## 十二、总结

这是一个**面向 AI Agent 的软件开发流程管控框架**，核心价值：

1. **规范化**：将软件开发拆为 6 个 Phase + 10 层 Gate，每步都有明确输入输出
2. **质量保障**：5 角色制衡 + 零 Mock 验收 + 三层审查，防止 AI 自产自销
3. **可恢复性**：磁盘状态为唯一真相源 + 滚动快照，会话中断不丢失进度
4. **自动化**：从项目初始化到报告生成的完整脚本链，支持 AutoLoop 全自动运行
