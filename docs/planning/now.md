# XBrainLab Now

最後更新：`2026-08-31`

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

PR #79 已在不跳過測試、不增加 timeout 的前提下修復 `assistant-runtime` shard 的重複
process isolation，並以 merge commit `65d5957947eae8c20be9b9c91efae468c4779bcd`
合併。B2 後續在同一 branch 收斂單一 raw event anchor 與重複 suggestion presentation；使用者已於
`2026-08-30` 對 exact head `2cb82134a3973c7e322508e77d672c050a1aa25c` 完成手測並同意
merge。PR #75 已以 merge commit `c7cf4b831c3a7579ee99a23b1a41c65251fa0c57` 合併，B2
worktree 與本機／遠端 task branch 已清理；Lane B 當時進入 B3。

PR #82 已將 C2 product-equivalent Import profiler 以 exact head
`faf86c8772d48674ab02936fa444dad4ed49f38d` 合併，merge commit 為
`d36cfdee21b82084094757b369c3b9ab6c4fb677`。它只修改 dev tooling／tests，沒有產品行為
變更；C2 task worktree 與本機／遠端 branch 已清理。Exact Windows／WSL report 與 teacher gate
證據保存在 ignored `build/dev-artifacts/import-e2e/faf86c87/`。

PR #81 已以 exact head `d32eb4dfe438fecf9c12875d04cbe6360b24b4eb` 通過使用者手測，並以 merge commit
`13532b817d230283dcbe2b92cdf2bcacc28c5333` 合併 B3 Warning severity-label cleanup。PR #83
已以 exact head `0159383990b1b0219a66113a57e262b5624225c4` 通過使用者手測與所有 non-skipped
checks，並以 merge commit `c57cee24ceb10c826ac7716bf2df63b1ab8f4b2e` 合併 B4 class loss
weighting。Lane B 下一個 active slice 是 B5；B6 只保留為 B5 後的 candidate。

本 campaign 要在不新增 workflow owner、不建立第二套 command／state truth 的前提下，交付：

1. 保留已完成的 Assistant evaluator report contract；沒有新 hypothesis 時暫停 Lane A。
2. 保留已完成的 Epoch import setup、Warning presentation 與 class loss weighting outcome。
3. 在既有 training lifecycle 內完成 validation early stopping；更進階的 bounded training search
   只能在 B5 合併後另作 target decision。
4. 保留 C4 已完成的 bounded negative result：P300 Apply 沒有同一 request 內可安全刪除的重複
   Raw load、完整 sample materialization 或 label decode；不為了湊加速擴張 profiler／validator
   framework 或修改產品。

本次 plan calibration 合併後，B5 與 C4 已從 exact
`fb752a5a3c810b249576b28f6e18baec38c81c16` 分別建立；任何舊 baseline 或 abandoned C3
candidate 都沒有作為 product branch base。C4 維持零 product diff，B5 繼續施工。

## Roles and worktree control

- **Root coordinator**：唯一能修改本 plan、canonical target／decision、worktree ledger、PR
  base／head、CI／manual record 與 merge state 的角色。Root 做邊界與證據審核，不用自評
  取代 worker 或 reviewer。
- **Assistant implementer**：一次只擁有 Lane A 的一個 bounded PR；不修改 product lane，
  不自行 merge 或宣稱 handoff-ready。
- **Training implementer**：只擁有 B5；重用既有 training owners，不同時施工 B6，也不修改
  Import workflow。
- **Import performance implementer**：只擁有 C4；先用既有 C2 baseline 做一次 bounded direct
  audit，只有發現同 request 的可刪除重複工作才修改產品。不能弱化 source scope、content digest、
  label／event semantics、rollback 或 cancellation。
- **Independent reviewer**：只審查 frozen exact SHA，檢查 scope、owner、observable behavior、
  test quality 與 claim。可以因可重現的 contract／lifecycle／evidence defect veto，不在被審
  branch 實作自己的 finding。

本 plan 合併並完成舊資源清理後，允許 `main + B5 worktree + C4 worktree`，以及在 frozen exact
SHA 後使用一個 ephemeral reviewer slot。每條 lane 只配置一位作者與一位獨立 reviewer；不再派
額外 user-simulator 重複同一維度。B5 與 C4 預期不重疊；若實際碰到同一 production owner，root
立即改為串行。Root 是唯一能修改本 plan 與處理 rebase／status reconciliation 的角色。

## Lane A — comprehensive Assistant cleanup

Lane A 暫停。A1 cleanup 與 A2 evaluator evidence contract 已完成；same-source evaluator gate 仍為
false，但目前沒有新的 product defect 或可驗證 improvement hypothesis。不得為了維持施工而再改
prompt、scorer 或 model。只有出現可重現產品失敗、新模型候選，或能對 frozen evaluator 定義明確
before／after outcome 時才重新立 plan。

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

## Gate repair G1 — completed in PR #79

G1 已完成並合併。它只移除 dedicated `assistant-runtime` domain 內重複的 nested
`pytest-forked`，保留 owned domain process、16 個案例、teardown assertions、hard timeout、JUnit、
coverage 與 completion attestation。後續 lane 不再重開這個 scope。

## Gate repair G2 — completed in PR #88

G2 已在 exact head `e61a0c6452e4e084b7049cc9724298827f7bdf3b` 完成，並以 merge commit
`b1d84e096e1374125a358f1cd75f24c9deaba450` 進入 `main`。Basedpyright 維持鎖定 `1.39.2`，
zero-debt baseline 的 source origin 是 `dace4e7324eea80d296ebcabd67b8d6fb8c40935`；canonical gate
必須同時維持 baseline `0`、observed `0`，且不以 suppression、exclude 或 config 放寬換取通過。
後續 clean PR 只需維持 zero gate，不因 source SHA 改變而重寫這個歷史 baseline origin。B5 已 rebase
到上述 merge commit，仍須以自己的 exact final SHA 通過 gates 與 Windows manual acceptance。

## Lane B — product correctness and training

Lane B 的 B1–B4 已完成。B5 必須從 PR #83 merge 後且包含本次 plan calibration 的 exact `main`
建立；它仍使用既有 training command、option、snapshot、dialog 與 history owners。B6 不與 B5
並行，也不為 future search 預建 owner、database 或 scheduler。

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

### B2. Epoch imported-event presentation (completed in PR #75)

單一 `719`／`769` 是 placement anchor，不是多 class 清單；Apply 後 runtime event ID 也可能被重映射。
PR #75 只收斂 Epoch 上方 presentation：

- 非 BIDS title 使用 `Imported event setup`，成功 handoff 不再顯示 `Suggested from ...` summary；
  mismatch／blocker／unavailable summary 保留。
- internal event、event-code、EEG-event 不顯示 `Event anchor`、`Epoch anchor` 或任何新增 raw code；
  只顯示 `Source`、`Placement` 與必要的 `Label field`。
- time-field 保留 `Time field`；interval 保留 `Start field`／`Duration field`。
- BIDS 保留既有 source-aware title、`Label field` 與 `Window mode`，移除非操作性的
  `Epoch anchor / Event onset`。
- Events table 仍是所有實際 class event 的選取入口；raw provenance 留在 Import Review。

不改 context DTO、`t_min`、`t_max`、event placement／selection、recipe 或 epoch execution。先加會對
舊 presentation 失敗的 observable tests，再做最小修正。需 normal／narrow capture、真實 multi-class
GDF 與 BIDS／interval walkthrough、source-diverse gate、independent review 及 exact-SHA manual acceptance。

### B3. Global Warning severity-label cleanup (completed in PR #81)

所有 `AlertSeverity.WARNING` modal 隱藏黃色的重複 `Warning` severity word，保留 icon、accent、
caller title、message 與 confirmation controls；Information／Error 不變。這是 shared presentation
修正，不在個別 caller 分別改 title。UI 修改已授權；需 shared modal tests／capture 與真實
Assistant + 3D VRAM conflict 手測，確認沒有重複 modal loop。

PR #81 已完成 exact-head tests／capture／CI 與使用者手測，後續 lane 不再重開這個 scope。

### B4. Class loss weighting (completed in PR #83)

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

上述 contract 已在 exact head `0159383990b1b0219a66113a57e262b5624225c4` 通過 independent
review、canonical UI／source-diverse／CUDA evidence、所有 non-skipped CI 與使用者手測，並以 merge
commit `c57cee24ceb10c826ac7716bf2df63b1ab8f4b2e` 進入 `main`。B5 必須保留這些語意。

### B5. Validation early stopping

只能在 B4 merge 後且包含本 execution calibration 的新 `main` 建立。Training Settings 在既有
`Evaluation` 下加入 `Early stopping`、`Patience` 與 `Minimum improvement`；預設分別為 disabled、
`3`、`0`。`patience` 必須是正整數，absolute `min_delta` 必須是有限非負數。UI 不增加第二個 metric
選單：Best validation loss／performance／AUC 分別以 validation loss／accuracy／AUC 作 monitor；Last Epoch
或無法證明 validation split 有樣本時禁止啟用。UI 只作 presentation，configure 與實際 Start boundary
都要由 backend 重驗。使用者已在本輪規劃中確認上述 layout／default／History outcome，且後續明確要求
實作本 plan，故 UI authorization 已取得。

Early-stop monitor 使用 strict improvement：loss 必須下降超過 `min_delta`，accuracy／AUC 必須上升超過
`min_delta`；相等不重設 patience。第一個 finite observation 建立 monitor baseline。AUC `None` 不增加也
不重設 counter；若全程都 undefined，跑滿 configured epochs 後沿用既有 selected-checkpoint-unavailable
失敗，不 fallback。既有 `TrainRecord._update_validation_metrics()` 的 checkpoint tie semantics 保持不變：
loss 的 `<=` 與 accuracy／AUC 的 `>=` 仍可讓較晚的 tie 成為 selected checkpoint；History 顯示實際
selected checkpoint epoch，不把它誤稱為 strict monitor first-best。

每個 `TrainRecord` 自有 monitor／counter／terminal evidence；某 repeat early stop 後仍 final-evaluate，
再依序執行後續 repeats，下一 repeat 從空 state 開始。Interrupt 在 batch／epoch boundary 被觀察到時優先
成為 Cancelled，不得被 early stop 覆寫。Early stop 是 successful completion；`TrainingPlanHolder` 仍以
既有 Evaluation option reload selected validation checkpoint，再對 final split 評估。Test 不參與停止或
checkpoint selection。B4 train-only weighting 不變：monitor 只讀既有 unweighted validation result。

不修改 `EpochRunner`：它已把 validation result 寫入 `TrainRecord`，`TrainingPlanHolder` 只需在每輪完成後
讀取 record-owned observation。現有 `epoch == configured target` final-evaluation boundary 與
`TrainRecord.is_finished()` 要共同接受 successful early stop；不得只在 loop 加 `break`。Trainer terminal
仍為 `COMPLETED`。Training History 顯示 `Completed early`，detail 包含 completed／configured epochs、
monitor、patience 與以 1 起算的 selected checkpoint epoch。

`ConfigureTrainingCommand`、`TrainingOption`、state snapshot 與 dialog round-trip 保存三個設定；Assistant
model-facing `configure_training` 維持零參數 GUI handoff。Training record schema 升為 v3，嚴格保存
early-stop request／result；真實 v1／v2 artifact 明確遷移為 disabled／not-stopped，未知或缺損 v3 fail
closed。既有 v1／v2 reader 的移除仍需另立 artifact-support decision。Saliency producer identity 納入設定，
實際 selected state fingerprint 仍是模型來源真相。

Owners before／after 都是既有 TrainingOption／TrainRecord／TrainingPlanHolder／Trainer 與 application／UI
projection，owner delta `0`。預計最多 11 個既有 production files、net `+450 LOC`；不新增 production
module／public class／owner。超標即停止並先做 deletion／reuse review，不自動建立第二套 lifecycle 或
future B6 abstraction。

Focused evidence 要覆蓋三種 metric direction、strict threshold／tie distinction、patience exact boundary、
undefined AUC、per-repeat reset／continuation、cancel priority、best-checkpoint reload、successful terminal、
v1／v2→v3、snapshot reopen、History presentation、disabled equivalence 與 B4 validation isolation；再跑
Training Settings capture、training source-diverse gate 與 exact-SHA Windows 手測。

本輪 CI blocker repair 已完成：兩個既有 backend snapshot assertion 納入三個 default；Training Settings 在
150% 且內容超過高度上限時，必須以 native vertical scrollbar 寬度預留 dialog 寬度，避免 viewport 吃掉
input column。focused validation 包含 13-row capture（明確三個 new labels）及既有 inflated-native-combo
strict guard。後續 G2 已合併全域零診斷 gate；B5 rebase 後必須維持 Basedpyright baseline `0`、
observed `0`。

### B6 candidate. Bounded training search (not active)

B6 只在 B5 合併與手測後進行 target discussion，不屬於本輪 active implementation。候選方向是讓
使用者以固定的小型 trial／time budget 搜尋少量既有 TrainingOption 參數；搜尋 metric、參數集合、
budget、cancel／resume 與可見結果必須先形成 public target。不得預先恢復 archived Optuna／SQLite
設計，不新增 search database、parallel training owner、scheduler 或第二套 trial state。若既有
training lifecycle 無法以一個 direct collaborator 表達，B6 在 planning 階段停止。

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

### C2. Windows-first product-equivalent Import profile (completed in PR #82)

**Problem and evidence**

現有 `teacher-dataset-import-performance` 只量同步 ApplicationService 的 catalog／review／apply／
background idle；`import-loading-profile` 只量 fresh-service command lifecycle；Dataset latency unit tests
則固定 cold module-import boundary。沒有 artifact 從真 Qt `Import Data`、chooser、worker queue、loading
surface、wizard review、Apply 到 Dataset publication ready 分解使用者等待。C1 已量得完整 SHA-256 每次
約 `0.32s`、Review＋Apply 上限約 `0.64s`，且 path identity candidate 在 native Windows 只改善約
`0.738%`／`9ms`；不得再預設 SHA 或 path 是主因。

**Outcome, scope, and non-goals**

- 建立 `perf/import-e2e-profile-v1`，只修改 dev tooling、tests 與本 plan；透過真 Qt wizard、既有
  ApplicationService command spine 與 visible controls 執行，不新增 production telemetry／hook／owner。
- dev-only tracer 在 runtime 外部記錄 Import click→chooser、chooser accept→operation allocation／start、
  catalog／scan／review→wizard ready、re-preview／validate、Apply→raw load／label／metadata／identity verify／
  commit、Dataset publication ready 與 background idle。另記錄 wall／CPU／peak RSS／process I/O、Qt
  heartbeat、cancel delivery 與 tracer overhead。
- 固定三個主要 workload：BBCI GDF single file internal events、A01T–A03T GDF＋MAT folder、OpenNeuro
  ds003061 P300 subject 001 三 run BIDS；小型 MNE-BIDS 只作控制組。
- Windows native 是產品結論來源；WSL 只作 baseline。每個 workload 記錄 first fresh-process diagnostic，
  再做一次 warm-up 與三次 measured fresh-app passes；OS page cache 不宣稱為真正 cold cache。
- Artifact 寫到 ignored `build/dev-artifacts/import-e2e/<exact-SHA>/` JSON＋Markdown，只保存 fixture role／
  count／bytes，不保存使用者 absolute path。
- 不修改 loader、cache、worker pool、SHA、scope、SourceFileBoundary、Review→Apply digest、rollback、
  cancellation、label／event semantics 或 UI copy。

**Correctness, decision, and stop condition**

每次 timed Apply 同時核對 raw count、event `(sample, label)` digest、label apply、recipe/content identity、
BIDS channel／electrode metadata 與 Dataset-ready publication；source replacement、cancel 與 rollback 另以
non-timed case 證明。非作者 performance＋data reviewer 審 frozen exact SHA 與 artifact。

若同一 Windows phase 三輪都佔 total 至少 35%，且 deletion／reuse intervention 能留在既有 owner、最多
8 個 production files、pure-refactor net `+100 LOC` 內，才從 exact main 另開 bounded optimization。
候選需讓 Windows total median 同時改善至少 15% 與 0.25 秒、target phase 至少改善 15%，且任何其他
phase 不得退步超過 10%。若無 reproducible dominant cost，或修理需要新 cache／pool／owner／state／
semantic trade-off，C2 以 ranked diagnostic checkpoint 結束，不繼續猜測。

Exact Windows report 的 stable medians 為 BBCI `1.601s`、Graz folder `1.940s`、P300 BIDS
`4.096s`。BBCI／Graz 的 Review 分別佔 `68.2%`／`61.5%`；P300 Apply 為 `2.484s`，佔
`60.8%`。Windows source identity 約 `0.001s`，final identity verify 約 `0.087s`；Qt heartbeat
max median 約 `0.12–0.20s`。因此 C2 已交付 ranked timing report，但沒有證據支持刪 SHA／path
boundary、增加 worker，或直接宣稱產品已加速；後續調查因此只限 P300 Apply 的可刪除重複工作。

### C3. Detailed Apply tracer (abandoned before product measurement)

C3 candidate 在 production `0` files 的前提下，將既有 profiler／tests 擴張約 `+1327/-151`，並把
主要時間投入 trace identity、strict validator 與 native environment proof。它雖修正了已重現的
evidence ambiguity，但沒有完成 Windows P300 measurement，也沒有改善 Import latency；繼續投入的
成本已高於本輪產品目標。Candidate exact `2674192125209fc928b93790a65f8225213df8fa`
沒有 PR、不得 merge，相關 isolated clone／venv 與 branch 在 C4 開工前按 exact target 清理。

後續不得把 C3 code、artifact schema 或 environment framework 當成 C4 的必要前置；C2 的 Windows
product-equivalent timing 已足以把調查範圍限定在 P300 Apply。

### C4. Direct P300 Apply de-duplication (closed: no bounded safe candidate)

作者在 exact clean base `fb752a5a3c810b249576b28f6e18baec38c81c16` 對同一 OpenNeuro
P300 subject 001 三個 selected runs 做 repo 外、執行後刪除的 application-seam call-count：
`RawDataLoaderFactory.load = 3`、`AdmittedLabelResourceSession.load = 3`、
`BaseRaw.load_data = 0`、`BaseRaw.get_data = 0`。也就是每個 distinct EEG 與 event carrier 各
load 一次，沒有 application-level 完整 sample materialization。Static trace 亦證明
`prepare_replacement_import()` 載入後，detached interpretation 與 commit 重用同一批 prepared Raw。

非作者 reviewer 在相同 frozen SHA 核對 BIDS unique projection、selected-resource scan、Apply label
loop 與 prepared commit，沒有發現同 canonical path／parser config／request 的重複工作。因此 C4
依既定 stop condition 以零 product diff 關閉；不新增 cache、worker、state、測試或 profiler
framework。暫存 script、fixture symlink 與 result directory 已移除。

本 session 的 Windows interop 在 command dispatch 前以
`WSL ERROR: UtilBindVsockAnyPort:307` 失敗，所以沒有取得 current-source Windows warm-up＋三輪
before。既有 native Windows artifact 缺 exact source／fixture identity，且不是 current real-Qt
`--p300-once` path，不能代替本輪 baseline。這限制任何 current Windows timing、before／after 或
產品加速宣稱，但不會把已證明不存在的 application-level duplicate 變成安全候選。

**Problem and outcome**

C2 已證明 P300 Apply median 為 `2.484s / 4.096s`（`60.8%`）。本輪 static audit 顯示 selected EEG
目前只在 `DatasetStateService.prepare_replacement_import()` 各 load 一次，commit 重用同一批 prepared
Raw；source 尚未證明 duplicate。C4 因此只沿用 C2 exact Windows OpenNeuro P300 fixture 與既有
`--p300-once` 路徑，先做一次 warm-up 與三次 measured before，再用一個 repo 外、執行後刪除且不提交的
call-count／cProfile 確認實際 invocation。若沒有同 canonical resource、同 parser config、同 request 的
重複 application-level Raw load、完整 sample materialization 或 label decode，C4 以
`no bounded safe candidate` 結束，不再增建 profiler。

**Implementation ceiling**

- 只有直接證據成立，且 duplicate 的可移除 cumulative cost 足以支持門檻時才修改產品；優先刪除
  第二次 load／materialization，或重用既有 request-local prepared object。
- 最多 2 個 production files，owner delta `0`，net production 不超過 `+80 LOC`；不得新增 cache、
  worker、state machine、receipt、persistent telemetry、artifact schema 或 compatibility path。
- regular-file／scope、byte count、完整 reviewed-content SHA-256、Review→Apply digest、final identity
  verify、SourceFileBoundary、atomic replacement、rollback、cancel 與 label／event semantics全部保留。
- header admission→lazy sample read、完整 SHA／final verify、SourceFileBoundary、stat／metadata projection
  與 MNE 內部必要 IO 不算 duplicate，不以弱化它們湊加速。
- 需要第三個 production file、跨 request state，或只能靠弱化上述 invariant 加速時立即停止。

**Validation and stop condition**

對 frozen candidate 使用相同 Windows environment、fixture、fresh-process command，再做一次 warm-up 與
三次 measured after；只比較既有 product-equivalent Apply／total timing，不建立新 report contract。
Apply median 必須同時改善 `0.25s` 與 `10%`，total median 必須同時改善 `0.20s` 與 `5%`，其他 phase
不得退步超過 `10%`；三輪 correctness identity 都必須一致。另維持 raw count、BIDS metadata、event
sample／label digest、recipe／content identity、source replacement、cancel 與 rollback。Focused observable
tests、canonical source-diverse Import gate、independent performance＋data review 與 exact-SHA Windows
手測仍必須通過。未達門檻即撤回 product diff；沒有 product diff 時只以 canonical docs 記錄 bounded
negative result，不要求 manual acceptance。

## Progression, review, and merge gates

1. B3、B4 與 C2 已完成；C3 已放棄且不得 merge。B5 與 C4 已從同一 exact `main` 建立互不重疊
   worktree；C4 已依 negative-result stop condition 關閉，B5 繼續施工，B6 維持 not active。
2. C4 的作者 call-count 與非作者 review 已完成，沒有 product diff 或人工驗收需求。B5 仍由單一
   worker 建 deterministic lifecycle evidence，focused tests 通過後 freeze exact head，再由一位非作者
   reviewer 審查；不新增重複 user-simulator role。
3. Reviewer finding 只有重現本 scope contract、直接 safety／data loss，或使證據無法支撐本次
   claim 時才 blocker；其他最多三項 follow-up，不擴大 diff。
4. 通過 review 後才跑 applicable canonical gates。Executable IDs、argv、timeout 與 artifact contract
   只讀 `scripts/dev/handoff_gate_spec.py`，不手寫弱化版。Artifact、tests、CI 與 review
   必須屬於同一 clean／explained SHA；source 改變即全部失效。
5. 可以在使用者離席時完成 code、focused validation、artifact inspection、PR 與 exact-head CI，
   並標示 `scope-complete, awaiting manual acceptance`。任一 product／UI／data／training behavior
   PR 不得自動 merge。
6. B5 與任何 C4 product diff 都各自需要同一 exact SHA 的 Windows manual acceptance 與 merge
   同意。若其中一條先 merge，另一條在交付手測前必須對最新 `main` 做 base reconciliation；source
   改變即重跑適用證據。

## Campaign stop condition

下列條件全部成立才能宣稱本 campaign 完成：

- G1 的已合併 evidence 不被後續 branch 逆轉。
- B2–B5 各自的 observable outcome、focused evidence、applicable source-diverse gate、exact-head CI、
  人工驗收與 merge approval 完成；B6 是否啟動屬於下一輪決策。
- A2、C1 與 C2 的已記錄 outcome 不被後續 branch 逆轉；C3 保持 abandoned／unmerged。C4 必須交付
  一個通過 before／after 門檻的 bounded product improvement，或明確的 no-safe-candidate 結論；不得把
  必要 materialization、C1 關閉候選或 WSL-only improvement 宣稱為產品加速。
- 所有 merged／abandoned candidate 已有明確記錄；本機再次只留 `main`，root
  `settings.json` 未被 stage／commit／revert／overwrite，並提供最終 Git worktree／branch／SHA／status
  inventory。

若缺 fixture／model／CI／native environment、需要新 public contract／UI 決策、或觸發新 owner／
state machine／receipt，該 lane 立即停為 checkpoint 交回 root；不以「長時間自治」當成擴大
授權。
