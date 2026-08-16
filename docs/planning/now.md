# XBrainLab Now

最後更新：`2026-08-16`

## 目前焦點

**在 PR #27／`assistant/runtime-measurement-v1` 完成第一輪 Assistant Settings 修復：下載要有可信進度且
不污染 terminal，local-only 啟用語意要清楚，Advanced 要收斂成輕量分組，並能在同一程序真正停用、
卸載及重新啟用 Assistant。**

UI visual-regression guard 已由 PR #24 合入 `main`。Quota-aware Codex dispatch 已收斂到
`.agents/README.md` 與 project `.codex/config.toml`：Terra 是 coordinator/default，Luna 只處理有
exact oracle 的 bounded worker，Sol 只處理客觀 high-risk decision；它不再是 product active work。

## 已完成的 CI change-scope repair

- PR #25 只有 agent-guidance、其 static audit 與 focused test，卻因 CI 將全部 `scripts/*`、`tests/*`
  視為 product path，而跑了 Linux shards、跨平台與 public multi-dataset gate。
- 修理範圍只新增窄的 `agent_guidance` scope：`AGENTS.md`、`.agents/**`、project `.codex/config.toml`、
  guidance audit 與它的兩個 exact tests 可走 focused audit/test/lint lane；一般 script、test、產品、依賴、
  workflow 或未知 path 均 fail closed 為完整 product CI。
- classifier 必須是可單元測試的純 helper；混合 scope、空 diff、首次 push 與未知 path 不可降級。
- 此為 CI/docs/test-only repair，已由 PR #26 合入 `main`；後續一般 script、test、產品、依賴、workflow
  或未知 path 仍 fail closed 為完整產品 CI。

## Assistant runtime recovery and measurement

- 使用者目前不能可靠使用 Assistant；已知 claim 不能由 mock tool-call eval 或舊 artifact 支撐。
- Assistant 必須和 UI 共用 `ApplicationService / Command API` 的 state、capability 與 error semantics，
  不能建立第二套 readiness truth。
- `assistant/runtime-measurement-v1` 的唯讀 host probe 已確認：protected `settings.json` 仍選擇已退役的
  `microsoft/Phi-4-mini-instruct`，local policy 在 model load 前正確阻擋它；不改設定地指定
  `ibm-granite/granite-3.3-2b-instruct` 時，runtime package 齊全但 local cache 缺失。這是目前
  Assistant 不可用的直接 blocker，尚未到可判定 chat lifecycle 或 tool dispatch 的階段。
- 使用者的正常 WSL Poetry terminal 已確認 `/dev/dxg`、RTX 5070 Ti 16 GB 與
  `torch.cuda.is_available()` 均可用；先前 Codex sandbox 的 CUDA 不可見不代表產品開發環境失敗。
- 使用者已明確授權透過產品 Settings 安裝 Granite。下載預估 5.08 GB、VRAM 約 6 GB，落在既定
  10 GB 單模型／20 GB cache boundary；設定只作本機變更，不 stage、commit 或直接覆寫。

### Observable outcome and repair boundary

- 成功：cache 完整、GPU-ready、簡短無工具回覆非空、嚴格 `query_state` envelope 有效，且真實
  ChatPanel 的狀態詢問恰執行一次成功的唯讀 `query_state`、後續一般問答不呼叫工具並回到 idle。
- 第一輪只用既有 runtime inspector 與 ChatPanel workflow walkthrough，記錄階段結果、總耗時、
  tool duration、UI idle 與 artifact；不另建全工具大腳本，也不跑會載入資料或訓練的 legacy verifier。
- 若任一步失敗，只修第一個 confirmed boundary：provision/model load、structured output、agent command
  admission，或 ChatPanel lifecycle。任何 source UI 修改仍先取得明確確認。

### Measured checkpoint (2026-08-16)

- Granite installation completed through the product lifecycle: the exact local cache is complete (about 5.07 GB) and
  the inspector classifies the normal WSL Poetry runtime as `gpu-ready`.
- Offline real-runtime smoke passed: one ordinary prompt returned non-empty text, and strict structured output returned
  exactly `{"tool_name":"query_state","parameters":{}}`.
- Two real ChatPanel walkthrough attempts reached the same functional point: the state request executed exactly one
  successful `query_state` (about 43–47 ms); the ordinary EEG explanation called no tool and completed in about
  1.9–2.0 s; ready and both turn screenshots were captured. RAG correctly reported its optional local embedding
  snapshot unavailable and stayed disabled.
- The walkthrough did not persist its terminal JSON/Markdown artifact after `window.close()`. This is a real evidence
  gap. The bounded close trace confirms the product root cause: `MainWindow.closeEvent()` waits for
  `_owned_ui_background_work_idle()` before it calls `_close_assistant_for_shutdown()`, while that idle snapshot counts
  the live Assistant `LocalRuntimeProcessOwner` as a remaining subprocess. The assistant can therefore never be asked
  to release the very process that makes the preceding gate false. Direct real assistant close completed after both
  model load and an ordinary generated answer in about 2 s, with no generation thread, worker or model remaining.

### Confirmed minimal repair (authorized 2026-08-16)

- Preserve the shutdown fence and training stop order. Before the global idle snapshot, drive the existing Assistant
  lifecycle close/retry; only after it reaches terminal ownership may the global snapshot require zero subprocesses.
  Apply the same ordering in normal and shutdown-only close paths. Do not weaken or exclude arbitrary background work
  from the snapshot.
- Add a focused close-order regression: an active Assistant-owned subprocess must cause the existing Assistant close
  action to run, then permit the normal global-idle gate once it reports terminal. Retain the existing tests that wait
  for genuinely unrelated UI/background work.
- Assistant Settings currently writes the downloader's full progress message into an unconstrained label in a
  horizontal action row, then sizes the dialog from the resulting content hint. It also renders a historical Assistant
  start failure that is not bound to the current model inspection or download attempt. The combination causes the
  reported width overflow and makes a new installation look failed even when no current download failure occurred.
- Keep one compact primary model state (`Checking`, `Not installed`, `Installing`, progress, `Ready`, or a current red
  failure). Raw progress detail must not control geometry. Move environment/cache detail under Advanced settings and
  remove the unbound historical failure from this dialog. Yellow is reserved for one current actionable warning, not
  normal missing/installing states.
- Dynamic content may fit height but must preserve the current dialog width within the screen boundary. A 520 px dialog
  must keep status, action, footer and horizontal-scroll state usable for not-installed, installing, failure and ready.
- The user explicitly approved both visible Settings changes and MainWindow close-order behavior in one Assistant PR.
  Do not modify downloader policy without a real `ModelDownloadOutcome` failure and safe diagnostic.

### Implementation checkpoint (2026-08-16)

- Settings now owns only compact current-state copy; raw downloader detail no longer controls geometry, runtime/cache
  detail lives under Advanced, and the unbound historical start-failure surface and its dead presentation path were
  deleted. Automated captures cover not-installed, installing, failed, ready and advanced at 520 px.
- Normal and forced MainWindow close paths now drive the existing Assistant teardown before the unchanged global-idle
  requirement. The real offline Granite two-turn walkthrough persisted its terminal artifact: one successful
  `query_state`, one zero-tool explanatory turn, closed runtime/dispatcher, released controller and zero generation
  threads.
- Focused tests, repo Ruff check/format, Basedpyright, MkDocs strict, the UI walkthrough and approved-reference baseline
  comparison pass locally. This is WSL evidence, not Windows manual acceptance. Existing required CI, including
  cross-platform/Windows jobs, remains mandatory and must not be skipped, weakened or made optional.

### Assistant Settings completion slice (authorized 2026-08-16)

#### Problem and evidence

- Hugging Face progress suppression is currently applied through an environment variable after the library has already
  been imported, so concurrent tqdm rows still flood and interleave in the terminal. The downloader also passes the
  deprecated `resume_download` argument even though current Hub downloads resume automatically.
- Production download progress only publishes 0 and validated 100. The parent already measures exact model-cache bytes
  every 0.5 seconds for resource limits, but discards that measurement; the existing UI test that injects 42% therefore
  proves only rendering, not the real producer path.
- The only product backend is local. `Use local assistant` is therefore a misleading legacy checkbox rather than a
  backend choice, and unchecking it does not itself prove that the loaded controller/model and CPU/GPU memory were
  released.
- The current bordered Advanced card visually competes with the two primary segmented controls and leaves runtime,
  cache and exact response values without clear grouping.
- Cache chronology is now calibrated: the Granite 5 GB weight blob completed at 13:24 local time and the offline
  walkthrough was recorded at 14:27. The walkthrough reused the already-complete cache in offline mode; it did not
  download or prove that it had created the cache.

#### Observable outcome

- The download child programmatically disables Hub progress rendering before `snapshot_download` and does not pass the
  deprecated resume argument. Application logs retain bounded lifecycle/error messages without concurrent transfer rows.
- The existing consumption poll emits monotonic integer progress from observed model bytes and the catalog estimate;
  it never exceeds 99 before exact snapshot validation, while only validated success emits 100. Resume starts from
  existing bytes; cancel, failure and timeout never claim completion.
- Remove the local-assistant checkbox. When persisted local Assistant is disabled, the footer primary action reads
  `Enable Assistant`; otherwise it reads `Save Changes`. Both require a ready selected runtime and neither introduces
  a dirty-state `Close` mode. The one-model dropdown remains unchanged.
- Advanced becomes a thin divider/chevron row labelled `Advanced`, with inline `Runtime`, `Exact response values`, and
  `Assistant` groups. `Disable Assistant…` lives only in the Assistant group and requires confirmation.
- Disable is rejected while a turn is active with an instruction to press Stop first. On success the existing runtime
  owner closes the dispatcher/controller, releases the model, clears controller and visible conversation context,
  persists `local.enabled=false`, retains model cache/response settings/EEG workflow state, and can create a fresh
  dispatcher/controller when re-enabled in the same process. Cleanup or persistence failure must not claim disabled;
  application shutdown during deactivation escalates to the existing terminal CLOSED path.

#### Scope, ownership, and non-goals

- Extend `AssistantRuntimeLifecycle`; do not add another owner, state machine, receipt, downloader, cache scanner or
  compatibility path. `AgentManager` remains the UI adapter and clears only Assistant conversation presentation after a
  successful lifecycle terminal. `ModelSettingsDialog` remains presentation/admission only.
- Reuse the existing consumption scan and local model estimate. Do not add network byte instrumentation, parallel
  downloads, alternate models/backends, cache deletion, first-run redesign, ChatPanel redesign, EEG changes or CI
  weakening. Root `settings.json` remains protected from Git and agent-authored runtime writes.
- Expected change is at most six production/support files and roughly +120–250 net production LOC. Stop for explicit
  complexity review before continuing if the bug fix exceeds +300 net production LOC, eight production files, or adds
  a production module/public class/authoritative owner.

#### Ordered repair and validation

1. Add red producer tests for Hub progress suppression/deprecated argv and observed-byte monotonic 0–99 progress; add
   red UI/lifecycle tests for removed checkbox, dynamic CTA, lightweight Advanced grouping, busy rejection, async
   deactivation, failure, shutdown race, conversation clear and same-process re-enable.
2. Implement downloader changes by reusing the consumption poll. Extend the existing lifecycle with a deactivation
   transition and terminal signal, then adapt `AgentManager` and the confirmed Settings layout without changing other UI.
3. Re-run identical focused tests plus directly adjacent downloader, lifecycle, manager and Settings suites; run Ruff,
   Basedpyright and strict MkDocs. Capture collapsed/expanded, disabled/enabled, installing/error/ready UI at 520 px and
   relevant DPI, checking no horizontal scroll, clipping or inaccessible focus.
4. With an isolated temporary config and the existing Granite cache, run an offline Disable → Enable → ordinary answer
   → strict `query_state` → close walkthrough. Do not mutate repo-root `settings.json`, redownload, or delete the cache.
5. Push the exact source to PR #27 and rerun every required existing CI check, including Windows/macOS/Linux/UI and
   multi-dataset lanes. Source changes invalidate prior evidence. Handoff remains pending until the user manually tests
   that exact head and explicitly approves merge; then merge the PR and delete the short branch.

#### Stop conditions

- Stop as `checkpoint` if true unloading cannot be expressed by the existing lifecycle owner, if persisted-disable
  failure cannot be rolled back without a second state owner, if progress requires a second cache scan, or if the real
  offline walkthrough would require changing/deleting the user's cache or protected settings.
- This slice is `scope-complete` only when the observable UI/runtime behavior and focused validation pass. Automated
  WSL/offscreen evidence does not constitute Windows native or user manual acceptance.

#### Implementation checkpoint (2026-08-16)

- Downloader now calls the Hub progress-disable API before the pinned snapshot request, omits the deprecated resume
  argument, and publishes monotonic observed-cache progress capped at 99 until exact validation publishes 100.
- Settings now has no local-only enable checkbox. The footer exposes `Save Changes` or `Enable Assistant`; Advanced is
  a lightweight expandable row with Runtime, Exact response values, and Assistant groups plus confirmed
  `Disable Assistant…`.
- The existing runtime lifecycle owns deactivation, including active-turn rejection, async cleanup, persistence rollback,
  shutdown escalation and a fresh dispatcher for same-process re-enable. AgentManager clears only Assistant conversation
  presentation after the successful terminal; cache, response values and EEG workflow remain outside that mutation.
- Directly related downloader/dispatcher/lifecycle/threading/manager/Settings/capture tests pass (372 tests). The UI
  capture contract passes for not-installed, installing, failed, ready, advanced and disabled states at 520 px, including
  no horizontal scroll and restoring primary content after Advanced collapses. Actual production delta remains four
  production files and below the +300 net bug-fix review trigger; no module, public class or owner was added.
- Ruff check/format, Basedpyright and strict MkDocs pass. An isolated `/tmp` settings workflow with existing Granite cache
  and Hugging Face offline flags passed real unload → controller release/cache retention → same-process reload, then one
  successful `query_state`-only turn (about 40 ms), one zero-tool EEG explanation, and terminal application close with no
  controller/dispatcher/generation thread left. It did not download or alter repo-root/user production settings.
- Remaining before user handoff: exact-source push and every existing required PR check. Native/manual acceptance is still
  pending and prior PR #27 evidence is stale because source changed.
- Exact head `a0cc825e98c87de7810909b30f9e101e8a9ef5e3` passed every reported Windows, macOS,
  dataset, visual, lint, docs and non-UI Linux check, but `linux-integration-ui` failed. The same failure reproduces
  locally: the human-like walkthrough still dereferences the removed `local_enable_chk`; its Qt callback aborts before
  closing the modal dialog, so the outer process reports only a 180-second timeout. This is a stale directly-coupled
  capture call site, not evidence to relax the timeout or CI gate. Remove only that retired-widget mutation and rerun
  the exact integration test before creating a new source commit.
- The stale widget mutation is now removed without changing the timeout or gate. The identical red test changed from
  `1 failed in 188.65s` to `1 passed in 103.98s`; the complete capture subprocess itself finished in 96.90 seconds.
  The directly adjacent walkthrough sweep passed 239 tests; Ruff check/format, Basedpyright and MkDocs strict also pass.
  Remaining work is a new exact commit/push and a fully green rerun of all required CI.

## 下一步

1. 刪除 human-like walkthrough 對退役 `local_enable_chk` 的直接操作；不增加 timeout、不降低 gate。
2. 重跑同一 red integration test，確認完整 capture 正常退出且 artifact contract 維持通過。
3. 重跑直接相關 focused/static 檢查，建立並推送新的 exact source commit。
4. 等待 PR #27 全部既有 required CI，再交使用者手測；未取得 exact-source 手測通過與 merge 同意前
   不得合入 `main`。

## Non-goals

- 不把 tool-call eval、thesis evidence、MCP、packaging 或任意 dataset support 拉進第一個 Assistant slice。
- 不因 agent 不可用就替換 product model、加入 silent fallback、建立第二套 state owner 或重寫整個 panel。
- 不修改 `v0.6.0` tag/release、Settings 以外的可見 UI、EEG pipeline 或 training outputs；repo-root
  `settings.json` 只允許產品 Settings 在使用者授權下寫入，不由 Git 操作。
- 不以 deterministic mock、dashboard PASS 或 Linux offscreen 冒充 real Granite／Windows product evidence。

## Entry condition

- PR #26 已合入 `main`；Assistant branch 初始狀態只保留使用者的 `settings.json` dirty path。
- 使用者已確認正式 WSL Poetry runtime 的 CUDA 可用，並授權受控 Granite 安裝。
- 每個 native/Qt run 都有明確 timeout、資源上限與單一 PID/session ownership。

長期目標讀 [Roadmap](roadmap.md)，evidence contract 只讀 [Validation](../validation/README.md)。
