# XBrainLab 目前狀態

最後更新：`2026-09-22`

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
| Assistant | Local catalog以Granite 4.0 Micro 3B作recommended primary、Granite 3.3 2B作lower-memory選項；per-user settings保留上次確認的supported model，已退役selection會靜默正規化為recommended model。Strict envelope、18-action stage surface、parameter provenance、typed pending receipt infrastructure、capability、confirmation、GUI handoff與model-free walkthrough存在。 | PR #71 的exact 3B bounded baseline為36/36 positive、10/10 explicit parameter origin、5/5 missing guard、22/24 product no-action與6/7 clarification execution boundary；`desktop-source` release profile可重跑其frozen 81-case no-regression evidence，但artifact明示它不是24/24、7/7 Stable promotion或安全零容忍。 |
| MCP | Executable package、transport、CLI、capture、schema projection與tests已退役；provenance只留在Git history。 | 不是release能力；未來若要恢復，必須另開public contract、security與validation decision。 |
| Packaging | Windows launcher與source啟動方式存在。 | 沒有signed installer。 |

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

## Assistant research baseline

後續正式非 TEST 題庫已在來源移除 `ground_truth.review_status`；runner 維持原樣複製與
原始位元組指紋核對，不含匯出轉換。歷史 d0 不變，沒有重跑模型或更改判分。
Windows focused 100 tests、實際題庫的題目／答案保留核對及獨立 review 通過。
正式來源及版本見[研究規格](validation/thesis_protocol.md)；指定舊題庫時仍原樣複製，不隱式刪欄。

### 完整 DEV 起始基準（2026-09-22）

新研究方法的 initial candidate 已在 clean
`67dd8bf9155124296b0d9863f2db9a74c103cbbc` 完成五模型 × 264 題，全部 RAG on、repeat 0。
每模型 Action／Clarification／No-call 分母為 144／48／72；1,320 筆有效量測均有
完整終態、cleanup、判分、輸入與輸出證據。這是每模型最多五套 DEV 設定中的第一套，
不另計額外 baseline，也沒有執行 RAG off、VALID 或 TEST。下方歷史 B0 不改寫。

| 模型 | First macro | Final macro | P50（秒） | P95（秒） | 最大值（秒） |
| --- | ---: | ---: | ---: | ---: | ---: |
| Granite 4.0 Micro | 0.6273 | 0.6273 | 1.518 | 4.299 | 8.324 |
| Granite 3.3 2B | 0.5255 | 0.5301 | 2.151 | 5.196 | 10.839 |
| Phi-4 Mini | 0.6597 | 0.6736 | 4.405 | 11.149 | 29.439 |
| Llama 3.2 3B | 0.3171 | 0.3889 | 1.801 | 5.429 | 11.254 |
| Gemma 3 4B | 0.4884 | 0.5231 | 4.843 | 16.225 | 50.954 |

Macro 為三種決策的等權平均；不是一般逐題正確率或完整操作成功率。
等待時間含 RAG、生成、解析／驗證及格式修復，計入所有有效成功／失敗決策終態，
不含模型載入、暖機、工具執行或事後 scorer。載入／暖機及逐題成功／失敗組另列報告。
此次 selected 的 1,320 個終態皆 completed，沒有有效決策逾時；不能因此宣稱無原始失敗。
累計 charged active time 為 5,872.203 秒（約 97.9 分），包括原失敗與恢复成本，
不含使用者／診斷間隔的等待，也不是純 GPU 運算時間。

原次 Granite3.3 的 `DEV-A08-02-V2` 決策逾時，模型子程序被結束後 capture metadata
仍為 prepared，正確判為無效量測。326 筆原有效結果保持未重跑，只以同 source／環境／
題庫／配置補一筆 attempt-2，並繼續 993 個未執行案例；共保留 1,321 份 attempts。
恢復成功不證明原 native 卡住根因已修好。報告 `dev_complete` 與
`presentation-audit.selected_complete` 為 true；整體 presentation audit 仍列出唯一
superseded capture 未完成，不抹除原始失敗或把無效量測判成模型正確。

報告入口：`D:\XBrainLabRuns\d0\index.html`，內含可查詢逐題頁面、CSV、JSON、
固定 inputs、raw／manifest／journal、歷次 reports 與 launches。
報告介面提供模型比較、模型／題型／正誤交集篩選、搜尋及分頁；逐題呈現預期與
既存 observed 欄位，產品執行證據與決策分數分開。詳細統計／來源可展開，歷史失敗
警告仍可見。這是離線呈現更新，不重新判分或推論；正式研究主張不因此增加。
首頁與內頁以實驗目錄名稱、DEV 階段及模型／RAG 條件辨識同一實驗，不用「Latest report」
代稱；技術說明預設收合，頁面不列 SHA，CSV／JSON／audit 的原始指紋與驗證仍保留。
程式分工為 bounded evidence readers、統計呈現、逐題／CSV 輸出和組裝入口；
CSS／JavaScript 在 `scripts/dev/assistant_report_assets/` 以可讀原始碼維護，產出時內嵌，
不依賴 CDN。既有 presentation audit 另記錄兩個資源的 SHA-256。
介面版 `reports/20260922-123106-fd4bd418` 的 report JSON／CSV 與原版一致，
原 raw／inputs 保持不變；Windows Edge 離線雙尺寸、篩選／分頁、鍵盤與無 JS fallback
已驗證。這是自動瀏覽器證據，不代表使用者已接受設計。
`D:\XBrainLabRuns\d0-validation\final1320-audit.json` 獨立核對全部 selected 題目，
1,436 組 generation capture 的實際 bytes／hash／trace、同一 frozen scorer 與 input-audit
重播、完整分母及獨立 P50／P95 計算均一致。Scorer 重播證明紀錄一致，
不取代盲測真人 oracle 審查；精確 decision 起算 clock 未另存，不能事後重建該 timestamp。
預檢 pf2 的 66 fixtures／264 oracles 與 sm1 的 15 題五模型 smoke 不混入正式分母。

同凍結 source 的 report-only 已重建完成：11,646 個 raw／input 項目保持不變，
完整 report JSON 與 CSV bytes 一致；1,320 筆 CSV、1,323 個 HTML 頁面及 8,169 個
本機連結通過。證據在 `d0-validation/report-rebuild-verification.json`；
原成功報告 `reports/20260922-061343-96c61481` 與重建的
`reports/20260922-074043-c9a89d4b` 均保留；後續介面版另存新 reports，
不可把新 renderer 身分當成原始量測 source。

source snapshot 保存在 `D:\XBrainLabRuns\d0-validation\source-67dd8bf9.zip`，SHA-256
`8f7235d1b1cf05518f3e5af93f3e79bc5cdc2422e109e0dd65af1cd50747fbbd`；
環境／模型／語料身分由 retained manifest 保存，共享 native Windows 環境與受控模型 cache
未複製或升級。還原需同一 Git source／環境與本機 cache，不宣稱全離線安裝包。

背景喚醒原本使用 `exec resume`，因開啟的互動會話持有 writer 而失敗。
現改為單次 `codex queue`：12 項 subprocess 回歸、獨立 review、真 live-TUI smoke，
以及本次實驗完成後實際接回原會話均有證據。`d0-bg` 的原失敗保留，新的
`d0-bg-queue` 只觀察既有 recovery，不重新啟動推論。Queue receipt 只代表排入；
`d0-validation/queue-receiving-turn.json` 才核對本次相同會話的新 turn 與精確接續訊息。
本機 Codex 0.155.1 的開啟 TUI 路徑已觀察成功，不保證關閉、重啟或所有客戶端皆可喚醒。

這仍是單次 DEV initial 系統比較，不是正式排名、穩定尾延遲或產品 native GUI 驗收。
Gemma 使用已核准 NF4，其餘 BF16，不能當成同精度的純模型比較。
缺資訊澄清仍是明顯弱點：Final 正確數為 Granite4／Granite3.3 各 1/48、Llama 2/48、
Phi／Gemma 各 15/48；
決策正確也不代表 Command 已執行完成，產品 outcome 必須分開閱讀。
後续調優／VALID／TEST 仍需使用者決策，不因基準完成而自行追加。

### 正式 B0 — 共通修理後的完整 Pilot

Tag `assistant-b0-formal-20260921-926d90ea` 固定
`926d90ea80b0fa66322238d7914fde07cde26af3`，已完成同一 30 題 DEV、五模型 × RAG on/off
的 300/300 Pilot。十條件 cleanup 通過、沒有缺題／timeout／無效量測，active time
1,225.047 秒。報告在 `build/dev-artifacts/p0-926d90ea-report/index.html`；durable 目錄為
`E:\XBrainLabData\evidence\assistant-b0-formal-20260921-926d90ea`，入口是
`results/report/index.html`、`README.md`。封存含完整歷史 bundle／tracked source、環境鎖定／清單、
固定輸入、原始結果與先前診斷；6,216 個檔案逐檔校驗通過，總計 1,924,819,267 bytes。
`manifest.sha256` 本身的 SHA-256 為
`63c62e517656e2ec4c947460fa441f06455a0ad8faa5394a2bd4c2e0152dbded`。

共用 parser 現接受整份回答單一 JSON fence，保留原 schema／admission 邊界；預設只允許
初次加一次格式修復。新 Pilot 暴露並修復 scorer 對非法 typed clarification 的假陽性：
可選工具／missing fields 仍須符合既有 direct-tool、stage 與 schema 契約，不把 Host 拒絕
算成正確回答，也不新增問句內容評分。產品 owner 沒有新增；未做 prompt／RAG 調優。

| 條件（RAG off / on） | First macro | Final macro | Invalid output（任一次） |
| --- | ---: | ---: | ---: |
| Granite 4 | 0.556 / 0.611 | 0.556 / 0.611 | 0 / 0 |
| Granite 3.3 | 0.463 / 0.500 | 0.463 / 0.519 | 0 / 1 |
| Phi-4 | 0.648 / 0.685 | 0.648 / 0.685 | 0 / 0 |
| Llama 3.2 | 0.370 / 0.370 | 0.463 / 0.407 | 6 / 6 |
| Gemma 3 | 0.463 / 0.519 | 0.537 / 0.519 | 5 / 3 |

Macro 等權計算 Action／Clarification／No-call，不是完整操作成功率。300 題完整判分
重播一致、320 次生成 capture hash／trace 對照通過，每題最多兩次生成／一次修復。
Gemma 的 68 次輸出仍全帶 fence；對應輸入以精確 tokenizer／模板重渲染一致，無 optional context 丟棄。
靜態合法的外框不再造成零分，但最後仍有 off 2／on 3 題格式／typed 契約失敗。

已從新 tag 的 bundle 在全新鎖定 Windows 環境實跑 Granite 4 RAG-off 30 題：
first／final 分數、repair 次數與核對的五項 product-outcome 欄位均與原條件一致，
真 bandpass 2–35 Hz Command 與 after-state 通過，capture／input／cleanup 通過。
這不是全五模型重驗或逐 byte 軌跡一致的保證。還原的 163 個套件版本與共享環境相同，
沒有安裝共享環境另外 33 個文件／資料／開發工具；完整差異在 `environment/comparison.json`。
模型與 embedding 全檔 hash 相符；生成模型沿用 D 槽受控 cache、不複製大型權重，
各 RAG raw 目錄的 embedding junction 在封存時實體化並校驗，不冒稱零資源複本。環境還原仍依賴
既有 Windows Python、Poetry 與套件來源／cache，不是可完全離線安裝的備份。
本輪臨時 checkout／環境約 5.4 GB 已移除，可依封存 README 重建；共享環境、模型與
舊封存保留。README 提供全部／指定條件重跑指令及已驗證的路徑限制，不需留著臨時環境。

本輪採 Windows Python＋Qt offscreen，Gemma 仍用已核准 NF4、其餘四模型維持 BF16。
先前的啟動變數傳遞問題、Windows 長輸出目錄的 WinError 206，以及 `ae482c41` 的 246 題
scorer 缺口 partial 均保留，不混入新結果。短 output root 可避開已重現的目錄限制，
沒有藉本輪重寫 training filesystem。前後同時改變格式、repair budget、scorer 與 Qt 平台，
不能把耗時或分數差異歸因單一因素；單次小樣本不支撐正式排名、穩定 P95 或 Test 結論。
缺資訊時自行補參數、不應操作卻提出操作、動態 publication 下的拒絕仍會出現。
七個 unexpected-action flags 包含四次導覽、兩次被拒絕的 set-reference，以及一次經測試
driver 確認後成功清除合成 fixture 的 training history；不是七次成功的破壞性執行，
但也不能只描述成開窗問題。Clarification 正確率僅判決策／結構，不代表詢問內容切題，
不得把完整量測或可還原研究基線說成產品零錯誤、native GUI 驗收或 handoff-ready。

### B0 單一入口驗證（2026-09-21）

`baseline.cmd` 已把固定 B0 的 source 還原／檢查、選條件、真實執行和報告串接。
用法與資料夾契約由[研究規格第 5 節](validation/thesis_protocol.md) 擁有；
它只支援固定 30 DEV 題／十條件，不是正式 Development／Validation／Test 通用 runner。
入口 `78908640`（script SHA-256 `d3c8a4aac3b332915b1ab3e97e530383d1d0a141fc84b35d4399099b4f0677e5`）
載入 clean frozen `926d90ea`，沿用共享 Windows 環境與既有模型，沒有新增環境或下載。

`D:\XBrainLabRuns\b0-entry-78908640\index.html` 是本次入口驗證結果；
首輪 `reports/20260921-130913-6df16d95` 保存原始完整測量。300/300、十條件 cleanup
通過，沒有缺題／逾時／無效量測；active time 1,283.531 秒，不包含入口前置校驗和報告。
300 題 decision／product-outcome／input audit 重播一致；319 次逐題生成加十次暖機的
metadata／prompt／raw hash 及模型身分核對通過。HTML／CSV／JSON 一致，302 頁 HTML、
1,851 個相對連結通過。73 項直接相鄰 focused tests、Windows preflight、重複入口排他
及獨立邊界覆核通過。report-only 未改 raw；完成後 resume 未新增模型子程序、未改原有
case／報告。整個資料夾複製到中文／空白 Windows 路徑後，全 300 題讀回、相對連結及
重新產生報告通過；證據在結果根目錄 `recovery-verification.json`，臨時複本驗完清除。
不將這些證據稱為產品 CI／native UI handoff-ready。

這是入口工程驗證，不新增正式 repeat，也不替換上節封存分數。Gemma 本次 final macro
off/on 為 0.463/0.574，與原次不同；不可挑較高成績。固定 case／source／seed 不表示
逐次 model input 完全相同：233 題 first prompt 完全相同，另 67 題僅有 training 的匿名
subject reference／`backend_generation` 差異；只正規化這兩欄後全部相同。兩輪合計
600 個題前邊界均為空 stage、零對話／pending／active jobs，未觀察到資料或對話殘留。
這是凍結 harness 原有的執行期資訊變動，不是新入口修改題目／RAG；其影響不能全歸因於
GPU 不確定性。兩輪原始輸入與結果均保留；控制非任務資訊對正式比較的影響仍需後續決策，
不在凍結 B0 上追改 prompt、scorer 或產品 publication。

### 前期快照與原始證據（不追改）

前期 Pilot 快照保留於 tag `assistant-b0-20260921-ac8af81d`／commit
`ac8af81d87d3c88a32455dd0ce0e91996767f38a`。2026-09-21 使用者同意其不作正式 B0：
先修共用格式相容與無效重複重試，再跑相同矩陣並另凍結基線；舊 tag、封存及分數不改寫。
下列均為該前期版本的證據。DEV Pilot 使用 30 題、五模型 × RAG on/off，
共 300/300 題 recorded；10 個 condition cleanup、300 個 case boundary、prompt capture 與
input audit 全數通過，沒有 missing、timeout、無效量測或 product outcome 缺失。總 active time
為 1,876.047 秒。這是研究可行性與成本證據，不是正式模型排名、Validation／Test、穩定 P95
或產品 handoff。

| 條件 | First macro | Final macro | Invalid model output |
| --- | ---: | ---: | ---: |
| Granite 4 RAG off / on | 0.556 / 0.611 | 0.556 / 0.611 | 0 / 0 |
| Granite 3.3 RAG off / on | 0.463 / 0.500 | 0.463 / 0.519 | 0 / 1 |
| Phi-4 RAG off / on | 0.648 / 0.685 | 0.648 / 0.685 | 0 / 0 |
| Llama 3.2 RAG off / on | 0.370 / 0.370 | 0.463 / 0.407 | 6 / 6 |
| Gemma 3 RAG off / on | 0.000 / 0.000 | 0.000 / 0.000 | 30 / 30 |

表中 Invalid model output 是「任一次生成曾格式錯誤」的題數，不等於最終仍錯誤；
Granite 3.3 on 的該題已修復，Llama off/on 最終格式錯誤分別為 2／3 題。
2026-09-21 離線覆核全部 300 題：既有 scorer 的完整判分 object 與原紀錄一致，436 次
生成的 capture 雜湊／trace 對照通過。Gemma 180 次輸入以 pinned tokenizer／模板重新
渲染完全一致，2,116–3,196 tokens，沒有丟棄 optional context；全部生成含 code fence，
由產品與 scorer 共用的 strict parser 拒絕。60 題的兩次修復輸出均相同，其中 58 題輸入也
完全相同；其餘兩題僅 backend generation 更新。這支持目前格式遵循與重複修復的限制，
不能推論 Gemma 在其他系統的能力，也沒有隔離量化的因果影響。原始零分不覆寫。
同一 scorer 重播只證明紀錄一致，不取代題目／oracle 的獨立語意覆核。

本機 durable archive 位於
`E:\XBrainLabData\evidence\assistant-b0-20260921-ac8af81d`：約 1.4 GB、3,136 個檔案，
逐檔 SHA-256 驗證通過。它含完整 Git bundle／source snapshot、非 Test 題庫、環境鎖定、
原始軌跡、報表與重跑 wrapper，不含 root settings、密鑰、個人設定或封存 Test。五模型與
embedding 維持 D 槽單一受控 cache，archive 保存並實際重算其完整 hash，不複製 35 GB 權重。
從 bundle 的隔離 checkout 以全新 Windows venv 還原成功：PyTorch 三件套皆為 `+cu130`、
`pip check` 通過、非 Test prepare 重建 300 jobs 且所有 frozen identity 相符。第一次錯誤的
環境方法及 PowerShell 中文路徑失敗亦保留，不算成功證據。

後續在 `E:\XBrainLabData\evidence\assistant-b0-restore-validation-20260921` 補足實際測量：
再次從封存 bundle 還原 clean B0 與全新鎖定 Windows 環境，核對 Granite 4 的 14 個 cache
檔後，離線跑完固定 RAG-off 30 題。逐題 first／final 分數與修復次數和原 run 相同，包含
真實 bandpass 2–35 Hz command 與後端 publication；capture、input audit 及 cleanup 通過。
一題 stop-training 的產品結果因動態 publication 由原先等待確認改為阻擋，差異如實保留，
不能宣稱所有軌跡／操作終態逐字重現。此為 Windows Qt offscreen 執行，不取代 native
視覺驗收；只有單模型 RAG-off 補驗，不是全矩陣重跑，也不是完全離線安裝包。

可讀報告入口為 `E:\XBrainLabData\evidence\assistant-pilot-review-20260921\report\index.html`。
它從原始 E 槽封存重建，保留原分數與來源身分，新增分類分母、成功／失敗延遲中位數及
最大值、獨立載入／暖機成本、修復與失敗、可搜尋逐題軌跡及 Excel CSV。
呈現前重新核對 request／result／capture 雜湊；缺失不冒充模型回答。
衍生報告與診斷另存追加目錄，原 B0 封存不覆寫；報告可讀性不等於新增科學效度。

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
