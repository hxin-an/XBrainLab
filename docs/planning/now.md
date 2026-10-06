# XBrainLab Now

最後更新：`2026-10-06`

## Active — 研究／產品分離PR驗證

2026-10-06使用者同意送產品PR與CI驗證。只push本task分支並開main-base產品PR，
核對exact head的所有適用checks，修理本範圍驗證阻擋；不merge、不關閉研究PR或刪除worktree。
Outcome／stop：PR建立且同head所有適用CI完成成功，回報產品交付界線及剩餘真人驗收。
若需要新產品決策／外部資源則明示阻擋；不因CI pending就停止追蹤。

本輪使用者同意將研究流程留在封存，產品繼續獨立開發。
產品worktree：`D:\workspace_v2\projects\lab\XBrainLab-product`，
branch `refactor/product-research-separation`，基準main `72548c00`。
研究分支 `feat/valid-selected-systems` 的f77b4bfe、原始實驗與使用者settings均保留。

### 已完成邊界

- 承接停止訓練exact-run確認、訓練publication一致性、取消數值原句membership的產品修復。
  12檔+306/-40/net+266已做complexity與獨立覆核；owner不變，非新增控制層。
- 研究批次／五輪配置／題庫評分／報表／背景續跑入口及專屬測試從產品刪除，未留legacy空殼。
  LocalBackend研究pin／template override、兩個無讀取者DTO欄位及MainWindow研究factory已清除。
- 真CPU訓練stop／結束／替換run、resample、numeric DSP及panel／saliency路由改用產品測試，
  不依賴研究scorer。一般runtime生命週期、dense-only工程診斷、capture與既有產品gate保留。
- 研究方法與執行歷史不再佔用產品文件；保存位置由[驗證契約](../validation/README.md#research-archive-boundary)擁有。
  最新選版理由已補存NAS與E槽，各四份文件SHA一致；原TAR／source／結果不覆寫。
- NAS封存根入口的11個範圍環境檢查exit0，使用封存source與NAS共享環境，不引用產品worktree。

### 本機證據與限制

Windows共用環境未重建。初次完整collection拒絕舊editable checkout的namespace路徑；
僅在測試程序移除舊根路徑並保留active-checkout guard後，最終10471項collection exit0。
直接修復／backend／catalog回歸505 passed；遷移流程與測試分組88 passed；
移除MainWindow研究factory前28／後27 passed，少的一項為刪除能力專屬測試。
相鄰Agent／saliency／training refresh與runner先前172 passed；不將重疊案例相加宣稱總覆蓋。
一次分組檢查在並行刪檔時拿到舊清單而失敗；凍結修改後同組88通過，未放寬assert或timeout。
Ruff／format、guidance、strict docs與diff檢查通過。三位agent依職責交叉覆核實際diff，
最後找到的背景研究入口已刪除並重審，範圍內無阻擋項；不宣稱其他模組已全盤審查。

產品模型／prompt／RAG、可見UI與EEG語意不變；未追加模型推論或改分。
Qt驗證為Windows offscreen，不是新真人手測。尚未有本分支CI／source-diverse／native手測證據，
不稱handoff-ready，不自動merge。完整collection不是全套測試執行。

### PR #158 CI 修正

首輪CI的scripts分組3 failed／1590 passed：三個保留的工程診斷測試仍假設Host會攔下
原句沒有的數值，與已核准移除numeric membership的契約不符。CI原始失敗保留於run
`37429167262`；不改scorer、不恢復舊Host限制、不動研究封存或結果。
本機重現三項後更新斷言：自行補值仍判模型失敗、合法格式不重試；Host准入與模型分數分離，
診斷runner到達執行邊界但抑制真實執行。兩份完整工程測試114 passed、獨立覆核無阻擋。
Windows Git不能解析WSL worktree指標造成的兩項環境失敗，僅用測試process的正確Windows
GIT_DIR／GIT_WORK_TREE解決；無Git metadata、共用環境或scorer改動。push後重驗同head CI。
本修正無可見UI變更，無新owner。停止條件仍為所有適用CI成功；不merge。

Next：追蹤產品PR #158修正後同head CI；研究PR不整批合併。
更廣泛逐模組打磨另訂目標，不藉本切片繼續擴張。原始資料、共享環境與封存都不清除。
