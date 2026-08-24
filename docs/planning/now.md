# XBrainLab Now

最後更新：`2026-08-24`

## 目前焦點

完成 PR #50 的 **Agent 改版與新增 Granite 3B 模型** 最終整合。使用者已在 WSLg 手測原候選
`13088c41762bfc3902ca9c6ed2ade9ca2004e75c`，接受中文輸入為本輪已知限制並同意 merge；但之後
`main` 經 PR #48／#51 推進至 `v0.8.0` merge commit
`f1fd85333d3b297a28651a01c2464a886647002f`，因此舊 exact-SHA acceptance 已失效。

## Outcome 與 evidence

- Granite 4.0 Micro 3B 是 recommended primary，Granite 3.3 2B 是 lower-memory 選項。
- 支援的最後模型選擇持久化；已退役 model setting 靜默正規化為 3B，不恢復 blocking first-run modal。
- 保留 inline setup、Space/New Chat guard、compact bubble、typed multi-turn clarification infrastructure、
  18-action command spine，以及 `v0.8.0` 已驗收的 GUI／Saliency 行為。
- 凍結模型基準為 36/36 positive、10/10 explicit parameter origin、5/5 missing guard、20/24 no-action、
  0/7 production-controller clarification；這是 bounded improved baseline，不是 Stable promotion。

## Scope、non-goals 與 UI 確認

- Scope：將固定 `main` `f1fd8533` 整合進既有 Assistant 候選，只處理直接衝突、owner 語意、回歸測試、
  canonical truth 與 exact-source evidence。
- Non-goals：不修中文 IME、不再調 prompt／tool contract、不改 import、不新增模型、owner、state machine、
  compatibility path 或可見設計。
- 舊 first-run modal 在 Assistant 候選已退役且沒有 production caller；modify/delete 衝突維持刪除，
  不把阻塞流程帶回產品。
- Owners before／after不變：AgentManager／AssistantRuntimeLifecycle擁有 UI admission 與 runtime lifecycle，
  LLMController協調 turn，ToolAttemptCoordinator擁有 tool admission，PendingInteractionCoordinator保存必要
  cross-turn receipt，ApplicationService仍是 authoritative command spine。
- 使用者已批准原 Agent/UI scope；本次不引入新的可見行為。因 source SHA 改變，仍必須重新交付 WSLg
  手測並取得 merge 同意。

## 施工與 focused validation

1. 保留 `v0.8.0` current truth與共用 modal migration，保留 Assistant 對舊 first-run modal 的刪除。
2. 審查自動合併的 Assistant bubble、Settings 與直接 tests，先跑 conflict-adjacent focused suites。
3. 在 clean exact commit 執行 applicable handoff manifest／UI artifact／Granite report並推送 PR #50。
4. 等待所有 non-skipped PR checks `completed/success`，再交付同一 SHA 給使用者做精簡 WSLg 回歸。
5. 只有使用者回報新 SHA 通過並再次明確同意，才經 PR merge commit 合入 `main`。

## Stop conditions

- 任一衝突需要新的產品取捨、owner、public contract 或可見行為；
- Granite denominator低於凍結 baseline，或 Settings／Space／bubble／multi-turn action出現回歸；
- exact source、artifact、PR head/base不一致；
- 任一 applicable check missing、pending、cancelled、failed，或使用者尚未重新批准。

任一條件成立即停止，不 merge。
