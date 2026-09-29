# XBrainLab Assistant 研究與實驗規格

最後更新：`2026-09-29`

## 文件狀態與接續方式

使用者《碩論準備/研究方法草稿.md》擁有研究設計，本文件固化已確認的執行／證據契約。
[Now](../planning/now.md) 擁有施工順序、授權範圍與進度，
[Current](../current.md#assistant-research-baseline) 擁有實際證據及限制。
設計確認不代表已實作或實驗已完成。壓縮後依上述文件及 Git 接續，不重開舊清理。

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
本次執行授權停在封存／比較工具與137固定20題 smoke（累計最多60分鐘），不自動調優、
不執行正式 VALID、不讀取／執行 TEST、不重新下載模型。後續產品契約施工另依Now的
明確授權；不自動擴張正式研究矩陣或把新source當作舊輪次的延續。
舊 B0/B1/B2 搜尋安排、最多 30 條件 VALID、TEST 加跑同模型 B0、P95 10 秒門檻
已被新版設計取代，不再派工；歷史決策留 Git，舊 B0 封存／分數／入口不追改。

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
| VALID | 五套入選系統 × 99 題 × 三次 | 1,485 次；選完整系統 |
| TEST | 完整系統及三項消融 × 132 題 × 三次 | 1,584 次；評估，不再選版 |

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
不固定真 counter、不略過 stale checks；原 publication 與實際模型輸入分別保留。
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

#### 同137工作站的可搬移副本

使用者另批准同機NAS帳號間的整包複製目標。`create --wheel-cache EXISTING_CACHE`
建立v3可搬移包：程式、非TEST題庫、設定、固定模型／embedding與目前環境精確版本的
相容wheels均放包內。只複製資源清單列出的模型檔案，不複製cache token／私人settings；
wheel缺失或不一致即拒絕，不下載新版或退回另一模型。原始v1/v2封存及證據不原地改寫。

接收者在自己的可寫NAS目錄執行`./run.sh`；system Python／Git仍是同機先決條件。
首次使用包內離線wheels及hash-pinned requirements建立副本內環境，之後重用並檢查
安裝版本。Ubuntu缺ensurepip時由固定pip wheel啟動，無sudo、無全域pip安裝。不同
副本路徑／UID另建環境，不沿用複製來的venv絕對路徑。`./run.sh --check-environment`
只建立／核對環境，不呼叫模型、不消耗研究案例。正式run仍須逐輪批准。

可寫資料限包內`.runtime/`、`runs/`及`comparisons/`；不允許這些輸出經symlink重導外部。
v3比較的明確`--output`也須位於包內`comparisons/`。模型完整hash由既有runner在推論
前核對，不每題或在bootstrap重複掃描整套權重。移動後新run重新記錄真實路徑與環境；
舊run不可改manifest冒充可resume，仍保留原始證據。應散布未執行的乾淨包，避免把
先前`.runtime/`、診斷或runs當新包必要輸入；程式不自行刪除這些內容。

這不建立跨使用者GPU排程：既有lock為每使用者，仍需協調137 GPU使用。模型與研究
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
