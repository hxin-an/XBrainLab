# XBrainLab Assistant 研究與實驗規格

最後更新：`2026-10-03`

## 文件狀態與接續方式

使用者《碩論準備/研究方法草稿.md》擁有研究設計，本文件固化已確認的執行／證據契約。
[Now](../planning/now.md) 擁有施工順序、授權範圍與進度，
[Current](../current.md#assistant-research-baseline) 擁有實際證據及限制。
設計確認不代表已實作或實驗已完成。壓縮後依上述文件及 Git 接續，不重開舊清理。

### 目前執行方法：全部25候選VALID與條件式TEST

五模型各有五個已封存的DEV候選；DEV用於開發，不先依DEV淘汰候選。所有25候選
以同一可靠執行基礎各跑完整99題VALID一次，共2475筆（使用者最新指令取消三次重複）。
每候選計算單次三類等權macro及decision P50。依未四捨五入macro遞減、P50遞增選版；
仍完全相同時按Granite4、Granite3.3、Phi、Llama、Gemma順序，同模型取較早candidate。
所有候選完成且證據有效才選版；失敗／缺題不是較低分，不容許挑選完成的部分。

各候選模型／量化／生成／提示／RAG／oracle／raw scorer保持原封存內容；研究source明記
原DEV與本次執行版本，完整normal/retry模型輸入驗證等價後才推論。五輪為五個既有runner
配置及同一批次入口，不新增執行控制層。舊VALID後Host路徑修理可能影響計時，故本次
25候選全新執行，不把舊1485筆混入母體；舊三repeat封存不追改，新配置明確repeats=[0]。

若最終winner仍為原Phi R5且模型輸入／研究因素相同，沿用原TEST結果；若不同，先凍結
新winner，再跑Full及原三項單因素消融，各132題一次，共528筆，條件順序沿原repeat0。
配對family bootstrap仍抽10000次，但只使用該次原始答案，不宣稱已量到重複執行變異。
不依TEST高低再選版、不新增DEV第六輪、不改題目或評分；新結果如實保存並回存本機。
沿用每個五模型VALID配置14400秒active上限，整個五配置順序執行；約15分鐘監控摘要
一次，終態後驗收完整性，不密集逐題輪詢。GPU不可用則等待，不終止他人程序。

此擴大選版於2026-10-03初次TEST後獲使用者批准；原封存與實際時序保留。以下已執行
的五版VALID及首次TEST是歷史紀錄，不再限制本次25候選排程。這是方法補齊，不另設
新舊選版流程比較實驗；文件不把新增排程冒稱事前已固定或已完成。

2026-10-03全量輸入驗收發現Granite4 R1的VALID-N03-01-V0收到unavailable而非training，
原99題情境驗收不成立。使用者批准修理publication競態及actual-input檢查後，僅將該
候選完整99題再跑一次，作為工程替代量測，不是第六套DEV提示或三次重複設計。
替代規則在重跑前固定：新99題整批納入，原R1 99題保留但排除正式選版；不挑高分、
不逐題拼接、不採缺值界限例外。其他24候選保留已核對的原量測與source，選版記錄明示
兩個工程source與替代原因；新source須保持模型／提示／RAG／題庫／raw scorer／計時邊界，
完整模型輸入與原預檢等價。重跑後重新選版，不能預設先前觀察到的Granite4 R3仍勝出。
若不同於Phi R5，再依上列矩陣執行單次TEST；推論前與封存稽核皆需驗實際輸入可靠性及
預定workflow stage，不以fixture建立成功或Host擋下錯誤呼叫代替輸入有效性。

歷史d0的完整DEV起始基準已完成：五模型各264題，1,320次執行計入當時研究批次第一套。
2026-09-29使用者確認五模型各完成五輪，第1輪為基準、第2–5輪改善，不由agent依分數
自行提前停止。使用者已確認以本次驗收的產品基線加必要實驗工具準備，建立新研究批次
第1輪；五模型同一工作站137起跑，整批五輪共6,600個正式案例執行。精確source及環境
在準備完成後封存，不將目前仍未完成的工具稱為已封存基準。
舊d0的source／契約及Windows環境不同，只保留歷史，不拼接成新批次第一輪或改寫分數。
五輪候選帳目須可追查，不默默增加第六輪；工程smoke另外標示，不混入正式分母。
執行採逐輪討論：工具準備完成後先確認第1輪的版本、配置與執行條件，再跑完整DEV；
每輪結果與錯誤分類交回討論，批准下一輪調整後才封存／執行。不自主一次跑完五輪。
使用者決定先完成DEV、VALID及TEST／消融，再推進其他清理優化；執行仍依各階段固定
配置、範圍與額度，TEST不提前讀取。這次確認方向與設計，不自動啟動整批實驗。
2026-09-29使用者另批准合併工具PR後啟動正式第1輪：137、五模型各264題、candidate1、
seed0／repeat0、RAG on、最多一次格式修復、14400秒active執行預算。確認啟動與最初
有效案例正常後即交回，不持續監控整輪；不自行開始第2輪或因錯答調參／重跑。
上述第1輪的137固定20題工程smoke保持獨立，不再追加該輪額度。不得執行正式VALID、讀取／執行TEST
或重新下載模型；不擴張本輪矩陣、不把舊d0的結果作為本次第一輪。
2026-09-30使用者另授權第2輪：共同文字工具呈現與五模型短提示，固定candidate2，
先做新的固定20筆工程smoke，再啟動1,320筆正式DEV；開跑前多位獨立reviewer核對
程式與輸入／研究契約。20筆為五模型各四題（A01-01、A08-01、C01-01、N01-01之V0），
工程budget3600秒，不依其分數調提示或追加候選。正式預算與第1輪相同；初始量測正常
即交回，不持續監控至完成。不授權VALID／TEST或下一輪。
2026-10-02使用者另批准第3輪：Granite4／Llama沿用第2輪規則與文字目錄作起點，
Phi／Gemma／Granite3.3沿用第1輪規則與JSON目錄作起點，再加入各自的完整輸出形狀／
操作與回覆區分。這是研究提示起點，不回退共用runner或產品修復。精確model_id選固定
profile；完整source在推論前封存。每模型candidate3各264題，共1320筆，固定因素及正式
預算不變；本輪不追加20題smoke。離線驗證與獨立覆核後開跑，初始有效量測正常即交回。
不因有效錯答改提示／重跑，不授權第4輪、VALID／TEST或merge。
2026-10-02使用者閱讀第3輪總結後另批准第4輪：Granite4從R2提示移除泛用輸出示意，
明示單一操作／回覆互斥；Gemma從R1提示明示執行決策而非文字承諾，不帶泛用示意；
Phi／Llama／Granite3.3保留R3基礎，分別釐清工具／參數來源、當前請求與參考值、首次
JSON封裝及不操作邊界。逐模型短提示置於目錄／保留示意之後，不新增推理階段或Host政策。
只改研究提示呈現；固定因素、一次格式重試及預算不變，candidate4五模型各264題。
不追加smoke推論；完整輸入／精確tokenizer與獨立覆核、同head適用CI通過再封存開跑。
初始有效量測及進度正常即交回；不授權第5輪、VALID／TEST或merge。
2026-10-02使用者另批准第5輪：Granite4以R2提示改為必填操作欄位的當前值來源提示；
Phi／Llama以R3提示分別替換帶參數／泛用reply示意為完整缺值／開窗資訊對照；
Gemma以R4提示聚焦所請求工具自身條件；Granite3.3以R4格式要求搭配操作／回覆對照。
示例依公開工具契約撰寫，不取DEV原句、改寫或答案數值；只替換呈現，不回退共用工程修理。
固定candidate5、五模型各264題、既有生成／RAG／判分／一次格式重試不變；無額外smoke。
同head CI、完整輸入及精確tokenizer／獨立覆核後封存開跑，初始有效紀錄正常即交回。
這是第五套也是最後一套DEV候選；不自動選版、啟動VALID／TEST、追加候選或merge。
2026-10-02使用者在五輪完成後明確授權VALID：按既定DEV平衡正確率／P50選五套，
一次排入全部三次repeat，共1485筆；封存、直接驗證及獨立覆核後開跑，初始有效量測與
進度正常即交回，不監控整輪、不merge或讀TEST。五輪是事先固定的候選評估預算，
不是收斂／全域最優宣稱；Granite3.3末輪仍改善的限制保留，不因此追加第六輪。
DEV入選：Granite4=R2、Llama=R3、Gemma=R4 repair-03、Phi與Granite3.3=R5，無同分。
早期source有已知Qt退出／停止確認缺陷，VALID使用明記的新工程封存：保留各入選
prompt完整輸入等價、固定模型／RAG／生成／判分，共用已修理的R5執行基礎。不冒稱原DEV
SHA直接執行；入選DEV source/run與VALID執行source分別記錄，舊證據不重判、不覆寫。
開跑前固定順序：沿既有build_jobs模型順序Granite4、Granite3.3、Phi、Llama、Gemma，
每模型依repeat0、1、2，各repeat按case_id排序且獨立新condition/session；不複製輸出。
DEV完全同分同P50取較早candidate（本次未用）；VALID按三次平均平衡正確率，再平均P50，
仍完全相同時按上述既有模型順序選定。不使用VALID結果再改提示或選版規則。
舊 B0/B1/B2 搜尋安排、最多 30 條件 VALID、TEST 加跑同模型 B0、P95 10 秒門檻
已被新版設計取代，不再派工；歷史決策留 Git，舊 B0 封存／分數／入口不追改。

### 2026-10-02 TEST執行凍結

使用者批准TEST施工、完整執行、資料稽核及本機回存。VALID成功run為
`20261002-124746-8263faf9`（7c4ac807，1485筆）；依事前平均macro再平均P50選定
Phi-4 Mini R5（macro 0.7654320988），不因TEST結果換模型或提示。
正式矩陣為以下四條件各132題、repeat 0/1/2，共1584次案例執行；修復生成另計。

| 條件 | RAG | 狀態式工具目錄篩選 | 最多格式重試 |
| --- | --- | --- | ---: |
| full | on | on | 1 |
| rag-off | off | on | 1 |
| tool-filter-off | on | off | 1 |
| retry-off | on | on | 0 |

目錄消融僅擴大提供模型的工具schema；state、blocked原因、RAG候選資格／結果、
固定提示示意及Host admission／confirmation維持full。可看見不代表可執行；Host攔截
不將錯誤模型提案變成正確。另兩項各只停用自己的機制。Full完整輸入須於既有DEV/VALID
情境與入選版本逐字相同；各消融完整輸入／runtime政策差異在讀TEST前用無推論證據確認。
沿用精確Phi模型／生成設定、137及共用環境，不增加模型、DEV候選、B0或smoke推論。

排程先repeat後條件：repeat0為上述表格順序；repeat1左移一格，repeat2左移兩格。
每condition/repeat独立載入與既定warmup，案例依case_id遞增且逐題reset。
這是減少時間順序偏差的固定輪換，不宣稱四條件完全平衡。預算仍受14400秒active上限
約束，不因有效錯答加跑。完整題庫僅在此研究配置固定及無推論消融檢查通過後解封；
其來源hash、fixture/input/token預檢與最後工程source SHA在執行前封存。

主分數仍為各repeat三類macro後平均；P50/P95各repeat先算再平均，不混池。
呈現三類分數及always-respond參照macro 66.67%（Action 0、其餘100%），不將兩類
合法回答率解讀成回答品質。分開記錄原始模型、Host admission及實際執行結果。
補充full對各off的配對差、修復觸發／救回／時間成本，不以變好才宣稱完成。

2026-10-03使用者確認：研究正確率只評模型原始工具／參數答案，首答及既有格式重試
後答案分開保存。Host拒絕、成功執行或執行失敗均不改模型分數。現行research runner
與其engineering-smoke以完整raw/capture/input identity、原scorer、decision計時及
fixture/reset/cleanup為有效量測條件；product outcome及UI計時另留診斷，觀測不完整
不得偽称執行成功，也不得單獨排除原始答案或中斷整批。原standalone Pilot gate不變。

首次TEST在fa9d4d54因英文數字four/eighteen與Host原句literal檢查不相容停止：模型
bandpass 4/18原始答案已判正確，並非模型錯答。使用者另批准移除bandpass/notch/resample
的Host原句數字membership檢查，仍保留schema/range/capability/publication/confirmation；
method來源及RAG共用helper不變。新TEST封存揭露此post-VALID工程修理與新source，
不能稱完整產品版本與VALID相同。模型／prompt／RAG／生成／oracle／raw scorer不變，
執行前另驗Full輸入逐字一致。既有DEV/VALID原始分數與source保留，不回填或重跑。
失敗TEST批次保留，新source重新完整排程，不拼接兩版結果；新run不以分數高低重跑。

不確定性：依Action／Clarification／No-call分層，分別以36／12／18個family為抽樣
單位有放回重抽10000次（analysis seed0）；每family的2改寫×3repeat及四條件成套
保留。由每family六次平均正確率算各層均值，再三層等權計macro；同一次抽樣索引用於
full/off配對差，取2.5及97.5百分位數。此分析不再生成模型輸出，不把repeat當獨立題庫。
區間是題庫涵蓋任務／family抽樣假設下的條件式不確定性，不代表所有真實使用者，
不把三個個別95%區間稱為同時95%或事後用顯著性重選系統。模板相關性列限制。

題庫／RAG重合稽核依使用者`碩論準備/資料集驗證/README.md`，於正式TEST啟動後
進行，不因此再調提示、題目、oracle或分母。標準答案建立及scorer證據如實交代；
既有使用者審題與工程驗證不冒稱第二位獨立人工標註。不新增強制真人研究。
工程fixture修正需新source及重驗；正式source改變不得混批。未知缺證據／cleanup失敗
仍fail closed。正常錯答照實保存；新oracle／研究決策問題交使用者，不自行修答案。

NAS TEST沿用stage內一個完整封存包、12條件在同一run；全部成功VALID/TEST結果
複製至`D:\workspace_v2\projects\lab\碩論準備\實驗\result/<STAGE>/<run-id>`，
保留index、reports、raw證據、inputs、launches、audits（如有）、prepared manifest。
逐檔hash及離線HTML links核對後才稱回存完成。不帶權重／環境／暫存EEG，NAS原件不改。
使用者要求節制監控：啟動核對後依預估時程低頻讀摘要／終態；不逐題輪詢或反覆拉全log。
本輪終點為完整TEST、稽核與本機副本交付，不以啟動即宣稱完成，不自動merge。

## 1. 研究定位與限制

第一主線是可靠、好用且介面清楚的 EEG 軟體；本規格只處理第二主線：

1. 五個本地模型所對應的完整 Assistant 系統，在決策正確性與等待時間上有何差異？
2. RAG、狀態式工具篩選與格式重試，分別如何影響選定系統的正確性與等待時間？

比較的是模型及對應配置共同形成的系統，不是同精度纯模型能力或全域最優。
Assistant accuracy 不是 EEG 分類正確率、完整操作成功率、臨床有效性或易用性。
單次小樣本 Pilot 不代表正式 TEST、穩定排名或可靠尾端延遲。

## 2. 模型與矩陣

五模型是 Granite 4.0 Micro、Granite 3.3 2B Instruct、Phi-4 Mini Instruct、
Llama 3.2 3B Instruct、Gemma 3 4B IT（文字模式）。精確 revision、chat template、
runtime 與量化由 `scripts/dev/assistant_pilot_models.py` 的固定配置及 manifest 保存。
Gemma 使用 NF4 4-bit 權重／BF16 compute，不 double quantization、不 CPU offload；
其餘四模型 BF16。不得 silent fallback，不擴張產品 Settings 模型清單。

共同生成設定：greedy、`do_sample=False`、每次最多 512 新 token、context budget 8,192。
實際 structured generation 不啟用 temperature/top_p 抽樣。決策期限 120 秒，含格式重試；
起始設定最多一次格式修復。起始 seed=0，不代表跨環境或重跑逐位元一致。
2026-09-23 使用者確認：VALID 每套入選系統獨立執行三次，三次皆固定 seed=0，
維持 greedy 與相同系統／題庫設定；分別保存結果，觀察執行波動，不刻意引入抽樣差異。
同 seed 不保證逐位元一致，三次 repeats 也不是三份獨立題庫。執行排程仍須在 VALID 前固定。
新封存協定將三次 repeats 排在同一 run 內，各有獨立 case／condition 身分及分母；
不是複製同一次輸出，也不把 repeat 當失敗補跑。可執行排程不等於已執行正式 VALID。

歷史d0保留其原語料／embedding hash及檢索規則，不因新版研究回寫。
新批次採已驗收Development產品基線：固定all-MiniLM-L6-v2 snapshot、獨立dense／BM25
召回、等權RRF（rank constant 60）、最多三例；dense門檻0.7不作BM25的否決門檻。
當前語料161筆英文單輪示範（117操作、44回答／不操作），index schema 6；兩欄工具回覆，
不帶對話歷史、不保存多輪補值草稿。完整規則由[Agent架構](../architecture/agent.md)擁有。
新候選仍須封存source、語料與完整檢索設定；同embedding名稱不代表同配置。
已接受的工程證據與已知失敗由[Current](../current.md#assistant-research-baseline)擁有，
不是本次正式DEV成績或未知題目全部正確的證明。
DEV 不調 RAG 語料與檢索設定；degraded retrieval 不算 RAG on。題庫／oracle 不進 RAG 或 few-shot。

| 階段 | 已確認矩陣 | 次數與出口 |
| --- | --- | --- |
| DEV | 五模型，每模型五套設定（基準占第一套）；每套完整264題一次 | 完整矩陣6,600次；各選一套 |
| VALID | 全部25個凍結候選 × 99 題 × 一次 | 2,475 次；選完整系統 |
| TEST（若新winner） | 完整系統及三項消融 × 132 題 × 一次 | 528 次；評估，不再選版 |

基準輪的1,320次包含於五輪矩陣，不額外加跑基準或RAG off。五輪是候選設定，不是同
設定重複五次；各模型可不同調整，但可調範圍、題庫與評估次數一致。每輪先記錄理由
再凍結設定，退步仍計入並保留，不隱藏額外候選或用重跑湊輪數。五輪完成後選最佳，
不是必選最後一輪。正式執行批次／額度仍需另行固定並授權，不因設計確認自動開始搜尋。

## 3. 題庫與輸入隔離

495 Cases／165 原始 families，同 family 改寫不能跨 split。

| Split | Cases | Action | Clarification | No-call |
| --- | ---: | ---: | ---: | ---: |
| DEV | 264 | 144 | 48 | 72 |
| VALID | 99 | 54 | 18 | 27 |
| TEST | 132 | 72 | 24 | 36 |

已完成 d0 使用的非 TEST workbook 為使用者已人工確認版本，SHA-256：
`2161af9932950e2a0726daeae3d744935d8d1bc6f408d739b2240d2752a29c23`。
歷史 d0 原檔保持不變。後續正式非 TEST 題庫為
`D:\workspace_v2\projects\lab\碩論準備\實驗\題型_已審不含TEST.xlsx`，
SHA-256：`817b82b893b515fd44cb399056255659599cea40a0cb88b42527f45530353ec9`。
這份來源已移除 `ground_truth.review_status` 及其下拉選單，其他題目／答案與工作表不變。
Runner 原樣複製題庫，不做刪欄或特殊指紋轉換；新實驗重新 prepare 並使用新 output，
不沿用 d0 的舊 manifest。Repo 沒有題庫產生器，後續編修以這份來源為準。
新版完整附件包含 TEST，
本輪不可為核對 DEV 而讀該附件；若題目改動，取得新非 TEST 匯出並另立版本。
非 TEST intake 可核對 VALID 結構，但不能執行 VALID 模型評估或用其結果調參。

每題保存 ID/family/split、英文輸入、oracle、缺少資訊與 fixture 身分。
只有當題使用者輸入、實際可見產品狀態／工具及固定 RAG 進 prompt；答案与其他题目隔離。
初始狀態由真 Commands 建立核對，題間重置工作區、對話及 pending interactions。
同條件重用模型，不沿用前題 EEG 狀態。Synthetic EEG 不冒稱 source-diverse 資料驗收。

新 DEV 的研究專用投影只控制非任務資訊：模型 state card 不含 backend generation 數字；
training progress 的匿名 subject reference 按出現順序改成穩定別名。真實 stage、進度數值、
工具與任務資訊保留。Host 仍用原 publication generation 作 freshness/admission，
不固定真 counter；停止確認依[核准的run-bound例外](../target/agent.md#backend-owned-stage-contract)
在執行邊界核對原trainer/run仍在running，不因同場進度更新失效，其餘stale checks不變。
原 publication 與實際模型輸入分別保留。
這是新 DEV 配置，不回套舊 B0，也不宣稱兩者輸入相同。

## 4. 評分、計時與量測完整性

### 決策正確性

目前產品與研究consumer共用嚴格`tool_name / parameters`兩欄parser；操作須提供完整參數。
不操作使用`respond_to_user`及非空`parameters.message`，不評文字品質。
不使用mode、changes或pending要求，不假造多輪歷史。產品以完整單一英文要求為範圍；
研究決策分數不證明Host admission、使用者確認或實際工具執行成功。
目前scorer為`xbrainlab.assistant_decision_scores.v6`，response contract為
`assistant_tool_response.v1`。歷史封存保留原scorer／契約與已存分數；reader辨識版本，
不以目前parser重新評分舊capture，也不把舊五欄提案重標為新格式通過。

- Action：最後一次輸出符合 parser/schema，工具與參數符合 oracle。
- Clarification／No-call：符合允許的非操作結構且未提出工具操作；不評文字內容，
  不宣稱澄清品質或多輪完成率。
- 無格式重試時只判首次；最終格式錯誤、無回應及完整紀錄的模型逾時判錯。
  Host 擋住錯誤操作不會讓模型變正確。初次／修復後可另列，主分數用最後一次。
- 每類正確數除以該類有效量測數，三類等權平均為平衡決策正確率。
  少類別、缺題或未知終態不能宣稱完整矩陣完成。

決策、admission、使用者確認及實際 Command／GUI outcome 分層記錄。
完整且同turn/request的確認拒絕／取消事件是有效量測的`blocked`／`cancelled`，不是
執行成功，也不是「缺少執行觀察」。缺事件、重複或矛盾執行事件、身分不符仍判量測無效。
Scorer 正反例保護參數、格式、錯誤工具、正常不操作與有效失敗，並獨立覆核可達的錯判。
正式實驗若發現 scorer 缺陷，一致重評受影響資料，不只修抽到的個案。

### 等待時間

由系統收到訊息至格式檢查完成；工具提案須再完成是否可執行的檢查，失敗計至回報。
含 RAG、prompt 組裝、生成、解析、驗證與格式重試；不含載入、暖機、使用者確認、
實際工具執行、事後 scorer 或報告。各段邊界須有真 trace，不能拿整個 turn 時間替代。

新 DEV 的整體 P50/P95 包含有完整紀錄的成功與失敗：格式錯誤、Host 阻擋、決策逾時。
逾時值代表至失敗回報的實測等待，不假装是成功生成耗時。排序後採線性插值；列樣本數及排除理由，
可另外列成功／失敗組。VALID/TEST 每次先算指標，再取三次指標平均，不把 repeats 混池重算 P95。
舊 Pilot 的 completed-only latency 保留原語意，不改寫為新規則結果。

### 失敗與恢復

有效低分、格式錯誤、逾時照實保留，不因分數重跑。紀錄缺失等無法判定案例才可用
相同 source／題庫／配置補跑；原 attempts 保留，替代關係可追溯，每個 logical case 計一次。
修改程式或配置後另開 run，不拼接前後版本。本輪顯式補跑每個無效案例最多一次；
仍有問題先診斷，不無限重試。未解 child／cleanup、来源差異須阻止 resume。

## 5. 單一入口與結果資料夾

### 每輪一鍵執行與兩份結果比較

沿用《碩論準備/實驗/產出格式/實驗產出格式說明.md》的四表：模型總表、題型正確率、
題組正確率、逐題結果；保留實際完整prompt／raw output、預期／實際差異、CSV／JSON。
不重新設計報表，不以新摘要替代原始證據。外部文件的舊輪次／平台文字須在正式開跑前同步。

每輪獨立封存為`development/round-01`至`round-05`；一輪可綁定五模型各自不同的
設定與source。包內沿用`run.sh`、`manifest.json`、`sources/<head>/`、`environment/`、
`inputs/`及`runs/<run-id>/`，完整程式與scorer保留在包內，不依賴開發worktree／最新main。
權重／embedding可共用固定snapshot，但須可取得且逐檔指紋核對，不原地替換。
環境與資源須先準備好；一鍵不代表空白機器零安裝，也不承諾跨環境逐位元相同。

`./run.sh`跑完該輪封存配置所選模型及完整DEV，自動產生既定報告；再次執行建新run，
不覆寫、不自動進下一個改善輪。`--resume`只續原run，`--report-only`及`--audit`
不重新推論。這些操作能力不授權因有效錯答重跑或挑分數，正式每輪的計分run須明確記錄。

新v2封存包提供兩run比較入口`./compare.sh RESULT_A RESULT_B`；路徑相對目前shell目錄，
不是包內run ID。預設寫入包內新的`comparisons/<id>/`，也可用`--output NEW_DIRECTORY`。
同source的137固定20次工程驗證與限制見[Current](../current.md#dev-round-tooling)；
這不是完整DEV或正式模型排名，逐輪批准與進度由Now擁有。
它不是現有單run audit：按模型、case與repeat對齊，輸出工具／不操作決策一致率、
工具及參數一致率、都對／都錯／錯變對／對變錯、P50／P95及逐題耗時差、輸入輸出明細。
JSON排版／key順序不構成參數差異；不評非操作回覆的文字品質、不另用LLM評相似度。
一致不表示正確；兩個相同錯誤須同時保留「一致」與「都錯」。首次／修復後不得混比。
先揭露source、配置、模型、題庫、oracle／scorer與環境差異，再分辨同設定重跑和跨輪
比較；不得把不同輪次差異稱為重現失敗，或默認不同scorer的正誤直接可比。
缺題、無效／損壞與重複ID須明列，不靜默剔除、不把兩份缺失算一致；分母及不可比較
原因必須可查。比較唯讀，不修改原分數或報告、不呼叫模型。

比較讀取與原manifest／journal指紋相符的既有`reports/*/report.json`，再核對request、result
及capture；沒有可核對報告時明列不可比較，不自行用新版程式重建或重判。
保存JSON完整明細與Markdown摘要，不另建四表報告系統。不同scorer／oracle或無法核實
身份時不計正誤改善；決策一致率也不替代模型準確率。原始報告及分數不修改。
v1歷史封存仍可讀取，但不往舊包加新入口或更改manifest；如需比較，由新包讀取兩份結果。

### 可封存 DEV／VALID 協定

#### 同工作站／NAS：共用唯讀資源與分層入口（2026-09-30）

使用者選定本次使用方式：完整程式與評分器、題庫、設定隨實驗版本封存；接收者複製
到自己的可寫資料夾。Python環境與模型／embedding可繼續使用NAS上同一份固定資源，
只需接收者讀取／進入／執行權限，不要求每個副本重建venv或複製模型。
這不是任意機器的獨立可攜包；原資源不可刪除／原地升級，未通過權限檢查不能宣稱
另一帳號可用。工具不自動chmod／開放私人目錄，也不處理跨帳號GPU排程。

搬移單位是完整`experiment/`，不是各個round；固定頂層為README、run.sh、compare.sh、
`stages/`、`snapshot/`、`results/`，另有執行時隱藏`.runtime/`。透過
`assistant_experiment_batch.create_experiment`封存一次完整樹，取代前版逐層batch-source。
`snapshot/sources/<commit>/`每個不同commit只存一份完整獨立Git快照，跨模型／round／stage
共用；`snapshot/inputs/`按內容封存題庫及資源指紋，TEST未授權時不讀取或加入。
`snapshot/environment/shared.json`固定Python位置、平台及套件版本，不是已安裝二進位的
逐檔hash。模型內容仍由既有runner於推論前核對。各round的`config.json`對應模型、
candidate及source；README記調整理由／目標模型／共同影響，不能覆蓋機器設定。

在自己的副本執行`./run.sh --check-environment`核對封存、環境版本、資源目錄存取及
執行限制工具，不推論、不新建run；`./run.sh`自動清理衝突Python環境變數、設定offline／
offscreen及本地cache，委派既有runner。保留core=0及18000秒外層wall guard，active預算
由原config擁有。所有cache/log/temp位於副本`.runtime/cache/`，拒絕cache樹既有符號連結；
run及comparison輸出不允許導向副本外。檢查模式不證明CUDA／模型準確率或逐位元重現。

root、`stages/dev`、各round、`stages/val`、`stages/test`各有`run.sh`，全部引用中央snapshot；
`snapshot/manifest.json`固定scope、順序及檔案指紋。不掃目錄、不新增另一套case journal、
評分或resume政策。只允許實體子目錄、禁止重複選擇；全樹封存核對及所選scope的完整
ready／環境預檢在第一次推論前完成。歷史source／round配置／run證據不原地升級。
新增DEV輪次使用`assistant_experiment_batch.append_round`：先驗既有封存，再暫存新
source／輸入／round，驗證組合後原子發佈更新manifest。根manifest及coordinator因新增
輪次而有新身分；既有round檔案與結果保持原內容。部署時不得有並行寫入者或執行中批次。
任一stage有blocked_reason就整個所選範圍拒絕執行，不跳過後宣稱完整研究完成。
只有DEV第1輪固定時，可建立清楚標示只含round-01的DEV批次；root若包含尚未ready的
VALID／TEST必須保持blocked。將來完整五輪／VALID／TEST全固定後才可建立整研究重跑包。

批次按固定順序委派runner，失敗／取消即停止後續；每次產生新的`results/runs/<id>/`。
`results/runs/<id>-scope.json`只列選擇及已指定的輸出位置、完成／失敗／未嘗試，不另計分。
成功原始參考結果逐檔核對複製到`results/reference/<original-id>/`，原始manifest／source
身分及歷史絕對路徑不改寫。比較器从包內raw及中央snapshot讀取；reference只供比較，
不承諾搬移後resume部分舊run。`compare.sh`不推論／重評分，另存`results/comparisons/`。
不允許從多次執行挑最高分。GPU仍需使用者協調，
同一副本不應同時啟動多批，入口不是常駐服務或安全沙箱。

階段封存：DEV每輪保存五模型各自候選、完整程式／prompt／RAG／scorer及差異理由，
相同source僅存一次；VALID階段固定DEV入選的五套系統及來源round/run對應，固定三次
repeat後不回頭調參；TEST在選定完整系統與三項消融及工程驗證固定後才取得封存TEST。
現有config仍只接受DEV／VALID；TEST和消融的實際執行尚未實作，不因分層入口而解禁。
同版本重現另建run，不占另一改善輪，也不能用重跑湊五套候選；正式計分run須記錄。
工程修正版新包須區分封裝coordinator與各模型source，不回寫舊run的版本／指紋。

DEV第2輪沿用共同程式，由精確model_id選定短提示；未知模型在載入前拒絕。
研究用`DevContextAssembler`將真實工具schema呈現為文字，保留required／選填、型別、
enum及額外欄位限制；各模型提示與共同程式一併按source封存，不依題號／答案選提示。
產品預設提示、Host／工具契約、scorer、RAG與一次格式修復不變。candidate_index只記錄
候選輪次，不決定執行時提示。五模型各264筆；本輪固定20筆工程驗證不作挑提示的搜尋集，
答錯與工程執行失敗分開記錄。無推論preflight涵蓋全部DEV fixture及五模型完整輸入，
另以保存的RAG輸入與精確tokenizer核對預算；這些不代表模型準確率改善。

量測工具修改的無推論驗證也須涵蓋錯誤工具選擇，不只fixture與預期答案的happy path：
用固定回應走真Host／產品視窗，核對導航、開窗取消、確認、通知、渲染失敗／逾時及
下一題清理。產品通知測試須呼叫實際建立者，不能複製舊文案造視窗代替；未知視窗、
缺證據與清理失敗仍停止，已完整觀察的模型錯答照實計錯、不轉成量測排除。
無推論工程重播不計正式準確率、不增加候選輪次；修理後新source另封存，保留舊失敗run。

第3輪按上述逐模型起點保留JSON或文字目錄，重用同一產品schema／publication；
完整輸出示意只從當前可用的公開工具契約產生，不讀case ID或oracle，不提供當題授權／值。
五套profile連同共同程式封存；候選來源決定呈現，不由candidate_index或觀測分數切換。
第2輪工程20題為歷史證據，第3輪不沿用為同source驗證，也不追加新smoke推論。

#### 相容工作站的可搬移副本

使用者批准NAS帳號間整包複製，供環境相容的實驗室Linux工作站使用；137為已實測
機器，不是hostname／IP限制。2026-09-29使用者接受既有證據，不再追加跨機、跨帳號
或新環境推論驗證；此決定不把未測項改標通過，也不改變正式研究固定工作站的要求。
`create --wheel-cache EXISTING_CACHE`
建立v3可搬移包：程式、非TEST題庫、設定、固定模型／embedding與目前環境精確版本的
相容wheels均放包內。只複製資源清單列出的模型檔案，不複製cache token／私人settings；
wheel缺失或不一致即拒絕，不下載新版或退回另一模型。原始v1/v2封存及證據不原地改寫。

接收者在自己的可寫NAS目錄執行`./run.sh`；system Python／Git仍是先決條件，既有
固定Python版本／平台核對保持不變，不新增自動適配或fallback。
首次使用包內離線wheels及hash-pinned requirements建立副本內環境，之後重用並檢查
安裝版本。Ubuntu缺ensurepip時由固定pip wheel啟動，無sudo、無全域pip安裝。不同
副本路徑／UID另建環境，不沿用複製來的venv絕對路徑。`./run.sh --check-environment`
只建立／核對環境，不呼叫模型、不消耗研究案例。正式run仍須逐輪批准。

可寫資料限包內`.runtime/`、`runs/`及`comparisons/`；不允許這些輸出經symlink重導外部。
v3比較的明確`--output`也須位於包內`comparisons/`。模型完整hash由既有runner在推論
前核對，不每題或在bootstrap重複掃描整套權重。移動後新run重新記錄真實路徑與環境；
舊run不可改manifest冒充可resume，仍保留原始證據。應散布未執行的乾淨包，避免把
先前`.runtime/`、診斷或runs當新包必要輸入；程式不自行刪除這些內容。

這不建立跨使用者GPU排程：既有lock為每使用者，仍需協調執行機器的GPU使用。模型與研究
資料的接收者權利須確認；不自動開放hxin家目錄或變更群組權限。同帳號換路徑、另一
帳號、真CUDA／模型執行是三種不同證據，不互相替代；可用範圍與缺口由Current記錄。

#### 一般封存與執行

`scripts/dev/assistant_experiment_package.py create --bank BANK --config CONFIG --output PACKAGE`
把編輯完成的 config 與題庫封存為新包。只接受 clean exact source，不能覆寫既有包。
每個不同 source 各存獨立 shallow Git checkout，不依賴開發 worktree 或外部 Git objects。
`config.json` 在 create 前是唯一可編輯設定；包內 config／resources／環境規格由 manifest
固定，修改設定需建立新包，不手改 derived selection／manifest。

- config 的 `split` 選 DEV／VALID；`models` 選模型、各自 `candidate_index`、source head/root
  與 model cache；`embedding_cache`、`resource_inventory`、`budget_seconds` 明確指定。
- seed=0、RAG on、greedy、初始一次格式修復由本協定固定；DEV repeat 0，VALID repeats 0–2。
  `purpose=engineering-smoke` 才能選固定 DEV `case_ids`，不計為新正式候選。
  目前封存config的重試上限固定為1，足以表達第1輪；研究允許後續調整上限，但其具體值
  與必要配置支援須在該輪討論及實作驗證後另版封存，不宣稱目前入口已支援任意重試數。
- `candidate_index` 限1–5，但無中央 ledger 證明所有離線包未重用編號；研究紀錄仍須綁定
  每模型候選的source／設定。歷史d0屬舊批次；新批次第1輪才占本批次第一套。
  工程smoke不計為正式候選，也不能藉此額外調參。
- 多 source 候選必須支援此協定，且 dependency lock、固定模型／生成 factories、model catalog、
  RAG config／語料與 coordinator 一致；不把新 evaluator 疊到舊 source 上冒稱原版。
- 相對路徑以 config 所在目錄解析。封存包保留相對 cache 引用或明確外部 binding；
  搬工作站需帶同版共用資源及重建環境，不自動猜路徑／下載。prepare/resume 在 child 前
  核對每個固定 snapshot 的完整檔案 SHA-256，不在每題重讀所有權重。

在包內執行（Linux；先將 `environment/python` 指向按封存 lock 建立的環境）：

```bash
./run.sh                         # 新 run，不覆寫結果
./run.sh --resume RUN_ID         # 原來源／配置／runtime 續跑
./run.sh --report-only RUN_ID    # 不載模型，只重建報告
./run.sh --audit RUN_ID          # 原候選 scorer／input／capture 離線重播
./compare.sh /path/run-a /path/run-b   # 不推論、不重評，另存比較結果
```

`XBL_PYTHON` 可明確覆蓋本機 Python binding。入口不另擁有 journal／cleanup／resume policy。
`--replace-invalid` 只和 resume 使用，需先診斷，保留原 attempt 且最多替代一次；
有效錯答、格式錯誤及有效逾時不能因分數重跑。不同 runtime 建新 run，不混接量測。
搬移包後支援新 run／離線報告；既有 partial run 的 resume 仍需原本的絕對來源與資源路徑，
不宣稱可搬移未完成 run 後無縫續跑。其他包的 run 即使放進本包目錄，也不得被誤接續。
同主機／使用者共用 GPU lock；這不代表預約了其他使用者的 GPU，開跑前仍須查共享負載。

包保存 `sources/<head>/`、`environment/`、`inputs/`、`manifest.json`、`run.sh`、`compare.sh`。
每次 `runs/<id>/` 沿用 `inputs/`、`prepared-manifest.json`、`raw/`、`reports/`、`launches/`；
`selection.json` 由 runner prepare 產生在 run 的 inputs，不建立第二個 selection 權威。
HTML 仍為四表；VALID 各 repeat 分開呈現，JSON `repeat_summary` 保存每次指標算完後的
等權平均，不混池重算 P50／P95，缺任一完整 repeat 不給完整均值。

離線 audit 另存 `runs/<id>/audits/<id>.json`，核對封存輸入、原始 capture、原 scorer 判分及
input audit，前後確認既有 inputs/raw/reports/launches 未變；不改原分數或重新推論。
各候選使用其自身 scorer，不用目前開發版重評舊結果。這是可追查性證據，不是人工 oracle
正確性或跨平台結果逐位元一致的證明。歷史 d0 仍用其原 frozen source／核對入口。

本輪 engineering smoke 為五模型各跑 `DEV-A01-01-V0`、`DEV-A08-01-V0`、
`DEV-C01-01-V0`、`DEV-N01-01-V0`，共20筆；執行累積60分鐘，不含資源複製。
選題依開窗、填參數、缺資訊不操作、知識不操作的介面類型，不依歷史分數。
真 RAG、終態、capture、cleanup 是工程驗收，20題全對不是通過條件，也不能據此調參。
工程驗證不拿Windows d0與Linux候選直接比較；新研究批次固定同一137工作站，
正式第1輪仍須在版本與配置封存後另行確認開跑。

### 歷史 DEV 起始基準

沿用 Windows runner/condition/case/report，只允許核准模型／全部五模型的 DEV initial、
RAG on、repeat 0；未核准候選、VALID/TEST 或消融不得因入口通用化而可執行。
每個條件載入／生成暖機一次，RAG on 另暖機；使用既有本機模型／embedding cache、離線推論。
Qt offscreen 實際產品觀測不等同 Windows 可見 GUI 手測。

Windows PowerShell 入口（以下保留 d0 當時指令；新實驗改用上節正式題庫與新的 manifest／output）：

```powershell
.\dev.cmd prepare --bank D:\XBrainLabRuns\b0-entry-78908640\inputs\reviewed-non-test-bank.xlsx --config D:\XBrainLabRuns\b0-entry-78908640\inputs\pilot-config.json --manifest-output D:\XBrainLabRuns\d0-manifest-v2.json
.\dev.cmd run --bank D:\XBrainLabRuns\b0-entry-78908640\inputs\reviewed-non-test-bank.xlsx --config D:\XBrainLabRuns\b0-entry-78908640\inputs\pilot-config.json --expected-manifest D:\XBrainLabRuns\d0-manifest-v2.json --output D:\XBrainLabRuns\d0
.\dev.cmd resume --output D:\XBrainLabRuns\d0
.\dev.cmd report --output D:\XBrainLabRuns\d0
```

`--models phi4,gemma3` 可限制核准模型，預設全部；完整基準仍需五模型。
`prepare` 只核對與保存 manifest，不推論；`run/resume` 自動保存報告；`report` 只重建報告。
新 output／manifest 必須不存在。resume 沿用保存的模型／輸入；僅經診斷的無效量測才用
顯式 `--replace-invalid`，不對有效錯答使用。不要在背景已執行時再手動啟動同一批。
預先 prepare 的背景 run 必須帶 `--expected-manifest`：重新核對 source／環境／輸入後，
整份 manifest 必須與固定檔相等，否則在建立 output／推論前拒絕；不能只事後比對。

結果保存 inputs、raw manifest/journal、實際 prompt/raw output、逐題 attempts、source／
環境／模型／語料身分、reports 與 launches。HTML 是入口，CSV/JSON 用於分析；分母、
分數、links 與 raw 可核對。Report-only 不推論／改 raw，歷次報告保留。
固定 clean/explained commit 後才跑；同步產品線只在輪次間，不在執行中 pull。
本輪总機器預算沿用四小時，跨 resume 累計，單題保留安全上限；不並行搶同一 GPU。

### 背景執行與單次喚醒

背景程序執行既有 runner、保存 log／終態，完成或失敗後只以
`codex queue --thread <exact UUID> --message <trusted handoff>` 排入一次接續訊息。
不另開 `exec resume` 取得 writer、不使用 `--last`，也不切換會話／改模型／繞過鎖。
原 d0 的 `exec resume` 因互動會話仍持有 writer 而失敗；只測已卸載會話的 smoke
漏掉此情境。該失敗證據保留，不能以更清楚的錯誤提示冒稱修好喚醒。

在本機 Codex 0.155.1，保持原 TUI 開啟、首回合完成後不再按鍵，真 `queue` 已自動
觸發同一會話的下一次 task_started／task_complete。Queue 仍需已開啟且能消費訊息的
宿主；不宣稱關閉 TUI、重啟或其他客戶端也保證自動執行。
CLI 回傳成功只記為 `wake_queued`，原始 receipt 在 `wake.stdout.log`；不代表接續完成。
真正接續與驗收以同一會話的事件及結果為準，不只看 queue exit code。

固定 run、source、manifest、會話 ID 與 cwd；captured turn 完成、無 active turn 且 armed
才送出。最後 idle 檢查與使用者開啟新 turn 間仍可能競態，由既有 queue 接收，不能宣稱
沒有競態。完成／異常均保存結果；失敗、逾時或是否已送出不明時不自動重試，
保留手動檢查方式，避免指令其實已排入卻再次發送。不得退回 `exec resume`。
喚醒後核對可信計畫／版本／結果，只接續 Now 批准工作；raw model output 不是施工指令，
不擴大權限、不解封 TEST、不自動調優。不建立產品控制平面；休眠／關機不保證作業持續。

### 歷史 B0 日常入口

`baseline.cmd` 保持 frozen `926d90ea` 的 30 DEV 題 × 五模型 × RAG on/off，
不是目前分支的完整 DEV。PowerShell 在 evaluation worktree 執行：

```powershell
.\baseline.cmd --list
.\baseline.cmd --check
.\baseline.cmd --conditions granite4-rag-off
.\baseline.cmd --output D:\XBrainLabRuns\my-b0
.\baseline.cmd --output D:\XBrainLabRuns\my-b0 --resume
.\baseline.cmd --output D:\XBrainLabRuns\my-b0 --report-only
```

此入口沿用 sibling `XBrainLab\.venv`、E 槽封存與 `D:\XBrainLabCache\b0-926d90ea`，
不下載／升級。Source/output 沿用最多 60 字元短路徑，缺資源停止。
B0 還原限制與報告位置由 Current 擁有，舊綠燈不代表新 source 通過。

## 6. 階段出口與後續授權

DEV 只調提示詞、工具資訊呈現、格式修復提示與上限；模型／生成／RAG 固定。
每模型完成五套完整評估（基準＋四套改善），取最高平衡正確率，同分取較短P50；
不要求完美、不因某模型基準較高就少給改善輪次，也不以同設定重跑湊足五套。
VALID 五套固定配置各三次，按三次平均平衡正確率、再平均 P50 選版，不回頭調參。
完全同分同速的處理及 repeat 排程須在選版前固定，不等看到 VALID 結果才決定。

TEST 四條件為完整系統、移除 RAG、移除狀態式工具篩選、移除格式重試。
工具篩選消融只改模型可見清單，保留狀態資訊、固定 RAG 與 backend admission／確認／資料保護；
移除重試只生成一次，其餘條件沿用選定系統配置，不為消融重調參。
配置凍結、使用者確認並提供封存 TEST 後才執行；不因消融較好事後改選完整系統。

歷史d0 DEV initial 的scope-complete：1,320有效案例、完整分母、原始輸入輸出／判分／時間可核對、
報告可重建、直接驗證及獨立覆核通過。背景等待可結束当前回合以省 token，但只是
已交接 checkpoint，不代表完成。調優／VALID／TEST 仍須下一階段授權。
