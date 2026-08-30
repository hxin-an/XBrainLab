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

PR #74 已以 exact head `9b29f5c6799eea83758ae6906e68419858aa60f9` 通過使用者手測，並以
merge commit `60c53727ced15da910a24d341ab2bb67883633e8` 合併；A1 worktree 與本機／
遠端 task branch 已清理。PR #78 已將 A2 evaluator report contract v11→v12 以
exact head `1804217f5856aa3b658bc114a6194e065eb35c52` 合併，merge commit 為
`8e21de1175b3d0cc71ea1a0bc0331a9e54066ab2`；same-source 81-case outcome 與 gate 未變。

C1 candidate `82ad9545644d29a550a2b41202e7bab2379a0b88` 保留完整 SHA、scope、
SourceFileBoundary、rollback 與 label／event semantics，但 WSL 及 native Windows 都未達預先
定義的效能門檻；候選已關閉，沒有 PR，也不宣稱 Import 已加速。下一個 Import
optimization 必須從新的 Windows product-equivalent profile 另立 plan。

PR #75 的 B2 product candidate 已 freeze 於
`82c3e51cf705d9573f0f305a54ed28c649d50e67`；30 個 focused tests、33 個 async teardown tests、
9-state capture 與 independent review 通過。但 exact-head GitHub required check
`linux-integration-rest` 連續兩次在無 diff overlap 的 `assistant-runtime` domain 超過 1200 秒，
因此 B2 現在是 CI checkpoint，尚未可交付人工驗收。

本 campaign 要在不新增 workflow owner、不建立第二套 command／state truth 的前提下，交付：

1. 一份無混合分母、可人工閱讀的 Assistant evaluator report contract。
2. Epoch anchor 文案、全域 Warning 視覺去重複。
3. Training Settings 中已核准的 class loss weighting 與 validation early stopping。
4. 以 current-main 的 BIDS Review／Apply 實測為基礎，刪除重複 path resolution 並改善 Import latency。

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
- **Import performance implementer**：只擁有 Lane C 的 bounded PR；先量測再修改，不能弱化
  source scope、content digest、label／event semantics、rollback 或 cancellation。
- **Independent reviewer**：只審查 frozen exact SHA，檢查 scope、owner、observable behavior、
  test quality 與 claim。可以因可重現的 contract／lifecycle／evidence defect veto，不在被審
  branch 實作自己的 finding。
- **Cross user-simulator**：非作者 worker 用 product-equivalent scenario 交叉驗證。這只是第二層
  保險，不取代 exact-SHA Windows 真人手測。

現階段明確允許 `main + B2 frozen product worktree + G1 gate-repair worktree`，再加一個
ephemeral reviewer worktree。A2 與 C1 worktree 已收旗。G1 合併後先清理其 worktree，再將
B2 cleanly rebase 到新 `main`；不用 cherry-pick 將 gate 修復塞進 product branch。

## Lane A — comprehensive Assistant cleanup

### A2. Evaluator evidence contract cleanup (completed in PR #78)

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

## Gate repair G1 — Assistant runtime domain isolation

**Problem and evidence**

PR #75 old head `0803d84bdc4e184d5877a1a8aba4a1c274230d59` 與 rebased head
`82c3e51cf705d9573f0f305a54ed28c649d50e67` 的兩次 GitHub run，都在
`tests/integration/assistant_runtime` 的第一個 domain process 超過 1200 秒；前一次 log
顯示 16 個 forked Qt lifecycle cases 只產生 13 個 dots，其後所有 integration domains 皆完成。
B2 diff 與 Assistant runtime／test runner 為零 overlap。同一 exact B2 source 在 WSL 以 CI 環境旗標
連續 5 輪通過 80／80 cases，每輪約 12 秒；移除重複的 per-test fork 後同樣通過
16／16。直前 PR #78 的同一 required shard 可在 4m39s 成功，證據指向 GitHub Linux
hosted runner 上的間歇 Qt／`pytest-forked` process-exit lifecycle，不是 B2 defect。

**Outcome, scope, and non-goals**

- 保留 `scripts/dev/run_tests.py` 已有的每 domain owned process、`prlimit --core=0`、
  completion attestation、1200-second hard timeout、JUnit 與 coverage。
- 只對已有 dedicated `assistant-runtime` domain 停用內層 `pytest-forked` plugin，讓 16 個案例
  在該獨立子程序中共用一個 Qt event-loop lifecycle；直接執行 test file 的現有隔離仍保留。
- 不改產品碼、Assistant lifecycle semantics、test assertions、通過條件、skip policy 或 timeout；
  不加 rerun，也不為 CI 建立新 control plane。Owner delta `0`。UI 修改不適用。

**Repair, focused validation, and stop condition**

1. 先用 runner unit test 固定：只有 `assistant-runtime` shard argv 含 `-p no:forked`，其他
   shard argv、attestation expected args、JUnit／coverage 不變。
2. 跑 runner focused tests，並在 dedicated domain 中連續執行至少 5 輪 Assistant runtime tests；
   每輪必須 16／16，且 teardown assertions 不能弱化。
3. 非作者 test-quality reviewer 審 frozen SHA，確認這是移除重複 process boundary，不是
   隱藏 hang。推送 test／CI-only PR，exact-head required checks 必須全部 completed／success。
4. G1 若仍在同一 domain 超時，停為 checkpoint 並收集 per-test identification；不加長
   timeout。G1 成功則使用 tests／CI exemption 合併，清理 worktree，然後 rebase B2 並重跑
   exact-head evidence。

## Lane B — product correctness and training

Lane B 由同一 product implementer 串行；每個編號是獨立 branch／PR，上一個 merge 並重新從
`main` 建立下一個。B4／B5 共用 training command、option、snapshot、receipt、dialog 與 history
owners，禁止並行。

A2 evaluator scripts／docs、B2 Epoch UI 與 C1 Import backend 的預期 production／test files 不重疊。
若實際 diff 新增 shared ApplicationService、training owner 或同一 canonical doc，必須由 root 串行，
不讓 worker 自行並行解衝突。

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

## Lane C — BIDS Import latency

### C1. Reuse admitted canonical path identity (closed below threshold)

**Problem and evidence**

pre-plan baseline `67027a26292352ec77dbf2d846cf68d3a1c6983c` 的 canonical OpenNeuro
ds003061 P300 subject 001 workload（3 個 EEGLAB `.set`，約 182 MiB）在 WSL `/mnt/d`
以一次 warm-up、三次 measured pass 得到 blocking median `12.412s`：catalog `0.055s`、
Review `4.732s`、Apply `7.626s`、background idle `1.572s`。相同 production content-hash
implementation 單次完整 SHA-256 約 `0.32s`，Review 與 Apply 合計上限約 `0.64s`，不是主要
瓶頸。built-in cProfile 另顯示 Review／Apply 對已 admission paths 反覆執行
`Path.resolve()`／`stat()`／`lstat()` 是 dominant non-data cost；Catalog 已可忽略。

舊 `perf/windows-import-parallel-v1` 的 two-worker EEGLAB header preflight 在 native Windows
反而較 serial baseline 慢約 23%，且 cancellation／progress semantics 不完整，明確禁止 cherry-pick
或重做。PR #70 的過度 metadata-stability 防禦清理已在 main，不再重複施工。

**Outcome, scope, and non-goals**

- 從最新 plan merge commit 建立 `perf/import-path-identity-reuse-v1`，沿用既有
  `CanonicalPathIdentityScope`，讓 discovery／admission 已 canonicalize 的 selected EEG、BIDS
  sidecars 與 label carriers 在同一 Review／Apply operation 內以 scope lookup 重用。
- 只移除為 dictionary key、dedup、metadata／recipe projection 而重複觸發的 filesystem path
  resolution；真正的 resource admission、regular-file／scope check、byte count、完整 SHA-256、
  Review→Apply digest、SourceFileBoundary、cancel 與 rollback 全部保留。
- 不建立 global／persistent cache、worker pool、owner、receipt、compatibility path、public DTO 或
  production instrumentation；不改 MNE preload、資料載入順序、label／event semantics、UI 或文案。
- Owners before／after 都是既有 ApplicationService／DataInterpretationCommandService 與其 state／apply
  services；owner delta `0`。最多 8 個 production files，pure-refactor net production LOC 不得超過
  `+100`。若 Apply propagation 會超標，C1 只交付 Review reuse；Apply 必須另立後續串行 slice。

**Focused validation and stop condition**

1. 施工前後用同一 fixture、相同 environment、一次 warm-up 與三次 measured pass 比較 wall／CPU／
   RSS／I/O、Review／Apply／background median；先在本 planning PR merge 後的 exact main 重跑
   baseline，SHA 成本另列但不修改。若新 baseline 與 pre-plan `12.412s` 相符，WSL blocking median
   必須降至 `<=9.31s`；否則仍要求至少 25% 改善。
2. 目前 Windows 3.11 venv launcher 指向已移除的 Conda Python，system Python 3.12 又缺 MNE；在 repo
   外以 lockfile 建立 isolated Windows Python 3.12 environment，先量 exact-main，再量同一 C1 SHA。
   Windows 必須同時改善至少 15% 與 `0.25s`，且任何 phase 不得退步超過 10%；只有 WSL 改善不得
   宣稱產品加速或合併 C1。
3. Characterization／regression 覆蓋 admitted path reuse、out-of-scope／symlink／reparse rejection、
   file／folder／BIDS、review reopen、Review 後 source replacement、cancel 與 rollback；不得以 timing
   assertion 取代 observable contract。
4. canonical source-diverse data gate 必須維持 raw count、label apply、event timing／digest 與 recipe
   trace exact correctness。作者證據完成後，由非作者 performance＋data reviewer 審 frozen SHA，
   再交 exact-source 人工手測。

若 canonical path reuse 未達雙平台門檻，C1 停為 checkpoint 並關閉 candidate；不以更多 abstraction、
弱化 digest 或 broad loader parallelism 湊數。下一個 optimization 需依新的 measured profile 另立 plan。

## Progression, review, and merge gates

1. G1 先在 exact `8e21de11` main 上獨立修復 required-check lifecycle；合併並清理後，
   B2 才 rebase 到新 main、重生 capture／focused evidence 並觸發新 exact-head CI。
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
6. 使用者回來後的手測順序：BIDS Import latency → Epoch → Warning → Class weighting →
   Early stopping。每個 product PR 都需當前 exact SHA 的明確「手測通過」與「同意
   merge」，並記錄在 PR。純 docs／tests／CI／guidance 才可使用 repo exemption。

## Campaign stop condition

下列條件全部成立才能宣稱本 campaign 完成：

- G1 已在不跳過案例、不加長 timeout 的情況下讓 exact-head required CI 穩定通過。
- B2–B5 各自的 observable outcome、focused evidence、applicable source-diverse gate、exact-head CI、
  人工驗收與 merge approval 完成。
- A2 與 C1 的已記錄 outcome 不被後續 branch 逆轉；不將 C1 關閉候選宣稱為產品加速。
- 所有 merged／abandoned candidate 已有明確記錄；本機再次只留 `main`，root
  `settings.json` 未被 stage／commit／revert／overwrite，並提供最終 Git worktree／branch／SHA／status
  inventory。

若缺 fixture／model／CI／native environment、需要新 public contract／UI 決策、或觸發新 owner／
state machine／receipt，該 lane 立即停為 checkpoint 交回 root；不以「長時間自治」當成擴大
授權。
