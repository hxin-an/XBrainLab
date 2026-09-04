# XBrainLab Now

最後更新：`2026-09-04`

## Current baseline

`2315c8ac08c1cc2683e6526eec9b368add809bff` 是目前 `main`／`origin/main` 的產品基線，已合併 PR #110：
SSVEP import review routing、lazy Dataset startup repair，以及 EEGLAB embedded `.set` sampling-rate preflight。
使用者已在該 exact source 的 Windows 手測 MAMEM1 `sub-1` 三個 run，以 `trial_type` 的五個頻率 class
完成 supervised training，接受目前 CV split class coverage 的已知限制並同意 merge。歷史、CI 與完整
manual acceptance 由 Git 與 PR 記錄保存，不再作為 active plan。Repo-root `settings.json` 的本機修改由使用者
擁有，絕不可 stage、commit、revert、覆寫或隱藏。

## Active slice — Evaluation retryable stale worker reporting

### Problem and evidence

- Windows 2026-09-04 13:03 在 Evaluation detached render 中記錄
  `XBrainLab.ui.core.worker - ERROR - Worker task failed`；根因是
  `Evaluation results changed while render data was being read. Refresh Evaluation and try again.`。使用者確認
  畫面最後正常，故此問題是可恢復狀態被記成 ERROR，不是 training 或 evaluation 結果遺失。
- `EvaluationRenderPublisher` 在 materialize 前後比對 application publication 與 training read boundary，資料
  變動時 fail closed 並以 `evaluation_render_stale=True`、`retryable=True` 拒絕 publication；這個 backend guard
  正確，不能移除或放寬。
- `EvaluationPanel._on_evaluation_render_error()` 已辨識上述 diagnostics，清除舊 render 並經既有 75 ms、最多
  8 次 retry lifecycle 重試。但 `ui.core.worker._run_worker_task()` 在 queued UI callback 取得 exception 前無條件
  `logger.error("Worker task failed", exc_info=True)`，所以每個預期 stale retry 先留下 misleading ERROR。
- 既有 backend `test_training_boundary_change_discards_copied_render_data` 強力保護 fail-closed guard；既有
  `test_evaluation_stale_render_retries_without_error_log` 使用 real Evaluation work lifecycle 證明 retry，但只排除
  panel-specific log，沒有 assert generic worker ERROR，因而漏掉本次 defect。

### Outcome and contract

- 相同 Evaluation target 的 retryable stale result 必須自動沿用既有 retry lifecycle，最終成功時不產生
  `Worker task failed` ERROR，也不顯示 unavailable product error。
- 非 retryable exception 仍必須經既有 worker error signal、ERROR log 與 Evaluation unavailable handling；不把
  真正失敗靜默化。
- stale guard、75 ms×8 retry budget、selection/generation identity、loading/cancel/cleanup lifecycle 都維持既有
  contract。使用者已授權這個 narrow UI code fix；不進行 copy、layout 或 interaction redesign，但 exact-head
  Windows manual acceptance 仍必要。

### Scope, ownership, and non-goals

- 只修改 `EvaluationPanel` 的 private async result handling 與 focused UI tests；預計一個既有 production owner、
  production net `+20–45 LOC`、不新增 owner/module/public API/state machine/compatibility path。
- 採 deletion/reuse first：重用既有 `ApplicationError` diagnostics、`_on_evaluation_render_ready()` 與 retry scheduler。
  `_load_evaluation_render()` 只捕捉同時具有 stale 和 retryable diagnostics 的 `ApplicationError`，回傳 panel-private
  expected-result payload；ready callback 以同一 scheduler 排程 retry。其他 exception 照原本越過 worker boundary。
- 不改 global `Worker`／`PythonThreadWorker` API 或其通用 logging policy，不改 backend guard、ApplicationService、
  ownership registry、retry budget、UI copy/layout、saliency、data split 或 CV coverage。
- retry exhaustion、MAMEM1 CV class coverage、以及 duplicate saliency generation 都是 deferred candidates；本 slice
  不把它們包進來。三格式 capability gate（EEGLAB／EDF／BrainVision）必須在本 PR 合併後另開，不提前實作或宣稱。

### TDD repair and focused validation

1. 在 `tests/unit/ui/test_evaluation_publication_refresh.py` 先新增最小 red reproduction：以既有 port、
   `EvaluationWorkController` 和 `PythonThreadWorker` seam 讓第一次 render 拋出帶 stale+retryable diagnostics 的
   `ApplicationError`，第二次回傳有效 detached publication。assert 可觀察到 final detached publication、retry timer idle、沒有
   `XBrainLab.ui.core.worker` 的 `Worker task failed` ERROR。current source 必須只因通用 worker 的 eager ERROR 而紅。
2. 加相鄰 preservation case：non-retryable `RuntimeError` 仍產生 generic worker ERROR 並顯示既有 unavailable state；
   不以 broad log suppression 偽造 green。既有 cleanup retry cancellation 與 backend boundary-change guard 仍為直接
   adjacent protection。
3. 只在 panel private async bridge 實作 expected-result handling；assert stale retry 不把 exception cross generic worker
   boundary，success 仍必須完全驗證 request/operation identity。不要改 test-only port 或以 mock bypass worker。
4. 在 Windows locked Poetry environment，先跑 red selector，再跑同一 selector green：

   ```powershell
   $env:QT_QPA_PLATFORM='offscreen'; $env:MNE_DONTWRITE_HOME='true';
   poetry run pytest tests/unit/ui/test_evaluation_publication_refresh.py::test_evaluation_retryable_stale_render_does_not_log_worker_failure -q
   ```

   使用明確 timeout 與 `prlimit --core=0` 的等效 wrapper；完成後跑完整
   `tests/unit/ui/test_evaluation_publication_refresh.py`、直接 worker suite
   `tests/unit/ui/core/test_worker.py`、changed-file Ruff 與 `git diff --check`。不將 offscreen evidence 宣稱為
   Windows native acceptance。
5. Exact PR head 的 Windows manual check：完成一次 CPU training 後開啟／刷新 Evaluation，確認 transient stale
   retry 最終恢復 render 且 log 不再出現 `Worker task failed` for this expected condition；非 retryable diagnostic
   不做人工刻意觸發。PR CI 的所有 non-skipped checks 必須 completed/success，然後才請使用者在 exact head
   明確批准 merge。

### Implementation progress and focused evidence

- Exact red selector reproduced the defect with `1 failed in 3.37s`; its only failure was the generic
  `XBrainLab.ui.core.worker` `Worker task failed` ERROR for the retryable stale render.
- Minimal repair is confined to the existing panel private bridge in one production file: only an
  `ApplicationError` carrying exact `evaluation_render_stale=True` and `retryable=True` diagnostics returns the
  expected-result payload to the existing retry lifecycle. Production delta is `+33/-11 LOC` (net `+22`), owner
  delta `0`; no global worker policy, backend guard, retry budget, owner, or abstraction changed.
- Green exact stale selector passed `1 passed in 3.33s`; the unexpected-failure preservation selector passed
  `1 passed in 3.20s`. Independent review found `0` blockers.
- Windows locked-venv focused aggregate passed `83` tests with `0` failures and `2` existing deprecation warnings;
  changed-file Windows-venv Ruff and `git diff --check` passed.
- These are dirty-source focused evidence only, not an exact commit, CI, canonical data-gate, or native Windows manual
  acceptance. Next: commit/push/PR, run the exact-head canonical data gate and CI, then record Windows manual
  acceptance before merge.

### Stop condition

- 若 minimal red test 無法經真 Evaluation work/worker seam 重現、expected-result payload 需要改 global worker semantics、需改
  backend guard 或 retry budget、或觸及超過一個 production file，停止並重新討論。
- 若 retry failure 不是 stale+retryable diagnostics，保留 ERROR，不擴張成 arbitrary exception suppression。
- 完成條件是 expected stale no longer creates generic worker ERROR while it retries and succeeds, unexpected failure
  remains visible, focused tests/quality checks pass, and exact-head Windows acceptance plus merge approval are recorded.
