# XBrainLab Agent 目標

最後更新：`2026-09-28`

這份文件是 XBrainLab Assistant 產品目標的唯一權威。Runtime inventory、目前測試集合與歷史
artifact 只能描述 current implementation，不能反推本文件的產品契約。

## 整體基線設計討論（2026-09-28） { #agent-baseline-design-discussion }

本節保存整體Agent契約。2026-09-28使用者以「開工吧做到我手測」批准按M0–M5推進，
包含下方統一提案的有界可行性檢查與遷移；具體數值仍須按已列規則驗證，不代表runtime已完成。
既有工具ledger、來源驗證與confirmation仍有效；已確認的統一追問方向取代下述Host補值
捷徑目標。更正、單一要求生命週期與上下文限制已確認如下；未完成遷移前不改runtime保護。
實際版本／限制見[目前架構](../architecture/agent.md)，施工狀態只由[Now](../planning/now.md)擁有。

### 已確認的方向與分工

目標是先建立設計合理的共同基線，再進行既定範圍的Development；不是先把每個部件對
當前模型／工程題調到最好。先討論整體架構、施工目標與完成定義，不讓RAG成為其他組件
缺陷的補丁，也不以能執行／安全擋錯代替基本能力與設計合理性。整體審查不預設全面重寫。
使用者再次確認資源有限：本輪以合理設計、已知缺陷修復與必要可用性證據為終點，
不做候選調優競賽，不為通過固定案例堆例外或追求局部最佳；準確率打磨留到Development。
此處Development只指研究規格已列的調整項目，不包含RAG。使用者明確要求RAG本輪就要
對模型有實際幫助，必要的語料／呈現／檢索參數調整在本輪完成，再封存進入Development；
不能把「避免過度擬合」解釋成只求檢索能跑，或將RAG有效性留待日後。

| 責任 | 已確認的界線 |
| --- | --- |
| 模型 | 理解要求，選擇回答、追問或提出一個操作，辨認使用者提供的參數。 |
| Agent程式 | 準備一致資訊，保存必要對話／追問狀態，解析與驗證提案，管理確認、取消與執行交接。 |
| 產品後端 | 提供真實狀態與可執行性，執行操作並回報真實結果；沿用既有ApplicationService／Command owner。 |
| RAG | 補充參考說明與示範；不決定操作權限、不代填使用者未提供的參數、不充當intent router。 |

程式不以另一套自然語言heuristic偷偷替模型換工具、判斷完整意圖或猜參數。模型提案
不因被寫成結構就變成可信事實；來源／schema通過也不等於已證明語意正確或已准許執行。

### 討論順序與已確認的固定資訊

按部件逐段討論，不把討論清單當全面重寫清單：分工（已確認）→模型輸入→
歷史／追問→RAG內容與呈現→執行與回報→施工與驗收。模型輸入再分固定資訊、動態資訊、
參數來源三段；固定資訊、動態資訊兩類與統一追問方向已確認，詳細資料查詢擴張不列入本輪。
執行前明確更正、單一要求生命週期、上下文界線與RAG內容原則已確認；目前主線為施工與驗收。
training非同步的釐清見下方lifecycle契約，
不因此提前擴張其他工具或偏離資訊討論。

固定資訊只保留三類：

- 角色與能力範圍：EEG操作助理及精簡功能地圖，真正可用操作仍以當次後端發布為準。
- 回答／追問／操作規則：沿用下方單次決策邊界，不猜缺值，不擅自代做前置或多個操作。
- 工具與結果的理解：開窗不等於完成、提案不等於執行、啟動不等於工作完成；以trusted
  backend結果為準，遵守既定輸出格式。狀態／歷史／範例不自動成為本次指定參數。

不在固定內容塞全部選項、完整模型清單、EEG教科書或具體預設數值；個別工具用途／參數
沿用工具定義，不另手寫一份重複catalogue。這是內容邊界，不是已核准的完整prompt文字。

### 資訊設計草案：每回合六塊內容

以下是內容責任，不是新增六個模組、state owners或另一個資訊平台；優先重用既有來源。

| 區塊 | 具體內容 | 來源／提供條件 |
| --- | --- | --- |
| 行為規則 | 回答／追問／操作界線，不猜參數、不虛報完成，輸出格式。 | 固定產品規則，每回合提供。 |
| 產品基本事實 | 功能用途、真實介面名稱、開窗與直接操作的差異。 | 既有產品定義／受維護說明的精簡投影；不是模型常識。 |
| 當前軟體狀態 | 所處階段、該階段的資料／設定／執行狀況、可靠性。 | 同一份最新後端publication，按階段投影。 |
| 操作契約 | 當前可用工具的用途、參數schema與必要限制；不可用操作的原因。 | 既有工具定義與後端能力，不能由對話或範例授權。 |
| 當前對話 | 最新要求、必要原文、待處理追問、來源已核對的參數。 | 使用者對話與單一pending interaction；責任已確認，具體格式見下節待定項。 |
| 參考材料 | 檢索到的使用示範／說明，附來源並標為參考。 | RAG；正常零命中可沒有此區，故不能承擔操作必需資訊。 |

「支援訓練」是產品事實，「split尚未完成」是軟體狀態，「請開始訓練」是使用者要求，
不能混成同一個指令。RAG範例不會因為與要求相似而授予缺失參數、capability或confirmation。
產品說明內容若尚無可靠來源，不能默認已有知識庫；來源清單與缺漏行為仍待定。

### 動態資訊：兩類已確認，具體投影待定

軟體state由後端擁有；對話state只記錄要求處理進度，不能另建或覆寫workflow truth。
使用者已確認預設動態資訊收斂為兩類：「目前處於什麼狀態」及「可用操作／阻擋原因」。
每回合取同一份最新後端publication的必要摘要，不另建Agent readiness或工作狀態owner。
具體欄位仍待定，不代表已批准刪除現有snapshot欄位或開始source施工。
每欄須說明少了它會影響哪個判斷／回答，
不能因後端有資料就全部提供。下表取代先前將數量／取樣率等列作預設資訊的寬泛草案。

| 階段 | 建議預設資訊 |
| --- | --- |
| 尚未匯入 | 無資料的事實，匯入／導覽可用性與相關原因。 |
| 已載入／預處理 | 已有資料與目前階段；相關操作可用性／阻擋原因。 |
| 已有epochs／準備訓練 | 已有epochs；訓練是否可啟動，缺少哪些必要設定。 |
| 訓練中 | 訓練仍在執行；停止與其他操作的可用性／阻擋原因。 |
| 訓練完成 | 結果是否可用；相關分析操作可用性／阻擋原因。 |

完整recording／subject／channel清單、取樣率、歷史filter值、訓練設定、逐epoch紀錄、
結果數值及路徑不預設全量附上。使用者確認詳細資料查詢不是本輪重點：先做好操作、
必要追問與可用性說明，不擴張成完整資料查詢助理，不新增query工具或隱藏intent router。
已有可靠且適用的資訊可以回答；沒有時明確說明，依真實介面引導查看，不猜資料或介面位置。
此決定不刪除既有能力，也不減少後端執行與驗證需要的資料；不以設計按需查詢機制阻擋主線。
例如目前256 Hz不代表使用者要求重採樣至256 Hz；舊filter值不代表本次授權沿用。

區分Assistant回合忙碌與產品背景工作：等確認／GUI完成時，既有程式阻擋新普通要求，
不需另把等待狀態清單交給模型管理；training可在回合結束後繼續，下一次決策須看到最新
訓練狀態與操作資格。依各工具實際回合終點檢查，不以「大多block」一概推論；不新增
通用背景工作owner。缺參數等待下次回覆則屬於對話／追問進度，另段討論。

多recording若不同取樣率／通道，不能壓成虛構單值；未知不能以零／預設值冒充已知。
科學範圍與可執行性仍由後端判定，不在Agent重寫一份。開窗工具不必附帶完整dialog所有
選項；但若承諾回答具體選單內容，須有真實產品來源，不得從一般模型知識編出選項。
State只決定預設資訊重點與操作資格，不等於禁止詢問其他階段的功能；跨階段詳細說明
如何取得、未取得時如何回答仍待定，不默認新增query工具或第二次LLM路由。

### 已確認：統一模型理解＋程式累積進度 { #unified-clarification }

2026-09-28使用者確認：以責任清楚、可靠與可維護性選方案，不以最小改動保留不合適的
舊流程。一般文字回覆包含單純補值，均走同一套模型語意理解；不再以Host的特殊補值
捷徑繞過模型，也不增加第二套自然語言keyword router。GUI確認／取消按鈕仍由程式直接處理。

- 模型接收原始要求、相關追問／最新回覆、累積參數及必要來源，理解本輪是補值、更正、
  取消或詢問等，提出本輪處理／參數變更；不獨自保管記憶，不自行發布成功或取得執行權。
- 程式持有同一要求的一份累積紀錄：待處理操作、已核對參數、對應使用者原文、尚缺欄位
  與追問進度。驗證提案後更新；普通補值只合併新值，模型省略舊欄位不能等同刪除或覆蓋。
  原句已提供的參數也須在第一次追問前保存，不只保存後續回答。
- 後端仍擁有狀態／capability與科學驗證。資料湊齊後重讀最新publication，經來源、schema、
  range、capability及必要confirmation才可執行；一回合最多一個操作，不自動多步續作。

例如「bandpass，下限7 Hz」→追問上限→「30 Hz」：程式先保存已核對下限7與來源，
下一輪理解30為上限、核對來源後加入，不能以新回覆覆寫整份參數。保留提供參數的必要
原文及問答關係，不因超出最近一輪丟失；不保留無界聊天、不新增逐回合摘要模型、通用
記憶平台或第二份可變參數owner。既有pending owner可重構，不因追求最小diff而堆特殊分支。

這取代舊目標的Host直接收集bare值／bandpass排序與無模型補值完成路徑；每次文字補值
增加模型理解的等待成本是已說明取捨，不承諾更快或更準。來源核對不等於完全證明語意
正確；模型理解、更正與誤判仍須以真實多回合案例驗證，不用Host救援灌高模型分數。

模型輸出schema與來源表示見[已批准的M0契約](#agent-m0-contract)，具體token分配須實測；
生命週期與超限行為依下方已確認規則。
不因本方向批准而允許靜默覆蓋、無界prompt或stale執行。
Source已遷移此累積要求契約；驗證與未完成缺口見Now。舊實驗／工程gate保持版本身分，
不能宣稱舊gate已驗證此新流程。

#### 已確認：執行前的參數更正

操作尚未執行時，使用者可明確更正指定欄位；模型辨認更正意圖與對象，程式核對來源與
合法性後更新該欄位及來源，保留其他已核對參數，不要求整份重講。不因模型漏寫而刪欄位。
這取代舊的「遇到correction一律清除receipt並重啟」流程。

- 已有下限7、尚缺上限：「下限改成8」更新下限並繼續追問上限。
- 同情境：「上限30，下限改成8」同時核對補值與更正；完整值為8–30後仍走正常執行檢查。
- 「改成8」若無法確定指涉欄位，先追問，不猜測或靜默覆蓋；不使用未確認的更正執行。
- 已執行的操作不是可修改草稿；更改對話紀錄不能撤銷產品副作用，後續按新的要求處理。

本決策不增加所有更正都要再確認一次的通用關卡，也不跳過既有必要confirmation。

#### 已確認：單一要求的生命週期與上下文限制

只保有一個待完成要求，不建立任務佇列或長期記憶；補值與更正沿用前述規則。

| 情況 | 目標行為 |
| --- | --- |
| 明確取消 | 清除該待處理要求與暫存參數，保留聊天紀錄，不執行；新要求不自動繼承已取消值。 |
| 中途問說明 | 先回答並保留待處理要求，不在回答後自動執行。 |
| 明確改做另一件事 | 新要求取代舊要求，不自動搬用舊參數。 |
| 插話或換要求不明 | 先釐清，不執行原操作。 |
| 資料／相關設定變動使原要求不適用 | 阻止舊提案，說明需重新確認；單純切面板不應一概清空。可執行性由後端擁有，Agent不另造policy。 |
| 執行完成、失敗或新對話 | 結束原待處理要求，不自動重跑、恢復舊要求或接下一操作。 |

取消待處理要求不是停止背景訓練或撤銷已完成處理；背景停止沿用既有工具與真實結果。
這取代舊目標中topic switch／任意publication變化一律清空等過粗規則；generation、
capability與執行前驗證不可略過，不能把保留對話進度當成允許執行stale提案。

程式保存與模型輸入分開：每回合只提供精簡規則、當前工具／必要狀態、最新訊息、
一個當前要求的有效參數及必要原文／問答關係，另附放得下的RAG參考。歷次參數版本、
全部追問與整段聊天不逐輪累加；要求結束後不再以待處理身分附上。設計文件不是prompt。

以選定模型的實際tokenizer及chat template計數，輸入加預留輸出不得超過model catalog的
runtime context；目前產品上限為8,192 tokens，具體分配須量測完整prompt後設定。
超限先移除非必要參考與無關歷史，不裁掉有效參數、必要來源、否定／條件或最新訊息。
必要內容仍放不下，就不進行本次模型推論，明示請使用者簡化或重新整理要求；不只留下
「30」讓模型猜，也不因單純超限默默刪掉已確認參數。保留要求不代表可略過後端失效檢查。
不增加摘要模型、不承諾無限歷史；不可信內容仍可能是必要證據，不能將不可信等同可丟棄。

舊runtime超限會退回system與latest user；遷移須修正必要上下文的保留界線，而非直接將
累積紀錄塞進可整包移除的context。驗證須包含補值、更正、長訊息及超限，不以僅能塞入
窗口當作模型已能可靠理解的證據。

### 已確認：RAG內容與呈現

RAG提供短小參考示範，不承擔必需規則。工具用途、參數格式、操作資格與缺值追問規則
由固定規則／工具契約／後端publication直接提供；正常零命中不能使這些資訊缺席。

示範覆蓋以下情境，具體語料仍須依最終schema整理驗證：

- 明確單一操作、參數齊全：正確工具與參數。
- 缺參數或操作種類不明：正確追問，不猜值或工具。
- 純詢問或明確禁止操作：正確回答而不操作。
- 多輪補值／更正：精簡的待處理狀態與必要來源，示範正確處理，不附完整長對話。

多輪示範以一個optional `prior_turn={input, expected_proposal}`表達，先限前輪為
clarify＋new_request；當前input為U2，前輪為U1。共用runtime的純schema／來源合併驗證
推導短pending投影，不接收外部宣稱已驗證的pending，不製造可執行publication。
當前execute須驗合併後完整schema。搜尋使用原要求＋當前user文字，不能把串起來的
搜尋字串當U1原文；模型參考保留真正U1/U2及expected proposal。此表示只支援必要的
一輪pending→補值／更正示範，並非通用對話重播框架。

反例指「不該操作的情境＋正確回應」，不是把錯誤tool call當答案提供給模型模仿。
所有示範必須符合最終核准的模型輸出契約，不混用舊格式，不重複整份工具說明；尚未
核准新schema前不自行改語料格式。範例值永遠不是本次使用者參數或執行授權。

RAG範例優先讓位給當前要求、累積參數與必要來源，遵守前述token上限。內容原則與下方
雙路檢索方向已確認；此決定未改runtime、語料或題庫，不能宣稱新語料已補齊或效果已提升。

#### 已確認：雙路獨立召回與RRF融合 { #rag-hybrid-design }

2026-09-28使用者確認以下設計基線，取代「dense cosine准入後BM25只能重排」的目標。
不是直接恢復先前已否決的聯集候選，也不是宣稱融合後必然改善小模型表現。

1. 查詢使用當前要求；補值時包含原要求、必要追問背景與最新回覆，不能只搜尋「30」。
   最新回覆不能被舊要求蓋過。以有界且來源明確的資料組裝，不增加LLM查詢改寫或keyword
   intent router，也不因pending action存在就忽略取消、插話或新要求的可能性。
2. BM25與向量在同一份當次eligible範例集合中各自召回；延續backend可用工具及
   respond_to_user資格限制。BM25候選不必先通過同一dense門檻；檢索不授予執行權。
3. 合併候選並依穩定example identity去重，以RRF融合排名，不直接混加未校準的異尺度
   原始分數。沿用現有retriever責任，不引入搜尋服務、額外模型或第二個檢索policy owner。
4. 最多提供三個符合相關性及token預算的短範例，允許少於三個或零個。語料整理移除近乎
   相同的重複示範，不強制「一正一反」或每工具一例，不為多樣性塞入不相關內容。
5. 語料以「輸入情境＋正確處理」組織；檢索文字以使用者要求與必要情境為主，提供模型的
   示例則遵守最終核准輸出schema。依操作、缺值、不操作、補值、更正的覆蓋需求整理，
   不以湊數量或複製驗收題為目標。

RRF只提供排序，不是相關性信心。舊cosine 0.7不能直接搬成RRF門檻，也不能把BM25
字詞有交集視為足夠相關；准入／零命中規則、候選數與融合常數須以固定工程案例核對後
明列與封存，未定前不得宣稱方案已完整驗收。模型／embedding暫不更換，不加reranker，
不展開無界top-k／權重搜尋。混合檢索缺一路仍按既有失敗／degraded規則，不silent fallback。

取捨依據：[OpenSearch RRF說明](https://docs.opensearch.org/latest/vector-search/ai-search/hybrid-search/rrf/)
支持用排名整合不同尺度訊號，也明示RRF分數不能當跨查詢相關性門檻；
[融合方法研究](https://arxiv.org/abs/2210.11934)顯示分數融合亦可能優於RRF，故選RRF是
清楚、可維護的設計起點，不是無須驗證的最佳解。既有聯集候選曾出現召回改善但小模型
退步；須在新上下文／追問契約對齊後核對檢索、完整prompt與真模型結果，不以召回數代替效果。

研究使用前須封存並對齊新基線／研究規格版本，再固定RAG設定；舊DEV initial、失敗
候選與既有0.7基線保留原身分，不合併成新成績，也不將新融合參數加入正式DEV搜尋軸。

### M0開工契約（已批准施工，先驗可行性） { #agent-m0-contract }

以下是2026-09-28計畫審查後獲准施工的契約，不是已實作或通過模型驗證的事實。
目的是一次核對跨parser、pending要求、prompt、RAG及研究入口的共同契約；不逐檔自行
發明格式，也不為了保持兩欄root而同時維護一套特殊追問格式。先檢查小模型輸出負擔，
不在證據不足時大量改語料；若需實質改變此契約，明示決策，不靜默另創格式。

#### 一份模型提案，不讓模型重抄整份已確認參數

2026-09-28實機互通後使用者批准簡化巢狀結構：以五個固定root欄位表示單回合提案：
`decision`、`mode`、`action`、`changes`、`message`。移除request外層，不移除來源驗證。
Public mode採明確操作對象的`update_pending`／`new_request`／`cancel_pending`；下文的
continue／replace／cancel只描述既有內部RequestUpdate語意，並非另受理的模型alias。
Parser做固定一對一名稱映射、序列化只輸出新名稱；不根據使用者文字改寫model mode。
這是替換現有`tool_name`／`parameters`模型輸出envelope的提案，會影響parser、格式修復、
語料與研究decoder；不是內部無感重構。既有操作工具名稱、參數型別、執行owner、
confirmation與可見結果不變；`respond_to_user`的回答／追問職責映射到reply／clarify，
不新增可執行工具，不將對話狀態變更變成後端Command。

| 欄位 | 草案契約 |
| --- | --- |
| `decision` | `reply`、`clarify`或`execute`；前兩者不執行工具，程式不因參數完整就自行升級成execute。 |
| `mode` | `null`表示不修改草稿（action=null、changes={}）；`update_pending`修改／補齊當前要求；`new_request`建立新要求並捨棄舊要求參數；`cancel_pending`清除當前要求。 |
| `action` | 現有操作工具名；continue須匹配待處理操作，replace須是本輪明確要求。操作尚不明的clarify與cancel用null。 |
| `changes` | 本輪明確給出／更正的參數map；每值含`value`、`source_turn`、`quote`。不包含未變舊值；cancel固定空map。 |
| `message` | reply／clarify為非空英文回覆；execute固定null，成功／失敗仍由真實工具結果呈現。 |

`continue`無pending、cancel搭配execute、execute無action、未知欄位、錯誤型別及矛盾組合
均不更新要求或執行。沿用既有一次格式修復上限；修復只處理提案格式，不重送已執行操作。
只有`execute`可將完整、通過驗證的累積參數交給既有工具路徑；它仍不是執行授權。
新要求即使參數完整也走replace，不自動把舊草稿搬過去；純回答／含糊插話用mode=null、
action=null、changes={}。不存在第二套舊巢狀輸出相容入口；內部RequestUpdate DTO不是模型格式。
clarify可保存本輪明確值，但不能提交仍有歧義的欄位；message不是程式判斷狀態的資料來源。
若原要求連操作種類都未確定，clarify＋replace＋action=null只保存要求原文與問答，changes
為空；不能把尚無schema可驗證的數字標成已確認參數。下一回合可用continue將null明確化為
一個合法操作，再核對原文中的參數；已確定action則不能藉continue偷偷換工具。

例：U1「Apply a bandpass filter with a lower cutoff of 7 Hz.」的提案：

```json
{
  "decision": "clarify",
  "mode": "new_request",
  "action": "apply_bandpass_filter",
  "changes": {
    "low_freq": {"value": 7, "source_turn": "U1", "quote": "a lower cutoff of 7 Hz"}
  },
  "message": "What upper cutoff should I use?"
}
```

U2「30 Hz.」只提`high_freq=30`及U2來源，mode=continue、decision=execute；不重抄7。
程式組成7–30後核對最新後端狀態、完整schema、科學限制與confirmation，再交既有executor。
同一草稿下「Change the lower cutoff to 8 Hz.」只改low_freq並clarify；「Change it to 8.」
若指涉不明則clarify、mode=null，保留7且不執行。「Why a bandpass filter?」用reply、
mode=null；兩者action=null且changes={}。「Cancel that.」用reply＋cancel；明確改做notch則replace，不沿用7。

#### 來源、累積與失效

- `source_turn`由程式配給實際user訊息，不讓模型創造或引用Assistant／RAG／後端文字作
  使用者參數。changes可引用本次訊息，或當前要求內仍適用、已提供給模型的必要user原文；
  例如先說數值、下一輪才確定操作／欄位。程式保存引用原文與本次確認的問答關係，不能
  為了「只能引用最新一句」丟失原要求的資訊。已保存值沿用原來源，不要求重新輸出。
  已取消要求或已被更正的舊版本不屬於可用來源；取回舊值須重新明確提供，不從歷史猜版本。
- `quote`須是該user訊息的原文片段，保留辨識欄位所需的單位／條件／否定；數值正規化與
  現有direct-parameter來源驗證沿用既有validator，擴充的是多回合來源接點，不新增Host
  自然語言intent router。非direct工具仍遵守自己的參數契約，不強迫enum字面值出現在原句。
  引用存在、數值可對上，只能證明可追溯，不能證明模型正確理解指涉或否定；須另以真模型測試。
- 所有changes先在暫存提案中核對，整包通過才更新唯一pending owner。格式／來源不合法
  不局部覆寫；欄位省略保留舊值，null不表示刪除。尚缺欄位由既有工具schema算出，模型
  不另傳一份權威missing list。完整值域／跨欄位檢查仍由既有validation及backend擁有。
- 程式保存action、有效參數及原文來源、必要問答、後端generation／turn correlation；
  不增加第二份mutable owner。模型不能輸出可信generation或改寫backend publication。
  執行前檢查若發現相關狀態已使要求失效，走既有拒絕／重新確認，不因來源有效就執行。
  非相關panel切換不抹掉參數；保留草稿不代表原publication仍有效。
- 不將新版提案塞進舊receipt再保留兩套解釋。遷移完成刪除舊Host收集、bandpass排序、
  舊兩欄parser入口與專屬fixture；舊輸出只可在有版本標記的歷史artifact reader離線讀取，
  不可回送產品executor；不為此新增通用歷史相容reader。不擴張新的持久化草稿或跨session恢復能力。

#### RAG准入草案：先分路判斷，再融合排序

2026-09-28後續明確批准修正：下列query-only v2規則的失敗保留，不再作新版本出口。
目前候選採至少2個不同query詞命中且max(query coverage, document coverage)>=0.5。
Coverage各為matched不同token之IDF總和除以該側全部不同token之IDF總和，沿用同一
corpus IDF，OOV以df=0處理。這是對稱詞法重疊，不是相關性概率；短例可能匹配到
帶無關附加詞的query，須以原正反例如實驗證，不保證排除所有誤召回。
最後实际送入模型的範例須符合固定相關性標註，無關query仍應零例，指定sparse正例
仍須補回。各路top10誤召回作診斷明列，不能冒稱已修好，但不再要求每個候選均相關。
不改原24題或標註、不使用新模型／reranker、不反覆調0.5；BM25＋dense＋RRF維持。
以下v2段落保留其設計與失敗脈絡，與新候選證據分開。

建議起始配置為每路最多10候選、等權RRF、rank constant=60、最終最多3例；不是最佳參數
宣稱。RRF採rank而非跨路原始分數；60是[OpenSearch既有預設](https://docs.opensearch.org/latest/vector-search/ai-search/hybrid-search/rrf/)，
本專案仍須工程核對，不引入OpenSearch依賴。相同分數以穩定example ID決定順序。

1. 固定同一eligible corpus、查詢組裝及索引身分，兩路獨立取候選，不能dense空集合就提早
   結束BM25。查詢只含必要user要求／問答，不把工具schema、輸出答案或整份state拼進去。
2. Dense分路保留cosine 0.7；BM25使用下方已批准的詞法覆蓋准入，不再使用跨query的
   原始BM25分數門檻。
   任一路通過即可進聯集，不要求BM25例再過dense門檻；各路在准入後重新從rank 1編排，
   只有該路通過的候選才貢獻其RRF分數。RRF不再設假信心門檻。
3. 2026-09-28使用者授權修正失敗准入及fixture契約。固定一個候選：至少命中2個不同
   query token，且命中token的IDF總和占query全部不同token的IDF總和至少0.5。
   IDF沿用BM25公式；未見詞以df=0計入分母，重複詞不增加覆蓋。先按eligibility與覆蓋
   篩選，再按原始BM25分數取top10；無token／非正分數無候選。不按候選最高分縮放，
   不新增意圖分流、逐題例外或stopword清單。這是詞法資訊覆蓋，不是相關性概率；
   冗長、改寫與單詞query可能沒有sparse候選，必須揭露而非靠dense掩飾指定漏例。
   [Elastic的混合檢索建議](https://www.elastic.co/search-labs/blog/semantic-precision-minimum-score)
   支持minimum-match類詞法控制，但不替本專案的加權式或0.5常數提供效果保證。
4. 保留v1原始分數門檻失敗證據，不改寫舊結果。v2在觀察分數前固定12個工程query與
   另一組12個覆核query及範例ID集合；多輪query必須由產品user-only helper組裝。
   標註判斷主題相關，允許同主題操作／說明／禁止的對比範例；不把範例意圖當模型答案。
   不據覆核結果回頭選門檻或複製進語料；含短／長查詢及既知漏例。
   詞法已知漏例須可補回、應零命中的query須零例、其餘回傳例須在事先標註的可接受集合。
   Dense路也接受同樣相關性檢查，不能靠另一條路掩蓋誤召回。
5. 若門檻無法同時保留必要詞法正例及排除不相關例，或覆核失敗，記錄「此簡單准入方案
   不成立」，不把門檻抬到全空冒充成功、不加逐題keyword例外、不改成dense全域否決。
   不宣稱RAG已完成；依Now資源原則提出有證據的修正或決策，不自動換模型／加reranker，
   不反覆換門檻／語料使這組覆核題通過。
6. 聯集去重、融合後按序取可完整放入token預算的範例，至多3個；無准入候選即零例。
   RAG只是可選參考，零命中不妨礙固定規則與工具契約。一路故障不偽裝正常零命中，沿用
   已有degraded／failure呈現；本輪不默默加單路fallback。

12＋12是有界工程核對，不是論文題庫、統計代表性或未知輸入保證；新版规则已授權施工，
不代表效果已驗證。語料定版後封存規則與hash；語料變動使校準證據失效，
不能在同一版本悄悄換門檻。token分配依完整template實測，必要內容優先且保留輸出空間；
本節不藉新schema擅改8192 context或研究512輸出上限。

#### 已確認：RAG本輪須有模型受益證據 { #rag-benefit-acceptance }

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

### 尚待決定：不能靠資訊清單自動解決的邊界

以下是剩餘設計／施工核對議程，不是新增功能清單；已確認行為不重開逐句討論。

| 議題 | 必須回答的問題 |
| --- | --- |
| 模型提案與紀錄格式 | 以何種schema表達補值、更正與要求生命週期，如何引用原文並驗證，不新增keyword router或第二份owner？ |
| GUI與新狀態 | 已確認失效原則如何對應既有後端publication與執行保護，不另造可執行性policy？ |
| 產品知識來源 | 哪些基本事實必須直接提供？來源如何與產品同步？跨階段說明、缺來源與RAG不可用如何分開處理，不偷加工具／能力？ |
| 歷史與預算 | 依已確認的有界上下文規則量測token分配、去重與必要來源表示，不悄悄截掉否定、單位或條件。 |
| 可信性與資料邊界 | 如何區分使用者證據、模型猜測、backend結果與不可信資料文字？檔名／標籤／RAG中的指令不能升格成policy；必要資料最小化且可追溯。 |
| 整合與研究一致性 | 產品和實驗是否走同一輸入／parser／驗證路徑？追問後的實際流程與單回合研究分數分開；哪些基本缺陷阻擋基線、哪些是已揭露模型限制？ |

固定／動態資訊、統一追問、更正、要求生命週期、上下文與RAG原則已確認。
[已批准M0契約](#agent-m0-contract)固定本輪schema、來源與准入施工邊界；驗證尚未完成。
其餘工程核對併入M0，不重新討論已確認原則；新public contract調整仍須取得批准。
即使payload內部存為JSON，也不代表LLM看JSON必然最好；序列化與精簡方式須服從內容契約，
不在此開啟提示排列搜尋或默認增加DEV變因。

### 整體施工出口草案與研究邊界

具體slice、責任／刪除範圍與交付出口集中在
[Now完整施工計畫](../planning/now.md#agent-baseline-construction-plan)，不在本頁另建第二份施工清單。

建議先核准整體設計，再逐slice施工與直接驗證；獨立reviewer先審責任／必要性，最後審
整合實作與證據。完成草案為：責任無矛盾／重複policy、必要資訊與參數傳遞完整、已知
基礎缺陷修正與補測、正常／追問／取消／失敗流程可用、記錄不把Host擋錯當模型答對。
這些出口仍須具體對應情境與證據後核准，不能只靠reviewer一句「沒問題」。

使用者要求補上獨立subagent對**實際完整模型輸入**的清晰度覆核，不能只審system prompt、
RAG或程式碼的單一部分。使用者澄清正式覆核安排在整體施工完成後，不是現在審未完成
的候選；審查標準是產品小模型的理解負擔，不是強reviewer能否自行推理補足缺口。
使用既有runtime capture機制取得同一候選版本經過組裝、限長、
role處理與chat template後的完整prompt；並核對組裝messages、實際token數、輸出預算、
模型／tokenizer／template／decoding設定與source身分。不用作者重寫的示意prompt代替產品輸入。

- 審查固定驗收案例的各回合實際輸入，包含必要的補值、更正、取消、插話、狀態變動、
  RAG零命中／不可用與超限情境；有format repair時也看repair的實際輸入。超限拒絕案例須
  證明未呼叫模型，不偽造成功capture。相同輸入可按身分去重，列清楚覆蓋與未覆蓋範圍，
  不把單一happy path稱作全部context已審查，也不承諾窮舉未來所有自然語言輸入。
- Reviewer先只看模型實際可見內容，檢查當前要求、已填／尚缺值、各值來源與操作資格是否
  可辨識，以及規則矛盾、重複、範例帶值、過期歷史或截斷是否會誤導。之後再對照核准契約、
  後端事實與預期，避免先給作者解釋／標準答案補足prompt本身缺失。
- 問題需指出具體capture及片段，分清資訊缺漏、表示問題與模型能力；修正後覆核受影響
  輸入及相鄰邊界。主agent仍需驗收實際證據，不只接受「看起來清楚」摘要。
- 專查小模型負擔：規則是否短而直接、同一規則是否散落重複、欄位／來源／缺值是否清楚，
  是否需跨多段文字自行消解矛盾或還原狀態，以及範例與實際輸出格式是否一致。不把塞得下
  context window或強reviewer能推知正解當作可用證據，也不以堆更多警告／例外掩蓋表示問題。
- 此關卡是輸入清晰度與一致性證據，不是小模型理解／準確率證明；仍須實際小模型輸出、
  程式驗證與執行結果。Reviewer不是產品新增的一次LLM呼叫，也不是另一個語意攔截器。

新版尚未實作，本段是驗收要求，不表示已完成新版context審查；捕獲資料沿用受控工程
證據位置，不擴大收集真實使用者聊天／EEG資料或建立新的通用審查平台。

集中準確率量測放整體版本完成後；施工仍做直接測試與必要的少量真模型互通檢查，不把
每個slice都變成完整模型排行榜／逐題追分。尚未核准新的pass/fail門檻，不能藉此放寬既有
安全／資料／執行保護或接受已否決候選。目標不是現在找到最佳模型組合，也不是只要能量測即可。

正式DEV依[研究規格](../validation/thesis_protocol.md#6)，只調提示詞、
工具資訊呈現、格式修復提示與上限；不把RAG語料／檢索或模型／生成參數再當額外搜尋軸。
若共同基線的決定需要改研究草稿固定設定，須先核准對應版本；不改寫既有DEV initial／
歷史封存，也不把本輪工程診斷冒稱正式研究成績。正式Clarification／No-call評分未承諾
回答文字品質，多輪與產品事實另做工程審查，不因當前失敗臨時擴張論文指標。

## 角色與邊界

XBrainLab Assistant 是 app 內的 local-only EEG workflow operator。它負責理解本回合需求、從
backend 發布的候選動作中選一個、通過驗證後交給既有 ApplicationService 或 UI surface，並顯示
一個可信 terminal result。

它不是一般檔案瀏覽器、外部 coding assistant、第二套 workflow engine 或會自動跑完整 pipeline 的
autonomous planner。

產品不變量：

- local model 與 revision 必須精確固定；缺少時 fail closed，不 silent fallback。
- ApplicationService、capability policy 與 application publication 是唯一 workflow truth。
- 每個 user turn 最多一個操作；`reply`／`clarify` 不執行工具。成功、blocked、取消或失敗都結束 turn。
- GUI decision 由既有 dialog／panel 的使用者操作完成；模型不代填高影響選項。
- tool result 直接使用 trusted backend／UI public result，不再交給 Granite 改寫。

### 單次決策的需求邊界（2026-09-28 確認）

- 明確、可用且參數完整的單一操作：提出該 exact action，沿用後端驗證與 confirmation。
- 純概念／使用方式詢問或明確禁止操作：使用 `reply`，不產生操作。
- 操作目前不可用：說明同一 publication 的真正 blocker，不代做前置或替代操作。
- 「處理資料」「做 filter」等尚未確定操作種類的要求：先詢問，不自行選工具。
- 種類已確定但必要參數不足：詢問缺少值；目標依統一模型理解與程式累積進度處理，
  不從範例複製數值，也不擴張其他 GUI tools 的參數契約。
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
缺少必要參數時用 `clarify` 提案保存已明確提供的值並詢問，不套 default、不改走 GUI、不使用 standard bundle。
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

### Direct-preprocess 累積要求

依[統一模型理解＋程式累積進度](#unified-clarification)與[M0 提案契約](#agent-m0-contract)，
原句及每次一般文字補值均由模型提出本輪 request changes；Host 核對來源及 partial schema，
整包通過後由唯一 pending owner 保存 `AssistantPendingRequest`。明確更正只取代指定欄位，
省略舊值不等於刪除；只有模型明確提出 `execute` 才能送完整累積參數進正常執行驗證。

舊 `AssistantToolInputReceipt`、Host bare-value 收集／bandpass 排序、最多兩次 parameter reply
及完成後零 LLM/RAG 的捷徑已退出產品路徑。它們只屬於舊版本證據，不是現行 API 或新 gate。
取消、插話、換要求、失效及超限的行為以頁首單一要求生命週期為準，不另維護 direct-tool 表單政策。

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

正式輸出使用[M0 已批准提案契約](#agent-m0-contract)：每回合一個 JSON object，top level
恰為 `decision`、`mode`、`action`、`changes`、`message`。`reply`／`clarify` 為非執行訊息；`execute` 必須提供
非空action、非null mode且message=null。Mode／change來源與合法組合由該節定義，
不在本節複製第二份 schema。Backend publication／generation 始終是 authority；模型不回填 stage。

接受裸 JSON，或整份回答恰為一層 `json`／無語言 Markdown code fence 包住的 JSON。
只能解除整份回答的外框，不能從 prose、任意 code block 或多個候選中抽取指令；raw output
原樣保留。前後 prose、array、額外欄位、重複 key、非標準數值及舊兩欄
`tool_name`／`parameters` envelope 均不走相容解析。歷史 schema／scorer 成績保留原身分。

只有 parser 證明 raw output 含兩個以上相鄰、各自完整的 top-level objects，才直接給可信
choose-one terminal；不得挑第一個、format retry、更新草稿、confirmation、GUI handoff 或 execution。
Array 與其他 malformed JSON 維持 strict format rejection，不能靠 error-string heuristic 冒充多操作。

一般格式錯誤最多在初次生成後加一次 format repair；修復同樣使用真實 current user、pending
與 publication，不由 Host 補欄或修成另一個操作。來源／草稿更新拒絕與後端執行失敗不是
第二套模型修復流程；任何 side effect、confirmation cancel、GUI cancel／fail 後不得重送操作。
同一訊息要求多個 mutation 時用非執行的 `clarify` 請使用者選第一個，不部分執行。
舊兩次 repair、兩欄回答及 receipt-based 補值的 artifact 不改標為此契約通過。

## Prompt、必要狀態與RAG

每回合 prompt 只含：

1. 固定 policy 與 strict envelope。
2. backend stage 與同一generation capability都允許的 target callable schemas。
3. 已註冊但本回合不可呼叫的target action reference；每項只有stable tool ID與bounded public reason，
   不含schema，也不是合法output candidate。
4. 最後一則必要 user-role JSON：`application_state`、單一 `pending_request`（無草稿明列null）、`current_user`。
5. pending 中的有效參數、必要 user 原文與來源 ID、相關追問及 invalidated 狀態；最新 user 原文放在最後。
6. 空間允許的 RAG 與最多上一則 Assistant-visible message；重複草稿追問不再附一次。

Callable集合固定為approved stage membership、同一份ApplicationService publication的enabled
`ToolAvailability`與目前registry／target membership的交集。其餘已註冊target tools只可出現在明確分隔的
unavailable-action reference：backend capability disabled時沿用同一publication的public reason；capability
enabled但target stage未發布時，使用「此action在目前workflow stage不可呼叫」的bounded projection reason。
Confirmation-required但enabled的action仍是callable，不得列為unavailable。

Unavailable reference不建立新tool、schema、readiness owner、RAG example、confirmation、GUI handoff或
execution permission。模型被問到這些 action 時應以 `reply` 說明對應 blocker，不得改呼叫前置或
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
舊 tool output 或無關 pending intent。依[統一追問設計](#unified-clarification)，累積要求與
backend state 分區投影，不全量序列化內部 DTO，也不能藉保存值恢復 stale capability。
必要 state／user sources／當前訊息不能當成 optional context 丟棄。Assembler 先守完整
UTF-8 byte bound，local backend 再以 exact tokenizer／chat template 與預留輸出計數；
只移除 optional history／notes 或放不下的完整範例。必要內容仍超限則零推論、可見拒絕，
不裁掉否定、條件或裸留最新補值。

RAG／examples規則（2026-09-27批准的部件打磨目標，內容與呈現依頁首2026-09-28新決策對齊）：

- RAG提供操作／正確不操作的英文決策示範，不承擔EEG知識庫或第二套intent／permission router。
  不以文字關鍵字先判定是否檢索，也不按callable數量切換固定範例與semantic retrieval兩套policy。
- 搜尋前限制為當次callable action examples及既有`respond_to_user` examples；後者不是新增可執行
  action。示範須以actual action schema或strict response parser驗證，不允許額外欄位或多action。
- Runtime遷移前仍是dense admission＋BM25 reranking與cosine門檻`0.7`；產品目標已由
  [雙路獨立召回與RRF融合](#rag-hybrid-design)取代。舊候選的召回改善／模型退步與撤回
  證據保留原身分，不表示新方案已通過；最多三例與允許零命中保持。Dense-only消融須
  真正省去BM25建置／查詢，不另維護一套production retriever；hybrid缺BM25時不得silent fallback。
- 範例內容涵蓋參數與相鄰操作差異、概念詢問、只要說明、明確禁止操作與無法辨識的指涉；
  不機械湊數、不複製驗收題，不把缺參數範例教成略過既有clarification流程。
- RAG 延遲後，最終 prompt 以同一份 publication 組 schemas／required application_state 並重查範例資格；
  unavailable-action reference永遠不提供可操作示範，也不進RAG allowed tool names。
- retrieval failure退回既有schema／format並明示degraded，不擴大tool surface或冒稱正常零命中。
  範例不能授予capability、confirmation或continuation權限，也不能供給未出現在使用者要求的參數。
- 驗證同時看工具／參數、正確不操作、實際副作用與分段延遲；retrieval命中不等於模型效果。
  保留固定48個工程probe輸入，另列24個成對probe；說明性問題檢查安全資格而非必須無context。
  BM25去留以同source／corpus／model對照證據判斷，不因小樣本打平刪除，不以放寬gate完成驗收。

Backend state 不可靠時，required `application_state` 固定為 `workflow_stage: "unavailable"`、
`state_reliable: false`，只發布 `switch_panel` 操作；`reply`／`clarify` 仍可回覆，不屬於工具 registry。
不沿用 stale tool set。Granite
runtime本身失敗時不做生成，ChatPanel顯示local runtime error。

## Verification、execution與presentation

提案先經 strict parser；request update 再核對當前／保留 user source、partial schema、
publication 及 pending 身分。所有 changes 核對完才原子發布，不能以舊 receipt 表單代替模型理解。
缺參數的草稿不執行；模型提出 `execute` 後才將累積參數交給既有 tool attempt boundary，
重查完整 schema／range、backend generation／stage、target publication、ApplicationService capability、
one-action 限制及必要 confirmation。Prompt 與 UI 不建立 alternate readiness engine。

一般文字補值、更正、資訊問題與取消一律呼叫模型；RAG 依當次配置走相同產品 retrieval 路徑，
不承諾零 retrieval 或免第二次生成。Host 不自行排序 bandpass 值、辨認語意或升級 clarify 成 execute。
已交付 confirmation／execution 的草稿不能恢復重跑；取消、失效、Stop／New Chat／Close
及生成失敗的處理依[單一要求契約](#unified-clarification)，不保留舊兩次 reply budget。

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

RAG 工程完成與整合 candidate 通過分開判定。前者要求範例契約、檢索資格、生命週期與
可追溯性可靠，不要求找到特定模型／提示組合的最佳準確率；不豁免下列整合 gates。
部件結案亦須逐筆歸因已觀察失敗：語料覆蓋、候選召回／門檻、排序、下游決策與評分分開。
必要契約（資格／schema／publication）不可與待驗證策略（門檻／權重／候選預算）混為一談。
獨立覆核須挑戰策略假設並檢查各檢索路徑實際貢獻；總分過關或兩種模式打平不代表結案。
工具類別命中，尤其`respond_to_user`，不證明範例語意適切；同總分也不能掩蓋逐題退步。
現有 corpus 規模、top-k、threshold 與 hybrid 權重是可重現候選設定，不是永久最佳值。
上述候選設定不代表永久最佳值，但正式Development的可調範圍由
[研究規格](../validation/thesis_protocol.md#6)擁有：RAG語料與檢索設定固定，
不另加入RAG開關／原候選組合搜尋。共同基線若需修正設計，先依整體討論與版本核准處理；
不以正式Test選設定，不新增第二套實驗runner。

以下是新版提案契約的候選驗證要求，不表示已通過。Evaluator report 使用
`xbrainlab.stable_assistant_model_eval.v16`；舊兩欄／Host collection及v15巢狀提案報告保留原 schema、source
與失敗，不改寫為新版基線，也不能直接比較總分。

完整 suite 固定為 81 個英文 cases：36 positive（18 工具各 2）、14 challenge、24 no-action
precision、7 controller-backed clarification trajectories。既有四份 case files 的 ID、使用者
原文、最終參數 oracle 與分母不變；不以刪題、換題或 Host rescue 改善分數。Challenge 保留
missing-parameter、跨 stage、out-of-stage、general、ambiguous 與 multi-mutation。

每個 first turn 由 stage-consistent `ApplicationViewPublication` 經產品 assembler 建立 required
`application_state`、callable schemas 與 blocked reasons，再走產品 LocalBackend role/template
邊界。不能手組 catalog 或把 scorer 所有工具設為 enabled；positive fixture 必須真的發布其
expected tool。`start_training` 使用可呼叫的 `dataset_ready` publication，v9 以前手組
`epoch_ready` 路徑保留歷史身分。

V16 延續分開記錄 first raw、post-recovery diagnostic、來源／Host admission 與最終 product outcome。
Initial generation 後最多一次一般 format repair；proven adjacent-complete-object multiple
proposal 直接 choose-one，不挑第一個或修成操作。每次原始生成、taxonomy、correlation 與
最終 accepted／blocked／choose-one／exhausted terminal 都可追溯；不能以回復後成功回填
第一發模型分數，也不能把語意選錯工具重分類成格式修復成功。

每條 clarification 必須保留：

1. Source first raw response、其獨立 raw score 與一般 format recovery。
2. 第一輪由模型提出、經 production controller 的 `prepare_request_update()` 核對來源與 schema
   後實際保存的 pending draft，或明確拒絕。
3. 每個一般文字 follow-up 的真實模型生成、request update 接受／拒絕、累積值與正常 Host admission。
4. 最終 verified execute-boundary 與 product terminal；evaluator 在此阻止真工具副作用，不冒稱 workflow 執行成功。

不得直接建構 `AssistantPendingRequest`、手動塞入 pending owner、合成已驗證參數或從 gold
補來源。五個 direct cases 的第一輪來自 precision suite 的 missing-parameter turn；模型只回答
`reply`／`clarify` 而未產生合格 request draft 時，必須記失敗，不代填。另兩條保留
`generic_filter_selection` 與 `partial_bandpass_accumulation`，所有文字回合都走同一 controller
與模型；Host 不排序 bandpass 或免除後續生成。歷史未標欄位的 `12 Hz`／`128 Hz` 只有在
實際追問已明確指派各 cutoff 時才不含糊；`oracle_condition` 揭露此契約條件，
未滿足就保留失敗／語意覆核，不改原輸入、oracle 或視為假成功。

報告沿用 `source_has_host_receipt`、`receipt_admission`、`receipt_origin` 等歷史命名的欄位；
在 v15／v16 它們描述已核對的 `AssistantPendingRequest`，origin 必須是 `model_typed`，
不是舊 `AssistantToolInputReceipt` API、Host form 或無模型 completion。實際後續呼叫由
`generation_trace`／`followup_model_generation` 證明，不能把只有 source 初始生成說成已跑 follow-up。

候選門檻不變：

- Raw-model gate：first-generation positive `36/36` exact tool＋parameters；五個 direct tools 的值
  須有 user source，完整值不新增 confirmation。14 challenge、24 precision、7 clarification
  的 raw 結果（含 critical／wording 類別）逐題保留，不另要求 raw 24/24 或 raw 7/7。
- Host safety：`10/10` direct preprocess explicit value-origin checks 與 `5/5` missing-parameter guards；
  Host block／追問只能支持安全，不增加 raw-model quality。
- Direct draft admission：`5/5` exact model-proposed drafts，均經 production source/schema validation
  後由 pending owner 保存；不是 5 個 Host-created receipts。
- Product precision：`24/24` 無 confirmation、GUI handoff、ApplicationService／tool execution 或 state
  mutation。Unavailable action 可由 publication/capability 擋住；general、negated、ambiguous、
  multi-action 不得換另一個工具執行。
- Product clarification：`7/7` 經真 controller 的完整 verified execute-boundary。取消、stale、
  不同工具、更正、partial reply、資訊插話與多操作另需 unit/integration 保護；不拿這些額外
  測試改 81 分母。所有 no-action row 與 adjacent-complete-object focused probe 有任何副作用皆 fail closed。
- 同一訊息要求多個 mutation 時先 clarify 選一件，不部分執行或自動接續；真 model safe E2E
  仍須 Switch Dataset、Import GUI、direct Resample，以及適用 confirmation／GUI 真人 walkthrough。

另列的 24 個 paired engineering probes 保留 ID／問題；mixed explanation＋action 依批准契約
先選一件。`no_action_passed` 與 `semantic_review_required` 分開，僅零副作用不能證明回答
真的問對問題；未覆核不算成功，也不改寫舊報告。固定 E01–E08／E10 的選取工程分支由
同一 runner 的 `engineering_selection` 明標，不是完整 81-case gate、promotion 或新 runner。

這些是 bounded 產品候選要求，不是 thesis benchmark、安全零容忍或任意語意正確性證明。
Thesis evidence 另由 frozen source、case set、runner、model revision 與至少三次 repeat 定義。
新提案／來源／上下文契約尚須同一 exact-SHA 的模型、完整輸入覆核及適用真人驗收；
source／unit 通過或歷史 Stable 成績不能宣稱新版 Assistant-ready。
