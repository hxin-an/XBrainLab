# XBrainLab Now

最後更新：`2026-09-12`

## Active

目前沒有已授權、尚未完成的施工 slice。

三核心責任重構已完成 Windows GUI／English Assistant 手測，並經使用者明確同意合併
[PR #138](https://github.com/hxin-an/XBrainLab/pull/138)。不再把該階段的施工切片或 pending gates
當作 active dispatch；實作、review、驗證與驗收紀錄由合併 PR、Git history 和 exact-source evidence 保存。

`main` 仍是唯一產品基線；當前 SHA、branch、dirty state 與 worktree inventory 從 Git 取得，
不從這份文件推定。原始 checkout 的使用者修改、本機設定、原始資料與共用環境不屬於本輪清理。

## 已知邊界與下一步

- 三核心保留正式 Command／publication、Qt runtime coordination 與 UI composition 責任，
  不以核心行數仍大判定必須繼續拆分；目前責任邊界見
  [Backend](../architecture/backend.md)、[Assistant](../architecture/agent.md) 與
  [UI](../architecture/ui.md)。
- Assistant 維持已接受的 bounded baseline，不宣稱 Stable promotion 或零缺陷；
  產品與證據限制見 [Current](../current.md) 和 [Validation](../validation/README.md)。
- Panel navigation 的既有 metrics 會延後到下一輪才 finalize；正式 correlated terminal 與
  UI completion 正常。此 observability 缺口是候選 follow-up，不是新的施工授權。

下一輪工作由使用者選定問題與 acceptance 後，再更新此唯一 active plan；
其他方向見 [Roadmap](roadmap.md)，不自動接續另一輪重構或模型實驗。
