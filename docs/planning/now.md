# XBrainLab Now

最後更新：`2026-10-12`

## Accepted baseline

PR #162 已於 2026-10-12 合併；main `620a4341` 與手測產品 `c4885f44` 的
source tree 一致。使用者已明確手測通過並同意 merge。既有 Training Settings、
Data Splitting、狀態列與 Preprocess history 設計保留；不再將功能驗收推論成結構已理想。
歷史驗收、失敗與閱讀證據已保存於主 checkout 的 ignored
`build/handoff-evidence/pr162-accepted/`；不改寫歷史結論或研究資料。

## Active — Training／Preprocess 保留決定核查與結構收斂

### 問題、證據與 outcome

使用者已多次要求逐模組深入整理，既有 reviewer 與檢查角度未充分阻止過早結案。
前輪從 519 路徑補成 554 路徑，已修正直接交界漏列；但完整閱讀、無回歸與「有理由保留」
仍不能單獨證明可維護性已達標。ApplicationService 4,211 行、共用 application tests
10,810 行、Training sidebar 1,924 行，是需核查責任集中與修改成本的訊號，不是刪碼配額。

本輪不重新盤點全專案，而是沿既有責任分組核查保留決定，將站不住腳的結構實際收斂。
Outcome：具體減少責任混雜、重複 policy／轉接與測試查找成本；保留項有源碼與可行替代
方案的比較，不只「有 caller／怕拆壞／CI 綠」。不承諾零 bug、100% coverage 或全面消除大檔。

### 範圍、責任與 non-goals

| 組別 | 既有保留對象／需解決的問題 | 寫入責任 |
| --- | --- | --- |
| Shared command spine | ApplicationService 初始化／公開查詢／两階段 prepare→commit／錯誤與發布；比較 focused owners 的既有責任，檢查不必要的跨域知識與重複傳遞 | Main |
| Training | manager／holder／record／split generation／resource／sidebar 保留決定；配置、訓練與 terminal／artifact 責任能否局部收斂 | Training worker；先提具體方案 |
| Preprocess | command／processor／pipeline transaction、Raw／Epochs 直接語意、render／preview、下游失效與 rollback；不另立 publication owner | Preprocess worker；先提具體方案 |
| Tests | 對應單元、共用與 integration tests 的組織、duplicated fixture／mock choreography；實際行為 oracle 與低 mock 流程 | 跟隨對應 owner；shared test 由 Main |
| Scripts／validation | 既有本輪 runner／capture／handoff／CI 入口，重複用途或 setup、無用途 wrapper 與 false-green 風險 | Validation worker；先提具體方案 |

相關設定與 canonical docs 隨真實決策同步，不另立第二份 plan／通用盤點平台。
三組 product/tests/scripts 都必須有決定，不因只完成 ApplicationService 就宣稱整輪結束。
第三方模型數學、全 Import／Agent／Evaluation／Saliency 重做、論文與資料下載、環境搬遷
不在範圍。直接資料／取消／publication 邊界仍必須檢查。
UI 狀態：既有全部可見布局、文案、功能、互動已接受，本輪只授權保持行為的內部變更。
正式 Command／query／Assistant／artifact 契約不默改；必要新決策另行報告。

### 施工順序與 complexity review

1. 先核查既有結案理由對應的實際 source、入口、caller、state reader/writer、error／cleanup。
   每責任組比較 deletion、局部收斂、重用既有 owner、抽出純邏輯與保留；原摘要不是證明。
   不新增逐 helper 台帳。既有 ignored review notes 作工作材料，canonical 決策放原有文件。
2. 先處理 shared ApplicationService 與 Training 執行鏈，再接 Preprocess 交界，tests/scripts
   同步整理；可獨立的只讀比較平行做，source 寫入不重疊。跨 owner 移動先協調。
3. 每 slice 先列 entry/callers、deletion candidates、owners before/after、預期 source delta、
   passing characterization、rollback 與停止條件，再寫碼。新增 production module/public class、
   owner/state machine/receipt/compatibility 或跨數量門檻先 complexity review。
   不為消除大檔引入 generic dispatcher、mixin 或每方法 proxy；純搬檔不稱責任簡化。
4. Refactor 先同範圍 passing baseline；bug 先真實可觀察 red。保護功能／語意／數值、
   stale/cancel/stop/retry、publication、artifact 與 cleanup，不靠減 assertion 換綠燈。
5. 高風險獨立 reviewer 先讀原碼／契約／問題，再比較改動与保留方案；分開判斷回歸安全、
   原維護問題是否解決、剩餘結構理由是否成立。Main 看實際 diff／原始證據並承擔結論。
   無新 defect 不等於結構合格；無可證明改善也不強拆湊數。

### 驗證、資源與停止條件

- 使用既有 Windows shared Python／models；native abort 風險採 prlimit 與明確 timeout。
  Baseline/focused 順序協調，不同 agent 不併發跑重型 native suite。
- 每 slice 只跑直接相關 tests／lint；完整候選依 validation contract 取同 head CI、
  source-diverse、平台與適用 native/UI evidence，不重跑 CI 等價本機全套。
- 七個缺指定 OpenNeuro sub002/sub003 的 optional cases 仍是未執行，不藉本輪隱藏或刪 marker。
- 原手測批准僅限 PR #162。新版本需一次集中手測；不每小切片要求使用者驗收。
  PR/worktree 維持單一主要目標，超過 root complexity/PR 門檻不自行假定例外。
- 完成必須：所有本輪保留責任組有可驗證決定、已確認冗餘物理清除、沒有未決 scope 內
  結構問題、測試保障未下降、獨立覆核接受結構與回歸、最終同版 gates 通過。
  交付需前後責任差異、產品／測試／腳本／文件／設定各別行數、實際限制與 Windows 完整程式。
- 不在完成一個 slice、compaction 或 CI pending 停工；不擴成新功能，也不自行 merge 新候選。
  若只有閱讀／搬檔而無可證明的改善，明確報告，不能換成「已完全乾淨」。

### Current / next

Current：PR #162 已合併；task worktree 建於 main `620a4341`，分支
`refactor/training-preprocess-boundaries`。主 research checkout 的 dirty docs/settings 不動。
舊 task tracked source／Git 登記已清，Windows preview console 仍持有的空目錄暫不強制終止
不明程序；必要 evidence/manual artifacts 已逐位元核對保存，shared環境與原始資料保留。
已確認第一組 coherent slices（不是整輪完成）：
- Training：ApplicationService 的 saved-split start/discard 約 95 行實際組織 split candidate、
  resource receipt、commit／rollback，TrainingCommandService.handle_train 卻只有 23 處 unit
  caller、繞過 saved split。移入既有 TrainingCommandService 的唯一 train/discard 入口，
  required lazy split-service getter 保持冷啟動；刪除原 shortcut，不能保留第二條便利入口。
  Admission／lock／synchronous terminal publication 仍屬 ApplicationService；owner 數不變，
  預估 2 production files +110/-120、net -10，不新增 module。Main 改 service glue，worker
  改 training_service／專屬 tests；先 passing baseline，保留 public saved-split、receipt、
  startup rollback、synchronous/interactive 結果與 artifact tests。回退為獨立 commit。
- Preprocess：_DetachedPreprocessStudy 只用來讓 fresh PreprocessStateService 讀取 captured
  source，且提供四個只會 throw 的 mutation 方法。既有 prepare_* 改接明確 source_data，
  移除 fake Study／temporary Observable service；commit_prepared 的單一 mutation owner
  不變。預估 2 production files net -20～-50，無新 module／owner；先既有 prepare/command
  characterization，再驗 live source 不被 prepare 改動、cancel/stale 與正常 commit。
- Validation：public cross-source runner 的兩條路徑重複 import／preprocess／close，未檢查
  is_closed，疑有未完成 close／exception 錯判通過或蓋原錯誤；先真 service cleanup 故障重現，再在既有 runner 局部
  收斂。四個固定 case、兩種 protocol、數值／artifact oracle 不減少；不是新增 runner owner。
  未使用的 saliency 配置須先證明不影響結果或契約，不能只因沒有 compute 就直接刪除。
- Validation consumer：已重現 required CI verifier 接受 empty results + 成功 summary。
  在既有 public runner 抽出純 summary 計算，由 producer／consumer 共用四個 required case
  規則；consumer 核對真實 rows 與宣稱的一致性，不新增 schema owner。先檔案破壞 red，
  再保護 missing／duplicate／failed／protocol／reload 與正常完整報告；script 預估 net
  +40～80、product 0。既有 source provenance 檢查獨立保留。
- Split representation：pure config parsing 現位於 mutable DatasetGenerationCommandService，
  preview、ApplicationService shim 與 sidebar 因此依賴 mutation owner。改由既有 immutable
  DatasetSplitSpecification 提供 to_config／from_config，保留 payload normalization、fingerprint、
  workflow rejection 與錯誤文字；刪 callback/shim 與 payload round trips，不改 domain config
  廣義 constructor。預估 4～5 production files 約 230 行移位、net -30～60，owner 不增加。
  先 parser/preview/deferred/UI saved-split baseline；preview→save→train allocation 要一致。
- Final training result：holder 直接保存/回填 TrainRecord 兩個 storage fields 的 rollback 移入
  既有 TrainRecord completion/export 操作；holder 只管計算與 terminal，record 管原子可見性。
  disk 多檔 crash atomicity 不擴張。2 production files 預估 net +7；先實際 artifact roundtrip
  與 final export failure baseline，保護原 record identity／tracker stable token／先前 repeats。
- Epoch provenance：已核對 Raw loader 不會載入 preprocess history；真實 TimeEpoch／WindowEpoch
  才是來源 producer。將既有 provenance stamp 放在這兩個 producer，刪 aggregate 以顯示文字
  推論權威的路徑。保留 metadata schema／來源座標／split 語意；僅不再接受手工捏造 history
  作為來源證明，這不是支援的 import 契約。3 production files 預估 net -10～30，無新 owner。
  先 real producer→resample→FIF reload baseline，再 forged-history red；舊 fixture 改走真 producer，
  不用直接 stamp 掩蓋風險。無有效來源仍 unverified；正常 import/epoch 數值與分類不改。
  直接依賴：Resample 必須在重採樣前讀取已驗證 metadata，成功後沿用原 source identity/grid
  更新 rate/window metadata；不能從匯入路徑重新造出來源權威。既有 reader 改為命名純函式，
  在同 epochs module 小函式處理更新，不新建 owner。4 production files 合計預估 net +5～45；
  真 producer→epoch-resample→FIF reload 與 malformed/unverified/event-grid 檢查一起驗證。
  獨立覆核指出既有 reader 未核對 metadata rate/tmin/tmax 與 live MNE timing；新 Resample
  使用這個 reader 作 admission，因此需先補 stale timing 的 real-data red 與窄幅核對。
  已知來源 window 必須和實際資料一致，無效 metadata 保持 unverified；FIF 非整數 sfreq
  roundtrip 用來界定數值容差，不改 schema 或為缺資料推論 provenance。
  實測採 exact FIF serialization match，而非任意容差。獨立覆核另追蹤到 off-grid tmin
  存檔捨入後再次 resample 會偏移 source window；先 red，再只對已驗證的 detached epochs
  還原 metadata 記錄的原時間起點。原始 samples／events／live source 不變，必須驗證
  第二次 resample 的 source start／end 與來源資料未被改動；未驗證資料不得走此修復。
- Shared application tests：10,810 行混合 import、publication、training、analysis、montage。
  依責任分組移至明確 test modules；單組 helper 留在該組，共用小型 fixtures 集中，禁止
  跨 test module imports。AST 核對每個 test body／decorator 保留與 collection case IDs 對應，
  baseline 為本輪既有 395 passed；唯一已刪案例是完全 mock 的私有 start-wrapper choreography，
  無 saliency assertion，真正 public split→train／rollback coverage 保留。此項改善查找與
  修改邊界，不宣稱搬檔提高覆蓋率或產品縮碼；production delta 0。
- Capture fixtures：polish/reviewer 兩份相同 Step 2 construction／settle 移入既有
  training_evidence_fixture，兩路直接重用；刪 wrapper，保留各自 capture coverage／width。
  Product 0，script 預估 net -40～55；先現有真 Qt holdout/CV/layout baseline，再 failure
  cleanup 測試，不改 screenshot 期待或可見 UI。不同 Training Settings 場景不強合併。
- Training manager 歷史模式：全 repo production constructor 已只有 explicit compute、全已完成
  run set；自動 baseline／append-only saliency target 的欄位、分支與專屬測試無產品入口。
  刪這條舊模式，保留 run identity/count、command completion barrier、CAS、取消、terminal
  retry 與手動 no-target domain 路徑。先所有現行 manual/async/terminal characterization，
  逐一區分測試中的舊模式與仍必要競態，不刪一般 race oracle。預估 manager/service/contract
  3 production files net -50～90，owner 不增加；非 UI/功能移除，不改已退役狀態。
  先確認 diagnostic reason 無 artifact reader，再移除舊模式專屬 reason。
- Sidebar draft 收斂：combined configure 與 settings-only 重複傳遞同一 publication generation／
  prospective model 到 recommendation、resource preview、device provider。以既有 sidebar 私有
  helper 統一這個 draft 的查詢與 collect；初始 snapshot、model dialog 次序、文案、command
  與確認行為不動。1 production file 預估 net -15，無新 owner；保留兩種現有 UI flow tests，
  加強同 draft/model/generation 的 observable request 斷言。

Next：上述 slices 已實作並有 focused characterization；shared spine、Training、Preprocess、
tests／scripts 的保留比較已逐組完成，manager/sidebar 與 scripts 的獨立結構覆核無阻擋。
先閉合 provenance 的 FIF→再次 resample 邊界與獨立覆核、manager 最後 postcheck，
再凍結 source、分段 commit 與完整候選同 head CI／必要 Windows handoff；尚非 handoff-ready。
