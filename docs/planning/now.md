# XBrainLab Now

最後更新：`2026-09-16`

## Agreed order — Import UI → Assistant evaluator → cleanup/refactoring

使用者於 2026-09-16 指定以上順序；Preprocess panel 暫不作為下一個優先施工項目。
Import 白框修正已於 2026-09-16 完成 Windows 局部手測，使用者回覆「沒問題了可以準備合併」。
接受的產品 source 為 `b052fd75`，與修正 commit `d0a8b435` 的產品內容相同；接受範圍見
[Current](../current.md)。PR／CI／合併狀態以 GitHub 與 Git 為準，不重啟已完成的修理。
使用者批准的 Benchmark 第一輪已有離線 calibration 實作，能力與限制見下節；
其餘 UI 改版、Assistant runtime repair 與重構尚未開始。

本輪要讓匯入操作更清楚、Assistant 評測結果可信，再依具體問題繼續降低程式複雜度。
不以籠統的「架構已乾淨」、行數下降或總分提高作為完成證明。

### 1. Import UI：後續調整先確認範圍

- 已接受的白框修正不再是 active slice；原生 first-frame 與 transient-window 回歸留在測試。
  修理／失敗／逐幀證據與合併批准隨該修正 PR 保留，不把施工日誌留作後續 dispatch。
- **待確認**：使用者實際想調整的步驟、畫面、文案與互動；先看目前 UI／截圖並列出問題，
  不預先認定整個 wizard 都要重做。
- **邊界**：以已合併的匯入能力為基準，保留 reviewed labels、無標籤選擇、subject/run 選取、
  確認與取消、資料一致性保護。支援格式或 EEG 語意改變必須另作決策。
- **施工前**：將確認過的可見變更、預期行為、非目標、既有 owner、驗證與回退方式寫回本節。
  沿用共用 Windows 環境與 PowerShell log 先提供 PR 前局部預覽；不把 PR／CI 當作開啟本機
  預覽的前置條件，也不把預覽通過當作正式 CI 或合併批准。後續具體 UI 變更仍待確認。
- **完成條件**：已同意的 UI 問題有實際 diff 與正常／失敗／取消路徑證據，Import 既有能力
  無回歸；同版本適用 CI、跨來源資料及 Windows native 畫面／操作檢查通過，再集中一次手測。
  不要求使用者重測全部 134 個資料集，也不把既有自動匯入證據當作新 UI 的驗收。

### 2. Assistant evaluator：先確認評測器是否判得準

- **本輪 scope-complete**：三決策／三層離線 calibration、合成正反例及 focused regression
  已完成；契約、入口與 claim boundary 見
  [Benchmark calibration](../validation/assistant_benchmark_calibration.md)。這不是整體 Benchmark
  完成，也未執行真模型或證明產品成功率。舊 evaluator、81 cases 與 gates 不變；Git／CI／合併
  狀態仍從實際 repository 取得，不因本機驗證通過宣稱已合併或 handoff-ready。
- **下一個候選**：正常 ChatPanel → Host → Command 路徑的真實 observation 收集與 scorer
  對照，先確認少量場景、來源與資源預算，再補齊 active plan；不自動啟動模型／prompt／RAG 改動。
  人工 seeds、family 隔離、Validation／Sealed 管理與同軌跡獨立人工評分仍未實作。
  GUI 依題意區分「開窗」與「完成操作」目前只作 calibration 假設，正式凍結前仍需確認。
- **診斷順序**：由少量可重現案例核對輸入、預期行為、raw output、解析／admission、confirmation、
  command 執行、verification 與評分結果，分開 evaluator 誤判、模型行為錯誤與產品執行錯誤。
- **修理邊界**：先固定預期行為與判分規則，再修理有證據的案例／scorer／runner 問題；
  重用既有 Command truth 與驗證入口，不讓 evaluator 建立另一套 readiness 或假成功。
  工具名稱、參數、確認及可見結果等產品契約變更仍須另外確認。
- **證據品質**：選取與已知誤判直接相關的正確、錯誤及必要邊界案例；明列分母、失敗、skip、
  runner／scorer 及模型版本。舊 frozen 結果保持原身分；若判分規則需改，先批准、版本化並說明差異，
  不暗改舊分數、不刪失敗案例充當進步。必要的真模型執行先固定案例與資源預算。
- **後續整階段完成條件**：可重現的誤判已修正，已知正／反例能被正確區分，有實際執行證據與獨立檢查，
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
