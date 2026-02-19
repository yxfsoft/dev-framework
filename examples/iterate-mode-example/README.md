# Iterate-Mode 示例

此目录展示了一个完整的 iterate-mode 迭代示例结构。

## 文件说明

```
iterate-mode-example/
├── manifest.json          # 迭代元信息
├── tasks/
│   └── CR-001.yaml        # 完整的任务文件示例（bug_fix 类型）
├── verify/
│   └── CR-001.py          # 对应的验收脚本示例
└── README.md              # 本文件
```

## 任务文件要点

- `id`: 任务唯一标识，格式 `CR-xxx` / `INF-xxx` / `F-xxx`
- `type`: 任务类型（bug_fix / enhancement / new_feature / refactor / infrastructure）
- `design`: 必须包含 `approach` 和 `why_this_approach`
- `acceptance_criteria`: 每条标准初始 `status: FAIL`，验收通过后改为 `PASS`
- `done_evidence`: 由 Verifier Agent 填写，Developer 不可修改
- `review_result`: 由 Reviewer Agent 填写

## 状态流转

```
pending → in_progress → ready_for_verify → ready_for_review → PASS
```

## 验收脚本要点

- 零 Mock，使用真实环境验证
- 由 Analyst 生成，Developer 和 Verifier 不可修改
- 每条 acceptance_criteria 对应一个 verify 函数
- 运行结束输出 EVIDENCE_JSON 供 Verifier 收集证据
