# Assistant 判分工程校準

最後更新：`2026-10-06`

以單輪操作／不操作與三層判分，驗證工程 scorer 能區分明定正反例。
**只有離線、agent-authored 合成校準，不是論文評分器、正式 Benchmark 或真人一致性結果。**
不改產品工具契約、模型、prompt、RAG、Host、GUI 或既有 acceptance gate。

## 可執行範圍與舊證據

入口是 `scripts/dev/assistant_benchmark_calibration.py`，預設案例為同目錄的
`assistant_benchmark_calibration_cases.json`。使用產品 `CommandParser.parse_product`、
`ToolSchemaValidator` 與 `get_all_tools()`；不執行工具、不建立 ApplicationService，也不載入模型。
它是讀取觀察資料的純判分器，不是新的執行、admission 或 capability owner。

Checked-in v5 corpus 有三個案例、六份合成觀察：No-call、backend Action、
GUI-opening Action 各有一正一反例。另有 focused tests 變更觀察欄位以檢查誤判。
退役跨輪草稿的一題／兩份觀察不計入新分母；其餘 input／oracle 不變。
舊完整 v4 fixture 留在 `assistant_benchmark_calibration_cases_v4.json` 作歷史資料，
現行 runner 拒絕舊 schema，不用新 parser 重評舊輸出。
案例的 `source` 必須是 `agent_authored_calibration`，不能標成人寫的 seed。
這些案例不是完整工具覆蓋、真實 EEG 操作或真模型軌跡。

`run_stable_assistant_model_eval.py` 現為 v17，固定 20 題基本 gate 與 74 題單輪廣度分列；
舊 81 題／七條跨輪軌跡是歷史身分，驗收由 [validation contract](README.md) 擁有。
產品回覆為兩欄 envelope，stage 保留為 backend 情境。本校準不評缺值回答語意或來源
驗證，報告明示 `clarification_semantics`／`source_validation` 為 `not_evaluated`；
不能由合法 response 宣稱模型知道缺少什麼，不能回算歷史成績。
`main@73acb83a` 盤點時，81 題中的 23 個第一輪輸入與 RAG gold 的輸入在空白／大小寫正規化後
相同（positive 19、challenge 2、precision 2）；這不表示每次都檢索到答案，但它們不能被重新
包裝成未見過的 sealed test。v12 抑制真實工具執行，因此舊分數也不能改名為 Product Outcome。

## 兩種決策與三層分數

每個案例只指定一種預期決策。三層保留各自的結果，不用 Host 修復後的成功回填 raw 分數。

| 決策 | Raw／Agent 決策判分 | Outcome 額外必要證據 |
| --- | --- | --- |
| `no_call` | 合法兩欄 `respond_to_user`，無 pending action。 | 完成回覆、無 action proposal／執行／GUI／確認、無多餘 pending，狀態不變。 |
| `action` | 精確工具與符合產品 schema 的參數；不評模型stage回填。 | Host 驗證成功、必要確認、依案例完成 GUI 或 backend 操作，結果及狀態符合預期。 |

- `raw`：第一次模型原始輸出的結構決策；不修復格式、不以關鍵字猜工具或缺少參數。
- `agent`：Host 處理後最後被選定的決策 envelope；與 raw 使用同一決策 oracle。
  Host 是否真正准許執行另由 Outcome 的 `host_verified` 檢查，不憑 envelope 推定。
- `outcome`：Agent 決策正確，且完整觀察滿足所有預期；不是只看 `completed` 字樣。
  錯誤 case identity 不得在任何一層得分。取消、pending、error、缺欄位與不符狀態不算成功。

參數不做字串轉數字、別名或容錯；schema 允許的 `4` 與 `4.0` 可等價，`true` 不等於 `1`。
產品 parser 要求非空回覆，但回覆內容是否正確、充分、易懂仍需人工評分；結構正確不能證明
自然語言回答品質。產品安全拒絕可能是正確行為，但若題目預期完成操作，仍不是該題的完成成功。

### GUI 完成的校準假設

目前採「依題意」區分：題目只要求開啟匯入視窗，需正確視窗可見、enabled 且未改資料；
題目要求完成匯入，則一定要讀取 backend 結果及資料狀態，不能只用視窗開啟代替。
這是合成觀察的工程校準假設，不改變產品工具、GUI 或 confirmation 契約，
也不能用此處的完整 Outcome 評分覆蓋外部研究所凍結的模型決策評分。

## v5 校準資料契約

頂層固定為 `schema`、`cases`、`observations`、`expected_scores`；schema 值為
`xbrainlab.assistant_benchmark_calibration.v5`。拒絕重複 JSON keys、NaN／Infinity、
重複 ID、空庫、缺少案例觀察、缺少或多出的標註。未知觀察欄位也不能通過 Outcome。

Case 欄位：

- `id`、`family_id`、`split`、`source`、`input`、`stage`：身分、來源與場景。
  runner 只接受 `development`，不發現／載入其他 split；`family_id` 在此是標記，
  **尚無跨 split 分組或防洩漏實作**。
- `decision`、`tool`、`parameters`、`missing_inputs`：事先寫好的 oracle，不從實際答案生成。
- `completion`：`response`、`backend` 或 `gui`；
  `requires_confirmation`：案例當下需要的確認。
- `before`、`after`：同一組非空欄位的狀態投影；`ui`：預期 UI 投影。
  目前範例使用合成 generation、rate、count，並非已接上產品 snapshot。
- `effects`：有順序的 `{kind, tool}` 清單，必須精確匹配，不能多呼叫或重複執行。

Observation 欄位：`id`、`case_id`、`raw_response`、`agent_response`、`complete`、
`host_verified`、`terminal`、`before`、`after`、`ui`、`effects`、`pending`、`errors`、
`execution`。決策保留產品原始 JSON envelope 字串；其他欄位是同一次操作的觀察投影。

Backend success 必須同時有正確 `execution: {tool, parameters, success: true}`、
proposal → 必要的 confirmation_approved → execution、有預期的最終狀態、無 errors／pending。
GUI-opening success 必須有 proposal → 必要確認 → gui、`gui_ready`、正確 surface、
`visible: true`、`enabled: true`，且沒有 backend execution；它不取得 backend 成功分數。
No-call 的 effects 為空，execution 為 null；不再有建立參數草稿的 effect。

工具宣告必要確認時，oracle 不能省略。額外的動態 backend／資源政策仍由產品擁有，不能從
工具的靜態 flag 推斷全部已核准；未來真實收集器必須取得當次產品政策與確認紀錄。
目前任意人可手寫觀察 JSON，`complete: true` 或 `host_verified: true` 本身沒有證明力；
**因此此 runner 永遠只輸出合成校準身分，不會將輸入升格為真實產品證據。**

`expected_scores` 以 observation ID 對應三層布林人工可讀標註，與評分函式輸入分離。
runner 比較每層 matched／false_positive／false_negative；目前標註同樣由 agent 撰寫，
不稱 blinded human agreement，也不以對自己撰寫的標註全對來宣稱 scorer 普遍可靠。

## 重現與可宣稱結果

在既有環境、repo root 執行；不需要下載或新環境：

```bash
python scripts/dev/assistant_benchmark_calibration.py
python -m pytest tests/unit/scripts/test_assistant_benchmark_calibration.py --no-cov -q
```

CLI 可用 `--cases PATH` 明確指定 Development manifest，只輸出 stdout JSON。
Exit `0` 表示所有校準標註一致，`1` 表示有誤判，`2` 表示資料或讀取錯誤。
報告保留 cases 與 scorer SHA-256、逐觀察三層結果；hash 不涵蓋產品依賴或環境，
重現時仍須記錄 Git source、dirty state、命令與環境版本。報告固定
`model_executed: false`、`product_benchmark_score: null`、`human_agreement: null`。
三題六觀察共 18 個分層標註比較，不是 18 題模型評測或產品成功率。

## 宣稱界線

此校準器只保護工程判分與觀察資料契約，不處理研究題庫、選版、重跑或正式統計。
論文受測source、方法與原始結果由[研究封存](README.md#research-archive-boundary)保存，
不隨產品校準器改動重評。產品交付仍依[驗證契約](README.md)，不以合成校準代替真模型、
真Command或Windows操作證據。
