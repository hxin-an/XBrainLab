# XBrainLab 驗證策略

最後更新：`2026-08-09`

這頁定義 current gates、evidence identity 和 claim boundary。Dated checkpoint output 不在這裡
冒充 current result；歷史結果看 records 或 Git history。

## Current Validation Status

| 項目 | Current truth |
| --- | --- |
| Candidate checkout | 由 `git rev-parse --show-toplevel` 和 generated evidence 記錄，不在 canonical docs 寫死本機 path。 |
| Product baseline | `main` |
| Current candidate | `integration/eeg-workflow-improvements-v1`；未合併 checkpoint；只有 exact-head push / CI 可以提升證據狀態。 |
| Baseline | `main@a0e16b400236b687bd2b4c9f58ef4a20929e377b` |
| Closure state | Merged development checkpoint；not release-ready；Assistant not ready；not product complete |
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
- Authoritative Linux suite 已分成 8 個互斥 shards，aggregate 會拒絕缺少 attestation 或
  coverage file 的結果；Windows / macOS 改跑 focused platform contract。Required public
  multi-dataset gate 未移除。Runner tests、Ruff 與 YAML check 已在本機通過，仍需 exact-head
  GitHub Actions 證明實際 scheduling、coverage combine 與 native platform 結果。
- 移除三組已證明重複或無 assertion 的 tests；保留的 tool/controller/downloader suites
  提供較強 state、failure、shutdown 與 duplicate-start assertions。這是 test hygiene，不是以
  減少 authoritative product inventory 換取 CI 速度。

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

目前狀態是已合併到 `main` 的 development `checkpoint`。這個分類只表示後續開發基線已收斂，
不表示 Assistant、效能、資料格式或 release gate 已完成。

## EEG Workflow Improvements Checkpoint

`integration/eeg-workflow-improvements-v1` 整合五個尚未進入 `main` 的改進：curated
Braindecode model catalog、BIDS scan 前 subject selection、training test accuracy curve、
backend-admitted cross-fold Evaluation summary，以及 cross-fold Saliency summary / detached display
normalization。Local focused backend `74 passed`、focused UI `204 passed`、public IO/BIDS/cross-source
integration `40 passed`、representative EEGNet pipeline `2 passed`；strict format matrix 為 `20/20`
lifecycle cases、`14/14` required formats，strict cross-source runner 為 `4/4` required cases。
Independent source review additionally found and closed stable model-ID loss at the Training UI
boundary and subject-cohort conflation in cross-fold summaries; their red-first regressions and
expanded adjacent suite passed before this checkpoint was updated.

The first exact-head run after fixing the required fixture profile proved the public multi-dataset
job itself, but its Windows/Linux/macOS general jobs failed on stale display-name assertions, eager
training imports from Dataset startup, async callback timing, and platform-specific Qt geometry.
The follow-up checkpoint closed those locally with `2577` UI, `2351` LLM/Assistant, `317`
architecture/read-side, and `441` focused workflow tests. A later native-CI closure pass also ran the
complete unit-script (`1148`) and unit-UI (`2584`) suites, all integration shards, the strict
multi-dataset format matrix, and the `4/4` cross-source training smoke. These are development-run
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
| 7. Multi-dataset | `fetch-required-ci` through `public-cross-source-training`，包含 `real-data-interpretation-training` | Fixed denominator、verify-only、wizard、IO/BIDS、cross-source diversity，以及 Graz external labels、PhysioNet internal events、public BIDS 從 Data Interpretation 到 epoch/dataset/training 的連續 product spine。 |
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
Graz 2a 外部 MAT labels、PhysioNet EEGMMIDB 內建 events、public MNE-BIDS events.tsv 與
OpenNeuro P300 `.set + events.tsv`
都能沿 current `scan -> preview -> validate -> apply` spine 進入後續 workflow；這仍不等於
full BIDS validator 或任意 EEG source 支援。
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
