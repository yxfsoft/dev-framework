# Init-Mode 工作流（首次开发）

> 适用于：从零开始的新项目开发
> 输入：需求文档 + 技术栈选择
> 输出：完整项目代码

---

## 概述

首次开发等同于 iteration-0。与 iterate-mode 的区别：
- 无基线测试（基线为空）
- 任务类型全部为 new_feature
- 需要先建立项目骨架和基础设施

---

## Phase 0: 项目初始化

### Step 0.1: 创建项目结构

运行 `scripts/init-project.py`，生成：

```
{project}/
├── .claude/
│   ├── agents/              # 从框架复制的 Agent 定义
│   │   ├── analyst.md
│   │   ├── developer.md
│   │   ├── reviewer.md
│   │   └── leader.md
│   ├── dev-state/           # 开发状态目录
│   │   ├── session-state.json
│   │   ├── baseline.json    # 空基线
│   │   ├── experience-log.md
│   │   ├── run-config.yaml
│   │   └── iteration-0/
│   │       ├── manifest.json
│   │       ├── requirement-raw.md  # 指向需求文档
│   │       ├── tasks/
│   │       ├── verify/
│   │       ├── checkpoints/
│   │       └── decisions.md
│   └── CLAUDE.md            # 项目宪法（从模板生成）
├── ARCHITECTURE.md
├── docs/
│   └── {requirement-doc}    # 用户提供的需求文档
├── config/
│   └── default.yaml
├── scripts/
│   └── verify/
└── tests/
```

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

init-mode 特有步骤：生成 `feature-checklist.json`

```json
{
  "project": "{project-name}",
  "mode": "init",
  "features": [
    {
      "id": "F001",
      "name": "完整数据链路: 截屏采集→同步→OCR→入库→搜索",
      "status": "FAIL",
      "priority": "critical",
      "slice": "screenshot",
      "criteria": [
        {"id": "F001-C1", "desc": "截屏文件生成", "status": "FAIL"},
        {"id": "F001-C2", "desc": "sidecar JSON 正确", "status": "FAIL"},
        {"id": "F001-C3", "desc": "同步到服务端", "status": "FAIL"},
        {"id": "F001-C4", "desc": "OCR 提取文字", "status": "FAIL"},
        {"id": "F001-C5", "desc": "向量入库", "status": "FAIL"},
        {"id": "F001-C6", "desc": "搜索 API 可找到", "status": "FAIL"}
      ]
    }
  ]
}
```

所有 Feature 初始为 FAIL。Agent 逐个攻克。

### Step 1.4: 输出需求规格书

写入 `iteration-0/requirement-spec.md`，等待用户审批。

---

## Phase 2: 架构设计 + 任务拆分

### Step 2.1: 基础设施层拆分

优先拆分 Phase 0 的基础设施任务：

```
基础设施 CR（必须先完成）:
  INF-001: 数据库 schema + ORM/迁移
  INF-002: 配置加载框架
  INF-003: API 骨架 + 认证
  INF-004: 客户端 SDK 框架
  INF-005: 向量数据库 Collection（如适用）
  INF-006: 环境验证脚本
```

### Step 2.2: 垂直切片拆分

按照特性清单中的切片，每个切片拆分为多个 CR：

```
切片 "screenshot" 的 CR 序列:
  CR-001: 单屏截屏 + 1080p 缩放
  CR-002: WebP 压缩 + sidecar JSON
  CR-003: 自适应截屏频率
  CR-004: 窗口元数据提取
  CR-005: 帧间去重 (pHash)
  CR-006: 多显示器支持
  CR-007: 集成到采集主程序
  CR-008: Syncthing 同步配置
  CR-009: Pipeline OCR 处理
  CR-010: 向量化入库
  CR-011: 搜索 API 验证
  CR-012: 切片端到端验证
```

每个 CR 带完整的 design + acceptance_criteria + verify 脚本。

### Step 2.3: 依赖关系

```
INF-001~006 → 无依赖，可并行
CR-001~006 → 依赖 INF 完成
CR-007 → 依赖 CR-001~006
CR-008 → 依赖 CR-007
CR-009~010 → 依赖 INF + CR-008
CR-011 → 依赖 CR-010
CR-012 → 依赖全部
```

### Step 2.4: 用户审批

展示完整的任务列表和依赖关系图，等待用户确认。

---

## Phase 3: 开发执行

### 基础设施批次

```
Batch 0: INF-001 ~ INF-006（可并行，最多 3 Agent）
  → 完成后运行基础设施验证脚本
  → 基础设施冻结
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

## Phase 4-5: 审查与交付

与 iterate-mode 相同，参见 `iterate-mode.md`。

---

## Init-Mode 特有规则

1. **基础设施冻结**：Phase 0 完成后，基础设施代码只能扩展不能修改
2. **Feature Checklist 为主导**：任务状态追踪以 feature-checklist.json 为准
3. **切片顺序**：按优先级执行，高优先级切片先做
4. **跨切片依赖**：如果切片 B 需要切片 A 的基础设施，切片 A 必须先完成
5. **渐进交付**：每完成一个切片就是一个可运行的增量
