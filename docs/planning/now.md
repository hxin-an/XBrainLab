# XBrainLab Now

最後更新：`2026-09-20`

## Active — 共同基線整備（使用者已授權施工）

本節優先於下方歷史順序。目標為啟動器、研究文件與 RAG 的共同 main 基線；
不是正式題庫評測、pilot 或 Assistant Stable promotion。只讀／使用既有工程案例，
不讀正式 Validation／Test，不把題目或 oracle 加入 RAG。

1. **啟動器 PR #143**：head `8314b590` 的三個 Windows-only 測試被 Linux shard 收集後
   skip，導致 mandatory completion gate 失敗。修正既有平台分流及 Windows 測試環境依賴，
   不放寬 skip gate、不改 `start.cmd` 行為。驗證三個真 CMD 案例與 routing 回歸後 push，
   追蹤同 head CI；產品 merge 仍需明確批准，純測試修正不冒稱新的產品手測。
2. **研究成果**：保存並審查 `feat/assistant-benchmark-calibration` 已有離線 calibration、
   研究規格及未提交出題文件／導覽；同步 main 後以非產品 PR 合併。只確認模板身分，
   不讀正式題目、不寫新研究 runner。focused calibration／docs checks，無 GUI 手測要求。
3. **RAG**：從最新 main 建立 `improve/rag-common-baseline` 獨立 worktree。
   18 工具各 4 筆英文正例（共 72），沿用單動作 corpus 契約；不新增回答／追問範例，
   不變更模型、工具、confirmation、format retry 或 capability owner。
   擴充前固定 36 正例查詢（各工具 2）及 12 邊界工程探針，沿用 verify_rag 真離線檢索；
   不以只允許預期工具製造命中。Top-3 至少 33/36、每工具至少一題、不得低於修改前。
   schema／ID／重複及語意審查、工具排除、索引重建／重用皆須通過。
   固定 embedding revision、threshold=0.7、top-k=3、context budget；只修有證據的直接缺陷。
   更新 corpus hash／collection identity。真模型以既有 pinned primary，舊基準一次＋最多
   兩個候選各一輪完整 frozen 81-case；不改分母／既知失敗清單、不下載模型、不降 gate。
   獨立 review 與 Windows ChatPanel 真實 journey 後集中一次 Assistant 局部手測。
4. **整合凍結**：同 head 適用 CI 成功且取得產品手測／merge 批准後合併 RAG；保存
   source、corpus、embedding／模型 revision、設定與證據身分。稱研究前共同基線，
   正式 B0 仍依研究規格固定。研究線與 UI 線各自工作目錄，工具契約先協調。

共用現有 Windows Python、模型、embedding 與資料；不新增環境、不搬資料。
root `settings.json` 不 stage／stash／覆寫，`wip/data-split-summary` 保留。
合併後才清理精確對應的 worktree／臨時產物，保留必要失敗與驗收證據。
本輪 UI layout／文案／流程沒有修改授權；RAG 正例／檢索改善已授權。
每個 slice review；不因小 commit、CI pending 或 compaction 停工。
候選預算用完、必要資源不可用或缺少合併批准時明確回報，不擴大施工。

**Next**：#143 head `2c36a5e7` 的 CI 已成功，產品 merge 批准仍待使用者回覆。
研究 PR #144 已完成 review／92-case calibration／docs／CI，合併於 `c44f4a7b`。
RAG 探針在擴充前固定；舊 23 例為 14/36，72 例初稿 30/36，依空結果診斷修訂六個正例後
為 34/36，各工具至少一題；所有索引／範圍／context gate 通過。探針已用於 development 修訂，
不稱 holdout 或正式 Test。模型舊基準 81/81 完整執行（兩個既有失敗），候選模型尚未執行。
下一步：完成 focused checks、同步 main、固定 candidate commit，再做完整真模型及 Windows journey。
**Stop**：四步完成，或真正的新決策／資源／產品批准阻擋；不把 focused pass 當完整完成。


## 已保存的研究準備

離線 calibration 與人工出題委託文件已由 PR #144 保存並通過非產品 review／focused 驗證。
出題说明與 CSV 是 AI 教學示例，不是正式題庫。M1 題庫、M2 runner 尚未完成；
不把啟動器手測當作全產品或 Assistant 接受。既有 workspace 清理已結束，細節留 Git history，
不重啟舊清理；受保護設定、資料、共用環境與未合併 Split WIP 保留。

## 第二主線研究里程碑計畫（研究文件準備中；runner 尚未施工）

2026-09-19 使用者確認先備妥完整計畫與里程碑，完成題庫及系統前置驗證，再進入 pilot。
本節是唯一執行順序／進度來源；[Assistant 研究與實驗規格](../validation/thesis_protocol.md)
擁有題數、模型、計分、實驗條件、預算與證據契約，不在此複製第二份研究規格。

- **問題與證據**：已累積方法決策，但逐項討論缺乏整體交付順序；研究規格第 7 節仍明列
  正式題庫、五模型 runner 與完整 outcome／報告接合未完成。舊 calibration 不是新實驗就緒證據。
- **Outcome**：以 M0–M6 串起計畫、題庫、系統、pilot、改善、選版與結果；每階段有可核對出口，
  不用「系統應該沒問題」或完成一個小切片代替整階段完成。
- **目前位置**：M0 出題模板／覆蓋草案及系統準備方案已整理並對照目前 source，待整包核對；
  M1–M6 尚未依本計畫啟動，沒有正式題庫或 pilot 成績。
- **下一步**：一次核對研究規格第 3 節的 M0 草案與下方 M2 系統準備範圍，
  明定必要授權後才開 M1／M2；不是立即跑 pilot。
  尚未定案的研究細節按下方時點集中決定，不再每個欄位或技術選項都逐條等待使用者。
- **本次 scope／non-goals**：只更新本文件與研究規格；不出正式題、不讀封存 Test、不實作 runner、
  不改產品／UI／工具契約、不下載／清除模型、不接受條款、不跑實驗或寫外部 Notion。
- **本次文件驗證／停止條件**：核對決策狀態、數量、依賴、連結與 strict build，完成後交付計畫。
  此文件完成不等於 M0 已獲施工批准，更不是 M1–M6 完成或產品 handoff-ready。

### 完整里程碑與依賴

依賴順序：**M0 → M1 與 M2 平行準備 → 兩者皆通過 → M3 → M4 → M5 → M6**。
平行指工作安排，不是本次授權啟動多 agent、GPU 並行或背景長跑。

| 里程碑 | 交付物 | 驗收與下一階段入口 | 主要分工 |
| --- | --- | --- | --- |
| M0 研究／施工計畫定稿 | 研究問題、已確認規則、題目模板、準備工作範圍、資源方案及待定項時點 | M1／M2 不存在會阻擋施工的契約／授權缺口；後續決策有 owner 和截止階段，不要求先猜實測值 | Agent 整理整包建議；使用者核對研究意圖與授權 |
| M1 題庫準備 | 規格第 3 節的完整題庫、oracle、初始狀態、family／split 清單及封存資料 | 題數與分組符合規格、可判分、語意經審查；Test 由使用者封存，開發端沒有讀取權 | 使用者負責人工內容與 Test；agent 協助非 Test 模板、改寫、檢查 |
| M2 系統與評測工具就緒 | 可用的五模型接入、單一入口、真實觀測、scorer、結果目錄、失敗與續跑處理 | 已知正反例及代表性端到端路徑通過；紀錄／計時／分母可核對；必要安全檢查通過 | Agent 實作與 focused 驗證；使用者處理必要模型授權及適用的集中驗收 |
| M3 Pilot | 規格第 6 節的小規模真模型試跑、問題分類、成本與可行性報告 | M1／M2 均通過才開跑；可區分模型錯誤、產品故障與無效測量，能據以確認 M4–M6 預算 | Agent 執行／整理；使用者集中確認成本、速度目標與必要調整 |
| M4 Development | 保存的 B0、有限改善方案、B1／B2 候選及同題比較 | 規格第 6 節的中止與進入 Validation 清單通過；不以分數完美為出口 | Agent 推進已授權方案；使用者只處理契約、範圍或超預算決策 |
| M5 Validation 與凍結 | 固定候選的比較、選版理由、人工 scorer 核對與 Test 配置 | 選版規則先固定，評分可信；選定系統、B0、適用消融與分析方式凍結後才解封 Test | Agent 執行與整理；使用者人工核對、確認凍結並提供封存 Test |
| M6 Test 與論文結果 | 完整逐題結果、人工核對、表圖、失敗分析、限制與重現附件 | 承諾條件結果完整且無未解釋排除；每項論文主張能連到證據，不要求正向結果 | Agent 整理證據與結果草稿；使用者核對解釋與論文表述 |

### M1：先完成題目，不拿 pilot 代替出題

1. Agent 先提出工具／情境覆蓋表與一份共用題目模板：題號、family、split、使用者輸入、
   初始狀態、可用工具、允許的答案／參數、禁止副作用、預期觀測層與 fixture 身分。
   先以少量非 Test 人工題驗證模板與 oracle 可表達需求，再大量填題；不擴張工具契約。
2. 使用者協調自己／受邀者提供人工 seeds／改寫與語意核對；agent 先提供模板與格式檢查，
   Dev／Validation 的 AI 改寫須另行確認，不替代人工作者生成「全人工 Test」。
   先分 family 再改寫，不能事後隨機切分。
3. 正式題庫全數完成後核對語意、標準答案、數量與重複風險。Validation 不用來修產品或調 prompt；
   對其題目格式的必要準備不等於允許先看模型結果。Pilot 只抽已準備好的 Development 題目。
4. Test 由使用者在隔離位置完成審查與封存；agent 可提供本機檢查工具供使用者執行，
   只接收數量、版本／hash 與審查狀態，不接收題文、oracle、含題文 log 或實驗前的 Test 軌跡。
   這不能冒稱 agent 已獨立審過 Test 語意；單人出題／評分限制照實保留。

### M2：確認可測量與可運作，不要求模型先很準

#### M0 source 核對與 M2 最小準備範圍

以下是 source-backed 準備提案，不是 runtime 通過證據或產品修改授權：

| 現有接點 | 可重用部分 | M2 必須補齊／確認 |
| --- | --- | --- |
| `llm/action_contracts.py`、tools definitions、核准 target | 18 工具、schema、既有 owner 與確認／結果契約 | 逐工具情境與可觀測結果對應，不新增第二套 readiness |
| `scripts/dev/assistant_benchmark_calibration.py` | 真 parser／schema 的離線正反例模式 | 新研究 scorer 配合已確認的缺資訊不執行與 GUI 交接分層；不改寫舊 calibration 的歷史成績 |
| `scripts/dev/run_stable_assistant_model_eval.py` | 保存設定／模型輸出及既有評估接點 | 舊 runner 綁定 primary 與 frozen cases，會攔截工具執行；不能直接當五模型真實 outcome runner |
| `llm/core/backends/local.py` prompt capture | 實際 prompt、raw output、metadata | 接上 case／repeat／修復與事件因果鏈，完整報告不是單次 capture 就有 |
| 正常 ChatPanel／Host／ApplicationService 與既有 walkthrough | 真實操作、UI、狀態與確認 owner | 研究 fixture 下的觀測、隔離／重置與結果收集，不複製命令執行責任 |
| 產品 model allow-list／runtime | 既有兩個 Granite 的受控產品載入 | 五模型研究接入與其餘三模型精確 revision／相容性另設有界研究配置；不默默擴張產品 Settings 或關閉 allow-list |

直接相關差異在準備開始時須核對：`pipeline_state.py` 的 preprocessed 工具清單目前未列
`select_channels`，而核准 target 的 stage 說明允許它；先確認實際 publication，不能用文件
假定該情境可執行。此為 M2 覆蓋／修理候選，不在本次文件工作順手改產品；若只需研究先選
已一致的合法情境，不把未測的情境冒稱已通過。

研究 fixture 建議從可重現的合法資料狀態建立，分為空工作區、有資料／預處理、epochs、
設定完成、執行中及完成 run；用現有服務建構、在案例間重置，不讓前題副作用影響下題。
Agent 負責 fixture 與機器欄位；使用者不用手填 publication、generation token 或內部 ID。
Synthetic fixture 適合工程驗證，但真實產品 outcome 必須另外取得適用的真實來源與 Windows
原生 UI 證據；不新下載整套資料集，也不把模擬訓練終態或預寫 JSON 當成實際運算。

本輪不擴張 GUI、模型產品清單、公開工具或一般對話功能；研究所需的接入、紀錄、scorer 與
直接必要缺陷才在待授權範圍。只做單回合主分數的提案，不等於允許省略取消／狀態一致性測試。
模型精確來源、大小／VRAM、既有 cache 與可寫輸出位置須在下載前唯讀盤點，交付一份資源方案；
目前沒有選定新儲存目錄、下載模型、刪 cache、安裝環境或新增正式 CLI。

#### 授權後的實作順序

施工前重新讀 Git／source，沿用既有 Command、模型載入與 prompt capture 能力；
每個直接必要 slice 補上 call sites、具體驗證命令與回退邊界，不在文件中發明尚不存在的 CLI。

1. 先接題目格式、oracle 與 scorer 的正反例，涵蓋選對／選錯、參數錯、缺資訊、No-call、
   Host 擋住錯誤但模型仍判錯等情況；確認讀取錯誤能被辨識，而不是靜默漏題。
2. 接正常 Assistant／Host／Command 觀測路徑，使用研究 fixture 核對操作、GUI 交接、
   前後狀態、確認／取消與必要失敗路徑；不以攔截執行或捏造 UI 終態當作產品成功。
3. 補單一入口的選一／多個／全部條件、逐次輸出、計時、修復預算、失敗分類與彙整。
   驗證中斷不遺失已存證據、續跑不覆寫、不重送終態不明操作、設定不一致不混入同一 run。
4. 經資源與授權確認後，五模型分別做載入／固定暖機／少量非 Test smoke check；
   固定精確 revision／模板／runtime／生成設定，核對 RAG on 真有檢索、off 不檢索。
   不相容或 OOM 明列 blocker，不換模型冒充通過；不要求 smoke check 決策全部正確。
5. 以同一份保存軌跡核對輸入、raw output、事件、決策分數、產品 outcome 與時間；
   已知 parser／scorer、取消／安全、漏記／誤計時問題須修到能判斷結果，才可進入 pilot。

此處「系統就緒」只涵蓋研究所需的可運作／可測量能力與必要安全保護，不是全產品零缺陷。
UI 或公開工具契約變更仍須明確確認；需要產品 handoff 時遵守既有 workflow，不為每次純評測
改動都要求 GUI 手測。真模型 smoke check 也須有預先列明的有限案例與資源預算。

### M3–M6：用證據推進，不以分數好看才結束

- **Pilot 前保存基線**：M2 就緒時保存可追溯的準備版本。Pilot 若暴露須修的產品／配置問題，
  留下前後版本與原因；M4 第一個改善方案前固定可重跑的 B0，不事後拿新版冒充改善前基線。
- **Pilot 出口**：交付每模型／條件的可行性、測量缺陷、延遲／修復／失敗分布與成本估計。
  成本須含載入、操作、重試及實際排程開銷，不只用最快題估計整場。超預算或量測仍壞即為
  checkpoint，提出有範圍的修正／調整，不暗中把剩餘矩陣跑完。
- **Development 出口**：按既定輪數／方案預算與規格 gate 執行。五模型比較不能變成無限調參；
  未授權且無關的產品／架構問題列為後續，不阻擋已能可信測量的本輪研究。
- **Validation 入口與出口**：看結果前固定候選、共同預算、速度門檻、相近判準、統計與安全規則。
  使用保存軌跡做人工作業；若 scorer 有缺陷，一致重評受影響紀錄，不挑有利版本。
  完成選版與凍結後，不再依 Validation 追加改善方案。
- **Test 出口**：只跑規格批准的完整系統、適用消融與同模型 B0；原始軌跡可追到圖表。
  低分、負面消融或 B0 較好都照實報告，不據此重新選版／調參後混入同一獨立 Test。
  人工抽查、剩餘缺失與論文限制齊全，才宣稱本階段結果完成。

### 集中決策時點與分工

| 最晚決定時點 | 集中核對的內容 | 處理方式 |
| --- | --- | --- |
| M1／M2 開始前 | 研究問題表述、題目模板／覆蓋、fixture 與操作層範圍、實作／模型資源授權；多輪是否納入 | Agent 提供一包建議，使用者確認範圍；未批准的多輪數量不默認施工 |
| M3 開始前 | M1／M2 通過證據、精確五模型配置、pilot 題目清單／順序、smoke 與 pilot 資源範圍、輸出位置 | 不需要先決定最終模型贏家；不使用 Validation／Test 做 pilot |
| M3 完成後、M4 開始前 | 實測成本、剩餘人力、改善預算／截止日期、必要的技術配置調整 | 維持既定上限；需變更研究預算或範圍時一次確認，不自行延長 |
| M5 開始前 | 最終 Validation 矩陣、P95 門檻、相近／較簡單判準、統計算法與人工抽樣細則 | Agent 依 pilot／Dev 提出完整預設方案，使用者集中核對；不得看 Validation 後挑規則 |
| M6 解封前 | 選定系統、B0、適用消融、精確 source／設定／題庫／scorer 身分與執行清單 | 核對既定方法已落實，不再新增研究問題或依 Test 選有利分析 |

使用者協調自己／受邀者的人工出題，負責 Test 封存、必要條款與研究取捨、約定的人工核對及真正產品驗收；
agent 負責模板、非 Test 輔助工作、直接必要實作／驗證、紀錄與報告整理。
檔名、內部欄位、輸出排版等在既有契約內由 agent 提供一致預設，不逐項打斷使用者；
新下載、外部分享、破壞性清理、可見 UI／工具契約與實質預算擴張仍不是默認授權。

### 時程、風險與跨 context 接續

- 研究規格中的結果目標日與暫定改善截止日保留，但**尚無可行性證據，不是完成保證**。
  M1 要先完成整套題庫，受邀出題者及審查分工尚待確認；機器平行不能抵銷此人力依賴。
- M1 初批人工題完成後記錄實際出題／核對時間，估算剩餘工作；M2 盤點模型授權與接入缺口，
  M3 才有正式機器成本。據此在同一計畫排定可承諾的時程，不先替每個 milestone 填虛構日期。
- 若日期、完整題庫與可投入人力互相衝突，集中提出調日期／範圍的選項；不得縮題、改成 AI Test、
  降低驗證或自動增加人工負擔來假裝準時。未取得模型存取權也不能偷偷替代五模型。
- 每個 milestone 以具體交付與 gate 狀態回報；目前僅文件，不宣稱已通過題庫／runtime gate。
  未來施工只在已批准 scope 內持續，context compaction 或完成小切片不是停止或新授權的理由。
- 接手先讀本節、研究規格、Git 與可辨識的執行狀態，再續作當前已授權項目；在此更新進度、
  下一步與 blocker，不建立第二份工作日誌／控制平台，也不啟動下方舊候選。

下方是既有產品優先順序與候選背景，不覆蓋本節目前只討論／更新研究文件的 scope。

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
  正式研究已確認依產品完成契約區分「開窗」與「完成操作」；詳見研究規格。
  舊合成 calibration 不因此成為真實 GUI outcome 證據。
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
