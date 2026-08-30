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

PR #79 已在不跳過測試、不增加 timeout 的前提下修復 `assistant-runtime` shard 的重複
process isolation，並以 merge commit `65d5957947eae8c20be9b9c91efae468c4779bcd`
合併。B2 已 rebase 並 freeze 於 `a121cebb787d62fa54d3b91696917088b876fdeb`；
exact-head CI 與 independent review 通過，但使用者檢查發現單一 raw event anchor 會被誤讀為
class 清單，且 `Suggested from import`／`Suggested from loaded label files` 重複。PR #75 尚未
通過 manual acceptance，必須在同一 branch 收斂 presentation 後重生所有 exact-source evidence。

本 campaign 要在不新增 workflow owner、不建立第二套 command／state truth 的前提下，交付：

1. 保留已完成的 Assistant evaluator report contract；沒有新 hypothesis 時暫停 Lane A。
2. 收斂 Epoch import setup presentation，再依序完成全域 Warning 視覺去重複。
3. Training Settings 中已核准的 class loss weighting 與 validation early stopping。
4. 以 Windows product-equivalent GUI workflow 重新建立完整 Import 時間帳；只有 measured dominant
   cost 達門檻後才另開 bounded optimization，不延續 C1 的 path／SHA 猜測。

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

現階段明確允許 `main + B2 product worktree + C2 Import profiling worktree`，再加一個
ephemeral reviewer worktree。A2、C1 與 G1 worktree 已收旗；B3／B4／B5 不預先建立空 branch。
Root 是唯一能修改本 plan 與處理兩條 branch rebase／status reconciliation 的角色。

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

### B2. Epoch imported-event presentation

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

### C2. Windows-first product-equivalent Import profile

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

## Progression, review, and merge gates

1. B2 與 C2 可在 production files 不重疊的兩個 worktree 並行；B2 仍留在 PR #75，C2 從 exact main
   建立。B3 只有 B2 merge／cleanup 後才建立；B4／B5 依序串行。
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
6. B2 手測完成後依序為 Warning → Class weighting → Early stopping。C2 profiling 若始終只有
   scripts／tests／docs，可使用 repo exemption；後續任何 production optimization 都需同一 exact SHA 的
   Windows manual acceptance 與 merge 同意。

## Campaign stop condition

下列條件全部成立才能宣稱本 campaign 完成：

- G1 的已合併 evidence 不被後續 branch 逆轉。
- B2–B5 各自的 observable outcome、focused evidence、applicable source-diverse gate、exact-head CI、
  人工驗收與 merge approval 完成。
- A2 與 C1 的已記錄 outcome 不被後續 branch 逆轉；C2 交付 Windows-first ranked timing report，且
  不將 C1 關閉候選或 WSL-only improvement 宣稱為產品加速。
- 所有 merged／abandoned candidate 已有明確記錄；本機再次只留 `main`，root
  `settings.json` 未被 stage／commit／revert／overwrite，並提供最終 Git worktree／branch／SHA／status
  inventory。

若缺 fixture／model／CI／native environment、需要新 public contract／UI 決策、或觸發新 owner／
state machine／receipt，該 lane 立即停為 checkpoint 交回 root；不以「長時間自治」當成擴大
授權。
