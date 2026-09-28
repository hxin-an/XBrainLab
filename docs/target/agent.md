# XBrainLab Agent 目標

最後更新：`2026-09-28`

這份文件是XBrainLab Assistant產品目標的唯一權威。Runtime inventory、tests與歷史artifact
只描述實作或證據，不反推產品契約。[目前架構](../architecture/agent.md)描述source，
[Now](../planning/now.md)管理施工，[驗證契約](../validation/README.md)管理candidate gates。

## 已批准：完整單輪操作基線 { #agent-baseline-design-discussion }

2026-09-28使用者確認以完整單輪操作取代跨輪草稿能力，建立可固化進Development的
可靠基線。每次普通要求只處理一個完整操作，執行參數只取本次明確要求；後端既有設定
仍由其工具契約擁有，聊天歷史／RAG不能提供缺失參數。純說明正常回答；GUI工具完整
要求是指定開窗，不必預先填入dialog全部選項。

本輪只支援英文輸入與英文回答，不納入中文、多語或翻譯適配。上下文品質必須同時
檢查規則一致性、當前要求與參考的可辨識性，以及目標小模型實際能否遵守；獨立 reviewer
判斷清楚不代替模型行為證據。人工挑選示範只供根因診斷，不是產品檢索能力或正式成績。

2026-09-28 後續批准一個上下文／語料適配候選：先分清是否要求執行，再判斷參數是否
完整；缺值要指出缺漏並請完整重述，明確禁止則確認不操作，不因文字含完整數值而執行。
純說明含數值也不是操作授權。模型輸入中回答與操作須同樣清楚；規則集中、工具/schema
沿用backend真實投影，RAG示範與當輪要求分開。此為呈現假設，不新增Host自然語言判斷。
語料用清楚的英文完整／缺值／部分值／禁止／說明對照，保留正例，不以錯誤呼叫作示範。
維持既有BM25＋dense／RRF及固定參數；准入／來源保護不因簡化而移除。

本輪不增加功能，不以堆範例／逐題例外或候選調優競賽掩蓋基本能力缺陷；RAG須有實際
模型受益證據，不能以檢索接線完成代替。固定互通後只允許有具體根因的一次有界呈現
修理；仍不成立時依Now提出決策，不擅自放寬gate或無限消耗模型額度。

| 責任 | 核准界線 |
| --- | --- |
| 模型 | 理解當輪要求，回答、詢問缺漏或提出一個完整操作；辨認操作、否定與參數。 |
| Agent程式 | 準備一致輸入，嚴格解析與驗證，管理確認、取消、執行交接；不保存操作草稿。 |
| 產品後端 | 沿用ApplicationService／Command擁有狀態、capability、科學限制與真實執行結果。 |
| RAG | 提供參考示範，不決定權限、不供給當輪缺值、不充當intent router。 |

不增加第二模型、自然語言Host router、readiness owner或工作佇列。模型提案不因為是
JSON就變成可信事實；schema與來源通過不證明語意正確或已准許執行。

### 單輪理解、缺值與生命週期 { #unified-clarification }

缺值時指出缺少什麼，請使用者重新提供完整要求，回答後結束回合；不保存、合併或
更正先前操作的參數。下一輪裸數字、指涉更正或「照剛才」不能延續舊操作；
完整重述才是新獨立要求。一般文字仍交同一模型路徑，不由Host辨認bare值或猜意圖。

例如「bandpass，下限7 Hz」只能得到請重新提供完整要求的回答；
其後「30 Hz」不能借用7執行，「Apply a bandpass filter from 7 to 30 Hz」才是完整新要求。
資訊問題與禁止操作不執行；混合說明＋操作或多個操作先請使用者選一件，不部分執行。

移除的是對話草稿，不是confirmation、GUI handoff或training背景工作。既有確認／取消
按鈕仍以typed回覆處理，按request identity消費一次，執行前重查publication；
生成失敗、Stop、New Chat、Close與取消後不得恢復舊批准或自動重跑。
取消Assistant回合不等於停止背景training；停止工作沿用既有工具及真實backend結果。

### 單輪模型wire契約 { #agent-m0-contract }

模型回覆恰好是`{tool_name, parameters}`，沒有其他root欄位或舊格式alias。

| 欄位 | 契約 |
| --- | --- |
| `tool_name` | 一個當次可呼叫的既有工具名；或非執行回答標記`respond_to_user`。 |
| `parameters` | 工具的完整實參object；`respond_to_user`時恰好含非空字串`message`。 |

`respond_to_user`不是第19個工具，不進executor；缺值回答不是等待補值state。
移除decision／mode／changes／source_turn／quote、RequestUpdate與參數草稿DTO，
不維護兩套runtime解析或將新契約轉入舊receipt。正常工具的required/type/enum/range仍
由既有validator與backend擁有；五個direct工具來源只核對本輪原文。
非direct工具遵守其既有參數契約，不強迫enum字面值出現在使用者句子。
來源匹配不是intent／否定證明，不用Host語意救援把模型錯答改判成功。

### 固定資訊、動態狀態與context budget

固定資訊只含角色／能力範圍、回答／缺值／操作規則與工具結果的正確理解；
工具用途與參數以既有定義投影，不再手寫第二份catalogue或塞入EEG教科書、
完整選項清單及具體預設值。開窗不等於完成、啟動不等於工作完成；狀態不是使用者授權。

動態資訊只由同一份最新backend publication投影目前stage、必要狀態及操作／阻擋原因，
不建立Agent readiness或背景工作truth。完整recording／subject／channel清單、
歷史filter值、逐epoch紀錄、結果與路徑不預設全量附上；不同recording不能壓成虛構單值，
未知不能以零／預設冒充已知。細節查詢不是本輪重點，不新增query工具或第二LLM路由。
有可靠資訊才回答，缺來源時明示並依真實介面引導，不猜資料或介面位置。

模型必要輸入為精簡policy、當次工具／必要state、當輪完整原文；另附放得下的RAG。
不傳先前user／Assistant對話、累積參數或逐輪摘要；畫面聊天與診斷紀錄仍保留。
此無歷史投影由使用者於2026-09-28明確核准；指涉先前回答不屬可依歷史解答的能力。
以選定模型實際tokenizer與chat template計數，
輸入加預留輸出不得超過catalog runtime context；產品上限8,192 tokens不因本契約擴大。
先移除optional notes，RAG只能完整放入或整筆略過；必要state、否定／條件與
current user不能靜默截斷。必要內容仍超限便零推論、可見拒絕，請縮短完整要求或
New Chat後重述。不新增摘要模型、不承諾無限歷史；詳細projection依下節契約。

### RAG內容與呈現

RAG是操作／正確不操作的短英文decision demonstrations，不是EEG知識庫或必需規則來源。
正常零命中不能使工具契約、缺值規則或backend資格缺席。語料涵蓋完整單一操作、
缺值／部分值需完整重述、操作種類不明、純詢問、明確禁止與混合要求先選一件。
不複製評測原句、不把錯誤tool call當示範答案，不增加跨輪補值／更正示範。

每筆是獨立`input / expected_proposal`；提案符合兩欄wire，操作通過完整schema及
本筆input來源驗證，不接受prior_turn或宣稱已驗證的serialized pending。範例永遠是
untrusted參考，不是當輪參數、capability或confirmation授權；只能整筆打包，
若source／proposal被sanitization或限長改變則整筆略過，不能提供失真的可執行示範。

### 雙路獨立召回與RRF融合 { #rag-hybrid-design }

固定一個有界候選，不加新模型／reranker、query rewrite、keyword router或逐題例外：

1. Query只取當輪user文字，不加入先前要求、Assistant問句、tool schema、答案或整份state。
   搜尋先限制同一eligible corpus：當次callable工具示範及合法respond_to_user示範。
2. Dense與BM25獨立准入，每路最多10筆；dense cosine門檻0.7。BM25須至少命中2個
   不同token，且max(query-IDF覆蓋, document-IDF覆蓋)>=0.5。覆蓋各為matched unique
   token的IDF總和除以該側全部unique token的IDF總和，同一corpus IDF，query OOV以df=0
   計入分母；重複詞不增加覆蓋。Eligibility與覆蓋先篩選，再按raw BM25取top10。
3. 一路通過即可入聯集，不由dense否決sparse；各路准入後從rank1重排，只有准入候選
   貢獻該路分數。聯集按stable ID去重、等權RRF，rank constant=60；同分按stable ID排序。
   不把raw BM25、per-query min-max或RRF當相關性概率，也不另設假信心門檻。
4. 按融合順序取能完整放入預算的示範，最多3筆，允許零例。Dense-only真正省略BM25
   建置／查詢；hybrid任一路故障明示degraded／failure，不偽裝零命中或silent fallback。
5. 固定v5的10＋10單輪工程query／相關ID標註後才量測：最終送例須在預定相關集合，
   無關題零例，指定sparse正例須補回；分路top10錯候選另列診斷，不混成最終模型輸入。
   Topic relevance允許同主題操作／說明／禁止對比，不等於decision equivalence。
   v5保留v4全部query／原標註與required IDs，只補新語料的同主題示範ID。
   v4只從原v3的24題移除4個跨輪案例；v1 raw-cutoff、
   v2 query-only覆蓋與v3原fixture／失敗報告保留歷史身分，不改寫成成功。
6. 短doc可能匹配帶無關附加詞的query；此對稱重疊與固定0.5不是未知輸入保證。
   驗證失敗如實保留，不調到全空、不加逐題例外或dense全域否決，也不反覆調詞追分。
   語料／索引／規則／fixture均以版本與hash識別，變更不能沿用舊准入證據。

10＋10是有界工程核對，不是論文holdout或統計代表性。參數已固定但不是永久最佳值；
准入通過與模型受益必須分開。Token分配服從完整template實測，不藉此改context或研究輸出上限。

### RAG本輪須有模型受益證據 { #rag-benefit-acceptance }

檢索正確、沒有破壞既有功能，都是必要但不充分的條件；本輪RAG的outcome包括對模型
有實際幫助。必要調整屬於本輪，不移交正式Development，也不先保證目前RRF提案必然有效。

具體驗證建議：整體Agent契約與上下文接好後，在同一source、模型／revision、生成設定、
資料狀態及user要求下做少量RAG開／關配對；只改是否提供RAG參考，不連帶更換prompt
規則或工具。事先固定代表性情境，包含預期RAG能補足的需求、原本已會的操作及容易被
誤導的不操作／追問情境；不用正式Validation／Test題、不複製評測原句進語料。

- 看raw模型的操作選擇、參數或追問是否有可重現的改善，並核對實際產品結果；Host擋錯、
  命中更多例子或輸出更長，不能代替模型受益。基線已強時，不要求任意總分漲幅，但也
  不能因「天花板效應」就免除受益證據。
- 一併列出退步與額外等待／token成本，不只挑改善案例；新增嚴重誤操作或系統性誤導
  不能用其他題加分抵銷。小範圍配對只支持已測情境，不宣稱統計顯著或所有模型都受益。
- 未觀察到幫助時，先依完整輸入／檢索／raw輸出定位原因，再做必要修正；不機械掃描
  參數組合、反覆刷分或為個別題堆特例。若仍無支持證據，明示RAG尚未達本輪要求，
  不冒稱完成、不默默刪掉RAG，也不無限消耗額度；需要改變方案／資源時提出具體決策。

通過後固定語料、查詢組裝、准入／融合參數與範例呈現的版本；正式Development不再把
它們當調參軸。日後研究若要改RAG，屬另行批准的新基線，而非本輪未完工作順延。

### 完整模型輸入的獨立覆核

使用者要求獨立subagent審查候選經組裝、限長、role處理及chat template後的實際完整
prompt，不能只看system、RAG或作者重寫的示意。核對messages、token數、輸出預算、
model／tokenizer／template／decoding設定與source身分；capture沿用受控工程位置，
不擴大收集真實聊天／EEG資料或新增審查平台。

- 覆蓋完整／缺值／否定／多步／資訊、GUI、狀態變動、RAG零命中／不可用與超限，
  有format repair時也看其實際輸入。超限須證明未推論，不偽造成功capture。
- Reviewer先只看模型可見內容，檢查當輪要求、參數與資格是否清楚，規則是否矛盾或重複，
  範例帶值、過期歷史與截斷是否誤導，再對照契約與後端事實；不能先用標準答案補足缺口。
- 以具體capture／片段區分資訊缺漏、呈現與模型能力，修正後覆核受影響及相鄰邊界。
  按輸入身分去重並列明覆蓋，不把happy path說成全部context已審。
- 標準是產品小模型理解負擔，不是強reviewer能否推知答案；塞得下window不等於可靠。
  不堆更多警告／例外掩蓋問題，Reviewer不成為產品第二模型或語意攔截器。

此覆核支持輸入清晰度，不證明模型準確率；仍須真模型raw輸出、Host驗證與產品結果。
主agent驗收實際diff及證據，施工／交付進度與具體gate不在本頁另建清單。

## 角色與邊界

XBrainLab Assistant 是 app 內的 local-only EEG workflow operator。它負責理解本回合需求、從
backend 發布的候選動作中選一個、通過驗證後交給既有 ApplicationService 或 UI surface，並顯示
一個可信 terminal result。

它不是一般檔案瀏覽器、外部 coding assistant、第二套 workflow engine 或會自動跑完整 pipeline 的
autonomous planner。

產品不變量：

- local model 與 revision 必須精確固定；缺少時 fail closed，不 silent fallback。
- ApplicationService、capability policy 與 application publication 是唯一 workflow truth。
- 每個user turn最多一個操作；`respond_to_user`不執行工具。成功、blocked、取消或失敗都結束 turn。
- GUI decision 由既有 dialog／panel 的使用者操作完成；模型不代填高影響選項。
- tool result 直接使用 trusted backend／UI public result，不再交給 Granite 改寫。

### 單次決策的需求邊界（2026-09-28 確認）

- 明確、可用且參數完整的單一操作：提出該 exact action，沿用後端驗證與 confirmation。
- 純概念／使用方式詢問或明確禁止操作：使用`respond_to_user`，不產生操作。
- 操作目前不可用：說明同一 publication 的真正 blocker，不代做前置或替代操作。
- 「處理資料」「做 filter」等尚未確定操作種類的要求：先詢問，不自行選工具。
- 種類已確定但必要參數不足：說明缺少值並請重新提供完整要求；不保存已提供值、
  不從範例複製數值，也不擴張其他GUI tools的參數契約。
- 同一要求包含概念解釋＋操作，或多個操作：請使用者選擇先做哪一件，本回合不部分執行。
  操作後的 trusted terminal 訊息不是第二次模型解釋，也不啟動 autonomous continuation。

這是批准目標，不代表目前 prompt／corpus／scorer 已全部對齊。遷移須同時處理範例與
驗收預期，保留原題與歷史 raw／分數身分；不能把「只操作」評為已完成解釋＋操作，
也不能把更正評分規則宣稱模型能力提升。

## Local model selection contract

Assistant Settings與runtime共用`XBrainLab/llm/core/model_catalog.py`的單一allow-list：

| Role | Exact model | Revision | Visible positioning |
| --- | --- | --- | --- |
| primary | `ibm-granite/granite-4.0-micro` | `56111ae135df9c53a78c99028e7bc24035a9e979` | Granite 4.0 Micro 3B，recommended default |
| lower-memory | `ibm-granite/granite-3.3-2b-instruct` | `707f574c62054322f6b5b04b6d075f0a8f05e0f0` | Granite 3.3 2B，較低資源選項 |

新安裝、缺漏model choice或retired selection解析至primary；已儲存且仍在allow-list的2B choice保持原值。
Settings可完成exact model的install／status／activate／delete與generation settings，但不自行判斷cache或
runtime readiness。選定model若缺少、不完整、OOM或載入失敗，既有catalog／download lifecycle／runtime
owner必須fail closed並顯示對應狀態，不得silent fallback到另一個model。Primary變更不授權改寫現有使用者
的root `settings.json`，也不把downloaded-but-unsupported cache冒充可選model。

## Authority layers

- **Runtime compatibility inventory**：source 中可註冊的 implementation；只支援 migration、debug 或
  legacy callers。
- **Current model-facing projection**：目前 product prompt 實際發布的集合；由
  [current architecture](../architecture/agent.md) 描述。
- **Approved target surface**：只由下方 intent ledger 的 18 個核准工具組成。

名稱、membership、參數、execution kind、owner、confirmation 或 terminal result 任一改變，都是
public product contract decision；必須先更新本文件並取得使用者確認。

## Target intent ledger

### GUI completion tools

下列七個工具對模型都是零參數。Tool 只請求既有 GUI；真正選擇、preview、apply、confirmation 與
cancel 都由該 GUI owner 完成。`opened`／`accepted` 不是成功，只有 correlated
`completed`、`cancelled`、`blocked`、`unavailable` 或 `failed` 能結束 turn。

| Tool | Published stage | Existing owner／authoritative side effect | Terminal evidence |
| --- | --- | --- | --- |
| `import_eeg_data` | `empty` | Data Import chooser、Data Interpretation lifecycle、reviewed ApplicationService apply | import applied、cancelled、blocked 或 failed |
| `select_channels` | `data_loaded` | Dataset Channel Selection dialog；`PreprocessCommand(SELECT_CHANNELS)` | selected channels applied、cancelled、blocked 或 failed |
| `set_montage` | `data_loaded`、`preprocessed` | Montage Settings；`ApplyMontageCommand` | montage applied、cancelled、blocked 或 failed |
| `create_epochs` | `data_loaded`、`preprocessed` | Epoch Settings；`CreateEpochCommand` | epochs created、cancelled、blocked 或 failed |
| `configure_dataset_split` | `epoch_ready`、`dataset_ready`、`trained` | Dataset Split dialog；`SaveDatasetSplitCommand` | split saved／datasets generated、cancelled、blocked 或 failed |
| `select_model` | `epoch_ready`、`dataset_ready`、`trained` | Model Selection dialog；existing ConfigureTraining command owner | model selection saved、cancelled、blocked 或 failed |
| `configure_training` | `epoch_ready`、`dataset_ready`、`trained` | Training Settings dialog；existing ConfigureTraining command owner | training settings saved、cancelled、blocked 或 failed |

七個 names 共用既有 typed UI handoff registry 與一個 thin adapter。Internal route identity、underlying
command 與 decision fields 由 trusted action contract 固定，不是模型參數，也不建立新 UI owner。
新的 class loss weighting 與 validation early stopping 仍由 Training Settings 以人類決策完成；
`configure_training` 對模型維持零參數，不公開 weighting mode、class multipliers、patience 或
`min_delta` schema。完整 contract 見 [Training target](training.md)。

`import_eeg_data` 的 action identity 完全由模型 proposal 與 current publication 決定。它是 zero-parameter
GUI handoff，Host 不讀 latest user text 判斷 import、肯定／否定、英文動詞或 object grammar，也不以文字
heuristic 取代模型的選擇。publication、schema、capability、confirmation 與既有 UI handoff 仍是唯一 trusted
boundary；模型把資訊或否定 request 誤判為 import 必須如實記為 model/product accuracy failure，不能由 Host
semantic rescue 隱藏。

### Direct preprocessing tools

下列五個工具直接走既有 Preprocess command owner。Raw data 保留，因此不加 Assistant confirmation；
缺少必要參數時用`respond_to_user`請重新提供完整要求，不保存值、不套default、不改走GUI或standard bundle。
Backend 仍負責 Nyquist、range、state、resource 與 scientific precondition。

| Tool | Required parameters | Published stage | Terminal |
| --- | --- | --- | --- |
| `apply_bandpass_filter` | `low_freq: number`、`high_freq: number` | `data_loaded`、`preprocessed` | applied 或 typed blocked／failed result |
| `apply_notch_filter` | `freq: number` | `data_loaded`、`preprocessed` | applied 或 typed blocked／failed result |
| `resample_data` | `rate: number` | `data_loaded`、`preprocessed` | applied 或 typed blocked／failed result |
| `set_reference` | `method: string`，必須符合 backend-supported contract | `data_loaded`、`preprocessed` | applied 或 typed blocked／failed result |
| `normalize_data` | `method: "z-score" \| "min-max"` | `data_loaded`、`preprocessed` | applied 或 typed blocked／failed result |

Notch 的 schema、published stages 與 DSP operation 不因 sampling-rate precondition 改變。既有
preprocess command owner 必須在 MNE prepare 前，從本次 source data 的最低可靠 sampling rate 檢查
`freq < sfreq / 2`；違反時回 typed precondition，包含 requested frequency、sampling rate、Nyquist 與
可採取的下一步。若 sampling rate 無法可靠取得，維持既有 execution，不猜測阻擋。若資料已 resample，
訊息可指示使用者 reset → notch → resample；Assistant 不自動重排或套用這些動作。

### Direct-preprocess 單輪要求

依[單輪理解邊界](#unified-clarification)與[模型契約](#agent-m0-contract)，五個direct工具
只從本輪原文驗證完整實參。Host不得用歷史、RAG、預設或舊receipt補齊；bare值不是
沿用上一操作的授權。值來源核對不取代模型對操作、否定或多步要求的理解。
舊Host補值、bandpass排序、草稿與跨輪來源DTO退出產品路徑；原實驗保留歷史版本身分。

### Lifecycle tools

| Tool | Parameters | Published stage | Confirmation／terminal |
| --- | --- | --- | --- |
| `start_training` | none | `epoch_ready`、`dataset_ready`、`trained` | backend 缺 setup 時 blocked；沿用 start confirmation，後端確認成功啟動後以「已啟動」結束本回合，不等待整場訓練完成 |
| `stop_training` | none | `training` | 只接受使用者明確要求；依後端結果區分「已要求停止」與「已停止」，不可將前者宣稱為工作已結束 |
| `reset_preprocessing` | none | raw data 存在且未 training | 使用既有 destructive confirmation；保留 raw、清除 derived state |
| `clear_training_history` | none | history 存在且未 training | 使用既有 destructive confirmation；清除 runs/history，不清除可重用 setup |

Confirmation、resource receipt、generation token與 filesystem path 都由 trusted product code處理，
模型不得輸出或保存。

2026-09-28討論確認：保留training非同步，取代先前start_training等待real training terminal
才結束Assistant回合的文字。啟動成功須由後端確認，不把送出／排程當啟動成功，更不等於
訓練完成。回合結束後可繼續對話，後續決策取fresh publication；重複啟動與不相容操作仍由
既有capability policy阻擋。訓練完成／失敗由既有後端與介面回報，不重新呼叫模型、不自動
接下一操作；Agent不另存背景工作truth。此契約不擴張至compute_saliency或其他工具，
也不表示已完成所有啟動／停止／背景 terminal 的實機驗收。

### Owned analysis action

`compute_saliency`是唯一可由Assistant提出的analysis execution tool：

- 參數固定為空object，只在`trained`stage發布。
- 一律先使用既有Assistant confirmation card；取消後不得執行或continuation。
- 批准後開啟Visualization的Saliency Map，使用該panel當下合法的completed run、method與settings；
  模型不選擇也不保存這些值。
- 執行仍由既有VisualizationPanel、ApplicationService／AnalysisService與resource confirmation擁有；
  Assistant adapter不建立第二個command、readiness或operation owner。
- 只有同一owned operation id的`completed`、`cancelled`、`blocked`或`failed`能結束turn；opened、
  button clicked、scheduled或其他operation terminal都不是成功。
- 沒有合法completed run、selection stale或已有saliency operation時blocked，不silent fallback或重複啟動。

### Navigation

`switch_panel` 是唯一 navigation tool：

- `panel_name` 必須是 `dataset`、`preprocess`、`training`、`evaluation` 或 `visualization`。
- `view_mode` 只允許搭配 `visualization`，值為 `saliency_map`、`spectrogram`、
  `topographic_map` 或 `3d_plot`。
- 所有可靠 stage 都發布；backend state unavailable 時仍可發布。
- MainWindow materialization 的 correlated ready／failed callback 才是 terminal。
- Visible result 必須包含實際 destination，例如 `Opened Saliency Map`，不能一律顯示 generic
  Visualization 文案。

### Retired model-facing surface

下列名稱不屬於 target model surface：

- `list_files`、`get_dataset_info`、`query_state`。
- `load_data`、`attach_labels`。
- `scan_source`、`preview_interpretation`、`validate_interpretation`、`apply_interpretation`。
- interpretation recipe save／reload wrappers。
- `apply_standard_preprocess`。
- current `set_model`、parameterized `configure_training` wrappers。
- current `evaluate`、`visualize`、`saliency` wrappers。
- `reset_session`。

相關 backend services 與 GUI consumers 保留；只有 Assistant wrapper 在 caller inventory 為空後物理
刪除。不得新增 runtime fallback 或第二個 compatibility path。

## Backend-owned stage contract

沿用既有 `PipelineStage`，不建立 Agent state machine：

| Stage | Backend meaning | Target candidates before capability filtering |
| --- | --- | --- |
| `empty` | 無 raw data | Import、Switch |
| `data_loaded` | 有 raw、尚無 derived preprocessing | Channel、Montage、五項 direct preprocess、Epoch、Switch |
| `preprocessed` | Channel 或任一 preprocess 已成功 | Channel、Montage、五項 direct preprocess、Epoch、Reset、Switch |
| `epoch_ready` | 已有 supervised epochs，但 split／model／training settings 尚未全部完成 | 三項 setup tools、Start、Reset、Switch |
| `dataset_ready` | saved split、model、training settings 三項全部完成 | setup 可修改；Start confirmation；Reset、Switch |
| `training` | active training job | Stop、Switch；不發布其他 mutation |
| `trained` | 至少一個 completed run | setup／retrain、Reset、Clear History、Compute Saliency、results navigation |

`select_channels` 或任一 direct preprocess 成功會自然投影為 `preprocessed`。Channel與Montage都在
`data_loaded`／`preprocessed` publication中可用，且在Epoch成功後隨即消失；這不縮限既有GUI/backend的較寬
capability。Raw data可直接建立Epoch；`CreateEpochCommand`要求raw與合法epoch context，不以preprocessing
operation作前置條件，成功後直接投影為`epoch_ready`。`start_training` 是 `epoch_ready`
stage candidate，但split、model或training settings未齊時由同一publication capability排除schema並在
unavailable reference精確說明缺項，不能部分執行；全部ready後才成為callable。

Stage、setup flags、running state與completed runs都從同一份 immutable ApplicationService
publication產生。若 publication generation 在生成、repair、confirmation或GUI handoff期間改變，
舊 proposal／resolution一律視為 stale。

## Strict model output contract

正式輸出使用[單輪兩欄契約](#agent-m0-contract)；每回合一個JSON object，不回填stage、
backend publication或generation。接受裸JSON，或整份回答恰為一層`json`／無語言
Markdown fence；只能解除外框，raw output原樣保留。不從prose、任意code block或多個
候選中抽取指令；前後prose、array、額外欄位、重複key、非標準數值與舊格式皆拒絕。

只有parser證明raw含兩個以上相鄰且完整的top-level objects，才直接給可信choose-one
terminal；不挑第一個、不format retry，也不confirmation、GUI handoff或execution。
其他格式錯誤最多在初次生成後加一次repair，使用同一當輪要求與publication；
Host不補欄或改寫操作。來源／schema拒絕及backend執行失敗不增加模型repair loop。
任何side effect、confirmation cancel或GUI cancel／fail後不得重送操作。
歷史schema／scorer成績保留原身分；相同兩欄形狀不代表不同版本契約與結果等同。

## Prompt、必要狀態與RAG

每回合 prompt 只含：

1. 固定 policy 與 strict envelope。
2. backend stage 與同一generation capability都允許的 target callable schemas。
3. 已註冊但本回合不可呼叫的target action reference；每項只有stable tool ID與bounded public reason，
   不含schema，也不是合法output candidate。
4. 最後一則必要user-role JSON：`application_state`與`current_user: {text}`，保留當輪完整原文。
5. 空間允許的完整RAG示範，明標untrusted參考；不附先前user／Assistant對話、草稿、
   對話來源ID或累積參數。畫面聊天紀錄不等於模型上下文。

Callable集合固定為approved stage membership、同一份ApplicationService publication的enabled
`ToolAvailability`與目前registry／target membership的交集。其餘已註冊target tools只可出現在明確分隔的
unavailable-action reference：backend capability disabled時沿用同一publication的public reason；capability
enabled但target stage未發布時，使用「此action在目前workflow stage不可呼叫」的bounded projection reason。
Confirmation-required但enabled的action仍是callable，不得列為unavailable。

Unavailable reference不建立新tool、schema、readiness owner、RAG example、confirmation、GUI handoff或
execution permission。模型被問到這些 action 時應以`respond_to_user`說明對應blocker，不得改呼叫前置或
替代action；若模型仍輸出該stable tool ID，既有`PromptToolPublication`／attempt admission以同一backend
generation與同一reason fail closed。Prompt projection不加入general semantic Host router，也不以文字
heuristic推翻另一個當下確實callable的model proposal。

必要 `application_state` 只投影同一份 ApplicationService publication：

- always：stage、internal backend generation、`state_reliable`。
- stage-relevant counts／readiness。
- setup stage：split、model、training-settings flags與missing list。
- training：model、running與短進度。
- trained：finished run count、results available。

不放 file paths、完整 channels、完整 settings、diagnostics、recommended next step、full capability map、
舊tool output或對話草稿。必要state與當前原文不能當optional context丟棄。
Assembler先守完整UTF-8 byte bound，local backend再用exact tokenizer／chat template與
預留輸出計數；先移除optional notes，再按原排名打包完整範例。
必要內容仍超限則零推論、可見拒絕，請縮短完整要求或New Chat後重述；
不能裁掉否定、條件或靜默截斷current user。New Chat不是保存／恢復草稿的入口。

RAG／examples規則：

- RAG提供操作／正確不操作的英文決策示範，不承擔EEG知識庫或第二套intent／permission router。
  不以文字關鍵字先判定是否檢索，也不按callable數量切換固定範例與semantic retrieval兩套policy。
- 搜尋前限制為當次callable action examples及既有`respond_to_user` examples；後者不是新增可執行
  action。示範須以actual action schema或strict response parser驗證，不允許額外欄位或多action。
- 採[雙路獨立召回與RRF融合](#rag-hybrid-design)；最多三例與允許零命中保持。
  Dense-only須真正省去BM25建置／查詢，不另維護production retriever；hybrid缺BM25不得silent fallback。
- 範例內容涵蓋參數與相鄰操作差異、概念詢問、只要說明、明確禁止操作與無法辨識的指涉；
  不機械湊數、不複製驗收題，缺參數範例須請使用者重新提供完整要求，不示範跨輪補值。
- RAG 延遲後，最終 prompt 以同一份 publication 組 schemas／required application_state 並重查範例資格；
  unavailable-action reference永遠不提供可操作示範，也不進RAG allowed tool names。
- retrieval failure退回既有schema／format並明示degraded，不擴大tool surface或冒稱正常零命中。
  範例不能授予capability或confirmation權限，也不能供給未出現在使用者要求的參數。
- 驗證同時看工具／參數、正確不操作、實際副作用與分段延遲；retrieval命中不等於模型效果。
  保留固定48個工程probe輸入，另列24個成對probe；說明性問題檢查安全資格而非必須無context。
  BM25去留以同source／corpus／model對照證據判斷，不因小樣本打平刪除，不以放寬gate完成驗收。

Backend state 不可靠時，required `application_state` 固定為 `workflow_stage: "unavailable"`、
`state_reliable: false`，只發布 `switch_panel` 操作；`respond_to_user`仍可回覆，不屬於工具 registry。
不沿用 stale tool set。Granite
runtime本身失敗時不做生成，ChatPanel顯示local runtime error。

## Verification、execution與presentation

模型回覆先經strict parser；非執行回答只呈現訊息，其餘單一command送既有tool attempt
boundary，核對當輪來源、完整schema／range、backend generation／stage、target publication、
ApplicationService capability、one-action限制及必要confirmation。
Prompt與UI不建立alternate readiness engine；模型JSON不能關閉來源或確認檢查。

一般文字均走同一模型理解路徑；Host不自行排序bandpass、辨認意圖、合併舊值或把回答
升級成操作。缺值回覆結束當輪，不建立等待補值state。確認、GUI handoff與async工作仍
由既有typed correlation及backend lifecycle處理；失敗／取消不恢復或重跑操作。

GUI completion使用既有 pending interaction與request correlation。`accepted`、`navigated`、
`command_pending`或`deferred_to_ui`是否terminal必須依execution kind判斷：GUI completion只能等實際
dialog outcome；pure navigation則等panel/subview materialized。

Visible result使用既有Assistant bubble與confirmation card：

- 一個concise trusted backend／UI public message。
- 不顯示raw JSON、traceback、private path、capability dict或內部token。
- 不讓模型產生下一步建議或再解釋tool output。

## Diagnostic walkthrough target

`--tool-debug` 必須能在完全不建立或載入Granite的情況下使用正常ChatPanel、MainWindow、
ApplicationService、實際tool execution、confirmation與UI correlation。

- Debug launch顯示slim banner／step progress；normal launch不變。
- Enter只peek目前step；前一步terminal、無pending interaction且navigation idle後才commit並前進。
- Failure留在同一步，可retry；`confirmed=true`不得繞過真confirmation UI。
- 三份pure-data profiles：Complete Workflow、Lifecycle／Navigation、Contract Failures。

Diagnostic mode只是一個既有runtime lifecycle的no-generation transport狀態，不是新的workflow owner、
command policy或fake backend。

## Candidate validation與claims

候選案例、門檻、runner／report版本與同版本gate只由
[驗證契約](../validation/README.md)擁有，不在target複製另一份可漂移的出口。
新單輪基本集合為20題（`scripts/dev/stable_assistant_single_turn_cases_v1.json`），
74題單輪breadth另列；歷史81題含7條跨輪trajectory，保留原source／schema／分母與失敗，
不重標為新單輪通過，也不能直接比較總分。

產品與evaluator須共用stage-consistent publication、assembler、LocalBackend role/template、
parser與驗證；不手組全開catalog，不從gold補參數、來源或假pending。
First raw、format recovery、Host admission與product outcome分開記錄；Host擋錯不增加
模型分數，模型選錯工具不是格式修復成功。工程scripted模型只能證明程式邊界，不冒稱
真模型或workflow效果。RAG檢索准入與[模型受益](#rag-benefit-acceptance)分開驗收。

Source／unit通過、歷史Stable成績或相同wire形狀都不能宣稱新版Assistant-ready；
仍需同一候選的真模型、完整輸入獨立覆核及適用Windows真人驗收。這些是bounded
產品要求，不是安全零容忍、任意語意正確或thesis benchmark。
正式Development只調[研究規格](../validation/thesis_protocol.md#6)核准項目；
RAG語料／檢索設定與模型／生成參數不是額外搜尋軸，不改寫歷史封存與原失敗。
