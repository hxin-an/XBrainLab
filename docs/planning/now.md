# XBrainLab Now

最後更新：`2026-08-16`

## 目前焦點

**修復真實 Assistant 使用流程中已確認的兩個 UI/lifecycle defect：Settings 安裝狀態不得被長訊息
撐出畫面或用舊失敗黃字誤導，MainWindow 關閉必須先釋放 Assistant-owned subprocess 再判定全域 idle。**

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

## 下一步

1. Red-first 固定長 progress message／舊黃字／520 px geometry，以及 Assistant subprocess 先於 global-idle
   gate 關閉的 observable contract。
2. 以 deletion/reuse-first 修改既有 Settings renderer 與 MainWindow close ordering；不新增 owner、state
   machine、receipt、downloader 或 compatibility path。
3. 重跑相同 focused tests、直接相鄰 lifecycle tests、Ruff 與 Assistant Settings automated UI artifact；主
   agent 檢查 loading/error/cancel/success/narrow states。
4. 用既有 Granite cache 重跑 offline two-turn ChatPanel walkthrough，要求 terminal artifact 可保存且視窗在
   bounded time 關閉；不刪除或重下載約 5 GB cache。
5. Push/PR/CI 後交使用者以目前實際使用的 WSL Poetry workflow 手測。產品 source 未取得手測通過與
   merge 同意前不得合入 `main`；本 slice 不宣稱 Windows UI acceptance。

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
