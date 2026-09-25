# XBrainLab Now

最後更新：`2026-09-26`

## Active — 共同版本功能與實驗量測驗收，做到 Windows 集中手測

2026-09-24 使用者希望在第一版實驗前，逐一討論與打磨整個 Agent 部件，而非再次只按
程式檔案清理。範圍包含用途、內容、方法、操作體驗、實作、測試、腳本及研究可觀測性；
RAG 作法與庫內數量等基本合理性也須查證，不能把目前做法或工程測試通過當成設計合理。
最初僅制定計畫與唯讀審查；2026-09-24 使用者追加授權由本代理統一整合產品／實驗兩線，
先建立可靠共同基線，再分回產品部件與研究推進。允許本機checkpoint、整合候選及直接必要
的相容修理／補測；當時未授權發布PR，2026-09-25啟動本計畫後依下節建立驗證PR；仍不merge main、下載模型或啟動正式實驗，不更改公開工具、
可見UI、研究題庫／判分政策。下面各部件先討論，再依已確認的方案授權施工；計畫不是
把所有候選技術都批准實作。前輪內部清理的結果與限制保留在下節，不重做或改標研究證據。

使用者隨後澄清：本輪目標是先建立可靠基礎，完成後才開始跑 Development 改善。
不能把必要的 RAG／tool call／prompt 內容與方法打磨提前算成 Development，也不能
以「這應留給實驗」為由，讓已知基礎缺口進入 Development。部件小驗證是準備的證據，
不是正式 Development 成績；正式研究仍須有明確的起始版本與資料使用界線。

### 優先施工計畫 — 功能與量測驗收 { #integrated-functional-acceptance }

2026-09-25 使用者要求：分線继续改善前，先由代理實機跑過整合產品與另一線實驗腳本，
涵蓋已迭代的 Evaluation／Saliency，準備到一次集中 Windows 手測；實驗部署在工作站134。
計畫已固化並經獨立覆核，使用者現已明確要求開始執行，做到集中手測。
下方六部件打磨是後續工作，
不能跳過本節驗收直接接續。這不是重開無限全盤清理或重新定義研究方法。

#### 起點、已知事實與授權

- 起點為 clean `d4963adc3101741f3ba1f07779ee7c1e90a6157d`，worktree
  `D:\workspace_v2\projects\lab\XBrainLab-agent-baseline`；本次計畫文件修改須另記，
  不把 dirty source 當成已凍結版本。既有整合證據及限制見
  [Current](../current.md#assistant-integration-baseline)。本輪產品與研究須驗同一最終source，
  Windows／Linux runtime及模型配置各自記錄，不混用速度或判分成績。
- 已以 `hxin` 成功登入 `140.113.193.134`，既有主機金鑰核對通過；只執行身分查詢。
  今日GPU／程序、容量、環境、模型cache完整性與新source可執行性尚未預檢。
  舊 `b42cd81e` 工作站smoke是歷史證據，不替本輪背書。
- 保持已接受的UI／功能／資料語意、公開tools及研究判分政策。必要的相容修理和直接補測
  在已授權準備範圍內；新可見行為、contract或研究方法取捨集中提出，不偷偷改成容易通過。
- 原兩線、main的使用者 `settings.json`、原始資料、共用環境／模型與B0／d0結果不動。
  不讀sealed VALID／TEST，不跑新正式DEV／VALID／TEST，不下載／重複備份模型。
- **本輪授權**：使用者在確認計畫及PR用途後要求開始，允許push整合分支／建立一個驗證PR
  取得同head CI，不包含merge。這是一個階段整合PR，帶入既有已審查模組與研究改動，
  不因累積diff強迫逐slice手測；新增修理仍逐片複雜度審查與驗證。
  登入授權不等於可覆寫工作站既有source／env／結果；實作本計畫時僅使用
  預檢確認的既有資源及新隔離工程輸出，若需安裝、替換資源或新增下載，先列明再確認。

#### 執行順序與各段出口

| 階段 | 工作 | 出口／不可以冒稱的事 |
| --- | --- | --- |
| A. 版本與環境預檢 | 核对原兩線有無新修改、最終候選及適用gate；核對Windows共享環境與本機cache。134先查實際GPU負載、自有／他人程序、Python／lock／CUDA、既有五模型與embedding身分和容量。核對研究交接，不能假裝已聯絡不可見的獨立fork agent。 | 明確可用的執行環境與輸出位置；GPU空閒不等於已預約。不關閉別人的程序，不用silent fallback。缺資源先報具體缺項，不把登入成功當環境通過。 |
| B. 完整工程回歸 | 依現有CI／runner執行產品、tests、scripts整體回歸、全專案typing、架構、docs與適用跨平台／視覺gates；完整Linux aggregate沿用既有coverage verifier。補同版本canonical source-diverse與本次階段驗收要求的完整代表性import catalog，使用現存資料、不重下載。 | 同head全部適用non-skipped checks成功，原失敗與skip理由保留。不同SHA不換標，同版本等價CI證據不在本機重跑。完整catalog以registry required membership為準，不把少數資料流程當全catalog。 |
| C. Windows實際產品流程 | 原生Windows走Import／class／channel／montage → preprocess → epoch → split → training → Evaluation → Saliency；資料輸入與測試產物隔離，核對真資料副作用和結果，不只開視窗。涵蓋正常、取消、停止／重跑、重開結果及前輪已修路徑。 | 當前source的真操作／截圖及相鄰failure證據；Windows gate與必要100／125／150% DPI通過。Linux offscreen不代替Windows，代理操作不代替使用者最終手測。 |
| D. 真模型Assistant | 使用現有精確產品模型及RAG，跑適用既有bounded model gate與正常ChatPanel真操作；涵蓋開窗、填參數、實際操作、缺資訊、不可執行、確認／取消、停止與錯誤回報。 | 完整模型輸入／原始輸出與實際結果可追查；既有模型限制如實保留，不調prompt／題目或反覆重抽來取得綠燈。GUI成功與raw model正確分開，既有bounded限制不冒稱Stable。 |
| E. 實驗量測驗收 | 先完成下面的量測正反例，再於134從新封存的同source工程包實跑；沿用 `package → dev → pilot → condition` 及包內 `run.sh`，不是另寫簡化runner。 | 五模型固定20筆工程smoke、capture／判分／報告／cleanup可核對；可從包內啟動及離線重建／audit。不把「有報表」或「20題全對」當量測正確的替代證據。 |
| F. 修復與獨立覆核 | 真defect先重現、補測、最小修理，再驗受影響及必要相鄰流程；高風險owner／publication／async與量測邊界由非作者覆核。主代理核實實際diff及產物，不只收摘要。 | 無未處置的功能／量測blocking finding；已知模型錯答與產品bug分開。source變動後更新相依證據及最終CI，不因單組通過就提前交付。 |
| G. 固定版本、集中手測 | 將Windows與134產物綁到最終clean／明確解釋的source；提供範圍清單、修正／限制、實驗報告入口及重跑命令。直接開Windows完整程式與一個PowerShell即時log，確認有回應後交回使用者。 | 使用者測的是代理已實機驗過的候選；附一行重啟命令。沒有額外Windows Live Log視窗，不自動merge、不持續監控手測，也不開始另一輪部件改善。 |

**C的必驗重點**：Split含subject模式與實際預期工作數，不只看第一個run啟動；training含停止
與重跑。Evaluation核對fold／run／Summary、長標籤／圖表與scroll、實際結果及結果重開。
Saliency核對真Compute／Recompute、SmoothGrad有界完成、背景時其他panel仍可用、游標恢復、
fold／run／class／method切換、2D／3D及warning偏好、視窗縮放與結果重開；不把只顯示
「背景計算」當成功。若契約明示某模型／方法不支援，驗正確blocked行為，不要求偷偷fallback。

#### E的量測正確性：不只是腳本單元測試

- **身分與選擇**：核對單模型／核准子集／全部選擇、實際case／condition集合、source與
  模型revision／量化／template／prompt／RAG／生成設定；錯source、缺資源與設定漂移須拒絕，
  選擇不能只驗prepare清單而不驗實際啟動。沿用既有協定，不新增第二套manifest owner。
- **Capture與實際操作**：核對最終送模輸入、每次原始輸出、格式修復、Host admission、
  GUI／Command結果與terminal；對已知實際副作用核對，而非只信status字串。
- **Scorer正反例**：使用公開／合成且有獨立預期的正確與錯誤tool／參數、缺資訊、blocked、
  GUI取消、工具失敗及量測缺失案例；核對raw first、post-recovery、Host安全及最終結果不混算。
  對false positive／false negative及case分類作人工核對；必要補測不讀sealed題庫除錯。
- **計時與彙總**：以可控制時間的工程case與真run事件序列核對時段界線；載入／暖機另計，
  決策、格式重試、工具／人工等待按[研究規格](../validation/thesis_protocol.md)計算。
  分母、成功／失敗／逾時／無效量測、分位數與逐題輸出一致；不能遺漏失敗或用重試灌分。
- **中斷與重播**：使用獨立工程case驗背景啟動／SSH端退出、自有child逾時或可控中斷、
  同source/runtime續跑、跨source拒絕、不重覆計分／覆寫；不強殺共享GPU工作。
  從封存包另開新run，執行report-only及原scorer audit，核對原inputs/raw不變；
  既有協定不支援搬移未完成run後無縫resume，不將其列作本輪新功能。
- **134真跑邊界**：沿用protocol固定五模型各四題、共20筆 `engineering-smoke`，執行累積
  60分鐘预算（不含資源複製），不是完成時間保證。真RAG／終態／capture／cleanup缺項不能算通過；
  有效模型錯答保留，不因分數重跑，不當正式DEV成績或模型排名。額外故障注入用隔離工程
  case／fixture，不污染這20筆，也不重跑整套正式題庫。需要超出預算先報原因，不暗中加碼。

#### 分工、驗收與接續

- 主代理擁有候選、計畫、版本凍結及最終證據驗收；可獨立的產品／量測審查並行、寫入責任
  不重疊。CPU／文件工作可在模型執行時進行；同一GPU重型工作循序、一次一模型，
  不因平行化產生資源爭用。使用既有runner與ignored證據位置，不建新驗證平台或重複環境。
- 驗證命令、timeout與artifact政策由現有[驗證契約](../validation/README.md)、
  `scripts/dev/handoff_gate_spec.py`、CI及研究protocol擁有。本輪是完整功能驗收範圍，
  不是任意宣稱完整release dossier或Stable promotion；若宣稱full dossier須跑原完整manifest。
- **交付門檻**：適用同版本CI成功、Windows產品／Assistant實機證據齊全、134量測正反例及
  真smoke／封存audit完成、獨立覆核無blocker、來源一致。Pending／stale／missing gate
  不算通過。使用者不需逐slice手測；修理後只重验受影響及必要相鄰範圍，最後一次集中交付。
- **停止條件**：達到上述門檻且Windows程式已開啟有回應，交給使用者手測即停止主動操作。
  Compaction、單slice／commit完成或CI pending不是停止理由；缺新授權／必要資源才回報
  具體blocker。手測／merge另依明確批准，不自動把本計畫當merge授權。
- **可達效果**：證明指定版本在Windows代表流程與134指定工程量測範圍可運作，量測輸入、
  判分及計時可追查；留下雙線後續的共同起點。不能證明所有資料／硬體組合無bug、
  Saliency科學有效性、模型高準確率、研究統計效力或六部件設計／內容已全部打磨完成。
- **目前next**：A已確認main仍為 `94328196`；134既有Python／Torch／CUDA可用、查詢時GPU
  無compute程序，lock未變，不重建環境。首次20秒import預檢逾時保留，分段診斷後實測
  Torch／Transformers匯入約1.45／2.75秒，未載入權重。資源完整性仍待正式prepare核對。
  E既有量測正反例361案及新真Command計時直接組14案通過（重疊不加總）；新增test-only
  clock oracle區分生成開始、Command admission、terminal及晚輪詢，獨立覆核通過。
  C的Evaluation／Saliency／training局部原生流程通過，連續GUI流程亦已補齊：真wizard／
  dialogs、三subject、真鍵盤輸入1 epoch／batch 2、三個實際training jobs及結果重開；
  native相鄰兩案通過且獨立覆核，未新增產品owner或UI。仍須對最終source補齊C–E。
  驗證PR #147 的首輪 `1eaf618f` CI發現直接整合缺口，先修復再凍結重型驗證：
  Python 3.11 audit不支援 `Path.is_junction`；研究warmup仍直接讀worker；部分測試仍預期
  舊parser／run文案／saliency呼叫或繞過LocalBackend初始化；另有型別診斷、human-like
  walkthrough失敗及visualization baseline drift待依實際artifact判讀。逐項核對已核准契約，
  保留原失敗，禁止放寬gate或只更新snapshot求綠；以原失敗案及直接相鄰測試驗修理，
  async／量測邊界獨立覆核。若發現需要新UI／工具／判分取捨則停止該項提出決策。
  只做這些阻礙本輪驗收的相容修理，不重開模組清理。修完再跑同版本模型／import catalog；
  尚未標記B–G通過。
  2026-09-26追加診斷：短路徑Windows offscreen human-like run有完整failed JSON，
  Evaluation checker仍要求整個canvas同時可見，與已接受的局部scroll行為衝突；先以真Qt
  正反例驗「完整可讀且每一端實際可達」，保留遮擋／缺scroll／label overlap拒絕，
  不直接改成true或降低尺寸／字體。navigation與關閉thread findings保留待環境／owner核對，
  不用此offscreen run替代native handoff。CI上傳補保留failed -runs目錄，下一輪取真CI JSON。
  scroll修理已經真Qt正反例及247項直接測試通過、主代理核對實際diff；保留原fully_visible
  事實，另驗四端可達、遮擋／壞scroll拒絕及原位置恢復。研究warmup／junction直接118案
  通過；接續凍結修理、push同head CI，執行完整catalog、本機真模型與134工程包。
  134最新預檢已有非本代理GPU工作，先準備隔離包，不終止或爭用其他程序；真正執行前重查。
  GPU工作由主代理協調，不互相爭用；尚未宣稱C–G或最終CI通過。

### 目標、基線與文件分工

- **目標**：形成一套能說清楚各部件的目的、輸入輸出、責任與取捨，且能被可靠測量的
  第一版工程候選；不是先追求最高分、最少行數或全產品零缺陷。
- **版本**：整合 worktree 為 `XBrainLab-agent-baseline`／`integration/agent-baseline`，
  以研究線 clean `293f1890` 為起點，帶入產品 checkpoint `8c50bee9`；原兩線保留。
  這不是 main 已發布基線，也不因任一線先前通過就稱共同基線已驗收。
  本輪先固定產品source、runtime與研究observer／runner相容的**共同工程基線**，再由
  兩線從同一精確版本接續。這不表示下方六塊設計／內容已打磨完成，也不自動成為
  正式研究起始配置；後續部件準備與研究條件仍依各自已確認的範圍、版本及授權驗收。
  該版本與既有研究 B0 的命名／比較關係，在啟動研究前核對；舊 B0 與其證據不覆寫，
  不只記 HEAD 而漏掉 dirty diff。新授權允許必要本機checkpoint／整合worktree，
  不備份權重、不覆寫原實驗產物；兩線原始來源保持可恢復。
- **接續順序**：**共同工程基線整合／固定版本 → 本節功能與量測驗收／集中手測 → 兩線接續部件準備與研究流程核對 →
  確認研究起始條件 → 依授權執行研究**。後續Development／Validation／凍結／Test
  的題庫與測量門檻以
  [研究規格](../validation/thesis_protocol.md)為準；下方M0–M6只保留歷史，不重新派工。
  必要pilot驗實驗流程與成本，不代替部件準備，也不默認重跑已完成的歷史pilot／d0。
  前置工作可查證方法、補足或清理 RAG 內容、釐清工具／prompt、做有界小驗證與修缺陷；
  不能因觸及這些部件就稱已開始 Development。Development 是在固定可靠起點後，
  按明定研究問題與搜尋預算做系統性改善比較，另保存候選與成績。
- **文件**：本節是本線順序／狀態／next step 的唯一入口；實作事實歸 architecture/current，
  公開行為決策歸 target，題數／split／判分／模型矩陣歸 thesis_protocol。
  研究線最新入口與完成狀態已向 clean `293f1890` 核對，不以舊里程碑推斷題目尚未完成，
  不讀取sealed Validation／Test；跨線整合統一由本代理協調，原研究worktree先唯讀保留。

### 共同工程整合已完成／下一步

產品 `8c50bee9` 與研究 `293f1890` 的必要改動已在 `integration/agent-baseline` 合成，
直接接合驗證與獨立覆核通過；結果、初次失敗及證據限制由
[Current](../current.md#assistant-integration-baseline)擁有。原兩線與歷史B0／DEV封存保留，
不更改scorer／題庫、不恢復失效產品欄位或另建owner。這是本機工程scope完成，不是main發布、
release handoff-ready或六部件全部通過。

先完成上方功能與量測驗收及集中手測，再以最終整合分支的精確clean commit為共同起點，
而不是繼續各自舊HEAD：產品線按下方順序
先討論Tool call／操作能力，再逐塊打磨；研究線先核對封存入口與起始配置，不自動重跑歷史
pilot／d0或開始新DEV／VALID／TEST。任何改變研究條件的後續部件改動另立candidate，
舊結果不換標。公開工具、可見UI、模型／RAG／prompt政策改變仍須先確認；原worktree、
使用者settings及資料不刪除；本輪push／驗證PR依上方新授權執行，仍不merge。

### 後續部件打磨第一步：先確認目前架構與品質

使用者再次明定：更進一步前須先確認現況。這是逐部件討論的共同起點，不直接啟動新一轮
大改或假定每塊都有問題。前輪已核實的責任分析與仍適用證據沿用；只補本次產品部件視角
尚未回答的問題與來源已變更的證據，不為新計畫重跑等價全套。

- **架構現況**：用一條真實要求串起工具公開、context／RAG、模型輸出、驗證、確認、
  Command／GUI交接與結果回報，查責任是否清楚、是否重複決策、是否存在不必要等待或轉接。
- **設計與內容品質**：核對工具契約、prompt的資訊／規則、RAG內容與方法是否足以承擔
  各自目的；查缺項、矛盾、過期、重複及資料來源，不能只以可執行或沒有exception判合格。
- **實作與證據品質**：檢查直接相關產品碼、tests／fixtures、scripts／設定／文件的一致性；
  大檔與過度設計、真正行為oracle、mock邊界、失敗／取消／重跑與可重現性一起判斷。
  區分已驗、未驗與失效證據，不把passing數當coverage，也不以審查取代必要動態驗證。
- **交付與判斷**：先給目前系統的簡明評價，每塊列「已有證據支持保留」「進入打磨前需修」
  或「尚待查證」及其依據；獨立reviewer核對重要結論、重大缺口與保留理由，主代理負責
  最後核實。未查清項不算通過，不承諾永不出錯，也不因行數大就預設要拆。
- **出口**：架構／品質現況與已知缺口明確後，逐塊討論處置；共同工程基線先保護接合
  可靠性，後續仍須在核准的研究起點前處置必要內容／方法缺口，不把基礎修理當調優成績。

### 每塊固定的討論與施工節奏

1. **我先準備現況**：從正式入口追到實際模型輸入、輸出、操作與錯誤；提供具體例子，
   清楚分開已實作、設計目標及未知項，不只給 class／檔案圖。
2. **補查依據與內容盤點**：查相關原始論文／官方技術文件，記適用情境與限制；核對
   實際內容、分布、重複與維護來源。分開標示基本工程要求、可選方法與待驗假設；
   不因某技術流行就導入，也不把外部參數／效果直接套成本專案標準。
3. **一起做一組有界決策**：每次一個部件，提出保留／調整／刪除選项、理由、成本與
   可觀察的驗收方式；集中討論會影響使用行為或研究的選擇，不逐個 helper 詢問。
   保留現有 UI 為預設；可見行為、public tool contract 或研究條件改變先明確確認。
4. **確認後施工與小驗證**：維持既有 owner／Command 路徑；同步處理直接 tests、fixtures、
   scripts、文件與無用能力。先 characterization，真 defect 先 RED，再做 focused integration。
   Engineering checks 與有界模型小驗證使用明確標記的公開工程樣例／準備用案例並保存軌跡，
   不冒稱 Development 實驗、不讀 Validation／Test 除錯。模型下載／執行仍依實際授權與
   資源限制；安全／功能與內容缺口須在可靠基礎驗收前修好，不推給後續研究。
5. **獨立覆核後銜接下一塊**：review 實際 diff、內容與證據，同時檢查未改部分的保留理由；
   無 blocker 才記本塊完成。若需跨塊修理，記清直接依賴，不把一塊完成當整體完成。
   保留無新證據不重開決策的原則；每塊不另要求完整手測或 merge。

### 建議順序與每塊出口

順序是討論提案，不把表內候選改法當核准契約。各塊均沿用上述五步。

| 部件 | 要一起釐清的內容 | 本塊出口與驗證 |
| --- | --- | --- |
| 1. Tool call／操作能力 | 現行工具如何區分開窗、填參數、直接操作、導覽與回覆；名稱／描述／schema是否清楚；缺資訊、狀態不可用、確認與成功各代表什麼；是否有重疊或缺口。 | 用代表性原話→實際公開工具→模型決策→backend／UI結果說清楚；逐工具契約與正常、缺資訊、不應操作、失敗邊界可核對，不能把開窗／排程當任務完成。 |
| 2. Context／prompt／歷史 | 模型實際看到哪些狀態、工具、規則、上一輪內容；哪些是權威、哪些只是參考；是否重複、矛盾、過期或超出 token budget。 | 保存可讀的最終模型輸入樣本；檢查資訊來源、順序、截斷、無資料／長輸入與狀態改變；不讓評分答案進入 prompt。 |
| 3. RAG 與知識／範例庫 | 它究竟補什麼；schema已足夠的情況是否需要檢索；資料來源、條目粒度、分布與更新；embedding、關鍵字混合、top-k、排序、token成本與失敗行為各有何依據。 | 盤點實際內容與獨立情境，不用總筆數冒充涵蓋；以獨立於庫內原文的準備用查詢核對相關條目命中、錯誤／無關取回、缺適用資料與延遲，修好已知內容與檢索缺口。基礎可用性小驗證不冒稱正式效益；改善幅度與一般化效果留待可靠基礎完成後的實驗回答。 |
| 4. 回合控制、確認與使用者回饋 | 一回合何時完成；缺資訊接續、格式修復、backend失敗、人工取消與Stop有何差別；忙碌、等待人工、錯誤與再次操作如何呈現。 | 正常與故障路徑含遲到／重複回覆、拒絕確認、關閉／重啟；驗副作用恰一次、舊回覆不覆蓋新狀態，重試不重送已執行操作。UI有變才做局部預覽確認，不重開已接受排版。 |
| 5. 模型與 runtime | 精確模型／模板與設定、載入／切換、離線資源、取消／釋放、冷啟動與逐題等待如何區分；現行產品與研究模型支援是否一致。 | 核对 pinned identity與可行性，無silent fallback；依授權做有界真模型 smoke及失敗／清理檢查。時間按載入、RAG準備、決策、操作分開；未量測不承諾加速，不為比較一次載入全部權重。 |
| 6. Evaluator／評估題庫／實驗腳本 | 和研究線核對已備妥題目、family分組與適用工具；scorer是否誤判、觀測是否貼近真產品；單一入口如何選實驗、保存輸入／輸出／失敗並重現。 | 評估oracle／scorer與產品路徑對齐；正常、錯誤、不操作與未完成不混算，先做判分正反例與人工抽核。沿用既有研究規格，不另定題數或擴張矩陣；正式Test只由保管者核實封存。 |

### RAG 庫數量與評估題數不混為一談

- **RAG corpus**：數原始來源、有效條目、重複／近重複及各工具／stage／情境覆蓋，
  不把改寫筆數當獨立知識。補內容由缺口驅動；top-k、混合搜尋或reranker均待具體證據，
  不是預先承諾導入。避免把失效工具、其他狀態的例子或錯誤參數當可執行指示。
- **評估題庫**：依 protocol 核對 family、類別與split的數量和獨立性；是否足以回答研究問題，
  要看每類／每工具的樣本與不確定性，不能只看總題數或把repeats算成新題。
  已公開工程例子不得改標封存Test，正式測試題／oracle不得回填RAG；Validation不參與內容調整。
- **外部依據起點**：[Contextual Retrieval](https://www.anthropic.com/engineering/contextual-retrieval)
  用於理解chunk／混合搜尋／rerank的取捨；[RAG evaluation](https://learn.microsoft.com/en-us/azure/foundry/concepts/evaluation-evaluators/rag-evaluators)
  用於區分檢索與最終輸出評估。它們不是本產品效果證據，也沒有在此核准任何最低條目數。

### 全部件整合、停止條件與接續

- 每塊都回答前輪固定的四項：實作是否過度複雜、測試是否真保護行為、不拆是否有具體
  工程理由、是否涵蓋原始完整範圍；這次另確認部件目的／內容／方法合理性，不只審程式碼。
- 全部六塊的已確認改善完成、已知重要缺陷與阻擋證據缺口處置後，做一次跨部件獨立覆核，
  核對相同候選的適用CI／真模型／Windows gates，再集中一次端到端手測。
  各塊的可見設計確認只用局部預覽，不要求每次全套重測；需要修理只驗受影響及必要相鄰流程。
- 凍結第一版時保存精確source（含所需程式碼備份身分）、模型／模板／prompt、工具契約、
  RAG內容／索引、設定／環境、題庫／scorer身分及可重跑入口；工程版本與研究B0不混稱。
  不默認複製全部資料或權重，也不把目前尚未實作的runner命令寫成已可執行。
- 可靠基礎驗收完成後，核對既有題庫與測量就緒門檻，再依授權跑pilot → 有界Development →
  Validation選版 → 凍結正式配置 → Test。Development不得先於可靠基礎驗收啟動；
  保存負結果，不以分數漂亮才結束，也不把基礎功能修好宣稱為研究改善效果。
- 只對新證據、具體缺陷、契約衝突或必要依賴重開已定部件；非阻擋改善最多列三項後續，
  不無限追加方法。壓縮不丟失決策；每次對話更新本節當前塊與next step，不另寫平行worklog。
- **目前狀態／Next**：第一輪架構／品質核對與最新user來源修理已完成；目前先完成上方
  共同工程基線整合，再從 **Tool call** 的代表情境討論六塊打磨。未下載／載入模型、
  未讀sealed Validation／Test；研究線最新工程能力已核對，但不等於共同基線已驗收。
- **本次文件驗收**：與既有研究規格的分工／基線／順序／授權不衝突，連結、guidance audit、
  strict docs build通過即交付討論計畫；不執行模型評測或以文件通過宣稱產品就緒。

### 初步審查結論與仍待討論的部件

- **可保留**：18個正式工具沿用同一backend publication、Host驗證、Command／GUI
  outcome及correlation邊界；RAG是英文操作範例檢索，不是EEG文件知識庫。沒有證據支持
  新增執行owner或重寫整套架構。
- **已修復的來源缺陷**：最新user以 `System:`／`Tool Output:` 開頭曾被誤排除，
  模型輸入與參數來源驗證回退上一要求；6案RED包含真Command錯用舊128Hz而非當前64Hz。
  `8c50bee9` 以既有history的明確 `internal` role隔離host trace，保留真人原文；
  outbound仍只有既有模型roles。331案直接回歸與22案runner回歸、獨立review通過。
  這是model-free工程修理，沒有重跑模型或把舊研究結果換標。
- **本線契約／RAG待釐清**：target對select_channels stage有矛盾、resample的number
  與實作integer不一致、repair範圍與目前terminal分界不同；不自動放寬或增加重試。
  corpus為72筆／18工具各4筆／29種tool+parameters組合，均是單步肯定正例。
  公開36正例probe至少1筆與corpus原文完全重合，不能沿用文字獨立性主張；六題
  diagnostic缺實質相關性oracle。既有34/36僅是舊檢索工程結果，不是本輪Agent成績。
  target canonical/top-2與目前semantic/top-3仍待決，未批准擴库或新方法。
- **評估腳本結論限於本線副本**：本線舊runner的dirty內容身分、完整capture、真操作
  outcome與關鍵字scorer有證據限制；不能據此判定研究線最新版也有相同缺口。
  2026-09-24 核對研究 clean `293f1890` 與產品 checkpoint `8c50bee9`，共同基點為main
  `94328196`；研究線領先main38個commits，不是舊dirty runner副本。
  研究線不只改scripts，也改controller／parser／prompt_policy／worker／local backend／
  engine／model_catalog／main_window，必須按共有契約整合，不能只複製scripts目錄。
  已核對最新入口、封存／capture與真操作觀測，整合已獲授權；在獨立候選逐一處理共有
  邊界並用公開工程案例驗證。新版本的成績另記，不把舊分數當新系統證據，
  不維護兩套互相追補的runner，不改sealed題庫或scorer政策。

## Completed record — 產品 Assistant 深度清理（整合前 checkpoint）

以下保留產品線施工與當時覆核紀錄，已固定於 `8c50bee9`；原先漏失的最新要求來源錯置
亦已修復並獨立覆核。下方數字與dirty來源描述屬當時證據，不是新整合版本的證據；
不能據此宣稱共同Agent基線已驗收。

先前把已完成切片誤報為完整模組結案的判斷已撤回。2026-09-24 重新按原始範圍比較
重要責任群的保留／收斂／拆分方案，完成 source 改善、同候選直接整合與非實作者覆核。
最後的 long-session fixture 與 capture 樣式污染亦已處置；四項原始結案標準均完成，
無剩餘已確認的 in-scope blocker。主代理已核對實際 diff、XML 與保留理由。
目前為 `64bd5fdca29ae10ea0ad089b24f3d5b41e2137d1` 加本輪 dirty diff 的本機
scope-complete，不是 handoff-ready；沒有 commit／push／PR／merge 授權或同 head CI。

### 四項結案標準與本次處置

| 必須回答的問題 | 已完成處置與判斷依據 |
| --- | --- |
| 功能必要，實作是否仍過度複雜？ | 刪 accepted 同步回呼 FIFO、重複 shutdown observer、必備依賴的 optional fallback、舊模板／metadata 尾鏈、下載清理 subclass 與 RAG 重複 filter。取消、失敗資源持有、exact correlation、confirmation 與 cache integrity 保留。 |
| 測試通過，是否真正保護重要行為？ | 真 Qt dispatcher 強制先 emit，驗 GUI 返回後處理及 transcript 順序；真 delayed shutdown 驗失敗通知與最終釋放；真 HF 停止條件取消生成 thread，空 criteria mutation 確實失敗。真 transcript／timer 保護通知重試、clear／close；兩個 CLI 真入口拒 missing／failed／duplicate／stale terminal，不以有文字判成功。 |
| 決定不拆，是否有工程依據？ | 下方逐責任群比較狀態、affinity、回呼與替代方案；已拆完整 viewport，publication 歸回既有 coordinator，不替仍大的檔案給 blanket approval。 |
| 切片完成，是否滿足原始整體目標？ | 下方原始範圍保留 Agent／tools／core／RAG、Chat、runtime、接線與相關 tests／scripts／config／docs，並揭露共享檔閱讀界線；最後整合與非實作者模組覆核已通過，不以單片 approval 代替。 |

### 邊界決策與保留理由

- **ChatPanel → ChatTranscriptView**：完整移交 widgets／layout、分批重建、六個 timers、
  reader anchor／follow-tail；Panel 保留 runtime／turn／composer／confirmation 呈現。
  四個既有 transient surfaces 借用同一 viewport，三個窄 signals 協調幾何與 replacement。
  只抽 rebuild helper 會留下十多個跨類欄位／回呼；搬到 ChatController 會混入 widgets，
  皆否決。新增 presentation class／責任 owner 一個，但沒有新增可變 history／runtime policy。
  刪 Panel 舊 append／layout 相容入口，產品 capture 與 tests 全部遷到真正 owner。
- **Publication → 既有 coordinator**：bridge、rendered revision、兩個 retry timers、
  render commit 與 training notice 歸同一 owner；Manager 只提供 status／terminal rendering、
  idle 查詢三個窄 ports。只搬 projection 仍需跨類拼裝同一 retry transaction，另建 owner
  無必要；因此由既有 coordinator 直接擁有 Qt lifecycle，刪 schedule DTO／test-only snapshot。
  Assistant 不 acknowledge Desktop，失敗 obligation、latest revision、clear／close 保留。
- **Controller 保留的組合責任**：generation／worker／RAG shutdown 共同處理 affinity、
  回呼斷線、late callback fence、failed close retry 與 release。搬往 GUI Lifecycle 是反向
  依賴與錯 thread；另建 shutdown owner 需大量 resource ports 或整個 Controller proxy，
  沒有移除政策。proposal／confirmation／execution 已交既有 policy、pending、tool owners；
  debug 只保留 model-free origin，執行鏈共用，另拆只會新增 history／metrics／terminal 接線。
- **Runtime 保留不同生命週期**：admission reservation 在 Controller 綁定前；delivery ACK、
  terminal-before-ACK、startup rollback、dispatcher cleanup 不是同一狀態。
  deactivation 可重新啟用，永久 close 不可，不能盲目合併。physical cleanup 由 dispatcher
  單一回報，刪重複 observer；未 bind startup rollback 與 failed cleanup ownership 仍必要。
- **Manager 保留兩個呈現入口**：normal/debug 的 composer、rejection 與 copy 不同，但
  reservation／reject／matching commit 只有 turn_state 一個 owner。抽共用 helper 需新增
  錯誤 taxonomy、文案 flags 或 callback 協定，沒有刪除 state policy。command-in-flight
  與含 GUI handoff 的 turn RUNNING 語意不同，不能以後者替代 Stop 門禁。
- **Core／RAG／tools 保留信任界線**：process owner 與 model-thread lease、persisted
  integrity 與 operation lease、tool schema 與 backend capability 各保護不同邊界。
  Dispatcher 的 optional shutdown signal 有真 scripted walkthrough controller consumer，
  同步 close 是其正式生命週期；不是為測試保留。兩現行模型原生 system role，已刪無用
  capability 欄位與不可達 template fallback，現行 prompt／token budget 不改。

### 授權、複雜度與整合規則

- **Outcome／非目標**：維持既有可見 UI、功能、18 tools、模型／prompt／RAG policy、
  Command 與 EEG 語意。不改研究 scorer／題庫／artifact、使用者 settings、其他 worktree，
  不下載或執行 commit／push／PR／merge。既有 Evaluation／Saliency 修改保留、不計本次增量。
- **複雜度**：唯一新增 class 是完整 viewport presentation owner；其餘責任歸回既有 owner。
  首次 viewport 候選 +804/-734，觸及略超1,500行的 architecture exception 明確限於完整
  layout／六 timers／anchor／rebuild 移交，無有效的半遷移中間態，不用 facade 或壓縮碼避門檻。
  四大檔並非字數達標就結案；按上列實際耦合選擇拆分或保留。
- **驗證方法**：Windows native、timeout／core=0、先 passing characterization；
  發現真缺陷再 RED→GREEN。保留失敗報告，不以放寬 assertion 消除紅燈。
  模型、時鐘、外部 IO 可隔離；queued delivery、transcript、timers、QObject 銷毀採真實機制。
  Source-bound capture fingerprint 包含新 viewport 與 coordinator；bytes mutation 會改 fingerprint。
- **整合中發現**：截圖量測把 QRect inclusive bottom 算多一像素，已補12px接受／13px拒絕
  邊界測試並修量測式，門檻未改。整組失敗已定位為 UIUX capture tests 未還原 QApplication
  style（native空白12px、裸Fusion14px、正式完整theme10px）。還原後又揭露四個截圖測試
  隱性依賴前例的Fusion；已明確套用正式capture樣式並在各測試後還原，不改圖像門檻。
  整組371通過，session結束樣式仍是原windows11，不留跨測試污染。
  Long-session 舊 runtime fixture 缺必要 signal 且使用同步 submit，已遷 Qt queued delivery，
  原資料／流程／延遲斷言不改，含202回合 soak 的24案通過。
- **回退／基準**：本次 before 為
  `/tmp/xbrainlab-agent-boundaries-before-20260924.iEtqAF.tar.gz`，只撤 owned patch。
  下方以前階段數字不重計為本次成果；測試組有重疊，不能相加宣稱 coverage。
- **結案／發布界線**：同候選直接整合、文件同步與非實作者四項結案核對完成。
  正式發布另需授權與同 clean head applicable CI／人工 gates；本機深度清理不等於
  handoff-ready，不因本輪結案自行建立PR或要求合併。

### 原始範圍與保留理由

以下是模組／直接共享路徑覆蓋，不宣稱整個 repository 或所有測試逐行閱讀。
非實作者覆核包含未修改的 source，不能以單片 approval 取代模組結案。

| 範圍與入口 | 責任／去留 | 閱讀與直接證據 |
| --- | --- | --- |
| `llm/agent` 27 檔（含 package） | Controller 組合 turn；orchestrator 擁有 correlation，pending owner 擁有待決互動；保留 parser/schema/origin/confirmation/publication 邊界。刪舊入口、未用參數／DTO／欄位及不可達 handoff 路由。 | 全 source；大型 controller 測試讀相關 fixtures／案例及全部增量，非全測試逐行。正式 parser、18-tool producer、取消與原生 import dialog 路徑。 |
| `llm/tools` 10 檔＋action contracts／pipeline | registry/schema→capability→Command 或 typed UI request，不新增 policy owner。分類與 model-facing projection 保留真 consumer；結果歸既有 ToolCommandResult。 | 全 source、直接 caller；工具／verifier 與真 public projection 的 hostile、cyclic、redaction 測試。 |
| `llm/core`／backends 11 檔 | config→resolver→process owner→child engine→local backend。保留 exact model、quota、consent、設定 migration、失敗時持有資源。刪假 owner/thread fallback、無用 config API 與無 producer fallback 標記。 | 全 source；config 全測試，其他直接 fixture／案例和全部 diff；實際 process ownership tests，未下載或重跑真模型。 |
| RAG 6 Python 檔＋bundled corpus | retriever 擁有 client／embedding，indexer 借用；manifest/digest 為持久化信任檢查。BM25／ranking／corpus 保留不變。 | 全 source、indexer/security 全測試及直接 retriever 案例；未將單元回歸冒稱新模型準確率。 |
| Chat 13 檔＋ChatController | 保留呈現、scroll、bounded history、restore 與確認。typed history 唯一可變紀錄；viewport 責任已完整移交，刪隱藏 renderer、無用樣式／icon、雙 list 和不可達 update transport。 | 全 source；native chat／controller、真 subscriber reentry、anchor／rebind／delete-during-rebuild 與202回合兩次 prune，非只有 panel queue。 |
| Manager／runtime／dispatcher／publication／presentation／status | 既有 owner 分掌 Qt affinity、turn admission、resource lifecycle 與 publication acknowledgement；identity 各守不同 async 邊界。刪測試専用入口與無效傳遞，Stop 晚到 navigation callback 用既有 lease fence。 | 各 owner 全 source 由分工覆蓋、主 agent 查實際 diff；真 Qt activation、取消、關閉／重試及 revision tests，無新控制層。 |
| workflow host／router；settings/download／MainWindow 接線 | 真 GUI completion 留在既有 dialog／panel owner；只保留 registry 產生的 Agent routes，lazy navigation／command pending 不是成功 terminal。Settings standalone、app-parent download 與 optional manager 有實際使用情境。 | host/router/settings 全檔；MainWindow 等共享檔只查 Assistant 直接路徑。真 import dialog 取消、Stop 後 callback 及訓練設定路由回歸。 |
| 產品 capture／DPI／RAG／setup scripts、profiles | local 單回合、雙回合、UI geometry、DPI 與人工 profiles 各有不同 consumer，不刪有用途腳本。capture 成功需 matching request＋typed result＋successful terminal，不以有文字判成功。 | 兩個 local CLI、UIUX／DPI／driver／contract／capture config／fixture／5 profiles 全讀；巨大共享 capture、setup、verify 等只讀相關路徑。研究 evaluator 僅同步內部參數，scorer／題庫不改。 |
| 相關 tests／fixtures／arch guards | 保留真外部資源隔離；刪無效入口専屬 AST 模擬器／白名單，保留 hostile payload、failed-close、stale／duplicate 保護。 | 各區清楚區分全檔與直接案例；passing counts 不代表 coverage 提升。尚無本輪 coverage 百分比或全產品 CI。 |
| 文件／設定／開發規則 | current architecture 擁有實際責任；now 記錄結案與發布界線。refactor workflow 要求原始模組範圍獨立結案。 | guidance audit／strict docs build；不碰使用者 settings、模型政策、研究 worktree。target 的 select_channels stage 文案矛盾只列非阻擋 follow-up，不偷改契約。 |

具名保留：`compact_tool_state.interpretation` 有真 backend snapshot producer；parser
`_BARE_COMMANDS` 仍用於 malformed-output 診斷，不是執行兼容入口。未用 result／metadata
專屬測試已移除或遷到真 producer，hostile payload、取消／stale／duplicate 安全斷言保留。
Controller／Manager 仍大，但已評估並否決只搬行數、增加 adapter 的微型抽取。

### 本次追加清理的改動與證據

相對本次 boundaries before，不含前階段、Evaluation／Saliency 或 main：production 14檔
+1050/-1381（淨減331），tests 22檔 +1582/-709（淨增873），scripts 7檔 +112/-71
（淨增41）；文件與流程規則另計。測試增加包含真行為 oracle、失敗時序與正式入口基線，
不是為 deleted helper 留相容測試。尚未量測 coverage 百分比。

目前大型檔案：Controller 2420行、Manager 1447行、RuntimeLifecycle 1477行、Panel 1426行；
新 viewport 752行。這些是維護風險訊號，不是零風險保證，保留理由以上方責任分析為準。

以下為同一未提交 candidate 的 Windows native focused evidence，各組重疊，不相加：

- UI／admission／publication／ChatController／RAG：568通過；最後 canonical import 調整後的
  publication＋architecture另269通過。
- Runtime units330、runtime／offline context integration24、core template／取消64、
  downloader／lifecycle75、catalog38均通過。Downloader最初Windows長路徑fixture失敗，
  改短pytest專用temp後通過，沒有改模型／cache政策。
- Product UI walkthrough10通過；long-session24通過，含202回合／兩次prune，
  每回合 terminal 與 admission exact correlation 一致。
- 六個source-bound capture／DPI script test files整組371通過，零失敗／錯誤／跳過；
  樣式隔離7個focused正反例亦通過，原12px與影像門檻不變。
- 所需 Ruff／format、修改production typing與兩個local CLI typing通過；guidance audit、
  strict docs build通過。共享 evidence script 的既有 QLabel optional typing 診斷仍存在，
  未把該整檔宣稱零診斷。

XML 位於 `build/assistant-cleanup/`；紅燈、mutation與前候選報告保留原意，未改標成綠燈。
沒有本次真模型新實驗、新機網路安裝、clean-head CI或新版人工驗收；不宣稱全repo逐檔
或所有測試逐行讀完。目標文件 `select_channels` stage 文案矛盾是另需契約決策的非阻擋
follow-up，不在本輪偷改公開契約。

### 前一階段驗證與限制（不是本次深度結案）

以下均為 dirty working tree 的 Windows native、model-free 證據；不是 clean-head CI、真人
workflow、模型準確率或論文結果。各組有重疊，不相加宣稱 coverage：

- 最後批准尾項完成後：Agent＋architecture **1179 passed**；tools/root **185 passed**；
  UI **388 passed**；Agent／runtime／LLM integration **80 passed**；native host／Import／Stop
  與相關 host units **57 passed**；source-bound scripts **316 passed**。原始報告保留在
  `build/assistant-cleanup/`，均正常 exit0。
- Response/parser 同選集在施工前為497通過、兩個新增 fixture 缺少 json import；補 import 後
  該兩案在 production 修改前通過。施工後 **498 passed**，僅刪一個未用 natural-language
  capability 專屬案；evaluator recovery／trajectory **9 passed**。108個現有公開 parser 測試
  literal、432次 recovery 對照，其保留欄位／action／七個 taxonomy 字串逐項一致。
- 尾項 direct Ruff／typing 與分片覆核已通過。此尾项對 before archive：production 15檔
  +51/-379（淨減328），tests 20檔 +201/-325（淨減124），scripts 無新增變更；文件另計。
- 整輪重開清理對 reclosure before（ChatController 使用獨立 before）：production 43檔
  +259/-1750（淨減1491），tests 52檔 +1279/-2212（淨減933），scripts 8檔 +96/-30
  （淨增66）；workflow 1檔 +10/-10。這不含此前 Saliency／Evaluation／第一輪 Agent 修改。
- 較早候選證據保留：core281、RAG107、UI／ChatController652、git-bound scripts316 曾通過，
  不重標為尾項後執行；Stop 有真 Manager callback RED→GREEN。早先 Flow72中一個舊 fixture 參數已遷移，
  原失敗未改標成功。腳本最初16個失敗來自兩個長路徑、兩個抓圖 seam、12個空 Git identity；
  以短 pytest-owned 路徑、明確外部 seam 及正確 Windows Git metadata 修正後重跑，不關閉檢查。
- 既有 cache 真離線 RAG gate 曾通過（72 points、Top-3 34/36），未做新機完整安裝／網路下載。
  另一次舊跨域單 process Qt teardown timeout 未證明原因，沒有宣稱已修；採既有隔離 runner。
  歷史數字不當作本次真模型或人工驗收，也不修改研究 sealed cases／scorer／舊 artifact。

先前 reviewer 的廣泛結論已撤回；上述測試與有效清理保留，不回寫成新候選證據。
本次責任群替代方案與最終整合結果已在上方補齊。尚未量測完整 coverage 百分比。Current 責任見
[Agent 架構](../architecture/agent.md)，安裝限制見[本機環境](../developer/local-setup.md)；
本頁不保留逐片施工流水帳。

## Current — Evaluation 內部清理與補測完成，尚未發布

使用者已要求依逐模組六項準則，加上完整範圍清單、數值／不必要工作檢查、獨立 reviewer
退件權審查 Evaluation；隨後授權不改 UI／功能／資料語意的清理與補測，並明確授權五個
無產品 caller 的舊數值 API 退役。已完成修理、補測及非實作者交叉覆核，無剩餘已確認
的 in-scope blocker。下方 UI 迭代是歷史證據，不是新的待辦。
這是本機 scope-complete，不是 handoff-ready：仍為 `64bd5fdc` 加本輪 dirty diff，
沒有 clean head CI，也尚無 commit／push／PR／merge 授權。main 與使用者 settings 未改。

- 範圍：產品 Evaluation（非 Assistant 評測研究線）：render publisher／work、panel 與
  四個呈現檔、EvalRecord／TrainRecord／Evaluator 的結果與分類計算路徑、analysis/service／
  state／UI ports 直接邊界、相關測試與 product evidence scripts。共享檔只審／改相關段落。
- 證據：三路独立唯讀審查確認：相同 Evaluation signature publication 清掉已顯示 DTO，
  百分比 checkbox 後續不更新；舊 backend get_confusion_figure 只有測試 caller；部分
  回呼便利分支／DTO 欄位／work API 無正式 caller；數值 oracle 對稱或只驗 support；
  screenshot readability 只驗整張 canvas，20 類 canvas2028×1809／viewport968×526
  仍回 fully_visible=True。數值真 probe 正確，100k×4 pooled read 約5.15–5.56ms，
  尚無可支持的效能 blocker，不新增 cache／worker 或架構層。
- Outcome：上述已確認缺口關閉；入口、責任、去留、保留理由及測試對應逐塊覆核。
  保留現有排版、完整名稱可捲動、統計 pooling 定義、public Command/query、split／
  producer identity、immutable DTO、取消／stale／close／publication 保護。
- A 完成：populated panel no-op publication 先 RED 再修；刪 test-only callback／work／
  UI adapter leaves，producer serialized contract 不改。此切片 production +9/-60，淨減51行。
- B 完成：不對稱、unequal-fold、未完成 sentinel 手算 oracle；刪 backend confusion
  plotting、`TrainRecord.get_acc/get_auc/get_kappa`、`EvalRecord.get_auc/get_kappa`，
  保留有正式 caller 的 `EvalRecord.get_acc`。AUC 收回既有 Evaluator，不留多餘 helper；
  數值／持久化 oracle 移到正式 scorer 與獨立 sklearn 對照。production +3/-174，淨減171行。
- C 完成：canvas 完整／viewport 可見／捲動可達分開判定，必要 gate 不放寬；真 widget
  回歸與真 service→panel workflow 已完成。evidence script +24/-3；沒有刪整支正式腳本。
- 以上內部 A/B 共 production +12/-234、淨減222行，與前輪 Saliency／Evaluation UI
  diff 分開計算；不以整個 dirty worktree 當本次新增量。新 owner／module／class 均為零。

### 最終 focused evidence 與獨立覆核

- Windows Evaluation UI／ports／read-side architecture：183 passed；
  `build/evaluation-ui-preview/integrated-native.xml`。
- 數值／record persistence／render／deterministic pipeline／training history：144 passed；
  五 API 退役獨立覆核另選18項通過（不與前述數量相加）。
- 最終真 training→persisted results→Evaluation Windows workflow：1 passed；
  `build/evaluation-ui-preview/service-workflow-native.xml`。
- source-bound evidence focused：34 passed、197 deselected；
  `build/evaluation-ui-preview/evidence-viewport-native.xml`。
  前兩次33/34的原因已查清：WSL建立的worktree `.git`含Linux絕對路徑，Windows Git
  無法查來源而回空 digest，不是已證實的source drift；僅在驗證程序指定正確Windows
  `GIT_DIR`／`GIT_WORK_TREE`後通過，未改Git metadata／產品／斷言。
- 最終來源的既有 `run_public_cross_source_training_smoke.py --format json --strict`：
  4 passed、0 missing／failed；EDF／GDF完成訓練與artifact reload，EEGLAB／CNT保留
  import／preprocess及缺少足夠class語意時阻擋監督epoch，不能宣稱四者都做了訓練。
- 修改檔 Ruff／format、production typing、diff check 通過。共享 evidence script 的
  Assistant label 可空型別診斷在 HEAD baseline 已存在，本輪未改其行為，不冒稱該整檔零診斷。
- 非實作者覆核實際diff與證據：生命週期／數值與API／evidence producer／真service
  integration／測試替代／範圍完整性均無blocking finding；不是實作者自己的PASS宣告。
  合成fixture不代表科學品質；新integration未涵蓋Validation split或model-summary真worker
  失敗，不替代既有窄層保護，也不替代未來同headCI／真人Windows驗收。

### Evaluation 範圍盤點與保留理由

以下是本模組範圍，不是全專案逐檔審查。完整閱讀的專属核心為
`ui/panels/evaluation/` 五檔（含匯出入口）與 `application/evaluation_render.py`、
`evaluation_work.py`；共享檔只涵蓋列明路徑，沒有把搜尋命中當作讀完整檔。

| 區塊／入口 | 清理或保留判斷 | 直接保護 |
| --- | --- | --- |
| Service → render publisher → immutable DTO | 保留來源／split／producer／選取前後驗證、不可變複本；跨 Fold 限同 cohort／round／Run、互斥 Test masks；先 pooling predictions 再算 metrics | render tests：不對稱手算、unequal-fold、未完成排除、來源與 stale 拒絕 |
| Service → evaluation work → shared registry | 保留 admission／single claim／checkpoint／commit fence；刪無正式 caller 的 cancel／snapshot 轉接，不另建取消 owner | work tests：取消、重試、single claim、request identity |
| Panel → typed UI ports → worker → charts | 刪 test-only callback overload、wait helper、未使用 DTO storage、舊 scalar split fallback、無 caller 的 UI 同步 adapter；真正 service 同步入口仍供 scripts 使用 | publication／panel／read-side tests；真 service workflow |
| Model summary 與 Qt lifecycle | 保留 bounded cache、request/worker identity、pending latest、terminal callback 後釋放及 shutdown／cleanup 差異；這些分別保護可重現 stale／關閉邊界，不是第二套業務真相 | summary failure、A→B→A、取消／close／late callback tests |
| Confusion matrix／bar chart／table | 只呈現 detached 數值；保留既有 label 量測、局部捲動、figure cleanup；百分比只影響矩陣，不改 metrics | 真 artist／table 數值、geometry、wheel／pixel、空／錯誤狀態 |
| EvalRecord／TrainRecord／Evaluator 分類與結果路徑 | 刪舊 backend confusion plotting 與專屬 tests；五個已授權便利 API 已退役；保留有正式 caller 的 accuracy、history figures、持久化與 split 讀取 | evaluator／record／deterministic oracle；真保存結果重新讀取 |
| analysis／service／state／ports 相鄰邊界 | 保留既有 Command/query、正式 serialized catalog 與 revision；不另增 owner／receipt／compatibility path | analysis 相關測試、UI ports、read-side architecture |
| Product evidence scripts | baseline、polish、human-like、visualization walkthrough、native smoke、source-diverse、MOABB journey／UI capture 均有不同正式用途，沒有已證實可刪的整支腳本；只修 canvas 完整被誤當 screenshot 完整的證據 | 真 4／20 類 widget、既有 evidence consumers／manifest gate |

測試清理保留行為對照：舊 backend plotting 三個專屬案例隨能力刪除；重複的 Evaluation
model-summary callback「integration」案例刪除，獨有 visible／capture 斷言併入原三種錯誤
component test（該兩檔 7→6 cases，實際通過）。真 service integration 另走
FIF→epoch→兩 Fold×兩 Run CPU 訓練→保存／載回→Run／Train／Test／Summary／跨 Fold→
真 publisher 失敗與恢復→reset／close，直接檢查 matrix／table／三組 bars，不偽稱
model-summary 真 worker 覆蓋，也不以合成資料聲稱科學有效性或來源多樣性。

目前沒有量測到需要新 cache／thread 的 Evaluation bottleneck。Panel 與 publisher 仍大，
但不為縮行把有共同生命週期的狀態搬成新控制層；此次新增 owner 數為零。

### 已完成 UI 迭代與當時證據（歷史記錄，不取代上方結案狀態）

- 觸控板追加修理（使用者已授權，不改排版）：原生診斷證實 angleDelta 水平事件能捲動，
  pixelDelta-only 事件在 canvas → viewport 後被忽略（bar 100→100）。尚未擷取使用者
  實體觸控板事件，不將此重現等同完整裝置驗收。
- Outcome／steps：先加入真 chart 的像素位移 RED，涵蓋水平／垂直、雙方向、細小位移、
  混合 pixel／angle 不重複捲動與邊界；在既有 canvas 處理像素位移，保留 angle 路徑。
  focused native tests／typing／review 後重開獨立 Windows 預覽並帶到前景。
  不新增手勢 owner／全域攔截／設定，不改其他 panel；Stop 為修理證據完成且預覽可操作，
  實體雙指操作仍交由使用者確認，不提前開始後端清理或重型 gates。
- 觸控板修理結果：新回歸先重現 pixel-only 不動與 mixed delta 錯誤距離；existing canvas
  現直接依 pixelDelta 更新兩軸既有 scrollbar，Qt 自行限制範圍；像素優先且不再套一次
  angleDelta，不重複反轉平台已處理的自然捲動方向。沒有 pixelDelta 時保留原 Qt 路徑。
  垂直短圖最大位移不足 120 的 fixture 改用 30px 精確距離驗證，另保留兩端 clamp 檢查。
  Windows focused 44 passed（`build/evaluation-ui-preview/touchpad-native.xml`），Ruff／
  Basedpyright 通過。獨立 reviewer 讀實作與 artifact，無 blocking finding；實體裝置事件
  送達仍未驗證。已替換舊版，重新以獨立 Windows 程序開預覽，不依附工具終端。

- 最新確認：上一版矩陣偏右上、比例不佳，UI 尚未接受。使用者同意跨 Fold 的
  `Run 1 (Summary)` 改為 `Run 1`（各次序號保留）；單一 Fold 內的多 Run 彙總仍為
  `Summary`。矩陣改回较大、置中的正方形；放不下兩張圖時提前使用既有 chart tabs。
- 已重現滾輪缺陷：真 Windows canvas 收到 wheel 後 accepted，但垂直 scrollbar 留在
  0；同事件送 scroll viewport 則前進到 200。Matplotlib 消耗事件，未交給外層捲動區。
  修理只讓 Evaluation chart canvas 將捲動交回 Qt，不改全產品／資料或新增捲動 owner。
- 本次步驟：wheel 真事件 RED（上下／水平／邊界）與矩陣 square／center／大小回歸 →
  既有 canvas、panel layout 與顯示字串最小修理 → 相鄰 UI tests／截圖 → 開新 Windows
  隔離預覽。原生可操作預覽是本次終點，UI 確認前不宣稱 Evaluation 模組結案。

- 使用者已確認修理長 class label 擠壓、下方資料列推擠圖表；Run 彙總名稱指定為
  `Summary`，單一 completed Run 不顯示、至少兩個 completed Run 才提供。追加檢查
  Fold／Run／Split 下拉選單是否有 Saliency 同類白邊，確認缺陷才修。
- 證據：metrics table 以最多 12 列同時設定 min/max height；圖中文字主要依畫布寬度
  而非 label 長度排版；on_model_changed 只要有任一完成 Run 即加入舊 Summary 文案。
  白邊尚需 Windows pixel／原生檢查，不以相同元件推定已重現。
- Outcome：長名稱仍可讀、多列在表格內捲動而不擠壓主圖、單次無冗餘彙總、選單深色
  背景連續；保留 run identity、跨 fold 彙總、split、計算與 publication 語意。
- Scope：Evaluation 既有 UI 元件與直接測試；優先重用現有 popup 呈現方式，不新增
  backend owner，不改其他模組樣式、不展開 Evaluation 後端清理、不動 main 或設定。
- Steps：真 widget／繪圖與 native popup 建立 RED → 最小 coherent UI 修理 → focused
  regression／geometry／pixels／lint → 開 Windows 隔離示例預覽並確認有回應。
- Validation：短／長 class 名、多列／少列、縮窄再放寬；單次／多次／未完成 Run、選取
  與 split 保留、popup 頂底背景及清單末列／鍵盤可達。模型與昂貴計算可在預覽隔離。
- Stop：使用者可直接操作本次 changed-surface 原生預覽；等待 UI 設計確認後才進行
  內部清理與重型／正式 gates。Saliency 已結案 dirty slices 保留，不重做或發布。
- 已重現：Windows 三個 popup 的頂／底白邊（2／50 項），以及 metrics 3→40 列時
  plot group 高度 467→248；先 RED 再修。popup 只改獨立 frame 背景，無全域樣式改動。
  長清單初次末列失敗是 fixture 在 native window exposure 前開 popup，修為等待真實
  exposure，保留像素與末列／鍵盤斷言，不增加 production 捲動 workaround。
- Summary 已使用至少兩個完成 Run 的条件，保留原 identity／split／跨 fold 路徑；舊
  summary freshness／失敗案例改用兩個完成 Run 作 fixture，沒有刪除這些保護。
- 長標籤第一版雖通過 non-overlap，但 native screenshot 四類別仍需過量捲動，因此
  不作交付；正調整現有 canvas 的文字量測／換行／軸間距並保留很多類別的局部捲動。
  表格取消依列數強制增高，保留短表上限與長 class tooltip；不碰 backend 數值。
- 上一版 UI 候選（未接受）：普通四類長名稱在 460×350 圖區完整可見且無捲動；matrix 完整換行／
  X 軸直排、寬高獨立分配，很多類別才局部捲動，不縮為 7／8pt。長→短→空資料會
  釋放多餘捲動範圍；現有 canvas 共用，無新 owner／模組／類別。
- 上一版直接證據：Windows 五個相關 UI test files 共 101 passed，四個 production files
  Basedpyright 零診斷、Ruff 通過。`build/evaluation-ui-preview/focused-native.xml`；
  獨立 reviewer 檢查 Summary identity、table sizing、canvas lifecycle／resize 及原生
  圖，無 blocking finding；這不是 Evaluation 後端結案審查。
- 已開 Windows 原生預覽：`build/evaluation-ui-preview/preview.py`，標示合成資料，
  使用真 panel／chart／controls 與隔離 runtime；可切短名／長名／20 類及一／兩次完成
  Run，不使用研究模型或使用者資料，不改 main。Qt timer 已確認 window visible、
  platform windows、五列表格、Run 1／Run 2／Summary，截圖已人工視覺檢查。
- 本次修正結果：跨 Fold 顯示 `Run 1`／`Run 2`，同 Fold 多完成 Run 的 `Summary`
  不變。矩陣恢復置中正方形，保留完整水平換行名稱；plots／details 分配調為 3:1，
  兩圖不能等寬容納時使用既有頁籤。滾輪事件只從 Evaluation canvas 轉送至既有
  QScrollArea viewport，保留方向、delta、phase、device 與事件接受狀態。
- 獨立覆核另重現 1500／1600 中間寬度仍溢出：原門檻將兩張圖所需寬度相加，
  實際並排卻等寬分配。補原生 RED 後改為兩倍最大需求，加間距；回歸涵蓋窄／中／寬
  來回切換、selection 保留、真正上下／水平 wheel 與捲動終點，不只直接操作 scrollbar。
- 本次直接證據：Windows 五個 UI test files 107 passed，artifact
  `build/evaluation-ui-preview/revision-native.xml`；三個本次 production files Basedpyright
  零診斷，Ruff／diff check 通過。跨 Fold 名稱另有 backend／UI／capture script focused
  33 passed（與 UI 群組重疊，不加總）。已檢視原生四長名稱截圖，無多餘捲動、圖方正置中。
- 獨立 reviewer 以小型 Windows 診斷覆驗 1280／1400／1500／1600 頁籤與 1800 並排皆無
  水平溢出，原 finding 已關閉；本次 wheel／geometry／layout 無新 blocker，不代表後端結案。
- 新版原生預覽已開啟，Qt timer 確認 visible／windows／五列表格及三個 Run 選項。
- Next／Stop：等待使用者確認本次修正版 Windows 預覽；尚未展開 Evaluation 後端清理、正式重型 gates
  或 PR。已接受的 Saliency 不重測，不把預覽視為完整 workflow 手測。

## Current — Saliency 清理已結案，尚未發布

2026-09-23 使用者確認改由 Saliency 往前討論，Import 最後；先建立隔離工作區與保存
計畫，不修改正在手測的 main。工作區 `XBrainLab-product-workflow`，分支
`refactor/product-workflow`，起點為已接受的 main `94328196`（PR #146）。
本節保留先前取代「Import Wizard 優先」的決策；最新 active scope 以本文件頂部為準。

目前沒有尚未完成的 Saliency 施工切片。使用者已接受 UI；內部清理與最後三項缺口
已完成，非實作者已按下列六項準則獨立覆核，未發現新的 blocking finding。
這是本機 `scope-complete`，不是 `handoff-ready`：來源仍為 `64bd5fdc` 加本輪 dirty diff，
尚未獲得 commit／push／PR／merge 授權，也沒有對應 clean head 的 CI。
Saliency 先保留未發布成果；Evaluation 最新授權以本文件頂部 active slice 為準。
以下保留的施工證據不是新的派工，不因 context recovery 重做已完成切片。

### 已完成並接受的 UI 修理 — Saliency 縮窄時功能列文字擠壓

- 使用者追加回報：調整視窗寬度時 Saliency 功能列文字疊在一起，明確要求先修這項 UI，
  再繼續內部清理與獨立審核。既有其他 UI 接受保留，不重新整套手測。
- 初步線索：panel 的 responsive grid 以固定 700／760 門檻及 ctrl_bar／panel 寬度估算
  選擇 layout；需用真 Qt geometry 確認縮窄／再放寬是否採到 stale width、是否低估文字與
  controls 實際需要的寬度。這是待驗原因，不能只改門檻猜測修好。
- Outcome：支援視窗寬度與 Windows DPI 下標籤／選擇框／checkbox 不重疊或被擠掉，
  窄寬來回調整能正確換行；保留功能、選取、busy／cancel 行為與既有文案。
- Scope：只修 Visualization 功能列及直接受影響的 layout／geometry tests／原生預覽；
  不新增 backend owner、不改 EEG／計算語意、不同步做後端清理。若發現不同 UI 設計取捨另確認。
- Steps：真實 widget 縮放重現並補 RED → 既有 layout 內最小修理 → 同測試與相鄰控制列回歸
  → Windows native 縮放預覽，明示示例資料、確認有回應後讓使用者看。
- Validation：連續縮窄／放寬、長 method／class、Absolute 顯示／隱藏、選取不丟失、
  控制列 containment／文字尺寸／不重疊；檢查 100／125／150% 的直接 changed surface。
  此設計確認前不重跑全套 compute／跨平台重型 gates。
- Stop：本 UI defect 的直接證據收齊並展示原生畫面；確認修理後再恢復下方內部三項未結工作。
- 已重現與修理：嵌入 panel 在 1180 寬（bar 880）仍採 wide，Run label 與 Fold combo
  的 QRect 實際相交；側欄隱藏時亦重現。先建立 RED，再改為聽取 bar 自己的 Resize／Show，
  由既有 QGridLayout 的實際 minimumSize 選擇可容納的一／二／三行。避免寬版 minimum
  size 反過來鎖死 window 縮窄；保留窄版最小寬度，修正 wide 未還原 class combo 寬度。
  不縮字、不隱藏功能、不新增佈局 owner，不改計算或資料流程。
- 直接驗證：Windows panel suite 123 passed，125／150% 各 4 個連續 resize regression
  passed；包含 embedded／top-level、側欄顯示／隱藏、長 method／class、真選取保留、
  Spectrogram 的 Absolute 隱藏／還原、文字尺寸／containment／無重疊。Ruff 通過。
  150% 初次 top-level 測試因要求超出螢幕的寬度失敗，改以螢幕可用寬度測 top-level，
  embedded 仍保留完整寬度範圍；未放寬文字／重疊斷言。另修測試 parent/child teardown。
- 原生預覽：build/saliency-ui-preview/resize_preview.py 使用真 panel controls 與隔離示例
  選項，renderer／計算不執行；Windows 三倍率截圖位於同目錄 resize-*。已檢視窄／中寬
  圖，預覽不是正式 workflow handoff。使用者已明確回覆「沒問題了開始修後端吧」，
  本 UI 修理已接受；不重測其餘已接受 UI。單檔 Basedpyright 零診斷。

### 已完成 — 內部責任收斂與取消證據

- 問題與 outcome：處理獨立 reviewer 提出的三項缺口；在已接受 UI baseline 上消除
  3D 重複 lifecycle presentation，補真 3D 取消／重試，量測昂貴 evaluator 的取消耗時。
- 切片 A：先用正式 panel 的 unavailable status 與 pending runtime probe 回歸保護可見
  行為，再刪 3D 的 status field／setter／重複提示與 test-only 入口。Panel 仍是呈現 owner，
  backend publication／native commit／generation fences 全部保留，不新增 owner。
- 切片 B：沿用既有真 GUI／Assistant fixture 與 EEGNet／Captum，在 Windows interactive
  3D 驗 compute → 重算 → prepare 中取消 → late callback → 再算成功及關閉。CPU attribution
  與互動 VTK 真實執行，僅用可釋放同步 barrier 定位取消時點；不以 stub scene 取代證據。
- 切片 C：先量測代表性 Gradient／SmoothGrad workload 的取消請求到 worker 結束，區分
  UI 接受、拒絕 publication 與實體釋放；不以預設性能目標新增 cache／worker。若需修改
  合作式取消粒度，先記錄量測、直接 baseline／失敗回歸、caller、同值與原子性保護再施工；
  可見語意或新架構取捨另提決策。
- 驗證：各切片 focused baseline／回歸，資料／非同步獨立覆核，再整合六項結案準則。
  保留既有 dirty slices；限定檔案可分別回退，不以全 worktree reset 回復。PR／merge 尚未授權。
- Stop：三項逐一有實際結論與直接證據，再請未參與實作的 reviewer 判斷模組結案；
  不因一批測試綠燈就宣稱全模組乾淨，也不以未知項自行轉 follow-up 結案。
- 取消 baseline：Windows CPU／Torch 4 threads，固定 seed 未訓練 EEGNet，128×32×256
  合成輸入、batch 16、SmoothGrad 預設 5 noise samples。首個 forward 後發取消標記，
  evaluator 仍跑完全部 8 batches；Gradient 8 forwards／83–89 ms，SmoothGrad 16 forwards／
  455–468 ms（各 3 次）。這是 evaluator tail，不是 GUI end-to-end 或所有硬體延遲。
  evidence：build/dev-artifacts/saliency-validation/cancellation-before.json。
- 最小修理決定：唯一 production caller TrainingPlanHolder 已持有 should_cancel，直接
  傳入 evaluator，在進入工作、每個 batch 與各 attribution 方法間檢查；沿用既有
  StaleSaliencyUpdateError 及 manager 的取消／拒絕發布／cleanup，不新增 owner 或 thread。
  要求是取消後不再啟動下一個計算單位；已進行中的單次 Torch/Captum 呼叫仍合作式完成，
  不承諾硬體搶占或固定毫秒上限。先 RED 驗 pre-cancel／forward 中取消／noise 中取消、
  false callback 下同 seed 同結果，再修改 evaluator + holder 兩檔及直接測試。
- 最後結果：A 刪除 3D 重複 status／setter／提示與 class coverage map，八個真 panel／
  late probe baseline 在刪除前後通過；Panel 是唯一 lifecycle 呈現 owner。B 真 Windows
  GUI／Assistant → EEGNet／Captum → 3D 取消／晚到結果拒絕／重試／native cleanup 六案
  全通過，檢查互動 QtInteractor、actors、finite scalars 及有空間差異的 framebuffer。
  C 取消訊號已傳入 evaluator；真 manager 中途取消驗證後續計算不啟動、舊 record 保留、
  retry 成功，同 seed 五種方法的值不變。未新增 owner、thread、state 或 exception。
- 同一測量條件修理後首個 forward 後即退出，Gradient／SmoothGrad 各為 1 forward；
  evaluator tail 0.038–0.101 ms。這只說明未再執行剩餘批次，不是 GUI／CUDA 延遲保證。
  單次已在執行的 Torch／Captum 仍完成後才觀察取消。前後 probe JSON 保留在同一 evidence 目錄。
- 最後覆核：原獨立 reviewer 直接讀 diff／測試並解析 artifacts，確認原三項 findings
  可關閉、六項準則於 Saliency 範圍達成；responsive 修理另由未參與該修理的 reviewer
  檢查 layout／reentry／selection，未找到 blocker。不宣称整個 repo 或永久零缺陷。
- 最後本機證據：`final-panel-native.xml` 256 passed；`cancellation-regression.xml`
  34 passed；`final-source-diverse.json` 4 passed。均位於
  `build/dev-artifacts/saliency-validation/`。`build/dev-artifacts/` 的
  `saliency-final-native-entrypoints.xml` 6 passed、`saliency-final-offscreen-entrypoints.xml`
  4 passed／2 explicit native-only skips；不把重疊群組加總。63 個修改 Python 檔 Ruff
  check／format 通過，全專案 Basedpyright 零診斷；未調整 diagnostic baseline。
  真 3D native 案例不在一般 offscreen CI 執行，後續影響該路徑仍須補 native evidence。

### 已同意的逐模組結案準則與順序

2026-09-23 使用者同意依下列六項準則逐模組討論、清理；並明確確認**以下順序適用
每一個模組，不只是 Saliency：討論並確認 UI 行為 → 清理後端、測試與相關 scripts →
獨立 reviewer 結案 → 下一個模組**。本輪從 Saliency 開始，後續 Evaluation、Training／
Data Split、Preprocess／Epoch、Import 同樣遵循，不在 UI 未確認時提前展開其後端清理。
這取代「限定切片回歸通過即可
視為模組清理完成」的判斷；不以「重大歷史包袱」等無可核對的形容詞作為退出條件。

1. 無已確認無用途的程式：追查正式 caller、動態註冊、設定、scripts 與文件後，刪除
   無用途 API、分支、狀態、包裝及專屬測試；只有測試呼叫不是保留理由。
2. 同一政策不多處獨立實作：同一 workflow 狀態／決策有明確權威；多層防護須指出
   各自保護的不同邊界，不能把必要的 freshness／integrity 檢查當成重複刪除。
3. 每份狀態、cache、轉接都有用途：能指出產生者、消費者、失效時機，以及不能直接
   使用既有資料的原因；未查清的項目不可標為完成。
4. 處理責任混雜：若修改同一規則需要同步修改多份判斷／狀態，就收斂責任；不按
   檔案行數強迫拆分，也不以搬檔／新增代理層冒充改善。
5. 測試保護正式行為：重要成功、失敗、取消、重試、stale result、關閉路徑有適用
   observable evidence；只塞內部狀態或 mock 成功不代表完整流程已驗。先有替代證據
   再刪維持舊入口的測試，保留必要外部依賴隔離。
6. 相關 scripts 逐支去留：指出現行用途、入口、與其他腳本的差異；一次性任務已結束、
   用途退役或功能重複時，連同專屬設定／測試／文件清理，不移到 legacy。

節奏：先逐項討論 UI 操作與預期狀態，用正式 Windows 流程確認正常及異常行為；
必要的可見修改先取得確認，不能把已接受的 warning 外觀當作整個 Saliency 行為驗收。
UI 行為確認後才追加後端內部清理，保持已確認行為並補 focused regression；若 UI
驗證重現 backend defect，先定位、明示直接修理範圍，不以此提前展開整輪後端重構。
既有 dirty 修改保留，不撤回。使用者已再次明確確認 Saliency UI 行為已確認過，
該模組直接接續後端／內部清理，不重開 UI 討論或要求重測；其餘模組仍先確認 UI。
後續若影響已接受行為，補受影響部分的驗證，不預設整套重測。模組結案由獨立 reviewer 核對
六項準則；範圍內已確認要修的項目須關閉，未查清不得自行轉為下一輪 follow-up。
保留項要有可核對理由，需要行為／效能取捨時由使用者確認。不承諾永遠沒有新 bug。
模組討論／UI 行為確認不等於每塊都要求正式手測或 merge；整合版本才集中驗收，
仍依既有 exact-source／CI gate 與授權辦理，不新增第二套清理平台或任意數字門檻。

Saliency 已按這些準則完成本輪結案；上述三項已修理並獨立覆核，不再列為未結項。
模組範圍是下方核心 production、直接測試與四支 scripts，不外推為全專案清理完成。

## Completed record — 研究線最新工程與歷史量測

2026-09-23 核准的封存包／Linux evaluator 工程範圍已 scope-complete；
固定20題、搬移後離線報告／原候選判分核對、歷史d0不變及三方獨立覆核完成。
實際來源、產物與限制由 [Current](../current.md#linux-evaluator-2026-09-23)
擁有；執行及研究契約由[研究規格](../validation/thesis_protocol.md)擁有。
本輪未PR／push／merge；不自動開始新候選、完整DEV、正式VALID或TEST。

### 產品 Saliency 施工界線補記（歷史，非當前整合授權）
- 問題與證據：上一輪 Import 修理已合併，但本文件仍指向已刪除的 worktree 及待 PR
  狀態；使用者現在要求逐站討論 UI／操作，並審查是否存在無用途或重複腳本。
  這是新的審查方向，不代表已確認 Saliency 有新 defect 或腳本可直接刪除。
- Outcome：Saliency 每塊 production／tests／scripts 都追清實際入口、責任與用途，
  刪除已確認死碼、無用腳本與專屬測試，收斂重複政策／轉接／狀態；必要保留項有理由。
  三項 UI 修整與測試綠燈只是基線，不代表深度清理完成；逐塊施工後再整合驗收。
- 順序：Saliency／Visualization → 產品 Evaluation 結果頁 → Training／Data Split →
  Preprocess／Epoch → Import Wizard。後續各站目前是候選，不同時展開全部重構。
- 目前授權：使用者提供 Windows 截圖並確認三項修整：Assistant 與 3D 同時使用時的
  VRAM 提醒可勾選 Do not ask again；Fold 不再包含可選的 Select a fold；下拉選單
  上下白邊修正。保留整體 UI 操作。另審查 Saliency 後端、測試、架構及相關腳本。
  未確認的計算語意／流程取捨只回報，不直接實作；其他 panel 仍未授權施工。
- 最新澄清：使用者要求深入查冗餘設計、死碼、無用 scripts，從 Saliency 一塊塊修好。
  授權行為保持的內部刪除／收斂與直接測試修理；保留已接受外觀、方法／資料語意、
  Assistant 工具契約、取消／一致性保護。不以額外 UI／政策改動替代清理。
- Non-goals：不更換 main 手測版本、不改另一條 Assistant Evaluation 研究線的
  題庫／runner／scorer／模型／prompt／RAG／封存，不升級或複製 virtual environment、
  不下載或搬資料、不動任何既有 settings.json，不自動發布 PR／merge。
- 假設：後續可重用現有 Windows Python 與資料；本次不建立新環境；設計接受後執行必要計算驗證。
  新 worktree 不帶入 main 的本機設定；需要原生預覽時另確認啟動路徑與測試資料。

### 研究線最近完成（原來源證據）

報告閱讀介面與產生器可讀性整理已完成；實際能力及證據邊界見
[Current](../current.md#assistant-research-baseline)。這不是其餘 evaluator 政策修理、
資料夾遷移或人類設計驗收完成；外部產出格式計畫的未實作項保持待辦。

`review_status` 已改在正式非 TEST 題庫來源移除，runner 恢復原樣複製；
正式來源與驗證見 [Current](../current.md#assistant-research-baseline)。

2026-09-22 核准的完整 DEV initial 已 scope-complete：1,320 有效量測、獨立判分／capture
核對、報告重建及實際 queue 接續已通過。結果與限制集中於
[Current](../current.md#assistant-research-baseline)，執行契約由
[研究規格](../validation/thesis_protocol.md) 擁有，不在本 plan 重複保存數值。
本輪沒有 PR／push／merge，也不等於產品 native GUI 或正式 TEST 驗收。

上述已完成工程範圍之外，下方 DEV 調優候選仍未授權；不自動執行第二套、VALID／TEST，
不重跑已完成的起始基準或歷史 Pilot。以下保留歷史及候選，不作新的施工授權。

## Completed record — 產品 Saliency 清理證據補記

以下保留整合前產品線的施工狀態與證據，當時的dirty／待發布描述不代表共同基線目前狀態。
- 文件準備已完成；下方清理與本機整合證據屬本輪 dirty candidate，不使用 PR #146
  或清理前的 UI 綠燈代替本輪驗證。
- 後續施工：focused tests、相鄰流程與適用 source-diverse gates；可見改動需同來源
  畫面／walkthrough 與 Windows native 確認。沿用 validation contract，不另建 gate 系統。
- Next：Saliency 內部工作已完成，待發布授權；沒有 pending 施工或 reviewer。
  不要求使用者重測全部已接受 UI。發布後仍依 exact-head CI／適用 gate 決定正式交付；
  其他模組尚未因此取得 UI 接受或施工結案。
- Stop：Saliency 清單逐塊有實際讀取與去留結論，確認的冗餘完成刪除／收斂並有直接
  行為驗證與獨立覆核，最後整合 review 才交付。未知項不得算完成；PR／merge 另需授權。
  本輪審查結論須區分已檢查範圍、實際 findings 與未證明的科學有效性。

### 深度清理清單與施工界線

| 區塊 | 已做的限定清理 | 模組結案狀態 |
| --- | --- | --- |
| Settings／參數與方法 | 收斂 store mapping、參數重算、dialog alias；保留 command admission 與 artifact decoder 的不同責任 | 已獨立覆核結案 |
| Compute／取消／publication | 移除 test-only prepare／defer／holder setter；保留正式批次發布、ack／retry、commit fences；evaluator 採用既有取消訊號 | 已覆核；保留單次 Torch／Captum 合作式取消界線 |
| 結果與 provenance／快取 | 刪重複 copy／不可達 fallback；保留模型與資料 provenance、artifact 語意 integrity、filesystem transport 三種不同保護 | 已獨立覆核結案 |
| 四視圖與 controls | renderer 只收 detached DTO；刪隱藏 selector、同步 scene fallback、死 helper、重複 3D status；保留 native resource ownership | 已獨立覆核結案，responsive UI 已接受 |
| 專用測試與 fixture | 先遷移正式入口與真 publisher 再刪退休入口測試；補 artifact／alias／shared selector／真 3D 取消重試／數值與中途取消 | 已覆核；native-only 案例需原生環境執行 |
| 相關 scripts／gate／docs | 四支直接腳本均有 gate／人工入口；保留整支，刪內部重複並修兩個驗證缺口；不是全 repo scripts 審查 | 已核對去留並獨立覆核結案 |

- 每塊先列具體檔案、caller、deletion candidates、owners before/after 與 focused baseline；
  不新增通用盤點系統、legacy 目錄、第二套 owner 或純搬檔重構。小切片可逐一回退。
- 既有 source-diverse／Windows 真 compute 與 render 證據是施工前基線；變更後先驗直接
  影響，整合完成再取得新 source 的必要 gates。未改模組不反覆跑同等重型驗證。

#### 已核對的第一批施工切片

- Backend：Evaluator 已算好的 effective noise parameters 重用於 batch，方法名稱／store
  mapping 收回既有輕量 saliency_methods；EvalRecord 的 decoder 已強制 dict，刪 load 端
  不可達 malformed-store 分支及 getter／setter 外重複 metadata copy。保留 decode、
  context／integrity 檢查與持久化隔離；owner 不增，先過原數值／tamper baseline 再改。
- Views／Settings：移除無 production caller 的 PlotType/get_saliency 舊便利 API 與
  專屬無效測試；Settings 移除重複 alias／重複初始化。3D 永遠隱藏的 class_combo
  退役，保留 shared panel selector 的 canonical key 與 first-available／blocked 語意；
  改成只保存選定 key，不新增選擇 owner。保留公開 SaliencyRenderData／worker 保護。
- Panel：刪無 caller 的 _has_service_saliency_summary；cache 的 presence 與 lookup
  改用一次同一查詢，重用既有 publication identity predicate；各 renderer 保持不同
  update_plot 參數，但共同 publication／terminal 綁定只保留一份。保留 queued worker
  finished、stale、operation／commit fences，不在這個切片移除 compute-attempt ledger。
- Scripts／tests：walkthrough validator 的 optional final_state 可略過終態檢查，先
  RED 重現缺失／空值後改 fail closed；runtime claim 不再硬寫 XCB。reviewer capture
  的 29+5 歷史 inventory 合成同一份 34 項，保留名稱／順序；polish 同檔 PNG 轉換
  重用既有函式。刪被目錄級 guard 覆蓋的單檔 guard／舊拼字 assertions，不削弱 gate。
- Rollback：上述切片各由限定檔案 diff 回復；不碰既有 UI acceptance 修改或其他工作區。
  先 focused baseline，修改後同組回歸，hidden selector 與 publication 變更獨立覆核。
- 第二批限定候選已查 caller：render 的單份 prepare 只有 service 空轉接、stress fixture
  與舊測試，正式 UI port 使用 prepare_variants；notification.defer 只有測試，正式流程
  使用 reserve／publish_reserved／release。刪前將既有測試移至真實入口，保留取消、
  commit、queue handoff／retry／ack 保護；不更動 Command／query DTO 或 Assistant 契約。
  Sidebar.update_info 是空方法，刪除自身與 panel 的空呼叫；實際資訊仍由 InfoPanelService 更新。
  3D checkbox callback 包裝未被使用，下一片改為既有 scene 上兩個布林值；constructor
  的同步 engine／自行建立 plotter fallback 只供舊測試，改由現有背景準備與 QtInteractor
  入口測試。prepare_engine 本身仍由 worker 使用，必須保留。以上不增加 owner。
- Renderer 邊界：所有實際繪圖 caller 已使用 SaliencyRenderData；Visualizer 與 3D engine
  的 EvalRecord／Epochs 第二入口只留在測試。遷移到同一 detached DTO，將 context drift、
  legacy missing、持久化 roundtrip 的 oracle 放回真 SaliencyRenderPublisher → renderer
  路徑，再刪 renderer 內重複 record mapping／context fallback。不改 publisher、artifact
  admission 或數值算法；先取得遷移後 passing baseline，沒有替代證據的案例不刪。
- Holder.set_saliency_params 只有七個 unit 與兩個 integration fixture 呼叫；正式 manager
  使用 prepare_saliency_update + 整批 publish。將九個 caller 改真 preparation/publication
  流程後刪此 convenience，不刪 Study／TrainingManager 的正式設定入口，不改批次原子性。
- 整合檢查：全專案 Basedpyright（不同於單檔分析）指出 Captum kwargs 失去舊 helper 的
  Any seam；為已經 canonical normalizer 驗證過的 effective_parameters 補同等型別註記，
  不新增轉換／驗證、不改任何計算值，重跑完整 gate，不調整 diagnostic baseline。
- 實際 stress 驗證發現 runner 不理會 QT_QPA_PLATFORM=windows，固定改為 offscreen，
  因此 --require-interactive-3d 在 Windows 永遠失敗。先 RED 驗 explicit Windows 選擇，
  再只開放 Windows 的既有環境變數 opt-in；預設 CI/offscreen、macOS 與原 resource gates
  保持。原生重跑明確設定 PYVISTA_OFF_SCREEN=false；不假冒 offscreen 為 desktop。

### 本輪深度清理結果與限制

- 完整讀取的核心 production 範圍為 30 檔：panel 1 檔；views／Settings／renderer 17 檔；
  application saliency services、方法定義、Evaluator、provenance／integrity、EvalRecord／
  artifact store 12 檔。另讀 warning 元件、被刪 CheckboxObj 與共享 owner 的相關段落；
  不把後者算成全檔審查。直接腳本四支；測試按修改責任追到真行為，非全 repo 逐檔審查。
- 最終 production 27 檔 +288/-1055，淨減 767 行；scripts +29/-44，淨減 15 行；
  tests +1619/-770，淨增 849 行（補 observable evidence，不用淨減測試當品質指標）。
  未增加 owner、state machine、receipt 或
  compatibility path。移除 ui/core/utils.py 及其專屬 test；其餘為原 owner 內收斂，
  沒有刪使用者資料、模型、環境或研究線檔案。腳本沒有可整支刪除項。
- 保留 compute-attempt ledger：同一 publication 的 dispatch／confirmation 期間需要擋
  重複提交，failure／cancel／reset 會釋放；不是第二套 backend operation state。
  保留 geometry／STFT 等 bounded cache 及 native async cleanup，未以縮行數移除它們。
- 覆核：backend／publication 與 UI／native lifecycle 由非實作者交叉審查；主 agent
  檢查實際 diff 與整合證據。DTO 遷移保留 context drift／legacy missing／持久化 roundtrip、
  一基底事件碼與字串 class key、VarGrad absolute、float64 cancellation-sensitive 數值 oracle。
- 清理後本機證據：backend renderer 161；Windows UI／Settings／panel／views 364；
  真 GUI／Assistant compute、SmoothGrad 重算、取消與 native lifecycle 9；source-diverse 4
  通過。這些是不同執行組、部分有重疊，不加總成唯一案例或全專案覆蓋率。
  Holder 正式路徑與六模型 family workflow 34、scripts stress 62 通過；完整 Basedpyright
  零診斷、architecture compliance 通過。POSIX-only filesystem 案例未由 Windows 取代。
- Windows 真四視圖 capture：compute completed、互動 3D framebuffer 有 actor、無未捕捉
  例外、clean shutdown。原生 stress 2 輪 warmup +12 輪量測，14 次 3D close 成功，
  零晚到回呼／active Qt worker，resource 與 memory contracts 通過；不是無 memory leak
  的普遍證明。Windows 100/125/150% app-polish matrix 通過。
- 證據位於 build/dev-artifacts/saliency-validation/ 的 deep-*、renderer-detached.xml；
  綁定 64bd5fdc 加清理 dirty source，最後文件收斂與 test formatting 另記於 diff，
  不是未來 clean PR head 的同版本 CI。初次完整 typing 與 native stress 的失敗已修正並
  重跑，不掩蓋初次結果。source-diverse 重用 E 槽，沒有下載／複製環境。
- 限制：大型 panel／base view／3D view 仍有整合責任，不因大小判定必拆；取消粒度與
  測量已完成，界線見上方結論。相關 scripts 之外的全 repo 腳本尚未
  審查，隨後續模組逐支處理，不冒充本輪已清完。Attribution 科學有效性、所有模型／
  資料與逐 bit 重現不是本輪工程測試的保證。

### 已接受 UI 與清理前基線（以下舊數字不是深度清理後證據）

- Fold 的提示項目前在 init／refresh／clear 三處作為普通選項加入；改為空清單的
  placeholder，無資料時不可選；有結果只列真實 Fold／Fold Set，保留 selection identity。
- VRAMConflictChecker 的提醒是 UI advisory，不是 backend resource admission 或 Assistant
  工具授權。沿用 ModalAlertDialog presentation 與 application_settings 保存個別提醒偏好；
  只有使用者勾選並按 OK 才保存，關閉／Escape 不默認同意。跨重啟記住選擇，不讀寫 root
  settings.json，不略過 OOM／資源 preflight／工具確認。預覽與測試使用隔離 config root。
- 2026-09-23 使用者追加確認：Do not ask again 移至 dialog 最下方左側，與右側 OK
  同一列；只調整 opt-out dialog 排版，未使用 opt-out 的既有 modal 位置保持不變。
  先以真 Qt geometry 驗證同列、不重疊與按鈕可達，再開原生警示框；仍不跑重型測試。
- 最新文案確認取代舊提醒：標題 GPU Memory Usage，正文說明 local Assistant 與 3D
  同用可能增加 GPU memory usage，若變慢可分開使用；這不是已偵測不足。
  勾選改為 Don’t show this again。使用者不接受上一版外觀，已授權再做一版：縮短正文、
  統一標題／正文／勾選框左緣、調整標題與操作列間距，保留黃色圖示；其他 modal 不變。
  最新確認：正文合為單一段落，移除句間強制換行，依視窗寬度自然折行；其他排版不變。
  本次只驗直接 modal／VRAM 小測試和 Windows 原生警示預覽，未接受設計前不跑重型 gate。
  新版對齊檢查先重現左緣 18／52 不一致，修正後直接 modal／VRAM 39 cases 在 Windows
  通過；已開真實警示框、確認有回應並檢視截圖；使用者已接受單段正文設計。
- 白邊先用 Windows popup 擷取確認來源；只修 Visualization 的受影響選單，不任意
  改全產品樣式。保留鍵盤、滑鼠選擇和長清單捲動。
- Owner before/after：backend command／operation／publication owners 不變；既有 VRAM
  checker 保有提醒政策，modal 只負責呈現，Qt settings 保存使用者偏好。不新增 owner、
  state machine、receipt 或 compatibility path；production 3 檔 +91/-23，淨增 68 LOC。
- 驗證：真 Qt dialog 勾選／未勾選／取消及 fresh checker 持久化；Fold empty／多項／刷新
  保留及跨 fold set 選取；native 展開 Fold／Run／Method／Class 的像素及鍵盤操作，
  另跑直接相關 lifecycle／render regression。測試隔離昂貴推論／GPU，不啟動研究模型。
- 審查：沿資料→completed run→saliency method／class→artifact→render 追蹤真入口與
  取消／stale／整批發布；核對測試 oracle、mock 邊界及相關腳本用途。不將通過測試數量
  或 3D 頭部圖宣稱為 attribution 科學有效性或腦內定位。
- 整合回歸發現兩個舊測試仍把空 Fold 視為 enabled：補空／有結果情境，保留 busy
  還原與 summary query 不阻塞 Qt 的原始保護；不為舊 assertion 改回可選空提示。
  完整型別 gate 另發現 combo.view()/window() 的 Qt stub 可為 None；補呈現層窄 guard，
  保持正常 popup 外觀不變，再驗型別與直接 popup 回歸；不放寬 analyzer baseline。
- 清理前 UI 整合結果：UI 396、backend 數值／artifact／publication 315、Windows 真 GUI／Assistant
  compute／SmoothGrad 重算／取消／render lifecycle 9、canonical source-diverse 4 通過；
  source-diverse 重用 E 槽資料，不下載。兩項舊空 Fold assertion 改成空／有結果案例，
  獨立覆核確認沒有削弱 busy／Qt 回應性保護；沒有刪除測試或 backend 功能。
- 原生證據：四視圖含互動 3D、clean shutdown 通過；Windows 100/125/150% 完整
  app-polish matrix 通過；變更表面 modal／popup 三倍率各 47 通過。capture 初次因
  WSL worktree Git 路徑及共用環境 namespace 來源檢查失敗，改用行程限定 Git 路徑／
  import path 後補跑成功，保留 failed artifacts；未改共用環境、Git metadata 或 gate。
  以上 capture 綁定 guard 修理前的 source fingerprint，不是最終 commit 的交付證據。
  最後 nullable guard 後 Windows popup／Fold 54、完整 Basedpyright 零診斷及 changed-file
  Ruff 通過。完整 regression／Linux visual／跨平台 CI 留給獲授權後的同一 PR head。
- 證據位置：`build/dev-artifacts/saliency-validation/`，早期 JUnit 在
  `build/saliency-validation/`。本機來源仍為 `64bd5fdc` 加本 slice dirty diff；沒有
  commit／push／開 PR／merge。main 的 protected settings.json 雜湊核對未變。
- 已驗：Windows 原生四種 popup 白邊先全部重現；僅改 list style／combo palette 不足，
  最後針對 popup 獨立 window 補背景。Fold 改動的 busy refresh／empty restore 風險由
  獨立覆核抓到並修正，保留既有 operation fence，無新增 owner。直接 Fold／popup
  22 cases 在 Windows 通過（含 50-item 清單最後列可達與鍵盤選取）；VRAM／modal
  38 cases 通過，包含勾選、OK、Escape、close、INI 及新 process 讀回。不是 full suite。
- 預覽：`build/saliency-ui-preview/preview.py` 為忽略於 Git 的一次性 native preview，
  重用真實產品 controls 與既有 detached fixture，示例 Fold／class，計算與 render 隔離；
  Qt 設定寫入該預覽的獨立 config root，不動使用者設定。截圖與預覽不是完整 GUI handoff。
- 清理前初步唯讀審查：compute／artifact／render 的整批發布、取消不覆寫及 stale 拒絕有
  實際 owner／測試；亦有真 MNE／EEGNet／Captum 與解析梯度 oracle，非全靠 mock。
  未確認新 backend blocker，未逐行審完全套大型 tests，也未重跑數值／跨平台 gates。
  三項後續候選：取消只在 run 前後檢查，延遲尚未量測；核心 panel orchestration 仍大；
  label-render 固定等待與 GUI compute 矩陣未納 3D 的 evidence 邊界可再改善。不在本輪改政策。
- 相關腳本：visualization render walkthrough、native render stress、reviewer captures、
  polish captures／DPI runner 均查到 gate／CI／其他 capture caller，暫無可整支刪除項。
  部分 Settings fixture 重複不等於整支無用途；全 repo 腳本清單仍未完成。
- 解讀限制：一個 completed run 缺完整 Test／Validation class coverage 會讓本批 Saliency
  不發布，舊結果保留。Attribution 對 true class output；3D 是 electrode 值插值，不是
  腦內 source localization。方法科學有效性、跨模型梯度與隨機方法逐 bit 重現未由本輪證明。

## Accepted history — 產品品質線：Import 適配與內部整理

以下保留另一線施工及證據；已由 main@94328196 的 PR #146 合併，不是本線 active 工作。

使用者已授權本輪施工，並要求先更新文件、深入整理完整 Import 路徑，不只修單一 helper。
工作區為 `XBrainLab-product-quality`，分支 `refactor/product-quality`，起點 `8636a754`。
本節是本線唯一施工進度；下方研究里程碑由 Evaluation 線維護，不覆寫或執行其題庫／評測。
PR #143–#145 已進入此 main 基線；舊啟動器、RAG、split receipt 與回應性修理不再 active。
使用者已批准刪除 `wip/data-split-summary`，未合併的 UI 修改未帶入本輪。

### 問題、outcome 與界線

- 正式 BIDS importer 使用 metadata／內容，不以 MOABB 名稱白名單放行；Graz GDF 名稱還原、
  T1／T2 語意防護與轉換端 loader 修補需要分清來源、假設及責任。
- 靜態閱讀發現 preview 與 apply 各自實作 run mapping 查找，對同名檔案唯一性處理不同；
  這是待重現風險，不先宣稱使用者資料已錯誤。
- Outcome：preview／validate／apply／recipe／epoch 的 recording 與 class 解讀一致，
  重複政策收斂；production、直接相關 tests／fixtures／scripts 的去留有具體理由。
- 允許修復已重現的 mapping 誤套或資料一致性缺陷；不改 Graz 自動還原或 Assistant 公開工具。
- 2026-09-21 使用者批准移除僅因內部事件名稱為 T1／T2 而要求逐 recording mapping 的
  特例；現有 Match Labels 選事件、填 class 應足以確認，不新增 UI。外部 labels、既有
  recipe 的明確逐檔 mapping 及一般資料一致性／epoch 前置條件保持。
- 不改研究題庫／runner／scorer／模型／prompt／RAG，不新增下載、不搬資料、不升級共用環境，
  不覆寫任何 worktree 的使用者 settings.json；本輪不是 B0 封存。
- 保留有證據的來源適配，不以特例、LOC 歸零為目標；獨立 UI 打磨留待下一階段討論。

### 施工順序

1. 文件先行：校準已合併歷史；逐段追蹤選取 recordings、events／labels、channels、
   review／apply 與 recipe 的實際 caller，在既有資料架構文件記錄保留／收斂／限制。
2. Baseline：沿用 focused tests，建立真 MNE／Command 路徑的 characterization；
   已重現缺陷先 RED，再修理。查清完整路徑、唯一 basename／run 與 carrier 對應。
3. 收斂：在既有模組重用純函式統一等價查找規則；歧義簡寫不得套用到另一筆 recording。
   保留無歧義輸入與 recipe，維持既有 admission、mutation/publication ownership；
   不新增 authoritative owner、state machine、receipt、通用適配平台或 compatibility 空殼。
4. 相鄰清理：同時檢查專用適配、label 建議、recipe trace、資料一致性與相關腳本；
   確認無 caller 或已有可靠替代證據才刪除 helper／重複測試，不擴張無關 panel。
5. 獨立 review、focused／source-diverse／必要 Windows native 驗證；同候選適用 CI 通過後
   集中一次 Import 局部手測。PR 發布／merge 各依授權，不自行合併。

### 驗證、複雜度與完成

- 正例：完整路徑、唯一檔名／run；不同 run 的相同 T1／T2 不同語意；apply／recipe／epoch 一致。
- 反例：跨 subject/session 同名、重複 run、部分 mapping、對調 carrier、真 stale source；
  失敗不得部分 publication；不更動原始檔案、波形、事件時間。
- 適配：Graz 已知模式保留、名稱／順序／通道數不同不得誤套；BIDS external／embedded／
  no-label 路徑維持。用真物件與 Command evidence 補強 mock-only 覆蓋後才刪重複測試。
- 每個 coherent slice 記錄實際 diff、owner 前後與 production LOC；觸及 root complexity
  門檻先 review。Rollback 為各 slice revert，不用大規模搬檔冒充架構改善。
- 不將舊 134-root campaign 當成本 head 證據；CI 已提供的等價 full checks 不本機重跑。
- Stop：已授權範圍、直接驗證與 review 完成後集中交付；若新政策／UI 決策或必要資源阻擋，
  先完成其餘安全工作並提供具體證據。小 commit、CI pending、context 壓縮不是停止條件。
- 已驗：既有 BIDS／reader baseline 72 passed；新增真 Commands 6 個案例原先 4 failed／2 passed，
  重現 run 簡寫丟失、同名檔案 metadata 誤配、歧義 basename 誤套。修理後另外追到 recipe
  將同名 recordings 的 metadata overrides 壓成單一 basename，初次 apply 正確但重播丟失語意。
- recipe 同名 metadata、完整路徑 mapping remap、部分 remap 誤合併與歧義簡寫被 remap
  誤升格均已有真 Command regression；獨立覆核的 findings 已修理，最後覆核無 blocker。
  原 scope 有歧義的簡寫不因重新命名而取得語意授權；沒有 reviewed mapping 時維持原事件，
  不為測試新增 epoch hint 政策。擴大 focused 曾 255 passed；最後 remap 修理直接相關
  82 passed，需在固定版本重新取得整合 evidence。
- BIDS recommendation 清理為 production +8/-42/net -34 LOC，characterization 先後皆 77 passed；
  Graz reader seam 改用真 MNE 物件補正反例、annotation preservation 比對改為事前 snapshot，
  對應 35 tests 通過。純解析／state owners 不增加；不改推論門檻或 UI。
- T1／T2 修理前的 production 合計 +165/-99/net +66 LOC、5 個既有模組；不新增 owner／module／class。
  Apply 內部 mappings 每批先解析一次，移除 preview/apply 的分歧查找；existing publication
  owner 與 cancellation 不動。相關 catalog／converter 腳本確認仍有用途，本輪未任意刪除。
- Static typing、changed-file lint 與 strict docs portal（42 pages／1,617 links）已通過；
  既有 MNE／NumPy deprecation warnings 保留，不在本輪升級共用環境。
- 候選 6f1cf5f9 已驗 focused 256／source-diverse 4 passed。Windows wizard 19 passed／
  2 failed：原 PR #141 已新增 no-label Back/Next driver，folder trace expectation 卻漏同步；
  基線與候選測試 blob 相同，獨立覆核確認。僅補完整序列中的返回步驟，保留所有 state
  assertions，不改 UI。舊 catalog 因候選需更新而主動中止；保存 partial evidence，不計通過。
- 9a0cc0f0 已完成 focused 256、source-diverse 4、Windows wizard 21 與代表性 catalog
  134 passed；這些是修正 T1／T2 政策前的基線，不代表新修改已驗證。
- T1／T2 repair 已完成：真 Commands 重現填 A/B 後 epoch hint 仍是 T1/T2；真 wizard
  重現完成選擇後仍要求額外確認。名稱特例、專用 helpers、確認與套用分支已移除；
  現在以明確 class maps 決定分類／逐檔差異，不新增 owner／module／UI。
- 替換兩個只保護退役政策的 mock-heavy unit tests，改由真 MNE／Command 與 native UI
  覆蓋：共用 class、明確逐檔優先、recipe replay、事件 sample／class 序列與來源 bytes。
  直接回歸保留同名／歧義／remap 的 epoch 防護；獨立覆核的五項資料流程探測通過，無 blocker。
- 6af61225 已完成 focused 279、source-diverse 4、Windows native 22 與代表性 catalog
  134 passed；詳細結果在 build/import-quality 的同版本 verified artifacts。
  使用者已確認 Windows 原生 T1／T2 → A／B 操作通過；此為局部操作確認，不是全部 Import
  驗收或 merge 授權。2026-09-21 使用者已授權推送／開 PR；仍未授權 merge。

- 2026-09-21 使用者同意的操作路徑覆蓋收尾已完成：既有 UI 測試補單／多檔共用 class、
  返回改名後重新 review、BIDS 內部事件及外部 MAT 的實際 epoch／recipe 語意；CSV／TSV
  原 placeholder 測試升級為真 widget → Commands → epoch／recipe，無 labels 實測 epoch
  拒絕且不改 working data。保留取消／重試／失敗 atomicity 的既有保護；完整對照及限制由
  [validation contract](../validation/README.md#import-support-claims) 擁有，不複製另一份矩陣。
- 收尾僅 tests/docs，production 0 LOC；獨立 review 的多檔 oracle 缺口已修正。首輪外部
  測試抓到等待 worker 而未等待獨立 render timer 的時序錯誤；移除測試內手動刷新，限時
  等待自然繪製後 4/4 通過，原失敗保留。整合 Windows native 30/30、0 skip 通過
  （build/import-quality/path-closure-native-integrated.json），lint 通過。未重跑未變產品的
  134-root catalog，不把既有結果換標成新 head；仍有來源警告與 MNE／NumPy deprecations。
- Next：推送產品品質分支、建立 PR 並追蹤同 head CI，修復 in-scope 失敗；不自行 merge。
  本輪沒有再次改變使用者剛確認的產品行為，不要求重測 T1／T2，也不把局部確認当 merge 同意。
## Completed record — B0 完整執行入口（2026-09-21）

使用者授權的可日常重跑 B0 入口已實作、獨立覆核及實跑全矩陣；
`baseline.cmd` 的固定範圍與用法由[研究規格第 5 節](../validation/thesis_protocol.md)擁有，
實際結果、資源位置與重現限制見 [Current](../current.md#assistant-research-baseline)。

- 重用 frozen runner／scorer／report，沒有新增產品 owner、環境或模型下載；原封存不改。
- 全 300 題與報告驗收、report-only、無重送的 completed resume、中文／空白搬移驗證通過。
  入口測試／相鄰契約與 Windows preflight 完成，測量與各次報告保留。
- 已辨識既有 prompt 的匿名識別／publication counter 變動；不追改 B0，也不把它說成
  完全相同輸入或正式模型排名。正式比較前的非任務資訊控制留待 M4 決策。
- 本輪 scope-complete；沒有產品 UI 變更、push／PR／merge 或 Development／Validation／Test。
  不自動啟動下列 candidate。

## Completed record — 正式 B0 共用修理與封存（2026-09-21）

使用者授權的共用格式／重試修理、相同矩陣重跑及另立正式 B0 已完成。
`assistant-b0-formal-20260921-926d90ea` 固定 `926d90ea`；前期 `ac8af81d` tag、
原始分數與封存不追改。精確版本、結果、封存位置與限制由
[Current](../current.md#assistant-research-baseline) 擁有，契約由 target／研究規格擁有。

- 共用整份 JSON fence 相容與預設一次格式修復，沒有新增 owner／控制層；直接相鄰的
  舊 evaluator observation adapter 及非法 typed-clarification scorer 假陽性亦已修正。
- Focused tests、契約／安全獨立覆核通過；完整 300 題與 320 次 capture、分母、
  逐題判分及報告連結經獨立核對，低分、失敗與先前 partial 原樣保留。
- 新鎖定 Windows 環境真跑單條件 30 題，分數／repair／核對的產品結果一致。
  E 槽封存 6,216 檔逐檔校驗通過，僅移除本輪臨時 checkout／環境；共享資源保留。
- 本輪 scope-complete，不是 native UI 驗收或產品 handoff-ready；未 merge、
  未跑 Validation／Test，也未開始 Development 調優。後續候選須另行確認。

## Future — 完整 DEV 起始基準後的調優（尚未授權）

前期 Pilot／B0 與新版完整 DEV initial 均已完成。
事實與限制見 [Current](../current.md#assistant-research-baseline)，
報告入口／契約見研究規格第 5 節。舊分數與快照不追改。
下一輪若經使用者確認，才依
[研究規格](../validation/thesis_protocol.md) 的每模型最多五套設定規則選擇改善方案；
本輪 initial 已占各模型第一套。只調已允許的提示詞／工具呈現／格式修復，RAG 固定。
不因 Pilot 分數直接調 prompt／RAG、挑模型或啟動
Validation／Test；Test 仍封存且本輪未讀取。

可據本次證據討論的改善最多三項：缺資訊時自行補參數、不得操作時仍選擇工具、
動態 publication 變動下的操作交接。共用 fence 與重複修復已處理；仍存在的模型格式錯誤
不能說成全部解決。這些是候選，不藉報告施工直接改模型或產品。

## Completed record — Assistant Evaluation 準備至 Pilot（2026-09-21）

使用者已確認本輪做到「文件校正 → 非 Test 題庫接入 → 評測系統就緒 → Pilot →
結果報告與改善前基線封存／還原驗證」。不是只做文件，也不自動進入 Development 調優、
正式 Validation／Test 或 B1／B2。研究條件與預算只由
[研究規格](../validation/thesis_protocol.md) 擁有；本節只記執行順序、責任與進度。

### 起始問題、施工範圍與出口

- **起始證據**：既有 calibration 只讀合成觀察；舊 frozen 81-case runner 攔截工具執行，
  不能當成本輪真實 Product Outcome。正常 ChatPanel／Host／Command 與 prompt capture 可重用，
  新題庫讀取與單次決策 scorer 已完成 focused 驗證；五模型配置、真實 outcome 與
  完整 runner／軌跡判分／計時／續跑在本輪開始時尚待施工及驗證。
- **起始題庫狀態**：已接收使用者指定的非 Test Excel，結構為 DEV 264 題／66 families、
  VALID 99 題／33 families，family 無交集。使用者於 2026-09-21 明確確認題目與答案
  全數人工覆核完成；當時實際 runtime fixture 仍須準備，不以人工確認代替執行證據。
  Test 仍由使用者保管，
  不為找題庫而讀取封存題文、答案或其他對話全文。
- **完成出口**：Pilot 全部預定案例有完整可追溯軌跡，測量與判分可核對，交付分條件結果、
  有效失敗／無效測量、延遲與資源成本、後續實驗可行性，以及可還原的改善前基線。
  模型低分不是未完成；缺少條件／紀錄或只跑工程 smoke 不能算 Pilot 完成。
- **假設**：使用英文單回合題庫及既有產品工具契約。必要的取消、停止、狀態過期與晚到結果
  只作工程保護，不擴張為未批准的正式多輪實驗。
- **範圍**：題庫格式／oracle 接合、真實觀測、scorer、模型研究接入、單一實驗入口、
  計時／軌跡／結果彙整、安全續跑、Pilot 與封存。直接必要缺陷先重現、最小修理。
- **非目標**：不改公開工具、產品模型清單、UI layout／文字／流程；不調 prompt／RAG 追分，
  不做全面重構、EEG 模型研究或重新下載整套 EEG 資料。Test 不讀、不跑。
- **UI 確認**：本輪不含可見 UI 變更；真實操作觀測沿用現有 UI。若修理需要改可見互動
  或 public contract，先提出具體決策，不把本輪批准當作通用授權。

### 雙線工作區與共用邊界

| 工作線 | 工作目錄／起始 branch | 責任 |
| --- | --- | --- |
| Evaluation（本線） | `D:\workspace_v2\projects\lab\XBrainLab-evaluation`；`feat/assistant-evaluation` | 本節授權範圍、研究規格、評測與基線 |
| 產品品質（另一對話） | `D:\workspace_v2\projects\lab\XBrainLab-product-quality`；`refactor/product-quality` | 另行確認的清理、重構與 UI 調整；不是本線的隱含施工範圍 |

兩個 worktree 從 `main@8636a754` 建立，Git 決定最新 branch／dirty 事實；`main` 仍為唯一
產品基線。工作目錄可持續使用，task branch 仍須保持明確目標，不演變為永久平行產品。

- 本線擁有研究規格與 Evaluation active 內容；另一線更新自己的計畫區塊，不覆寫本線進度。
  本文件仍是唯一 active plan，不另造第二套總計畫。合併時保留兩線各自有效更新。
- Command API、工具／完成語意、狀態 publication、資料解讀與 UI 觀測接點是共享邊界；
  修改前協調 owner 與受影響案例，不各自建立相同責任，也不自行合入另一線未完成修改。
- 每輪實驗固定 source／設定／模型／題庫／scorer 身分；只在輪次之間明確同步已接受的
  `main`。中途不 pull／換 source，改版另立 run 身分，不混用前後結果。
- 不複製大型模型與 EEG corpus；必要來源按不可變 revision／hash 管理。各 worktree 的
  可寫設定、run output、log、暫存與 RAG index 須分離或有明確唯讀共用邊界，先驗證再執行。
  主工作區 `settings.json` 不覆寫、不 stage。
- 優先使用既有 Windows 環境；實驗期間不得升級共用依賴。若需要不同依賴，先確認有界的
  隔離環境與空間方案，不默默改另一線。量延遲期間不並行 GPU 訓練、模型推論或重型測試。
- 正式實驗與 B0 不靠 worktree 留存保證：封存內容／還原要求由研究規格擁有。

### 實作與驗證順序

1. **文件與接收**：移除已結束 dispatch、保存本輪與雙線決策；核對非 Test 題庫路徑與
   元資料。只有當題使用者輸入可進入該回合；oracle／答案與其他題庫內容不得進入 prompt、
   few-shot 或 RAG。Validation 不用來除錯。只取得使用者提供的
   Test 封存狀態／數量／身分，不代稱已獨立審題。
2. **題庫與 scorer**：沿用既有 parser／schema，實作正式研究的三類／分層判分與完整性檢查；
   用已知正反例保護工具／參數錯誤、正常不執行、Host 擋錯不算模型答對、缺失軌跡與錯誤身分。
   不覆寫舊 calibration 或 frozen 81-case 的規則與歷史成績。
3. **真實觀測與 runner**：正常 ChatPanel／Host／Command 路徑接 case／attempt／terminal，
   開窗就緒與完整操作 outcome 分開；產品 owner 決定 readiness、confirmation、mutation。
   補選一／多個／全部條件、輸入輸出與各時間段、失敗彙整與安全續跑，不新建產品 owner。
4. **模型與資源**：唯讀核對五模型精確來源、revision、權重大小、VRAM、授權與 cache。
   缺模型／條款需取得對應授權，不 silent fallback、不自動增加 cache 上限。固定配置後，
   有界載入、暖機與非 Test smoke；RAG on 須真正可用，degraded 不能當作 on 成績。
5. **Pilot**：題庫／系統 gate 通過後，按研究規格固定 manifest、題號、配置與輸出；
   先小階段驗證測量，再補完整矩陣。有效低分照跑照留；測量故障修理後只補受影響部分，
   不以看見答案後重試挑分數。機器時間到預算上限即保存 partial，不自行延長。
6. **收尾與封存**：核對逐題軌跡／分母／失敗與量測界線，交付粗略成本與限制；
   保存 source、環境、模型／資料身分、重跑命令與原始結果，實際還原驗證 B0，
   不開始 B1／B2，不將 Pilot 當正式獨立 Test 或穩定 P95／模型排名。

每個直接必要 slice 實作前在本節補 call sites、具體 focused validation 與回退邊界；
新行為先 RED→GREEN，refactor 使用 passing baseline。每次修改 review，高風險資料／
async／評測證據採獨立覆核；同一份實際 diff 與測量證據由主 agent 驗收。
不為每個內部 slice 要求使用者重測 GUI；產品行為變更仍遵守正式 handoff／merge 規則。
Pilot 完成不等於產品手測／merge 同意；外部寫入與交付仍依 repo 授權邊界。

**完成位置**：題庫／scorer、研究 runtime 注入、五模型檔案取得、全部 selected fixture、
真 Qt observation 與完整 runner 已完成 focused 驗證；Gemma 經批准 NF4 配置通過 GPU
工程檢查。第一版 frozen Pilot `8a7935c3` 在 176/300 fail closed：Phi-4 對
`DEV-C06-01-V3` 錯誤呼叫 `switch_panel(visualization, 3d_plot)`，產品正常顯示既有
`VRAM Warning`，但 driver 把該可歸因的產品警告誤記為 `unexpected_dialog`／無效量測。
已完成的低分與失敗原樣保留，不作挑分重送；此 run 僅是量測框架缺口證據，不納入正式
Pilot 比較。完整 300 題 Pilot 與 B0 封存／還原結果見本節後續完成紀錄及
[Current](../current.md)；下列施工細節保留為歷史證據，不再是 active dispatch。
題庫 intake 證據與來源如下。
來源為使用者指定的 `C:\Users\Administrator\Downloads\題型_已審不含TEST.xlsx`，
SHA-256 `2161af9932950e2a0726daeae3d744935d8d1bc6f408d739b2240d2752a29c23`。
只讀原檔；工作表、split、ID／family／fixture 與 ground-truth 對應 fail closed，
不發現其他檔案或讀取 Test。原 workbook 的 363 筆 review_status 均仍為待人工複核，
runtime 證據 source 為 `8314b590`。使用者於 2026-09-21 已確認全部人工覆核完成；
此為原 workbook hash 所對應的補充宣告，不覆寫原檔／舊 runtime 證據。

直接施工接點：`scripts/dev/assistant_pilot_bank.py` 讀取這份明確 XLSX 契約並輸出有
source identity 的非 Test bank；`scripts/dev/assistant_pilot_scoring.py` 以既有
`CommandParser.parse_product`、`ToolSchemaValidator`／工具 registry 做離線決策判分。
保留 workbook oracle／fixture 原始欄位與舊證據標記；供模型的輸入與 oracle 分離。
Scorer 區分 Action、Clarification、No-call，正常 respond_to_user 不要求 exact message
或 typed pending receipt；錯誤 call 被 Host 擋住仍不能變成模型正確。這只是決策判分，
不宣稱 backend／GUI 成功，不改舊 calibration 或 frozen 81-case。
刪除候選：無；既有 product owner 前後不變，production LOC +0/-0，僅 scripts／tests，
不增加 state machine、receipt 或相容分支。XLSX 不新增套件／修改共用環境。
Focused：新增相應 unit tests 先 RED→GREEN；覆蓋正常讀取、split／family 洩漏、重複／
缺漏／衝突 ID、無效 JSON、受限壓縮／XML、source 身分，以及正／錯工具參數、
布林不等於數值、正常／空白／invalid 不操作回覆、初次／修復後分開與不偷用 oracle。
真 workbook 做 metadata／完整性核對，題庫內容不 commit。獨立 review 後才接實際 runtime；
rollback 僅移除本 slice 新 scripts／tests 與對應計畫，不改原 XLSX／模型／產品。
**已查**：bank／selection／models／fixture／scorer 與既有 calibration 的 Windows
focused tests 合計 226 通過；runtime 注入及相鄰 default／spawn／cancel tests 132 通過；
MainWindow factory／既有 UI shutdown tests 28 通過。scorer、runtime 與 fixture 經獨立 review，
主 agent 已查實際 diff／測試及真 workbook；Ruff、diff check 通過。第三方 deprecation
warnings 保留，未改環境。真 workbook 363 題 oracle schema 全數合法，人工覆核由使用者確認。
正常 controller 的 generation request／events、activity、Command completion 與 turn terminal
可作觀測接點；舊 runner 明確 suppress 工具執行，不沿用其結果作真實 outcome。
既有 TurnMetrics 包含整個 turn，UI request success 也不代表畫面已就緒，須分別觀測。
既有 Windows 環境為 Python 3.12.10／torch 2.11.0+cu130／transformers 4.57.6；
未安裝或升級。三個批准 snapshot 的既有 HF 帳號 access 通過；39 個必要檔案下載及
大小／官方 LFS SHA-256 核對完成，新增 22,768,349,036 bytes，盤點總 cache
41,711,365,409 bytes（含既有 repo/cache 與保守 WSL 用量），未刪既有資料。
**已完成的量測修理**：上述 UI 實例已補 RED→GREEN characterization；只將可識別、由本回合 action 引起的
產品資訊警告記為 product outcome 並安全關閉，未知 dialog 仍 fail closed。Windows runner
子程序已加 `CREATE_NO_WINDOW`，保留 stdout/stderr、精確 PID、timeout、terminate/kill 與
cleanup 語意；相鄰 117 tests 與 focused Ruff 通過，diff review 無 blocker。

第二版 frozen run `efa46489` 在 35 個完整結果後依使用者要求停止；精確執行中 child 已確認
退出，partial 只保留工程證據、不納入 Pilot。這 36 份已寫 result 的 baseline 顯示模型載入
中位數 7.424 s、整題中位數 12.854 s，載入占總 wall time 57.0%；fixture 中位數 0.289 s、
decision 中位數 2.049 s。每題 fresh process 雖隔離嚴格，但 300 次載入不是研究條件，模型
載入本來也另行統計，故改成每個 model×RAG condition 一個 owned child／一次 cold load，
同條件 30 題依序執行。

Condition worker 只重構 `scripts/dev` runner/case seam，不改產品 runtime owner、prompt、題庫、
scorer、UI 或 public contract。每題沿用既有正式 `reset_session` 與 `reset_conversation`，重新
建立 fixture、trace、UI driver、case deadline 與 result；進題前 fail closed 核對零 active
operation／turn／pending interaction、空 conversation/transcript、初始 pipeline stage 與同一
pinned runtime。prompt capture 需用序號範圍精確綁定每題，warmup 每 condition 只做一次。
Parent 對 condition child 保留精確 PID、硬 timeout、stdout/stderr、journal 與不重送 started
condition；任一 case 或 reset audit 失敗立即停止並保留所有已完成結果。先用 synthetic/real Qt
characterization 證明兩題不同 fixture／conversation 無污染、child timeout cleanup 與 resume
語意，再跑一個 2-case 真 GPU before/after probe，確認只載入一次且決策／capture 完整，最後
以新 clean commit 從 0/300 重跑。不得把舊 176／35 題與新 source 混成一批。

Owner 前後不變：產品 model process 仍由既有 LocalRuntimeProcessOwner 擁有，Study mutation
仍由 ApplicationService 擁有；研究 parent 由 per-case child scheduling 收斂成 per-condition
child scheduling，不新增產品 owner/state machine/receipt。刪除候選為每題重複 runtime
bootstrap、warmup 與 RAG warmup。回退為 condition runner/case adapter 與 tests；若無法證明
reset isolation，回到 fresh-process 設計而不宣稱效能改善。production LOC +0/-0。

**Condition batching 施工狀態**：parent manifest 已升為 v2，依 condition 分成 10 個 hidden
Windows children；每個 child 一次 cold load／warmup，30 題各有獨立 hard watchdog、fixture、
trace、UI driver evidence、prompt capture range 與 result。case 之間經正式 reset owners 並
檢查空 pipeline／conversation／transcript／pending interaction／owned jobs；parent 只為 child
實際回報的 case 建 journal terminal，不把未開始題偽造成失敗。Report 將 model load／warmup
每 condition 計一次，case timing 仍逐題。相關 128 tests 與 Ruff 已通過。
第一個真 Phi-4/RAG-off probe 在模型完成一次載入／warmup後、首題進入 boundary audit 時
fail closed：產品 `pipeline_stage` 契約為字串，runner 誤當 Enum 取 `.value`。沒有送題或產生
模型成績，condition cleanup 通過。已補最小 RED→GREEN 與 parent 相鄰 29 tests；舊 probe
只保留工程失敗證據。修正後以 frozen `c31a8559` 重跑同一真 GPU／真 Qt condition：30/30
結果均為 recorded、cleanup 與 case boundary 通過，conversation／visible transcript／active
operation／pending interaction 皆在每題前歸零，逐題 prompt capture 與 input audit 無 issue。
模型只 cold load 一次（8.002 s），30 題 condition wall time 108.011 s；相對先前 fresh-process
36 題實測的整題中位數 12.854 s，30 題推估 385.620 s，減少約 72.0% 無研究價值的等待。
Probe report 保留為 partial engineering evidence：有效 decision 30/30、無 missing／invalid／
timeout，first／final macro 皆 0.648；低分不重送也不當成 runner 失敗。此 probe 當時仍不是
Pilot 完成；後續完整 frozen 300 題結果如下。
當時已有基本報表與 B0 封存／環境還原；後續已補完整可讀報告及還原後真實測量，見 Current。
UI layout／文案／產品互動不變；只改研究 driver 對既有警告的觀測分類與 runner 的 console
presentation。回退為這兩個 script seam 與 tests，不改產品 owner/public contract。
**當時出口**：frozen `ac8af81d` 的 300/300 題完整執行、基本報告與 B0 環境還原已完成；
Test 未讀取。缺資訊題的 prompt/history/RAG 由逐題 input audit 核對，fixture setup 不取代此 gate。

模型唯讀 preflight 找到下列官方 pin，使用者於 2026-09-21 批准下載；尚未認證載入成功：

| 官方來源 | 候選 revision | Safetensors 權重大小 | 權限 |
| --- | --- | ---: | --- |
| [Phi-4-mini-instruct](https://huggingface.co/microsoft/Phi-4-mini-instruct) | `cfbefacb99257ffa30c83adab238a50856ac3083` | 7.672 GB | MIT；已下載／核對 |
| [Llama-3.2-3B-Instruct](https://huggingface.co/meta-llama/Llama-3.2-3B-Instruct) | `0cb88a4f764b7a12671c53f0838cd831a0843b95` | 6.426 GB | 既有帳號 access 通過；已下載／核對 |
| [gemma-3-4b-it](https://huggingface.co/google/gemma-3-4b-it) | `093f9f388b31de276ce2de164bdc2081324b9767` | 8.600 GB | 既有帳號 access 通過；已下載／核對 |

官方 shard metadata 加上既有兩個 Granite，五模型權重合計約 34.571 GB，尚不含其他
cache／設定／tokenizer；超過原 20 GB 總上限。使用者已批准上述精確
來源下載至 `D:\XBrainLabCache\models`、研究期間總模型 cache 上限提高至 50 GB；先
精確盤點現有用量，若仍超限便停，不刪共用模型、不繞過條款，也不代使用者接受條款。
五個 pinned tokenizer 都完成原生 system／untrusted context／request template 檢查。
兩個 Granite、Phi、Llama 依序完成 Windows GPU BF16 load→32-token engineering generate→
close，四個 owned child 均確認退出。32-token smoke 不等於正式 512-token／8K prompt
壓力測試、GUI tool outcome 或 Pilot 分數。Gemma 的 tokenizer 成功，但 load 在物化前拒絕。
全部維持 `trust_remote_code=False`、local-files-only，不代接受條款、升級或 silent fallback。
產品 allow-list 仍只含兩個 Granite；研究已重用既有 `engine_factory`／lifecycle 接點。

**Gemma 限制**：研究候選估算 12,000,000,000 bytes 尚非實測 peak；既有 model-load guard
在 required > 75% available 時 fail closed，因此需至少 16,000,000,000 bytes 可用。
所有本 agent 模型程序退出後再查為 15,738,077,184 bytes，尚差 261,922,816 bytes。
這是 admission rejection，不是 OOM、模型錯誤或準確率；不為過 gate 降低未測估算、不
關無關程序。原生權重 header 確認 BF16 tensor 共 8,600,158,944 bytes；加最保守 full-length
KV 為 9.741 GB，但尚未含 activation/workspace/allocator，不能用來假裝總 peak 已知。
使用者後續批准 Gemma NF4/BF16，量化 estimate 已依實測上調為 11 GB，沒有繞過 guard。
本機 evidence：ignored `build/dev-artifacts/model-preparation-20260921/`，含下載 receipt、
各模型 smoke（包括 Gemma 失敗）、bank-hash selection 與 initial fixture report。

### 直接必要 runtime slice（2026-09-21）

**2026-09-21 已批准 Gemma 量化修理**：只將 Gemma 研究配置改為 bitsandbytes
NF4 4-bit／BF16 compute，其他四模型不變。沿用官方 pin／已下載權重，不改日常
settings、不下載或升級共用環境。原 12 GB BF16 估算被既有 75% guard 拒絕不是 OOM。
先 RED tests，再由既有 immutable spec 攜帶量化 estimate/type/compute；research factory
固定配置並拒絕漂移；default product 4-bit 行為不變。研究量化固定指定 GPU，不 offload。
初始 estimate 依 pinned tensor headers：BF16 8.600 GB，其中 embedding 等未量化
1.355 GB、候選 Linear 7.245 GB；保留 metadata、保守 8K KV、activation/workspace
與載入暫存餘裕，先估 8 GB（未實測）。保留既有 75%/90% guard 與 OOM cleanup。
Focused：量化/非量化 admission、無 estimate/漂移拒絕、dtype/device/pin、相鄰載入與
OOM tests；Windows native load、代表性 prompt/output、peak memory、cancel/reload/close。
新 evidence 不覆寫舊拒絕；實測超出估算須上調重驗，不為過 gate 降低。
Owners 不變，無新 class/state/receipt；optional spec fields 與既有 backend branch。
UI unchanged；回退只移除此配置接合，不刪共用模型或證據。出口為安全實測及獨立 review
後接續 runner/Pilot，不將 smoke 當 Pilot 或 BF16 accuracy。

**量化驗證結果**：初始 7,025-token input 的 peak reserved 8.869 GB 超過 8 GB
analytic estimate；如實保存並上調為 11 GB。較強 7,671 input＋512 output 原生生成
35.62 秒，peak allocated 9.375 GB／reserved 9.878 GB、400 個 Linear4bit，全部 CUDA。
直接 engine 同程序 unload 後仍保留 allocator pool，故 reload 被 11 GB guard 拒絕；
保留此限制，不把它說成成功。產品實際 owned-process 邊界另驗兩輪載入／串流／
並行消費時取消／再生成／close；均成功且 child 退出，可用顯存前後同為
15,738,077,184 bytes。第一版 cancellation probe 同執行緒不消費 stream，觸發正常
hard-stop/restart-required；修正 probe 為產品同樣的並行消費，舊失敗保留。
Windows focused quantization／catalog／backend／injection 合計 99 tests 通過；
獨立 source review 無 blocker。工程 artifacts 為 model-preparation-20260921 下
gemma-nf4-*／gemma-owned-nf4-*，不計入 Pilot 分母，未宣稱 BF16 速度或品質等價。

證據：`AgentWorker` 已使用 owned process，但固定建構預設 engine，且每次生成重新讀取
日常 settings；`LocalBackend` 三處直接取 product spec；系統角色與連續 user roles 能力
混在同一 flag。五模型研究不可經 Settings 正規化而無聲換回 Granite。
Outcome：既有 runtime 注入不可變研究 spec／frozen generation config；預設產品行為與
allow-list 不變。UI 文案／layout／public tools 不變，不建立第二個 controller 或取消 owner。
步驟／接點：`LocalBackend` explicit spec 與固定 template kwargs；既有 `LLMEngine`
接受 backend factory；`AgentWorker` 透過既有 `LocalRuntimeProcessOwner.engine_factory`
傳入可 pickle 的研究 factory，選用 frozen config loader；`LLMController` 選用 worker factory。
`LocalModelSpec` 分開連續 user role 能力，Granite 現有 prompt 保持不變；Gemma 只作官方
template 必要相容，Llama 固定模板日期。不改 product catalog membership、download policy
或 runtime lease／cancel／close 實作；MainWindow 接合另先核對既有 lifecycle seam。
Complexity review：刪除／收斂候選為重複 spec lookup；owners 前後不變，不新增 public class、
state machine 或 receipt。實際 runtime production +91/-12/net +79 LOC／5 files，屬研究
接入功能而非純重構；MainWindow 接點另 +5/-2/net +3。可獨立回退，不刪下載模型／題庫。
Focused：既有 local backend／engine／worker／controller characterization 先通過；新增
default policy 拒絕、spec/config mismatch、固定模板與 settings、Windows spawn／stream／
cancel／close 測試。外部權重隔離允許 mock，但 owned process lifecycle 必須實際執行。
獨立覆核 default-policy bypass、父子程序身分漂移與 shutdown；主 agent 核對實際 diff。
此 slice 出口為上述工程證據閉合，之後接真實 GUI／Command 觀測；不冒充 Pilot 完成。
研究端接點 `scripts/dev/assistant_pilot_models.py` 僅固定五個既有／批准 spec，重用
LaunchSpec／SettingsSnapshot 與 module-level engine factory；拒絕未列模型，不替產品
新增 resolver policy。Pilot 初始工程配置沿用 structured-decision greedy／512 output，
8,192 context、seed 0；四模型 BF16，Gemma 依後續批准 NF4/BF16；
Llama template 日期固定 2026-09-21。
這是先行 smoke／Pilot 配置，不提升為正式實驗參數。Focused：完整 pins、未知模型拒絕、
frozen config 重建互不污染、spawn pickle 身分、existing two-model product catalog 不變。

Pilot selection 準備：不依模型結果選題。DEV A01–A18／C01–C06 各選字典序第一個
family，N01–N03 各選前兩個 family；family 內選最長 input，平手以 case ID 排序。
保留 30 個不同 family、18／6／6 配額、18 action tools；第一階段固定 A05、A08、
C01、C02、N02 第一個 family、N03 第一個 family（2／2／2、含 GUI 與直接操作）。
只保存 bank hash、選題規則、ID 與分階段順序，oracle 不進 prompt；拒絕錯誤 ID、
不足配額／重複 action tool／VALID 入選。接點為既有 `assistant_pilot_bank.py` 的純函式，
focused synthetic bank tests 保護順序不受輸入排列影響、更新 bank hash 不能偷用舊身分。
實際選題最長版本僅 37–81 字元：包含本題庫相對較長變體，不宣稱 long-context 壓測。

### 真實 fixture／UI 接合 slice

**正常路徑 observation slice**：重用 controller generation／dispatcher／runtime signals，
script 收集 per-case/per-generation 原始 input/output、confirmation、Command、UI handoff
與 turn terminal；不接受 oracle、不代執行或推導成功。controller 只在既有 parser／
ToolAttemptDecision 位置加 best-effort 診斷（含拒絕）；不重評 admission，不新增 owner。
觀測有界、時間戳與關聯身分明確，缺漏／截斷標為無效量測；GUI visible-ready 由後續
實際 Qt driver 另觀測。先已知完整／拒絕／錯誤／缺失 trace tests，再真 Qt controller
路徑驗證；獨立 lifecycle review。無可見 UI／工具契約變更；回退只移除此診斷接點與
research collector，不改既有執行／取消政策。此 slice 完成後仍須 runner 與真 Pilot。
RAG off 由 controller 的明確研究建構選項跳過 start/retrieve，沿用既有無檢索組裝路徑；
預設 on 不變，不用 failed/degraded retriever 假裝 off。On 須另驗 ready/檢索無錯誤，
embedding 唯讀共用、可寫 vectors 在研究 run 隔離；corpus 不加題目／答案。

**真 Qt driver／單一入口**：script 只對 isolated synthetic case 的實際 confirmation card
按批准；按真 handoff route 觀測 visible/enabled dialog 或實際 panel/view，保存畫面，
開窗題在 ready 後透過真 Cancel 收尾。不憑 oracle 挑畫面、不合成 resolution，不對未知
提示框任意 Yes。Start/Saliency 另待真 job terminal，不能以 turn terminal 代替。
每題 fresh Study/MainWindow/owned runtime，先固定 settings/prompt/log/RAG/output 隔離；
模型 load/warmup 與單次決策120秒分列，case process 有硬 timeout；只停自己的程序。
父入口固定 DEV30／5model／RAGon-off／seed0，先6題60次再24題240次，支援指定條件與
同身分續跑，不覆寫結果或重送已開始但未終結的case。總4小時含setup/load/cleanup；
到限保存partial。Source/environment/hash漂移拒絕續跑；先合成正反例與真Qt工程驗證，
再凍結commit跑Pilot。A14 CPU live fixture 明確10000epoch ceiling，仍只有12trials；
只為維持running初態，在decision完成/120秒時立即stop，另≤10秒cleanup；自然先完成
為fixture drift不是模型錯誤。其他completed fixtures仍1epoch，不增加EEG研究範圍。

問題：舊 fixture 是 128 Hz／4 channels，與本題庫的 250／256／512 Hz／5 channels 不符；
部分舊 helper 會刪共用 temp 目錄，不能直接沿用。`MainWindow.init_agent` 固定 manager
建構，研究不能在啟動後偷換 controller／engine 或以 debug transport 取代正常路徑。
Outcome：逐 case 專屬新目錄中的 deterministic EEG，經既有 Scan→Preview→Validate→Apply
與 preprocess／epoch／split／train Commands 產生真實狀態；fixture、publication、callable
tool 必須核對，不以人工 stage 字串或 oracle 偽造。fixture 配置只建初始狀態，不執行待測動作。
接點：研究 script `assistant_pilot_fixture.py` 與直接 integration tests；先覆蓋 empty、
data_loaded、preprocessed、epoch_ready、dataset_ready，完成／執行中 training 與 saliency
必須用真 job，另驗取消／close。不得呼叫會刪 global temp 的舊 helper，原資料唯讀。
UI 只為 `MainWindow` 加可選 manager factory，預設仍建相同 AgentManager；研究沿用既有
AgentManager(runtime_lifecycle=...) 與 lifecycle.start(launch_spec=...)，在 UI 綁定後啟動。
不新增研究 resolver、不走 Settings／model switch，不改可見 UI；controller／Command
owner 不變。constructor/init_agent 實際 +5/-2/net +3 LOC，無新 owner。
Focused：預設 MainWindow lifecycle／shutdown baseline、factory 真 Qt 綁定與 close；fixture
以實際 service publication／channel／sfreq／event／split 檢查。相鄰 UI 流程不全套重測。
Rollback 僅移除 factory 參數與新研究 script/tests；不清共用 cache、原始題庫或 EEG 檔案。
slice 出口後接 observer／runner，非 Pilot 完成；等待 signal／GUI handoff／模型錯誤各自記錄。
實際 30 個選定 DEV 的 initial-state fixtures 均已經真 Commands 驗證；另補五個
job-dependent case 的真 CPU training／Gradient saliency，fixture suite 32 tests 通過。
真 Qt driver 及 adjacent host 17 tests 通過，包含真 completed saliency render。
以上只是初態及量測準備，不是 30 題模型結果或完整 Pilot。
observer source review：既有 generation request/events、dispatcher input/confirmation、
command completion 與 runtime turn terminal 可重用；Host admission 及可見 surface-ready
尚無完整觀測。須在既有判定接點加 failure-isolated diagnostic notification，或研究端
Qt show/next-loop 觀察，不攔截 execute、重算 admission 或把 modal 關閉當開窗延遲。

**2026-09-21 runner 整合修理／證據**：原 helper 在 composer 空白時等 disabled Send，
真 host 工程 attempt2 因而未送出；已改填入後等待 ready，真 Qt regression 保護。
Gemma attempt3 正常走完三次格式錯誤與耗盡終態，完整 raw／capture／scorer、cleanup；
這是有效模型失敗，不是正確回答。Granite4 RAG-on engineering bandpass 已真正執行
8–30 Hz 濾波、記錄 Command／publication 並正常 close。兩者不是 workbook 或 Pilot。
Decision clock 改採實際交付／回覆事件，不以 provisional envelope 結束修復計時；
job 從永久 identity/result 追蹤，不只 poll active；UI pending drain 後才產出結果。
Windows venv launcher 有兩層 PID：已用 base interpreter＋child-local launcher hint，
原生確認實際 PID＝Popen PID 且仍用同 venv；不終止無關程序。
Training 初態改在暖機後建立；turn 終態或120秒定點停止 runner 自有初始 CPU job，
明列 runner cleanup，不算模型 stop 成功。真正 stop engineering case 被 Host stale
publication 擋住，保留原始證據並釐清，不修改模型/prompt來追分。
Prompt provenance 核對初次 fresh history、當題 input、state card 與 untrusted RAG 分離；
缺資訊英文語意仍由人工覆核，不宣稱字串檢查能證明。後續已完成 Product Outcome、
報表、callback exception／cancel工程檢查及 source freeze，再完成全部 300 題；未因 checkpoint 停止。
整合 complexity review：production 六個既有 files 共 +197/-24/net+173 LOC，
owner 數不變；沒有新增 production class/module/state machine/receipt。研究 scripts
分別擁有 bank、fixture、配置、passive trace、UI driver、case composition、sequential
journal 與離線報表，均不替代 ApplicationService／Host policy。暫無可刪的產品 owner；
需要的注入 seam 可整組回退，原模型／設定／題庫不動。逐題 fresh runtime 的載入成本
獨立報告；這輪先確保可核對，並不宣稱此 runner 已優化成最高吞吐量。
取消的 prompt capture 另保護 late-chunk 邊界：僅 host terminal 與 capture status
均 cancelled 時，可接受 host raw 是 child raw 的嚴格 prefix，保留未觀測尾段長度與
兩份原文；scorer 不使用該尾段補分。完成／錯誤或非 prefix 不一致仍無效。
真正提交後、生成前便達決策 deadline，須有同題 submission＋cancelled terminal；
可記為尚未送入模型的有效 timeout，不偽造 prompt。Qt poll exception 留存 error 後
走正常清理；不能穿出 callback 造成無證據的 native abort。
兩批整合 focused tests 為146＋137通過；之後直接新增的報表／callback／取消 tests
另依其實際結果核對。兩個 MkDocs strict build通過。實際 Windows --prepare 已核對
300 jobs／五模型／embedding hash；執行拒絕 dirty source，後續完整 Pilot 已由 clean frozen source 完成。
最後的 Product Outcome 已接合：正確 decision／Host blocked／實際 Command／GUI
handoff 分列；driver Cancel 只證明可開窗，不說匯入完成。錯誤工具真的執行仍保留
observed_actions；Saliency 精確綁定本次 compute operation ID，不以舊 fixture job代替。
有匹配 request、clock、screenshot 的 UI timeout／render failure 是有效產品失敗，
缺觀測才是無效量測。新 saliency engineering attempt2 已真模型執行／渲染完成並
通過新 binding；舊 artifact 不補造 ID 或覆寫。獨立覆核 blocker 已解除。
Runtime／passive observer 切片提交於 `aba24e5c`；最終 runner 由 clean `ac8af81d` 執行完整
manifest。300/300 均 recorded，10 個 condition cleanup、每題 boundary／capture／input audit
全數通過；正式 report 為 non-partial、完整 selected schedule，總 active time 1,876.047 秒。
模型錯誤與低分照留不重送。B0 tag 為 `assistant-b0-20260921-ac8af81d`；E 槽封存約 1.4 GB、
3,136 個檔案逐檔 SHA-256 通過。五模型 66 個 snapshot 檔（34,655,741,445 bytes）與 11 個
embedding 檔（91,578,415 bytes）重算一致；大型資源維持 D 槽單一受控 cache，不重複複製。
從 bundle 在 E 槽隔離 checkout、由外部 Poetry 2.3.4 建立全新 Windows venv，三個 PyTorch
套件均為 `+cu130`、`pip check` 通過，非 Test prepare 重建 300 jobs 且所有身份相符。
第一次把 Poetry 裝入目標 venv 的錯誤方法與 PowerShell 中文路徑失敗均保留；修正後 ASCII
wrapper 的 PrepareOnly 單一命令通過。這不是產品 merge 批准或正式模型排名。

**歷史交付更正**：上述完成宣稱未區分基本報表與完整可讀輸出，也未取得還原後真模型／工具
測量；後續補驗及限制由 Current 擁有。M4 仍是後續研究決策。Context compaction、完成一個
slice、CI pending 不是完成。

## 已結束的共同基線

PR #143 啟動器、#144 研究準備與 #145 RAG／直接手測修理已合併；
本輪起始 main 為 `8636a754`，實際 Git／PR 擁有版本事實，不重做舊候選／手測。
#145 包含 Assistant preprocess 回應性、首次 data split receipt stale 與 Visualization
publication 修理。舊 81-case 證據仍有原先 bounded 限制，不是本研究 Pilot 成績。
Split WIP 已依使用者批准刪除，不能再列為待保留分支；主工作區本機設定、資料、
必要歷史證據與共用環境保留。

## 歷史 — 前期第二主線研究里程碑（M1 核對、M2 與 M3）

2026-09-19 使用者確認先備妥完整計畫與里程碑，完成題庫及系統前置驗證，再進入 pilot。
本節保存前期 Pilot 的歷史安排，不再派工；新版初始基準的結果見 Current，
後續候選以上方 Future 為準。[Assistant 研究與實驗規格](../validation/thesis_protocol.md)
擁有目前題數、模型、計分、實驗條件、預算與證據契約。

- **起始問題與證據**：已累積方法決策，但逐項討論缺乏整體交付順序；研究規格第 7 節當時明列
  正式題庫、五模型 runner 與完整 outcome／報告接合未完成。舊 calibration 不是新實驗就緒證據。
- **Outcome**：以 M0–M6 串起計畫、題庫、系統、pilot、改善、選版與結果；每階段有可核對出口，
  不用「系統應該沒問題」或完成一個小切片代替整階段完成。
- **目前位置**：M1／M2 與 M3 Pilot 已完成；非 Test 題庫、fixture、五模型 runner、真實 outcome、
  report 與 B0 還原均有 exact-source 證據。Test 仍由使用者封存，本輪未讀取。
- **下一步**：M4 Development 仍是 candidate；先由使用者確認有限改善範圍與速度目標，再施工。
  未定的正式 Validation／Test 細節仍於原決策時點處理，不提前解封或以 Pilot 選正式冠軍。
- **已完成 scope／non-goals**：以上方已授權範圍及明確三模型下載批准為準；不包括代接受新模型條款、
  任意產品契約／可見 UI 改動、正式 Validation／Test 或 M4–M6。封存 Test 不讀。
- **本次完成條件**：Pilot 報告與改善前基線封存／還原驗證；不是只交付文件，
  也不因此宣稱 M4–M6 完成或產品 handoff-ready。

### 完整里程碑與依賴

依賴順序：**M0 → M1 與 M2 平行準備 → 兩者皆通過 → M3 → M4 → M5 → M6**。
平行指工作安排；獨立且有益的 agent 分工依 repo 規則，GPU 排程與背景長跑仍受本輪預算／隔離限制。

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

以下為既有 source 接點盤點，不是 runtime 通過證據；施工權限以上方 active scope 為準：

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
直接必要缺陷已納入上方有限授權，產品契約或可見 UI 改變仍另作決策。只做單回合主分數的提案，不等於允許省略取消／狀態一致性測試。
模型精確來源、大小／VRAM、既有 cache 與可寫輸出位置須在下載前唯讀盤點，交付一份資源方案；
目前沒有選定新儲存目錄、下載模型、刪 cache、安裝環境或新增正式 CLI。

#### 本輪已授權的實作順序

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
- 每個 milestone 以具體交付與 gate 狀態回報；目前進度由上方 active 節擁有，
  文件更新不等於已通過題庫／runtime gate。施工只在已批准 scope 內持續，
  context compaction 或完成小切片不是停止或新授權的理由。
- 接手先讀上方 active、本節、研究規格、Git 與可辨識的執行狀態，再續作當前已授權項目；
  在 active 節更新進度、下一步與 blocker，不建立第二份工作日誌／控制平台。

下方是既有產品優先順序與候選背景，不覆蓋本輪授權至 Pilot 的範圍，也不授權本線施工其他候選。

## Historical order — Import UI → Assistant evaluator → cleanup/refactoring

以下為2026-09-16的順序與候選背景，不是目前狀態或派工入口；最新授權以上方Active為準。

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
