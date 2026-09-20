# Assistant Benchmark：第一輪判分校準

最後更新：`2026-09-16`

依據[使用者的 Notion 計畫](https://app.notion.com/p/3ce4ab11187a81c0a30ade5cf08b1b52)，
本輪先固定三種決策與三層判分，驗證 scorer 能區分明定正反例。
**目前只有離線、agent-authored、Development 校準，不是正式 Benchmark 或真人一致性結果。**
不改產品工具契約、模型、prompt、RAG、Host、GUI 或既有 acceptance gate。

## 可執行範圍與舊證據

入口是 `scripts/dev/assistant_benchmark_calibration.py`，預設案例為同目錄的
`assistant_benchmark_calibration_cases.json`。使用產品 `CommandParser.parse_product`、
`ToolSchemaValidator` 與 `get_all_tools()`；不執行工具、不建立 ApplicationService，也不載入模型。
它是讀取觀察資料的純判分器，不是新的執行、admission 或 capability owner。

Checked-in corpus 有四個案例、八份合成觀察：No-call、Clarification、backend Action、
GUI-opening Action 各有一正一反例。另有 focused tests 變更觀察欄位以檢查誤判。
案例的 `source` 必須是 `agent_authored_calibration`，不能標成人寫的 seed。
這些案例不是完整工具覆蓋、真實 EEG 操作或真模型軌跡。

既有 `run_stable_assistant_model_eval.py` v12 與 frozen 81 cases 保持原樣、原 gate 用途。
`main@73acb83a` 盤點時，81 題中的 23 個第一輪輸入與 RAG gold 的輸入在空白／大小寫正規化後
相同（positive 19、challenge 2、precision 2）；這不表示每次都檢索到答案，但它們不能被重新
包裝成未見過的 sealed test。v12 抑制真實工具執行，因此舊分數也不能改名為 Product Outcome。

## 三種決策與三層分數

每個案例只指定一種預期決策。三層保留各自的結果，不用 Host 修復後的成功回填 raw 分數。

| 決策 | Raw／Agent 決策判分 | Outcome 額外必要證據 |
| --- | --- | --- |
| `no_call` | 正確 stage 的 `respond_to_user`，無 pending action。 | 完成回覆、無 action proposal／執行／GUI／確認、無多餘 pending，狀態不變。 |
| `clarification` | `respond_to_user` 帶正確 pending tool 與完整 missing-input 集合。 | 觀察到相符的 pending receipt，沒有執行，狀態不變。 |
| `action` | 正確 stage、精確工具與符合產品 schema 的參數。 | Host 驗證成功、必要確認、依案例完成 GUI 或 backend 操作，結果及狀態符合預期。 |

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
這是 v1 合成校準保留的歷史假設，不改寫舊 scorer 或成績。正式研究已於 2026-09-19
確認依工具完成契約區分開窗與直接操作，缺資訊採正確不執行指標；以
[研究規格](thesis_protocol.md)第 4 節為準，不以此處的 typed clarification／完整 Outcome
契約覆蓋正式研究方法。它不改變目前產品工具、GUI 或 confirmation 契約。

## v1 校準資料契約

頂層固定為 `schema`、`cases`、`observations`、`expected_scores`；schema 值為
`xbrainlab.assistant_benchmark_calibration.v1`。拒絕重複 JSON keys、NaN／Infinity、
重複 ID、空庫、缺少案例觀察、缺少或多出的標註。未知觀察欄位也不能通過 Outcome。

Case 欄位：

- `id`、`family_id`、`split`、`source`、`input`、`stage`：身分、來源與場景。
  runner 只接受 `development`，不發現／載入其他 split；`family_id` 在此是標記，
  **尚無跨 split 分組或防洩漏實作**。
- `decision`、`tool`、`parameters`、`missing_inputs`：事先寫好的 oracle，不從實際答案生成。
- `completion`：`response`、`clarification`、`backend` 或 `gui`；
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
No-call 的 effects 為空，Clarification 只有對應 pending effect，兩者 execution 都是 null。

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
四題八觀察共 24 個分層標註比較，不是 24 題、81 題新模型評測或產品成功率。

## 後續正式 Benchmark 的必要條件（本輪未實作）

1. **案例與凍結**：真人 seeds 明列作者／來源；先按 seed family 分 Development／Validation／
   Sealed，再改寫，避免同源變體跨 split。正式配額與來源由[研究規格](thesis_protocol.md)
   第 3 節擁有，舊 Notion 配額不再作為施工依據。不能為滿配額拆散 family；已接觸的題不可當未知測試。
2. **真實收集器**：走正常 ChatPanel → Host → Command 路徑，取得 admission、確認、實際
   呼叫參數／結果、最終狀態、GUI、errors/crash 與完整 effects；預先固定觀察終點與 timeout。
   不能用 v12 的 synthetic publication、工具名或 mock success 充當操作結果。
3. **人工校準與保密**：獨立人工與 evaluator 判同一份軌跡，保留歧異再修 scorer；另一次手動
   重跑屬執行變異，不能混進同軌跡一致率。Sealed 由獨立保管者管理，開封、重跑及失敗保留
   規則先固定；本輪未建立 Sealed，亦未讀取其內容。
4. **正式分數**：凍結 exact source、工具／scorer／case 版本、模型 revision／quantization、
   prompt／RAG、環境／硬體、seed／重跑數／重試預算。每類與總分保留分母、失敗、排除及變異；
   正式主分數依研究規格的平衡決策正確率；Product Outcome 另列，不能由本輪合成觀察推估。

既有 [Thesis Protocol](thesis_protocol.md) 的廣泛研究目標與歷史門檻不由這個小型校準器取代。
正式實驗前需明定新 protocol 與舊門檻的適用關係；本文件不授權模型實驗或產品契約修改。
