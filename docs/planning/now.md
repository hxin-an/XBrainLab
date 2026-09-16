# XBrainLab Now

最後更新：`2026-09-16`

## Agreed order — Import UI → Assistant evaluator → cleanup/refactoring

使用者於 2026-09-16 指定以上順序；Preprocess panel 暫不作為下一個優先施工項目。
使用者已於 2026-09-16 以「先幫我處理」授權修正下列兩段 Import 白框閃爍；其餘 UI 改版、
evaluator 與重構尚未開始。推送／開 PR 另待本次詢問的明確回答；合併仍需手測及另行批准。
白框修正的本地實作與 focused 驗證完成。使用者於 2026-09-16 明確要求先開啟 Windows
版本做 PR 前局部手測；下一步是沿用共用環境及 PowerShell log 開啟修正版，確認有回應後
交回操作，不再以 PR／CI 尚未取得作為本機預覽的阻擋。只檢查兩段白框及取消／重試，
不要求重測整個產品。定稿後仍需推送／開 PR 授權、同 head 適用 CI 與正式 handoff gates；
本次預覽不稱 handoff-ready，也不是合併批准。外部寫入與合併授權仍未收到。

本輪要讓匯入操作更清楚、Assistant 評測結果可信，再依具體問題繼續降低程式複雜度。
不以籠統的「架構已乾淨」、行數下降或總分提高作為完成證明。

### 1. Import UI：先討論，再完成已確認的 UI 修正

- **第一個已回報問題**：使用者於 2026-09-16 指出 Import 會閃出多個白框，並確認發生於
  選完 subject 後及按 `Confirm and Import` 後。先聚焦這兩段交接，不擴為整個 wizard 重設計。
  Windows 真 MainWindow＋public BIDS fixture 已重現精靈建立期間 44 次 parentless label/button/
  panel 的 top-level Show；它們使用淺色預設 palette，隨後才被 reparent。對應 review rows 的
  layout 尚未掛入 card 就呼叫 show，以及數處 setVisible 早於 addWidget。不是 backend 載入失敗。
  新增事件觀測回歸已 FAIL（捕捉瞬時 Show，不只看最後截圖）。首輪未觸發匯入與第二輪前景錄影
  零幀的證據保留；不能把該次錄影稱為已驗證不閃爍。
  Parent-before-show 修正後，44 次意外小視窗降為 0；隨後的 124 幀螢幕錄影仍抓到
  loading/preview 首次呈現白底（`build/dev-artifacts/import-white-flash/after-walkthrough`），
  因此未提早交付，繼續修理首幀交接。不改 Windows 全域設定、不添加固定等待，
  不修改其他 panels 或 backend。
  關閉 DWM animation 的診斷仍閃白，未納入產品。只在 loading/preview 使用 BaseDialog 的
  opt-in Windows 首幀顯露：初次 paint 完成後的 Qt turn 恢復 opacity；QTimer 歸 dialog 所有，
  不新增 authoritative owner、不加固定等待、其他 dialogs/platform 保持原行為。兩個 Windows
  首幀測試均在接入前 FAIL；正式修正後 166 個 Windows focused tests PASS（含 file/BIDS/
  recipe 元件、首幀、關閉／銷毀、取消／重試與 fresh review），changed-file lint/format PASS。
  真 MainWindow 連續兩次匯入成功；`build/dev-artifacts/import-white-flash/product-fixed-repeat`
  保存 190 幀與視窗事件：無意外小視窗，匯入後畫面無大片白底。診斷只隔離 folder chooser，
  用暫時置頂的測試主視窗避免錄到其他 app；不是所有 DPI、所有資料集或真人驗收。
  Production 5 files，+39/-10/net +29 LOC；未改 coordinator/Command/persistence，未增 owner。
- **已檢查的交接路徑**：`DataInterpretationActionCoordinator` 在 subject 確認後建立 loading
  dialog，再建立、顯示 preview 並關閉 loading；preview 的 show/resize 另有 layout 調整。
  Confirm 後會等待 preview 銷毀，再由 continuation 進入 revalidation／apply，必要時重開 review
  或 resource confirmation。先核對視窗 show/hide/destroy 與實際首幀繪製的時間，不把這些路徑
  的存在直接當作白框成因；修正保留既有 modal／取消／確認保護。
- **本問題下一步與驗收**：先開啟 Windows 修正版供使用者做 PR 前局部手測，附短檢查流程；
  取得推送／開 PR 授權後執行同 head 適用 CI、source-diverse／DPI
  gates。現有正常／慢 metadata 取消與重試、第二次匯入及首幀證據不取代正式 gates。
  已取得這兩段閃白修正的 UI 授權；範圍僅穩定繪製／交接，不重新設計操作流程或 EEG 語意。
  先保留失敗重現，再修理既有 owner；必要時按視窗／繪製責任補最小回歸測試。
  完成時需證明過渡不露出白色空框、狀態持續可理解，
  必要確認不跳過、取消／重試及匯入結果仍正確。穩定後的截圖或後端匯入 PASS 不足以證明不閃爍。
- **待確認**：使用者實際想調整的步驟、畫面、文案與互動；先看目前 UI／截圖並列出問題，
  不預先認定整個 wizard 都要重做。
- **邊界**：以已合併的匯入能力為基準，保留 reviewed labels、無標籤選擇、subject/run 選取、
  確認與取消、資料一致性保護。支援格式或 EEG 語意改變必須另作決策。
- **施工前**：將確認過的可見變更、預期行為、非目標、既有 owner、驗證與回退方式寫回本節。
  白框修正以外的具體 UI 設計／互動變更仍未確認；不因排列優先順序而擴張施工。
- **完成條件**：已同意的 UI 問題有實際 diff 與正常／失敗／取消路徑證據，Import 既有能力
  無回歸；同版本適用 CI、跨來源資料及 Windows native 畫面／操作檢查通過，再集中一次手測。
  不要求使用者重測全部 134 個資料集，也不把既有自動匯入證據當作新 UI 的驗收。

### 2. Assistant evaluator：先確認評測器是否判得準

- **待確認**：evaluator 指的是哪個既有 runner／scorer／報告入口，以及目前觀察到的不合理結果。
  在此之前，不把「處理 evaluator」解讀為重寫 Assistant、換模型或改 prompt／RAG。
- **診斷順序**：由少量可重現案例核對輸入、預期行為、raw output、解析／admission、confirmation、
  command 執行、verification 與評分結果，分開 evaluator 誤判、模型行為錯誤與產品執行錯誤。
- **修理邊界**：先固定預期行為與判分規則，再修理有證據的案例／scorer／runner 問題；
  重用既有 Command truth 與驗證入口，不讓 evaluator 建立另一套 readiness 或假成功。
  工具名稱、參數、確認及可見結果等產品契約變更仍須另外確認。
- **證據品質**：選取與已知誤判直接相關的正確、錯誤及必要邊界案例；明列分母、失敗、skip、
  runner／scorer 及模型版本。舊 frozen 結果保持原身分；若判分規則需改，先批准、版本化並說明差異，
  不暗改舊分數、不刪失敗案例充當進步。必要的真模型執行先固定案例與資源預算。
- **完成條件**：可重現的誤判已修正，已知正／反例能被正確區分，有實際執行證據與獨立檢查，
  並清楚列出仍屬 Assistant 本體的問題。Evaluator 可靠不等於 Assistant 已達 Stable。
  若未發現 evaluator 缺陷，記錄判分依據與真正問題，不為了這個階段而強行修改。
  若只改測試／評分工具且沒有產品行為變更，不另要求 GUI 手測。

### 3. 清理與重構：按已確認的模組問題施工

- 完成前兩階段後，依實際 diff、reachable callers 與 reviewer findings 決定第一個模組，
  不現在先宣告整個核心都要重寫，也不重新執行已結束的全面匯入盤點。
- 每個模組明列責任、入口、測試保護與刪除／保留理由；優先刪除確認未使用的能力與專屬測試，
  合併重複政策與狀態。大型檔案依責任處理，不以搬檔或降低單檔行數冒充改善。
- Production、tests 與 scripts 一起看；mock-heavy 測試是否移除須有更可靠的替代證據。
  檢查不必要的資料複製、重複掃描及等待，但不先承諾大幅加速。
- **完成條件**：通過 reviewer 對本次責任邊界、回歸風險、測試有效性及複雜度的審查，
  已承諾項目與必要驗證齊全，才交付整合版本；不以做完一個切片當作整階段完成。
  無關發現列為後續候選，不無限擴張本輪。

### 節奏與跨輪延續

本文件是唯一 active plan；每階段開始前補齊具體 scope／假設／驗證／stop condition，施工中更新
next step 與 blocker。小 commit 用於回退，review 依模組與風險安排，不因每個小切片就要求手測／merge。
有產品可見變更時，在同意的完整範圍驗證完成後集中手測；真正需要新決策或授權時明確停在該邊界。
Context compaction 不是完成條件：接手先讀本節、Git 與執行狀態，再繼續已授權的下一步。
優先順序不是全部實作的預先授權；也不自動啟動下方獨立的 Assistant runtime repair 候選。

## Closed baseline

Quality-baseline closure was accepted and merged via
[PR #140](https://github.com/hxin-an/XBrainLab/pull/140). Its implementation/evidence history stays in
Git/PR, not active dispatch. Known Assistant limitations below remain deferred.

Retained import was manually accepted and merged through
[PR #141](https://github.com/hxin-an/XBrainLab/pull/141) on 2026-09-16. Accepted source, bounded
coverage and known limitations belong to [Current](../current.md); required data/failure evidence
remains on E. The former task worktrees were removed; do not restart their completed campaigns.

## Deferred candidate — Assistant runtime reliability (not evaluator scope)

Goal: reliable selection and parameter-collection continuity with no unexpected workflow side effects.
LOC, static pass, literal prompt assertions or one improved score are not completion criteria.

1. **Mechanism audit before choosing a fix.** Trace baseline/retained failures from full rendered input/
   RAG through raw output, parser, capability/provenance, typed receipt, GUI terminal and visible response.
   Separate intent errors, missing clarification fields, invalid/stale admission and evaluator assumptions.
   Reproduce a bounded set through normal ChatPanel with real execution, using no patient data.
   No Host intent guessing or new model experiments in this diagnostic phase.
2. **Approve a repair boundary.** Select one evidence-backed hypothesis and existing owner. Explicitly
   decide behavior for unspecified/multiple actions, missing/partial values, correction/cancel and
   unavailable tools. Tool/schema/confirmation/visible-flow or model/RAG changes require separate
   approval; current source/tests do not ratify target. A larger model is neither proven necessary nor
   authorized. No generic evaluator platform, control plane or parallel state owner.
3. **Separate development and acceptance.** Keep frozen 81/scorer unchanged as regression evidence.
   Before implementation, define supplementary development cases and disjoint reviewer-owned holdout
   by failure family. Never tune on the holdout or shrink its denominator; disclose prior exposure to
   frozen cases. Reuse existing runners, review any necessary bounded extension, and agree a candidate/
   resource budget before execution. Do not repeatedly add two more prompt attempts after failure.
4. **Implement/review one coherent repair.** Prefer deletion/reuse; test failing observable behavior
   through actual owners, then passing behavior. Mock external inference only in unit tests; real-model/
   native evidence cannot substitute fake generation or preapproved GUI terminals. Independent reviewer
   checks mechanism, meaningful tests, complexity and scope, not only summary.
5. **One integrated acceptance.** Require 36/36 positive, 10/10 explicit origin, 5/5 missing guards,
   5/5 direct clarification admission, 24/24 product no-action and 7/7 clarification. Holdout must show
   zero unexpected execution/confirmation/navigation/mutation and correct authorized continuations.
   Separate raw-model/Host/product outcomes. Then same-source normal ChatPanel→GUI→Command journey,
   relevant cancel/stale cleanup, applicable CI and one final Windows GUI/English Assistant acceptance.
   No Stable/generalized-safety claim from bounded cases alone. Unsupported mechanism or exhausted
   budget means a documented decision checkpoint, not weaker gates or automatic extra prompt edits.

This runtime repair proposal is separate from the evaluator phase above; its promotion criteria do not
automatically become evaluator-repair gates or authorize product/model changes.
New implementation begins only after diagnostic outcome, scope and budget are approved.

其他候選方向見 [Roadmap](roadmap.md)；不宣稱 Assistant Stable 或零缺陷。
