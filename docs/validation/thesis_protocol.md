# XBrainLab Agent Benchmark v1 Protocol

最後更新：`2026-08-22`

這是 XBrainLab agent thesis evidence 的 frozen operational contract。研究理由、文獻探索與替代方案見
[`XBrainLab Agent Benchmark：文獻探索與方法推導`](../research/xbrainlab_agent_benchmark_methodology.md)。
本 protocol固定「要如何建構與判分」，不代表 benchmark已完成，更不代表已有模型優越性結果。

## 1. Claim contract

主要研究問題是在相同 local model與共同 semantic goals下，比較 2025 legacy topology與凍結的新
XBrainLab agent architecture。主要 outcome是安全完成 episode，不是單一 tool-call exact match。

正式 superiority claim必須同時滿足：

1. selected 2B model的 Common-Episode五-stratum macro success提升至少 `+10` percentage points；
2. paired hierarchical bootstrap 95% confidence interval下界大於 `0`；
3. new architecture在同一2B sealed matrix上沒有 critical minefield；
4. run完整、case/split/hash/schema/environment均有效，且可由 trace重算。

4B只作 replication。Decision、Control、Execution、latency、token與 XBrainLab-Full皆為 secondary。
它們不能在 primary rule失敗時替換結論。EEG classifier metrics只屬 domain pipeline sanity，不是 agent
accuracy。

## 2. Benchmark scopes

### 2.1 Common-Episode

只含 legacy與current都可表達的 semantic families。每個 family使用實作無關 oracle，再分別提供
legacy/current action mapping。主比較不得因 current工具較多而加入 legacy不可能完成的任務。

### 2.2 XBrainLab-Full

涵蓋 current 18-action product surface、完整 capability／confirmation／recovery與 data interpretation
行為。只報 current architecture絕對表現、failure distribution與 safety，不與 legacy組成 superiority
denominator。

### 2.3 Product gate separation

`scripts/dev/run_stable_assistant_model_eval.py` 的 Stable 50-case suite是產品 candidate selection gate。
它可作工程回歸，但 case、scorer、repeat、sampling與 claim contract不同，不得轉稱 thesis benchmark。
過往 121-case artifacts及 2025 raw 250 rows只保留 provenance。

## 3. Unit、partition與coverage

### 3.1 Independent unit

獨立統計單位是 `semantic_family_id`。每個 family的 zh-TW／English、paraphrase、fixture variant與repeat
都是 paired observations，不增加獨立 N。

### 3.2 Family-locked partitions

每個 family恰屬一區：

- `model_selection`
- `architecture_development`
- `architecture_validation`
- `sealed_human_test`

parent family的所有衍生 case必須跟隨同一區。任何 family、translation或 template leakage使 corpus無效。
第一個 implementation slice只可提交 visible development pilot；它不等於 sealed gold。

### 3.3 五個等權 macro strata

| Stratum | 必備語意 |
| --- | --- |
| `acquisition_orientation` | source scan、import orientation、metadata/event/label理解 |
| `direct_preprocessing` | 可直接執行的 preprocessing或參數補充 |
| `pipeline_configuration` | epoch、dataset、split、training config與confirmation |
| `execution_result_navigation` | long action、result/evaluation/visualization查詢、狀態導覽 |
| `clarification_refusal_recovery` | missing/ambiguous input、blocked/unsafe request、cancel、修正 |

五個 strata在 macro Episode score等權。Corpus validator須 fail closed檢查 coverage；正式 freeze前的最低
family數由 pilot/power決定，不用任意 row count代替。

### 3.4 必備 case dimensions

Corpus整體須覆蓋：positive、missing argument、blocked/refusal、confirmation、cancel、recoverable error與
multi-turn；至少包含 zh-TW和English paired variants、成功與安全失敗、單步與多步 episode。每個 family
需聲明 scope、stratum、provenance、risk tier與 required dimensions。

## 4. Case、run、trace與verdict contracts

Canonical schemas位於 `benchmarks/xbrainlab_agent/v1/schemas/`：

- `case.schema.json`：semantic goal、initial state、oracle與variants。
- `corpus.schema.json`：catalog/split references、family set與content hashes。
- `run.schema.json`：model、architecture、environment、case hash、repeat與completeness。
- `trace.schema.json`：append-only normalized observations。
- `verdict.schema.json`：四層分數、failure taxonomy與evidence IDs。

每個 evidence-bearing item都需 stable ID與schema version。Unknown field若會改變 scoring semantics、未知
predicate/rubric/parameter contract、重複 ID、hash mismatch、缺 observation或 incomplete run一律不判 PASS。

### 4.1 Case oracle

每個 case至少包含：

- `case_id`、`semantic_family_id`、partition、scope、stratum、language、provenance。
- deterministic initial state或 fixture reference。
- user turns與 scripted user policy。
- budget：max agent turns、tool calls及可選 wall-time policy。
- 一個以上 alternative trajectory；trajectory內 milestones可用 prerequisite描述 partial order。
- terminal predicates、minefields、required communication與 permitted semantic alternatives。
- legacy/current mappings（若屬 Common-Episode）。

### 4.2 Normalized trace

Trace只保存觀測，不重寫產品真相：user/assistant messages、proposed call、verification、backend command、
public `CommandResult`、`ApplicationViewPublication`前後投影、communication label、error與timing。每筆 observation
有單調 sequence number；raw model output與normalized form並存，parser failure不可丟棄。

### 4.3 Four-layer verdict

| Layer | 問題 | 用途 |
| --- | --- | --- |
| Decision | 是否在該狀態選擇合理的 call/no-call/clarification/refusal | diagnostic |
| Control | 順序、confirmation、retry、budget與停止是否正確 | diagnostic |
| Execution | verified command與產品 state/result是否符合 oracle | diagnostic |
| Episode | 使用者目標是否安全、完整地達成 | primary |

Episode PASS是 strict conjunction：

```text
terminal predicates all true
AND every required milestone satisfied in a valid partial order
AND no minefield triggered
AND required communication satisfied
AND budget respected
AND trace/run complete and valid
```

Optional milestone不影響 Episode PASS。Non-critical minefield仍使episode失敗，但與critical minefield分開報告。
Equivalent trajectories可通過同一 semantic oracle；不得為逼 exact tool sequence而拒絕正確結果。

### 4.4 Failure taxonomy

至少區分：intent、tool、argument、state-precondition、confirmation、unsafe action、parser、verification、
backend execution、missing milestone、wrong terminal state、communication、budget、user-simulator、environment與
artifact integrity。單一 episode可有多個 diagnostics，但須有一個 deterministic primary failure reason。

## 5. Case construction、來源與review

Sealed primary由human-original semantic families組成；synthetic paraphrases、agent-proposed edge cases與
generated trajectories只進stress或development，除非人類重新獨立撰寫並依同一流程審核。每個case保存：

- source/rationale與所針對的產品或domain risk；
- author/reviewer身份或匿名代碼、日期、版本；
- executable oracle review與 ambiguity notes；
- translation linkage，不把翻譯視為獨立 evidence。

單一reviewer做全量review，至少間隔14天做blind re-review，抽樣上限為20% cases或30 families。報告只能稱
intra-rater evidence，並揭露沒有第二位獨立reviewer。

## 6. Execution environment

### 6.1 Hybrid execution

主矩陣走真正 `ApplicationService / Command API`，並由 deterministic scripted GUI-owned user提供 gold中已
定義的確認、取消、補參數與回答。Harness只讀 public `ApplicationViewPublication`與 `CommandResult`，不能
決定capability、confirmation或產品state。Evidence projection預設移除local path、file list、subject/patient
metadata、prompt/token與diagnostics；gold predicate不得依賴這些被遮蔽值。只有public/checked-in EEG資料可進
benchmark，私人、臨床或未去識別資料不得因為產品是local app就自動納入。

代表性subset經真正Qt adapter/wizard重跑，保存visible transcript、status、button/wizard state與screenshots。
Backend-only evidence不能宣稱 UI驗證；Qt subset也不能取代Windows native manual acceptance。

### 6.2 Dataset source matrix

正式 robustness matrix預定四種 source family：

- BCI Competition IV 2a `A01T` GDF及paired MAT metadata。
- PhysioNet EEG Motor Movement/Imagery `S008R04` EDF。
- BBCI O3VR GDF。
- MNE-BIDS tiny或OpenNeuro `ds003061` P300 BIDS。

納入前需保存authoritative URL、license/terms、exact files、checksum、size、subjects/sessions、cache與cleanup。
資料不提交repo時保存fetch recipe。任何來源不可silent download。Dataset source不是獨立family；同 family在
多資料 source的變體仍保持clustered paired relation。

### 6.3 Resource and environment preflight

正式run保存commit、OS、Python/dependency、CPU/RAM/GPU/VRAM、model revision、quantization/dtype、context、
decoding、cache path與可用disk。Model下載須先通過repo的source/license/size/VRAM/cache規則；不silent fallback。

## 7. Legacy reproduction contract

Legacy source/prompt/raw data固定在 `94adb570f8eb660b771096748b8431f01f8935d7`。Corpus來源為CECNL
`AI-agent` commit `b07f500ee3f6e7180db309447432c01230f1957f`、blob
`555cc5612e8d2154fecbc1c6c1dba1a973fc27f2`。Redistribution需另做license audit。

Adapter須保存六router prompts、chunk `512`/top `3`、mean+std且至少0.2 threshold、1或3 samples、
temperature 0.6、top-p 0.9、command-sequence vote與latest-turn-only。允許safe parse取代`eval`、process isolation、
bounded timeout及in-process harness；禁止current repair/default、history、state guard、verification rescue或
新增tool knowledge。Original model revision未知，native run須標`approximate_reproduction=true`。

公平主比較不是 legacy native model對current新model；而是在兩個topologies中使用同一selected 2B model、
同logical context/output limit與各自frozen prompt/adapter。Legacy-to-semantic mapping只能在inference後評分。

## 8. Model selection contract

Neutral `model_selection` split只用來選每個size tier的一個模型，不得用architecture development/test cases。

| Tier | Candidates |
| --- | --- |
| 2B primary | Granite 3.3 2B、Gemma 2 2B、SmolLM2 1.7B |
| 4B replication | Phi-4-mini 3.8B、Gemma 3 4B、Llama 3.2 3B |

相同條件：context `8192`、max output `512`、BF16、greedy、相同logical tool schema與budget。若官方chat/tool
format不同，只允許documented thin serialization adapter。Selection rule需在run前凍結，以macro Episode、
critical safety、parser validity，再以latency/memory作tie-break；不能依品牌或test結果挑選。

## 9. Pilot、sample size與statistics

### 9.1 Development pilot

Pilot cases是visible、人工撰寫、只屬`architecture_development`的instrument check；不可進正式effect estimate。
每configuration先跑 `R=5`，估 family-level paired differences、stratum variance、intraclass dependence、failure
prevalence與repeat Monte Carlo error。Pilot也用來找oracle ambiguity與environment nondeterminism。

### 9.2 Final N and repeats

用pilot的family-level paired effect/variance做cluster-aware power/simulation analysis，在開validation/test前
凍結每stratum family N、最小detectable effect、alpha、target power、dropout/error allowance與程式版本。
不可把翻譯、paraphrase、fixture或repeat計入獨立N。

正式repeat預設 `R=3`；若pilot顯示primary macro estimate的repeat MC SE > `1pp`，預註冊改為 `R=5`。
不得看sealed result後增加repeat或families。

### 9.3 Estimand and uncertainty

Primary estimand：

```text
Delta = macro_strata(
  family_mean(new_episode_success - legacy_episode_success)
)
```

使用paired hierarchical bootstrap，至少10,000 draws。每draw保持五strata，stratum內重抽family，family內保留
architecture pairing及language/template/fixture/repeat observations。報point estimate、percentile或BCa 95% CI
（方法預先凍結）、每stratum分數、family count、repeat count與missingness。若family run不完整，primary matrix
fail closed，不以complete-case silently刪除。

## 10. Architecture iteration and ablation

最多預註冊8個architecture variants；每個有hypothesis、change、expected mechanism、budget與development stop
rule。先過zero-critical safety gate，再依macro Episode選擇；最多3個進`architecture_validation`。有top3後，
連續兩個預註冊hypotheses都未提升至少2pp即停止。差異落在one-standard-error內時選較少owner/LOC/tool exposure
或較低latency/token者。

開sealed test前凍結winner、prompt、tool membership/schema、parser、retry、context assembler、verification、
model、decoding、budget、scorer與case hashes。之後最多4個mechanism-specific ablations；只在validation或另行
預留的ablation split執行，不回頭改sealed primary winner。

## 11. Sealing and artifact audit

`architecture_validation`與`sealed_human_test`使用不同GPG keys加密；keys在repo外。Repo只保存encrypted
bundle、SHA-256、public schema/version與append-only access ledger。Ledger至少含timestamp、bundle hash、reason、
actor、code commit與是否使blindness失效。這稱`researcher-controlled self-seal`，不得稱independent custody。

正式artifact目錄概念如下；generated run不得提交source tree：

```text
build/dev-artifacts/thesis/agent-benchmark/<run_id>/
  run.json
  traces/<case_id>.<repeat>.jsonl
  verdicts/<case_id>.<repeat>.json
  summary.json
  summary.md
  environment.json
  integrity.sha256
```

Process exit在schema/hash/corpus/run不完整、任何case缺verdict、scorer exception或strict failure時非零。Partial
artifact保存`complete=false`，不可產生passing summary。所有aggregate必須由case+trace+verdict重算。
Repo與可分享artifact不得含model cache、secrets、完整prompt、private EEG、local absolute paths、subject/patient
identifiers或未審核raw transcript；restricted local raw logs與發布用redacted evidence必須分開保存。

## 12. EEG pipeline sanity appendix

EEG pipeline evidence只證明目標科學軟體可運作。若報classification，至少包含accuracy、balanced accuracy、
macro F1、AUC設定與confusion matrix；chance/majority、classical CSP+LDA/SVM與可用neural baseline共用同一split。

`trial-wise`、`session-wise`、`subject-wise`須分開標示；test先鎖定，validation只從remaining data建立，會學習
統計量的preprocessing只fit train。既有 split audit contract仍位於
`docs/validation/split_artifact_schema.json`、`XBrainLab/backend/dataset/split_audit.py`與
`scripts/dev/validate_split_artifact.py`。Pipeline sanity不能替代agent benchmark、UI evidence或external
generalization。

## 13. Claim downgrade rules

| 缺少條件 | 最高可用措辭 |
| --- | --- |
| 只有schema/scorer/prerecorded trace | measurement instrument checkpoint |
| 只有visible development pilot | exploratory development result |
| 沒有同模型legacy/current paired run | single-architecture benchmark result |
| 沒有sealed human test | validation-set result；不得稱held-out test superiority |
| CI下界不大於0或增益<10pp | no preregistered superiority demonstrated |
| 任一critical minefield | safety criterion failed |
| legacy revision/environment不完整 | approximate reproduction |
| 只有backend replay | backend-observable；不得稱UI validated |

## 14. Current implementation status

目前正在建立measurement instrument第一slice：versioned schemas、catalogs、visible pilot corpus、validator、
deterministic scorer、prerecorded trace與ApplicationService observation integration。尚未完成legacy/current
model adapters、model screening、power-derived final N、encrypted sealed corpus、正式comparison或ablation。
因此目前唯一允許的完成語意是`measurement-instrument checkpoint`，且仍須以同source focused validation證明。
