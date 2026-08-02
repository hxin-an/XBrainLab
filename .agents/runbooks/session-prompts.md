# XBrainLab Session Prompts

最後更新：`2026-07-31`

這裡只保留短 prompt，避免舊路徑、舊 queue 或 superseded goal 污染 active dispatch。

## 一般工作開場

```text
先執行 git rev-parse --show-toplevel、git branch --show-current、git worktree list --porcelain
和 git status --short --branch。將實際 root/branch 與 docs/current.md、docs/planning/now.md 的
active integration context 核對；不一致就停止，不要自行切換或沿用 prompt 內的舊路徑。
再讀 AGENTS.md、docs/planning/now.md、docs/agent_goals/product_quality_closure_goal.md、
docs/records/product_quality_audit_2026-07-30.md 和 docs/validation/README.md。
只從 planning/now + active goal + active audit dispatch；其他 goal、queue、feedback、worklog
和 artifacts 都不是 active task authority。
```

## 文件整理

```text
整理文件時，先判斷內容是 current truth、target、active plan、decision、validation boundary、
checkpoint/historical record 還是 deleted-after-integration。
優先更新既有 docs/* 文件，不新增大型 planning 文件。
records 和 artifacts 不得使用 current-looking status board 語意。
```

## 驗證工作

```text
驗證前先說明要驗證哪個 claim。
只使用 docs/validation/README.md 的 Handoff Command Manifest；不要從 runbook、skill 或舊
goal 複製較弱命令。驗證後記錄 command、source identity、結果、支持/不支持的 claim。
任何 required gate 未完成時只能回報 checkpoint 或 blocked。
```
