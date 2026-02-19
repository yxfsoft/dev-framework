# Dev-Framework 使用指导手册

> **路径约定**：本文档中的 `dev-framework/scripts/` 指框架仓库的 scripts 目录。
> 如果框架不在项目子目录下，请替换为框架的实际安装路径（如 `D:/tools/dev-framework/scripts/`）。

---

## 一、概念速查

### 三种项目场景

| 场景 | 说明 | 用哪个脚本 |
|------|------|-----------|
| **新项目一次开发** | 从零开始，只有需求文档 | `init-project.py` |
| **老项目多轮迭代** | 项目已用框架管理，加新需求 | `init-iteration.py` |
| **接手项目首次纳管** | 已有代码但没用过框架 | 先 `init-project.py`，再 `init-iteration.py` |

### 两种运行模式

| 模式 | 说明 | 适用场景 |
|------|------|---------|
| **Interactive**（默认） | 需求审批、任务方案、审查结果这几个节点暂停等你确认，其余全自动 | 日常开发，你想把关关键决策 |
| **Auto Loop** | 全自动跑完 Phase 0→5，只在安全阀触发时停止 | 大批量任务、夜间执行、你信任框架流程 |

### 三种需求输入

| 类型 | 例子 | Analyst 怎么处理 |
|------|------|-----------------|
| **一句话需求** | "搜索太慢了" | 标记低成熟度，默认走路径 B（逐维度协助完善） |
| **粗概要需求** | "优化搜索：加缓存、混合检索、过滤面板" | 标记中成熟度，补充缺失维度后拆分 |
| **完善需求文档** | 包含功能规格、性能指标、验收标准的完整 PRD | 标记高成熟度，可直接走路径 A（直接拆分） |

三种输入最终都会经过**成熟度评估 → 交互确认（A/B/C）→ 需求规格书**的统一流程，区别只在于 Analyst 需要补多少内容。

---

## 二、场景 A：新项目一次开发

### 适用情况

你有一份需求文档（或脑子里的想法），要从零搭建一个完整项目。

### 操作步骤

#### Step 1：准备需求文档

把需求写成一个文件，放在任意位置。内容多少都行——一句话、一页概要、一份完整 PRD 都可以。

#### Step 2：初始化项目

```bash
python dev-framework/scripts/init-project.py \
    --project-dir "D:/my-new-app" \
    --requirement-doc "D:/my-new-app/docs/requirements.md" \
    --tech-stack "python,fastapi,vue"
```

**参数说明：**

- `--project-dir` — 项目目录。不存在会自动创建
- `--requirement-doc` — 需求文档路径。脚本只记录路径，不解析内容
- `--tech-stack` — 技术栈，逗号分隔。写入 CLAUDE.md 供所有 Agent 参考

**执行后产物：**

```
D:/my-new-app/
├── .claude/
│   ├── agents/           ← 5 个角色协议
│   ├── dev-state/
│   │   ├── session-state.json   ← current_phase: "phase_0"
│   │   ├── baseline.json        ← 空基线（L1=0, L2=0）
│   │   ├── run-config.yaml      ← 运行模式配置
│   │   ├── experience-log.md
│   │   └── iteration-0/         ← 首次开发 = 第 0 轮迭代
│   │       ├── manifest.json    ← mode: "init"
│   │       ├── requirement-raw.md
│   │       ├── tasks/
│   │       ├── verify/
│   │       ├── checkpoints/
│   │       └── decisions.md
│   └── CLAUDE.md          ← ⚠️ 有占位符需要手动填写
├── ARCHITECTURE.md
├── config/default.yaml
├── tests/unit/
├── tests/integration/
└── docs/
```

#### Step 3：填写 CLAUDE.md

打开 `.claude/CLAUDE.md`，填写以下占位符：

| 占位符 | 填什么 | 举例 |
|--------|--------|------|
| `{{PROJECT_DESCRIPTION}}` | 项目一句话描述 | "企业级全文搜索系统" |
| `{{PROJECT_OVERVIEW}}` | 项目详细概述 | "基于向量检索的文档搜索平台，支持 OCR..." |
| `{{PACKAGE_MANAGERS}}` | 包管理器 | "pip (Python), pnpm (前端)" |
| `{{CODE_STYLE}}` | 代码风格规范 | "Python: ruff + black, 行宽 120" |
| `{{DIRECTORY_STRUCTURE}}` | 目录结构说明 | 列出主要目录的用途 |
| `{{SECURITY_POLICY}}` | 安全策略 | "API 密钥存 .env，不入 Git" |
| `{{PROJECT_URL}}` | 项目地址 | "https://github.com/..." |

`{{PROJECT_NAME}}` 和 `{{TECH_STACK}}` 已由脚本自动填写。

#### Step 4：启动 Claude Code

在项目目录下启动 Claude Code，输入：

> 请按照 .claude/agents/leader.md 的协议，以 init-mode 启动开发流程。需求文档在 docs/requirements.md。

Claude 会按以下流程自动执行：

```
Phase 0  环境初始化 → 项目骨架 + 基础设施
Phase 1  读需求 → 成熟度评估 → 交互确认 → 需求规格书
Phase 2  架构设计 → 基础设施拆分 + 垂直切片拆分 → verify 脚本
Phase 3  编码（基础设施批次 → 切片批次）
Phase 3.5 Verifier 独立验收
Phase 4  Reviewer 代码审查
Phase 5  全量测试 → 迭代报告 → git push
```

---

### 示例：一句话需求建新项目

```bash
# 需求文档只有一句话：
echo "做一个个人知识库搜索工具" > D:/knowledge-search/docs/requirements.md

python dev-framework/scripts/init-project.py \
    --project-dir "D:/knowledge-search" \
    --requirement-doc "docs/requirements.md" \
    --tech-stack "python,fastapi,sqlite,vue"
```

启动 Claude Code 后，Analyst 会：
1. 读到这句话，评估为**低成熟度**
2. 展示评估结果，建议走**路径 B**（协助完善）
3. 逐维度与你交互：
   - "功能行为：搜索什么内容？文本？PDF？网页书签？"
   - "用户体验：是 Web 界面还是命令行？需要实时搜索建议吗？"
   - "性能：预计数据量多大？搜索响应时间目标？"
   - "安全：是否需要登录？数据敏感吗？"
4. 全部确认后输出完整的 requirement-spec.md
5. 等你审批后进入 Phase 2 拆分任务

### 示例：粗概要需求建新项目

```
# docs/requirements.md 内容：
## 个人知识库搜索工具

核心功能：
- 从本地文件夹导入 Markdown/PDF/网页书签
- OCR 识别图片中的文字
- 全文搜索 + 向量语义搜索
- Web 界面，支持过滤和排序

技术约束：
- 纯本地部署，不依赖云服务
- SQLite 存储元数据，Milvus Lite 存储向量
```

Analyst 评估为**中成熟度**，会补充缺失的维度（性能指标、错误处理、数据迁移等），然后让你确认。

### 示例：完善需求文档建新项目

```
# docs/requirements.md 内容（节选）：
## 1. 概述
个人知识库搜索工具，纯本地部署。

## 2. 功能规格
### 2.1 数据导入
- 支持 Markdown (.md)、PDF (.pdf)、HTML 书签导出
- 导入时自动 OCR（Tesseract），提取图片中文字
- 导入进度条，预计 1000 文件 < 5 分钟

### 2.2 搜索
- 全文搜索（SQLite FTS5）+ 向量搜索（Milvus Lite）
- 混合排序：BM25 * 0.4 + 向量相似度 * 0.6
- 搜索响应 < 500ms（10 万条数据）
- 支持过滤：文件类型、日期范围、标签

## 3. 验收标准
- AC1: 导入 1000 个 Markdown 文件，搜索能命中所有文件
- AC2: 搜索 "机器学习" 返回 Top 10 中至少 8 个相关
- AC3: 搜索响应 P95 < 500ms
...
```

Analyst 评估为**高成熟度**，建议走**路径 A**（直接拆分），但仍会用八维度检查补全遗漏（如错误处理、日志格式等）。

---

## 三、场景 B：老项目多轮迭代

### 适用情况

项目已经用框架管理过（`.claude/dev-state/` 目录已存在），现在要加新一轮需求。

### 操作步骤

#### Step 1：初始化新迭代

```bash
python dev-framework/scripts/init-iteration.py \
    --project-dir "D:/knowledge-search" \
    --requirement "搜索结果高亮关键词；新增标签管理功能" \
    --iteration-id "iter-2"
```

**参数说明：**

- `--project-dir` — 已有项目目录（必须有 `.claude/dev-state/`）
- `--requirement` — 这轮迭代要做什么。直接写文字，Analyst 会深化它
- `--iteration-id` — 迭代编号，你自己命名。会创建对应目录。不能跟已有的重复

**执行后产物：**

```
.claude/dev-state/
├── session-state.json      ← current_iteration 更新为 "iter-2"
├── baseline.json            ← 上一轮的基线（不动）
└── iter-2/                  ← 新建
    ├── manifest.json        ← mode: "iterate"
    ├── requirement-raw.md   ← 你写的需求文字
    ├── tasks/
    ├── verify/
    ├── checkpoints/
    └── decisions.md
```

#### Step 2：运行基线测试（推荐）

```bash
python dev-framework/scripts/run-baseline.py \
    --project-dir "D:/knowledge-search" \
    --iteration-id "iter-2"
```

这会运行 L1 单元测试 + L2 集成测试 + Lint，把当前项目的测试状态记录到 `baseline.json`。后续开发过程中，测试结果不能低于这个基线。

**参数说明：**

- `--project-dir` — 项目目录
- `--iteration-id` — 写入 baseline.json 的迭代标记

#### Step 3：启动 Claude Code

```
请按照 .claude/agents/leader.md 的协议，以 iterate-mode 继续开发。
当前迭代是 iter-2。
```

---

### 示例：一句话迭代需求

```bash
python dev-framework/scripts/init-iteration.py \
    --project-dir "D:/knowledge-search" \
    --requirement "搜索太慢了" \
    --iteration-id "iter-3"
```

Analyst 会：
1. 读现有代码（search_service.py 等），理解当前搜索实现
2. 评估为**低成熟度**："搜索太慢"没有量化目标，没有范围界定
3. 交互确认，建议路径 B，逐维度补充：
   - "当前搜索 P95 响应时间是多少？目标降到多少？"
   - "是全部查询都慢还是特定场景？"
   - "可以接受缓存带来的数据延迟吗？"

### 示例：粗概要迭代需求

```bash
python dev-framework/scripts/init-iteration.py \
    --project-dir "D:/knowledge-search" \
    --requirement "优化搜索性能：1.加查询缓存 2.混合检索权重可配置 3.搜索结果分页" \
    --iteration-id "iter-3"
```

Analyst 评估为**中成熟度**——有明确的三个改动点，但缺少性能指标和边界条件。
补充后拆分为 3-5 个 CR。

### 示例：完善迭代需求

```bash
python dev-framework/scripts/init-iteration.py \
    --project-dir "D:/knowledge-search" \
    --requirement "$(cat <<'EOF'
## 搜索性能优化

### 问题
搜索 API P95 响应时间 3.2s，目标降到 500ms 以内。

### 方案
1. 查询缓存（LRU, maxsize=256, TTL=300s）
2. 混合检索权重从硬编码改为配置项
3. 搜索结果分页（默认 20 条/页）

### 验收标准
- AC1: P95 响应时间 < 500ms（10万条数据）
- AC2: 缓存命中率 > 60%（重复查询场景）
- AC3: 分页参数 page/size 生效
- AC4: 权重配置修改后无需重启

### 不改的部分
- 索引逻辑不动
- 前端 UI 不动（仅 API 层变更）
EOF
)" \
    --iteration-id "iter-3"
```

Analyst 评估为**高成熟度**，直接走路径 A。可能只补充一些边界条件（如缓存满时的策略、异常大 page 值的处理）。

---

## 四、场景 C：接手项目首次纳管

### 适用情况

你接手了一个别人写的项目（或者自己之前没用框架的老项目），想用框架来管理后续开发。

### 操作步骤

#### Step 1：在已有项目上初始化框架

```bash
python dev-framework/scripts/init-project.py \
    --project-dir "D:/legacy-crm" \
    --requirement-doc "docs/handover-notes.md" \
    --tech-stack "java,spring-boot,mysql,vue"
```

脚本只**添加**框架文件，不修改任何已有代码。`--requirement-doc` 可以指向交接文档、README、或任何描述项目的文件。

#### Step 2：填写 CLAUDE.md（关键步骤）

这一步比新项目更重要，因为 Agent 对这个项目一无所知，CLAUDE.md 是它理解项目的唯一入口。

重点填写：
- `{{PROJECT_OVERVIEW}}` — 项目做什么、核心业务逻辑
- `{{DIRECTORY_STRUCTURE}}` — 目录结构，特别是代码在哪、配置在哪、测试在哪
- `{{CODE_STYLE}}` — 项目现有的代码风格（Agent 要延续而不是自己发明一套）

#### Step 3：运行基线测试

```bash
python dev-framework/scripts/run-baseline.py \
    --project-dir "D:/legacy-crm" \
    --iteration-id "iteration-0"
```

记录当前项目的测试状态。如果项目本来就有失败的测试，会被记录为"预存失败"，后续不算回归。

#### Step 4：开始第一轮迭代

```bash
python dev-framework/scripts/init-iteration.py \
    --project-dir "D:/legacy-crm" \
    --requirement "修复客户列表分页 bug；新增按区域筛选" \
    --iteration-id "iter-1"
```

然后启动 Claude Code：

```
请按照 .claude/agents/leader.md 的协议，以 iterate-mode 开始开发。
这是一个我接手的项目，首次使用框架管理。请先仔细阅读项目代码了解现状。
当前迭代是 iter-1。
```

Analyst 会花更多时间在 Phase 1 读代码理解现状，然后再做需求深化和影响分析。

---

## 五、Interactive 模式 vs Auto Loop 模式

### Interactive 模式（默认）

**配置：** `.claude/dev-state/run-config.yaml` 中 `mode: "interactive"`

**流程中的暂停点：**

```
Phase 1 → ⏸ 需求规格书审批（展示给你看，你确认或修改）
Phase 2 → ⏸ 任务拆分方案审批（展示 CR 列表和 verify 脚本，你确认）
Phase 4 → ⏸ 审查结果通报（告知哪些 CR 通过/打回）
Phase 5 → ⏸ 迭代完成汇总（展示报告，确认后 git push）
```

**自动执行的部分：**

```
环境检查、编码、测试、验收脚本运行、checkpoint 写入 — 全自动
```

**适合：**
- 日常开发，你想把关需求理解和任务拆分
- 第一次用框架，想观察流程
- 需求不够明确，需要交互完善

### Auto Loop 模式

**配置：** 修改 `.claude/dev-state/run-config.yaml`：

```yaml
mode: "auto-loop"

auto_loop:
  max_retries_per_task: 2      # 单任务最大重试次数
  max_parallel_agents: 2       # 最大并行 Agent 数
  stop_on_review_fail: true    # 审查失败是否停止
  checkpoint_frequency: "per_task"  # 每完成一个任务写检查点
  max_consecutive_failures: 3  # 连续失败 3 次停止
  timeout_per_task: 1800       # 单任务超时 30 分钟
  report_interval: 300         # 每 5 分钟报告进度
```

**全自动跑完 Phase 0→5，以下情况自动停止：**

| 安全阀 | 阈值 | 停止后 |
|--------|------|--------|
| 连续失败 | 3 次 | 生成诊断报告，等你处理 |
| 基线退化 | 任何退化 | 立即停止 + 回退建议 |
| 单任务超时 | 30 分钟 | 标记 timeout，跳过继续 |
| git 冲突 | 任何冲突 | 停止，要求手动处理 |

**适合：**
- 需求已经非常明确（完善的 PRD + 量化指标）
- 大批量任务（10+ CR），不想逐个确认
- 夜间运行，早上看报告

**从 Interactive 切换到 Auto Loop：**

```yaml
# 修改 .claude/dev-state/run-config.yaml
mode: "auto-loop"  # 改这一行就行
```

**建议：** 第一轮迭代用 Interactive，熟悉流程后再切 Auto Loop。

---

## 六、需求输入深度对比

### 一句话需求的完整旅程

**你输入的：**
```
"搜索太慢了"
```

**Analyst 的处理过程：**

```
Step 1: 成熟度评估 → 低
  原因：无量化目标、无范围界定、无技术约束

Step 2: 交互确认
  "您的需求: 搜索太慢了
   成熟度评估: 低
   建议补充: 性能指标、影响范围、用户场景
   请选择: A) 直接拆分 / B) 协助完善 / C) 补充信息"
  → 你选 B

Step 3: 逐维度协助完善

  维度 1 — 功能行为:
  "当前搜索响应时间: 经测试 P95=3.2s
   哪些查询慢: 全文搜索 + 向量搜索都慢
   建议目标: P95 < 500ms
   请确认或调整。"

  维度 2 — 用户体验:
  "搜索中是否有加载状态? → 检查代码：无
   建议: 加 loading 指示器 + 超时提示
   请确认。"

  维度 3 — 数据影响:
  "是否需要改索引结构? → 不需要
   是否加缓存表? → 建议内存缓存即可
   跳过此维度。"

  维度 4 — 性能:
  "当前数据量: 约 8 万条
   目标响应时间: P95 < 500ms
   建议方案: LRU 缓存 + 查询优化
   请确认。"

  维度 5 — 安全: "不涉及安全变更，跳过。"
  维度 6 — 集成: "仅修改搜索 API，不影响其他接口。"

Step 4: 输出 requirement-spec.md（10 个章节全部填写）
Step 5: 你审批 → 进入 Phase 2 拆分
```

**最终 Analyst 拆出的 CR（举例）：**

```
CR-001: 添加搜索查询缓存（LRU）
CR-002: 优化 Milvus 查询参数（nprobe 调优）
CR-003: 搜索 API 添加超时控制
CR-004: 前端搜索加 loading 状态
```

一句话需求最终也会变成 4 个精确的 CR，每个都有 design + acceptance_criteria + verify 脚本。

### 粗概要需求的完整旅程

**你输入的：**
```
"优化搜索：加缓存、混合检索权重可配置、搜索结果分页"
```

**Analyst 的处理过程：**

```
Step 1: 成熟度评估 → 中
  原因：有 3 个明确改动点，但缺少量化指标和边界条件

Step 2: 交互确认 → 你选 A（直接拆分）或 B（补充几个维度）

Step 3: 如果选 A，Analyst 自行补全缺失维度:
  - 缓存策略: LRU, maxsize=256, TTL=300s（基于代码分析的专业判断）
  - 分页默认值: page=1, size=20, max_size=100
  - 权重配置格式: config/default.yaml 中新增 search.weights 段
  - 边界条件: page < 1 怎么办? size > max_size 怎么办?

Step 4: 输出 requirement-spec.md
Step 5: 你审批
```

**拆出的 CR：**

```
CR-001: 搜索查询缓存层（cachetools LRU）
CR-002: 混合检索权重配置化
CR-003: 搜索结果分页 API
CR-004: 分页参数校验 + 错误处理
```

### 完善需求文档的完整旅程

**你输入的：** 包含功能规格、性能指标、验收标准的完整 PRD

**Analyst 的处理过程：**

```
Step 1: 成熟度评估 → 高

Step 2: 交互确认 → 建议路径 A
  "您的需求文档已包含功能规格、性能指标（P95<500ms）和 4 条验收标准。
   建议直接进入任务拆分。
   请选择: A) 直接拆分 / B) 协助完善 / C) 补充信息"
  → 你选 A

Step 3: Analyst 直接拆分（仍用八维度检查补全遗漏）:
  补充: "缓存满时 eviction 策略未说明 → 使用 LRU 默认策略"
  补充: "并发查询时缓存的线程安全 → 使用 cachetools 内置锁"
  补充: "权重配置热更新 → 每次请求重新读配置 vs 缓存配置"

Step 4: 输出 requirement-spec.md（大部分直接来自你的 PRD，少量补充）
Step 5: 你审批（快速确认即可）
```

**拆出的 CR 更精确，直接对应 PRD 中的方案描述。**

---

## 七、开发过程中的常用命令

### 查看当前状态

```bash
python dev-framework/scripts/session-manager.py \
    --project-dir "D:/my-project" status
```

输出：迭代、阶段、进度（x/y 完成）、当前任务。

### 写入检查点

```bash
python dev-framework/scripts/session-manager.py \
    --project-dir "D:/my-project" checkpoint
```

通常由 Leader Agent 自动调用。你也可以手动触发。

### 恢复上下文（新 session 或上下文被压缩后）

```bash
python dev-framework/scripts/session-manager.py \
    --project-dir "D:/my-project" resume
```

输出完整恢复摘要（任务状态、检查点、决策、经验、基线），同时写入 `resume-summary.md`。

告诉 Claude：

> 请读取 .claude/dev-state/{iteration-id}/resume-summary.md 恢复上下文，然后继续开发。

### 运行单个 CR 验收

```bash
python dev-framework/scripts/run-verify.py \
    --project-dir "D:/my-project" \
    --iteration-id "iter-1" \
    --task-id "CR-001"
```

### 运行所有验收

```bash
python dev-framework/scripts/run-verify.py \
    --project-dir "D:/my-project" \
    --iteration-id "iter-1" \
    --all
```

### 生成 verify 脚本骨架（Analyst 辅助）

```bash
python dev-framework/scripts/run-verify.py \
    --project-dir "D:/my-project" \
    --iteration-id "iter-1" \
    --generate-skeleton "CR-001"
```

从 CR-001.yaml 的 acceptance_criteria 自动生成验收脚本骨架。Analyst 必须补全业务逻辑。

### 质量门控检查

```bash
# 检查特定门控
python dev-framework/scripts/check-quality-gate.py \
    --project-dir "D:/my-project" \
    --gate gate_4

# 检查所有门控
python dev-framework/scripts/check-quality-gate.py \
    --project-dir "D:/my-project" \
    --all
```

### 任务规模估算

```bash
python dev-framework/scripts/estimate-tasks.py \
    --modules 3 --risk high --complexity moderate --mode iterate
```

输出建议的 CR 数量范围，仅供 Analyst 参考。

### 生成迭代报告

```bash
python dev-framework/scripts/generate-report.py \
    --project-dir "D:/my-project" \
    --iteration-id "iter-1"
```

---

## 八、完整场景走读：从接手到交付

以下是一个接手项目 + 两轮迭代的完整时间线。

### Day 1：接手项目，纳入框架

```bash
# 1. 框架文件注入
python dev-framework/scripts/init-project.py \
    --project-dir "D:/crm-system" \
    --requirement-doc "docs/README.md" \
    --tech-stack "python,django,postgresql,react"

# 2. 填写 CLAUDE.md（花 10 分钟，把项目概况写清楚）

# 3. 记录基线
python dev-framework/scripts/run-baseline.py \
    --project-dir "D:/crm-system" \
    --iteration-id "iteration-0"
# 输出: L1: 238 passed, 3 failed (预存), L2: 15 passed, Lint: 有问题
```

### Day 2：第一轮迭代（bug 修复）

```bash
# 初始化
python dev-framework/scripts/init-iteration.py \
    --project-dir "D:/crm-system" \
    --requirement "客户列表分页不生效，第二页数据和第一页一样" \
    --iteration-id "iter-1"
```

启动 Claude Code，Interactive 模式：

```
Phase 1  Analyst 读代码发现 bug：分页 offset 计算错误
         评估为高成熟度（bug 有复现步骤），走路径 A
         → requirement-spec.md → 你审批 ✓

Phase 2  拆分为 1 个 CR:
         CR-001: 修复分页 offset 计算 (bug_fix)
         → 你审批 ✓

Phase 3  Developer 修复 + L1 测试
         → ready_for_verify

Phase 3.5 Verifier 运行 verify 脚本 → PASS
           → ready_for_review

Phase 4  Reviewer 审查 → PASS

Phase 5  全量测试 ≥ 基线 → 报告 → git push
```

整个过程可能 20-30 分钟。

### Day 5：第二轮迭代（新功能，Auto Loop）

需求已非常明确，切换到 Auto Loop：

```yaml
# 修改 .claude/dev-state/run-config.yaml
mode: "auto-loop"
```

```bash
python dev-framework/scripts/init-iteration.py \
    --project-dir "D:/crm-system" \
    --requirement "$(cat <<'EOF'
## 客户区域筛选功能

### 功能描述
在客户列表页面新增"区域"下拉筛选，支持省、市二级联动。

### 技术方案
- 后端: Django ORM filter，新增 region 字段
- 前端: React Select 组件，两级联动
- 数据: 省市数据存 JSON 配置文件

### 验收标准
- AC1: 选择"广东省"后列表只显示广东客户
- AC2: 选择"广东省-深圳市"后进一步筛选
- AC3: 清空筛选恢复全部数据
- AC4: 无客户的区域显示"暂无数据"
- AC5: 与现有搜索框可组合使用
EOF
)" \
    --iteration-id "iter-2"

python dev-framework/scripts/run-baseline.py \
    --project-dir "D:/crm-system" \
    --iteration-id "iter-2"
```

启动 Claude Code：

```
请按 Auto Loop 模式执行 iter-2 的完整开发流程。
```

Claude 全自动跑完，你事后看报告：

```bash
python dev-framework/scripts/generate-report.py \
    --project-dir "D:/crm-system" \
    --iteration-id "iter-2"
```

```
# 迭代报告: iter-2
CR 总数: 5
通过: 5, 失败: 0
一次通过率: 80% (CR-003 rework 了一次)
L1: 267 passed (+29 new)
```

---

## 九、FAQ

**Q: iteration-id 怎么取名？**
必须符合格式 `iter-N` 或 `iteration-N`（N 为数字），如 `iter-1`、`iter-2`、`iteration-0`。首次开发固定使用 `iteration-0`，后续迭代推荐 `iter-N`。同一项目内不可重复。

**Q: 一轮迭代可以包含多个需求吗？**
可以。`--requirement` 里写多条就行，用分号或换行分隔。Analyst 会拆成多个 CR。

**Q: 迭代做到一半想加需求怎么办？**
告诉 Claude 新增需求，它会调用 Analyst 追加 CR 到当前迭代的 tasks/ 目录。

**Q: 可以跳过 Verifier 直接让 Reviewer 审查吗？**
CR ≤ 3 时，Leader 会兼任 Developer 和 Verifier，流程自动简化。不需要你手动跳。

**Q: run-config.yaml 可以在迭代中途改吗？**
可以。比如做到一半觉得 Interactive 太频繁，改成 Auto Loop 继续。

**Q: 怎么看所有可用的脚本和参数？**
每个脚本都支持 `--help`：
```bash
python dev-framework/scripts/init-project.py --help
python dev-framework/scripts/check-quality-gate.py --help
```
