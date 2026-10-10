# XBrainLab Now

最後更新：`2026-10-10`

## Active — 修復 Restart 舊 snapshot 接收競態，再補測後合併

PR #160 的產品版本 `edfa1ac8` 已完成 Windows 手測；使用者明確回報無問題並批准 merge。
文件收尾 head `02c23bdf` 的 CI run `38027638314` 在 Linux UI components 出現 SIGSEGV：
`test_restart_ignores_queued_old_controller_snapshot` 等待 Qt queue 時，
`_accept_controller_snapshot` 的 `sender()` 呼叫崩潰。獨立覆核確認舊 queued signal 在
Restart disconnect 後仍可到達，不能當作環境偶發重跑放行。Windows 同一測試單跑通過，
但不抵銷 Linux native crash；原始失敗不重標為通過，不刪測試或盲重跑。
PR 尚未合併，worktree 保留。必要原始證據已封存於
`D:\workspace_v2\archives\xbrainlab\pr-160-20261010`；研究 checkout、共用環境及設定不動。

本輪不再追加模型、prompt、RAG 或重試候選。多物件重試因安全回歸未通過而撤回；
既有一次格式修復與多物件零執行邊界保留。產品契約見 [Agent architecture](../architecture/agent.md)、
[Agent target](../target/agent.md)，證據及宣稱界線見 [Validation](../validation/README.md)。
已完成的施工計畫與歷史候選保留於 Git／PR #160，不再作為 active 指令。

2026-10-10 使用者已批准本項修復。Outcome：Restart 前排隊的舊 snapshot 不得崩潰、
污染新 runtime 或重複完成 restart；新 controller 的 snapshot 必須仍在 lifecycle 的 Qt
執行緒處理，維持 activation／cleanup／取消檢查。
Scope：既有 lifecycle signal 接線與直接 regression tests；不改 UI、模型、prompt、RAG、
工具契約或正式評分。不新增 owner／狀態機；優先重用 binding 及 controller identity。
Deletion candidate：斷線後依賴 QObject.sender() 的 snapshot guard；無相容分支。
UI確認：無 presentation 或互動變更；最後只補測 Restart 取消／確認與重啟後操作。
步驟：保留 CI native crash → 最小 queued/restart red → 修正安全接收與相鄰邊界 →
focused tests／跨執行緒證據 → 獨立 actual diff review → clean head CI／Windows 真流程 →
開啟補測版本。產品變更使舊手測 source 不再代表新版；新手測接受後再合併與清理。
假設：重用共享 Windows Python／固定 cache；Linux 由 CI 驗證，不另建共享環境或下載模型。
Stop condition：新 source 直接驗證、獨立覆核及全部適用 CI 通過後交 Restart 手測；
不盲重跑失敗、不刪除保護、不擴成一般 lifecycle 重構。

修正已完成：沿既有binding用captured controller identity與sip.isdeleted接收端檢查，
無新owner／class／signal，production +13/-6、net +7。原CI crash保留；不安全sender seam
在舊source先red，新版121項直接測試、4項相鄰整合與27項Manager／threading保護通過，
另驗current snapshot非全部丟棄、真QThread affinity與parent/native receiver已刪除的排隊回呼。
獨立actual diff review無阻擋；相鄰Manager沒有同樣explicit-disconnect路徑，不機械擴修。
Next：凍結／推送同head CI、Windows真模型Restart流程，再開補測；不得提前合併。
