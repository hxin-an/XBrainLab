# XBrainLab Now

最後更新：`2026-08-26`

## 目前焦點

Data Import blocking performance slice 停在 checkpoint；目前沒有 active product implementation
slice。

### Checkpoint evidence

- 在 WSL `/mnt/d` 的 OpenNeuro ds003061 `sub-001` 三個 run（約 190 MB），以一次 warm-up
  後三次 fresh `ApplicationService` passes（catalog → review → apply → background idle）測量。
- 最終 net `-5` one-shot candidate 的三次 correctness 均通過。blocking 分別為
  `12.006010s`、`12.046162s`、`12.088023s`，median 是 `12.046162s`；background 分別為
  `1.530436s`、`1.512019s`、`1.543808s`，median 是 `1.530436s`；stable-idle median 是
  `13.558181s`。10 秒 blocking gate 未通過。
- 保留 one-shot discovery/apply session transfer：production delta 為 net `-5` LOC，且
  detached、stale、rollback characterization 均通過。歷史 `54927d07` attribution（仍含後來
  撤回的 admitted-path experiment）曾測得 blocking median `11.444679s`、background median
  `1.543740s`；這不是最終 candidate 的成績。
- Primary reviewed-label path 為 `+45` production LOC，current median `11.652121s`，沒有可證明
  收益，已撤回。
- admitted-path threading 為 `+103` production LOC，僅約 `0.57s` 改善，複雜度／收益比不成立，
  已撤回。

### Stop condition

- 保留 opt-in profile 的 blocking/background/stable-idle contract，作為後續候選改善的可重現
  基線；不宣稱 handoff-ready。
- 不為追求 10 秒 gate 擴張至 raw staging、background redesign 或 security boundary weakening。
- 下一個 import candidate 必須先由新的 active plan、同一 workload 的 bottleneck evidence 與
  focused safety characterization 支持。
- 本 checkpoint 不修改 UI；root `settings.json` 是使用者本機設定，不納入此 slice。
