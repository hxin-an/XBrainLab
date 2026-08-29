# XBrainLab Now

最後更新：`2026-08-29`

## 目前焦點

唯一 active slice 是 **Assistant clarification capture v1**，從 exact base
`9e9df2afef503c553bf7d5ac332a57f7e7b48b2f` 的 branch
`fix/assistant-clarification-capture-v1` 開始。

已確認的能力邊界是：五個 direct preprocessing missing-parameter first turn 中，模型仍會猜測值並
提出 action。既有 parameter-origin guard 會 fail closed，阻止 ApplicationService／ToolExecutor 執行；但
現有 admission path 沒有把這個可理解的 blocked proposal 轉成同一 action 的
`AssistantToolInputReceipt`，因此 runtime 沒有可用的 follow-up question、verified values 或 exact pending
action，81-case clarification trajectory 是 `0/7`。本 slice 的目標不是讓 Host 替模型選工具或修正模型答案，
而是在 origin guard 已經拒絕不受使用者支持的 required values 時，保留該次產品 admission 已知的 factual
missing-input state，讓 Assistant 能安全地向使用者追問並接受下一輪補值。

## 施工進度（integration checkpoint）

- Plan commit `610f7640` 已完成；integrated exact commits 依序為 `3e1da98d`
  （origin guard → existing typed receipt）、`7d010388`（evaluator receipt-origin evidence）與
  `98f2839f`（LocalBackend opt-in runtime capture／developer testing docs／direct tests）。目前 HEAD
  是這三個 commit 之後的 integration branch，active slice 尚未關閉。
- 相對 exact base `9e9df2af` 的 production scope 正好四檔：`LLMController`、
  `ToolAttemptCoordinator`、`verifier`、`LocalBackend`；numstat 為 `+261/-33`、net `+228`，符合
  `<=4 files`／`<=230 net LOC`。沒有 UI、prompt wording、model/revision/catalog、tool membership、
  settings 或新增 production module／owner 變更。
- 同一 integrated HEAD 已完成 focused joint validation：controller／tool-attempt policy／verification、
  full evaluator unit、LocalBackend runtime capture 與 model-context boundary，共 `515 passed`（一個既有
  MNE deprecation warning）；touched Python scope 的 `ruff check`、`ruff format --check` 與
  `git diff --check` 均通過。未跑 81-case pinned-model suite、未建立 PR、未 push 或 merge。
- 下一步是兩位 **fresh reviewers**：admission reviewer 檢查 receipt action/verified-value/negative lifecycle
  與 owner boundary；evidence/privacy reviewer 檢查 env-disabled zero filesystem、prepared/completed/
  cancelled/failed artifacts、hash／attempt count、runtime privacy warning與 evaluator raw/Host/product score
  separation。兩份 review 都無 blocking finding 前，不進 81-case model run 或 PR。
- 已知 unsupported claims：尚無 integrated exact HEAD 的真實 GUI runtime capture artifact、81-case real-model
  score 或使用者手測；Host-origin receipt 只證明 fail-closed continuation admission，不證明 first-turn raw
  model clarification accuracy，也不承諾 prompt-only capability boundary 已被消除。

## Outcome

- 當模型選擇一個 direct preprocessing action、required parameters 含有非使用者／receipt 支持的值而被
  origin guard 拒絕時，runtime 產生既有語意的 `AssistantToolInputReceipt`：exact action、仍缺欄位、
  concise question、已驗證的 user values 與 current workflow stage。
- receipt 只提供下一輪 latest reply 的 factual continuation context；它不授權執行、不覆寫 capability、
  不把 action proposal 視為完成，也不替模型選擇／替換 tool。
- 補齊所有 missing values 的下一輪仍必須由模型重新提出同一 exact enabled action，並走既有
  admission、confirmation、origin verification 與 execution path；cancel、topic switch、stale receipt、
  different tool、partial reply 與 multi-action 保持零 unsafe execution。
- opt-in runtime capture 真正擷取 GUI 使用的 `LocalBackend.generate_stream` final fitted prompt 與每次 raw
  output（含 retry），並記錄 admission outcome；它用於判斷本方案是否改善 81-case clarification journey，
  但不改變 generation、admission 或 execution 行為。

## Evidence、假設與 privacy

- 已知 evidence：prompt/context-only v4 的 final exact source `fead32ca` 保留 `07c0b6ad` prompt，raw
  positive `36/36`，challenge `5/14`，precision `15/24`，clarification `0/7`；Host parameter safety
  `15/15`。此 slice 只處理已被 origin guard 阻擋卻未形成 receipt 的 clarification admission gap，
  不宣稱提升 first-turn raw model tool-selection accuracy。
- 假設：existing guard result 已足以由 current request、published contract 與 trusted state 推導 exact
  missing inputs；若無法無歧義地推導，必須維持拒絕並只產生一般安全 explanation，不能建立 receipt。
- 固定模型／revision：`ibm-granite/granite-4.0-micro@56111ae135df9c53a78c99028e7bc24035a9e979`；
  不換模型或 revision。
- Runtime capture 只在 developer 明確設定
  `XBRAINLAB_ASSISTANT_PROMPT_CAPTURE_DIR=<absolute-directory>` 時啟用；未設定時零 IO。每一次 generation
  或 retry 以 `<dir>/<session>/<sequence>/{prompt.txt,raw-output.txt,metadata.json}` 寫入，metadata 含
  `prepared`／`completed`／`cancelled`／`failed` 狀態、model/revision/options、attempt count、source／content
  hash 與必要 redaction metadata。capture write failure 必須 nonblocking、redacted，且不可改變產品結果。
- capture tests 可用 synthetic fixture，但實際功能可擷取 GUI runtime，artifact 因此**可能含 chat、path 與
  dataset metadata**，有真實 privacy risk；操作者必須使用受控本機 absolute directory 並在需要時人工清除。
  不寫入 UI、settings、upload、support log、git repository、model cache 或自動收集服務；不得假稱沒有
  privacy risk。

## Scope、non-goals 與 authority

- Scope：既有 direct-parameter origin rejection 到 Assistant clarification receipt 的最小 bridge；existing
  `LocalBackend` owner 的 opt-in runtime final prompt／raw-output capture；直接相關的 controller/admission/
  context tests 與 81-case evaluator projection／report evidence。
- Non-goals：不改 system prompt wording/order、word-number parser、model／revision、18-tool membership、
  tool schema/name/side effect、capability policy、confirmation、ApplicationService command、GUI handoff、
  UI、中文 intent/verifier、`settings.json` 或任何 real-data import／training flow。
- Owner before：`verify_direct_parameter_origins` 判斷 parameter provenance；
  `PendingInteractionCoordinator`／`ToolAttemptCoordinator` 擁有 receipt admission、continuation 與
  verification；`ContextAssembler` 只投影 receipt；`LocalBackend` 只套用 message boundary/template。
- Owner after：相同。只在既有 admission owner 補足「guard-rejected direct proposal → existing typed receipt」
  的單一 state transition，並由既有 `LocalBackend` 完成可選 capture；不新增 owner、state machine、receipt
  type、semantic Host router、fallback tool selection 或第二個權限來源。
- 預估 production 改動不超過 4 個檔案、150–230 net LOC。若超過其中任一限制、需要新增 public contract
  或無法復用 existing receipt constructor，先停下做 complexity review，不擴張本 slice。

## Repair steps、分工與 review

1. **Capture/evidence worker**（TDD、限 existing `LocalBackend` owner、scripts 與直接 tests）：
   - trace `ContextAssembler.get_messages` → LocalBackend template → raw response → origin guard → admission
     的實際 runtime seam；提出最小 capture API／artifact schema，證明不載入第二個 prompt path。
   - 以 synthetic fixture 驗 capture 的目錄／狀態／hash／nonblocking redaction，並建立 81-case focused
     evidence，分開 raw first response、guard block、receipt admission、follow-up response 與 product outcome；
     不修改 product admission。
2. **Admission worker**（TDD、只改 existing owner 與直接測試）：
   - 先寫會重現「guard blocked、無 receipt」的 observable red test，再以 existing typed receipt constructor
     完成最小 bridge；確保 receipt 的 action／stage／missing／verified values 均來自 trusted current
     admission facts。
   - 模型猜值一律丟棄，只保存原文可證明的 partial user values；wrong／ambiguous／multi／negated／
     informational／stale／unavailable／cancel／topic switch 一律不建 receipt。文字 `fifty hertz` 保持
     fail closed，不擴張 word-number parser。
3. **Admission reviewer**（獨立於 admission worker）：
   - 核對 authority、receipt scope、stale/cancel/different-tool/partial/multi transitions、owners before/after、
     production LOC/file count，並以 reachable behavior 提出最多三個 blocking findings。
4. **Evidence/privacy reviewer**（獨立於 capture worker）：
   - 核對 capture 只走 product runtime prompt path、raw/product score 未混淆、artifact redaction／SHA／source
     identity、English 81-case denominator 與 unsupported claims；不重複 review admission implementation。
5. **Integration Lead**（非 author／reviewer、只整合）：在兩個 focused green commits 與兩份 review 都完成後，
   核對 exact head、建立 PR、觸發 CI 與安排 checkpoint；不代替任一 worker 實作或 reviewer 判定。
6. **Root**：只協調／唯讀觀察，維持本 plan、核對 exact base/head 與 settings protection，分派兩位 authors 與
   兩位 fresh reviewers；Root 不修改 implementation，也不代替 reviewer。

## Focused validation 與 81-case criteria

- TDD focused tests：
  - origin guard blocked direct proposal creates no execution attempt but exactly one typed receipt only when
    action/missing values are unambiguous;
  - receipt projection keeps host-issued data untrusted/no authorization, and duplicate assistant question is not
    reintroduced;
  - one-reply completion proposes the same exact action with only verified + latest-reply values; partial,
    cancel, stale, different action, topic switch, negated and multi-action cases do not execute;
  - capture uses exact `LocalBackend.generate_stream` final fitted prompt and every raw output/retry, has one
    artifact per actual attempt with matching hashes, and is zero-IO/nonblocking when disabled or write fails.
- Evaluator focused criteria（81 English cases）：raw positive `>=36/36`；Host safety `15/15`；direct Host
  clarification admission `5/5`；product clarification `7/7`；product no-action `>=21/24` 且零新增 unsafe
  execution；capture artifact count 必須等於 actual attempts 且 hash 一致。14 challenge raw 是 known
  limitations，必須完整揭露但不得要求全部歸零、不得以 Host rescue 灌入 raw score。所有缺參數 guard block
  維持零 execution；raw score、Host safety 與 product outcome 分開報告。
- 只在 focused unit/integration、capture tests、source guards（若穩定）全綠後，才由 worker 對同一 clean
  exact SHA 跑一次 pinned-model 81-case suite。這不是 full handoff，也不是 hand test gate。

## Stop condition 與 handoff

- **Bounded baseline success**：bridge 可由 existing owner 表達、focused tests green、capture 的 actual attempt
  artifacts／hash／privacy warning 符合上列規則，且 81-case criteria 全部達成、raw/Host/product claims 分開。
  之後由 Lead 建立 exact-head PR、所有 CI non-skipped checks `completed/success`，再由 Root 交付同 SHA 使用者
  手測；使用者手測通過並明確同意 merge 前不得 merge。
- **Stop/fail closed**：若 guard result 無法唯一推導 exact action/missing inputs、需要 prompt／parser／tool
  contract／new owner、任一 cancel/stale/different-tool/multi path 能執行、或 81-case 仍顯示 critical
  unsafe outcome，即不擴張修理；保留 evidence、列出 capability boundary，交回 root 取得新決策。
- 失敗只形成 capability checkpoint：不改 prompt、不放寬 gate、不擴張 parser／tool contract／owner；保留
  redacted evidence並交回 Root 取得新決策。兩位 authors 與兩位 fresh reviewers 必須角色分離，任一 reviewer
  有 blocking finding 即不得進 PR。
- Root `settings.json` 和 worktree-local settings 均不得 stage、commit、覆寫、revert 或隱藏。
