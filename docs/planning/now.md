# XBrainLab Now

最後更新：`2026-08-29`

## 目前焦點

唯一 active slice 是 **Assistant bounded clarification closure v1**。它從
`fix/assistant-clarification-capture-v1` 的 clean exact base
`ed184ce4b2ad831624e40ebc500e396f050d3e41` 開始；先前 clarification-capture v1 的 receipt bridge、
prompt/raw capture 與其歷史 evidence 保留在該 base，不在本 slice 重做或重新宣稱模型能力。

### 問題與 trace evidence

目前 direct-preprocess clarification 的資料流是：

```text
latest user text
  → model guessed/partial direct tool proposal
  → LLMController._evaluate_tool_proposal
  → ToolAttemptCoordinator / verify_direct_parameter_origins
  → existing AssistantToolInputReceipt + PendingInteractionCoordinator
  → next model proposal → normal verification / execution
```

這條路已能 fail closed，但仍有四個可觀察缺口。

1. `LLMController._evaluate_tool_proposal` 目前只在模型再次提出 partial parameters 時累積 values；它不能
   以 bounded Host form 安全處理「12、40」這類未標示的 bandpass values，也不能在 receipt 中保存一個
   unassigned cutoff。因此模型猜參數或遺漏參數時，使用者補得再清楚也可能在多輪後失去可執行的 same-tool
   路徑。
2. `AssistantToolInputReceipt`／`PendingInteractionCoordinator` 已是正確的 cross-turn evidence owner，卻只存
   verified fields；目前沒有「先收集、再排序」的窄範圍 representation。若另建 generic intent state、
   action queue 或自動 execution，會重複 owner 並改變 one-action contract。
3. `import_eeg_data` 是 zero-parameter GUI handoff，現有 publication pass 即可讓模型 proposal 前進；它缺少
   對 latest user text 的 narrow positive-origin guard，資訊／browse／否定內容不應開啟 Import UI。
4. strict parser 對 malformed output fail closed，但一般 format recovery 可再要求模型輸出 single action；這不
   等同於「已知兩個以上相鄰完整 top-level JSON objects 由 Host 請使用者選一個且零 action」。top-level array
   仍是一般 strict format rejection／recovery，不在本 slice 擴張。
   `run_stable_assistant_model_eval.py` 的 v10 同時保存 raw、Host 與 product 欄位，但 v11 尚未記下整條
   receipt/form/reconstruction trace，不能證明這次的 lifecycle contract。

## Observable outcome

- 對五個 direct preprocessing tools，Host 只收集 latest user-authored、field-bounded evidence；它不選工具、
  不猜科學值、不能自動執行。
- Bandpass 在首次指派時可由 explicit `low`／`high` labels 直接收集，或在沒有 assigned field 時把兩個 Arabic
  decimal cutoffs（同一或兩個 bounded reply）排序為 `min → low_freq`、`max → high_freq`；一個 unlabelled cutoff
  只能保存為 unassigned evidence，直到第二個值到來。已驗證 field immutable；correction、contradiction、invalid
  或 mixed ambiguous evidence 清除 receipt，必須以新 request 重啟。
- 收齊 evidence 後，模型仍須在 current publication 下提出同一 exact tool；Host 從 receipt 重建完整 params，
  再走既有 schema、range、publication、capability、confirmation、ApplicationService／UI handoff。receipt
  永不直接執行。
- `import_eeg_data` 只有 approved positive verb `import/load/open/select/choose` 對應 EEG `data/dataset/file/folder`
  的單一 request 才能進既有 GUI handoff；問題、browse/list、否定、cancel、ambiguous、path-only、multi-action、
  open epochs 或 load model 不得開 UI。
- 可證明的兩個以上相鄰完整 top-level JSON objects 一律零 retry-to-action、零 receipt、零 confirmation、零 UI
  handoff、零 execution，並得到 Host-owned trusted choose-one reply；array 維持一般 format recovery。
- v11 evaluator 用真實 controller/pending boundary 產生可檢查 trace，raw first model decision、Host boundary、
  follow-up raw decision 與 final product outcome 分開報告；Host rescue 不得增加 raw-model score。

## Scope、non-goals 與 assumptions

### In scope

- 修改既有 `AssistantToolInputReceipt` 的最小 bounded evidence field，並復用
  `PendingInteractionCoordinator`、`ToolAttemptCoordinator`、`LLMController` 與 verifier。
- 五個 direct preprocessing tools 的 bounded Host form：

  | Tool | Form fields |
  | --- | --- |
  | `apply_bandpass_filter` | `low_freq`、`high_freq`；首次 explicit labels 優先；沒有 assigned field 時完整 unlabelled pair 才 sort；single value unassigned；correction/ambiguity clears receipt。 |
  | `apply_notch_filter` | `freq` 的 user-proven decimal。 |
  | `resample_data` | `rate` 的 user-proven decimal。 |
  | `set_reference` | backend-supported、user-proven `method`。 |
  | `normalize_data` | user-proven `z-score` 或 `min-max`。 |

- Receipt-bound same-tool final proposal、receipt-reconstructed params、current publication／stale／cancel／
  correction-fail-closed restart lifecycle，以及 `import_eeg_data` narrow positive-origin guard。
- strict parser／recovery 對已證明相鄰完整 multiple top-level objects 的 direct choose-one terminal。
- v11 stable evaluator、case trace／report schema、focused unit/integration tests 與同一 pinned model 的 81-case
  run。

### Non-goals

- 不重啟 `GUIDED_WORKFLOW`，不建立 cross-turn multi-action queue／ordered action receipt，也不對「first … then …」
  部分執行；同一 user turn 仍只允許一個 action 或一個 reply。
- 不換 model／revision、quantization、catalog、tool membership、tool schema、ApplicationService command、
  capability policy、confirmation authority 或 GUI handoff owner。
- 不新增 word-number parsing；`fifty hertz` 及其他未被既有 decimal grammar 證明的字詞維持 fail closed。
- 不做 UI layout、widget、copy styling、中文 IME、prompt-capture、import/data workflow、performance 或 legacy-wide
  cleanup。Assistant trusted reply 的行為契約已由使用者核准；**UI confirmation = N/A**，因本 slice 不修改
  `XBrainLab/ui/` 的可見 layout／interaction。若施工發現需要 UI change，停止並取得新的明確確認。

### Assumptions

- latest user text 是唯一可供 form 證明 value 的來源；model parameters、examples、history、defaults 都不是
  evidence。
- 所有已驗證 receipt field immutable；explicit bandpass label 只在首次指派時優先於 sorting，不能覆寫早期
  evidence。任何 tool form 的 correction、contradiction、invalid 或 mixed ambiguous input 都清除 receipt，使用者
  必須以新 request 重啟。
- generic `filter data` 不建立 pending intent；模型先要求選 bandpass/notch，後續明確同 action request 才能
  走 existing receipt admission。
- `import_eeg_data` guard 只讀 latest text、只保護此 GUI entry，不能演變成 general semantic Host router。
- target 中的 public behavior 已由使用者核准；任何超出本 plan 的 tool/action/confirmation/public behavior
  變更仍須重新決策。

## Owner、deletion-first 與 complexity boundary

### Current call sites and owners

- `CommandParser`／strict-envelope recovery：classify raw output before any proposal reaches execution.
- `ToolAttemptCoordinator`：current publication admission、origin rejection、existing typed receipt admission 與
  deterministic attempt decision。
- verifier：direct parameter provenance 和 narrow affirmative request matching；不選 action。
- `PendingInteractionCoordinator`：唯一 receipt lease、replace、requeue、clear lifecycle owner。
- `LLMController`：turn lifecycle、receipt activation／presentation、same-tool attempt 與 existing terminal handoff。
- `ContextAssembler`：只投影 host-owned receipt context；`ApplicationService`／capability／confirmation／UI owner
  維持不變。
- stable evaluator：evidence consumer，不得成為 receipt／execution owner。

### Target owner delta

Owner 數為 **0 delta**。`AssistantToolInputReceipt` 只擴充 bandpass unassigned evidence，
`PendingInteractionCoordinator` 仍是唯一 pending owner；collection/reconstruction 是 verifier + existing
coordinator/controller 的 bounded deterministic policy，不新增 generic form controller、intent classifier、queue、
state machine、second receipt type、fallback tool selection 或 alternate execution path。

施工前必須先檢查且能刪才刪的 candidates：

- controller 內目前只為模型 partial params 寫的 hand-coded merge/requeue branch；若 bounded form 完整取代其
  policy，移除重複 accumulation，不能同時保留兩套 precedence。
- evaluator 內任何手動 receipt／parameter accumulation surrogate；v11 必須改由 product-equivalent controller
  boundary 觀察，不能留下第二套 lifecycle。
- `GUIDED_WORKFLOW` compatibility residue **不是** 本 slice 的 deletion target；不重啟也不混入清理。

Complexity review **已觸發，先記錄而非以 incremental base 規避**。`ed184ce4` 相對 `main` 的既有 production
scope 是 7 files、`+317/-105`、net `+212`；本 closure 預估另增 net `+180–260`，並會新增 parser/recovery
等 touched files。因此整個 PR projected total 是 net `+392–472`，且很可能超過 8 production files。施工與
review 都必須在 exact integrated SHA 重算完整 `main..HEAD` 的 files、`+/-/net LOC`，不只看
`ed184ce4..HEAD`。

這個 full closure 可維持同一 PR 的唯一理由是：所有差異都完成同一既有 receipt transaction（user evidence →
same-tool proposal → existing command boundary），可刪除／取代 controller partial merge 與 evaluator-local
surrogate，且 owners 維持 0 delta、沒有 new public tool、queue、state machine 或 alternate execution path。兩位
fresh reviewers 必須明確判斷這仍是 coherent slice；若任一 reviewer 判定無法合理維持同 PR，停止並回報 Root，
不得默默以 `ed184ce4` incremental delta 掩蓋。

可能的既有 production 檔案僅限 `turn.py`、`verifier.py`、`tool_attempt_coordinator.py`、`controller.py`、
`parser.py`、`strict_envelope_recovery.py`，以及只有在直接需要 receipt-bound prompt/context 時的既有
`prompt_policy.py`／`assembler.py`；不新增 module／public class／authoritative owner。若實際 total production
delta 超過 `1,500` net LOC，必須拆 PR；若需要 new receipt type／queue／owner、或無法刪除重複 policy，先停下
做補充 complexity review，列出 `+/-/net LOC`、owners before/after、deletion/reuse、rollback，再請 Root 決策。

Rollback 是回退本 slice 的 production commits 到此 exact base；target contract 若要撤回則需新的使用者決策，
不得以 runtime fallback 偷改行為。

## Repair steps、two-worker boundary 與 review

兩位 worker 不可同時修改同一 production file；Root 只協調 exact SHA、scope、review 與 gates，不代替任何
worker 或 reviewer 判定。

1. **Worker A — Host form / lifecycle author（TDD）**

   - Owns `turn.py`、`verifier.py`、`tool_attempt_coordinator.py`、`controller.py`，及其直接 tests；只在必要時
     接上既有 prompt/context file，先在 plan 記錄原因。
   - 以 existing receipt 實作五個 bounded fields；bandpass explicit-label 首次指派 precedence、single unassigned
     value、two-value sort、以及 correction/contradictory/invalid/mixed ambiguity 的 clear-and-restart、budget、
     cancel/topic-switch/stale/different-tool clear 都須經 existing pending coordinator。
   - 要求 same-tool final proposal，將 receipt evidence 重建 params，再重跑既有 admission chain；不讓 model
     params 成為 value source，不 auto-execute。
   - 新增 `import_eeg_data` narrow positive-origin guard，並證明 no UI handoff on non-positive cases。
   - 接上 Worker B 的 typed multiple-proposal decision，但不實作 parser/recovery policy。

2. **Worker B — strict output / evaluator author（TDD）**

   - Owns `parser.py`、`strict_envelope_recovery.py`、`scripts/dev/run_stable_assistant_model_eval.py`、case/report
     data 與其直接 tests；不得改 controller、receipt lifecycle 或 tool policy。
   - 先定義可證明兩個以上相鄰完整 top-level JSON objects 的 typed classification／direct choose-one outcome；
     top-level array 與一般 malformed JSON 保持 existing repair，不能依 error text 猜 multi。
   - Worker A 接上 typed outcome 後，把 evaluator 升為 v11：保持 81 denominator、以 actual controller/pending
     boundary trace raw → Host admission → receipt form → final model proposal → reconstructed params → product terminal；
     不自行建立 receipt 或合成 values。

3. **Fresh lifecycle reviewer（非 Worker A）**

   - Review exact integrated SHA 的 authority、receipt data provenance、首次 explicit/unlabelled bandpass precedence、
     immutable-field correction restart、same-tool/stale/cancel/topic/different-tool lifecycle、import guard、
     zero-execution adjacent-object multiple path、
     deletion/owner/LOC boundary。最多三個 blocking findings；不能以 broad robustness 擴 scope。

4. **Fresh evidence reviewer（非 Worker B）**

   - Review v11 trace source separation、81 denominator、raw/Host/product gates、no synthesized receipt、report source
     identity、focused model command/result。最多三個 blocking findings；不能把 raw limitation 改記為 product success。

5. **Integration Lead / Root**

   - 只在兩個 focused green checkpoints 與兩份 fresh review 都無 blocker 後整合；核對 clean exact head、base、
     production numstat 與 protected `settings.json`。不在 review 時順手改 implementation。

### Integration checkpoint — 2026-08-29

- Clean integration base `f7a29284f2c779b0345fffb517d303163c074511` received product commit
  `9fe169af4537832a59003cec22db2ae1d75ed019` as integrated commit `54e93599` and evaluator commit
  `03d671610984083d1f5e0d11aba1298e8fe2b2c6` as integrated commit `9070ff11`. Cherry-picks had no
  conflict; this checkpoint itself must be committed separately before validation so the later exact source is
  reproducible.
- On `main..9070ff11`, runtime `XBrainLab/` production code is 11 files, `+707/-261`, net `+446` LOC.
  Including executable `scripts/dev/` code gives 13 files, `+1,610/-463`, net `+1,147` LOC; docs, cases and
  tests are excluded from both figures. This exceeds the net-300 and eight-production-file complexity triggers,
  but remains below the 1,500-net mandatory split threshold. Owners remain the existing parser/recovery,
  coordinator, verifier, pending coordinator, controller, assembler, backend and evaluator boundaries; no new
  production module or authoritative owner was added. The two planned deletion/replacement candidates are the
  controller's old model-partial merge path and evaluator-local duplicate trace composition.
- Next step is fresh non-author lifecycle and evidence/privacy review on the eventual clean integrated SHA,
  followed by the focused union regression. This checkpoint records no test, model, CI, handoff or manual-acceptance
  result.
- Evaluator follow-up source `9a1fa6656bef1f87da4e63ba1d3846e34fea05c3` was cherry-picked as `ca5183e0` after
  the first union regression exposed four obsolete harness continuations: the harness reset a receipt but did not
  replay the product's pre-model user-evidence collection. The correction stays in the evaluator/test boundary;
  the next step is to rerun the same union regression and then obtain fresh review. This entry intentionally records
  no rerun, model or acceptance result.

### Fresh-review blocker repair — 2026-08-29

Fresh non-author review of clean integrated `f37416e523f023fc69f868d1f77aaf75b2bb20bc` found two bounded
blocker groups. This repair remains part of the same closure: it does not add a LocalBackend/product owner, UI,
model change, new exception-control-flow path, receipt type, queue, or generic semantic router.

1. **Typed clarification origin.** `respond_to_user` must not mint a direct receipt merely because a typed pending
   tool is otherwise current. Reuse the existing affirmative direct-action matcher at typed clarification admission.
   Add the regression ``What is resampling?`` → ``128 Hz``: it neither admits a receipt nor reaches execution. The
   five affirmative direct-tool cases remain admitted.
2. **Evaluator/product evidence closure.** The evaluator must preserve typed adjacent complete objects as a
   Host choose-one product-safe terminal while keeping raw failure; narrowly recognise the existing
   `import_eeg_data` positive-origin `INTENT_BLOCKED` terminal as product no-action (not a raw pass); and use an
   internal untruncated final raw response for direct receipt admission while retaining only the bounded report
   preview. Its raw candidate gate is only first-generation positive `36/36`; challenge, precision and clarification
   raw results remain per-case diagnostics. Add a separate exact direct-admission `5/5` gate.

   The script-only evaluator also gains opt-in prompt-capture integrity. With capture disabled it performs zero
   capture filesystem I/O. With it enabled it validates one fresh session, contiguous completed sequence, recorded
   prompt/raw bytes and SHA-256, model/revision/options, and evaluator trace index-to-capture raw hash equality.
   The report exposes only redacted session identity, counts and booleans—never paths or content. Missing, malformed
   or mismatched capture is evidence-gate failure only: inference/report generation remains nonblocking. This is
   evidence validation over the existing LocalBackend capture, not a LocalBackend change or a concurrent-writer
   guarantee.

Repair ownership is deliberately disjoint: the lifecycle worker may change only existing coordinator/controller
admission and direct tests; the evaluator worker may change only evaluator script/tests/report cases. After both
focused checkpoints, integration reruns their union, ruff and diff checks, then fresh lifecycle and evidence review
on the exact clean SHA. No model run, handoff, PR, UI acceptance or merge is implied by this checkpoint.

### Repair integration checkpoint — 2026-08-29

Clean `cad16a8494c1bb1d5a297ac79b7849faf5250f94` received evaluator source
`e334dc22b4d74584d3af3efdfc7e7a480c2a9662` as integrated commit `330f6684551bd30f02091e4ee539b09ed4777060`;
there was no cherry-pick conflict. The lifecycle author checkpoint is `cad16a84`: existing typed admission now
requires the affirmative direct-action matcher, with the informational-question/numeric-follow-up regression and
retained positive direct cases in its focused controller/policy tests. The evaluator author checkpoint is
`330f6684`: its focused script tests cover safe adjacent-object choose-one, narrow import-origin no-action,
untruncated direct admission, raw-positive-only and direct-admission gates, plus opt-in capture integrity.

The evaluator change is confined to the existing development evaluator and its test file (`+707/-19` lines across
two non-production files); the lifecycle repair changes the existing coordinator and direct tests only. It does not
change a production owner, LocalBackend, UI, model, tool/public contract, or exception control flow. Author
checkpoints are implementation evidence, not a review, model, handoff or manual-acceptance result. Next: run the
specified model-free union and static checks on the exact integrated SHA, then obtain fresh non-author lifecycle and
evidence/privacy reviews before any model run.

### Fresh review outcome and evaluator trace repair — 2026-08-29

The fresh lifecycle review is **PASS** on `22449a0083426e05b38e4da9da13f0ee2fe7d5d0`. The fresh evidence review is
**BLOCKED**: 74 first-turn rows directly infer a product decision from evaluator-side static logic and therefore omit
controller-observed Host admission and product terminal. That conflicts with the v11 trace contract; a safe-looking
score is not evidence that the product boundary was actually reached.

The approved minimal repair is evaluator-only. Extend existing `_EvaluatorControllerHarness` and its direct tests so
that, after strict recovery, every final first-turn response is replayed through the existing unbound
`LLMController` parsing, admission, processing and presentation methods. Recorder adapters stop at execution,
confirmation, UI handoff, ApplicationService, ToolExecutor and state-mutation boundaries; they record crossing
attempts but never perform side effects. Every first-turn row must then carry explicit controller-observed
`host_admission` and `product_terminal`. The `24/24` product no-action gate must prove no boundary crossing through
that replay. Positive execution rows may state only **execution boundary suppressed**, never downstream execution
proof.

Raw score/generation capture, case taxonomy and fixed 81-case denominator remain unchanged. Remove or replace the
static product-surrogate and duplicate guards where the controller trace now owns the answer. This does not alter
product code, UI, LocalBackend, model/revision, receipt lifecycle, owner count or public contract; UI confirmation
remains N/A. The estimated delta is `+250–350` evaluator script LOC and `+180–260` test LOC, with production delta
`0` and owner delta `0`.

The evaluator worker begins with focused red tests for the absent controller fields and for recorder no-side-effect
boundaries, then makes the focused evaluator suite green. Integration subsequently repeats the exact seven-file
model-free union, ruff and diff checks; fresh lifecycle and evidence reviewers re-review the new clean SHA. A model
run remains stopped until that review closes. No test, model, handoff, PR or manual success is claimed by this
planning checkpoint.

## Focused validation、v11 trace 與 model gates

### Direct behavior tests

- Five direct tools：model guessed missing value → Host receipt has only user-proven evidence；scalar/method fields不從
  model/default取得。
- Bandpass：both labels、one label、two unlabelled in one reply、one then second unlabelled reply、mixed values、
  contradictory input、explicit correction、partial/requeue/budget exhaustion；所有 receipt field immutable，任何 tool
  form correction/contradiction/invalid/mixed ambiguity clear receipt and restart，single unassigned never maps to
  low/high。
- Generic filter → user selects bandpass：不建立 generic state，只有 exact action request 才有 receipt。
- Receipt complete：wrong/different/no-tool/malformed final output 不執行；same exact model proposal 才以
  receipt-reconstructed params 通過 normal schema/range/publication/capability/confirmation path。
- cancel、new chat、topic switch、stale publication、unavailable action、active receipt replacement、multi-action：
  zero execution，evidence 不外洩。
- `import_eeg_data`：approved verb/object affirmative request 能進既有 handoff；question/browse/negated/cancel/
  ambiguous/path-only/multi、open epochs與load model 零 UI handoff。
- parser/recovery：two adjacent complete top-level objects 得 trusted choose-one、零 retry-to-action/receipt/
  confirmation/execution；top-level array與single malformed JSON仍用既有 finite repair。

### v11 report contract

v11 的每一 row 必須包含 first raw output/taxonomy/raw score、由 controller replay 觀察的 first Host
origin/admission decision 與 product terminal、每次 follow-up raw output 與 form transition、final same-tool
proposal、receipt-reconstructed params、verification/confirmation/UI-handoff decision。source raw、follow-up raw、Host safety/admission、product
outcome 不共用分數欄位；Host block/receipt/reconstruction 永遠不得回填 raw score。

81-case denominator 固定為 `36 positive + 14 challenge + 24 precision + 7 clarification`。Gate 不能降低：

- raw first-generation：只 gate `36/36` positive；14 challenge、24 precision與7 clarification raw result逐 case
  完整報告（包含 critical／wording 分類），不得由 Host rescue 灌成通過，但不以 raw `24/24` precision或raw
  `7/7` clarification作 candidate requirement；
- Host safety：`15/15`，即 `10/10` explicit direct-parameter origins + `5/5` missing-parameter origin blocks；
- direct Host clarification admission：`5/5` exact direct receipts；
- product outcome：`24/24` precision no-action、`7/7` clarification execution boundary；
- 81-case 中所有 no-action rows，及 import/adjacent-object-multiple focused probes：零 confirmation、GUI
  handoff、ApplicationService／ToolExecutor execution或state mutation。
- prompt capture integrity is opt-in evaluator evidence: disabled runs add no capture filesystem access; enabled
  runs must prove a single fresh session, completed contiguous sequence and capture/trace byte-SHA/model/options
  agreement through a redacted report. Integrity failure fails only evidence gating, not inference control flow.

Focused Python tests、`ruff check`、`ruff format --check` 與 `git diff --check` 必須先通過。任何 Qt/PyTorch/MNE
related validation 使用明確 timeout 與 `prlimit --core=0`。之後才以固定 Granite model/revision 和 clean exact
SHA 執行 v11 81-case command；report 記錄 exact argv、model/revision、case SHA、source SHA、working-tree identity
與完整 gate outcome。model run 結果是 capability evidence，不是手測或 merge 授權。

## Stop condition、PR、CI 與 manual acceptance

- **Scope-complete checkpoint**：上述 focused tests、v11 report/unit coverage、兩份 fresh review 和 complexity
  accounting 都完成；model run 如有 gate failure，保留 exact report 並交回 Root，不能改 model、放鬆門檻、
  prompt-tune 到「看似通過」或擴張 Host authority。
- **Fail closed**：若需要 general intent owner、multi-action queue/guided workflow、auto execution、word-number
  parser、UI change、新 tool/public side effect、receipt type/owner、或 unsafe execution/confirmation，立即停止，
  保留 evidence 並要求新決策。
- **PR gate**：PR base/head 必須精確、branch clean/explained，CI 所有 non-skipped checks 都
  `completed/success`；missing/pending/stale/cancelled/failed 都不能 handoff。只可在同一 production exact SHA
  上附上 focused evidence、v11 report與兩份 review。
- **Manual gate**：Root 只在 PR/CI green 的 exact head 提供手測。使用者至少驗收 direct bandpass clarification
  （labels 或 two unlabelled values）、cancel/different-tool、affirmative vs informational import、以及 trusted
  choose-one boundary；source 改動即使 commit 後也使舊 hand test 失效。使用者明確通過並同意 merge 前不得 merge。
- `settings.json` 和任何 worktree-local settings 永遠不得 stage、commit、覆寫、revert 或隱藏。
