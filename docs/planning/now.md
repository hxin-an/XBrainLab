# XBrainLab Now

最後更新：`2026-08-16`

## 目前焦點

**建立 quota-aware Codex model dispatch，讓 Terra 擔任預設 coordinator，只有符合明確條件的
bounded worker 使用 Luna，只有客觀高風險決策使用 Sol。**

本輪從 `main@30dabdb2` 建立短 guidance branch。前一個 UI visual-regression slice 已由 PR #24
合入 `main`，不再是 active candidate。本輪只修改 repo-local Codex config、agent operations、
guidance audit/tests 與這份 current plan；不修改產品 runtime、UI 或 `settings.json`。

## 問題與證據

- 現行 model dispatch 只有 Terra/Sol，沒有低成本 Luna lane，也把「複雜但 bounded」直接導向 Sol。
- Project 尚無 `.codex/config.toml`，新 thread 與未明確指定的 worker 沒有 repo-local Terra fallback。
- Fast mode 若變成 project default 會放大所有 turn 的額度消耗；它只適合使用者正在等待、且模型生成
  是主要 latency 的 foreground task。
- 舊外部 guidance A/B surface 已退役；本輪不能以新的大量 paid eval 或 routing control plane 取代它。

## Observable outcome

1. Trusted XBrainLab project 的新 Codex thread 與 unspecified subagent 預設為 Terra/medium。
2. `.agents/README.md` 成為 Luna/Terra/Sol、Fast 與一次嘗試後升級規則的唯一 dispatch authority。
3. Plan 對非 trivial change/build 產生一筆短 dispatch record；小任務不為了便宜而額外複製 context。
4. Static audit 能拒絕缺少 model lane、錯誤 project default 或全域 persisted Fast 的變更。

## Scope / non-goals

- In scope：`.codex/config.toml`、model-dispatch guidance、static audit、focused contract tests。
- 不新增 custom agent profiles、model router、telemetry、paid A/B、第二份 planning 文件或 runtime receipt。
- 不改 `AGENTS.md` 的 repo invariants，不動產品、UI、Assistant、EEG pipeline、CI workflow 或 release。
- 不宣稱 repo guidance 能替已啟動的 host thread 自動換模型或自動切換 Fast tier。

## 修理步驟

1. 新增最小 project config：main 與 unspecified subagent fallback 為 Terra/medium，不 persist Fast。
2. 將 model dispatch 收斂成 Luna eligibility、Terra default、Sol hard triggers、non-triggers 與 escalation。
3. 擴充 guidance audit 與 unit contract，驗證 config、三個 model lane 和 cost-control boundary。
4. 跑 config-load smoke、focused tests、guidance audit、MkDocs strict 與 diff hygiene。
5. 完成後把 active priority 推進回 Assistant；本次 routing policy 留在 `.agents/README.md`。

## Focused validation / stop condition

- `python3 scripts/dev/audit_agent_guidance.py check --format json`
- `poetry run pytest --capture=sys tests/unit/test_agent_guidance_contract.py -q`
- 無 model turn 的 Codex config-load smoke、`poetry run mkdocs build --strict`、`git diff --check`
- Stop：同一 exact commit 上述檢查成功、`settings.json` 未 stage，且 diff 沒有產品或 UI 檔案。

## 後續順序

1. 完成本輪 model dispatch guidance。
2. 從最新 `main` 建立 Assistant task branch，先量測 real Granite 的 tool selection、confirmation、
   retry/cancel 與長 session，再決定最小修復。

長期目標讀 [Roadmap](roadmap.md)，evidence contract 只讀 [Validation](../validation/README.md)。
