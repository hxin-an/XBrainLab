# XBrainLab Now

最後更新：`2026-08-16`

## 目前焦點

**先收斂 CI change-scope：純 agent-guidance 變更不可再觸發完整產品矩陣；完成並合併後，才進入
Assistant runtime 量測，確認 real Granite、chat lifecycle 與 backend command spine 的實際失敗。**

UI visual-regression guard 已由 PR #24 合入 `main`。Quota-aware Codex dispatch 已收斂到
`.agents/README.md` 與 project `.codex/config.toml`：Terra 是 coordinator/default，Luna 只處理有
exact oracle 的 bounded worker，Sol 只處理客觀 high-risk decision；它不再是 product active work。

## CI change-scope repair

- PR #25 只有 agent-guidance、其 static audit 與 focused test，卻因 CI 將全部 `scripts/*`、`tests/*`
  視為 product path，而跑了 Linux shards、跨平台與 public multi-dataset gate。
- 修理範圍只新增窄的 `agent_guidance` scope：`AGENTS.md`、`.agents/**`、project `.codex/config.toml`、
  guidance audit 與它的兩個 exact tests 可走 focused audit/test/lint lane；一般 script、test、產品、依賴、
  workflow 或未知 path 均 fail closed 為完整 product CI。
- classifier 必須是可單元測試的純 helper；混合 scope、空 diff、首次 push 與未知 path 不可降級。
- 此為 CI/docs/test-only repair，不改產品或 UI；exact-head CI 成功後可直接 merge，無需 manual acceptance。

## Assistant runtime evidence

- 使用者目前不能可靠使用 Assistant；已知 claim 不能由 mock tool-call eval 或舊 artifact 支撐。
- Assistant 必須和 UI 共用 `ApplicationService / Command API` 的 state、capability 與 error semantics，
  不能建立第二套 readiness truth。
- `assistant/runtime-measurement-v1` 的唯讀 host probe 已確認：protected `settings.json` 仍選擇已退役的
  `microsoft/Phi-4-mini-instruct`，local policy 在 model load 前正確阻擋它；不改設定地指定
  `ibm-granite/granite-3.3-2b-instruct` 時，runtime package 齊全但 local cache 缺失。這是目前
  Assistant 不可用的第一個直接 blocker，尚未到可判定 chat lifecycle 或 tool dispatch 的階段。
- Granite 預估下載 5.08 GB、VRAM 約 6 GB，仍在既定 10 GB 單模型 / 20 GB cache boundary 內；但不得
  silent migration、覆寫使用者設定或未經同意下載。使用者選擇/安裝後，才可做有 timeout 的 prompt、
  structured-envelope、ChatPanel lifecycle 與 cancel/retry 量測。

## 下一步

1. 從最新 `main` 建立一條 CI task branch，以 red-first classifier truth table 實作並驗證 agent-guidance lane；
   exact-head CI 成功後直接 merge。
2. 接著從更新後的 `main` 建立 Assistant task branch，先確認 repo/Git/runtime identity 與 real Granite health。
3. 取得使用者對 Granite local selection / 約 5.08 GB download 的明確同意，或由使用者先在 Settings 完成
   安裝；不得自動替換已退役模型。
4. 唯讀重現 chat startup、unavailable/error、tool selection、confirmation、retry/cancel 與長 session；
   保存最小可重跑 evidence，不先改 UI。
5. 將第一個 confirmed root cause、observable outcome、scope/non-goals、修理步驟與 focused validation
   寫回本文件，再開始實作。
6. 若修復需要任何 `XBrainLab/ui/` 或使用者可見互動變更，先取得使用者明確確認。

## Non-goals

- 不把 tool-call eval、thesis evidence、MCP、packaging 或任意 dataset support 拉進第一個 Assistant slice。
- 不因 agent 不可用就替換 product model、加入 silent fallback、建立第二套 state owner 或重寫整個 panel。
- 不修改 `v0.6.0` tag/release、既有 UI layout、EEG pipeline、training outputs 或 repo-root
  `settings.json`。
- 不以 deterministic mock、dashboard PASS 或 Linux offscreen 冒充 real Granite／Windows product evidence。

## Entry condition

- Quota-aware guidance PR exact-head checks 成功並合入 `main`。
- 新 Assistant branch 的 initial state 只有允許保留的 `settings.json` dirty path。
- 第一輪只讀量測有明確 timeout、資源上限與單一 PID/session ownership。

長期目標讀 [Roadmap](roadmap.md)，evidence contract 只讀 [Validation](../validation/README.md)。
