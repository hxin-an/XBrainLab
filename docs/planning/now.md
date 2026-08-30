# XBrainLab Now

最後更新：`2026-08-30`

## Current baseline and campaign outcome

PR #71 已以 exact head `ab8b395e13a895d21e9f100d3ee379882e420236` 通過使用者手測並合併；
manual acceptance 記錄在該 PR。Pre-plan `main` 是 merge commit
`5bb55c206d8f481d184d065c4091e92b2417130e`。建立本 planning worktree 之前，Wave 0 的 Git
inventory 已將 25 個舊 worktree 收旂為唯一 `main`：具名 branch 保留，7 個 detached
head 以 `archive/worktrees-20260830/*` 保存，只有使用者擁有的 root `settings.json`
維持修改狀態。當前 worktree／branch／dirty identity 仍只從 Git 即時讀取，不由本文件代替。

PR #73 已以 exact head `4dda38269e443ecb683c40280d586eb9746ba11d` 通過使用者 WSLg
手測並以 merge commit `b536c0346003a06e4d4b7da7e842a6c3b91ea446` 合併；B1 worktree
與 task branch 已清理。Lane B 的下一個 slice 是 B2。

本 campaign 要在不新增 workflow owner、不建立第二套 command／state truth 的前提下，交付：

1. 一次全面、可分類驗證的 Assistant production 與 test legacy cleanup。
2. 一份無混合分母、可人工閱讀的 Assistant evaluator report contract。
3. Import review 一致性、Epoch anchor 文案、全域 Warning 視覺去重複。
4. Training Settings 中已核准的 class loss weighting 與 validation early stopping。

本文件合併後，所有 implementation branch 必須從當時的 exact `main` 建立；
`5bb55c20` 只是 pre-plan identity，不得當成後續 product branch base。

## Roles and worktree control

- **Root coordinator**：唯一能修改本 plan、canonical target／decision、worktree ledger、PR
  base／head、CI／manual record 與 merge state 的角色。Root 做邊界與證據審核，不用自評
  取代 worker 或 reviewer。
- **Assistant implementer**：一次只擁有 Lane A 的一個 bounded PR；不修改 product lane，
  不自行 merge 或宣稱 handoff-ready。
- **Product implementer**：按 Lane B 順序一次處理一個 product PR；不與另一 worker
  同時修改 ApplicationService／Training shared owners。
- **Independent reviewer**：只審查 frozen exact SHA，檢查 scope、owner、observable behavior、
  test quality 與 claim。可以因可重現的 contract／lifecycle／evidence defect veto，不在被審
  branch 實作自己的 finding。
- **Cross user-simulator**：非作者 worker 用 product-equivalent scenario 交叉驗證。這只是第二層
  保險，不取代 exact-SHA Windows 真人手測。

同時最多保留 `main + 2 implementer worktrees + 1 ephemeral reviewer worktree`。一個 PR 推送並
freeze 後，可移除本機 worktree、保留 branch 等待 CI／手測；需修正時才以原 exact
branch 重建。Worker 不得以 detached／歷史 branch 當 base，不得自動 cherry-pick 其他 lane。

## Lane A — comprehensive Assistant cleanup

### A1. Production and test legacy cleanup

**Current checkpoint and next step**

PR #74 原 head `8b9d2af4b5b7ac344de20a4154226f96ad22dfb7` 已完成 frozen inventory、
net-negative cleanup、focused evidence 與 CI；B1 合併後已將新 `main` merge 進 A1，舊 head 的
exact-source evidence 只保留為 baseline。receipt optional-access 已在既有
`tool_attempt_coordinator.py` owner 內以明確 `receipt is not None` 分支收窄，43 個 direct
receipt／policy／product-flow tests 通過，且該檔 Basedpyright 診斷歸零；`verifier.py` 與 montage
dialog 的兩個 diff 外診斷不納入 A1。非作者 user-simulator 亦在 frozen `e0cf4909` 通過 9 個
receipt／cancel／ChatPanel scenarios；independent reviewer 找到的唯一 blocker 是 canonical evaluator
harness 仍委派到已刪除的 `_reject_excluded_turn_command`，該無 caller wrapper 現已直接刪除，evaluator
與 product-flow 共 71 個 tests 通過。下一步建立新 frozen SHA，重做非作者審查、canonical handoff／CI
與 exact-SHA 手測。不得新增 replacement、owner、receipt、compatibility path 或其他 Assistant
cleanup candidate。

**Problem and evidence**

Assistant production 約 20.5K LOC；`controller.py`、`agent_manager.py`、runtime lifecycle 與 verifier
是大型但仍有真實 product callers 的 owner，不能因檔案大就切碎。目前真實 cleanup 空間是：
零 caller／no-op policy、已退役 Guided transport，以及大型 Assistant tests 中重複驗證 private
ordering 與 MagicMock choreography 的證據。

**Scope**

1. 刪除零 production caller 的 `state_reliability.py`，與 ignored ASK mode／workflow cap／fake-cap
   plumbing；不改 strict parser、verifier、receipt、generation correlation 或 security boundary。
2. 先強化至少一條 lower-mock product entry evidence，覆蓋 direct action、stale publication 不執行、
   receipt completion 不產生額外 generation，cancel／shutdown；再刪除重複 private-state、純順序與
   mock-only tests。
3. 退役尚未被產品使用的 Guided workflow transport：enum／factory／request fields、
   lifecycle／orchestrator／controller／assembler mode plumbing、可見 `Scope: Only this request.`
   與專屬 obsolete tests。保留一般 Assistant UI、18-tool contract 與所有 ApplicationService side effects。

使用者已明確授權移除上述可見 scope copy／row；這是 A1 唯一核准的可見變更。交付需有
ChatPanel 一般 request／progress／stop 的 screenshot 或 walkthrough，證明移除 row 後沒有空洞、夾斷或
狀態資訊遺失。

**Frozen candidate inventory**

| ID | Production candidates | Test disposition |
| --- | --- | --- |
| A1-01 | 整個 `XBrainLab/llm/agent/state_reliability.py`；兩個 reliability helpers 全 repo 零 import／caller。 | 直接刪除；無 replacement。 |
| A1-02 | `execution_policy.py` 的 `ASK_MODE`與 ignored `mode`／`workflow_tool_cap`；`tool_attempt_coordinator.py` 的純轉傳；`controller.py` 的 `_max_tool_executions`與 `_active_policy_mode()`。 | 收旂 `test_execution_policy.py`、`test_tool_attempt_coordinator.py` 與 `test_controller.py` 的 fake-cap／mode assertions；保留真正 `execution_count >= 1`、cancel、loop-break 保護。 |
| A1-03 | `turn.py` 的 `GUIDED_WORKFLOW`、`policy_mode`、guided factory、scope／terminal／excluded fields；固定回 single 的 `turn_scope.py`。 | 刪除／收旂 `test_turn_scope.py` 與 Guided-only request validation；保留 correlation、bounded text 與 single-turn admission evidence。 |
| A1-04 | `turn_orchestrator.py` 的 scope／terminal／excluded state 與 zero-caller `record_guided_repair()`；`controller.py` 的 scope bind／excluded rejection／Guided terminal branches；`assembler.py` 的 turn-policy bridge。 | 收旂 `test_turn_orchestrator.py`、`test_controller.py`、`test_controller_integration.py`、`test_context_assembler.py` 中直接注入 Guided／private state 的 clusters。 |
| A1-05 | `assistant_runtime_lifecycle.py` 的 scope／terminal／excluded admission transport；`assistant_command_dispatcher.py` 只做 request shape 直接依賴檢查。 | 收旂 `test_assistant_runtime_lifecycle_delivery.py` 的 dormant transport assertions；保留 delivery acknowledgement、watchdog、busy／cancel／shutdown。 |
| A1-06 | `agent_manager.py` 的 active-scope state、`_scope_summary_for_admission()`、`_with_active_scope()`；若全部 caller 消失，同步刪除 `ui/chat/presentation.py` 的 `scope_summary` 與 `ui/chat/panel.py` 的 scope row。 | 收旂 `test_agent_manager.py` 與 `test_chat_panel.py` 的 Guided／scope-copy assertions；以真實一般 request／progress／stop presentation 取代。 |
| A1-07 | 不刪 production owner；只評估 `test_controller.py`、`test_context_assembler.py` 中和 A1-02–06 同一 contract 的重複 mock／private-order tests。 | 先加強 `tests/integration/agent/test_product_flow.py`、`test_controller_lifecycle_faults.py` 與 receipt／stale publication 的 lower-mock evidence，再刪重複。 |

這七項是 A1 唯一有限輸入集。施工中新發現的 legacy／test smell 不自動納入 A1；最多作為三項
deferred follow-up 回報。必須保留的已知邊界是 ProcessRAGRetrieverLifecycle、injected RAG
test seam、`intent.py` 的 RAG no-action heuristic、strict parser／verifier／receipts／turn correlation，以及
AgentManager／RuntimeLifecycle／Dispatcher／LLMController／ApplicationService 的 owner 身分。

**Ownership and complexity**

- Owners before／after：AgentManager、RuntimeLifecycle、Dispatcher、LLMController、ApplicationService
  與現有 coordinators 不變；owner delta `0`。
- 不新增 module、public class、state machine、receipt 或 compatibility path。
- 預期 production `-330..-500 LOC`，tests `-500..-1000 LOC`；這是 complexity budget，不是為了
  達數字而刪 code 的驗收條件。
- 回滾點是同一 PR 的三個 coherent commits：orphan／no-op deletion、test evidence
  consolidation、Guided retirement。

**Focused validation and stop condition**

施工前後跑相同的 controller／context assembler／pending interaction／runtime lifecycle／product
flow baseline，再由 reviewer 以 classification matrix 將每個 Assistant scope／policy／compat marker 標成
`deleted`、`retained-real-caller`、`retained-security-evidence` 或 `explicitly-deferred`。只有零未分類
candidate、production 與 tests 都 net negative、owner 不增加，且上述 observable baseline 不變時
才 scope-complete。任一 public tool／side-effect 改變、需要新 owner 或無法強化證據時停在
checkpoint，不擴大重構。

### A2. Evaluator evidence contract cleanup

A1 完成並合併後才開始 A2。將模糊的 top-level `summary`、`precision_summary`、
`clarification_summary` 收旂為：

- `case_summaries.core`：50-case frozen core。
- `case_summaries.precision`：24-case no-action precision。
- `case_summaries.clarification`：7-case clarification。
- `case_summaries.total`：81-case inventory／completeness，不宣稱為單一 model accuracy。
- `candidate_gate`：獨立保留 raw model、Host safety、direct admission、product outcome 與
  overall gate，不將 gate pass 塞進任一 case denominator。

同一 PR 將 report `schema_version` 由 v11 提升為 v12，並遷移所有 repo consumers、tests、fixtures、
docs／walkthrough readers；不保留會再產生混淆的 legacy `summary`。Cases、scorer、thresholds、
generation policy、promotion gate 一律不變。Consumer migration test 必須對 v11 keys fail closed，
並對 v12 的各自 denominator／inventory／gate 作 exact assertions。
以同一 source 重生 artifact，除 schema path 外，每個 case outcome 與 gate 必須與 baseline 一致。

## Lane B — product correctness and training

Lane B 由同一 product implementer 串行；每個編號是獨立 branch／PR，上一個 merge 並重新從
`main` 建立下一個。B4／B5 共用 training command、option、snapshot、receipt、dialog 與 history
owners，禁止並行。

A1／B1 的預期 production／test files 不重疊，可作為初始雙線。若 Assistant evidence 需要修改
ApplicationService／Import publication，或 A2 需要修改 `docs/target/{agent,training}.md`，必須由 root
延後到對應 B1／B4／B5 merge 後，不讓 worker 自行並行解衝突。

### B1. Import review consistency

- 當 EEG 檔自帶 events／labels 且沒有 external carrier 時，刪除 Load Labels page 重複的
  black `No nearby label/event source detected` empty state，只保留一個 source-aware 說明。
- Review Metadata 已提供 subject 時不得顯示 missing-subject decision；完整顯式的 internal
  event selection、roles 與 class map 已通過 Recheck 時，不得再顯示 generic mapping-incomplete
  blocker。不完整、不一致或來源變更案例維持 fail closed。
- 不改 import source scope、label semantics、Review→Apply digest、rollback 或 parser／cache policy。

驗證需覆蓋 file／folder／BIDS，internal-only、external carrier、selected BIDS subject、complete／
incomplete mapping 與 Review 後替換 source；交付前跑 canonical source-diverse data gate。可見 UI 已取得
使用者修改授權，但仍需 exact-SHA Windows 手測。

### B2. Epoch anchor language

`Timing 719` 不是 duration／sample count／epoch window，而是 import 儲存的 event anchor。只調整
Epoch 上方的 presentation label：

- internal event：`Event anchor` / `Event onset`
- event-code：`Event anchor` / 實際 code，例如 `719`
- time-field：`Time field`
- interval：`Start field` / `Duration field`
- BIDS wording 保持既有 source-aware 表達

不改 `t_min`、`t_max`、event placement／selection 或 epoch execution。UI 文案修改已授權；需
layout variants capture、epoch context／runtime tests 與真實 internal／interval workflow 手測。

### B3. Global Warning severity-label cleanup

所有 `AlertSeverity.WARNING` modal 隱藏黃色的重複 `Warning` severity word，保留 icon、accent、
caller title、message 與 confirmation controls；Information／Error 不變。這是 shared presentation
修正，不在個別 caller 分別改 title。UI 修改已授權；需 shared modal tests／capture 與真實
Assistant + 3D VRAM conflict 手測，確認沒有重複 modal loop。

### B4. Class loss weighting

在 Training Settings 增加 target contract 已定義的 Off／Balanced／Custom；Off 為預設。權重只來自
當次 fold／repeat 的 training split class counts，只套用 training criterion；validation／test 不加權。
零 training-count class 必須在開始前 blocked。選擇與 resolved weights 必須進 option／snapshot／
run history／artifact 以便重現。Assistant 的 model-facing `configure_training` 維持零參數 GUI
handoff，不增加 weighting schema。
當前 reviewed dataset class map 是 Custom UI 的唯一 class-name／order source；configure 與 Start Training
都要重驗映射 generation。映射改變時既有 multipliers fail closed，不以位置或舊 class index 重用。
同一 shared TrainingOption 不得被動態 criterion 污染；resolved weighted CrossEntropyLoss 必須在取得
當次 train indices／labels 後以 record／fold-local 形式建立。

Focused evidence 要能證明 train-only counts、formula、criterion-only effect、validation／test isolation、
zero-count block、per-fold resolution、persistence 與 cancel／rollback；再跑 training source-diverse gate 與
Training Settings 手測。

### B5. Validation early stopping

只能在 B4 merge 後從新 `main` 建立。Training Settings 中預設 disabled；啟用後監控當次
validation checkpoint-selection metric（loss／accuracy／AUC），使用 absolute `min_delta` 與
`patience`。Last Epoch selection 或沒有 validation 時禁止啟用；undefined AUC 不計入 patience。
每個 repeat 獨立計數，early stop 是 successful terminal，不是 cancel。Best validation checkpoint 維持為
final evaluation、history 與 saliency 來源；test 不參與停止或 checkpoint selection。

現有 source 只在 `epoch == configured target` 時做 final evaluation，`TrainRecord.is_finished()` 也依賴
configured epoch。B5 因此必須在既有 owners 內一起收旂：`EpochRunner` 回報 validation monitor；
`TrainingPlanHolder` 在提前停止後仍 reload best 並走 final evaluation；`TrainRecord` 與 `is_finished()`
記錄 successful early-stop terminal；snapshot／checkpoint／history 保存 settings、observations 與 reason。
不得只在 epoch loop 加 `break`，也不新增第二個 training lifecycle owner。B5 開工前由 root 以這些
既有 files 做 complexity review；若預計超過 1,500 production LOC，先拆成「backend terminal／persistence」與
「Training Settings／presentation」兩個串行 PR，不申請大型例外。

Focused evidence 要覆蓋三種 metric direction／threshold、patience boundary、undefined AUC、per-repeat
reset、best-checkpoint reload、terminal reason、cancel 與 disabled equivalence；再跑 training source-diverse gate 與
Training Settings／history 手測。

## Progression, review, and merge gates

1. 起始 wave 只開 A1 與 B1，兩者都從 plan PR 合併後同一 exact `main` 建立。新增
   shared-file conflict 時由 root 串行，worker 不自行解決 scope overlap。
2. 每個 worker 先建 characterization／regression baseline，再施工。作者 focused tests 通過後 freeze
   exact head；非作者 user-simulator 交叉跑 user-like path，然後 independent reviewer 才能審查。
3. Reviewer finding 只有重現本 scope contract、直接 safety／data loss，或使證據無法支撐本次
   claim 時才 blocker；其他最多三項 follow-up，不擴大 diff。
4. 通過 review 後才跑 applicable canonical gates。Executable IDs、argv、timeout 與 artifact contract
   只讀 `scripts/dev/handoff_gate_spec.py`，不手寫弱化版。Artifact、tests、CI 與 review
   必須屬於同一 clean／explained SHA；source 改變即全部失效。
5. 可以在使用者離席時完成 code、focused validation、artifact inspection、PR 與 exact-head CI，
   並標示 `scope-complete, awaiting manual acceptance`。任一 product／UI／data／training behavior
   PR 不得自動 merge。
6. 使用者回來後的手測順序：Import → Assistant cleanup → Epoch → Warning → Class
   weighting → Early stopping。每個 PR 都需當前 exact SHA 的明確「手測通過」與「同意
   merge」，並記錄在 PR。純 docs／tests／CI／guidance 才可使用 repo exemption。

## Campaign stop condition

下列條件全部成立才能宣稱本 campaign 完成：

- A1 零未分類 Assistant cleanup candidate，所有保留 code 都有真 caller 或 security／evidence
  理由，production／test 均 net negative，owner delta `0`。
- A2 沒有 ambiguous legacy summary consumer，same-source case outcome／gate 未變。
- B1–B5 各自的 observable outcome、focused evidence、applicable source-diverse gate、exact-head CI、
  人工驗收與 merge approval 完成。
- 所有 merged／abandoned candidate 已有明確記錄；本機再次只留 `main`，root
  `settings.json` 未被 stage／commit／revert／overwrite，並提供最終 Git worktree／branch／SHA／status
  inventory。

若缺 fixture／model／CI／native environment、需要新 public contract／UI 決策、或觸發新 owner／
state machine／receipt，該 lane 立即停為 checkpoint 交回 root；不以「長時間自治」當成擴大
授權。
