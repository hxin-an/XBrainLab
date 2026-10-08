# XBrainLab Now

最後更新：`2026-10-08`

## Active

目前沒有已授權、尚待施工的產品切片。下一輪目標待與使用者討論，不自動擴張清理範圍。

## 已接受的產品基線

[PR #158](https://github.com/hxin-an/XBrainLab/pull/158) 已於 2026-10-08 合併：
使用者驗收 source `c20b8fc2381fa2dd45d202f8ed16ea286c1b58c2`，
main merge commit `125251c2f828278f530e3a3c91461fa8eb5bc451`。
同 head 的所有適用 CI 通過，Windows 手測通過並取得明確 merge 批准。

產品／研究分離與 Restart Assistant 的現行行為由[產品事實](../current.md)擁有；
研究保存位置由[驗證契約](../validation/README.md#research-archive-boundary)擁有。
本次驗收與失敗／修正證據留在 PR，未以產品合併回寫研究封存。

## 保留限制

Assistant 匯入確認後曾間歇卡住，後續實機與使用者重測成功，但根因仍未證實。
Restart Assistant 是恢復入口，不宣稱修好該匯入問題。若再發生，先保留現場證據定位，
不自行增加重試、重送操作或更改 EEG／後端取消語意。

研究分支、未提交的研究文件與使用者 settings 不屬本次產品工作樹清理範圍；
原始資料、研究封存與共用環境／模型快取保留。
