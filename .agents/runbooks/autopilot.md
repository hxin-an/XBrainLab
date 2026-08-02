# XBrainLab Autopilot

最後更新：`2026-07-31`

這份文件描述 agent 長時間工作時的 product-quality closure 循環。舊的 task queue 和
automation control surface 已退役。

## 唯一入口

Autopilot 每輪只能從以下文件 dispatch：

1. `docs/planning/now.md`：施工順序和 exit condition。
2. `docs/agent_goals/product_quality_closure_goal.md`：completion contract 和 product decisions。
3. `docs/records/product_quality_audit_2026-07-30.md`：finding status 和 required closure。

`docs/current.md`、architecture、records、worklog 和 artifacts 是 context/evidence，不是 queue。
不得從 roadmap、historical goal、feedback record 或舊 dashboard 自行恢復工作項目。

## 核心規則

持續推進，並以文件保存狀態。milestone 是最低交付門檻，不是工作上限。

Autopilot 不能把「worker 說已完成」當成完成。主 agent 必須像 reviewer / engineering manager 一樣驗收：

1. 先判斷本輪核心需求是否真的被解掉，而不是只修到局部症狀。
2. 讀取 worker diff 和 touched files，確認沒有繞過目標架構或新增第二套 truth。
3. 對 UI 工作看 screenshot / artifact；對 backend 工作跑 low-mock workflow 和 integration tests；對 agent 工作檢查 visible transcript 與 structured payload。
4. 若仍有明顯產品缺陷、架構旁路、未驗證流程或文件失真，打回繼續做。
5. 最終回報只能建立在主 agent 親自驗證過的 evidence 上。

## 工作循環

每輪工作：

1. 用 `.agents/runbooks/setup.md` 核對 worktree、branch、dirty ownership。
2. 從唯一入口選一個 audit slice，先確認 finding、scope、claim boundary 和 owner。
3. 對 source、runtime、tests 和 artifact 做同類掃描；先建立 focused regression。
4. 完成最小但完整的修復，不新增 compatibility success path 或第二套 workflow truth。
5. 依 `docs/validation/README.md` 的 manifest 跑 focused、adjacent 和必要 handoff gates。
6. 主 agent 讀 diff、看 artifacts、核對 command output；worker verdict 只作輸入。
7. 把 finding evidence 回寫 audit；只有 current truth 改變時才更新 canonical docs。
8. 未完成 exact-commit gates 時一律回報 `checkpoint`，不提前排 Windows acceptance。

## 可做

- 清理 `.agents/` 舊引用。
- 清理 canonical 文件的舊路徑與過期說法。
- 把短期舊文件的有效內容整合到 canonical 文件，然後刪除原舊文件。
- 依 canonical validation manifest 執行 dashboard、workflow、artifact 和 docs gates。
- 對架構文件做 source-code 對照。
- 使用新的 repo-local skills / workflows 推進 product delivery、驗證或文件校準。
- 推進 backend command adapter、UI chat、agent tool alignment、local LLM runtime、desktop launcher。

## 邊界

- 不恢復舊 `xbrainlab-*` repo-local skills。
- 不建立 `active-queue.md`、AQ、Prep Gate、Repair Loop 或等價第二份 dispatch board。
- 不新增新多角色 automation。
- 不把 UI / agent 各自接成第二套 backend workflow。
- 不以 compatibility-only path、mock-heavy test 或單一 dashboard PASS 作 product success evidence。
- 不在 stronger replacement coverage 存在前刪除弱測試或 compatibility test。
- 不在產品主線未穩定前提前做 tool-call eval。
- 不下載超過容量邊界的大模型。

## 完成定義

一輪 autopilot 工作完成時，至少要有：

- 清楚的修改範圍。
- 一個可檢查的驗證結果，或明確寫出沒跑的原因。
- 主 agent 自己做過驗收，而不是只引用 worker 回報。
- audit ledger 有 finding status、evidence 和 claim boundary；需要時再補 implementation log。
- 沒有把 legacy 文件重新升格成 current truth。
- 若改變產品能力或架構，已更新 implementation log 和相關 architecture / validation / planning 文件。
