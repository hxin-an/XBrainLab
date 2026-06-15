# Handoff Candidate Workflow

最後更新：`2026-06-15`

這份 workflow 用於任何準備交給使用者手測的修復、功能或整合 branch。

目標不是消滅所有人工驗收，而是避免使用者成為第一層 QA。agent 必須先用自動化、
artifact 和同類掃描抓掉明顯 bug，再請使用者做 acceptance。

## 0. Classification

先分類本輪交付：

- `checkpoint`：局部修復已驗證，但尚未跑完整 handoff gate。
- `handoff-ready`：可交給使用者手測；已完成本 workflow 的必要 gate。
- `blocked`：需要使用者決策、外部環境或無法自動取得的 evidence。

未完成必要 gate 時，不可把 checkpoint 說成 handoff-ready。

## 1. Start Gate

開始前必須記錄：

- current branch。
- `git status --short --branch`。
- intended scope。
- intentionally not touched。
- dirty files 是否屬於本輪；不屬於本輪則保留且不可覆蓋。

若工作會觸及 UI / backend / tests / docs 多個區域，先確認這些改動是否必須同 branch。
否則拆成 reviewable slices。

## 2. Focused Bug Protection

對使用者指出的 bug，先建立至少一種保護：

- red/failing test，若可自動化。
- failing script / walkthrough artifact，若是 UI 或 runtime 問題。
- explicit reproduction note，若只能人工重現。

修復後要跑同一條 protection，證明它轉綠或 artifact 已改善。

## 3. Same-Class Sweep

不能只修第一個 symptom。依問題類型做同類掃描：

- UI layout：檢查同類 dialog / panel / table / screenshot artifact。
- UI refresh / state truth：搜尋同類 manual refresh、observer callback、duplicated readiness。
- backend command path：搜尋 direct controller / Study mutation、capability bypass、legacy fallback。
- data import / label：檢查 auto-discovered / user-added / removed / reloaded label source。
- visualization / evaluation：檢查 fold、label mapping、empty state、figure lifecycle。
- performance：檢查 UI-thread blocking、eager loading、background worker cleanup。

若 sweep 發現同類 blocker，必須修完或回報 blocked；不能交給使用者去找下一個。

## 4. Happy Path Gate

每個 handoff candidate 至少跑一條代表性 happy path：

- UI 可見改動：跑 relevant UI walkthrough / screenshot script。
- data/import/label 相關：跑 Data Import wizard 或 replay artifact。
- training/evaluation/visualization 相關：跑 tiny pipeline 或 visualization render walkthrough。
- agent/MCP 相關：跑 agent tool / MCP adapter focused tests 或 walkthrough artifact。
- docs-only：跑 docs gate 即可，不宣稱產品 handoff。

happy path 要保存或引用 artifact / command output，不能只說「看起來可以」。

## 5. Edge / Regression Gate

再跑與本輪風險相符的 edge gate：

- data/import/label/epoch/training/evaluation/visualization handoff：
  required multi-dataset gate；Data Import wizard 另跑
  `tests/integration/ui/test_data_import_wizard_format_matrix.py`，確認代表格式都能打開五步
  wizard。
- backend command / ApplicationService：
  focused command tests + architecture/source guard。
- UI layout / visible UX：
  screenshot artifact + UI unit/integration tests。
- async / performance / resource：
  lifecycle tests、stale callback tests、figure/thread cleanup tests。
- docs-only：
  `git diff --check` 和 `poetry run mkdocs build --strict`。

如果 gate 太慢，可先回報 checkpoint；不能省略 gate 後仍說 handoff-ready。

## 6. Reviewer / Subagent Gate

subagents 可作為 gate reviewer，但不能替主 agent 判定完成。

常用 reviewer：

- UI / UX：檢查 screenshot、layout、visible language、primary action。
- Backend / architecture：檢查 command spine、state truth、legacy fallback。
- Test quality：檢查新增測試是否能抓真 bug，不只是 mock-heavy。
- EEG / data interpretation：檢查資料格式、label/event、BIDS-like boundary。
- Performance/resource：檢查 UI 卡頓、thread、figure、GPU/VRAM、lazy loading。

主 agent 必須讀 reviewer findings、決定修或明確標成非阻塞。核心需求相關 finding 不能標成
非阻塞後交給使用者手測。

## 7. Final Handoff Report

handoff-ready 回報必須包含：

- branch name and commit hash。
- pushed status。
- scope and non-goals。
- focused regression result。
- same-class sweep result。
- happy path command / artifact。
- edge/regression command / artifact。
- reviewer/subagent gate verdict，若有使用。
- remaining risks and claim boundaries。
- explicit statement: `handoff-ready` 或 `checkpoint` 或 `blocked`。

如果沒有 commit / push，或 worktree 有未解釋 dirty files，不可說 handoff-ready。
