# XBrainLab Now

最後更新：`2026-10-08`

## Active — Restart Assistant 功能驗證與交付

使用者明確核准在 Assistant Settings 加入 Restart Assistant，重建 Agent／模型、清除對話，
保留設定、EEG 與已提交後端工作；不自動重送操作。Windows 隔離 UI 預覽已展示，使用者於
2026-10-07 明確接受並要求功能實作；設定元件 focused tests 67 passed，未以模擬進度冒充重啟證據。
既有 PR #158 head `55068515` CI 已通過；使用者回報 Assistant 匯入確認後曾卡住，後續實機與
使用者重測均成功，根因仍未定位。Restart 是恢復入口，不宣稱修好該匯入問題。

- Scope：設定視窗的明確操作／確認／進度／失敗提示，重用 runtime lifecycle 與 dispatcher
  的完整清理，再啟動已保存的模型設定；舊 handoff／turn 回報不得進入新對話。
- Non-goals：不改 prompt／RAG／模型、EEG 語意或後端取消政策；不重啟整個 App、不加全域 kill、
  不清模型快取、不寫 root settings.json；不合併 PR 或清理研究 worktree。
- 假設／complexity：已有 lifecycle owner 可承擔 restart，dialog 只呈現狀態、manager 只接線。
  owner 前後不變；deletion candidate 是共用 unload／cleanup 的重複邏輯，不建第二套控制器。
  若需要新 owner／狀態機或超出複雜度門檻，先重審。LOC 與實際 diff 於施工後核對。
- Steps：查明 cleanup／turn 邊界 → 失敗保護測試 → UI 與既有 owner 最小 coherent extension →
  focused tests／獨立 async 覆核 → 隔離 Windows 元件預覽 → 接受設計後正式整合驗證。
- Focused validation：確認取消不改狀態；重複點擊不重啟兩次；舊 cleanup 未完成不啟新 runtime；
  cleanup／load 失敗明示；背景 Command 繼續且不重送；舊回報隔離；關閉設定或 App 不留下新程序。
- Stop：完整 restart focused／native evidence 與獨立 async review 通過後交付手測；不自動 merge。
  若資源／權限或新的產品決策阻擋則明示。不因一次成功宣稱原匯入 bug 消失。
- 已實作：既有 lifecycle 共用 unload／cleanup、真 READY 才完成；只 detach Assistant consumer，
  保留 Desktop completion。Qt ingress 拒絕被替換／銷毀／清理失敗的舊 sender；App close 優先。
  334 項直接相關 tests 通過，獨立 async reviewer 最終無程式碼阻擋；未宣稱全專案重審。
- Windows 真模型驗證：Granite CUDA、真 Settings 操作，閒置與生成途中重啟均完成；
  舊子程序退出、設定不變、對話清空、新模型可再次回答。最後一次等待既有 montage／owned work
  settled 後比較完整 backend state／generation，均不變；沒有放寬狀態一致性斷言。
  第一輪曾 full-state mismatch，但未記錄差異欄位，不能宣稱已證明原因。後續完整快照記錄確有
  匯入後 montage pending→ready 更新，既有 regression 也通過；這支持修正驗證基線的等待條件，
  不把後續成功抹去首次失敗。原始測試輸出與 build/restart-native-validation 的隔離證據保留。
- Next：使用者於 2026-10-08 核准更新產品 PR #158 並處理 CI，通過後開啟 Windows 手測；
  提交／push 本切片，核對新 head 全部適用 CI，修理直接阻擋並保留失敗證據。
  舊 head CI 不代表新功能通過；手測接受前不 merge，不清理使用中的 worktree。
- CI `37725549412` 的 Static Quality 偵測 Settings restart handler 未明確排除 optional manager；
  UI 已在無 manager 時停用按鈕，但型別檢查不能由 widget 狀態推導。入口補同一依賴檢查，
  不修改 type baseline／gate／重啟語意；驗 Settings focused tests 與新 head Static Quality。
  同 run 的 agent integration 暴露舊 runtime 替身缺少 restart signals；同步兩個直接相關
  integration doubles 的介面與 idle 狀態，保留原 assertion，重跑 long-session／product walkthrough。
- 同 run 的 Linux unit-ui 在直接 snapshot 呼叫的 `sender()` 原生查詢發生 SIGSEGV；
  Windows 單測未重現崩潰。直接 snapshot helper 不應依賴 Qt signal context，移除重複查詢，
  保留唯一 signal adapter 的 sender fence 與 activation ID 驗證；補無 sender context 的准入測試，
  並重驗 delivery／lifecycle／worker supervision 與獨立 async review。Linux integration-ui 的
  GC abort 另待修正後同組 CI 核對，不先推定已解決；不跳過任何 gate。
- 第二輪 Static Quality 的型別檢查已清零，architecture guard 指出新 `_request_unload`
  的未綁定 controller 清理入口尚未登錄。此路徑與既有 close／startup rollback 同屬 runtime
  owner，dispatcher 尚未取得它；只登錄 exact method／receiver 的 `close`，不放行一般 UI
  mutation。補准許與錯誤 receiver／method／callsite 拒絕測試，獨立覆核後跑完整 architecture gate。
  覆核並找到未綁定 controller.close 回 False 時無 dispatcher callback、會永久 restarting 的
  邊界；補 failed-bind → cleanup pending → restart 失敗 → 清理成功後重試的 red/green，
  未清理成功前不得建立新 controller。第二輪 Linux unit-ui／integration-ui 已通過，原 abort
  原因不據此宣稱證實；最後 head 仍須完整 CI。

## Candidate — 研究／產品分離 PR #158

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
Qt單元驗證為Windows offscreen。其後 head `55068515` 的 CI 已完成，使用者已完成該版本
GUI／Assistant 匯入重測；新 Restart 變更須另驗，不挪用舊 head 證據。完整collection不是全套執行。

### PR #158 CI 修正

首輪CI的scripts分組3 failed／1590 passed：三個保留的工程診斷測試仍假設Host會攔下
原句沒有的數值，與已核准移除numeric membership的契約不符。CI原始失敗保留於run
`37429167262`；不改scorer、不恢復舊Host限制、不動研究封存或結果。
本機重現三項後更新斷言：自行補值仍判模型失敗、合法格式不重試；Host准入與模型分數分離，
診斷runner到達執行邊界但抑制真實執行。兩份完整工程測試114 passed、獨立覆核無阻擋。
Windows Git不能解析WSL worktree指標造成的兩項環境失敗，僅用測試process的正確Windows
GIT_DIR／GIT_WORK_TREE解決；無Git metadata、共用環境或scorer改動。push後重驗同head CI。
本修正無可見UI變更，無新owner。停止條件仍為所有適用CI成功；不merge。

產品PR #158 head `55068515` 適用 CI 已通過；研究PR不整批合併。
更廣泛逐模組打磨另訂目標，不藉本切片繼續擴張。原始資料、共享環境與封存都不清除。
