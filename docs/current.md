# XBrainLab 目前狀態

最後更新：`2026-10-07`

## 一句話

XBrainLab `0.8.0` 是 Desktop GUI／Local Assistant／Saliency Refresh source baseline：使用者可由 Dataset
import/review 經 Preprocess、Epoch、Split/Training、Evaluation 到 Saliency visualization，也可用固定
local Granite透過18個核准action進入相同GUI與Command workflow。

## Current product truth

使用者匯入邊界集中於 `user_docs/import-support.md`：通用 EEG 檔案與 EEG-BIDS 是並列入口，
內嵌／外部／混合／明確無 label 均經既有 wizard。無 label 可檢視與前處理，不代表監督式
epoch/training ready。MOABB loader 轉成 EEG-BIDS 後的全清單相容性是已同意的最低目標；完整
1.5.0 inventory 的 recurring gate 目前要求 134 個代表路徑：原有 127 個加上七個新通過
轉換／實際匯入／recipe 重播的案例，另有九個授權暫緩、四個明確 blocker、零個未盤點。
每個 required entry 已綁定可攜式資料 manifest；統一路徑的同版本 fresh backend campaign 已
於 134/134 通過。
這是完整 disposition，**不是 147/147 相容能力**。目前同批通道配置／raw-epoch 相容性限制，以及
BIDS epoched/discontinuous 與仍未通過的逐項轉換／產品 blocker，
必須公開，不能透過文件把尚未完成的目標改寫為已支援。
明確無 label 的 BIDS 匯入不再強制 events.tsv；wizard 可選 `Continue without labels`，經後端
重新驗證後才確認匯入，仍阻擋監督式 epoch。原生自動流程可證明此路徑，不取代真人驗收。
BIDS 缺少 events.tsv 時亦可完整審查檔內事件與 class 後匯入並重播 recipe；不猜測 class。
外部 timestamp placement 遇到 inherited EEG metadata 明定 epoched/discontinuous 時會阻擋，
不再當成連續時間軸；新增或修改已審查的 sidecar 必須重新 preview/review。
Timestamp interval 結尾的表示誤差由 preview 與實際事件載入共用同一界線：最多一微秒，
且不超過半個 sample；不改寫來源時間、不允許 onset 落在錄製結尾或真正的 interval 越界。
BrainVision header 已計入的 signal／marker 依賴不再重複增加波形 RAM 估算；未被引用的檔案
仍計入，安全門檻與必要確認保持不變。

Import wizard 的元件先加入所屬版面再顯示；Windows 的 loading／preview 視窗在首幀繪製後
才顯露，避免 subject 選擇後與 Confirm and Import 交接時的瞬時白框。不新增固定等待，
不改資料語意、必要確認或取消政策。使用者於 2026-09-16 對 Windows source `b052fd75`
回覆「沒問題了可以準備合併」；這是所討論白框修正的局部手測接受，不代表所有資料集、
DPI 或下游流程都經此次真人驗收。後續純文件收尾不改該產品 source。

| 區域 | 目前能相信 | 邊界 |
| --- | --- | --- |
| Command spine | `ApplicationService / Command API` 是 GUI、Assistant 與 scripts 共用的產品命令入口。 | Lower-level domain tests 仍可直接使用 Study/managers；不得把它們接回產品 UI mutation。 |
| Data import | Formal BIDS subject selection、reviewed import、external/internal label mapping、recipe與多格式 loader存在；loading以穩定 phase/activity 呈現，不把各 command 的局部計數當整體百分比。 | 不是 full BIDS validator，也不能外推到所有資料集與 proprietary formats。 |
| Desktop presentation | Blocking alert／confirmation 使用共用 XBrainLab modal；confirmation 的 Cancel 是 Enter／Escape 安全預設，raw `QMessageBox` 不再是 production UI surface。Detached Evaluation render 不呈現 user-owned Cancel action。 | Inline validation、loading、operation status 與 canvas error 仍留在 workflow context；自動 artifact 不取代 Windows native keyboard、DPI 與 OpenGL 驗收。 |
| Preprocess / Epoch | Filtering、resample、rereference、normalize、channel selection與reviewed epoch flow存在，長工作有 owned lifecycle。 | Protocol choice與科學正確性仍由使用者負責。 |
| Split / Training | Split preview、training settings、fold/repeat plans與training history存在。Full Test 支援 Trial／跨 subject 同名 Session／Subject，Individual Test 支援 Trial／Session；Validation 為 Disable 或該 training mode 可用的任一 unit，且可與 Test 混用。非 CV 用 Ratio／Number／Manual，CV Test 為 exact KFold 並可搭配 Disable／Ratio／Number Validation。Preview receipt 與 Train 以同一 allocation/audit materialize，receipt 不一致或無可行 partition 會拒絕啟動；每次 Start Training有獨立 round identity。 | 分配是確定性且 bounded 的可行性搜尋，不是完整 solver；不保證任意資料集、科學獨立性、class balance 或模型品質。Recommendation不是AutoML或最佳參數保證。 |
| Model catalog | Pinned Braindecode 1.6.1提供61個可搜尋contracts，其中54個符合目前classification workflow而可選；provider失效時改列distinct `legacy.braindecode.*` recovery IDs。Model Selection使用catalog reviewed defaults。 | 不可選contracts會顯示license、task或resource reason；桌面UI不提供model constructor調參；upstream與legacy禁止silent fallback，catalog execution不代表科學品質。 |
| Evaluation | Individual fold/run支援Train、Validation、Test；Evaluation／Visualization選單只列完成的run（含正常Early Stop），不列中途停止的run，保留原始編號與歷史；cross-fold Summary只pool同一training round的disjoint Test masks。已完成結果的讀取綁定所選結果與trainer／split來源，不因其他fold的訓練進度失效，也不計算saliency producer SHA。 | 真正的來源或所選結果替換仍拒絕過期讀取；完成訓練但未計算saliency的run仍可選取Compute；`All Folds`的Split只有Test是刻意的統計邊界。 |
| Saliency | 桌面Compute／Recompute只執行Settings選定的方法，一次涵蓋目前訓練結果中所有subject的已完成fold／run，排除未完成者；Fold／Run／Method選單只控制顯示。未選的相容既有方法直接保留，不加入重算；所選方法僅保留最新成功結果，整批成功才發布。沿用exact Fold／Evaluation-admitted Fold Set publication；尚未計算者顯示Compute要求，舊結果可刻意回看；單一class selector可切all-class比較與single-class細看，3D控制使用epoch-relative time並在重複render維持單一orientation widget。 | 不代表attribution具科學有效性或腦內source localisation，不把epoch time冒充已審查event marker，也不保證所有模型梯度相容。 |
| Assistant | Local catalog以Granite 4.0 Micro 3B作recommended primary、Granite 3.3 2B作lower-memory選項；per-user settings保留上次確認的supported model，已退役selection會靜默正規化為recommended model。18-action stage surface、parameter provenance、capability、confirmation及GUI handoff存在；完整單輪兩欄契約見下節，不保存對話草稿。 | 模型仍可能漏執行、提錯工具或誤切panel；工程驗證與已知限制見下節，不宣稱Stable或安全零容忍。 |
| MCP | Executable package、transport、CLI、capture、schema projection與tests已退役；provenance只留在Git history。 | 不是release能力；未來若要恢復，必須另開public contract、security與validation decision。 |
| Packaging | Windows source bootstrap 經確認後準備生成模型與固定版本 RAG embedding，離線檢索驗證通過才完成／啟動；重跑重用完整 cache。入口與路徑見[本機環境](developer/local-setup.md)。 | 沒有 signed installer；流程回歸與既有 cache 離線驗證不代表全新 Windows 整機安裝已實測。 |

## Evidence truth

- Current product baseline永遠是Git的`main`；branch、SHA與dirty state從Git取得，不寫死在文件。
- Generated evidence只寫入ignored `build/dev-artifacts/`或
  `build/handoff-evidence/<full-SHA>/`；這些是可丟棄的當次輸出，不是durable storage。
  `artifacts/`不保存current evidence。
- Offscreen Qt、dashboard與自動journey是工程證據，不取代Windows真人操作。
- Visible UI source變更會產生exact-source default-scale candidate，並和
  `tests/baselines/ui/` approved references做fail-closed比對。UI layout/theme/font/dialog路徑另由
  Windows Qt platform在100/125/150%跑app-polish geometry/pixel contract；它仍不取代真人Windows
  DPI、多螢幕或remote-desktop acceptance。
- 任何產品行為變更都必須由使用者手測通過並明確同意merge；product source變更後須重新批准。
- Repo-root `settings.json`是本機設定，不屬於release tree。

## Assistant product boundary

Assistant Settings 提供需確認的 `Restart Assistant`：清除對話並以已保存設定重載模型，
保留 EEG 與已提交後端工作、不自動重送要求；完整清理後才建立新 runtime，READY 才報成功。
這是恢復入口，不代表已定位或修復偶發的 Assistant 匯入卡住；已隨 PR #158 驗收合併。

模型只輸出恰好兩欄 `tool_name / parameters`。一個既有工具名表示完整單一操作；
`respond_to_user` 的 parameters 只能含非空 message，是非執行回答標記，不是第 19 個工具。
不接受舊五欄／三欄格式。每次要求獨立，不保存或合併跨輪參數；缺值時請使用者重新
提供完整要求，裸值與「照剛才」不能借用先前操作參數。

模型輸入不附先前 user／Assistant 對話；畫面聊天與診斷紀錄仍保留。模型取得當輪原文、
必要後端狀態／可用工具／規則及可選 RAG 參考。Host 不猜自然語言意圖、不排序 bandpass
值，也不以歷史、RAG 或預設補值。Bandpass／notch／resample 數值由模型解析，Host 不要求
相同阿拉伯數字出現在原句；仍驗完整 schema／range 與後端 admission。
Reference／normalization 方法來源仍核對當輪原文，RAG 示範的來源檢查保持不變。
來源匹配不證明模型理解正確。

確認與 GUI handoff 保留 typed identity、取消與 freshness 邊界。停止訓練確認綁定原本的
training run；同場進度更新不使確認失效，換 run、已結束或已停止中仍拒絕，實際執行前
再次核對。其他命令的 publication freshness 規則不變。
格式錯誤含多個完整 JSON 物件最多共用一次修復；原始物件全部不執行、不抽取第一個。
修復後仍須通過既有驗證；使用者真正要求多項操作時，模型仍應請其選一件而非部分執行。
完整契約見 [Agent target](target/agent.md)，責任分工見 [Agent 架構](architecture/agent.md)。

產品支援完整、單一英文要求，不支援複合需求或聊天歷史補值。已接受版本仍有漏執行、
誤切 panel 及不可用工具提案等已知模型限制；Host 驗證與合法 JSON 不等於工具決策正確。
不宣稱任意要求可靠、Stable promotion、安全零容忍或自然語言回答品質已通過。
現行工程案例、真模型／GUI 證據要求及歷史證據的適用限制由
[驗證契約](validation/README.md) 擁有，不用論文分數替代產品 gate。

### RAG 部件邊界

RAG 在已發布 action 及合法 response 示範內檢索，不先以手寫語句分流。
語料為 161 筆英文單輪示範，使用兩欄工具回覆；缺值示範要求重新提供完整要求，不接受
prior_turn。固定 MiniLM、獨立 dense／BM25 召回及等權 RRF 融合，最多三例。
索引 schema 為 6，語料 hash 由 `RAGConfig` 固定，舊索引不可混用。
最終 prompt 依同一份當前 publication 重新確認範例資格，只加入完整範例；
不擴大工具、權限、confirmation 或參數來源。檢索准入與模型受益分開驗證，
不能以召回成功或語料數量宣稱產品可靠。

### 產品與研究封存

產品 main 只維護實際產品及必要工程驗證。研究候選、歷史提示、DEV／VALID／TEST 排程、
評分與報表、原始輸入輸出由研究封存保存；產品不提供研究重跑入口，也不回寫封存版本。
研究資料位置與證據界線見 [驗證契約](validation/README.md#research-archive-boundary)。
研究期間修好的實際產品缺陷仍保留，後續產品重構不改變論文受測版本。

## Dataset storage boundary

`XBRAINLAB_DATA_DIR/datasets/`是唯一central local hierarchy，分為source、bids、public-fixtures、
manifests與quarantine。這台開發機目前使用
`E:\XBrainLabData\datasets`；134 個代表性 BIDS entry 現為 `datasets/bids/<dataset-storage-id>`
的直接子目錄，12,434 個綁定輸入在同磁碟整理後維持內容雜湊，並由 fresh 134/134 backend
campaign 重播。2026-09-16 後續逐檔比對完成原 23 個隔離目錄的處置：17 份完全重複、3 份
被保留更多通道的正式版本取代；另 3 份中的 26 筆獨有 Brain Invaders recordings 通過逐筆
匯入／波形／事件／recipe 重播後加入正式目錄，舊副本已清除。正式区共 1,205 筆 retained
recordings，隔離資料單元為零。Clean product source `3a2c65aa` 的逐筆驗證已通過 1,205/1,205，
包含波形／事件讀回與 fresh-service recipe 重播，這仍是原 source 的 backend 基線，不改標新 SHA。
在 clean `b7cd1206`，Windows 正常 GUI 已完成全部 134 個正式根目錄／1,205 筆錄製：133 個
一般完整選取加上獲批准較長觀察的 Thielen2021，逐根核對完整檔案集合、畫面 publication、
事件／標籤讀回。Thielen 十筆／378,000 事件的畫面完成為 214.688 秒，含讀回共 217.703 秒；
原 150 秒診斷失敗保持保留，不能宣稱符合該期限或一般延遲 SLA。19 個多受試者預設選取、
21 個內嵌標籤切換路徑、8 個 native recovery／標籤回歸案例與同視窗連續兩次匯入亦通過。
BIDS 外部標籤切換內部事件時重用既有 Refresh label preview，刷新後仍須明確審查類別；
刷新前不把外部欄位冒充內部事件。無標籤匯入返回 Match Labels 仍能正常繼續，不強迫刷新。
既有 UI 類別命名會把 `Target` 整理成 `target`、`left_leg` 整理成 `left leg`；驗證保留明確
名稱對照，不把逐字不同誤判為事件遺失。原診斷失敗及各版 driver 雜湊仍保留。
同一 `b7cd1206` CI／docs 全部適用項目成功。134/134 recurring representatives 的最近執行
source 是 `751edfe0`；到 `b7cd1206` 僅有 tests/docs 改動。前述 `3a2c65aa` 基線到候選的
backend、scripts 與依賴未變；不重標歷史證據。後續文件收尾不改產品或測試內容。
這支持此機已保留資料、既有 wizard 與明確標籤審查路徑，不代表任意 BIDS、完整來源 cohort、
所有 GUI 操作、訓練／科學認證；自動證據本身也不等於真人驗收。
使用者於 2026-09-16 回報指定 Windows 候選 `1a0ffb0c` 手測完成並明確批准合併，
[PR #141](https://github.com/hxin-an/XBrainLab/pull/141) 已合併為 `2ae10927`。
本次手測接受範圍為所討論的匯入完成／資料列表與 Data Summary、開始前處理之前的流程；
使用者未列舉逐資料集或逐操作清單，不宣稱真人逐一測完 134 個資料集或所有下游流程。
候選 `1a0ffb0c` 的產品、腳本、測試與依賴與 `b7cd1206` 相同，僅文件收尾不同。
逐檔刪除、替代位置、差異 metadata 與 promotion 證據在 `evidence/retained-import-20260916`。
位置入口為 `datasets/manifests/import-locations-v3/README.md`；來源對照為
`datasets/manifests/source-locations-v2-c84e8fb0cc29.json`。原始 source 與歷史 evidence 的內容
核對／位置映射仍以 migration manifest 與 completion receipt 為準；這些保留內容不因代表路徑
通過而自動取得刪除授權。
Import dialog 只把設定的 data root 當起始位置，仍可選外部路徑。
Repo `build/`是可重建的當次 artifact 位置，不是 durable dataset authority；本機需長期保留的
campaign 已明確發布至 E 槽 evidence。任何其他副本或歷史資料仍須另經精確清理授權才能移除。

## Release boundary

`v0.8.0`只宣稱經使用者workflow手測、strict host guards與CI保護的Desktop GUI／Local Assistant／
Saliency Refresh source baseline；Assistant可包含明列且由使用者接受的bounded model limitations，不等於
Stable promotion。不宣稱signed installer、安全零容忍、scientific quality、任意dataset或模型全面支援
或產品1.0。
