# XBrainLab Now

最後更新：`2026-08-19`

## 目前焦點

在 `fix/assistant-direct-parameter-provenance-v1` 保留現行一段式 Granite 與18-action surface，只為五個
direct preprocess 加入必要參數的 latest-user-text provenance guard。明確值仍直接執行；缺值或模型
補值時零執行，以一般藍色英文 Assistant bubble追問。完成條件是同一exact source完成自動驗證、
真Granite host-aware evidence與正常ChatPanel真人手測入口；中間checkpoint不交付手測。

目前 phase：`Active；Qt process-isolation blocker已閉合，建立新的exact-source candidate evidence`

## Exact-model evidence

固定 `ibm-granite/granite-3.3-2b-instruct` revision
`707f574c62054322f6b5b04b6d075f0a8f05e0f0`、greedy generation、同一 GPU process與同一50-case
development suite；所有實驗只產生／評分 envelope，未執行產品工具：

- A 現行一段式：36/50；positive 36/36，challenge 0/14，warm P95約1.5秒。
- B gate-first：最佳31/50；positive 31/36，challenge 0/14，warm P95約3.2秒。
- C gate-first＋safe-decision RAG：最佳32/50；positive 30/36，challenge 2/14，warm P95約3.0秒。
- D proposal-first／critic-second 初始格式衝突輪：proposal 36/36，但 critic 只2/50可解析；此輪只用來
  找 evaluator contract defect，不作架構比較。
- D 修正通用 critic／response strict envelope後：proposal仍36/36；critic後positive 17/36；14個
  challenge只擋8個，6個仍被approve；安全response 0/14；總分17/50；warm P95約3.9秒。

D 最終報告位於 ignored local artifact
`build/dev-artifacts/stable-assistant-proposal-critic-development-v2.json`；positive cases SHA256
`a4311b63165c2f4fb1c68d88c1ed8c81ecb9ae3beb1760bf1c2e52cda57f31bc`，challenge SHA256
`df300230c11b0ca014b1320e20ec80f2529766d2cbb2d50cd38adbe78ba2405b`。Model load、runner identity、
逐case proposal／critic／branch／timing皆在該report。沒有執行heldout，因development promotion已失敗。

## Stop decision

- B/C/D 均未過預註冊門檻，不得接入正常產品 turn，不得稱為較安全或較準確，也不得交使用者手測。
- 不降低門檻、不以個別challenge句子調prompt、不把expected答案或錯誤raw calls放入RAG。
- 未採用的 gate-first、decision-RAG與proposal-critic evaluator程式／tests／corpus已從worktree移除；只保留
  本頁證據與 ignored report，避免失敗架構累積為產品複雜度。
- 現行一段式仍是工具選擇最佳baseline，但14/14 challenge都提出不應執行的action，不能因此宣稱
  Assistant-ready。Backend schema、stage capability與confirmation仍提供deterministic防線，但無法辨識
  ambiguous／multi-action意圖，不能把它們當作模型語意正確的替代品。

## 已核准的 observable outcome

- `apply_bandpass_filter`的low/high、`apply_notch_filter`的freq、`resample_data`的rate、
  `normalize_data`與`set_reference`的method必須能在最新使用者輸入的相應操作表達中被精確驗證；只在
  文字其他位置出現相同數字不算來源。
- 數字比對正規化整數／小數、Unicode dash與中英文range／target表達；method只接受使用者明寫的
  canonical value或安全的空白／連字號／大小寫變形，不推導同義值或default。
- Schema有效但任一必要值無法驗證時，`ToolAttemptCoordinator`回傳typed response boundary，
  ApplicationService與ToolExecutor皆不被呼叫。Controller用現有一般message presentation顯示簡短英文
  追問並結束turn；不是黃色Attention、不寫Tool Output、不做第二次model generation。
- 18-action membership、strict三欄model envelope、ApplicationService、capability與confirmation不變。
  明確完整參數仍無確認直接執行一次。使用者已明確接受ambiguous／multi-action若含完整可驗證參數時，
  模型可能只執行其中一項；one-command cap後不自動繼續第二項。
- UI可見決策已於2026-08-19確認：缺值顯示一般藍色bubble，訊息統一英文。沒有`XBrainLab/ui/`修改。

## Scope、complexity與施工順序

預計只修改既有verifier、ToolAttemptCoordinator與Controller，production低於3 files／淨增300 LOC；
owners前後皆為既有Controller、Coordinator與ApplicationService。新增的是服務五個真實callers的純
parameter-origin function與一個typed coordinator outcome，不是owner、state machine、receipt、module或
compatibility path。刪除優先：不恢復B/C/D、RAG、confidence gate或Host intent router。

1. 先以red tests鎖定明確／缺少／不一致／無關數字／method變形、零execution與藍色response terminal。
2. 實作純parameter-origin驗證，再由Coordinator於schema後、capability／execute前使用；Controller只呈現
   typed response，不重做policy。
3. Focused verifier／coordinator／controller已374 tests通過；Ruff／format與相關Basedpyright為
   clean。尚待ApplicationService／ChatPanel adjacent suites、MkDocs與canonical handoff gates。
4. 固定Granite revision已重跑：36 positive為36/36；五個missing-parameter raw outputs皆自行補值，
   production host guard已5/5拒絕並產生英文追問。Evaluator strict gate已改為同一composed
   contract；其他9個raw challenge仍保留為known limitations。
5. 固定candidate SHA後，正常ChatPanel真人驗證一般回答、navigation、Import取消／重試、明確與缺值
   preprocess、multi-action one-command cap、Training與Compute Saliency既有邊界，才交使用者手測。
6. Exact-source handoff在完整本機環境發現Basedpyright會載入Poetry環境中的第三方typed packages，
   integration base與本branch因而同為81個既有diagnostics／24 files；受限sandbox缺少這些search paths而
   顯示0 errors，不可作handoff證據。本slice三個production files在完整環境仍為0 errors。以
   唯讀regression wrapper固定這81項既有債，保留全部現行rules並讓任何新增diagnostic繼續fail；
   不在本Assistant slice修理24個不相關UI、MNE、Torch與visualization檔案。Allowlist必須由exact
   integration base產生，記錄locked Basedpyright version，candidate不得新增項目；resolved項目允許
   單調減少。Basedpyright原生baseline已因一般check會自動改寫檔案、且不同環境可產生競態而拒絕，
   不得採用。若唯讀wrapper會吞掉新錯誤或在locked環境不可重現，停止施工而不放寬type-check policy。
7. Exact `49bc1d7c` 已完成1064項Assistant adjacent tests、Ruff／format、唯讀Basedpyright regression、
   MkDocs、36／36 Granite positive＋10／10 explicit-origin＋5／5 missing-origin host guard、四個public
   source-diverse cases，且PR #40所有applicable non-skipped checks completed/success。Canonical handoff的
   complete regression另在本機offscreen Qt重現pyqtgraph `AxisItem`已刪除後仍收到延遲paint event的
   native abort；abort固定在dialogs中的pyqtgraph widget關閉後、下一個preprocess test處理延遲paint
   event時發生，屬共享Qt process lifecycle blocker，不是本Assistant產品路徑失敗。`run_tests.py ui`與
   Linux CI本來已用同一份`UI_UNIT_SHARDS`，只有default `unit/all`仍把整個UI樹放進單一process；修正後
   default unit gate重用既有10個native-safe UI shards，沒有新runner、沒有skip、沒有減少assertion或
   修改產品UI。新的契約test先以1個UI process對預期10個失敗，再轉綠；全部2673項UI tests已在10個
   fresh processes中2673／2673通過，且每個shard仍由required-pytest attestation驗證零failed／error／
   skipped。下一步只重跑complete regression與同一新exact source handoff；任一shard或aggregate evidence
   不完整即停止，不以分片掩蓋失敗。

## Merge boundary

Assistant product行為先以本短branch進`integration/assistant-stable-v2`。只有同一source的applicable CI
全數completed/success、真人手測通過並由使用者明確同意，才可合入integration；之後完整integration
candidate仍需另一次同源批准才可走PR合入`main`。Source改變即使手測失效。
