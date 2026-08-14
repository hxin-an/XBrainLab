# XBrainLab 驗證策略

最後更新：`2026-08-15`

這頁定義 current gates、evidence identity 和 claim boundary。Dated checkpoint output 不在這裡
冒充 current result；歷史結果看 records 或 Git history。

## Current Validation Status

| 項目 | Current truth |
| --- | --- |
| Candidate checkout | 由 `git rev-parse --show-toplevel` 和 generated evidence 記錄，不在 canonical docs 寫死本機 path。 |
| Product baseline | `main` |
| Current candidate | 從最新 `main` 建立的 manual UI follow-up / Reset Session surface-retirement candidate；實際 branch / SHA 由 Git 與 generated evidence 記錄。 |
| Baseline | 以 candidate merge-base 的最新 `main` 為準，不在 canonical docs 寫死 historical SHA。 |
| Closure state | Product foundation 與 dataset storage 已合回 `main`；本輪 follow-up 是 short-branch checkpoint，PR exact-head CI 與 merge 尚未完成；not handoff-ready；not release-ready |
| Data Import artifacts | Tracked folder is a dirty checkpoint；read its manifest for source identity and never treat it as current candidate evidence |
| Required authority | 本頁與 [Now](../planning/now.md)；舊 product-quality goal / audit 只作歷史 provenance。 |

`ux/assistant-product-v1@3869aaef` 或舊 stabilization branch 的 PASS evidence 不能代表目前
`main`。目前可用的人工作品 evidence 僅限 Graz 2a GDF 與 OpenNeuro ds003061 P300 BIDS
各一個資料集；這不是 format-wide acceptance，也不包含 Assistant 或效能完成判定。

## 2026-08-09 Integration Checkpoint

- Local-only `p300-multisubject` fixture profile 包含 OpenNeuro ds003061 的 3 subjects、9 EEG
  runs（約 543 MiB）。Exact scope tests 走 real catalog / scan / ApplicationService review，
  但不是 Windows multi-subject acceptance，也不加入 required-ci 下載量。
- 相同 P300 fixture 的 BIDS full review 由約 `9.15s` 降至 `7.92s`；selected discovery 約
  `3.39s -> 2.87s`，content identity 約 `2.00s -> 1.27s`。這是同機 checkpoint；現有
  one-shot ceiling 不支撐跨機 p95 或效能 closure。
- Authoritative Linux suite 分成 8 個互斥 commands，8 個 runner 可同時排程；aggregate 仍會
  拒絕缺少 attestation 或 coverage file 的結果。Windows / macOS 各自平行執行
  `platform-core-contracts` 與 `platform-product-lifecycle`，兩組合起來 exactly-once 覆蓋
  focused platform shards，且每個 Qt / native lifecycle shard 仍是獨立 pytest process。純
  source/static 的 `test_architecture_compliance.py` 只在 authoritative Linux suite 執行，不再
  於兩個 native OS 重複。Required public multi-dataset gate 未移除。Runner tests、Ruff 與
  YAML check 可作 local regression；仍需新 exact-head GitHub Actions 證明實際 scheduling、
  coverage combine 與 native platform 結果。
- 移除三組已證明重複或無 assertion 的 tests；保留的 tool/controller/downloader suites
  提供較強 state、failure、shutdown 與 duplicate-start assertions。這是 test hygiene，不是以
  減少 authoritative product inventory 換取 CI 速度。
- 後續 test-quality cleanup 移除 LLM worker/RAG coverage catch-all、MCP-only automation probes
  與重複 UI constructor/dialog/component probes；BM25 ranking/corpus policy、RAG failure/lifecycle、
  ApplicationService automation、AgentManager/runtime、sidebar capability/publication 與 label-dialog
  result/lifecycle 改由 focused tests 保護。保留的大型 UI workflow tests 仍是 mixed suites，需繼續
  以 structured result、state transition、real signal/lifecycle 為準逐項審查，不可依 mock 數量刪除。

## 2026-08-10 Candidate Closure Checkpoint

本輪在同一 working tree 重跑 authoritative backend、LLM/Assistant、scripts、UI 與 integration
shards，並通過 required public multi-dataset matrix、`4/4` cross-source smoke、teacher dataset
preflight、41-phase human-like walkthrough 與 Data Import / Assistant 可見 artifact review。
修正範圍是 stale fixture contracts、standalone debug host 的 typed setting confirmation、
walkthrough decision owner、跨平台 Qt teardown，以及 coverage-heavy CI 的 bounded test waits；
沒有放寬 product runtime timeout 或 resource policy。

這些是 local candidate evidence。完整 20 個 product scenarios gate 依使用者指示在本次延後，
不是通過；Windows 真人操作、real Granite tool-call accuracy、dual-monitor / DPI 和長時間 session
也仍未驗證。只有把這些變更 commit/push 後，由完全相同 head SHA 的 GitHub CI 全部成功，
才能把本輪提升為 Windows manual-test candidate。

## 2026-08-10 Data Import Label UX / Latency Checkpoint

- 外部 event value 的可見 `Use as` 已限制為 `Training class` / `Do not use`；後者保留 EEG
  event 但不納入 supervised class，且不顯示 class-name editor。舊 `keep_event=false` recipe
  row 在未編輯時保持原值。
- Data Import scan 與 Match Labels re-preview 改由完整 wizard loading surface 立即回饋；Cancel
  不受 busy Dataset panel 連帶 disabled，late callback 不會重新打開 wizard。
- OpenNeuro ds003061 P300、subject 001、三 runs 的同機 warm checkpoint：catalog `0.46s`、
  selected scan `4.67s`、first Preview `2.71s`、repeat Preview `1.43s`。主要改善來自 admission
  scope 內的 canonical path reuse 與單 command sidecar catalog；sidecar existence 仍逐 command
  重新發現，parser guards 未因效能最佳化而略過。
- OpenNeuro ds003061 P300、subjects 001-002、六 runs 的同機 checkpoint：scan `10.80s`、
  first Preview `6.82s`、repeat Preview `3.56s`。Apply 在相同六 runs 與 reviewed `trial_type`
  mapping 下由本輪 profile 前約 `59.5s`，先降至 `35.7s`，再以 bounded canonical path scope
  降至 `21.88s`。Freshness/content guards 仍執行；改善移除的是 WSL `/mnt/d` 上同一 admitted
  path 的 O(n²) 去重與重複 `resolve/lstat`。Dataset status 在完整 raw + label apply 結束前
  維持 `Importing EEG data and labels...`，成功、阻擋、取消與 worker failure 都會取代它。
- Narrowed BIDS run selection 會保存並重用已 admission 的 bounded scan scope，不再於每次
  Match Labels preview 重掃完整 source。Native Windows 因 `st_ctime` 不提供可靠 change-time
  語意，不重用上一輪 content digest；bounded BIDS JSON cache reuse 也會重新讀取並驗證完整
  payload，避免同大小內容替換被舊 parse cache 隱藏。
- Required fixture profile verify-only 通過（`205255918` bytes）；strict matrix 為 `20/20`
  lifecycle、`14/14` formats、`7/7` external placement；公開 wizard walkthrough `11/11`，
  focused backend `117` tests、IO/BIDS/cross-source `40` tests、strict cross-source `4/4`
  （2 個 training、2 個 import/preprocess boundary）、real
  handoff spine `3/3` 通過。
- Artifact：`build/dev-artifacts/data-import-label-use-as-v2/04-match-labels-bids-events.png`
  與 `build/dev-artifacts/data-import-wizard-steps/00-updating-label-matches.png`。這些是 Linux/xcb
  checkpoint，不取代 Windows native DPI / interaction acceptance，也不支撐 full BIDS claim。

## Agent Tool-Call 快速檢查

以下入口用來快速查看單一使用者要求如何經過 state/capability、request-scoped schema、
tool/parameters、verification、confirmation、CommandResult 與使用者可見回饋。預設模式不載入
LLM，但會走真實 product execution boundary：

```bash
poetry run -- python scripts/dev/run_agent_toolcall_showcase.py
poetry run -- python scripts/dev/run_agent_toolcall_showcase.py --list-cases
poetry run -- python scripts/dev/run_agent_toolcall_showcase.py \
  --case import.preview_interpretation --details
```

需要檢查實際本地 2B 模型的 proposal selection 時，必須明確指定已存在的 D 槽 cache；此命令
離線執行，不會自動下載模型：

```bash
poetry run -- python scripts/dev/run_agent_toolcall_showcase.py \
  --real-granite \
  --model-cache-dir /mnt/d/workspace_v2/.xbrainlab-cache/models
```

預設報告寫入 `build/dev-artifacts/agent-toolcall-showcase/` 的 JSON 與 Markdown。`--area`、
`--case` 可縮小範圍。`--resume` 只接受相同 Git commit、目前 product/showcase source
fingerprint、selector ID/version、prompt/case identity 的 v2 報告；real Granite 另要求 exact
model ID/revision、offline 與 no-silent-fallback identity 全部相同。identity 不符會拒絕整份
resume；case terminal semantics 不符則不沿用並重新執行。舊 artifact 的 summary、`pass`、
terminal 或任意 prose 都不是 authority；新報告只帶 allowlisted structured evidence，並以目前
contract 重驗 success、blocked、confirmation/cancel、approved confirmation、UI handoff、stale
revision 與 exact retry sequence。AuthorizedPath 與 host-only confirmation wrapper 只用
field-aware public projection，不能輸出私人路徑、secret 或 opaque unsupported marker。

`2026-08-09` 本機 checkpoint
的 deterministic 與 exact Granite 兩種模式皆為 `18/18`，其中包含 success、blocked、
confirmation/cancel、UI handoff、stale revision 與 runtime retry。這是產品診斷，不是 frozen
thesis benchmark，也不能作為 Agent accuracy claim。

## Evidence 原則

不要把一種 evidence 放大成所有 claim。

| Evidence | 能支撐 | 不能支撐 |
| --- | --- | --- |
| Focused regression | 指定 bug / contract 已被保護。 | 同類問題全部關閉、product handoff。 |
| Same-class/source guard | 已知 forbidden shape 或同類 call site 沒有回流。 | Runtime behavior、UI acceptance。 |
| Architecture/static checks | Import、dependency、typing、lint 等靜態邊界。 | 真 workflow、thread/native lifecycle。 |
| Real ApplicationService smoke | Product command spine 的代表性 state transition 和 side effect。 | 所有 panel UX、所有 datasets。 |
| Deterministic oracle | Event/class semantics、split integrity、held-out outputs 和 finite result contract。 | Scientific model quality 或泛化準確率。 |
| Strict multi-dataset gate | Manifest 內固定 sources、formats、label/event placement 和 cross-source boundary。 | Full BIDS validator、任意 clinical/proprietary format。 |
| Automated UI artifact | Exact-source visible state、layout、primary action 和 bounded interaction。 | Windows native DPI/multi-monitor、真人 usability。 |
| Local Granite/RAG walkthrough | 指定 product policy 下的 local runtime workflow。 | Raw-model accuracy、thesis benchmark、長時間穩定性。 |
| Launcher/startup smoke | Launcher command 和 bounded startup。 | Signed installer、release approval。 |
| `mkdocs build --strict` | 文件站可建且 MkDocs 可解析目前 links/nav。 | 文件敘述一定符合 source。 |

## Exact-Commit Evidence Contract

Final totals 和 PASS claims 只能來自同一個 clean exact commit 產生的 evidence。不得從
checkpoint notes、聊天、舊 branch、不同 pytest shards 或 dated sections 手動相加。

Final evidence 至少要記錄：

- `profile=handoff`；
- absolute worktree；
- branch、full commit SHA 和 HEAD tree SHA；
- dirty state、protected local changes 和 source/tree fingerprint；
- 每個 registered command、return status、duration、timeout 和原始 log identity；
- skip、xfail、xpass、deselection 和 fixture-manifest policy；
- UI/runtime artifact 的 generator、source identity、claims 和 limitations；
- evidence-root policy，以及 local runtime cache 的 redacted D-mounted identity。

Final report 必須逐欄確認：

1. report branch / commit 是當次明確指定的 candidate，並能追溯到最終 `main` 整合點；
2. report commit 唯一對應 pushed candidate SHA，final handoff report 另記錄
   `git rev-parse HEAD` 的 full SHA；
3. source tree clean，或只剩規則明確允許且未 stage 的 repo-root `settings.json`；
   `.vscode/settings.json` 和其他 dirty path 一律不是 protected；
4. handoff profile 沒有重用其他 SHA 的 cached report；
5. branch 有 configured upstream、`HEAD == upstream`，ahead/behind 是 `0/0`；
6. required gates 都由該 commit 產生，且 dossier final verification 通過。

`artifacts/quality/latest.md` 是可覆寫的 local report。檔名中的 `latest` 不代表內容就是目前
candidate；必須先讀 header identity。指向 `ux/assistant-product-v1@3869aaef` 的 report 只算
baseline evidence。

Dashboard 是 final evidence dossier 的 summary，不是 dossier 本身。即使
`profile=handoff` 且 dashboard checks 全部 PASS，runtime command logs、return status 和
artifacts 仍是必須另行檢查的 evidence。

## Current Handoff Gates

| Gate | Required evidence |
| --- | --- |
| Scope and inventory | `git status --short --branch`、full HEAD、worktree inventory、scope/non-goals、dirty ownership。 |
| Finding closure | Audit row 有 implementation、focused regression、same-class sweep、claim boundary 和主 agent verification。 |
| Architecture | `ApplicationService / Command API` 保持唯一 product command spine；`BackendFacade` 保持物理移除；沒有新的 controller/policy/fallback bypass。 |
| Functional happy path | Real FIF import 經 ApplicationService 到 preprocess、epoch、split、persisted training、evaluation、visualization readiness，且不 mock persistence。 |
| Semantic oracle | Deterministic dataset 驗證 source events/classes、disjoint/exhaustive splits、held-out targets/logits、finite metrics/probabilities 和 safe persistence。 |
| Data diversity | Required fixture manifest、Data Interpretation matrix、visible wizard matrix、IO/BIDS integration 和 strict cross-source runner 全部通過，mandatory case 不得 skip/xfail/deselect。 |
| Assistant/local runtime | Exact Granite、secure offline RAG、confirmation/error/retry/cancel/long-session 和 bounded shutdown；不做 silent fallback。 |
| UI/product | Relevant happy path、edge states、full/narrow/DPI screenshots、source identity 和人工 artifact review。 |
| Native lifecycle | Qt/PyTorch/MNE/Matplotlib/PyQtGraph tests 使用 timeout 與 `prlimit --core=0`；Preprocess 和 Visualization ownership gate 分開判讀。 |
| Static/quality | Ruff、完整 configured product-source Basedpyright（`XBrainLab/`，排除模型 cache）、architecture checks、relevant regression 和 handoff dashboard 由 final commit 重跑。Scripts/tests 由 Ruff、pytest 與各自 executable gates 保護，不宣稱納入 Basedpyright scope。 |
| Docs | Canonical truth 一致、stale current-tense claims 移除、source/link search clean、MkDocs strict PASS。 |
| Branch hygiene | Expected branch 有 configured upstream；`HEAD == upstream`、ahead/behind `0/0`；只有 unstaged repo-root `settings.json` 可例外；final report identity 吻合。 |
| Claim boundary | Windows native DPI/multi-monitor、interactive 3D、teacher datasets、long-session 和 product completion 仍分開。 |

任何 required gate 未完成時，狀態只能是：

- `checkpoint`：局部工作已驗證，但完整 handoff gate 尚未完成；
- `blocked`：需要使用者決策、外部環境或無法自動取得的 evidence；
- `handoff-ready`：只有全部 gate 從同一 clean pushed commit 完成後才可使用。

Product foundation 與 dataset storage 已經由 exact-head CI 成功的 PR 合回 `main`。目前 manual
UI follow-up / Reset Session surface retirement 仍是尚未合併的 `checkpoint`；只有該短 branch 的
focused evidence、PR exact-head CI 與 merge 完成後，變更才算進入產品基線。這仍不表示
Assistant、效能、資料格式或 release gate 已完成。

## EEG Workflow Baseline And Historical Polish Evidence

先前 EEG workflow 與 import/training/montage polish 的實作已透過後續 product-foundation PR 進入
`main`。本節後續的逐次測試數字與 CI 修復只保留為歷史 evidence，不是目前 candidate 的 total，
也不能取代 generated exact-head report。Windows interaction acceptance、Assistant readiness 與
延後的完整 product gate 仍然開放。

The first exact-head run after fixing the required fixture profile proved the public multi-dataset
job itself, but its Windows/Linux/macOS general jobs failed on stale display-name assertions, eager
training imports from Dataset startup, async callback timing, and platform-specific Qt geometry.
The follow-up checkpoint closed those locally with `2577` UI, `2351` LLM/Assistant, `317`
architecture/read-side, and `441` focused workflow tests. A later native-CI closure pass also ran the
complete unit-script (`1148`) and unit-UI (`2584`) suites, all integration shards, the strict
multi-dataset format matrix, and the `4/4` cross-source smoke (two training plus two import/preprocess
cases). These are development-run
observations, not final handoff totals; merge review still requires one completed successful
exact-head CI run for the final pushed candidate.

Ordinary integration runs use a deterministic offline tokenizer for host-side context admission and
budget enforcement. They do not claim exact Granite tokenization. Exact pinned-revision chat-template,
tokenizer and generation behavior belongs to the separate `granite-runtime` and exact-Granite
walkthrough gates, which run with the explicitly admitted D-drive model cache.

可見 artifacts 位於 `artifacts/ui/bids-subject-selection/`、
`artifacts/ui/model-catalog-checkpoint/`、`artifacts/ui/training-test-curve/`、
`artifacts/ui/evaluation-cross-fold-summary/`，以及 ignored
`build/dev-artifacts/saliency-cross-fold-normalize/`。這些結果支撐 validated checkpoint，不支撐
Windows acceptance、scientific accuracy、full Braindecode catalog、full BIDS compliance 或 merge
approval。候選的 exact-head CI 仍須成功，才可依 PR 規則合併。

## BIDS Match Labels Performance Checkpoint

`perf/bids-match-label-preview` 針對 OpenNeuro ds003061 P300 三個 runs 的 Match Labels
延遲做了 bounded optimization。相同 scan、相同已 admit BIDS scope 且資源風險為 safe 時，首次
Preview 沿用 Scan 的 bounded discovery/admission；每次重用前仍重新檢查可用 RAM 與檔案身分，
warning、unknown、blocking、scope 變更或檔案變更都會回到完整 preflight。Apply 仍執行完整
content freshness validation。

同機實測 current checkpoint：Scan `5.9s`；首次 Preview `4.3s`；後續 Preview `2.0-2.1s`。
公開 diagnostics 約 `0.20 MB`，Application state 約 `0.14 MB`；最佳化前重複 Preview 約
`8-11s`、diagnostics 約 `8.2 MB`。三-run P300 的 `2,245` 個 reviewed class events 與來源
sample/label 完全一致，`-0.2..0.5s` 建立 `2,243` epochs 並明確排除兩個 recording-boundary
events。這是 task-branch checkpoint，不是 Windows 真人 acceptance 或 full BIDS compliance claim。

## Visualization Interaction Performance Checkpoint

- Saliency Map、Spectrogram、Topographic Map、3D Plot 與 `All Folds` 現在共用同一條
  generation-bound background publication 路徑。GUI thread 只套用仍符合目前 selection / generation
  的 immutable publication；快速 A -> B -> A 切換不再讓舊 worker 覆蓋新畫面或永久停在 loading。
- Evaluation `All Folds` 的跨 fold pooling / metrics publication 也移到 serialized worker；切回單一
  fold 或快速返回原選擇時會拒絕 stale result 並重新排程必要工作。Model Summary callback 以 request
  sequence、identity 與 application generation 圍住，較晚抵達的舊 run 不可覆蓋目前 run。
- `All Folds` publication 不再對同一 fold 執行兩輪 provenance/context validation，也不再在
  pooling 後為 immutable DTO 再複製整份 class arrays。代表性 9-fold、5-method、7-class
  workload 的 raw publication 約 `1.756s -> 0.874s`，normalized publication 約
  `2.000s -> 0.961s`；fold validation 次數由 `18` 降至 `9`。
- 同一 application generation / run / method 的 Absolute 與 Normalize 互動共用一份 verified
  raw publication。Normalize 只建立一份 bounded display variant；selection、method、generation、
  invalidation 或 cleanup 會清除 cache。代表性 64 MiB payload 的原始四次 toggle publication
  路徑約 `625.8ms`；初次 verified raw 約 `98.8ms`，第一次四次切換（含 normalization）約
  `53.1ms`，warm 四次切換約 `0.011ms`。Matplotlib / 3D 實際繪圖仍是非同步成本。
- Spectrogram 的 STFT preparation 使用 bounded single-flight cache；相同 publication 的
  Normalize 切換只改 display normalization，不重算 STFT。因 Spectrogram 顯示的是非負 magnitude，
  Absolute 不再呈現成可切換但沒有不同語意的控制。Map / Topographic Map 的 trial/time aggregation
  使用 `float64` accumulator 後再發布，避免大型 `float32` cohort 累加精度流失；3D 的 exact geometry
  interpolation 與 prepared engine 也使用 bounded cache，並在 publication lifecycle 變更時失效。
  Prepared-engine entries 只持有 weak publication identity，不會因八筆 LRU 額外保留八份完整 saliency
  payload。
- Evaluation Model Summary 改用所選 completed run 的 trained model 與真實 EEG
  `(batch, channels, samples)` input shape；`torchinfo 1.8.0` 是 core dependency。這關閉了舊
  4D synthetic input 失敗後被誤顯示為 unavailable 的問題；summary 尚在準備時會顯示 pending，
  不再先顯示錯誤的 unavailable 文案，但尚未驗證所有 curated models。

本輪同類 Saliency / Evaluation focused suite 為 `431 passed`，publication / architecture / native
lifecycle suite 為 `334 passed`。Required IO / BIDS / cross-source integration 為 `40 passed`，strict
public cross-source smoke 為 `4/4`，代表性 pipeline 為 `2 passed`。主 agent 已檢視
`build/dev-artifacts/saliency-same-class-audit-v3/` 的 Map、Spectrogram、Topographic Map 與 3D
blocked-state artifact；headless artifact 不能證明原生 Windows / OpenGL 3D 互動，因此該項仍需
真人 acceptance。獨立 reviewer 退件後的 worker race / retention 修正另通過 focused `274 passed`、
UI root contracts `919 passed` 與 architecture compliance。Fast dashboard 仍因既有全 repo
Basedpyright baseline、strict resource calibration metadata 與目前環境缺 xcb 而非全綠，不能據此
宣稱 release-ready。

## Current UI Checkpoint

| Feature | Visible checkpoint | Evidence limit |
| --- | --- | --- |
| BIDS subject selection | `artifacts/ui/bids-subject-selection/bids-subject-selection.png` | Shows pre-scan scope selection; no adjacent exact-SHA manifest. |
| Braindecode model catalog | `artifacts/ui/model-catalog-checkpoint/model-selection-dialog.png` | Shows one selected model; catalog breadth is covered by tests, not this image. |
| Training test curve | `artifacts/ui/training-test-curve/training-accuracy-test-curve.png` | Shows the final published test-accuracy point; test loss is not plotted. |
| Evaluation cross-fold controls | `artifacts/ui/evaluation-cross-fold-summary/evaluation-controls-panel.png` | Shows `All Folds` / summary controls, but the plot area is not populated. |
| Saliency Normalize | `build/dev-artifacts/saliency-cross-fold-normalize/visualization-render-walkthrough.md` | Single-fold offscreen render evidence; it does not prove `All Folds` admission or Windows behavior. |

These are manifest-less visual checkpoints, not exact-SHA handoff evidence. The strict format matrix
and `4/4` cross-source training smoke are useful local regression outputs but likewise do not record
the full Git/evidence identity required by the handoff contract. A final candidate must regenerate
populated Evaluation / cross-fold Saliency artifacts under an exact-SHA dossier and still requires
Windows native DPI/multi-monitor acceptance.

## Delivery Flow

```text
main development checkpoint
  -> teacher-facing GUI/data fixes on short task branches
  -> performance measurement and polish
  -> simplified Assistant prototype + recalibrated Agent gates
  -> one explicit candidate commit
      relevant regression + multi-dataset + artifact + reviewer gates
  -> pushed PR whose exact-head CI completed successfully
  -> Windows human acceptance
  -> explicit merge decision
  -> merge through PR, fast-forward local main, verify remote containment
```

`push`、local PASS 或 pending CI 都不等於可合併。PR 必須以目前 head SHA 取得完成且成功的
checks；不得使用 `gh pr merge --auto` 代替檢查，因未受保護的 branch 可能在 CI 仍執行時
立即合併。

完整報告欄位和 task-slice 規則看 repo-root
`.agents/workflows/handoff-candidate.md`。

## Canonical Handoff Runner

`scripts/dev/handoff_gate_spec.py` 是 required gate ID、argv、timeout、environment、pytest outcome
和 artifact policy 的唯一 executable manifest。`scripts/dev/run_handoff_validation_manifest.py`
依 registry 順序把所有 required gates 交給 `scripts/dev/handoff_evidence_recorder.py`，任一 gate
失敗即停止；全部成功後，再用完整 required ID set 驗證 dossier。不要從這頁複製個別 command
重組 final handoff，也不要用 dashboard 取代 runner。

Canonical invocation：

```bash
MODEL_CACHE_DIR="$(realpath XBrainLab/llm/core/models)"
RAG_CACHE_DIR=/mnt/d/XBrainLabCache/rag
poetry run -- python scripts/dev/run_handoff_validation_manifest.py \
  --model-cache-dir "$MODEL_CACHE_DIR" \
  --rag-cache-dir "$RAG_CACHE_DIR"
```

兩個 cache argument 都是必填，必須解析為 `/mnt/d/...` 的 absolute D-mounted path。Recorder
會先移除 inherited `XBRAINLAB_MODEL_CACHE_DIR` / `XBRAINLAB_RAG_CACHE_DIR`，再對所有會載入
local-runtime assets 的 registered gates 明確注入兩個 path；這包含 complete regression 內的
Granite tokenizer integration、real Granite、RAG 和 local-LLM walkthrough，避免回落到 Windows
C 槽或 WSL home default。Recorder 的 check `environment` policy 只記錄 mount 和
resolved-path SHA-256 的
redacted identity，不把 injected cache path 寫入該欄位。這個 identity 證明每個 gate 使用同一組
明確 cache policy，但不代表 cache content 本身正確；model/revision、RAG artifact，以及 gate
自行產生的 logs/output 仍依各自 evidence contract 驗證。

Runner 預設把 evidence 寫到 repo-contained、gitignored 的
`build/handoff-evidence/<full-SHA>/`。Recorder 會自行確認 SHA segment 和 ignore policy，不依賴
呼叫者先手動執行 `git check-ignore`。需要 external evidence root 時，必須使用 checkout 外的
absolute SHA-scoped path，並明確 opt in：

```bash
HANDOFF_SHA="$(git rev-parse HEAD)"
poetry run -- python scripts/dev/run_handoff_validation_manifest.py \
  --model-cache-dir "$(realpath XBrainLab/llm/core/models)" \
  --rag-cache-dir /mnt/d/XBrainLabCache/rag \
  --evidence-root "/mnt/d/XBrainLabHandoff/$HANDOFF_SHA" \
  --allow-external-evidence-root
```

Repo-contained 但未 ignored 的 root 會 fail closed；checkout 外的 root 若沒有 explicit opt-in、
不是 absolute path 或缺少 full SHA path segment，也會 fail closed。External root 不會被錯誤地
送進 repo-relative `git check-ignore` 判斷。

Required pytest gates 只能透過 source-controlled wrapper 執行。Wrapper 會在 `pytest.main()`
正常返回後才原子寫入 SHA-scoped JSON attestation，記錄 runner、logical arguments、exit code
和完整 outcome counts；stdout 中的 `passed` 文字不具認證效力。這個契約用來防止提前退出、截斷
log 或偽造 terminal summary 被誤判為 PASS。它信任同一 candidate SHA 內受 review 的測試與
runner source，不是用來抵抗能任意修改同一使用者 source/evidence 的惡意程式碼。

## Registered Gate Inventory

下表用來說明 gate 意圖；exact argv 只讀 checked-in registry，不在文件維護第二份 shell manifest。

| Section | Registered IDs | Evidence boundary |
| --- | --- | --- |
| 1. Identity/static/docs | `git-status` through `mkdocs-strict` | Branch/upstream/source identity、Ruff、Basedpyright、MkDocs。 |
| 2. Architecture/security | `architecture-compliance`、`architecture-unit`、`persistence-path-stop-barrier`、`complete-regression` | Command spine、read-side boundary、safe persistence/path、Stop barrier，以及隔離 subprocess 的完整 unit/integration/regression suite。 |
| 3. Real command spine | `command-spine` | Real ApplicationService FIF workflow plus deterministic oracle；不支撐 scientific accuracy。 |
| 4. Assistant/local runtime | `assistant-security-suite`、`granite-runtime`、`rag-offline`、五個 `chatpanel-*` gates | Exact Granite、secure RAG、guided/training readiness/completion、recovery、long session 與 bounded shutdown。 |
| 5. UI artifacts | `human-like-product` through `data-import-wizard-validate` | Exact-source full/narrow/DPI/wizard/visualization artifact set。 |
| 6. Native lifecycle | `native-lifecycle-tests`、`preprocess-native-stress`、`ui-native-render-stress` | Preprocess and render ownership；不取代 Windows native acceptance。 |
| 7. Multi-dataset | `fetch-required-ci` through `public-cross-source-training`，包含 `real-data-interpretation-training` | Fixed denominator、verify-only、wizard、IO/BIDS、cross-source diversity；Graz external labels 與 PhysioNet internal events 走到 training，public BIDS 依 fixture 能力走到 preview/apply 或 epoch/split readiness。 |
| 8. Resource/dashboard | `resource-calibration`、`handoff-dashboard` | 在 ignored exact-SHA root 產生 CUDA calibration，dashboard 保留並驗證該輸入後做 final clean-source recheck；dashboard 必須維持最後一個 gate。 |

Section 2 的 WSL/POSIX regression 與 Windows native-opener source/dispatch guard 不能取代真人
NTFS junction/reparse acceptance。Section 3 的 real command-spine smoke 和 deterministic oracle
不能互相替代，也不能外推成 scientific model quality。

Section 4 必須共同覆蓋 success、confirmation approve/reject、blocked/error、retry、cancel、
RAG re-admission、long session 和 bounded shutdown。Deterministic tests 或 host-composed UI
不能單獨替代 exact Granite artifacts；exact Granite artifact 也不能外推成 raw-model accuracy。
所有 desktop 與 bounded walkthrough 退出路徑必須在 `QApplication` 尚存活時處理 Qt deferred
deletes；artifact 內容 PASS 但 process return code 非 0 仍視為 gate failure。

Section 5 的主 agent 必須逐張檢查 full-window、narrow width、100/125/150% scale、Assistant dock、
loading/empty/error/blocked/terminal、primary action、text fit、scroll、dialog geometry、provenance
和 overlap。Offscreen/Xvfb evidence 不取代 Windows native DPI/multi-monitor。Tracked
`artifacts/ui/data-import-wizard-steps/` 只能算 checkpoint；final runner 寫入 SHA-scoped
ignored/external root，不覆寫 tracked artifact。

Section 7 的 required denominator 不得用缺 fixture、刪 case、skip、xfail 或 deselection 縮小。
`required-ci` profile 固定包含三個 OpenNeuro ds003061 P300 runs；完整 pinned profile 約
`205 MB`，下載與 verify-only 必須先成功，P300 測試不得以缺 fixture skip 通過。
`real-data-interpretation-training` 必須整檔執行
`tests/integration/pipeline/test_real_data_handoff_gate.py`，不可只挑一個較容易的 node。它證明
Graz 2a 外部 MAT labels 與 PhysioNet EEGMMIDB 內建 events 可沿 current
`scan -> preview -> validate -> apply` spine 進入 training；public MNE-BIDS events.tsv 走到 epoch
與 split-configuration readiness，該 fixture 的 training 仍明確 blocked。OpenNeuro P300
`.set + events.tsv` 的 preview / apply 由獨立 public-BIDS gate 保護，不屬於該 handoff test 的
training claim。這些 evidence 仍不等於 full BIDS validator 或任意 EEG source 支援。
Sleep-EDF 和 CHB-MIT teacher fixture tests 是 optional acceptance evidence，
不混入 mandatory public IO gate。不同副檔名不等於不同 dataset source；同一 source 的轉檔
只算 format coverage。這組 gate 不支撐 full BIDS validator、任意 clinical/proprietary format
或 scientific accuracy。

Section 8 不使用 tracked `artifacts/resource_guard/calibration.json` 認證 handoff；該檔只算開發期
checkpoint。Canonical runner 會先將 calibration 寫到
`build/handoff-evidence/<full-SHA>/resource-calibration.json`，再把同一檔案作為 preserved input
交給最後的 dashboard。校正與 dashboard 都要求相同 branch、完整 commit、tree、source digest
及無未保護 dirty source；未 stage 的 repo-root `settings.json` 仍依 protected-local policy 顯式記錄。

Section 8 dashboard does not run or certify sections 3-6。它只總結自己實際執行的 checks，
並重新驗證 expected branch、configured upstream、`HEAD == upstream`、ahead/behind `0/0`、
dirty policy 和 execution 前後 source stability。Final dossier verification 由 canonical runner
在 dashboard 成功後執行；任何 artifact generator 若讓 tracked worktree 變髒，runner 必須
fail closed。

## Assistant Evidence Boundary

Product runtime 必須保持 local-only，exact model / embedding revision、consent/quota、offline
loading、resource admission、confirmation、capability、verification 和 shutdown policy 都要在
final source 重跑。

Artifact 或 tests 必須分開報告：

- model-owned output；
- host normalization / bounded repair；
- deterministic host continuation；
- ApplicationService capability / confirmation blocking；
- user decision boundary；
- raw-model score versus host-assisted product behavior。

Host-assisted product walkthrough 不能報成 raw-model accuracy。Tool-call benchmark 只有在產品
closure 後 freeze cases、scorer、prompt/source fingerprint 和 repeats，才可作 thesis evidence。

## Artifact and History Boundary

`artifacts/` 是 generated evidence，不是 canonical current truth。Artifact 只有在 source
identity、generator、claims 和 limitations 完整且吻合 current candidate 時才可用。

MCP code/tests/artifacts 若仍存在，只代表歷史探索或使用者明確要求的專項 evidence。MCP 已退出
active product / thesis roadmap，不是 handoff、release-candidate 或 thesis prerequisite。

歷史工程結果請看：

- [Product Quality Audit - 2026-07-30](../records/product_quality_audit_2026-07-30.md)
- [Implementation Log](../records/implementation_log.md)
- [Worklog](../records/worklog.md)
- Git history

這些 history sources 可以解釋一個 checkpoint 做過什麼，但不能把舊 branch 的 totals 或 PASS
直接升格成 current handoff claim。

## Claim Boundary

Automated closure 全部通過後，只能宣稱 **Windows handoff candidate**。以下仍需獨立 evidence
或真人 acceptance：

- Windows native DPI、多螢幕、遠端桌面和長時間互動；
- interactive 3D 和 native GPU teardown；
- teacher-supplied datasets 與真實使用流程；
- signed installer / release approval；
- scientific model-quality；
- frozen thesis-grade tool-call / agent accuracy；
- product complete 和 merge to `main`。
