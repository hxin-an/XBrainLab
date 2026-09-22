# XBrainLab Assistant 研究與實驗規格

最後更新：`2026-09-22`

## 文件狀態與接續方式

使用者《碩論準備/研究方法草稿.md》擁有研究設計，本文件固化已確認的執行／證據契約。
[Now](../planning/now.md) 擁有施工順序、授權範圍與進度，
[Current](../current.md#assistant-research-baseline) 擁有實際證據及限制。
設計確認不代表已實作或實驗已完成。壓縮後依上述文件及 Git 接續，不重開舊清理。

本輪只完成完整 DEV 起始基準：整合已接受 main 的 Import 修正後固定新 source，
五模型各 264 題，1,320 次執行計入每模型最多五套設定中的第一套。
不自動調優、不執行 VALID、不讀取／執行 TEST、不修改公開工具／UI、不下載或升級環境。
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
正式三次 repeats 的 seed／排程須在 VALID 前固定，不能把 repeats 當三份獨立題庫。

RAG 固定 all-MiniLM-L6-v2 snapshot、最多三範例、相似度門檻 0.7；語料／embedding 保存 hash。
DEV 不調 RAG 語料與檢索設定；degraded retrieval 不算 RAG on。題庫／oracle 不進 RAG 或 few-shot。

| 階段 | 已確認矩陣 | 次數與出口 |
| --- | --- | --- |
| DEV | 五模型，每模型最多五套設定；每套完整 264 題一次 | 最多 6,600 次；各選一套 |
| VALID | 五套入選系統 × 99 題 × 三次 | 1,485 次；選完整系統 |
| TEST | 完整系統及三項消融 × 132 題 × 三次 | 1,584 次；評估，不再選版 |

第一輪 1,320 次已包含於 DEV 額度，不額外加跑基準或 RAG off。
目前只批准首套；五套上限不是必須用滿，也不是自動搜尋其餘四套的授權。

## 3. 題庫與輸入隔離

495 Cases／165 原始 families，同 family 改寫不能跨 split。

| Split | Cases | Action | Clarification | No-call |
| --- | ---: | ---: | ---: | ---: |
| DEV | 264 | 144 | 48 | 72 |
| VALID | 99 | 54 | 18 | 27 |
| TEST | 132 | 72 | 24 | 36 |

已完成 d0 使用的非 TEST workbook 為使用者已人工確認版本，SHA-256：
`2161af9932950e2a0726daeae3d744935d8d1bc6f408d739b2240d2752a29c23`。
歷史 d0 原檔保持不變。後續新 DEV 準備／匯出自動移除 `ground_truth.review_status`，
不修改來源題庫；manifest／selection 指紋以移除後的 XLSX 為準，保存、預檢與續跑沿用
同一轉換。需重新 prepare 並使用新 output，不沿用 d0 的舊 manifest；既有 d0 report
仍核對原始指紋。其餘欄位／工作表保持；若該表含不支援的複雜格式或引用公式，明確拒絕，
不靜默破壞 Excel。新版完整附件包含 TEST，
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

### 新 DEV 起始基準

沿用 Windows runner/condition/case/report，只允許核准模型／全部五模型的 DEV initial、
RAG on、repeat 0；未核准候選、VALID/TEST 或消融不得因入口通用化而可執行。
每個條件載入／生成暖機一次，RAG on 另暖機；使用既有本機模型／embedding cache、離線推論。
Qt offscreen 實際產品觀測不等同 Windows 可見 GUI 手測。

Windows PowerShell 入口（本輪已批准的非 TEST 輸入）：

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
每模型最多五套完整評估，取最高平衡正確率，同分取較短 P50，不要求完美。
VALID 五套固定配置各三次，按三次平均平衡正確率、再平均 P50 選版，不回頭調參。
完全同分同速的處理及 repeat 排程須在選版前固定，不等看到 VALID 結果才決定。

TEST 四條件為完整系統、移除 RAG、移除狀態式工具篩選、移除格式重試。
工具篩選消融只改模型可見清單，保留狀態資訊、固定 RAG 與 backend admission／確認／資料保護；
移除重試只生成一次，其餘條件沿用選定系統配置，不為消融重調參。
配置凍結、使用者確認並提供封存 TEST 後才執行；不因消融較好事後改選完整系統。

本輪 scope-complete：1,320 有效案例、完整分母、原始輸入輸出／判分／時間可核對、
報告可重建、直接驗證及獨立覆核通過。背景等待可結束当前回合以省 token，但只是
已交接 checkpoint，不代表完成。調優／VALID／TEST 仍須下一階段授權。
