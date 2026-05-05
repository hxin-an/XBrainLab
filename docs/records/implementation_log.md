# XBrainLab Implementation Log

最後更新：`2026-05-05`

## 這份文件的用途

這份文件只記錄「高層次產品狀態」和「重要工程決策」。

它不再承擔逐 slice 實作細節、TDD 紅燈、完整 command output 或 artifact 清單。那些內容放在
`docs/records/worklog.md`。如果 implementation log 和 worklog 寫到同一件事，這裡只保留：

- 哪條產品主線前進了
- 目前可支撐什麼 claim
- 主要 evidence 入口在哪裡
- 還不能宣稱完成的是什麼
- 下一手 owner 應該看哪裡

## 文件分工

| 文件 | 職責 |
| --- | --- |
| `docs/current.md` | 目前真相：現在能做什麼、不能宣稱什麼、主要 blocker。 |
| `docs/planning/roadmap.md` | 產品主線：哪些 track 已有 baseline、哪些仍未達成成品。 |
| `docs/planning/now.md` | 短期施工焦點：下一輪應優先處理什麼。 |
| `docs/validation/README.md` | 驗證邊界：哪些 evidence 支撐哪些 claim。 |
| `docs/records/implementation_log.md` | 高層狀態快照：產品主線進度與交接判斷。 |
| `docs/records/worklog.md` | 細節流水帳：實作切片、失敗嘗試、測試命令、artifact 細節。 |

## Entry 格式

```md
## YYYY-MM-DD 主題

### 狀態

### 已可宣稱

### Evidence 入口

### 不能宣稱完成

### 下一手重點
```

## 2026-05-05 UI Controller Fallback Boundary Slices

### 狀態

The controller fallback audit now has explicit runtime boundaries for Training, Preprocess, Dataset,
Visualization, and AgentManager UI paths. Training sidebar fallback paths for split cleanup /
dataset generation, model selection, training settings, start / stop training, and clear history now
use `run_legacy_controller_fallback()`. Preprocess sidebar uses the same helper for filter /
resample / rereference / normalize / epoch / reset fallback. Dataset panel / sidebar / action
handler use it for metadata edit / batch metadata, smart parse, remove files, direct file import,
clear dataset, channel selection, and post-load label compatibility fallback. Visualization saliency
settings and AgentManager montage confirmation also use the helper. The helper allows fallback only
for mock / legacy non-`Study` contexts and refuses fallback when a real `Study` unexpectedly does
not return a `CommandResult`. `tests/architecture_compliance.py` now guards this boundary by
failing direct controller mutation calls inside UI `result is None` branches unless they go through
the explicit fallback helper.

### 已可宣稱

- Training, Preprocess, Dataset, Visualization, and AgentManager real product runtime will not
  silently mutate their controllers if the command helper fails to provide an ApplicationService
  result.
- Existing mock / legacy unit-test compatibility fallback remains available.
- The architecture compliance gate now prevents reintroducing direct controller mutation fallback
  inside missing-command-result branches.

### Evidence 入口

- Code: `XBrainLab/ui/application_capabilities.py`, touched UI fallback call sites,
  `tests/architecture_compliance.py`
- Tests: focused UI fallback tests plus `tests/architecture_compliance.py`
- Detailed validation commands：`docs/records/worklog.md`

### 不能宣稱完成

- This is not full UI architecture closure. Remaining work is to audit the non-controller
  `result is None` branches, then continue reducing observer/manual refresh paths.

### 下一手重點

Audit remaining UI `result is None` branches to confirm they are service-unavailable error handling,
not product runtime mutation fallback; then continue the command-driven refresh coordinator cleanup.

## 2026-05-05 Training Readiness Refresh Cleanup

### 狀態

Training sidebar is the first manual-refresh cleanup under the command refresh coordinator. Service
success paths for generate dataset, configure model, configure training settings, start training,
and clear history no longer call `check_ready_to_train()` directly from the action handler. They now
leave real `Study` readiness refresh to `refresh_after_command()` and `training_panel.update_panel()`.
Mock / legacy non-`Study` fallback still refreshes readiness manually.

### 已可宣稱

- Training readiness no longer has duplicated service-success refresh logic in the action handler.
- Legacy fallback behavior remains covered.

### Evidence 入口

- Code: `XBrainLab/ui/panels/training/sidebar.py`
- Test: `tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_start_training_service_success_uses_coordinator_for_readiness`
- Detailed validation commands：`docs/records/worklog.md`

### 不能宣稱完成

- This does not complete UI refresh target architecture. Dataset / Preprocess / other panels still
  contain manual `update_panel()` refresh paths that need the same treatment.

### 下一手重點

Apply the same service-success versus legacy-fallback split to Dataset and Preprocess manual
`update_panel()` calls, then consider an architecture guard for duplicated post-command local
refresh.

## 2026-05-05 Dataset Action Refresh Cleanup

### 狀態

Dataset action handler now applies the same coordinator-owned refresh split for smart parse, batch
metadata updates, and remove files. Service-backed success paths no longer call
`panel.update_panel()` directly; mock / legacy fallback still refreshes manually.

### 已可宣稱

- Three common Dataset mutating actions no longer duplicate service-success panel refresh.
- Legacy fallback update behavior remains covered.

### Evidence 入口

- Code: `XBrainLab/ui/panels/dataset/actions.py`
- Test: `tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_remove_files_service_success_uses_coordinator_refresh`
- Detailed validation commands：`docs/records/worklog.md`

### 不能宣稱完成

- This does not finish Dataset refresh cleanup. Data Interpretation apply, import labels, and inline
  metadata table refresh paths still need review.

### 下一手重點

Continue Dataset refresh cleanup on import-label compatibility and inline metadata edit, then
consider a static guard for duplicated post-command manual refresh if it can avoid false positives.

## 2026-05-05 Data Interpretation / Label Compatibility Refresh Cleanup

### 狀態

Data Interpretation import/apply and saved recipe reload apply now follow the same refresh boundary:
successful `ApplyInterpretationCommand` paths no longer call `DatasetPanel.update_panel()` directly.
The Dataset panel refresh is owned by `execute_application_command()` and
`refresh_after_command()` based on `CommandResult.changed_state`. Post-load label compatibility
also follows that boundary for service-backed `ImportLabelsCommand` success; only mock / legacy
`None` fallback refreshes manually. Direct `LoadDataCommand` compatibility fallback also no longer
duplicates Dataset panel refresh on service success.

### 已可宣稱

- Data Interpretation file import, folder/BIDS import, and recipe reload apply no longer duplicate
  Dataset panel refresh in the action handler on service success.
- Service-backed post-load label compatibility no longer duplicates Dataset panel refresh.
- Service-backed direct-load compatibility no longer duplicates Dataset panel refresh.
- Existing service-unavailable handling remains explicit instead of falling back to controller
  mutation.

### Evidence 入口

- Code: `XBrainLab/ui/panels/dataset/actions.py`
- Tests: `tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler`
- Detailed validation commands：`docs/records/worklog.md`

### 不能宣稱完成

- This does not finish the UI refresh target architecture. Inline metadata table refresh,
  observer events, and tab-switch refresh still need audit. Post-load label compatibility remains
  a legacy compatibility path, and direct load remains a compatibility fallback, not the Data
  Interpretation-first product workflow.

### 下一手重點

Continue the coordinator cleanup on remaining Dataset refresh paths and add broader refresh-scope
tests only where they can observe user-facing behavior instead of only mock calls.

## 2026-05-05 Dataset Sidebar Refresh Cleanup

### 狀態

Dataset sidebar channel selection and clear dataset actions now use the same coordinator-owned
refresh boundary. Service-backed `PreprocessCommand(SELECT_CHANNELS)` and
`ResetSessionCommand` success paths do not directly call `DatasetPanel.update_panel()`; only mock /
legacy `None` fallback refreshes manually.

### 已可宣稱

- Channel selection and clear dataset sidebar service-success paths no longer duplicate panel
  refresh.
- Mock / legacy fallback behavior remains covered.

### Evidence 入口

- Code: `XBrainLab/ui/panels/dataset/sidebar.py`
- Tests: `tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar`
- Detailed validation commands：`docs/records/worklog.md`

### 不能宣稱完成

- This does not finish UI refresh target architecture. Inline metadata table refresh, observer
  events, tab-switch refresh, and callback-driven refresh remain separate mechanisms.

### 下一手重點

Continue with Dataset panel inline metadata refresh or classify callback / observer refresh paths
before adding broader architecture guards.

## 2026-05-05 Dataset Inline Metadata Refresh Cleanup

### 狀態

Dataset table inline subject/session edits now use a legacy-only local refresh helper. Service-backed
`UpdateMetadataCommand` success paths no longer call `DatasetPanel.update_panel()` directly; mock /
legacy `None` fallback still refreshes manually.

### 已可宣稱

- Inline subject/session metadata service-success paths no longer duplicate panel refresh.
- Existing mock / legacy controller update behavior and backend capability read-only behavior remain
  covered.

### Evidence 入口

- Code: `XBrainLab/ui/panels/dataset/panel.py`
- Tests: `tests/unit/ui/dataset/test_panel.py`
- Detailed validation commands：`docs/records/worklog.md`

### 不能宣稱完成

- This does not finish UI refresh target architecture. Observer bridge refresh, tab-switch refresh,
  import-finished callbacks, and training/preprocess lifecycle callbacks remain separate mechanisms.

### 下一手重點

Classify remaining callback-driven refreshes before deciding whether to refactor them into the
coordinator or preserve them as explicit observer/event bridges.

## 2026-05-05 Preprocess Sidebar Refresh Cleanup

### 狀態

Preprocess sidebar operation and reset service-success paths now use coordinator-owned refresh.
Filter, resample, rereference, normalize, epoch, and reset no longer call `notify_update()` or
`update_info_panel()` after successful service-backed commands. Mock / legacy `None` fallback still
refreshes manually.

### 已可宣稱

- Preprocess sidebar mutating command success no longer duplicates panel or main-info refresh.
- Existing mock / legacy fallback update behavior remains covered.

### Evidence 入口

- Code: `XBrainLab/ui/panels/preprocess/sidebar.py`
- Tests: `tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar`
- Detailed validation commands：`docs/records/worklog.md`

### 不能宣稱完成

- This does not finish UI refresh target architecture. Callback-driven training/preprocess state
  changes, observer bridges, and tab-switch refresh remain separate mechanisms.

### 下一手重點

Classify remaining callback / observer refresh paths and avoid converting them blindly unless the
coordinator can preserve event semantics.

## 2026-05-05 Visualization Control Refresh Cleanup

### 狀態

Visualization control sidebar montage and saliency service-success paths now use coordinator-owned
refresh. Successful `ApplyMontageCommand` and `SaliencyCommand` no longer call
`VisualizationPanel.on_update()` directly; mock / legacy saliency fallback still refreshes manually.

### 已可宣稱

- Visualization control service-success paths no longer duplicate panel refresh.
- Legacy saliency fallback remains covered.

### Evidence 入口

- Code: `XBrainLab/ui/panels/visualization/control_sidebar.py`
- Tests: `tests/unit/ui/visualization/test_control_sidebar.py`
- Detailed validation commands：`docs/records/worklog.md`

### 不能宣稱完成

- This does not finish visualization product acceptance. Interactive desktop 3D / PyVista render,
  human desktop acceptance, and callback-driven UI refresh remain open.

### 下一手重點

Continue classifying remaining callback / observer refresh paths and keep product visualization
evidence separate from command-spine cleanup.

## 2026-05-05 UI Command Refresh Coordinator First Slice

### 狀態

The first `UI Command Refresh Coordinator + Controller Fallback Audit` implementation slice is in
place. Real `Study` UI command execution now calls a centralized refresh helper after
`ApplicationService.execute()` and maps `CommandResult.changed_state` to the main workflow panels,
main info panel, and assistant backend status. Evaluation / visualization query-only updates opt out
of recursive refresh, and the coordinator has a same-window re-entrancy guard.

### 已可宣稱

- There is now a concrete command-result-driven refresh spine for UI commands.
- The first slice has focused unit coverage and broader offscreen UI regression coverage.

### Evidence 入口

- Code: `XBrainLab/ui/refresh_coordinator.py`
- Tests: `tests/unit/ui/test_refresh_coordinator.py`、
  `tests/unit/ui/test_application_capabilities.py`
- Detailed validation commands：`docs/records/worklog.md`

### 不能宣稱完成

- This is not full UI refresh target closure.
- Controller observer events, panel-local manual refresh, tab-switch refresh, and remaining
  product-runtime controller fallback still need audit.

### 下一手重點

Continue the same milestone by separating product runtime service-success paths from mock / legacy
controller fallback, then gradually move panel refresh scope decisions into the coordinator.

## 2026-05-05 Local Tool-Call 121-Case Rerun

### 狀態

Remap-expanded tool-call suite 已完成 deterministic、primary local 和 fallback local 同套
`121` cases 重跑。這輪修正 local model 常見但可安全正規化的 output variants：recipe remap
alias tools、missing remap target placeholder、stale preview source path、metadata override string
maps、unrequested label-review noise、task/run generated prefixes、dataset missing test split ratio
和 bandpass frequency aliases。

### 已可宣稱

- `microsoft/Phi-4-mini-instruct` primary local model：`121 / 121`，repeat count `3`。
- `microsoft/Phi-3.5-mini-instruct` fallback local model：`121 / 121`，repeat count `3`。
- Dashboard 顯示 deterministic / primary / fallback 在同一 `121` case suite 上都是 `100%` pass，
  repeated-run stability 也是 `100%`。

### Evidence 入口

- Dashboard：`artifacts/agent_evals/dashboard.md`
- Primary：`artifacts/agent_evals/local_primary/local_microsoft_phi_4_mini_instruct.md`
- Fallback：`artifacts/agent_evals/local_fallback/local_microsoft_phi_3.5_mini_instruct.md`
- Detailed commands：`docs/records/worklog.md`

### 不能宣稱完成

- 這支撐 saved benchmark slice 的 thesis-candidate tool-call claim，但不是 product-complete。
- 這不取代 Windows human desktop acceptance、mature import wizard、MCP HTTP / long-running jobs、
  ChatPanel 長時間 workflow 或完整 release validation。

### 下一手重點

把 benchmark evidence 整理成 thesis report protocol，同時回到產品缺口：UI refresh coordinator、
controller fallback audit、mature Data Interpretation editor 和 human desktop acceptance。

## 2026-05-05 UI Command Refresh Coordinator Follow-up

### 狀態

Backend command spine 已比早期乾淨很多，`ApplicationService` 目前主要回到 dispatch /
capability-confirmation gate / result envelope，多數 workflow 細節也已拆到 focused command
services。但 reviewer finding 已確認 target architecture 尚未 closure：UI refresh 仍是
controller observer events、manual panel refresh、tab switch refresh、command result local refresh
和 ChatPanel / agent Qt signal path 的混合模式。

### 已可宣稱

- Backend command spine baseline 已大幅改善，且可作為後續 UI refresh cleanup 的依據。
- 這個 finding 已進入 current truth / planning follow-up，而不是被包裝成完成。

### Evidence 入口

- Current truth：`docs/current.md`
- Short-term plan：`docs/planning/now.md`
- Roadmap milestone：`docs/planning/roadmap.md`

### 不能宣稱完成

- 不能宣稱 backend / UI architecture fully aligned。
- 不能宣稱 product runtime mutating path 已完全沒有 controller fallback。
- 不能把 Data Interpretation baseline wizard 宣稱成 final import system。

### 下一手重點

執行 `UI Command Refresh Coordinator + Controller Fallback Audit`：集中處理
`CommandResult.changed_state -> panel / capability / assistant status refresh`，並把 product
runtime service-success path 與 mock / legacy controller fallback 明確分離。

## 2026-05-05 Recipe Reload Difference Review

### 狀態

Recipe reload preview now compares saved recipe selections with the current rescan before validation.
The backend preview payload exposes reviewable diff rows for EEG files, label carriers, and saved
choices; the Data Interpretation wizard renders those rows in `Review Summary`. Follow-up hardening
also blocks reload candidates when a saved selected EEG file is missing from the current scan, so
apply cannot fall through into a runtime import failure. The same blocker now covers missing saved
label/event carriers, so external labels cannot be silently dropped during recipe replay. Backend
remap support now lets a saved EEG file or saved carrier be explicitly mapped to a replacement item
in the current scan while preserving saved metadata / label field / anchor / role choices. The
wizard now exposes those remaps as user-facing selectors, then re-previews and re-validates before
apply.

### 已可宣稱

- Reloaded recipes no longer show only a generic `reapplied` message; the user can see whether saved
  files / label carriers still match the current scan.
- Missing saved EEG files and label/event carriers are now validation blockers before apply.
- Explicit backend `eeg_file_remap` can clear the missing-selected-file blocker and preserve saved
  metadata overrides on the replacement file.
- Explicit backend `label_carrier_remap` can clear the missing-carrier blocker and preserve saved
  choices on the replacement carrier.
- The UI can resolve simple renamed-file and renamed-carrier cases without falling through to a
  dead-end blocked dialog.
- Human-like walkthrough evidence was refreshed, including `07-recipe-reloaded.png`.

### Evidence 入口

- Backend/UI tests：`tests/unit/backend/application/test_data_interpretation_review.py`、
  `tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py`
- Workflow test：`tests/integration/backend/test_application_service_workflow.py`
- Remap screenshot：`artifacts/ui/data-interpretation-remap.png`
- Artifact：`artifacts/ui/human-like-walkthrough/07-recipe-reloaded.png`
- Walkthrough report：`artifacts/ui/human-like-walkthrough/human-like-walkthrough.md`

### 不能宣稱完成

- 這不是完整 recipe diff editor，也不是人類 Windows desktop acceptance。
- 這不處理複雜 recipe conflict resolution 或 anchor reconciliation；目前是 simple replacement
  selector。

### 下一手重點

把 same pattern 延伸到更成熟的 import wizard conflict handling：missing source、multi-file
matching heuristics、anchor reconciliation 和 embedded label editor。

## 2026-05-05 Data Entry Routing And Dataset Table Fit

### 狀態

General user wording such as `Load ...` / `Import my EEG folder ...` now routes to Data
Interpretation `scan_source` instead of the legacy `load_data` compatibility path, while explicit
legacy / direct compatibility wording still maps to `load_data`. The saved 118-case deterministic,
primary, and fallback local tool-call artifacts were refreshed on cached non-China local models.

The Dataset / Data Interpretation UI also received a focused product polish pass: preview dialog
tables now fit their panels with stretch + elide behavior, `Review Summary` uses lower-contrast dark
alternating rows, and the Dataset table keeps interactive columns while assigning remaining width
to `File` so loaded rows fill the main panel without squeezing filenames.

### 已可宣稱

- New data-entry language in agent eval now prefers Data Interpretation for normal file / folder /
  BIDS import requests.
- Automated UI replay evidence shows Dataset table columns fill the main panel, and `Events` /
  `Labels` visible text separates recording events from external labels without using success-green
  coloring for labels.
- Tool-call benchmark artifacts still show deterministic / primary / fallback `118 / 118`, with
  primary and fallback each repeated `3` times.

### Evidence 入口

- Tool-call dashboard：`artifacts/agent_evals/dashboard.md`
- Data Interpretation replay：`artifacts/ui/data-interpretation-replay.json`
- Screenshots：`artifacts/ui/data-interpretation-preview.png`、
  `artifacts/ui/data-interpretation-applied.png`
- Detailed commands：`docs/records/worklog.md`

### 不能宣稱完成

- 這仍不是 Windows human desktop acceptance、完整 mature import wizard、長時間 ChatPanel
  workflow 或 MCP HTTP / long-running automation closure。
- 這個 UI pass 修的是 table fit / contrast / Dataset table semantics，不是全介面重設計。

### 下一手重點

繼續把 mature Data Interpretation editor、assistant narrow composition、Windows launcher 真人驗收
和 long-running MCP / local-model workflow 分開驗證，不要讓 benchmark PASS 蓋過產品缺口。

## 2026-05-05 Walkthrough Resource Smoke Boundary

### 狀態

Consolidated automated human-like walkthrough 不只保存 screenshots、visible text 和 backend
snapshots，現在也把 close 後的 process/thread cleanup 納入 pass/fail smoke。這把 resource
notes 從「附錄紀錄」提升為可 fail 的 validation boundary，但仍明確限定為 coarse smoke。

### 已可宣稱

- UI-observable walkthrough artifact 會 gate obvious Python thread、Qt thread-pool 和 RSS
  high-water cleanup regression。
- 最新 artifact 仍是 `26 / 26` phases、`20` screenshots、resource smoke passed。

### Evidence 入口

- Script：`scripts/dev/capture_human_like_product_walkthrough.py`
- Unit gate：`tests/unit/scripts/test_capture_human_like_product_walkthrough.py`
- Artifact：`artifacts/ui/human-like-walkthrough/human-like-walkthrough.md`

### 不能宣稱完成

- 這不是 leak-proof soak test，也不是長時間 local model / training resource acceptance。
- 這仍不是 Windows launcher、雙螢幕或 DPI human desktop verification。

### 下一手重點

把同樣的 lifecycle thinking 延伸到 long-running local model、training / visualization jobs、
cancel/cleanup 和 repeated open/close UI smoke。

## 2026-05-05 Visible Data Entry Language Cleanup

### 狀態

ChatPanel / AgentManager 的 visible next-step language 現在以 Data Interpretation 為資料入口主線。
空狀態顯示 `Scan data source`，raw-loaded 狀態不再把 legacy `attach_labels` 包成下一步建議；
ChatPanel status rendering 也會過濾 legacy compatibility commands。若 legacy compatibility tool
仍因測試或相容路徑被觸發，visible fallback label 也改成中性的 `Import data` /
`Add labels to loaded data`，不再回到舊的 `Load EEG data` / `Attach labels` 主流程語言。

### 已可宣稱

- 新使用者看到的 assistant empty-state / next-step status 不再以 `load_data` /
  `attach_labels` 作為資料入口心智模型。
- Consolidated walkthrough artifact 已刷新，visible text 沒有 legacy command leakage。

### Evidence 入口

- UI logic：`XBrainLab/ui/components/agent_manager.py`、`XBrainLab/ui/chat/panel.py`
- UI tests：`tests/unit/ui/chat/test_chat_panel.py`、
  `tests/unit/ui/components/test_agent_manager.py`
- Artifact：`artifacts/ui/human-like-walkthrough/human-like-walkthrough.md`

### 不能宣稱完成

- Legacy compatibility tools 仍存在於 backend compatibility service、parser / schema compatibility
  和部分 historical tests；這個 slice 只移除可見 product-status 主路徑。
- 這不是完整 import wizard UX closure 或 human desktop acceptance。

### 下一手重點

盤點剩餘 legacy real-tool / RAG gold-set / test expectations，確認它們是 compatibility coverage
而不是產品主語言。

## 2026-05-05 RAG Legacy Example Policy

### 狀態

RAG prompt context 現在跟 agent primary tool surface 使用同一個資料入口邊界：含
`load_data`、`attach_labels` 或 `import_labels` 的 bundled gold-set examples 不會被建入
新 index，也會在 BM25 / dense retriever 回傳後、格式化進 prompt 前被過濾。這避免舊 few-shot
example 把 local LLM 帶回 legacy data-entry tools。

### 已可宣稱

- 新建 RAG index 不會收 legacy data-entry examples。
- 已存在的舊 Qdrant collection 即使回傳 legacy candidate，也會在 prompt 注入前被排除。
- RAG / assembler focused regression 通過。

### Evidence 入口

- Policy：`XBrainLab/llm/rag/example_policy.py`
- Boundaries：`XBrainLab/llm/rag/indexer.py`、`XBrainLab/llm/rag/bm25.py`、
  `XBrainLab/llm/rag/retriever.py`
- Tests：`tests/unit/llm/rag/test_example_policy.py`

### 不能宣稱完成

- 這不是 RAG corpus 全面重寫；gold set 仍需要補更多 Data Interpretation positive /
  blocked / recovery examples。
- 這不取代 118-case local LLM tool-call eval 或 ChatPanel true local-model walkthrough。

### 下一手重點

把剩餘 historical RAG examples 轉成 Data Interpretation-first examples，並確認 real-tool legacy
tests 只覆蓋 compatibility，不再當作 product prompt evidence。

## 2026-05-05 MCP Stdio Adapter Session Boundary

### 狀態

MCP stdio `tools/call` result 現在明確帶 headless adapter metadata：mode、transport、stable
session id 和 UI refresh boundary。這讓 external clients 可以分辨「MCP server 擁有自己的
ApplicationService session」和「正在控制使用者桌面 UI」是兩件不同的事。後續 hardening
也把 stdio `train` 的 error precedence 收斂到 backend truth：unready training 先回 capability
precondition；只有 backend-ready / enabled 的 long-running training 才回
`long_running_job_required`，避免 external client 以為 missing dataset / model 只是 job API
尚未實作。

### 已可宣稱

- MCP stdio tool calls 仍走 `ApplicationService` / automation payload；structured result 現在含
  `adapter.mode=headless_mcp_stdio`、`transport=stdio`、stable `session_id` 和
  `ui_refresh.supported=False`。
- MCP stdio 對 unready `train` 保留 backend precondition reason；對 enabled long-running
  `train` 才會回 recoverable job-boundary error，不會同步啟動長時間訓練。
- stdlib-only MCP client walkthrough artifact 已刷新並在 Markdown summary 顯示 adapter boundary。

### Evidence 入口

- Unit / integration tests：`tests/unit/mcp/test_server.py`、
  `tests/integration/mcp/test_stdio_walkthrough_artifact.py`
- Artifact：`artifacts/mcp/stdio-walkthrough.json` / `.md`

### 不能宣稱完成

- 這不是 MCP Streamable HTTP transport，也不是 long-running training job/cancel/progress model。
- 這不是 desktop UI control certification；stdio MCP 是 headless session。

### 下一手重點

設計 HTTP/session ownership、auth、job progress、cancel/recovery 和 resource lock，再把
long-running MCP tool boundary 從 explicit block 升級成真 job API。

## 2026-05-05 Data Interpretation Review Summary UI

### 狀態

Data Interpretation wizard 的 review surface 往 mature import wizard 再收斂一步：warnings、
confirmations、blocked reasons、downstream impact、recipe trace 和 format capability boundary
不再以 plain text review dump 顯示，而是放進可掃描的 `Review Summary` table。可見流程文字也改成
`Select source | Scan result | Preview | Confirm | Apply | Save recipe`，更接近使用者操作路徑。

### 已可宣稱

- Data Interpretation preview dialog 現在以 structured review rows 呈現 label / metadata /
  format boundary，不顯示 raw schema 或 traceback。
- Data Interpretation replay artifact 和 consolidated human-like walkthrough artifact 已刷新；後者
  仍明確標示 human desktop acceptance 未執行。

### Evidence 入口

- Dialog test：`tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py`
- Replay artifact：`artifacts/ui/data-interpretation-replay.json`
- Screenshots：`artifacts/ui/data-interpretation-preview.png`、
  `artifacts/ui/human-like-walkthrough/04-interpretation-preview.png`、
  `artifacts/ui/human-like-walkthrough/05-interpretation-confirm.png`
- Consolidated walkthrough：`artifacts/ui/human-like-walkthrough/human-like-walkthrough.md`

### 不能宣稱完成

- 這是 wizard review surface polish，不是 full mature import wizard：raw trigger selector、
  complex MAT/GDF anchor reconciliation、XDF/LSL stream selection 和 real-data manual certification
  仍未完成。
- Offscreen automated walkthrough 仍不是 Windows launcher / 雙螢幕 / DPI human acceptance。

### 下一手重點

繼續補 mature label/anchor editor 與 real-data capability boundary，同時推進 ChatPanel 長鏈和
MCP long-running boundary。

## 2026-05-05 Data Interpretation Event Role Selector

### 狀態

Data Interpretation wizard 的 event role review 從任意 free-text cell 收斂成 selector control。
使用者會看到 `Class cue`、`Time anchor` 等可辨識選項；recipe choices 仍保存 backend value
如 `class cue`。Replay script 也改為透過 selector 操作 event role，並把 `event_rows` 寫入
artifact，避免 transcript 說已確認但 UI state 沒有被 selector 實際更新。

### 已可宣稱

- Event role review 不再要求使用者手打 role text。
- Data Interpretation replay artifact 可見 `trial_type -> event role -> Class cue`。
- Consolidated automated human-like walkthrough 已刷新且仍通過，但仍不是 human desktop acceptance。

### Evidence 入口

- Dialog test：`tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py`
- Replay helper test：`tests/unit/scripts/test_capture_data_interpretation_replay.py`
- Replay artifact：`artifacts/ui/data-interpretation-replay.json`
- Screenshots：`artifacts/ui/data-interpretation-preview.png`、
  `artifacts/ui/human-like-walkthrough/04-interpretation-preview.png`
- Consolidated walkthrough：`artifacts/ui/human-like-walkthrough/human-like-walkthrough.md`

### 不能宣稱完成

- 這是 event role selector polish，不是 full mature import wizard：raw trigger selector、
  complex MAT/GDF anchor reconciliation、XDF/LSL stream selection、real-data manual certification
  和 Windows / DPI / dual-monitor human acceptance 仍未完成。

## 2026-05-05 Data Interpretation Recipe Reload Rehydration

### 狀態

Recipe reload 不再只讀 saved source path 後重建空 candidate。`ReloadInterpretationRecipeCommand`
現在會把 saved selected EEG files、metadata overrides、label carrier choices、event roles 和
class map 轉回 candidate builder 的 `choices`，再重新 scan / preview / validate。這讓 saved
recipe reload 保留使用者曾確認的資料語意，而不是只保留檔案位置。

### 已可宣稱

- Reloaded recipe preview 會帶回 saved metadata / label / event choices。
- Non-mocked source -> apply -> save recipe -> reload workflow 已覆蓋此行為。
- Human-like walkthrough artifact 的 reload command result 可見 rehydrated choices 和
  `choices:*` recipe trace。
- Human-like walkthrough 的 `07-recipe-reloaded.png` 現在是 reload preview dialog，phase notes
  保存 `Reloaded recipe / Reapplied` review row。

### Evidence 入口

- Unit：`tests/unit/backend/application/test_data_interpretation_recipe.py`
- Integration：`tests/integration/backend/test_application_service_workflow.py`
- Artifact：`artifacts/ui/human-like-walkthrough/human-like-walkthrough.json`

### 不能宣稱完成

- 這是 recipe rehydration + reload summary，不是完整 recipe diff UI。
- Human-like artifact 仍是 automated PyQt replay，不是 Windows human desktop acceptance。

## 2026-05-05 Tool-Call Local 118-Case Scoring Hardening

### 狀態

Tool-call benchmark 已用同一 `118` thesis-candidate cases 刷新 deterministic、primary local
model 和 fallback local model。這輪同時收緊 blocked-state scoring：direct blocked command 可被
verification / capability policy 擋下並回覆使用者；blocked intent 下改叫 reset、scan、
configure 等替代 tool 會算 failure，不再被舊 scorer 誤當成 pass。

### 已可宣稱

- deterministic eval、`microsoft/Phi-4-mini-instruct` primary eval 和
  `microsoft/Phi-3.5-mini-instruct` fallback eval 都是 `118 / 118`，local model 各重跑 `3`
  次。
- dashboard 已同步顯示 model comparison、case family、metric breakdown、failure taxonomy、
  worst cases 和 artifact paths。

### Evidence 入口

- Dashboard：`artifacts/agent_evals/dashboard.md`
- Primary local report：`artifacts/agent_evals/local_primary/local_microsoft_phi_4_mini_instruct.md`
- Fallback local report：`artifacts/agent_evals/local_fallback/local_microsoft_phi_3.5_mini_instruct.md`
- Validation record：`docs/validation/README.md`

### 不能宣稱完成

- 這支撐 tool-call benchmark claim，不是 UI / launcher / MCP HTTP / import wizard product
  completion。
- apply-lock local output 可被 verifier 視為 direct blocked command；它不是實際執行成功，也不是
  full natural-language no-call UX acceptance。

### 下一手重點

把 118-case benchmark 整理成 thesis report evidence，同時繼續推進 UI-observable import wizard、
ChatPanel 長鏈、Windows human acceptance 和 MCP long-running boundary。

## 2026-05-05 Tool-Call Apply Lock Eval Coverage

### 狀態

Tool-call eval suite 現在把剛補上的 `apply_interpretation` raw-edit boundary 納入 benchmark：
當 session 已有 epoch / downstream lock，且使用者要求套用新 Data Interpretation 並誘惑 assistant
改叫 scan 新路徑時，deterministic expectation 是 blocked / no tool call。

### 已可宣稱

- Deterministic scorer 會檢查 downstream-locked Data Interpretation apply 不可用替代工具硬推。
- `artifacts/agent_evals/latest.*` 和 dashboard 已刷新為 deterministic `118 / 118`。

### Evidence 入口

- Source：`scripts/agent/evals/run_tool_call_eval.py`
- Test：`tests/integration/agent/test_tool_call_eval.py`
- Artifact：`artifacts/agent_evals/latest.md`
- Dashboard：`artifacts/agent_evals/dashboard.md`

### 不能宣稱完成

- 此 deterministic-only boundary 已被上方 local 118-case rerun supersede；仍不可把 tool-call
  benchmark 擴張成 product-complete 或 UI acceptance claim。
- 這不是 ChatPanel human walkthrough、Windows acceptance 或 product-complete claim。

### 下一手重點

後續 local LLM eval rerun 應使用 `118` cases，確認 primary / fallback 對 apply-lock wrong-tool
temptation 的真輸出仍穩定。

## 2026-05-05 Apply Interpretation Raw-Edit Boundary

### 狀態

Backend capability policy 現在會把 raw-edit blockers 套到 `apply_interpretation`。如果 active
session 已有 epoch、generated dataset、trainer 或 locked raw data，UI / agent / MCP 都會看到同一個
reset/new-session blocked reason；`ApplyInterpretationCommand` 不會呼叫 import side effect。

### 已可宣稱

- Data Interpretation apply 不再只看 semantic validation，也會尊重 active pipeline mutation
  boundary。
- Agent / MCP 無法透過 `apply_interpretation` 繞過 UI lock，把新資料套進已有 downstream pipeline。
- 已有 focused regression 覆蓋 blocked command 不呼叫 `dataset.import_files()`。

### Evidence 入口

- Source：`XBrainLab/backend/application/capabilities.py`
- Test：`tests/unit/backend/application/test_application_service.py`
- Detailed validation：`docs/records/worklog.md`

### 不能宣稱完成

- 這不是完整 reset/new-session product walkthrough，也不是 MCP long-running job boundary。
- Data Interpretation mature wizard 和 Windows human acceptance 仍未完成。

### 下一手重點

繼續盤點其他 mutating commands 是否仍有 UI-only blockers，特別是 recipe reload / label apply /
visualization setup 的 capability 與 visible blocked reason。

## 2026-05-05 Data Source Entry UI Options

### 狀態

Dataset sidebar 的 Data Interpretation source entry 不再只露出 EEG file picker。UI 現在明確提供
`Interpret Data Source`、`Interpret Folder / BIDS` 和 `Reload Import Recipe` 三個入口；folder /
BIDS root 和 recipe reload 都直接走 Data Interpretation command path，不靠 legacy controller
fallback。

### 已可宣稱

- 使用者在 Dataset sidebar 第一層就看得到 file、folder/BIDS root 和 saved recipe 三種資料來源。
- Folder/BIDS 和 recipe entry 會進入 scan / recipe reload -> preview -> validate ->
  confirm/apply 的 Data Interpretation flow。
- Recipe reload 會讀 `reload_interpretation_recipe` capability gate，不再沿用 scan-source gate。
- 新入口有 focused UI tests 和 automated sidebar screenshot evidence。

### Evidence 入口

- Source：`XBrainLab/ui/panels/dataset/actions.py`
- Source：`XBrainLab/ui/panels/dataset/sidebar.py`
- Artifact：`artifacts/ui/data-source-entry-options/`
- Detailed validation：`docs/records/worklog.md`

### 不能宣稱完成

- 這不是 mature embedded label editor、raw trigger selector、recipe-diff UI 或 full human desktop
  acceptance。
- Reload recipe 仍是 review/apply entry，不代表所有 recipe semantic replay edge cases 已人工驗收。

### 下一手重點

後續 Data Interpretation UI work 應聚焦 embedded label/anchor editor、recipe reload diff、
BIDS sidecar visibility 和 complex external label reconciliation。

## 2026-05-05 Agent Data-Entry Tool Surface Downgrade

### 狀態

Agent stage prompt / tool exposure 已把 legacy `load_data / attach_labels` 從 Empty、
Data Loaded 和 Preprocessed 的 primary workflow language 移除。Context Assembler 現在會將
ApplicationService capability policy 與 stage allowlist 取交集，避免 backend compatibility
policy 把已降權的 legacy tools 重新放回 prompt。legacy tools 仍保留在 schema taxonomy、
parser / verification 和 compatibility service 裡，定位為相容入口而不是新資料入口主線。

### 已可宣稱

- In-app agent 的 primary data-entry prompt 已以 Data Interpretation scan / preview /
  validate / apply / recipe 為主。
- Backend capability policy 不能再單獨把 stage-filtered legacy data-entry tool 重新曝光到主
  prompt。
- Compatibility tools 仍可被 parser / verifier 辨識，沒有為了降權而刪掉相容面。

### Evidence 入口

- Source：`XBrainLab/llm/pipeline_state.py`
- Source：`XBrainLab/llm/agent/assembler.py`
- Source：`XBrainLab/llm/agent/confidence.py`
- Detailed validation：`docs/records/worklog.md`

### 不能宣稱完成

- 這不是完整 legacy data-entry removal；UI post-load label compatibility、MCP/client-facing
  language 和長時間 ChatPanel workflow 仍要繼續盤點。
- 這不是 UI import wizard maturity、Windows human acceptance 或 product-complete claim。

### 下一手重點

下一輪應檢查 UI / MCP / docs 是否還把 `load_data / attach_labels` 當 primary workflow
language，並繼續把使用者入口收斂到 Data Interpretation wizard / recipe flow。

## 2026-05-05 Automation / MCP Legacy Compatibility Metadata

### 狀態

Headless command schema 和 MCP `tools/list` 現在會把 legacy data-entry commands 標成
compatibility，而不是 primary workflow。`load_data`、`attach_labels`、`import_labels` 的
`AutomationCommandSpec` 和 MCP `x_xbrainlab` metadata 都包含 `legacy_compatibility=True`、
`primary_workflow=False` 和 Data Interpretation preferred commands。

### 已可宣稱

- MCP/headless client-facing schema 不再把 legacy data-entry commands 包成新資料入口主線。
- Tool calls 仍走同一個 automation -> `ApplicationService.execute()` path，沒有新增 MCP backend
  truth。
- Compatibility commands 仍可被呼叫，但 schema 明確指向 Data Interpretation scan / preview /
  validate / apply / recipe flow。

### Evidence 入口

- Source：`XBrainLab/backend/application/automation.py`
- Source：`tests/unit/backend/application/test_automation.py`
- MCP integration evidence：`tests/integration/mcp/`
- Detailed validation：`docs/records/worklog.md`

### 不能宣稱完成

- 這不是 HTTP MCP、long-running job model 或 full MCP client certification。
- UI post-load label compatibility 仍需 mature import wizard replacement，不是靠 metadata 完成。

### 下一手重點

後續 MCP work 應處理 HTTP / long-running command job boundary、progress/cancel/recovery，以及
UI language 是否仍引導使用者走 post-load compatibility label path。

## 2026-05-05 Training Start Long-Running Confirmation

### 狀態

Training sidebar 的 `Start Training` button 現在會尊重 backend `train` capability 的
long-running confirmation boundary。當 capability 要求 confirmation 時，UI 會先用使用者語言提示
training 可能耗時並使用 CPU/GPU；使用者拒絕時不執行 command，service 成功時不 fallback 到
controller。

### 已可宣稱

- UI button path 和 ChatPanel agent path 都會對 `train` long-running action 做 human confirmation。
- Real `Study` path 仍透過 `TrainCommand` / `ApplicationService.execute()`，mock compatibility
  fallback 只保留給 unit-test / legacy adapter 情境。
- 已留下 automated Qt replay screenshot / visible text / button state artifact。

### Evidence 入口

- Source：`XBrainLab/ui/panels/training/sidebar.py`
- Tests：`tests/unit/ui/test_sidebars_and_components.py`
- Artifact：`artifacts/ui/training-start-confirmation/`
- Detailed validation：`docs/records/worklog.md`

### 不能宣稱完成

- 這不是真人 Windows desktop training acceptance，也不是完整 training / evaluation / saliency UI
  長鏈驗收。
- 這不處理 MCP long-running job model；MCP training progress/cancel/recovery 仍是後續工作。

### 下一手重點

後續應把 button-driven train -> evaluate -> visualization / saliency flow 納入 UI-observable
walkthrough，並繼續補 Windows desktop human acceptance。

## 2026-05-05 Backend Command Gate Confirmation Boundary

### 狀態

Long-running / destructive confirmation 不再只靠 UI 或 agent 外層自律。`ApplicationService`
現在委派 `command_gate.py` 做 capability 和 confirmation gate；`TrainCommand` 新增
`confirmed` 欄位，backend-ready 但未 confirmed 的 training request 會被 command layer 擋下。

### 已可宣稱

- Backend-unready `train` 仍回 precondition reason，不會錯誤要求 confirmation。
- Backend-ready `TrainCommand(confirmed=False)` 回 `confirmation_required`，且不呼叫 training
  controller。
- UI / agent / application tool surface 在使用者確認後才傳 `confirmed=True`。

### Evidence 入口

- Source：`XBrainLab/backend/application/command_gate.py`
- Source：`XBrainLab/backend/application/commands.py`
- Source：`XBrainLab/llm/tools/application_surface.py`
- Tests：`tests/unit/backend/application/test_application_service.py`
- Tests：`tests/unit/llm/tools/test_application_surface.py`
- Tests：`tests/unit/llm/agent/test_controller.py`
- Tests：`tests/unit/ui/test_sidebars_and_components.py`

### 不能宣稱完成

- 這不是 MCP long-running job / progress / cancel model。
- 這不是完整 training completion / evaluation / saliency desktop acceptance。

### 下一手重點

繼續把 remaining destructive / long-running automation entry 檢查成同一種 pattern，尤其 MCP
job boundary、training cancel / recovery、以及 UI-observable full training path。

## 2026-05-05 Backend Command Boundary Cleanup

### 狀態

Backend command spine 持續從 `ApplicationService` god object 收斂成 focused command services。
Data Interpretation、analysis / visualization、training config / train-stop lifecycle、dataset
generation / split audit、reset lifecycle、legacy data / label compatibility 現在都有各自 service
boundary；metadata update / smart parse / remove file 也已移到 focused data-table boundary；
preprocessing operations 和 `create_epoch` 也已移到 focused preprocess boundary；state snapshot
assembly 和 `query_state` diagnostics 也已移到 focused state/query boundary。
`ApplicationService` 回到 dispatch、capability / confirmation gate 和 state/result envelope。
同一輪 UI runtime bypass audit 已修 Dataset direct file import 與 Preprocess reset 的
service-success controller fallback，讓 successful `CommandResult` 不會再被 UI 以 controller
mutation 重做一次。
後續 Training sidebar cleanup 也把重新 split 前的 dataset cleanup 和 Clear History 收回 typed
command path；Clear History 現在有使用者確認，successful service result 不再落回 controller
mutation。
Data Interpretation format capability taxonomy 也已抽成 focused module，讓 lifecycle module 不再
同時承接 scanner / candidate / format matrix 細節。
Metadata resolution / BIDS summary / recipe metadata rehydration 也已抽成 focused module，讓
Data Interpretation lifecycle module 的下一步拆分邊界更清楚。
Recipe serialization / JSON load-write / applied-interpretation-to-recipe builder 也已抽成
focused module，Data Interpretation lifecycle module 只保留 compatibility re-export。
Label carrier planner 也已抽成 focused module，Data Interpretation lifecycle module 不再直接承接
CSV / MAT parser helpers 或 label-anchor default selection。
Preview payload builder 和 safe / needs-confirmation / blocked validator 也已抽成 focused
review module，Data Interpretation lifecycle module 不再直接承接 review payload construction。
Source scanner / source classification 也已抽成 focused scan module，Data Interpretation
lifecycle module 不再直接承接 scan IO / source discovery。
Candidate builder / metadata override / event-class choice mapping 也已抽成 focused candidate
module，原大型 lifecycle module 現在主要保留 shared decision enum、applied lifecycle dataclass
和 compatibility re-exports。
Data Interpretation lifecycle object stores、latest-id resolver、snapshot assembly、clear 和
post-load label-import recipe recording 也已抽成 `DataInterpretationSessionState`；command
service 主要回到 scan / preview / validate / apply / recipe command orchestration。

### 已可宣稱

- Data Interpretation command lifecycle 由 `DataInterpretationCommandService` /
  `DataInterpretationApplyService` / `DataInterpretationSessionState` 承接。
- Evaluation / visualization / saliency / montage apply 由 `AnalysisCommandService` 承接。
- Model configuration、training option、train / stop、history cleanup 和 reset-time training config
  clear 由 `TrainingCommandService` 承接。
- Dataset generation、split config、split audit、rollback、split summary 和 dataset cleanup 由
  `DatasetGenerationCommandService` 承接。
- Reset preprocess、reset session、new session、downstream rollback 和 reset-time
  dependent-state clear 由 `LifecycleCommandService` 承接。
- 舊 `load_data`、`attach_labels`、`import_labels` 和 label helper 由
  `DataCompatibilityCommandService` 承接，並明確定位為 compatibility boundary。
- Metadata update、smart parse 和 remove files 由 `DataTableCommandService` 承接。
- Preprocessing operations 和 create epoch 由 `PreprocessCommandService` 承接。
- State snapshot assembly 和 query state diagnostics 由 `StateSnapshotService` /
  `QueryStateCommandService` 承接。
- Dataset direct file import 和 Preprocess reset 的 successful service path 不再 fallback 到
  controller mutation；controller fallback 僅保留給 mock / legacy `None` adapter 情境。
- Training sidebar 的 re-split dataset cleanup 和 Clear History destructive action 走
  `ClearDatasetsCommand` / `ClearTrainingHistoryCommand`，且 Clear History 有 confirmation。
- GDF / EDF-BDF / EEGLAB / BrainVision / FIF / MAT / CSV-TSV / TXT / BIDS events /
  XDF-LSL format capability boundary 由 `data_interpretation_formats.py` 承接。
- Subject / session / task / run metadata resolution、BIDS entity summary 和 recipe metadata
  rehydration 由 `data_interpretation_metadata.py` 承接。
- `ImportRecipe` serialization、recipe JSON load / write 和 applied interpretation recipe builder
  由 `data_interpretation_recipe.py` 承接。
- MAT / CSV / TSV / BIDS events / TXT label carrier planning、choice normalization、anchor /
  time model / granularity defaults 由 `data_interpretation_label_carriers.py` 承接。
- `InterpretationPreview` / `ValidationDecision`、candidate preview serialization 和 safe /
  needs-confirmation / blocked decision boundary 由 `data_interpretation_review.py` 承接。
- `ScanResult`、source scanning、source kind classification、BIDS root detection、label carrier
  discovery 和 scan warning / blocked reason assembly 由 `data_interpretation_scan.py` 承接。
- `InterpretationCandidate`、scan + user choices to candidate conversion、metadata override、
  event/class mapping 和 candidate recipe trace 由 `data_interpretation_candidate.py` 承接。
- Data Interpretation lifecycle stores、resolver、snapshot、clear 和 post-load label-import recipe
  recording 由 `data_interpretation_state.py` 承接。
- UI / agent / headless / MCP 的 command name、capability policy 和 `CommandResult` contract
  沒有因拆分改變。

### Evidence 入口

- Detailed slice validation：`docs/records/worklog.md`
- Backend boundary description：`docs/architecture/backend.md`
- Current blockers：`docs/current.md`、`docs/planning/now.md`

### 不能宣稱完成

- `ApplicationService` 還保留 public compatibility wrapper methods；需要繼續確認 UI / agent / MCP
  沒有把 wrapper compatibility 誤當新產品心智模型。
- Legacy `load_data / attach_labels / import_labels` 尚未完全退出產品心智模型。
- 這是 backend architecture cleanup，不是 UI / Windows / MCP / thesis final closure。

### 下一手重點

1. 檢查 UI / agent / MCP 是否仍有 controller-private fallback 或 legacy wrapper path 進入產品主路徑。
2. 確認 UI / agent / MCP 沒有重新引入 controller-private fallback 作為產品主路徑。
3. 維持每個 slice 有 focused tests、non-mocked workflow regression 和文件同步。

## 2026-05-04 Product Completion Status Snapshot

### 狀態

Goal 1 baseline 已不再只是 backend baseline：Backend Command Spine、Data Interpretation
第一版產品路徑、local assistant runtime、tool-call benchmark、stdio MCP server、Windows
launcher command path、ChatPanel walkthrough 和 VisualizationPanel render 都已有可重跑 evidence。

這些進展仍是 product-completion baseline，不是最終成品 closure。完成度判斷要以
`docs/current.md`、`docs/planning/roadmap.md` 和 `docs/validation/README.md` 的 claim boundary
為準。

### 已可宣稱

| Track | 高層狀態 |
| --- | --- |
| Backend Command Spine | `ApplicationService / Command API` 已成為 UI、agent、headless、MCP 的主要 command spine；多個 legacy path 已降為 compatibility。 |
| Data Interpretation | 已有 scan -> preview -> validate -> confirm/apply -> save recipe 的第一版 UI / backend 主線；metadata、class map、event role、label carrier plan 和 format boundaries 可預覽與保存，reviewed subject/session 也會同步到 loaded data / Dataset table。 |
| Label / Event Import | reviewed timestamp labels、MAT / TXT trial-order sequence labels、窄版 MAT sample-anchor labels 已接進 Data Interpretation apply path；ambiguous mapping 會 blocked / skipped，不自動亂猜。 |
| UI Product Experience | ChatPanel 已從 debug dock 改成產品面板；有 true local-model 回覆、tool command、多輪、Data Interpretation chain、pipeline chain、training boundary / completion walkthrough artifacts，以及 consolidated automated human-like UI walkthrough。Walkthrough artifact 現在保存 per-phase visible text、button state、workflow/backend snapshots 和 UI quality review。Walkthrough-driven polish 已修 Data Interpretation density、Training plot readability / history header、Evaluation compact controls 和 ChatPanel reset stale UI。 |
| Agent / Local LLM | local primary / fallback 非中國模型已跑同一 `118` thesis-candidate tool-call cases，各 `3` 次，artifact 顯示 `118 / 118`，dashboard 已列 model comparison、case family、metric 和 failure taxonomy；blocked substitute-tool scoring 已收緊。 |
| Automation / MCP | real stdio MCP server 已存在，tool schema 來自同一套 ApplicationService automation truth；stdlib-only client walkthrough、official Inspector CLI `tools/list` 和 automated Inspector GUI click-through baseline 已保存。 |
| Launcher / Visualization | Windows launcher command walkthrough、startup geometry diagnostics、MainWindow VisualizationPanel Matplotlib render evidence 已保存。 |
| Docs / Validation | thesis evidence 已校正為 tool-call accuracy；validation docs 已明確區分 engineering baseline、UI-observable evidence 和不能宣稱的 release/thesis closure。 |

### Evidence 入口

- Current truth：`docs/current.md`
- Roadmap track status：`docs/planning/roadmap.md`
- Short-term blockers：`docs/planning/now.md`
- Validation boundaries：`docs/validation/README.md`
- Detailed slice log：`docs/records/worklog.md`
- Goal continuation / handoff：`artifacts/goal/`
- UI artifacts：`artifacts/ui/`
- MCP artifacts：`artifacts/mcp/`
- Launcher artifacts：`artifacts/launcher/`
- Agent eval artifacts：`artifacts/agent_evals/`
- Data Interpretation artifacts：`artifacts/data_interpretation/`

### 不能宣稱完成

- Data Interpretation 仍不是完整 mature import wizard：post-load label editor、raw trigger
  selector、complex GDF / MAT anchor reconciliation、XDF / LSL stream parser、全格式 real-data
  manual certification 都未完成。
- `load_data / attach_labels` legacy compatibility 仍存在；新 UI / agent 的核心心智模型已往
  Data Interpretation 移動，但尚未能宣稱 legacy model 完全退出。
- MCP 已有 real stdio server、client config、CLI walkthrough 和 automated Inspector GUI
  click-through；仍不能宣稱 HTTP transport、long-running training through MCP 或 full MCP client
  certification。
- Windows launcher 已有 automated command walkthrough；真人 Desktop click-through、packaging
  release approval 和多螢幕實際操作仍未完成。
- ChatPanel 已有多個 true local-model walkthrough；仍不能宣稱長時間 autonomous workflow、
  完整 UI-routing render 或完整 release walkthrough。
- VisualizationPanel Matplotlib tabs 已有 screenshot evidence；interactive desktop 3D / PyVista
  render 尚未驗證，headless 只支撐 blocked UX。
- Tool-call benchmark 已達 thesis-candidate case 數與 primary / fallback x3 重跑；這支撐
  tool-call benchmark claim，不等於整個桌面產品、UI usability 或論文實驗最終 closure。
- 最新使用者要求的 UI-observable human-like walkthrough 已形成單一 artifact，且 artifact 直接
  保存 visible text / button state / workflow snapshot / UI quality review；它仍不能替代真人
  Windows / 雙螢幕 / DPI desktop acceptance。

### 下一手重點

1. 收斂 Data Interpretation label editor / raw event anchor / XDF-LSL boundary，避免 wizard
   與 post-load compatibility path 形成雙主線。
2. 繼續依 consolidated walkthrough screenshots 做 UI polish；Data Interpretation density、
   Training plot readability / history header、analysis compact controls 和 ChatPanel reset stale UI
   已做第一輪，下一步聚焦 mature import wizard editor、assistant narrow/main-window layout 和整體產品感。
3. 做 Windows Desktop 真人 click-through；雙螢幕、DPI、launcher 與真長時間 local model session
   仍需 human desktop acceptance。
4. 補 interactive desktop 3D / PyVista render 驗證，或把 release boundary 寫得更明確。
5. 硬化 MCP HTTP / long-running tool-call boundary，不把 Inspector GUI baseline 擴張成 full
   MCP client certification。
6. 將 roadmap、current、validation 和 records 保持同步，但避免把 worklog 細節複製進
   implementation log。

## 2026-05-04 Backend Application Boundary Cleanup

### 狀態

`ApplicationService` 已完成第一個 god-object cleanup slice：Data Interpretation scan / preview /
validate / apply / recipe lifecycle state 和 handler logic 已移到
`DataInterpretationCommandService`，reviewed metadata / label carrier side effects 已移到
`DataInterpretationApplyService`。`ApplicationService` 仍是 UI、agent、headless、MCP 共用的
command dispatch、capability / confirmation gate 和 `CommandResult` envelope。

### 已可宣稱

- Data Interpretation lifecycle 和 reviewed apply side effects 不再由 `ApplicationService`
  直接管理。
- UI / agent / automation / MCP 仍透過同一個 `ApplicationService.execute()` command spine 進入，
  沒有新增 controller mutation fallback。
- 新 service 有 focused unit tests，既有 backend application / agent tool contract tests 仍通過。

### Evidence 入口

- Source：`XBrainLab/backend/application/data_interpretation_service.py`
- Source：`XBrainLab/backend/application/data_interpretation_apply.py`
- Boundary docs：`docs/architecture/backend.md`
- Detailed validation：`docs/records/worklog.md`

### 不能宣稱完成

- 這不是整個 backend architecture closure。Training、visualization、analysis、legacy
  `load_data / attach_labels / import_labels` compatibility handlers 仍需後續拆分與降權。
- Data Interpretation wizard 仍不是 mature embedded label editor；legacy post-load label import
  仍不能被包裝成新資料入口主線。

### 下一手重點

下一輪 backend work 應繼續把 `ApplicationService` 中剩餘大塊 workflow handlers 拆成 focused
services / handlers，同時保持 UI、agent、headless、MCP 只走同一套 command truth。

## 2026-05-05 Analysis Command Boundary Cleanup

### 狀態

`ApplicationService` 已完成第二個 backend boundary cleanup slice：`evaluate`、`visualize`、
`saliency` 和 confirmed `apply_montage` handler logic 已移到 `AnalysisCommandService`。
`ApplicationService` 仍是 command dispatch、capability / confirmation gate 和 result envelope。

### 已可宣稱

- Analysis / visualization readiness commands 不再由 `ApplicationService` 直接管理。
- Agent / UI / headless / MCP-facing command names 和 `CommandResult` contract 保持不變。
- 新 service 有 focused unit tests，既有 backend application / agent tool contract tests 仍通過。

### Evidence 入口

- Source：`XBrainLab/backend/application/analysis_service.py`
- Source：`tests/unit/backend/application/test_analysis_service.py`
- Detailed validation：`docs/records/worklog.md`

### 不能宣稱完成

- 這仍不是整個 backend architecture closure。後續 slices 已另外拆出 training、dataset
  generation、reset lifecycle、legacy compatibility、data-table、preprocess 和 state/query
  handlers；目前剩餘重點見本日最上方 backend command boundary cleanup snapshot。

### 下一手重點

下一輪 backend work 應確認新 UI / agent 心智模型不回到舊 `load_data / attach_labels`，並檢查
UI / agent / MCP 是否仍有產品主路徑旁路。

## 2026-05-05 Dataset Sidebar Capability Truth

### 狀態

Dataset sidebar 的 `Add Labels to Loaded Data` 和 `Channel Selection` visible state 現在會讀
ApplicationService capability policy。real `Study` path 不再只靠 controller-local `has_data` /
lock 判斷來啟用 label compatibility 或打開 channel selection dialog。

### 已可宣稱

- Empty real Study state 下，`Add Labels to Loaded Data` 會依 backend `import_labels`
  capability disabled，tooltip 顯示 shared blocked reason。
- Channel Selection click preflight 會先檢查 backend `preprocess` capability；沒有 raw data 時
  顯示 shared blocked reason，不開啟 selector dialog。
- mock / legacy `None` adapter tests 仍保留 controller fallback compatibility。

### Evidence 入口

- Source：`XBrainLab/ui/panels/dataset/sidebar.py`
- Tests：`tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar`
- Detailed validation：`docs/records/worklog.md`

### 不能宣稱完成

- 這不是完整 Data Interpretation wizard editor，也不是 Windows human desktop acceptance。
- 其他 panel 的 read-only controller refresh 和 mock fallback 仍需持續盤點。

## 2026-05-05 Dataset Smart Parse Capability Truth

### 狀態

`DatasetActionHandler.open_smart_parser()` 現在會先讀 backend `apply_smart_parse` capability。
real `Study` path 在沒有 raw data 時不會打開 Smart Parser dialog，而是顯示 shared backend
blocked reason。

### 已可宣稱

- Smart Parse metadata mutation 的 UI preflight 與 ApplicationService capability policy 對齊。
- mock / legacy non-Study path 仍保留 controller fallback 行為。

### Evidence 入口

- Source：`XBrainLab/ui/panels/dataset/actions.py`
- Tests：`tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler`
- Detailed validation：`docs/records/worklog.md`

### 不能宣稱完成

- 這不是完整 UI mutating-path audit closure；context menu metadata / remove-file、training /
  visualization remaining paths 仍需持續盤點。

## 2026-05-05 Dataset Remove Files Capability Truth

### 狀態

Dataset context-menu `Remove Files` 現在會先讀 backend `remove_files` capability。real `Study`
path 在沒有 raw data 或 raw-edit boundary blocked 時不會先要求確認，而是顯示 shared backend
blocked reason。

### 已可宣稱

- Remove Files UI preflight 與 ApplicationService capability policy 對齊。
- mock / legacy non-Study path 仍保留 controller fallback 行為。

### Evidence 入口

- Source：`XBrainLab/ui/panels/dataset/actions.py`
- Tests：`tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler`
- Detailed validation：`docs/records/worklog.md`

### 不能宣稱完成

- 這不是完整 Dataset context-menu audit closure；batch metadata preflight 和其他 remaining
  UI mutating paths 仍需盤點。

## 2026-05-05 Dataset Batch Metadata Capability Truth

### 狀態

Dataset context-menu `Set Subject` / `Set Session` batch metadata flow 現在會先讀 backend
`update_metadata` capability。real `Study` path 在沒有 raw data 或 raw-edit boundary blocked 時
不會先打開輸入框，而是顯示 shared backend blocked reason。

### 已可宣稱

- Batch metadata UI preflight 與 ApplicationService capability policy 對齊。
- mock / legacy non-Study path 仍保留 controller fallback 行為。

### Evidence 入口

- Source：`XBrainLab/ui/panels/dataset/actions.py`
- Tests：`tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler`
- Detailed validation：`docs/records/worklog.md`

### 不能宣稱完成

- 這不是完整 UI mutating-path audit closure；training / visualization remaining paths 仍需盤點。

## 2026-05-05 Montage Dialog Capability Truth

### 狀態

AgentManager montage picker 現在會先讀 backend `apply_montage` capability。real `Study` path
在缺 epochs 時顯示 shared blocked reason，不打開 montage dialog；使用者接受 montage 後經由
`ApplyMontageCommand` / `AnalysisCommandService` 套用。

### 已可宣稱

- Montage blocked / success path 與 ApplicationService capability policy 對齊。
- UI-side preprocess controller fallback 被限制在 mock / legacy non-Study compatibility。

### Evidence 入口

- Source：`XBrainLab/ui/components/agent_manager.py`
- Tests：`tests/unit/ui/test_agent_manager_coverage.py::TestMontagePicker`
- Detailed validation：`docs/records/worklog.md`

### 不能宣稱完成

- 這不是完整 visualization UI product acceptance，也不是 Windows human desktop click-through。
- 仍需持續盤點其他 panel / dialog 的 real runtime controller mutation bypass。

## 2026-05-05 Visualization Sidebar Montage Capability Truth

### 狀態

Visualization sidebar `Set Montage` 現在也會先讀 backend `apply_montage` capability。real
`Study` path 在缺 epochs 時不開 dialog，成功時透過 `ApplyMontageCommand` 套用；stale
controller-local epoch 判斷不再覆蓋 backend command truth。

### 已可宣稱

- Visualization sidebar montage blocked / success path 與 ApplicationService capability policy
  對齊。
- mock / legacy non-Study path 保留既有 controller-local compatibility。

### Evidence 入口

- Source：`XBrainLab/ui/panels/visualization/control_sidebar.py`
- Tests：`tests/unit/ui/visualization/test_control_sidebar.py`
- Detailed validation：`docs/records/worklog.md`

### 不能宣稱完成

- 這不是完整 visualization UI product acceptance，也不是 desktop render / Windows click-through
  驗收。

## 2026-05-05 Training Clear-History Capability Truth

### 狀態

Training sidebar `Clear History` 現在會先讀 backend `clear_training_history` capability。real
`Study` path 在沒有 training history 時不再先跳 destructive confirmation，而是顯示 shared
blocked reason。

### 已可宣稱

- Training clear-history confirmation boundary 與 ApplicationService capability policy 對齊。
- mock / legacy non-Study path 保留既有 controller-local compatibility。

### Evidence 入口

- Source：`XBrainLab/ui/panels/training/sidebar.py`
- Tests：`tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar`
- Detailed validation：`docs/records/worklog.md`

### 不能宣稱完成

- 這不是完整 training UI / long-running training human acceptance。

## 2026-05-05 Reset Preprocess Capability Truth

### 狀態

Preprocess sidebar `Reset Preprocessing` 現在會讀 backend `reset_preprocess` capability，而不是
把 reset lifecycle action 綁到 `preprocess` edit capability。real `Study` path 在 epoched /
locked 狀態仍可執行 reset command，empty state 則顯示 shared blocked reason。

### 已可宣稱

- Reset-preprocess confirmation / blocked boundary 與 ApplicationService capability policy 對齊。
- lifecycle reset 不再被 preprocess-edit policy 誤擋。

### Evidence 入口

- Source：`XBrainLab/ui/panels/preprocess/sidebar.py`
- Tests：`tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar`
- Detailed validation：`docs/records/worklog.md`

### 不能宣稱完成

- 這不是完整 reset / new-session human desktop acceptance。

## 2026-05-05 Training Configuration Dialog Capability Truth

### 狀態

Training sidebar model selection / training settings dialogs 現在會先讀 backend
`configure_training` capability。real `Study` path 在 training running 時不開設定 dialog，而是
顯示 shared blocked reason。

### 已可宣稱

- Training configuration dialogs 與 ApplicationService capability policy 對齊。
- mock / legacy non-Study path 保留既有 controller-local compatibility。

### Evidence 入口

- Source：`XBrainLab/ui/panels/training/sidebar.py`
- Tests：`tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar`
- Detailed validation：`docs/records/worklog.md`

### 不能宣稱完成

- 這不是完整 training setup UX 或 long-running training acceptance。

## 2026-05-05 Stop Training Capability Truth

### 狀態

Training sidebar `Stop Training` 現在會先讀 backend `stop_training` capability。real backend 正在
training 時，即使 controller-local state stale false，也會執行 `StopTrainingCommand`；未在
training 時則顯示 shared blocked reason。

### 已可宣稱

- Stop Training UI action 與 ApplicationService capability policy 對齊。
- mock / legacy non-Study path 保留既有 controller-local compatibility。

### Evidence 入口

- Source：`XBrainLab/ui/panels/training/sidebar.py`
- Tests：`tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar`
- Detailed validation：`docs/records/worklog.md`

### 不能宣稱完成

- 這不是完整 long-running training human acceptance。

## 2026-05-05 Dataset Inline Metadata Capability Truth

### 狀態

Dataset table 的 Subject / Session inline cells 現在會依 backend `update_metadata` capability
決定是否可編輯。real `Study` path 在 downstream locked state 會顯示 read-only cell 和 shared
blocked reason，programmatic `itemChanged` path 也會先做 capability preflight。

### 已可宣稱

- Dataset inline metadata editability 與 ApplicationService capability policy 對齊。
- mock / legacy non-Study path 保留既有 editable table / controller fallback compatibility。

### Evidence 入口

- Source：`XBrainLab/ui/panels/dataset/panel.py`
- Tests：`tests/unit/ui/dataset/test_panel.py`
- Detailed validation：`docs/records/worklog.md`

### 不能宣稱完成

- 這不是完整 Data Interpretation wizard editor 或 dataset table UX acceptance。

## 2026-05-05 Visualization Saliency Settings Capability Truth

### 狀態

Visualization sidebar `Saliency Settings` 現在會先讀 backend `saliency` capability。empty real
`Study` path 不再開不能套用的 saliency settings dialog，而是顯示 shared readiness reason。

### 已可宣稱

- Saliency settings dialog gate 與 ApplicationService capability policy 對齊。
- mock / legacy non-Study path 保留既有 dialog / controller fallback compatibility。

### Evidence 入口

- Source：`XBrainLab/ui/panels/visualization/control_sidebar.py`
- Tests：`tests/unit/ui/visualization/test_control_sidebar.py`
- Detailed validation：`docs/records/worklog.md`

### 不能宣稱完成

- 這不是完整 saliency workflow UX 或 visualization desktop render acceptance。

## 2026-05-05 Dataset Clear-Session Capability Truth

### 狀態

Dataset sidebar `Clear Dataset` 現在會讀 backend `reset_session` capability confirmation policy。
empty real `Study` path 不再先要求 destructive confirmation；mock / legacy path 保留既有確認。

### 已可宣稱

- Dataset clear action 與 ApplicationService reset-session confirmation policy 對齊。
- mock / legacy non-Study path 保留既有 controller fallback compatibility。

### Evidence 入口

- Source：`XBrainLab/ui/panels/dataset/sidebar.py`
- Tests：`tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar`
- Detailed validation：`docs/records/worklog.md`

### 不能宣稱完成

- 這不是完整 reset / new-session human desktop acceptance。

## 2026-05-05 Data Interpretation Recipe-Save Capability Truth

### 狀態

Data Interpretation recipe save UI 現在會先讀 backend `save_interpretation_recipe` capability。
blocked real `Study` path 不再先開 file-save dialog；label import recipe trace update 也不會在
save capability blocked 時提出「Save Updated Recipe」確認。

### 已可宣稱

- Recipe save prompt 與 ApplicationService capability policy 對齊。
- mock / legacy non-Study path 保留既有 file dialog / command fallback compatibility。

### Evidence 入口

- Source：`XBrainLab/ui/panels/dataset/actions.py`
- Tests：`tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler`
- Detailed validation：`docs/records/worklog.md`

### 不能宣稱完成

- 這不是完整 import wizard recipe UX acceptance。

## 2026-05-05 Training Data-Splitting Capability Truth

### 狀態

Training sidebar 的 `Data Splitting` 現在會先讀 backend `generate_dataset` capability。real
`Study` path 在未建立 epochs 時不再依賴 stale controller state 打開 splitting dialog；backend
capability 也補上 training running 時不可 generate / clear datasets 的 boundary。

### 已可宣稱

- Data-splitting dialog gate 與 ApplicationService dataset-generation capability policy 對齊。
- Existing datasets replacement boundary 仍保留：只有 backend 允許 `clear_datasets` 時才可進入
  clear-then-generate path。
- mock / legacy non-Study path 保留既有 controller-local compatibility。

### Evidence 入口

- Source：`XBrainLab/backend/application/capabilities.py`,
  `XBrainLab/ui/panels/training/sidebar.py`
- Tests：`tests/unit/backend/application/test_application_service.py`,
  `tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar`
- Detailed validation：`docs/records/worklog.md`

### 不能宣稱完成

- 這不是完整 training workflow human acceptance 或 long-running training resource validation。

## 2026-05-05 Dataset Smart Parse Source-Of-Truth Cleanup

### 狀態

Dataset Smart Parse 現在在 real `Study` path 以 backend `apply_smart_parse` capability 作為
開 dialog 的 source of truth。controller-local `is_locked()` / `has_data()` checks 僅保留給
mock / legacy non-Study compatibility。

### 已可宣稱

- Smart Parse dialog gate 不再被 stale controller state 蓋過 backend capability truth。
- blocked real `Study` path 仍顯示 shared backend blocked reason。

### Evidence 入口

- Source：`XBrainLab/ui/panels/dataset/actions.py`
- Tests：`tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler`
- Detailed validation：`docs/records/worklog.md`

### 不能宣稱完成

- 這不是完整 metadata editor / Data Interpretation wizard UX acceptance。

## 2026-05-05 Dataset Channel Selection Source-Of-Truth Cleanup

### 狀態

Dataset sidebar `Channel Selection` 現在在 real `Study` path 以 backend `preprocess` capability
作為開 dialog 的 source of truth。controller-local `has_data()` / `is_locked()` checks 僅保留給
mock / legacy non-Study compatibility。

### 已可宣稱

- Channel Selection dialog gate 不再被 stale controller state 蓋過 backend capability truth。
- blocked real `Study` path 仍顯示 shared backend blocked reason。

### Evidence 入口

- Source：`XBrainLab/ui/panels/dataset/sidebar.py`
- Tests：`tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar`
- Detailed validation：`docs/records/worklog.md`

### 不能宣稱完成

- 這不是完整 preprocessing UX 或 Data Interpretation wizard acceptance。

## 2026-05-05 Data Interpretation Source Entry Source-Of-Truth Cleanup

### 狀態

Dataset main file import 和 folder/BIDS source import 現在在 real `Study` path 以 backend
`scan_source` capability 作為資料入口 source of truth。controller-local `is_locked()` check 僅
保留給 mock / legacy non-Study compatibility。

### 已可宣稱

- File / folder Data Interpretation entry 不再被 stale controller lock state 蓋過 backend
  capability truth。
- blocked real `Study` path 仍由 backend Data Interpretation capability / apply raw-edit policy
  控制，而不是 UI 自己判斷。

### Evidence 入口

- Source：`XBrainLab/ui/panels/dataset/actions.py`
- Tests：`tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler`
- Detailed validation：`docs/records/worklog.md`

### 不能宣稱完成

- 這不是完整 Data Interpretation wizard UX 或 human desktop import acceptance。

## 2026-05-05 Preprocess Helper Source-Of-Truth Cleanup

### 狀態

Preprocess sidebar 的 shared `check_lock()` / `check_data_loaded()` helpers 現在在 real `Study`
path 以 backend `preprocess` capability 作為 source of truth。controller-local `is_epoched()` /
`has_data()` checks 僅保留給 mock / legacy non-Study compatibility。

### 已可宣稱

- Preprocess action helpers 不再被 stale controller state 蓋過 backend capability truth。
- Legacy warning behavior 仍保留給 non-Study fallback。

### Evidence 入口

- Source：`XBrainLab/ui/panels/preprocess/sidebar.py`
- Tests：`tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar`
- Detailed validation：`docs/records/worklog.md`

### 不能宣稱完成

- 這不是完整 preprocessing workflow UI acceptance 或 signal/thread lifecycle validation。

## 2026-05-05 Dataset Sidebar Visible Capability Truth

### 狀態

Dataset sidebar 的 main source import、folder/BIDS import、recipe reload 和 Smart Parse button
現在會用 backend capabilities 決定 enabled / tooltip。real `Study` path 不再因 stale controller
lock 顯示錯誤 tooltip，也不再讓 backend-blocked Smart Parse 看起來可點。Data Interpretation replay
artifact 也已刷新，會保存 empty / applied Dataset sidebar 全部 button state。

### 已可宣稱

- Dataset source-entry / Smart Parse visible state 與 ApplicationService capability policy 對齊。
- mock / legacy non-Study path 保留既有 controller-local compatibility。

### Evidence 入口

- Source：`XBrainLab/ui/panels/dataset/sidebar.py`
- Tests：`tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar`,
  `tests/unit/scripts/test_capture_data_interpretation_replay.py`
- Artifact：`artifacts/ui/data-interpretation-replay.json`
- Detailed validation：`docs/records/worklog.md`

### 不能宣稱完成

- 這不是完整 Dataset page visual design pass 或 UI-observable walkthrough acceptance。

## 2026-05-05 Agent / Headless Recipe Remap Schema Truth

### 狀態

Data Interpretation recipe reload remap choices are now part of the shared command schema, not
only a backend/UI private path. Agent `preview_interpretation`, headless automation specs, and MCP
tool specs expose the same `choices.eeg_file_remap` / `choices.label_carrier_remap` contract.

### 已可宣稱

- Recipe reload remap is represented in the unified command truth for UI, agent, headless, and MCP.
- Deterministic tool-call eval now covers explicit EEG-file remap, explicit label-carrier remap, and
  missing remap-target clarification.

### Evidence 入口

- Source：`XBrainLab/backend/application/data_interpretation_choice_schema.py`
- Tests：`tests/unit/llm/agent/test_tool_call_normalizer.py`,
  `tests/unit/backend/application/test_automation.py`,
  `tests/integration/agent/test_tool_call_eval.py`
- Artifact：`artifacts/agent_evals/latest.md`
- Detailed validation：`docs/records/worklog.md`

### 不能宣稱完成

- Primary / fallback local LLM x3 artifacts still need rerun on the new `121` case suite.
- This does not complete the full recipe conflict editor, anchor reconciliation, or human desktop
  acceptance.

## 2026-05-05 Dataset / Data Interpretation Table-Fit Polish

### 狀態

Dataset 主表與 Data Interpretation preview/remap wizard table 現在會以實際 viewport 重新分配欄寬。
欄位保持 interactive resize mode，但整體會填滿主 panel；文字溢出交給 elide，而不是讓 table
header 內縮或外溢。Review Summary 也改成低對比 dark-theme alternate rows。Events/Labels 顯示
維持語意區分，不用 success-green 表示 external labels。

### 已可宣稱

- Automated PyQt replay 下，Dataset table 載入資料後欄位合計會貼齊主 panel。
- Data Interpretation metadata、label/event、remap 和 Review Summary table 在截圖中不再水平外溢。

### Evidence 入口

- Source：`XBrainLab/ui/table_sizing.py`, `XBrainLab/ui/panels/dataset/panel.py`,
  `XBrainLab/ui/dialogs/dataset/data_interpretation_preview_dialog.py`
- Tests：`tests/unit/ui/test_table_sizing.py`, `tests/unit/ui/dataset/test_panel.py`,
  `tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py`
- Artifacts：`artifacts/ui/data-interpretation-preview.png`,
  `artifacts/ui/data-interpretation-remap.png`,
  `artifacts/ui/data-interpretation-applied.png`,
  `artifacts/ui/data-interpretation-replay.json`
- Detailed validation：`docs/records/worklog.md`

### 不能宣稱完成

- 這不是 Windows Desktop 真人 click-through、雙螢幕 / DPI acceptance，或完整 mature import
  wizard redesign。
