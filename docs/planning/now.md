# XBrainLab Now

最後更新：`2026-08-19`

## 目前焦點

在 `fix/assistant-direct-parameter-provenance-v1` 保留現行一段式 Granite 與18-action surface，只為五個
direct preprocess 加入必要參數的 latest-user-text provenance guard。明確值仍直接執行；缺值或模型
補值時零執行，以一般藍色英文 Assistant bubble追問。完成條件是同一exact source完成自動驗證、
真Granite host-aware evidence與正常ChatPanel真人手測入口；中間checkpoint不交付手測。

目前 phase：`Active；Qt process-isolation blocker已閉合，dataset-narrow fixture gap待閉合後重建exact-source candidate evidence`

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
8. Exact `941af892` 已以native GPU通過complete regression、Granite runtime／stable eval、RAG offline、
   human-like product與UI reviewer fixes；`dataset-narrow`在18個loaded-summary scenarios皆因驗證fixture
   直接新增table row、未像產品`update_panel()`於vertical scrollbar出現後重算column widths而失敗。
   同一scenario呼叫產品已有refit後，header／viewport從256／233收旂為232／233，
   horizontal scrollbar由1變0且table evidence通過，故不修改`XBrainLab/ui/`。先以red test要求
   loaded fixture做同步layout settle，再修正capture script；36／36 scenarios通過後，所有candidate evidence
   必須在新exact commit完整重跑，不沿用`941af892`的部分dossier。
9. Exact `251741a8` 的canonical handoff已通過complete regression、Granite／Assistant與
   `dataset-narrow` 36／36，但`visualization-render`仍沿用退役的「開啟Visualization panel就會
   背景計算saliency」假設；實際產品已依核准contract要求visible `Compute Saliency` action，
   因此訓練成功但saliency仍未計算。修復只讓capture顯式呼叫既有panel action，等待
   same-operation terminal與Application publication同時顯示available後才render；不復原自動compute，
   不修改UI／backend／tool owners。先加explicit-action／terminal regression test，再重跑該gate與
   全部new-exact-source handoff。
10. Exact `627f2ae3` 已在final dossier通過上述兩個blocker，但Data Import capture仍要求舊版
    compact step labels `EEG Data／Metadata`，而現行base與branch的visible contract均為`EEG／Details`，
    導致第一張760px artifact在capture前fail closed。只校正capture exact-text contract並加unit guard，
    不改產品Wizard、copy或layout；重跑全部Wizard artifacts／validator後，仍需以新exact commit
    從頭執行canonical handoff。
11. Exact `426616b3` 已通過manifest前39個checks、完整11269 passed／51 policy-allowed skipped、
    Granite 36／36 positive、五項missing-parameter host guard、public cross-source與原生UI證據；最後
    `handoff-dashboard`卻另外執行未採用baseline contract的raw `mypy XBrainLab/`，把現有142項債務
    全部判成candidate failure。同一dashboard與manifest已執行唯讀Basedpyright regression並確認相對
    locked baseline零新增diagnostic。修復只讓`--handoff`使用canonical Basedpyright regression；raw
    mypy只在使用者顯式`--include-slow-checks`時保留為diagnostic profile，不放寬任何manifest gate、
    baseline或產品程式。先以dashboard CLI contract red test鎖定handoff不隱式啟用raw mypy，再重跑
    focused dashboard tests並從新exact commit完整重建handoff dossier；dashboard或任一既有gate未PASS
    即停止，不交付手測。
12. Exact `18fcf33f` 的local manifest已40／40、dossier verified、完整11312 passed／8 policy-allowed
    skipped且dashboard PASS；人工remote boundary核對仍發現PR #40 Windows product-lifecycle失敗與其餘
    jobs未完成，因此local dossier不能替代GitHub acceptance。Windows唯一failure是`UI_UNIT_ROOT_TESTS`
    以`str(Path)`在Windows產生反斜線，但跨平台contract test用POSIX prefix計算已執行shards，導致實際
    10個shard全被呼叫卻誤算9個。只將runner產生的root test paths正規化為POSIX，不修改tests集合、
    UI或execution boundary；Windows原始failure作red evidence，新增portable path assertion並跑focused
    runner tests。其餘Linux jobs停在hosted runner system-dependency setup，先由新push建立fresh run，
    只有再次重現才修改workflow。新exact SHA仍須重跑local canonical handoff、人工抽查artifact，並等待
    PR所有applicable checks completed/success；任一pending／cancelled／failed都不交付手測。

## Merge boundary

Assistant product行為先以本短branch進`integration/assistant-stable-v2`。只有同一source的applicable CI
全數completed/success、真人手測通過並由使用者明確同意，才可合入integration；之後完整integration
candidate仍需另一次同源批准才可走PR合入`main`。Source改變即使手測失效。
