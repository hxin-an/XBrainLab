# XBrainLab Now

最後更新：2026-08-17

## 目前焦點

**在 `test/assistant-21-action-smoke-v1` 收斂 Agent deterministic showcase，使其精確覆蓋 21 個
model-facing actions，但本 branch 只修改 dev diagnostic、tests 與 docs，先合回 `main`。**

使用者於 2026-08-17 要求先整理並合併目前不需要手測的部分，再另開 branch 實作 no-LLM frontend
walkthrough。Repo-root `settings.json` 是使用者本機 runtime 設定，不屬於本 slice。

## 問題與證據

- 現有 showcase 擴充到 24 cases／21 actions，但為了讓 `set_montage` diagnostic 通過，worktree
  同時改了 production intent 與 action registry；這會讓本來可免手測的 dev-only slice 變成產品行為
  變更。
- Showcase 應能由 canonical action contract 產生 host-selected diagnostic authorization，不需要替
  production prompt inference 新增 montage policy。
- 現有 deterministic runner 可驗證 command spine、typed UI request、confirmation、blocked、stale
  與 retry terminal；它不開 Qt、不載入 local model，也不證明真人前端流程或 raw model accuracy。

## Observable outcome

- 24-case showcase exact 覆蓋 canonical 21 model-facing actions，產生 schema v3 artifact，並對 recipe、
  state transition、confirmation、typed UI request 與 terminal semantics fail closed。
- `set_montage` 與 `switch_panel` 由 dev runner 的明確 scripted selection 驗證既有 boundary；production
  intent、registry、UI 與 runtime 行為完全不變。
- PR diff 只包含 `scripts/dev/`、`tests/`、`docs/`；`settings.json` 保持 unstaged。因不可能改變產品
  行為，本 slice 依 validation contract 不要求 manual acceptance。

## Scope、ordered repair 與 non-goals

1. 先保留 current focused baseline，再移除 `action_contracts.py`、`intent.py` 與其 product intent test
   的未提交變更。
2. 讓 dev runner 對 canonical direct action 建立 exact host-selected authorization；artifact 與 README
   清楚限制 claim，不把 scripted selection 說成模型判斷。
3. 跑 showcase focused tests、相關 intent/action contracts regression、Ruff、format-check、targeted
   Basedpyright 與 MkDocs strict；只在同一 source 綠燈後 commit、push、建立 PR。
4. PR 的 non-skipped checks 全部 completed/success 後以 merge commit 合併並同步本機 `main`。

Non-goals：不修改 `XBrainLab/ui/`、不新增 frontend walkthrough、不修 normal `switch_panel` async
completion、不啟動 Granite、不做真人 training，也不建立第二套 capability／state／confirmation owner。

## Stop conditions

- 若最終 diff 仍含任何 production file、runner 繞過 canonical tool/command mapping，或 21-action exact
  coverage／typed terminal corruption test失效，不得合併。
- 若 focused validation 或 PR non-skipped check不是 completed/success，停在 checkpoint，不宣稱完成。
- Phase B 的可見 UI change 必須在新 branch 實作，完成 screenshot／walkthrough 並取得使用者手測批准
  後才可合併。

## Implementation checkpoint

- 已移除 worktree 中 `action_contracts.py`、`intent.py` 與 product intent test 的 montage policy變更；
  current diff 除使用者本機 `settings.json` 外只剩 docs、dev script與test。
- Characterization baseline為15 passed；移除product montage intent後exact 21-action matrix如預期紅在
  23/24。Dev runner改為只對缺少production admission的typed UI direct action建立host-selected
  authorization後，focused intent/showcase回到147 passed。
- Test-quality mutation確認：過度泛化host-selection會讓path provenance的3 cases失敗；typed handoff
  parameter corruption與21-action catalog drift也會被現有test攔截。這些證據仍不支撐Qt或Granite claim。
- Final focused rerun為147 passed；Ruff check／format-check、targeted Basedpyright（0 errors）、
  MkDocs strict與git diff check均通過。尚待commit、push、PR checks與merge。
