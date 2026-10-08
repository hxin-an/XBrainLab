# XBrainLab Validation Contract

最後更新：`2026-10-06`

驗證回答「哪個exact source，在什麼環境，觀察到什麼」，不能把單一PASS放大成產品、科學或真人
驗收結論。日常與PR交付按下表選證據；CI routing由既有workflow擁有。明確要求完整dossier時，
gate的ID、順序、argv、timeout與artifact contract仍只以`scripts/dev/handoff_gate_spec.py`為準。

## Daily checks and PR delivery

本機focused checks用於修理回饋；CI負責同一PR head的完整回歸、跨平台與既有artifact gates。
同一證據只執行一次：已有成功的同版本CI artifact時，不在本機重跑等價全套，也不因新增一筆
不相關修改反覆讀取全部圖片。CI未涵蓋的必要證據才補本機執行，命令沿用既有runner。

### Feedback tiers and escalation

| Tier | Trigger | Work |
| --- | --- | --- |
| L0: edit feedback | Small edit or bug reproduction | Changed-file lint/format checks and the directly relevant failing test. |
| L1: coherent change | One behavior/refactor slice is ready | Focused behavior tests and directly affected integration/lifecycle protection. |
| L2: PR candidate | Formal delivery | Same-head applicable CI: regression, whole-project typing, platform/data/visual gates; local work fills only evidence CI lacks. |
| L3: full dossier | Explicit full-release request or applicable capability contract | The canonical complete manifest, not an everyday default. |

These are selection points, not four mandatory steps after every edit. Seconds for L0 and minutes
for L1 are feedback goals, not timeouts or permission to omit necessary protection. Escalate for a
changed shared contract, data/publication/async risk, a concrete failure or an unresolved evidence gap;
file count alone does not determine risk. Record why a broader run is needed before starting it.
Reuse a passing focused result until relevant source/environment changes; final delivery still needs
the exact-source evidence below. Do not launch equivalent full local work while waiting for CI.

Use existing Ruff/pytest entry points with explicit changed paths or behavior test node IDs for L0/L1.
The Poe tasks `check` and `check-full` include whole-project analysis and all unit tests; `test-backend`
includes the entire integration directory; `typecheck-fast` runs whole-project Basedpyright. Their names
do not make them fast feedback commands. They remain explicit aggregate tools, never per-edit defaults.
Before widening a slow run, inspect existing JUnit/timing data and separate collection/import, fixture,
test and teardown cost. Measure only the missing bounded path, not the full suite to obtain a ranking.
Do not add a second test-selection framework, a coverage target outside an approved active plan, or
duplicated worker runs.

The approved quality-hardening gate collects branch coverage for the full Linux aggregate and writes
`coverage.json`. `scripts/dev/run_tests.py verify-coverage` requires at least 85% line coverage
(`covered_lines / num_statements`) and requires branch data to be present. The branch percentage is a
recorded baseline, not a pass/fail threshold. Both the CI aggregate and an explicitly coverage-enabled
local aggregate use this verifier; focused shards only contribute raw coverage evidence.
`poe test-cov` selects that same full local aggregate with `XBL_TEST_COVERAGE=1`; it does not
bypass the line-only verifier through a separate direct pytest command.

### UI design iteration before formal handoff

已授權的可見 UI 調整先用真實元件做原生預覽，讓使用者直接操作並反覆確認設計。CLI 使用者
不能只收到圖片路徑；有桌面存取時由 agent 開啟預覽並確認視窗有回應。預覽使用隔離／示例資料，
明示不是完整 workflow，不更動使用者正在使用的主程式或資料。無法開啟原生視窗時明示限制，
提供可執行的替代方式，不宣稱已展示或已接受。

設計迭代期間只做直接相關的互動、geometry、截圖與 static checks；等使用者接受設計後才
更新審查過的 references、送出正式候選並執行重型 regression／跨平台／DPI gates。不為每次
顏色或間距調整反覆啟動全套 CI。直接安全／資料風險的必要驗證不延後，也不藉此削弱 CI。

設計接受不等於正式手測或 merge 批准。定稿後仍須下表的同版本證據，交付時直接開啟指定來源的
完整程式與可見即時 log；確認啟動成功後交回使用者，不再無故長時間監控。後续設計改動回到
預覽迭代，再為新的定稿 source 補齊必要證據。此流程不增加 backend-only 修正的設計批准門檻。

這是本專案的使用者工作流；[OpenAI 的可重用技能文件](https://learn.chatgpt.com/use-cases/reusable-codex-skills)
支持將實際合作經驗保存為 repo skill，但不替本專案規定驗證時機或批准政策。

### Applicable evidence

| 變更 | 本機最小證據 | 交付時必要證據 |
| --- | --- | --- |
| Docs／guidance／config | 結構／設定audit、相關測試，受影響docs build | 同head guidance／docs CI；不跑產品模型評測。 |
| 一般bug／重構 | 可重現defect或passing baseline、相關行為測試與static checks | 同head全部non-skipped CI成功；不另跑本機full regression。 |
| 可見UI | 操作與state測試、changed-surface screenshot／walkthrough | 同head視覺比較；layout／theme／font／dialog變更需Windows DPI gate。 |
| Data／import／label／epoch／training／evaluation／visualization | 對應資料語意與直接lifecycle測試 | 同head canonical source-diverse gate；CI artifact可直接滿足。 |
| Async／native | 完成、取消、stale callback與cleanup的直接保護 | 對應平台CI／stress evidence；未覆蓋的必要native seam才補本機。 |
| Assistant模型／prompt／tool契約／推論流程 | 直接command／policy／trajectory保護 | 適用的真model baseline與GUI journey；其他產品變更不重跑模型評測。 |

大型測試清理保留行為保障的對照，揭露刪除前後數量，不以任意減少denominator冒充品質提升。
Focused檢查通過後，只有新變更、失敗或未解風險才擴大／重跑。同版本CI失敗時先判讀原因；
不以增加timeout、無上限重跑、隱藏skip或忽略失敗來交付。一次重跑通過也保留原失敗的限制。

Git／CI identity、exit code、counts、widget可見／enabled、geometry與pixel差异由deterministic
工具判定。模型審查保留給語意、產品設計與異常原因；不得只看模型敘述就宣稱artifact存在或PASS。
同head CI／artifact連結加focused結果就是一般PR交付證據，不強制另建本機完整dossier。
新source需新CI；不同SHA、環境、模型revision或已知限制的證據不可冒充本次執行。

## Evidence levels

Assistant 的兩種決策／三層離線判分入口見
[Benchmark scorer calibration](assistant_benchmark_calibration.md)。它只校準 agent-authored
Development 合成觀察，不執行模型／工具，也不取代本頁的單輪 candidate gate 或產品驗收。

Harness changes that claim fresh-agent readiness need native new-session evidence, without inherited
chat or a prompt containing the intended answer. Check instruction/config/skill discovery, task takeover
and validation selection; for substantial workflow changes also replay one bounded real repair in an
isolated checkout. Preserve actual tool events, test exits and diffs alongside the candidate identity.
Record loaded global overrides and environment prerequisites; do not present them as repo-owned setup.
Static audits prove structure, not decision quality. Failed attempts remain reported; refine only from
observed failures. Reuse the existing CLI and ignored artifacts, not a new evaluator/control framework.
These cases do not certify identical behavior on every future task or product Assistant capabilities.

| Level | 支撐 | 不支撐 |
| --- | --- | --- |
| Unit/source guard | Bounded behavior或穩定靜態規則。 | 完整workflow、native UI、real dataset diversity。 |
| Integration | ApplicationService/domain/UI元件間的state transition。 | Windows真人操作或科學品質。 |
| Source-diverse data gate | 代表性來源的import/label/epoch/training contract。 | 所有格式、所有dataset或full BIDS compliance。 |
| Automated UI artifact | Exact-source layout、visible state與interaction；原生Windows capture可證明該DPI的自動geometry檢查。 | 真人DPI／多螢幕操作與usability；offscreen不能代表Windows。 |
| Handoff dossier | 同一clean/explained pushed SHA的完整工程證據。 | 使用者manual acceptance、signed installer或scientific certification。 |
| Manual acceptance | 使用者在指定產品source上完成實際操作並同意merge。 | 未測平台、未測資料集或後續改動的source。 |

## Import support claims

Use `user_docs/import-support.md` for the agreed user boundary. A reader registration,
synthetic wizard preview, BIDS-shaped FIF fixture, or a few MOABB examples cannot establish
complete EEG-BIDS/MOABB conformance. Track selected recordings and exact conversion/reader versions;
several formats exported from one GDF source remain one source family.

| Required behavior | Existing direct evidence entry points | Claim limit |
| --- | --- | --- |
| Common file import through Commands | `tests/integration/io/test_io_integration.py` | Includes derived compact files; not every format variant. |
| Internal classes and external rows anchored to real events | `tests/integration/pipeline/test_checked_in_real_dataset_validation.py` | Checked-in Graz sources, not all MOABB paradigms. |
| Time/sample origin, artifact retention, failed apply atomicity | `tests/integration/io/test_external_label_semantic_safety.py` | Real MNE I/O with controlled synthetic semantics; not independent dataset diversity. |
| Explicit no-label import → resample → rejected supervised epoch | `test_unlabelled_import_preprocesses_but_cannot_create_supervised_epochs` in the preceding module | FIF/FIF.gz with and without acquisition events; checks retained data and unchanged source bytes. |
| Explicit BIDS no-label Commands → resample → blocked epoch → recipe reload | `test_explicit_no_label_bids_import_does_not_require_events` in `test_public_bids_fixture.py` | Copied public BrainVision BIDS, with/without events.tsv; Command evidence is separate from GUI acceptance. |
| BIDS embedded events → complete explicit class review → import and recipe replay | `test_bids_embedded_events_require_observed_complete_review` in `test_public_bids_fixture.py` | Public waveform with controlled markers; rejects incomplete, overlapping, excluded and unknown class mappings. Not dataset diversity. |
| Visible internal class choices → single/multi-recording import → epochs → recipe replay | `test_physionet_internal_classes_from_wizard_survive_epoch_and_recipe` in `test_data_import_wizard_real_fixture_acceptance.py` | Starts without hidden mappings; checks source event samples, A/B and Back-edited B/A on both recordings. The second recording is a controlled copy, not another dataset. |
| Visible BIDS external-to-internal label-source choice → epochs → recipe replay | `test_visible_bids_wizard_reviews_embedded_labels_with_or_without_sidecar` in the preceding module | Controlled BrainVision markers at samples 100/200; both sidecar-present and absent paths. Does not prove arbitrary conflicting sidecar/embedded combinations. |
| Visible external MAT label choices → exact cue/class sequence → epochs and UI-saved recipe replay | `test_dataset_action_handler_imports_real_gdf_with_external_mat_labels` in `test_data_import_action_handler_external_labels.py` | Checked-in Graz waveform and MAT oracle; checks artifact-rejected epochs against independent MNE, not just import count. Adjacent multi-GDF case checks each expected MAT carrier and event/class order, not every cross-recording combination. |
| Visible generic CSV/TSV field/value choices → Commands → epochs → recipe replay | `test_changing_label_field_requests_backend_repreview_at_match_labels` in `test_data_import_wizard_runtime.py` | Real FIF with nonzero first sample and controlled timestamps; actual widgets author choices. This component/Command bridge does not exercise the outer async coordinator or every placement mode. |
| BIDS declared timeline and review freshness | `tests/unit/backend/application/test_bids_recording_timeline_safety.py` | Real FIF in a controlled BIDS-shaped directory, not EEG-BIDS format certification; verifies scoped inheritance and blocked unsafe timestamp placement or changed sidecars. |
| BIDS folder wizard → explicit no-label choice → fresh review → apply | `test_visible_bids_wizard_can_explicitly_import_without_labels` in `test_data_import_wizard_real_fixture_acceptance.py` | Real wizard/Commands, isolated directory chooser; with/without events.tsv, no classes and supervised epoch blocked. Native automation does not replace human acceptance. |
| Visible wizard no-label route | `tests/integration/ui/test_data_import_wizard_real_fixture_acceptance.py` | File chooser isolation with real wizard/readers; offscreen is not human native acceptance. |
| BIDS metadata/events/recipe and timing | `tests/integration/io/test_public_bids_fixture.py`, `test_bids_epoch_duration_handoff.py` | Public fixture and bounded timing cases; not full specification validation. |
| Selected timestamp label field independent of generic BIDS value codes | `tests/integration/io/test_bids_timestamp_label_field.py` | Generated BrainVision files through real Commands and recipe replay; event-code collisions remain blocked. Retained Thielen evidence is recorded separately in the inventory. |
| Large-event recipe persistence and public diagnostics | `test_data_interpretation_recipe.py`, `test_data_interpretation_public_projection.py` under `tests/unit/backend/application/` | Bounded derived evidence, complete explicit choices/content identity, and oversized-input rejection before overwrite; does not raise the 1 MiB limit. |

Dataset breadth and interaction coverage are separate evidence dimensions. Manifest-authored choices
and seeded dialog restoration tests cannot establish that a fresh wizard can author those choices.
For label-selection claims, inspect the UI-authored choices through apply and the actual epoch
sample/class sequence, not only a successful import or readiness flag. Returning to edit a reviewed
choice, cancellation/retry and failed-apply atomicity have separate tests; one happy path does not
stand in for those state transitions. The native wizard suite covers BIDS apply/revalidation/subject
cancel and retry plus missing-events recovery; the explicit no-label BIDS path also checks that a real
epoch command is rejected without changing working data. These are bounded routes, not all possible
file, label, placement and interaction combinations.

All-MOABB acceptance additionally requires a complete pinned release inventory and dataset-level
source selections, official loader identity, converter identity/options, export precision, preserved
units/channels/events/labels/entities, and observed Command import outcomes. Record access failures,
missing data, untested variants and unsupported semantics in the denominator; no silent exclusions.
Inspect selected-subject coverage separately from full-corpus coverage. Reuse existing data/evidence
runners where applicable; this contract does not authorize downloads, duplicate caches or a new
validation control plane. Existing compact MOABB registry is not a full inventory.

### Recurring representative import conformance

Every major-stage integrated acceptance, and every change to import/label semantics or the
MNE/MOABB/MNE-BIDS/reader dependencies, requires the complete representative import catalog plus
representative native Windows wizard evidence before handoff. Ordinary unrelated PRs keep focused
checks and normal CI; this requirement does not mean retraining every dataset or downloading the
corpus in CI. Existing source-diverse training gates remain independently required where applicable.

The executable membership authority is
`scripts/dev/moabb_user_journeys/data/moabb-import-catalog-v1.json`: all 147 pinned MOABB 1.5.0 exports,
including aggregate/subset variants. The [human inventory](moabb-inventory.md) describes that boundary.
Required cases must all execute successfully; deferred rights and unresolved blockers stay visible
but do not become passing cases. Removing an already passing required entry is a baseline regression,
not a way to achieve a green campaign. Source-BIDS-only and retained-conversion evidence must retain
their provenance limitations; neither means a fresh full-cohort conversion or benchmark replication.

`moabb-import-conformance` is registered in the existing handoff gate registry and full release
profiles. Its runner is `scripts/dev/run_moabb_import_conformance.py`; the existing
`XBRAINLAB_DATA_DIR` resolver or explicit `--data-root` selects the retained data root. Each required
case binds a content-hashed manifest, portable input paths, hashes, explicit label choices and
independent expectations. The runner uses actual Scan/Preview/Validate/Apply and fresh-service recipe
replay, checking full selected-run waveforms, channels/types, sample counts and class/sample tuples.
This does not replace native wizard checks or user acceptance.

Refresh `origin/main` before a formal campaign: admission compares against its accepted catalog,
including later promotions, and records its exact SHA. An unavailable Git/ref fails closed; only
an accepted main that genuinely predates the catalog uses the pinned initial 127-case baseline.
Use a new `--output` directory for each candidate. `--resume` permits reuse only with identical
source/environment/catalog/accepted-baseline identities and reverified input/result/recipe hashes; failed attempts
remain available. Missing, changed, unexecuted or timed-out required cases fail closed. No runner
acquisition or automatic terms acceptance is allowed. Reader/converter changes additionally require
attributable reconversion checks; replaying retained BIDS alone cannot prove a changed converter.

The durable local hierarchy is `E:\XBrainLabData\datasets\{source,bids,public-fixtures,manifests,quarantine}`,
with sibling `evidence` and `staging`. This is the current machine's data-root choice, not a hard-coded
product path. Its 134 required representative storage units are direct children of `datasets/bids`;
the current human entrypoint is `datasets/manifests/import-locations-v3/README.md`. Unbound retained
units were resolved on 2026-09-16: exact duplicates/superseded conversions were removed, and 26
individually verified extra recordings joined the three canonical Brain Invaders roots. The original
134-case campaign remains historical representative evidence; the expanded scope includes all 1,205
retained recordings and all 134 normal Windows GUI roots. Current outcomes and unresolved routes are
recorded in [Current](../current.md), not inferred from the representative pass count. Copy/hash/replay precedes reference
changes; original and failed evidence retention is separate from an explicitly approved exact-target
cleanup. Do not rewrite historical recipes.

## Exact-source requirements

完整dossier至少記錄branch、full commit SHA、HEAD tree、dirty state、protected local paths、source
fingerprint、command、return status、duration、timeout、skips與artifact hashes。只有repo-root
`settings.json`可作為未stage的protected local例外。

不同SHA、dirty source、舊branch、reduced denominator、stale cache或手動加總的結果只能稱
checkpoint。Dashboard是summary，不是dossier。

## Artifact locations

- Development output：ignored `build/dev-artifacts/<family>/`。
- Final handoff：ignored `build/handoff-evidence/<full-SHA>/`。
- Approved visual regression references：`tests/baselines/ui/`。
- `artifacts/`：只保留policy/ignore，不保存current evidence。

UI evidence涵蓋變更涉及的hierarchy、contrast、text fit、primary action、overlap、scroll、geometry與
empty/loading/error/blocked state。主agent實際查看changed surfaces與非預期差異；機械狀態先用
widget／geometry／pixel assertions，同版本未改的畫面不逐張重做模型審查。

Visible UI變更的default-scale candidate必須由`capture_ui_baseline.py`產生exact-source manifest並和
approved references比較；CI不得自行更新reference。Layout、theme、font或dialog路徑另跑Windows Qt
platform的100/125/150% app-polish matrix。Linux/WSL offscreen scale不能冒充Windows結果；automated
Windows capture也不取代真人native DPI、多螢幕或remote-desktop acceptance。

## Explicit full-release dossiers

只有使用者要求完整release dossier、Stable／科學模型能力宣稱，或適用契約明定完整dossier時，
才執行本節。一般產品PR可依上節完成交付；不得把focused／CI交付說成完整manifest通過。

完整 dossier 由 `scripts/dev/run_handoff_validation_manifest.py` 執行；命令、timeout 與 artifact
policy 只讀 `scripts/dev/handoff_gate_spec.py`。Runner 的 `--model-cache-dir` 與
`--rag-cache-dir` 必須指向 D-mounted local caches，寫入 evidence 的 cache paths 必須 redacted。
Evidence root 預設必須是 repo-contained 且 ignored；只有明確傳入
`--allow-external-evidence-root` 才能使用 external root。

完整 runner 會執行所有註冊 sections；只重跑 sections 3-6 或其他子集 does not run or certify
完整 handoff dossier。Windows automated checks 也不取代 Windows native acceptance。

- Identity/scope：Git branch、HEAD/upstream、worktree inventory、dirty ownership與non-goals。
- Focused protection：bug red/green或refactor characterization。
- Same-class sweep：直接相關call sites與必要source guard。
- User-like happy path與相鄰failure/cancel/retry/stale lifecycle。
- Data/import/epoch/training/evaluation/visualization：canonical source-diverse dataset gate。
- Static quality：Ruff、configured Basedpyright、architecture guards、diff check。
- Basedpyright gate以locked analyzer version執行完整project analysis，並和checked-in、唯讀的既有
  diagnostic allowlist比較；resolved diagnostics可單調減少，任何新增diagnostic fail closed。Gate不使用
  Basedpyright會自動改寫的native baseline，也不把sandbox缺少第三方search paths的假綠當證據。
- Docs：canonical truth、link/source audit、developer與user-site strict build。
- Branch/CI：focused commits、pushed exact PR head、所有non-skipped checks completed/success。

本節完整dossier宣稱缺任何required gate時只能稱`checkpoint`或`blocked`。一般PR按上節判定
applicable evidence；同一clean/explained exact commit全部通過才可稱`handoff-ready`。

## Merge approval and notification

產品runtime、GUI、資料流程或使用者可見行為有變更時，PR必須記錄`Manual acceptance`：日期、
測試範圍、product source identity與使用者明確的手測通過/merge同意。若product source之後改動，
批准失效並回到checkpoint。CI、自動journey與offscreen screenshot不能取代此批准。

已授權工作的純docs、tests、CI或agent-guidance PR，經review確認不改產品行為、且同版本所有
適用non-skipped checks成功後，可先通知再merge，不必逐次等使用者回覆。通知列明PR/source、
範圍、驗證與已知限制；通知後立即接續核對與merge，不把通知當成等待回覆的關卡。
只要求review或開PR、明示暫停／禁止merge時不適用此授權。
是否屬非產品變更看實際效果，不只看檔名；CI發布／部署改動仍按其外部影響確認權限。
產品PR仍須上述手測及批准，所有merge也都先通知；範圍不明、必要檢查未成功或新外部權限
未取得時不可用通知代替確認。追蹤與停止條件見`.agents/workflows/handoff-candidate.md`。

### Historical Assistant baseline evidence

PR #71 的 bounded baseline 與 v16 以前 81-case 報告保留原 source、schema、題目、
分母及失敗；它們涵蓋現已移除的七條跨輪累積路徑，不能重標為新單輪契約通過。
旧 `desktop-source` 的限定失敗 allowance 也不能用來放行新的候選。
其他與 Assistant 無關的 PR 可沿用已接受版本的已知限制，但不能宣稱舊報告在新 SHA 重跑。

### Single-turn Assistant candidate

#### 2026-10-08 R3 產品移植與格式恢復候選

使用者核准以最新產品底層移植研究R3的模型輸入設計，並將多JSON納入既有一次格式修復。
按Now的固定A/B/C順序比較，不改歷史研究輸入／分數；研究8個格式錯例只作已知回歸，
不稱新holdout。原20核心、6英文與74廣度案例及tool-decision判分保持；首答／repair後、
准入與實際副作用分列，Host擋錯不能救分。新候選不得挪用舊Development例外跳過gate。
重試成功仍需schema／來源／capability／confirmation與publication檢查；多物件不得抽取執行。
完整輸入獨立覆核、真模型證據及Windows正常ChatPanel流程須針對同一最終產品source。
RAG內容／檢索設定固定，配對只比較on/off，不調參追分；推論配額與施工狀態只由Now擁有。

#### 本輪Development候選交付例外（2026-09-29）

使用者在已知74題工具決策65/74首答、66/74最終，以及錯誤提案可能通過Host准入的
說明後，明確接受保留限制的Development候選版手測，並重申開發目標不包含複合需求。
本輪交付以完整、單一英文要求為範圍；不要求新增複合操作支援，不追加模型／prompt／
RAG調整。下列可靠基線gate的歷史失敗保留，不能改成通過、縮小舊分母或宣稱Stable。
除複合要求部分執行外，Reset漏執行、空資料epoch誤切panel、不可用工具提案也保留為
已接受的Development限制；不操作指引及既有backend保護不變，Host擋錯仍不救模型分數。

允許在既有source獨立覆核、基本20＋6題tool-decision證據、真模型Windows journey及
confirmation／cancel證據可追溯，且最終head全部適用non-skipped CI成功後，交限定範圍
Windows手測。模型與native原始證據仍綁定原source；僅文件變動可沿用，parser診斷修理
須連同既有132份capture前後等價覆核說明，不冒稱新head重新推論。
手測用可丟棄的working data，核對單一操作、參數、確認／取消、可見結果及GUI狀態；
不是重新測量準確率或要求使用者替已知失敗背書。手測接受及merge仍需各自明示批准。
此為本輪已知限制的交付例外，不是未來版本略過新缺陷或必要工程gate的通用授權。

#### 原可靠基線gate與歷史證據

2026-09-28 使用者批准完整單輪操作基線：缺值需說明缺項並請完整重述，不保存／合併
跨輪草稿。此節取代舊五欄提案、draft admission 與七條 continuation 的 active gate；
不是把失敗標為成功。正式模型回覆契約由 [Agent target](../target/agent.md) 擁有。

2026-09-28後續使用者明確將本輪驗收限於tool-call正確性，不審回答品質。以下第3項依
此授權更新：歷史完整回答語意成績與raw證據保留原判定；不把它們改標為模型全對。
版本v17報告仍保留原content screening／semantic-review欄位與claim，不能把其總分直接
重標為純tool-call準確率；以同份capture的獨立tool-decision覆核說明當前範圍。

候選須在同一 clean/explained exact source 閉合以下證據：

1. 18-tool registry、嚴格兩欄 parser、current-turn 參數來源、backend publication／stage／
   capability、confirmation、GUI correlation、取消及非同步 lifecycle 的直接測試。
   數值由模型解析並驗schema／range，不要求原句阿拉伯數字membership；方法來源仍驗當輪原文。
   缺值後只給裸數字不能沿用舊值；完整重述須能經真 Command 執行。Mock 生成不證明模型理解。
2. `run_stable_assistant_model_eval.py` v17 預設固定 20 題，題目／oracle 由
   `scripts/dev/stable_assistant_single_turn_cases_v1.json` 與程式內固定 SHA 擁有：
   五種 direct 操作各完整／缺值／否定，共 15；兩種 GUI 開窗；兩個說明；E01 7–30 Hz。
   每題允許產品既有的一次格式修復，修復後模型選擇與參數須 20/20；first raw 另報，
   不回填分數。語意選錯不是格式錯誤，不追加 semantic retry；Host 擋錯也不能救模型分數。
   CLI `--strict` 只驗可機械核對的模型／capture／cleanup條件；通過也不等於下項tool-decision
   覆核或完整candidate通過。所有profile不得沿用舊bounded失敗allowance放行新版本。
3. 對完整輸入／raw另做獨立tool-decision覆核：需要且可執行的完整操作須選對工具及參數；
   缺值、禁止、資訊或當前不可用的操作須正確不操作。模型錯誤提案不能因Host拒絕而救分。
   合法`respond_to_user`的message仍須非空，但不以解釋完整、禁止確認措辭、複誦或完整
   重述提醒判tool-call成敗。既有`semantic_review_required`不是自動通過；review必須明記
   本輪是tool-decision範圍，不能混同舊完整回答語意。Capture／raw／source／manifest須可核對；
   不以關鍵字匹配替代判斷，也不因答覆而免除應執行工具的正向要求。
4. 保留歷史 74 個單輪輸入（36 positive、14 challenge、24 no-action）作固定廣度報告，
   另列新契約下逐題結果，不宣稱 74=81 或把已移除的七條跨輪計為成功。模型品質、
   Host admission、抑制執行的測量 terminal 與真產品副作用分開。所有 no-action 的
   confirmation、GUI 或執行副作用均為缺陷，不能用正向題分數抵銷。
5. 所有題目由 stage-consistent ApplicationViewPublication 經產品 assembler 產生
   state／callable schemas／blocked reasons，再走實際 LocalBackend template／budget。
   不手寫全 enabled catalog；必要資訊不得被 token packing 截斷。保存每次真 input、
   raw output、格式修復及 engine cleanup；report 檢查 capture bytes／hash／sequence。
6. RAG 使用產品 ProcessRAGRetrieverLifecycle 與同一 assembler。保存 query、allowed
   tools、returned／assembled IDs、context hash 和 ready-empty／degraded 區別。
   v5 離線准入保留 v4 的全部20個單輪案例（10 calibration＋10 review），含原相關標註、
   required IDs與unrelated安全反例；只為新語料補四個新示範的同主題ID。主題相關不是
   決策等效，標註先於觀测凍結。舊v4、v3及失敗報告保留歷史身分。
   語料為161筆、index schema 6；固定 corpus、fixture、embedding、設定與呈現後跑
   相同題目的 RAG on/off。最後送例相關性、模型受益與額外等待分開，不以有召回取代
   受益，不默默關閉 BM25 或換模型。不因基線高分要求任意漲幅，也不免除受益證據。
7. 真模型 normal ChatPanel 路徑完成 Switch Dataset → Import GUI → Select Channels →
   direct Resample，以及適用的 confirmation／cancel／GUI walkthrough。
   No-generation diagnostic 與 evaluator suppressed boundary 不能取代此產品 evidence。
   所有同 head applicable non-skipped CI 成功後，才交集中 Windows 真人手測並取得 merge 同意。

本輪固定案例先於生成封存；初次互通比較後只有具體根因才容許一次有界呈現修理，再驗
相同案例。仍不合格則不發布為可靠基線、不放寬分母、不無限調 prompt／語料／門檻，
也不要求使用者替不合格版本做驗收。這是本輪收斂界線，不是零缺陷或論文準確率宣稱。
研究的frozen source、DEV／VALID／TEST及repeats由外部封存擁有，不由產品gate改寫。

2026-09-28 後續核准的英文呈現候選另固定6個新問法（完整／缺值／否定各2），由
`stable_assistant_english_generalization_cases_v1.json` 擁有；與固定20題分開記錄，不用6題
替代原gate，不宣稱統計或論文holdout。26題各off/on一次（52首答），只允許既有格式
修復，不追加語意重試；模型錯答不能因Host擋錯救分。完整輸入覆核通過才生成，
所有首答／修復另保留，新增題不得猜缺值或違反否定等契約。不以RAG換字算受益。

### 研究封存界線 { #research-archive-boundary }

產品repository保留運作中的產品與必要工程gate，不再承載研究候選切換、歷史prompt重播、
研究題庫／評分／批次排程與報表工具。這些程式及專屬測試隨受測source留在研究封存；
研究期間修好的實際產品缺陷與仍有效的工程驗證繼續維護，不因來源是實驗就刪除。

- NAS完整實驗：`/mnt/home/2025/hxin/XBrainLab-experiments`。`snapshot/manifest.json`與
  `snapshot/sources/`綁定原始受測程式及執行入口；不得改用最新產品main重評歷史結果。
- NAS固定模型與環境：`/mnt/home/2025/hxin/XBrainLab-resources`。
- 外接備份：`E:\XBrainLabBackups\research-20261005-162606`，保存實驗、資源及本機研究文件封裝。
  2026-10-06補充的選版理由在NAS另存`research-notes/20261006-valid-selection`，
  E槽另存`documentation-addenda/20261006-valid-selection`，不改原封裝。

研究方法、選版時序、原始答案／分數及重現性限制由上述研究紀錄擁有，不在產品文件維護
第二份實驗進度表。NAS及E槽是此研究的保存位置，不是一般使用者安裝產品的依賴。
產品重構不回寫封存；相同題庫或重現相同分數不等於研究設計無偏，也不等於產品驗收。

### Braindecode catalog candidate

Braindecode catalog／legacy recovery變更在final exact source需閉合下列證據：

1. Catalog／license guard證明61個pinned upstream contracts、54個selectable classification models、57個
   permissive legacy sources、四個CC BY-NC exclusions，以及no-barrel discovery／no-Hub legacy closure。
2. Linux與Windows對54個selectable upstream IDs各執行compatible-context constructor、finite forward及
   finite gradient；macOS至少執行六個catalog family representatives。每個family另有一條real CPU
   one-epoch → selected checkpoint → safe artifact reload → evaluation → Gradient saliency workflow。
3. Exact-source UI artifact顯示searchable healthy catalog。Windows真人驗收再確認：搜尋`EEGNet`與
   `EEGConformer`、disabled reason、no-match／Cancel、100／125／150% DPI；以EEGNet及EEGConformer各走
   CPU one epoch、Evaluation與explicit Compute Saliency。
4. Provider unavailable walkthrough只可顯示distinct `legacy.braindecode.*` recovery IDs，不得自動改變原
   selection；explicit recovery selection完成後的artifact必須記錄legacy provider／revision。恢復provider後
   persisted legacy ID仍不得被rebind成upstream。

此candidate不宣稱scientific accuracy、預訓練權重品質、non-classification task、REVE position-bank支援，
或macOS真人desktop acceptance。

#### Assistant manual walkthrough commands

從repo root啟動，每份profile使用fresh process與fresh session；不加`--model`，diagnostic
transport不建立或載入Granite。JSON profile是executable step sequence authority；本節只保存啟動
方式與人工選擇，不複製call list。

Response Presentation：

```bash
poetry run python run.py --tool-debug scripts/dev/agent_tool_walkthrough/response-presentation.json
```

Contract Failures：

```bash
poetry run python run.py --tool-debug scripts/dev/agent_tool_walkthrough/contract-failures.json
```

GUI Cancellation Recovery：

```bash
poetry run python run.py --tool-debug scripts/dev/agent_tool_walkthrough/gui-cancellation.json
```

Complete Workflow：

```bash
poetry run python run.py --tool-debug scripts/dev/agent_tool_walkthrough/complete-workflow.json
```

Lifecycle / Routing：

```bash
poetry run python run.py --tool-debug scripts/dev/agent_tool_walkthrough/lifecycle-routing.json
```

開啟XBrainLab Assistant後，每次只送出目前step一次。Dialog、confirmation、navigation或
training尚未terminal時不送出下一步。Unexpected outcome必須留在同一step；記錄step ID、
可見terminal與screenshot後停止，不繼續污染session。

Complete Workflow使用已provision的
`$XBRAINLAB_DATA_DIR/datasets/public-fixtures/physionet-eegmmidb-S008R04.edf`：

- Import以embedded events將T1對應`left fist`、T2對應`right fist`，排除T0。
- Channel Selection套用一組有效EEG subset，至少保留畫面上的C3、Cz與C4。
- Channel與Montage都在Epoch前完成；Montage選當前可用的standard montage，再以EEG Epoch選T1／T2、`0–2` seconds。
- Data Split選Individual／Trial，validation與test皆為`0.2`。
- Model選EEGNet；Training Settings選CPU、1 epoch、batch 8、Adam、learning rate `0.001`。
- 先核准Start Training；若resource preflight另顯示確認，再核准該次receipt，等到training completed。
- 確認Evaluation與Visualization／Saliency Map可開啟；最後核准Compute Saliency，若另有resource
  confirmation則再核准，並等到同一operation顯示`Saliency ready`與腳本`Complete (19/19)`。

任一product source改動都使對應的manual acceptance失效；純docs／tests且不可能改變產品
行為的收尾依本文前述豁免規則處理。

Stage驗收另有一個硬邊界：匯入建立的working raw copy不算preprocessing。只有
`preprocessed.operations`非空（Channel或任一direct preprocess已成功）才可發布`preprocessed`；否則
必須是`data_loaded`並向模型發布Channel與五個direct preprocess工具。

### Staged product rebuild

An explicitly user-approved modular cleanup stage may use one integration PR with independently
reviewed, reversible commits instead of a PR per slice. Record that exception and its module closure
criteria in the active plan. Cumulative diff size does not trigger intermediate manual acceptance;
individual slices still undergo complexity review. Final same-source checks, independent integration
review and human acceptance remain mandatory. This exception does not authorize contract changes.

未採用上述使用者核准之單一階段PR例外時，跨多個bounded slices的產品重建可先在temporary
integration branch組裝，但該branch不是產品
baseline、release source或manual-acceptance對象：

- 每個slice仍需focused evidence、clean/explained source、PR與所有applicable non-skipped checks
  completed/success；integration不能成為較弱CI的避風港。
- Intermediate slice可保留尚未物理刪除但unpublished的migration source；不得同時發布兩套產品
  contract、加入runtime fallback或宣稱handoff-ready。
- Final rollup PR只能聚合已分片審查的commits，不得在rollup新增未審product behavior。其累積diff
  可超過單一slice門檻，但每個原始slice仍受complexity rules約束。
- 使用者只對同步最新main、完整automated evidence已閉合的frozen exact head進行manual
  acceptance。Head或合併基線改變時，必須重新建立candidate並重新取得適用的手測批准。
- Final main merge仍須精確核對base／head、CI及manual acceptance；integration內部成功不能替代。
- 合併後刪除temporary branch與其CI routing；rollback使用PR revert final merge，不保留隱藏雙路徑。

## Claim boundaries

- Format coverage不等於dataset diversity。
- Import成功不等於label semantics、split independence、model quality或saliency validity。
- Cross-fold Summary只對backend證明可pool的disjoint test masks成立。
- Launcher smoke不等於signed installer。
- Local Granite walkthrough不等於Assistant-ready或thesis benchmark。
- Windows真人驗收不能外推macOS、Linux、其他DPI/driver或其他dataset。

歷史執行細節由Git history保存；active狀態只讀[Current](../current.md)與[Now](../planning/now.md)。
