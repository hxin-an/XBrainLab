# XBrainLab Engineering Portal

這個站只提供目前工程權威與目標入口，不展示 mutable dashboard、tracked screenshot 或歷史
checkpoint。

桌面操作與資料集流程請前往 <a href="guide/">使用者指南</a>；本頁只維護工程現況、架構與驗證
入口。

| 問題 | 唯一入口 |
| --- | --- |
| 現在能相信什麼 | [Current](current.md) |
| 接下來做什麼 | [Now](planning/now.md) |
| 目前如何實作 | [Architecture](architecture/README.md) |
| 目標態是什麼 | [Target](target/README.md) |
| 如何判讀測試與 evidence | [Validation](validation/README.md) |
| 重要產品決策 | [Decisions](decisions/README.md) |

## Product boundary

XBrainLab 是本地 EEG desktop product。Desktop workflow 已收斂到共同的 ApplicationService command
spine；Assistant 是下一階段，MCP 不在 active product/thesis roadmap。

Release、CI、人工驗收與科學品質是不同證據層級。只有 tag、GitHub Release、合併 PR 與同一
exact SHA 的 handoff evidence 能支撐 release 查詢；舊 artifact 名稱或 Git history 不能當 current
truth。

歷史文件的索引在 [Historical Records](records/README.md)，詳細內容由 Git history 保存。
