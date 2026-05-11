# Goal Launch Notes

最後更新：`2026-05-04`

這個資料夾放 Codex Goal / 長時間 runner 相關 artifact。

## Goal 1

主要 runbook：

```text
artifacts/goal/goal-1-product-autopilot.md
```

## WSL 啟動方式

在 WSL terminal 執行：

```bash
cd /mnt/d/workspace_v2/projects/lab/XBrainLab

/mnt/c/Users/Administrator/.codex/bin/wsl/codex \
  -C /mnt/d/workspace_v2/projects/lab/XBrainLab \
  --model gpt-5.5 \
  --dangerously-bypass-approvals-and-sandbox \
  --no-alt-screen \
  "先不要改檔。請讀取 artifacts/goal/goal-1-product-autopilot.md，回覆 READY TO SET GOAL。"
```

等 Codex 回覆後，在同一個 TUI 裡輸入：

```text
/goal Execute artifacts/goal/goal-1-product-autopilot.md end-to-end as the authoritative product goal. Continue autonomously until the Done Definition and validation gates are met; commit each validated slice locally; do not push.
```

接著輸入：

```text
開始執行。讀取 artifacts/goal/goal-1-product-autopilot.md，依它長跑到完成；如果未達工程級交付，繼續工作，不要提前交還。
```

## 常見問題

- 只打 `/goal` 不夠；目前 CLI 用法是 `/goal <objective>`。
- 若 session 尚未開始，Goal 可能無法設定。先用上面的初始 prompt 讓 session 開始，再輸入
  `/goal ...`。
- 若 `codex` command not found，使用完整路徑
  `/mnt/c/Users/Administrator/.codex/bin/wsl/codex`。
- 若看不到 Goal，先確認：

```bash
/mnt/c/Users/Administrator/.codex/bin/wsl/codex features list | grep goals
```

應顯示 `goals under development true`。

## Reviewer 要看什麼

Goal runner 回來後，不要只看它自稱完成。先檢查：

- 本地 commits。
- `docs/records/worklog.md` 和 `docs/records/implementation_log.md`。
- validation commands 與輸出。
- non-mocked workflow evidence。
- UI-observable replay artifact。
- 是否仍有 UI / agent / headless / MCP 任一入口繞過 ApplicationService。
