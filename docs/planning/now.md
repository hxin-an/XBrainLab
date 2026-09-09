# XBrainLab Now

最後更新：`2026-09-09`

## Active

目前沒有待施工的 implementation slice。

本機環境已收斂為一套 Windows GUI／Assistant 產品環境；WSL 僅保留既有開發工具，
Linux 產品測試由 CI 提供。固定手測入口、暫存保留規則與離線 WSL 原地壓縮步驟以
[本機開發環境](../developer/local-setup.md#多-worktree固定手測環境)為準。
[PR #133](https://github.com/hxin-an/XBrainLab/pull/133) 保存本輪驗證與失敗修正證據。
真實 WSL VHDX 尚未壓縮；使用者須保存工作並停止 WSL 後，從 Windows 執行已部署腳本。
腳本測試或已刪除 Linux 檔案不代表 Windows 虛擬磁碟已縮小，不自動刪除備份或合併 PR。

全面清理／品質強化與 Windows 手測修正已在 [PR #131](https://github.com/hxin-an/XBrainLab/pull/131)
完成；使用者於 2026-09-09 明確表示「手測完成 同意 merge」，並已合併。
該 PR 保存測試範圍、exact product source、CI、手測批准與歷史失敗證據。
不再把已完成的 Filter、RAG、Montage、Re-reference 或 Saliency 修理計畫當成 active dispatch。

下一個產品變更須由新的使用者要求界定；不因本輪結束自動追加清理或宣稱架構／測試已無缺陷。
產品能力與既有限制以 [Current](../current.md) 為準，驗證與批准規則以
[Validation contract](../validation/README.md) 為準。
