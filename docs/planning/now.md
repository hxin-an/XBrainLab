# XBrainLab Now

最後更新：`2026-08-16`

## 目前焦點

**從已驗證的 Desktop GUI baseline 進入 Assistant runtime 量測，先確認 real Granite、chat lifecycle
與 backend command spine 的實際失敗，再制定一個 bounded repair slice。**

UI visual-regression guard 已由 PR #24 合入 `main`。Quota-aware Codex dispatch 已收斂到
`.agents/README.md` 與 project `.codex/config.toml`：Terra 是 coordinator/default，Luna 只處理有
exact oracle 的 bounded worker，Sol 只處理客觀 high-risk decision；它不再是 product active work。

## 問題與證據

- 使用者目前不能可靠使用 Assistant；已知 claim 不能由 mock tool-call eval 或舊 artifact 支撐。
- Assistant 必須和 UI 共用 `ApplicationService / Command API` 的 state、capability 與 error semantics，
  不能建立第二套 readiness truth。
- 下一個 repair scope 尚不能在沒有 real runtime evidence 前決定；先量測不是授權廣泛重寫。

## 下一步

1. 從最新 `main` 建立一條 Assistant task branch，先確認 repo/Git/runtime identity 與 real Granite health。
2. 唯讀重現 chat startup、unavailable/error、tool selection、confirmation、retry/cancel 與長 session；
   保存最小可重跑 evidence，不先改 UI。
3. 將第一個 confirmed root cause、observable outcome、scope/non-goals、修理步驟與 focused validation
   寫回本文件，再開始實作。
4. 若修復需要任何 `XBrainLab/ui/` 或使用者可見互動變更，先取得使用者明確確認。

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
