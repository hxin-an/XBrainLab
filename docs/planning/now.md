# XBrainLab Now

最後更新：`2026-09-12`

## Active

## Quality baseline closure — approved implementation

User approved one finite integration PR with small reversible commits and one final native Windows
GUI / English Assistant manual acceptance. Do not stop after a slice, compaction or pending CI.
This file is the sole active plan; update next action and blockers here, not in another worklog.

### Problems, outcomes and authorization

Independent review confirmed unsafe Poe clean deleting durable output/runs, destructive MOABB capture
--force, two stress scripts leaking native settings, malformed setup JSON shape crashes, navigation
metrics ending only on the next turn, and two bounded Assistant ambiguity failures. Reachability review
identified unused CLI automation, Dataset convenience routes, mock tool execution and stale tooling.
Measured architecture guards repeat expensive scans. Inventory/AST coverage is not deep-read coverage.

Physically remove approved unused capabilities and fix confirmed defects with behavioral evidence.
Preserve typed Command/query ownership and visible workflows; no zero-defect or Stable model claim.
Latest fetched main is the starting baseline. Original checkout edits, root settings.json, datasets,
shared environments/caches and retained handoff evidence are protected. No downloads, new environments,
WSL compaction, broad cleanup or termination of unrelated processes.

User explicitly approved JSON headless CLI and exclusive Python adapter/export retirement. No legacy
folder, shim, forwarding entrypoint, replacement control plane or additional authoritative owner.
UI permission covers invisible deletion of unreachable folder/BIDS routes and tests/guards only;
keep actual Import Data file/folder/BIDS/recipe behavior, layout and copy.
Minimal prompt correction is allowed for ambiguous_en and generic_filter_selection: fixed model and
revision, tool contracts, RAG, frozen 81 cases and scorer; no Host semantic rescue. At most two candidate
prompt revisions. Unresolved required cases are a decision blocker, not completion.
User approved this one-stage PR cumulatively exceeding 1,500 production LOC if necessary. Each slice
still receives complexity review: deletion candidates, owners before/after, +/-/net LOC and rollback.

### Authorized slices and focused acceptance

1. **CLI retirement [pending]**: delete headless JSON CLI, application automation adapter and six
   exports, plus exclusive tests. First establish passing characterization; migrate unique confirmation,
   interpretation and deferred split/training protection to typed Commands. Check dynamic registration,
   exports, scripts, docs and tests. Preserve admission/mutation/publication owners.
2. **Safety/setup/isolation [pending]**: remove unsafe Poe clean task; remove destructive MOABB --force,
   reject all existing capture output directories and require fresh runs. Reuse isolated capture config
   in both native stress scripts. Normalize malformed setup JSON shapes to existing default without
   rewriting settings or changing valid model selection. Red/green tests cover results preservation,
   rejected overwrites and configuration restoration on success/failure.
3. **Dataset unused routes [pending]**: characterize real Import Data paths, delete unused folder/BIDS
   delegates and exclusively reachable implementation/tests/required facade guards. Retain real BIDS
   subject selection. Run identical characterization and relevant architecture negative fixtures.
4. **Assistant registry/terminal/ambiguity [pending]**: evaluator uses real registry metadata with its
   existing execution-suppressed harness; prove schema/description/membership parity before removing mock
   execution capability and exclusive tests. Navigation metrics finish on matching terminal only;
   cover success/failure/stale/duplicate callbacks and real UI callback boundary. Correct two ambiguity
   cases within two prompt candidates; run full frozen evaluation without positive/provenance regression.
   Separate raw-model and product scores; model evaluation does not prove real command execution.
5. **Tooling/test quality/scan cost [pending]**: remove unused remote SDK dependency group and regenerate
   lock without unrelated upgrades; remove dead integration-branch CI triggers/exclusive tests and broken
   packaged test-* entries, retaining repo commands and necessary gates. Remove only mapped duplicate
   tests with replacement evidence. Optimize repeated guard reading/parsing with before/after measurements,
   unchanged scope and negative diagnostics; no general AST framework, weakened gate or unmeasured
   complexity. Revert optimization without reproducible benefit.
6. **Integration/review/handoff [pending]**: non-author review of physical deletion, safety/state and
   behavioral test quality, then reconcile checklist against actual diff and evidence. Update only changed
   canonical truth/decisions. Applicable exact-commit handoff registry: required CI, source-diverse data,
   platform/native UI and Assistant. Prior green evidence cannot substitute. Report production/scripts/tests
   +/-/net separately, actual deep-read coverage and limitations.

Commits are independent rollback units. Validate shared seams early with focused checks; do not repeat
equivalent full local regression already supplied by same-head CI. Native tests use timeouts, POSIX core
disabled, existing Windows environment and isolated settings. Unrelated review findings do not expand scope.

### Handoff and stop condition

After all work, required reviews and gates pass, launch native Windows app with one PowerShell log and
give restart command plus one checklist: import/preprocess, subject split/multiple plans, stop/rerun,
result reopening, Saliency/SmoothGrad and English Assistant clarification/execution. Confirm response,
then hand back without monitoring. No per-slice manual handoff. New authority or unavailable necessary
resources can block; compaction and pending CI are not completion. Merge only after explicit exact-source
manual acceptance and merge approval; afterward remove only owned disposable stage worktree/artifacts,
preserving data, shared environments and necessary evidence.

### Next action / checkpoint

Fresh worktree from fetched main created; shared Windows Python/pytest usable with execution escalation.
Original three dirty files unchanged. Next: establish CLI baseline and safety/setup red tests.
No slices completed; PR and final gates not started.

三核心責任重構已完成 Windows GUI／English Assistant 手測，並經使用者明確同意合併
[PR #138](https://github.com/hxin-an/XBrainLab/pull/138)。不再把該階段的施工切片或 pending gates
當作 active dispatch；實作、review、驗證與驗收紀錄由合併 PR、Git history 和 exact-source evidence 保存。

`main` 仍是唯一產品基線；當前 SHA、branch、dirty state 與 worktree inventory 從 Git 取得，
不從這份文件推定。原始 checkout 的使用者修改、本機設定、原始資料與共用環境不屬於本輪清理。

## 已合併基準的邊界

- 三核心保留正式 Command／publication、Qt runtime coordination 與 UI composition 責任，
  不以核心行數仍大判定必須繼續拆分；目前責任邊界見
  [Backend](../architecture/backend.md)、[Assistant](../architecture/agent.md) 與
  [UI](../architecture/ui.md)。
- Assistant 維持已接受的 bounded baseline，不宣稱 Stable promotion 或零缺陷；
  產品與證據限制見 [Current](../current.md) 和 [Validation](../validation/README.md)。
- Panel navigation 的既有 metrics 會延後到下一輪才 finalize；正式 correlated terminal 與
  UI completion 正常。此 observability 缺口是候選 follow-up，不是新的施工授權。

其他方向見 [Roadmap](roadmap.md)，不自動擴大以上已授權施工範圍。
