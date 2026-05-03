# XBrainLab Implementation Log

這份文件記錄接手後的重要實作與整理工作。

它不是 changelog，也不是每日流水帳。它的目的是讓之後的人知道：

- 當時解決了什麼問題
- 為什麼這樣改
- 改到哪些區域
- 有什麼驗證證據
- 還留下什麼風險

新 entry 插在本格式說明下方，最新在上。

## Entry 格式

```md
## YYYY-MM-DD 主題

### 背景

### 變更

### 影響範圍

### 驗證

### 剩餘風險
```

## 2026-05-03 Tool-call eval minimum gates

### 背景

使用者確認 tool-call thesis 主線後，進一步要求把 tool 重構、verification architecture 和足量
資料 / case 數寫成明確條件，而不是只寫方向。

### 變更

- 在 thesis protocol、agent target、backend goal runbook 和 `AGENTS.md` 補明確 gate。
- tool surface 需要重構為 service-backed command，mutating agent tools 不直接包 controller。
- Verification Layer contract 需要檢查 schema、required parameters、state precondition、
  resource existence、confirmation boundary、unsafe / destructive action、confidence threshold。
- tool-call eval cases 數量明確化：engineering baseline 至少 `50` cases，thesis candidate
  至少 `100` cases，negative / blocked / recovery cases 至少 `30%`，multi-turn 至少 `15` cases，
  local LLM primary / fallback runner 至少重跑 `3` 次。
- 資料級支撐需要 checked-in compact fixtures、event-rich public fixture slice；external EEG dataset
  只作 pipeline support。

### 影響範圍

- 文件與長任務 runner 驗收條件。
- 不改 source code、不改 tests。

### 驗證

- `git diff --check`
- `poetry run mkdocs build --strict`

### 剩餘風險

- 這次只把 gate 寫入文件；scorer、case schema、runner 和 fixture coverage 仍待實作。

## 2026-05-03 Thesis evidence positioning correction

### 背景

使用者指出論文要仔細驗證的是 agent tool-call 準確率，而不是 EEG 訓練準確率。既有文件雖然有
寫 agent tool-call eval 要獨立於 EEG classification metrics，但 `thesis_protocol` 和部分
validation wording 仍容易把 external dataset / training metrics 誤讀成 thesis 主線。

### 變更

- 將 `docs/validation/thesis_protocol.md` 改成 Thesis Tool-Call Evaluation Protocol。
- 明確寫下 thesis 主指標：intent、tool selection、parameter、state-transition、
  blocked-command handling、error recovery、invalid call rate、parser / verifier failure。
- 將 EEG split、training / evaluation metrics、external dataset runner 降格為 product
  pipeline support / domain task sanity。
- 更新 `docs/validation/README.md`、`docs/architecture/validation.md`、`docs/current.md`、
  `.agents/context/thesis.md` 和 backend goal runbook，避免後續 runner 被帶去優先做
  training accuracy thesis。

### 影響範圍

- 文件定位與 agent 發包指令。
- 不改 source code、不改測試、不改既有 split audit helper。

### 驗證

- `git diff --check`
- `poetry run mkdocs build --strict`

### 剩餘風險

- records 裡的歷史紀錄仍保留當時 wording；current truth 已改到 validation / architecture /
  thesis context。若後續要寫正式論文章節，還需要把 benchmark case schema 和 report format
  落成程式碼。

## 2026-05-03 Supervisor delivery gate, window fallback, backend rollback boundary

### 背景

人工退件指出先前把局部修復與 dashboard PASS 誤當成完成。使用者要求主 agent
扮演審查者 / 發包者，worker 完成回報不能直接轉交；仍有已知 blocker 時必須打回。
同時 Windows/WSLg offset dual-monitor layout 讓新增的置中 / recovery 邏輯把視窗開到
螢幕上方，backend 也仍需補強 service-first contract 的可靠邊界。

### 變更

- `AGENTS.md`、`.agents/README.md`、`.agents/runbooks/autopilot.md` 補上 supervisor
  model：主 agent 必須自己讀 diff、看 artifact、跑 tests、確認 docs/current truth。
- `MainWindow` 對 first launch、不健康 saved geometry、post-show recovery 改用
  maximized fallback；fullscreen geometry 視為不健康，不保存。
- Window placement tests 加入使用者回報的 offset monitor layout 與 virtual-gap cursor
  regression。
- `ApplicationService.generate_dataset` 把 split apply 與 audit 包進同一 rollback boundary；
  apply exception 或 audit blocking issue 都會還原 datasets / generator / trainer。
- `evaluate` / `clear_training_history` capability 改以 actual training plan history 為準。
- 修正 architecture/current/now 文件，不再把 synthetic UI walkthrough 或 deterministic eval
  說成完整產品交付證據。

### 影響範圍

- Agent 操作規則：`AGENTS.md`、`.agents/README.md`、`.agents/runbooks/autopilot.md`。
- UI shell：`XBrainLab/ui/main_window.py`、window geometry tests。
- Backend contract：`XBrainLab/backend/application/capabilities.py`、
  `XBrainLab/backend/application/service.py`、`XBrainLab/backend/facade.py`。
- Documentation：`docs/current.md`、`docs/planning/now.md`、architecture docs、records。

### 驗證

- `git diff --check`
- Python ruff gate on touched Python files：PASS
- Window geometry gate：`22 passed`
- Backend application / facade / agent surface gate：`80 passed`
- Assistant chat product slice：`48 passed`
- `poetry run basedpyright`：`0 errors, 0 warnings, 0 notes`
- `poetry run mkdocs build --strict`：PASS

### 剩餘風險

- 真 Windows/WSLg 雙螢幕 Desktop launcher click-through 尚未人工驗收。
- 現有 UI product walkthrough 仍使用 patched training / synthetic records，不是真 UI 點按到
  real training/evaluation/visualization completion。
- true local model 在 ChatPanel 中的長時間 UI walkthrough 尚未完成。

## 2026-05-02 Launcher visible startup logs and geometry diagnostics

### 背景

人工退件指出 Windows launcher 啟動後 terminal 一片黑，無法判斷目前跑到哪裡；同時主視窗仍可能
出現在正上方。需要先排除 Desktop launcher 是否指向舊 repo / stale generated app，再補可以
定位 WSLg / Windows 雙螢幕行為的啟動診斷。

### 變更

- 確認 `/mnt/c/Users/Administrator/Desktop/XBrainLab.cmd` 指向 active repo
  `/mnt/d/workspace_v2/projects/lab/XBrainLab`；Desktop 上沒有其他 XBrainLab app / shortcut。
- Desktop `.cmd` 和 repo `.cmd` 改成 bootstrap active repo 的 PowerShell launcher，啟動時直接顯示
  active repo、PowerShell launcher path 和啟動狀態。
- PowerShell launcher 會顯示 log path、開 log / tail log 指令，並用 live tee 把 WSL / Python
  stdout、stderr 同時寫入 terminal 和 `%LOCALAPPDATA%\XBrainLab\logs\launcher-*.log`。
- 新增 `XBRAINLAB_STARTUP_DIAGNOSTICS=1` gated startup geometry diagnostics；啟用時 log screens、
  cursor、splash geometry、MainWindow restore/default placement、show event 和 post-show geometry。
- MainWindow post-show recovery 從單次 `0ms` 改成 `0ms + 250ms`，避免 Windows / WSLg 在 show 後才
  finalize native frame 或移動 window 時漏掉 top-edge recovery。
- Launcher 增加 `XBRAINLAB_LAUNCHER_SMOKE=1` basic smoke mode，讓 `.cmd` / `.ps1` 可驗證 preamble、
  active repo delegation 和 log 寫入，不會真的啟動 GUI。

### 影響範圍

- Launchers：`scripts/launchers/xbrainlab_wsl_launcher.cmd`、
  `scripts/launchers/xbrainlab_wsl_launcher.ps1`、
  `/mnt/c/Users/Administrator/Desktop/XBrainLab.cmd`。
- Startup shell：`run.py`。
- UI shell：`XBrainLab/ui/main_window.py`、`XBrainLab/ui/window_placement.py`。
- Tests：`tests/integration/ui/test_window_geometry.py`、
  `tests/unit/ui/test_window_placement.py`。

### 驗證

- `poetry run pytest --capture=sys tests/integration/ui/test_window_geometry.py tests/unit/ui/test_window_placement.py tests/unit/test_run_splash_geometry.py -q`
  - `19 passed`
- `poetry run ruff check run.py XBrainLab/ui/main_window.py XBrainLab/ui/window_placement.py tests/integration/ui/test_window_geometry.py tests/unit/ui/test_window_placement.py tests/unit/test_run_splash_geometry.py`
  - `All checks passed!`
- `poetry run basedpyright`
  - `0 errors, 0 warnings, 0 notes`
- Launcher smoke：
  - PowerShell parser：`PowerShell syntax OK`
  - repo `.cmd` smoke：active repo bootstrap passed
  - Desktop `.cmd` smoke：active repo bootstrap passed
  - repo `.ps1` smoke：WSL stdout / stderr were mirrored to terminal and launcher log

### 剩餘風險

- 本輪仍未執行真人雙螢幕 Windows click-through；automated / smoke tests 可證明 launcher 指向 active
  repo、terminal 不再黑、diagnostic logging 可用、post-show recovery 有 regression coverage，但不能
  完全替代真 Windows window manager 驗收。

## 2026-05-02 Dual-monitor startup geometry follow-up

### 背景

第一版 MainWindow geometry recovery 通過 automated tests，但人工回報真 Windows desktop
launcher 仍會把視窗打到最上方，且啟動 loading splash 不在螢幕中央。這代表原修復只覆蓋
top-left / offscreen，沒有完整處理 top-edge、native frame titlebar、dual-monitor startup
screen selection。

### 變更

- 新增 `XBrainLab/ui/window_placement.py`，集中處理：
  - saved geometry screen ranking
  - cursor / primary fallback
  - startup screen hint
  - splash centering
  - frame-aware geometry health check
- `run.py` 在 splash `show()` 前先置中，並記住同一個 startup screen，讓 splash 和
  MainWindow 不再各自選螢幕。
- MainWindow 改用 shared placement helper；restored / persisted geometry 會檢查
  client geometry、native frame geometry、available geometry 和 full screen geometry。
- top-edge、top-center、top-right、frame top 超出螢幕、跨螢幕 frame 都會視為不健康並
  reset / recenter。
- 預設 window size 改成保留更多上下視覺空間，避免小螢幕上看起來貼在最上方。

### 影響範圍

- Startup shell：`run.py`。
- UI shell：`XBrainLab/ui/main_window.py`、`XBrainLab/ui/window_placement.py`。
- Tests：`tests/integration/ui/test_window_geometry.py`、
  `tests/unit/ui/test_window_placement.py`、`tests/unit/test_run_splash_geometry.py`。

### 驗證

- `poetry run pytest --capture=sys tests/integration/ui/test_window_geometry.py tests/unit/ui/test_window_placement.py tests/unit/test_run_splash_geometry.py -q`
  - `15 passed`
- `poetry run ruff check run.py XBrainLab/ui/main_window.py XBrainLab/ui/window_placement.py tests/integration/ui/test_window_geometry.py tests/unit/ui/test_window_placement.py tests/unit/test_run_splash_geometry.py`
  - `All checks passed!`
- `poetry run basedpyright`
  - `0 errors, 0 warnings, 0 notes`

### 剩餘風險

- 本輪仍需要真雙螢幕 Windows launcher 人工 click-through。Automated tests 可覆蓋 screen
  ranking、top-edge rejection、splash centering helper，但不能完全替代 Windows / WSLg
  window manager 行為。

## 2026-05-02 MainWindow saved geometry recovery

### 背景

人工退件指出 Windows desktop launcher 開啟後主視窗會卡到螢幕左上角且移動不了。
既有實作只要 `restoreGeometry()` 成功就只做 available-screen clamp，沒有判斷該 geometry
是否產品上可拖曳、titlebar 是否可達，也會在 `closeEvent()` 反覆保存壞狀態。

### 變更

- `MainWindow` 新增 restore/persist 前的 geometry 健康檢查：貼左上、offscreen、尺寸不合理、
  titlebar 不可達會被視為不健康。
- 啟動時若 saved `main_window/geometry` 不健康，會 `remove("main_window/geometry")` 並用
  留出 titlebar 拖曳空間的預設位置重置。
- 首次啟動的預設大小 / 位置會避開左上角，仍限制在 available screen 內。
- `closeEvent()` 只保存健康的 normal geometry；壞 geometry 會移除，避免永久卡住。
- 補 Assistant dock titlebar event regression，確認自訂 titlebar 空白區不吃掉
  `QDockWidget` 原生拖曳事件。

### 影響範圍

- UI shell：`XBrainLab/ui/main_window.py`。
- Regression tests：`tests/integration/ui/test_window_geometry.py`、
  `tests/unit/ui/components/test_agent_manager.py`。
- Docs：`docs/planning/now.md`、`docs/records/worklog.md`、
  `docs/records/implementation_log.md`。

### 驗證

- `poetry run pytest --capture=sys tests/integration/ui/test_window_geometry.py -q`
  - `6 passed`
- `poetry run pytest --capture=sys tests/unit/ui/components/test_agent_manager.py tests/integration/ui/test_product_walkthrough.py -q`
  - `32 passed`
- `poetry run ruff check XBrainLab/ui/main_window.py XBrainLab/ui/components/agent_manager.py tests/integration/ui/test_window_geometry.py`
  - `All checks passed!`
- `poetry run basedpyright`
  - `0 errors, 0 warnings, 0 notes`

### 剩餘風險

- 本輪沒有執行真人 Windows Desktop launcher click-through；persisted bad geometry recovery
  已由 automated regression tests 覆蓋。

## 2026-05-02 Product validation closure

### 背景

最後一輪 review 指出 fast dashboard 曾經 FAIL，且 canonical docs 仍有 stale evidence。
需要把退件修復、最新 dashboard 和剩餘 manual evidence 收斂成 current truth。

### 變更

- 修正 assistant local-disabled startup，讓使用者在 transcript 看到明確 unavailable reason。
- 修正 confirmation / tool transcript，不再把 raw tool names、schema 或 backend wording 當產品文字顯示。
- 修正 montage apply path，避免繞過 `ApplicationService` command surface。
- 修正 `run.py` / assistant startup path，維持 local-only runtime；remote backend modules 已從
  product package 移除，remote SDK 只在 optional legacy group。
- 穩定 UI baseline capture geometry。
- 更新 UI unit legacy runtime expectations：remote model switch fail-closed 到 local-only，
  active local model deletion 會被 block。
- 刷新 deterministic agent eval artifact：`artifacts/agent_evals/latest.json`。
- 更新 canonical docs：`current.md`、`validation/README.md`、records。

### 影響範圍

- Product validation truth：fast dashboard、UI product gate、agent/backend command gate、
  backend / IO / pipeline integration、LLM local settings / scripts。
- Documentation：current state、validation strategy、worklog、implementation log。
- Related commits：`8b04380`、`1883d4b`、`8a6099a`、`41ec91c`、`3edee21`、
  `5ed1c87`、`4cd4d4c`、`406719c`、`e5454c7`。

### 驗證

- Latest fast dashboard:
  - `artifacts/quality/latest.md`
  - generated at `2026-05-02 20:35:07 UTC+08:00`
  - overall `PASS`
  - Ruff PASS
  - Basedpyright PASS：`0 errors, 0 warnings, 0 notes`
  - Architecture PASS
  - Startup Smoke PASS
  - UI Baseline PASS
  - UI Dialog PASS
  - UI Unit Suite：`814 passed`
  - Real-Data IO Integration：`31 passed, 8 warnings`
- Additional supervisor gates:
  - `git diff --check` PASS
  - `poetry run ruff check .` PASS
  - `poetry run basedpyright` PASS
  - `poetry run mkdocs build --strict` PASS
  - `poetry run python tests/architecture_compliance.py` PASS
  - UI product / geometry gate：`121 passed`
  - agent / backend command gate：`225 passed`
  - backend + IO integration：`33 passed, 8 warnings`
  - full pipeline integration：`70 passed, 4 warnings`
  - LLM / local settings / script unit gate：`674 passed`
  - deterministic tool-call eval artifact refresh：commit
    `e5454c7 test: refresh agent eval artifact`
- Local model preflight:
  - primary `microsoft/Phi-4-mini-instruct` already cached
  - current / projected cache `15.34 GB`
  - available disk `158.54 GB`
  - estimated download `0.00 GB`
  - VRAM estimate `9.0 GB`
  - license MIT

### 剩餘風險

- Windows Desktop launcher click-through 尚未人工驗收。
- true local LLM ChatPanel long walkthrough 尚未跑。
- external thesis dataset experiment / statistical reporting 尚未完成。

## 2026-05-02 Local-only assistant runtime enforcement

### 背景

人工驗收指出先前只是把 Gemini/API 從一般 UI gate 隱藏，product code 仍可經由
`INFERENCE_MODE=api`、舊 settings 或 worker model switch 進入 remote backend。這不符合
local-only runtime 目標。

### 變更

- `LLMConfig` 變成 local-only runtime truth：舊 remote mode 只作 migration input，讀入後統一回
  `local`。
- `LLMEngine` 只 instantiate `LocalBackend`；product package 刪除 remote backend modules。
- `AgentWorker.reinitialize_agent(...)` 只接受 local model catalog 裡的 Phi primary / fallback 或
  generic `Local`，其他 model name fail closed。
- `ModelSettingsDialog` 移除 remote key verification / remote model UI，只保留 local model
  install/delete/activate 和 generation parameters。
- `pyproject.toml` default dependencies 移除 remote SDK；remote SDK 只保留 optional legacy group。
- 刪除 Gemini verify/list scripts，移除 legacy benchmark scripts 的 Gemini model option。
- `tests/architecture_compliance.py` 新增 local-only runtime static guard，禁止 product path 重新出現
  remote backend class / remote key env path。

### 影響範圍

- Runtime：`XBrainLab/llm/core/config.py`、`engine.py`、`agent/worker.py`、local backend package。
- UI settings：`XBrainLab/ui/dialogs/model_settings_dialog.py`。
- Tests / scripts / deps：LLM unit tests、model settings tests、benchmark model configs、Poetry deps。
- Docs：current、agent architecture、validation、records。

### 驗證

- Targeted subset：
  - `poetry run pytest --capture=sys tests/unit/llm/core/test_config.py tests/unit/llm/core/test_engine.py tests/unit/llm/agent/test_worker.py tests/unit/ui/dialogs/test_model_settings.py -q`
  - `73 passed`
- LLM unit suite:
  - `poetry run pytest --capture=sys tests/unit/llm -q`
  - `644 passed`
- Required validation:
  - `git diff --check`
  - `poetry run ruff check XBrainLab/llm XBrainLab/ui/dialogs/model_settings_dialog.py tests/unit/llm tests/unit/ui/dialogs tests/architecture_compliance.py`
  - `poetry run pytest --capture=sys tests/unit/llm tests/unit/ui/dialogs/test_model_settings.py tests/unit/scripts/test_plan_local_model_download.py tests/unit/scripts/test_inspect_local_assistant_runtime.py -q`
  - `674 passed`
  - `poetry run python tests/architecture_compliance.py`
  - `Architecture compliant`
- Manual fail-closed probes:
  - `INFERENCE_MODE=api` -> `local local`
  - settings JSON with Gemini mode -> `local local local False`
  - `reinitialize_agent("Gemini")` -> no backend switch, one error signal

### 剩餘風險

- 本輪不下載模型、不跑真 GPU 長 smoke。
- 真 local model 長時間 ChatPanel walkthrough 和 Windows launcher click-through 仍未完成。

## 2026-05-02 Assistant product shell and geometry rebuild

### 背景

人工退件指出 Assistant 仍像 debug / developer panel：第一層出現 runtime / backend 狀態、
mode wording、local model readiness，footer 沒有承擔使用者有用的 workflow hint；同時 app
啟動 geometry / dock titlebar 行為可能導致視窗 off-screen 或 dock 不易拖動。

### 變更

- `ChatPanel` 第一層重整為產品 shell：header 只保留產品標題與 icon-only `...` options；
  empty state 使用 EEG workflow 語言；composer footer 只顯示 workflow next action。
- runtime / backend diagnostics 從 visible first layer 移到 tooltip / settings / logs；visible
  transcript 不顯示 raw tool syntax、JSON、backend facade / service naming。
- `AgentManager` dock titlebar 改成會 ignore 空白區 mouse events 的 custom titlebar，保留
  QDockWidget 原生 drag / float；floating dock 會 clamp 到可用螢幕。
- `MainWindow` 新增 first-run centering、saved geometry restore、off-screen clamp，以及
  resize / maximize / restore regression test。
- `VRAMConflictChecker` 補上缺少 visualization panel 時的安全路徑，並移除 Gemini wording。
- 更新 chat / product walkthrough / AgentManager / window geometry tests 和 Assistant screenshot
  artifact / baseline。

### 影響範圍

- UI shell：`XBrainLab/ui/chat/panel.py`、`XBrainLab/ui/chat/styles.py`。
- Dock / window：`XBrainLab/ui/components/agent_manager.py`、
  `XBrainLab/ui/components/vram_checker.py`、`XBrainLab/ui/main_window.py`、
  `XBrainLab/ui/styles/stylesheets.py`。
- Tests / artifacts：chat unit、product walkthrough、AgentManager coverage、window geometry、
  `artifacts/ui/ai-assistant-open.png`、`tests/baselines/ui/ai-assistant-open.png`。

### 驗證

- `git diff --check`
- `poetry run ruff check XBrainLab/ui/chat XBrainLab/ui/components/agent_manager.py XBrainLab/ui/main_window.py tests/unit/ui/chat tests/integration/ui`
  - `All checks passed!`
- `scripts/dev/run_ui_pytest.sh tests/unit/ui/chat/test_chat_panel.py tests/integration/ui/test_product_walkthrough.py -q`
  - `42 passed in 9.22s`
- `scripts/dev/run_ui_pytest.sh tests/unit/ui/chat/test_chat_panel.py tests/integration/ui/test_product_walkthrough.py tests/integration/ui/test_window_geometry.py tests/unit/ui/components/test_agent_manager.py tests/unit/ui/test_agent_manager_coverage.py -q`
  - `92 passed in 10.86s`
- `xvfb-run -a poetry run python scripts/dev/capture_ui_baseline.py`
  - refreshed Assistant screenshot artifact and baseline.

### 剩餘風險

- 尚未做真 Windows launcher click-through。
- 尚未做真 local model 長時間 ChatPanel walkthrough；本輪沒有下載模型，也沒有改 LLM runtime core。

## 2026-05-02 Assistant product status polish

### 背景

Goal session 完成 Assistant product audit follow-up 後，人工審核仍發現 footer / runtime
status 有重複資訊風險：頂部已顯示 workflow guidance，底部再出現完整
`Workflow: ... | Assistant: ...` 會讓 Assistant dock 看起來像 debug console。此問題雖不會讓
測試失敗，但會影響使用者第一眼感受。

### 變更

- `ChatPanel` 不再把 legacy `runtime_status_label` 加到 visible composer footer；它保留為
  compatibility anchor / tooltip carrier，避免舊測試或 caller 直接斷裂。
- header subtitle 從較長的操作說明改成 `From data import to training`。
- footer runtime summary 改成低干擾狀態與 tooltip，不再在畫面底部重複 workflow diagnostics。
- 控制列高度從 70px 壓到 64px，讓 composer 區更像輸入區，而不是第二層 debug status bar。
- 更新 `artifacts/ui/ai-assistant-open.png` 和 `tests/baselines/ui/ai-assistant-open.png`。
- 修正 controller coverage 測試：exception path 不再用 `hi`，避免被 greeting shortcut 提前處理。

### 影響範圍

- UI：`XBrainLab/ui/chat/panel.py`、`XBrainLab/ui/chat/styles.py`。
- Tests / artifacts：chat panel unit、LLM controller coverage、Assistant dock screenshot baseline。

### 驗證

- `git diff --check`
- `poetry run pytest --capture=sys tests/unit/llm/agent/test_controller_cov.py tests/unit/ui/chat/test_chat_panel.py -q`
  - `67 passed`
- `poetry run ruff check XBrainLab/ui/chat/panel.py tests/unit/ui/chat/test_chat_panel.py tests/unit/llm/agent/test_controller_cov.py`
  - `All checks passed!`
- `poetry run ruff format --check XBrainLab/ui/chat/panel.py tests/unit/ui/chat/test_chat_panel.py tests/unit/llm/agent/test_controller_cov.py`
  - `3 files already formatted`
- `poetry run basedpyright`
  - `0 errors, 0 warnings, 0 notes`
- `poetry run python scripts/dev/update_quality_dashboard.py`
  - overall `PASS` at `2026-05-02 18:11:29 UTC+08:00`
  - includes Ruff, Basedpyright, Architecture Compliance, Startup Smoke, UI Baseline Capture,
    UI Dialog Acceptance, UI Unit Suite `830 passed`, and Real-Data IO Integration `31 passed`。

### 剩餘風險

- 真 Windows launcher click-through 尚未做。
- 真 local model 長時間 ChatPanel walkthrough 尚未做；本輪沒有下載模型，也沒有長時間 local
  LLM smoke。
- Gemini/API code path 已從一般產品入口隔離，但 source code 尚未刪除。

## 2026-05-02 Assistant product audit follow-up

### 背景

人工產品審核明確指出上一輪仍不合格：Assistant dock 頂部擠滿 chips / controls、主視覺仍像
debug panel、user bubble 在窄 dock 會切字、Retry 沒有上一則 request 時污染 transcript、
agent 會把 raw tool output / schema error / empty list 直接回給使用者。這些問題不能靠
dashboard PASS 或 deterministic eval 解釋掉，必須從產品 UI 與 agent visible-output boundary 修。

### 變更

- 重新整理 `ChatPanel`：
  - header 只保留產品名、自然語言 subtitle、`Options`。
  - workflow state / next step 改成單句 guidance，不再是 top chip dump。
  - local runtime / backend readiness 移到底部低干擾 status / tooltip / settings。
  - `Retry` / `Clear` 移到 composer footer；沒有 previous request 時 `Retry` disabled。
  - empty state 改成 EEG 使用者起始導引；message bubble 增加 minimum text column，避免
    `hello` 在 380px dock 被切碎。
- 改 `AgentManager.retry_last_user_input()`：沒有上一則 request 時只顯示 footer/status notice，
  不新增 assistant bubble。
- 改 `LLMController` visible-output path：
  - greeting shortcut 直接回產品導引，不先 call tool。
  - visible tool summary 使用產品語言，不顯示 `Tool <name> completed (...)`。
  - missing argument / empty result / backend precondition / runtime error 分 bucket 處理。
  - structured `Tool Output` 繼續保留在 controller history / diagnostics / logs，不進第一層
    ChatPanel transcript。
- 改 `ToolCommandResult` / `application_surface.py`：legacy read-only `list_files` /
  `get_dataset_info` 也會正規化為 typed result，避免 `"Error: ..."` 或 `[]` 被當成成功回覆。
- 隔離 legacy remote runtime：`XBRAINLAB_SHOW_LEGACY_REMOTE_LLM=1` 未設定時，ChatPanel
  model menu、ModelSettingsDialog remote section、AgentManager startup 都不顯示或啟動 Gemini。
- 更新 UI screenshot evidence：
  - `artifacts/ui/ai-assistant-open.png`
  - `tests/baselines/ui/ai-assistant-open.png`

### 影響範圍

- UI：`XBrainLab/ui/chat/*`、`AgentManager`、model settings、main-window debug feedback。
- Agent：`LLMController`、tool result adapter、agent product-flow tests。
- Runtime config：legacy remote runtime product visibility gate。
- Docs / records / UI baseline artifacts。

### 驗證

- UI assistant / settings / AgentManager gate：
  - `timeout 300s scripts/dev/run_ui_pytest.sh tests/unit/ui/chat/test_chat_panel.py tests/unit/ui/chat/test_message_bubble.py tests/unit/ui/dialogs/test_model_settings.py tests/unit/ui/components/test_agent_manager.py tests/unit/ui/test_agent_manager_coverage.py -q`
  - `131 passed`
- agent product-flow / tool formatting / config gate：
  - `timeout 240s poetry run pytest --capture=sys tests/integration/agent/test_product_flow.py tests/unit/llm/agent/test_controller.py tests/unit/llm/tools/test_application_surface.py tests/unit/llm/tools/real/test_real_tools.py tests/unit/llm/core/test_config.py -q`
  - `110 passed`
- backend application / facade workflow gate：
  - `timeout 240s poetry run pytest --capture=sys tests/unit/backend/application tests/integration/backend/test_application_service_workflow.py tests/unit/backend/test_facade_coverage.py tests/unit/backend/test_facade_headless.py -q`
  - `57 passed`
- product walkthrough / agent integration:
  - `timeout 300s scripts/dev/run_ui_pytest.sh tests/integration/ui/test_product_walkthrough.py -q`
  - `2 passed`
  - `timeout 180s poetry run pytest --capture=sys tests/integration/agent/test_tool_call_eval.py tests/integration/agent/test_product_flow.py -q`
  - `7 passed`
- UI capture：
  - `timeout 240s xvfb-run -a poetry run python scripts/dev/capture_ui_baseline.py`
  - saved `artifacts/ui/ai-assistant-open.png`
- aggregate dashboard：
  - `timeout 420s poetry run python scripts/dev/update_quality_dashboard.py`
  - overall `PASS` at `2026-05-02 17:44:37 UTC+08:00`

### 剩餘風險

- 這輪有 screenshot artifact 和 deterministic layout assertions，但仍需要人工 UI 審核判斷
  380-460px dock 是否符合產品質感。
- 真 Windows launcher click-through 尚未做。
- 真 local model 長時間 ChatPanel walkthrough 未做；本輪沒有下載模型，也沒有長時間 local LLM smoke。
- Gemini/API code path 只是從一般產品入口隔離，尚未從 codebase 刪除。
- label import、smart parse、montage confirmation 仍是 controller / UI-request legacy path。

## 2026-05-02 Assistant runtime consent、service query commands 與 thesis split protocol

### 背景

本輪人工接手要求把 XBrainLab 往工程級桌面產品交付推進，而不是只修局部 patch。
前一輪已修 chat visible-response blocker，但仍留下三個產品缺口：Assistant UI 第一層仍有
過多 debug/control 資訊、本地 LLM 啟用缺少 first-run consent、UI / agent / backend 對 query
commands 與 dialog submit path 尚未完整收斂。另外，thesis-grade validation 不能只靠 tiny
pipeline smoke，需要固定 split protocol 和 artifact audit。

### 變更

- ChatPanel 將 persona/runtime/step mode 收進 Options / 低干擾 status；主視覺保留自然語言
  workflow stage 和 next step，不顯示 raw command names。
- 新增 `LocalRuntimeFirstRunDialog`，首次啟用 local runtime 前顯示 GPU/CPU resource notice、
  estimated download、cache status、provider/license/VRAM estimate，提供 Enable / Download /
  Use existing cache / Later / Disable。
- `LLMConfig` 增加 `local_runtime_notice_acknowledged`，settings dialog 和 assistant panel
  共用 local runtime truth；app startup 不自動載入大型 local model。
- `ApplicationService` 將 `evaluate`、`visualize`、`saliency`、`new_session` 從 placeholder
  推進成 typed query / lifecycle command；`BackendFacade.get_latest_results()` 保留 legacy
  shape，同時保存 service diagnostics。
- UI dialog/query paths 改走 command adapter：channel selection、split dataset、model
  selection、training settings、evaluation query、visualization query、saliency setup/query。
- agent deterministic eval 更新 query-command 語意；tool result payload 保留 diagnostics /
  state / capability。
- 新增 `XBrainLab/backend/dataset/split_audit.py`、`scripts/dev/validate_split_artifact.py`、
  `docs/validation/thesis_protocol.md`、`docs/validation/split_artifact_schema.json`，支援 split
  indices 保存、subject/session leakage audit 和 artifact validation。

### 影響範圍

- backend ApplicationService / BackendFacade
- UI ChatPanel / AgentManager / model settings / workflow sidebars
- agent deterministic eval artifacts
- split validation helper、script、tests
- current / planning / architecture / validation / records docs

### 驗證

- `poetry run ruff check XBrainLab/ tests/ scripts/dev/validate_split_artifact.py` 通過。
- `poetry run ruff format --check XBrainLab/ tests/ scripts/dev/validate_split_artifact.py` 通過。
- `git diff --check` 通過。
- `poetry run mkdocs build --strict` 通過。
- UI product gate：
  - `timeout 300s scripts/dev/run_ui_pytest.sh tests/unit/ui/chat/test_chat_panel.py tests/unit/ui/components/test_agent_manager.py tests/unit/ui/dialogs/test_local_runtime_first_run_dialog.py tests/integration/ui/test_product_walkthrough.py -q`
  - `62 passed`
- backend / validation / config gate：
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py tests/unit/backend/dataset/test_split_audit.py tests/unit/scripts/test_validate_split_artifact.py tests/unit/llm/core/test_config.py -q`
  - `41 passed`
- agent / facade / backend workflow gate：
  - `timeout 300s poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/unit/llm/agent/test_controller.py tests/unit/llm/agent/test_worker.py tests/unit/backend/test_facade_coverage.py tests/unit/backend/test_facade_headless.py tests/integration/backend/test_application_service_workflow.py -q`
  - `130 passed`
- deterministic eval artifact refresh：
  - `timeout 120s poetry run python scripts/agent/evals/run_tool_call_eval.py --output-dir artifacts/agent_evals`
  - `21 / 21` deterministic cases passed after query-command semantic update.
- full test gate：
  - `timeout 2400s poetry run pytest tests/ --deselect tests/unit/ui/test_visualization.py::TestSaliency3DEngine --tb=short -q`
  - `4386 passed, 3 skipped, 3 deselected, 1 xfailed, 14 warnings`

### 剩餘風險

- 真 Windows Desktop launcher click-through 尚未人工驗收。
- 真 local model 長時間 ChatPanel walkthrough 沒有跑；本輪只跑 preflight/cache/status/UI logic，
  沒有重複載入大型模型。
- label import、smart parse、montage confirmation 仍是 legacy / UI-request path。
- thesis protocol 已有 schema / audit / validator，但 external thesis dataset runner、repeat
  runs、baseline comparison、statistical reporting 尚未完成。

## 2026-05-02 Chat product flow blocker 與 visible-response contract

### 背景

使用者人工打開 AI Assistant 後發現兩個產品阻塞：介面仍像 debug dock，且輸入 `hello`
後沒有 assistant 回覆。這代表先前 automated final gate、local prompt smoke、launcher
startup smoke、deterministic eval 都沒有覆蓋最基本的 user-visible chat path，不能再宣稱
product delivery 完成。

### 變更

- `LLMController` 新增 visible-response contract：
  - empty model response 會回 visible error，不再 silent finalize。
  - tool-only successful turn 會產生 short tool summary，避免 JSON 被隱藏後使用者看不到結果。
  - ApplicationService blocked command 會立即發出 shared blocked reason。
  - busy re-entry 會顯示 assistant still processing，而不是默默忽略。
- `AgentManager` 在 controller busy 時不再先加入新的 user message 再被 controller 吃掉。
- `ChatPanel` 重新設計成產品級結構：
  - header：`XBrainLab Assistant`、backend stage chip、local model status chip、available command chip。
  - empty state：說明 assistant 可做 state inspection、blocked reason explanation、workflow guidance。
  - conversation area：專業 bubble、padding、max width、可讀 contrast。
  - composer：清楚 `Send` / `Stop` 狀態，processing 時禁用會造成 race 的 controls。
- 新增 product-flow tests：
  - normal `hello` path 產生 user bubble + assistant bubble + non-empty content。
  - empty response fallback visible。
  - worker error visible。
  - local unavailable first-open visible。
  - ChatPanel structure / status chips / composer controls。
- 文件校正 automated evidence 邊界：dashboard / deterministic eval / local smoke 不能替代真 chat product flow。

### 影響範圍

- UI chat panel
- AgentManager wiring
- LLMController response finalization
- UI / agent validation tests
- current / planning / architecture / validation docs

### 驗證

- `timeout 240s scripts/dev/run_ui_pytest.sh tests/unit/ui/chat/test_chat_panel.py tests/unit/ui/components/test_agent_manager.py -q`
  - `55 passed`
- `timeout 180s poetry run pytest --capture=sys tests/unit/llm/agent/test_controller.py tests/unit/llm/agent/test_worker.py -q`
  - `75 passed`
- `timeout 300s scripts/dev/run_ui_pytest.sh tests/unit/ui -q`
  - `817 passed`
- `timeout 300s poetry run pytest --capture=sys tests/unit/llm -q`
  - `652 passed`
- `timeout 180s poetry run basedpyright`
  - `0 errors, 0 warnings, 0 notes`
- `timeout 180s poetry run pytest --capture=sys tests/unit/llm/agent/test_controller.py tests/unit/llm/agent/test_worker.py tests/unit/llm/core/test_local_backend.py tests/unit/llm/core/test_engine.py -q`
  - `102 passed`
- `timeout 120s poetry run mkdocs build --strict`
  - passed
- `timeout 60s git diff --check`
  - passed
- `timeout 360s poetry run python scripts/dev/update_quality_dashboard.py`
  - overall `PASS`
  - UI baseline capture `PASS`
  - Basedpyright `0 errors`

### 剩餘風險

- 這一輪的 normal chat product-flow tests 使用 fake controller / fake engine，不載入大模型；
  真 local Phi model 的 full chat walkthrough 仍需 resource-safe smoke。
- Windows Desktop shortcut 的人工 click-through 仍未完成。
- UI action execution 仍有 controller direct-call legacy path；本輪修的是 chat product blocker，
  不是完成所有 UI command adapter migration。

## 2026-05-02 Deterministic tool-call eval baseline

### 背景

product-delivery final gate 通過後，可以開始 tool-call eval / thesis evidence 的第一層。
為避免把 local model loading 和 eval framework 綁死，先建立 deterministic scripted baseline；
這能驗證 case schema、scoring 維度、artifact 產出和 ApplicationService state/capability
邏輯，不宣稱 local LLM 真實成功率。

### 變更

- 新增 `scripts/agent/evals/run_tool_call_eval.py`。
- 建立 `21` 個 XBrainLab 專用 cases，覆蓋 empty/load/preprocess/epoch/dataset/train/reset/
  visualize/saliency/invalid parameter/multi-turn recovery/tool-result interpretation。
- scoring 維度包含 intent、tool selection、argument correctness、state-aware decision、
  blocked-command handling、multi-turn recovery、tool result interpretation、trajectory quality、
  runtime safety、local LLM reliability。
- 產出 machine-readable `artifacts/agent_evals/latest.json` 與 human-readable
  `artifacts/agent_evals/latest.md`。
- 新增 `tests/integration/agent/test_tool_call_eval.py`，驗證至少 20 cases、summary metrics 和
  artifact writing。

### 影響範圍

- agent validation scripts
- validation artifacts
- thesis evidence foundation
- validation docs

### 驗證

- `timeout 180s poetry run pytest --capture=sys tests/integration/agent -q`
  - `1 passed`
- `timeout 120s poetry run python scripts/agent/evals/run_tool_call_eval.py --output-dir artifacts/agent_evals`
  - `21 / 21` deterministic cases passed
  - artifacts written to `artifacts/agent_evals/latest.json` and `artifacts/agent_evals/latest.md`

### 剩餘風險

- 這是 deterministic baseline，不是 local LLM primary / fallback 真實 tool-call result。
- 下一步要接 local model runner，測同一批 cases 的穩定性、structured-output failure、
  retry / recovery 和 model-to-model 差異。

## 2026-05-02 Final product gate 與 local model preflight idempotence

### 背景

final gate 前的 local model preflight 暴露出一個產品交付問題：primary model 已在
`XBrainLab/llm/core/models` cache 中，但 preflight 仍把它當成新下載，導致 projected cache
從 `15.34 GB` 誤算成 `23.03 GB` 並回報超過 20GB 上限。這會讓已安裝模型的使用者看到錯誤
下載狀態。

### 變更

- `plan_model_download()` 現在會辨識 Hugging Face cache layout 和 safe local cache layout。
- 若模型已存在，preflight 回傳 `ok=True`、estimated download `0.00 GB`，projected cache
維持 current cache。
- 補 `test_download_preflight_allows_already_cached_model_without_increment()`。
- final gate 依 resource-safe execution 單項執行 backend、UI、LLM、pipeline、local runtime、
launcher、MkDocs 與 whitespace 檢查。

### 影響範圍

- local model download preflight
- operations / validation docs
- final product gate evidence

### 驗證

- `timeout 120s poetry run pytest --capture=sys tests/unit/llm/core/test_model_catalog.py tests/unit/scripts/test_plan_local_model_download.py -q`
  - `7 passed`
- `timeout 120s poetry run python scripts/dev/plan_local_model_download.py --format markdown`
  - `ok=True`; primary already cached; projected cache `15.34 GB`
- `timeout 300s poetry run pytest --capture=sys tests/unit/backend -q`
  - `2661 passed, 1 skipped, 1 xfailed, 3 warnings`
- `timeout 300s poetry run pytest --capture=sys tests/integration/backend tests/integration/io/test_io_integration.py -q`
  - `33 passed, 8 warnings`
- `timeout 600s poetry run pytest --capture=sys tests/integration/pipeline -q`
  - `70 passed, 4 warnings`
- `timeout 300s scripts/dev/run_ui_pytest.sh tests/unit/ui -q`
  - `811 passed`
- `timeout 300s poetry run pytest --capture=sys tests/unit/llm -q`
  - `649 passed`
- `timeout 300s poetry run python scripts/dev/inspect_local_assistant_runtime.py --format markdown --prompt-smoke --structured-smoke`
  - classification `gpu-ready`; prompt smoke `passed`; structured-output smoke `passed`
- `timeout 45s xvfb-run -a poetry run python run.py --model local`
  - `MainWindow initialized` before expected timeout.

### 剩餘風險

- launcher smoke is still automated startup under `xvfb`, not a human click-through of the Windows Desktop shortcut.
- local runtime health confirms prompt / structured smoke, but not full multi-turn scientific workflow quality.
- tool-call eval / thesis evidence still must wait until product walkthrough is stable.

## 2026-05-02 Agent tool typed result adapter

### 背景

UI / agent command surface 已開始共用 ApplicationService capability policy，但 agent real tools
仍有一個產品級可靠性缺口：部分 legacy tools 用字串回傳錯誤，例如 `"Error: ..."` 或
`"Failed ..."`，而 controller 會把「工具正常返回字串」當成 successful execution。這會讓
assistant 把 failed backend operation 記成成功，後續對話和 UI feedback 都會失真。

### 變更

- 在 `XBrainLab/llm/tools/application_surface.py` 新增 `ToolCommandResult` typed adapter。
- 將 ApplicationService blocked command 轉成 structured failed result，包含 command name、
  blocked reason、capability 和 state snapshot。
- 將 legacy string result 正規化：`Error:`、`Failed ...`、`Dataset generation failed ...`
  等會被視為 failed result，不再當成成功。
- `LLMController._execute_tool_no_loop()` 對 ApplicationService-backed tools 回傳
  `ToolCommandResult`，並把 failure 記入 metrics / history。
- `Tool Output` JSON payload 現在保留 `command_name`、`error_type`、`recoverable`、
  `blocked_reason`、`state`、`capability`、`raw_result`。
- 修正 `tests/unit/llm/agent/test_worker.py`，避免 LLM unit tests 將 repo `settings.json`
  污染回 Gemini / API mode。

### 影響範圍

- agent tool execution
- ApplicationService capability gate
- structured tool result history
- LLM unit tests and local runtime default config hygiene

### 驗證

- `timeout 120s poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/unit/llm/agent/test_controller.py -q`
  - `55 passed`
- `timeout 180s poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
  - `321 passed`
- `timeout 60s git diff --check`
  - 通過

### 剩餘風險

- 部分 real tools 仍先走 `BackendFacade` legacy method，再由 adapter 包成 structured result；
  之後應逐步讓 load / preprocess / epoch / dataset / train execution 直接回傳 backend
  `CommandResult`。
- UI side effects 仍使用 `Request:` 字串協定；下一步應改成 typed UI request/event。

## 2026-05-02 Local LLM runtime 與 desktop launcher baseline

### 背景

product-delivery 主線要求 XBrainLab 能逐步成為可直接使用的桌面軟體。使用者也明確要求
不可使用 Qwen，並進一步限制不可使用中國公司或中國來源模型。因此 local assistant runtime
不能保留 Qwen / DeepSeek / Yi / GLM / Baichuan / InternLM / MiniCPM 等模型作為候選，也不能
依賴 Gemini/API 作為產品路線。

### 變更

- 新增 `XBrainLab/llm/core/model_catalog.py`：
  - 定義 primary `microsoft/Phi-4-mini-instruct`。
  - 定義 fallback `microsoft/Phi-3.5-mini-instruct`。
  - 封裝非中國模型 allow-list、blocked provider policy、單模型 10GB / 總 cache 20GB preflight。
- 更新 local runtime：
  - `LLMConfig` 預設 local model 改為 Phi-4 mini，4-bit 不是預設硬需求。
  - `AgentWorker` 在 primary 不可用且 fallback cache ready 時依 policy 切到 fallback。
  - `LocalBackend` 阻擋 unsupported / policy-blocked local model。
  - 補 Phi remote-code compatibility patch，並讓 generation thread exception 回傳錯誤。
- 更新 UI：
  - Model settings 只列 product catalog 內的 local model。
  - AgentManager 第一次打開 chat panel 不再強迫 settings modal；local runtime unavailable 時面板保持可見並顯示原因。
- 更新 scripts：
  - `scripts/dev/plan_local_model_download.py`
  - `scripts/dev/inspect_local_assistant_runtime.py`
  - `scripts/launchers/xbrainlab_wsl_launcher.cmd`
  - `scripts/launchers/xbrainlab_wsl_launcher.ps1`
- 清理舊 Qwen cache，下載 primary / fallback Phi cache，並把可執行 benchmark script 的 Qwen model entry 移除。
- 複製可點擊 launcher 到 `/mnt/c/Users/Administrator/Desktop/XBrainLab.cmd`。

### 影響範圍

- local LLM model selection / download / health check
- agent runtime startup and fallback
- model settings dialog
- chat panel first-open failure boundary
- Windows launcher / operations docs
- local runtime and launcher validation docs

### 驗證

- fallback preflight：
  - `poetry run python scripts/dev/plan_local_model_download.py --model microsoft/Phi-3.5-mini-instruct --format markdown`
  - `ok: True`
  - projected cache `15.33 GB`
- primary health:
  - `poetry run python scripts/dev/inspect_local_assistant_runtime.py --format markdown --prompt-smoke --structured-smoke`
  - prompt smoke `passed`
  - structured-output smoke `passed`
- fallback health:
  - `poetry run python scripts/dev/inspect_local_assistant_runtime.py --model microsoft/Phi-3.5-mini-instruct --format markdown --prompt-smoke --structured-smoke`
  - prompt smoke `passed`
  - structured-output smoke `passed`
- startup smoke:
  - `timeout 35s xvfb-run -a poetry run python run.py --model local`
  - `MainWindow initialized` 後 timeout，屬 GUI smoke 預期結果。
- targeted tests:
  - `poetry run pytest --capture=sys tests/unit/llm/core/test_config.py tests/unit/llm/agent/test_worker.py tests/unit/ui/components/test_agent_manager.py -q`
  - `66 passed`
  - `poetry run pytest --capture=sys tests/unit/llm/core/test_local_backend.py -q`
  - `18 passed`

### 剩餘風險

- API / Gemini runtime code 仍存在，需要在產品收斂中隔離或移除；目前不再作產品目標。
- fallback 已驗證可載入與輸出，但尚未跑完整 agent multi-turn tool workflow。
- desktop launcher 已產出並通過 startup path smoke，但尚未完成真 click-through
  launcher -> chat panel -> tool call product walkthrough。
- local LLM smoke 尚未納入 fast quality dashboard 預設 profile。

## 2026-05-02 Product delivery 文件指令校準

### 背景

使用者指出 agent 仍把自己限制在「第一版後端 command layer 收尾」，但目前目標已經是
product-delivery engineering：backend、UI、agent、local LLM、desktop launcher 與後續
tool-call eval 要一路推進到工程級可用。檢查後發現 `docs/planning/now.md`、
`docs/index.md`、`.agents/runbooks/*`、`docs/planning/roadmap.md` 等 current-facing 文件
仍殘留文件整理期或全盤架構複盤期的保守指令。

### 變更

- 將 `docs/current.md` 和 `docs/index.md` 校準為 product-delivery 現況。
- 將 `docs/planning/now.md` 的「現在不做 / 第一版後端 Done Definition」改成
  Product Delivery Done Definition。
- 將 `docs/planning/roadmap.md` 改成 backend core、UI / agent command surface、
  UI chat、local LLM、desktop launcher、product stabilization、tool-call eval 的路線。
- 更新 `.agents/README.md`、`.agents/stack.md`、setup、autopilot、active queue、
  session prompts 和 architecture-review workflow，避免 agent 被舊 review gate 擋住。
- 更新 `docs/decisions/README.md`，記錄 milestone 是最低門檻、eval 要等產品穩定、
  local LLM 下載要受容量邊界控制。
- 更新 `docs/validation/README.md`，把目前優先驗證改成 product delivery 主線。

### 影響範圍

- agent 進場定位
- product delivery milestone
- planning / roadmap / decisions
- validation priority
- long-running autopilot behavior

### 驗證

- `poetry run mkdocs build --strict` 通過。
- `git diff --check -- docs .agents AGENTS.md README.md mkdocs.yml` 通過。
- stale instruction scan 通過：current-facing 文件中已沒有會要求「先全盤架構複盤、不開工、
  不一次做 UI / agent」的過期停止條件。
- legacy / active path check 通過：`docs/legacy/`、`docs/active/`、`.agents/legacy/`、
  `docs/records/documentation_audit.md` 皆不存在。

### 剩餘風險

- `docs/records/` 內仍保留歷史語句，作為流水帳與交接紀錄，不應被 agent 當 current truth。
- `architecture-review` workflow 仍可用於純 review 任務，但已標明不阻擋 product delivery。

## 2026-05-02 UI / Agent command surface unification

### 背景

後端 ApplicationService 第一版通過 contract tests，但 product-delivery gate 要求更高：
UI、Agent、Script 不應各自複製 readiness 判斷、state transition 規則或 blocked reason。
回頭驗收 Milestone 1 時也發現 `preprocess` capability 的前置條件判斷不夠準：raw-only
state 應允許 preprocessing，真正需要 preprocessed data 的是 `create_epoch`。

### 變更

- 修正 `CapabilityPolicy`：
  - `preprocess` 以 raw data 作為前置條件。
  - `create_epoch` 仍以 preprocessed data 作為前置條件。
- 新增 UI capability helper：
  - `XBrainLab/ui/application_capabilities.py`
  - UI component 可從 nearest real `Study` 取得 `BackendFacade.get_capabilities()`。
- UI 第一批 readiness 改讀 ApplicationService policy：
  - Dataset import -> `load_data`
  - Preprocess operations -> `preprocess`
  - Epoching -> `create_epoch`
  - Start Training -> `train`
- 新增 agent command surface：
  - `XBrainLab/llm/tools/application_surface.py`
  - 將 agent tool names 對映到 `CommandName`。
  - `ContextAssembler` 用 ApplicationService policy 列 available tools 和 blocked command reason。
  - `LLMController` 在 tool execution 前重新檢查同一 policy。
- Agent tool output 寫回 structured JSON payload：`ok`、`tool_name`、`message`、`raw_result`。
- Chat / AgentManager 補產品化控制：
  - retry
  - clear
  - backend/model compact diagnostics
  - debug tool flow 接到 `LLMController.execute_debug_tool()`
- 修正 `AgentWorker` runtime config reload：沒有 persisted config 時保留現有 engine config，
  避免生成前把已載入 runtime 誤覆蓋成 default unavailable local config。

### 影響範圍

- backend capability policy
- UI dataset / preprocess / training readiness
- chat panel and agent manager
- agent context assembly and execution guard
- local agent worker config sync
- backend / UI / LLM unit tests
- architecture docs

### 驗證

- `poetry run pytest --capture=sys tests/unit/backend/application -q` 通過，`9 passed`。
- `poetry run pytest --capture=sys tests/unit/backend/test_facade_coverage.py tests/unit/backend/test_facade_headless.py -q` 通過，`44 passed`。
- `poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q` 通過，`318 passed`。
- `scripts/dev/run_ui_pytest.sh tests/unit/ui -q` 通過，`807 passed`。
- `poetry run pytest --capture=sys tests/integration/backend/test_application_service_workflow.py -q` 通過，`2 passed`。
- `poetry run mkdocs build --strict` 通過。
- `git diff --check` 通過。

### 剩餘風險

- UI execution path 仍大量直接呼叫 controllers；目前完成的是 readiness / blocked reason 統一，
  不是完整 service-first UI migration。
- Real tools 還是透過 `BackendFacade` 舊字串回傳；conversation history 已保留 structured
  output，但 tool 本身尚未全面回傳 `CommandResult`。
- UI side effects 仍靠 `Request:` 字串協定，尚未 typed request/event 化。
- `evaluate`、`visualize`、`saliency`、`new_session` 仍是 disabled future command。

## 2026-05-02 Backend Application Service contract 收斂

### 背景

前一輪已新增 `XBrainLab/backend/application/`，但第二輪驗收發現 command
contract 還有不一致：部分 `CommandName` 有 policy entry，但沒有 command object 或
execute handler；`set_montage` 在 service 內回成功訊息但實際仍需 UI confirmation；
`reset_session` 只清資料與 trainer，尚未明確清掉 training config。

### 變更

- 補齊 future command objects：
  - `EvaluateCommand`
  - `VisualizeCommand`
  - `SaliencyCommand`
  - `NewSessionCommand`
- `CapabilityPolicy` 將 `evaluate`、`visualize`、`saliency`、`new_session` 標成
  unavailable future contract，不再宣稱可執行。
- `ApplicationService.execute()` 對未實作但保留的 command 回穩定 failure，不再可能因
  handler table 缺漏變成 `KeyError`。
- `set_montage` preprocess operation 改回 confirmation-required failure；實際 montage
  auto-match 仍留在 `BackendFacade` legacy path。
- `reset_session` 補 active session invalidation：除了 raw / preprocess / epoch /
  dataset / trainer，也清掉 model holder、training option 和 saliency params。
- `BackendFacade.load_data()` 在 total failure 時保留舊 `(count, errors)` raw error list
  shape；`stop_training()` inactive no-op 不再依賴錯誤訊息字串。
- 補強 tests：
  - command/policy coverage
  - future command stable failure
  - last_error lifecycle
  - reset confirmation and invalidation
  - training readiness capability transition
  - facade failure-shape / legacy montage / run-training precondition parity

### 影響範圍

- backend application command contract
- capability policy
- backend state snapshot / reset semantics
- `BackendFacade` compatibility surface
- backend application and facade tests
- backend architecture / planning docs

### 驗證

- `poetry run ruff check XBrainLab/backend/application XBrainLab/backend/facade.py tests/unit/backend/application tests/integration/backend/test_application_service_workflow.py tests/unit/backend/test_facade_coverage.py tests/unit/backend/test_facade_headless.py` 通過。
- `poetry run basedpyright XBrainLab/backend/application XBrainLab/backend/facade.py` 通過。
- `poetry run pytest --capture=sys tests/unit/backend/application tests/integration/backend/test_application_service_workflow.py tests/unit/backend/test_facade_coverage.py tests/unit/backend/test_facade_headless.py -q` 通過，`54 passed`。
- `poetry run pytest --capture=sys tests/unit/backend -q` 通過，`2660 passed, 1 skipped, 1 xfailed`。
- `poetry run pytest --capture=sys tests/integration/backend tests/integration/io/test_io_integration.py -q` 通過，`33 passed`。
- `poetry run pytest --capture=sys tests/integration/pipeline -q` 通過，`70 passed`。
- `poetry run mkdocs build --strict` 通過。
- `git diff --check` 通過。
- `poetry run python scripts/dev/update_quality_dashboard.py` 通過，`artifacts/quality/latest.md` 更新為 `PASS`。

### 剩餘風險

- UI 仍直接使用 controllers，尚未 service-first。
- `evaluate`、`visualize`、`saliency`、`new_session` 是明確 disabled 的 future contract，
  尚未實作 query/command behavior。
- `set_montage()` 仍是 `BackendFacade` legacy path。
- facade/controller parity 還需要更多 real workflow tests，尤其是 UI controller path。
- agent real tools 仍格式化 facade 舊回傳值，尚未直接消費 `CommandResult`。

## 2026-05-01 Backend Application Service / Command API 第一版

### 背景

後端在接手時已拆出 `DataManager` 和 `TrainingManager`，但 UI、assistant tools、
headless scripts 仍分別繞 controllers / `BackendFacade`。使用者確認本輪要實質推進
後端重構，方向是 UI / Agent / Script 共用 Application Service / Command API，
且 `BackendFacade` 只能作 wrapper，不能變成新的大泥球。

### 變更

- 新增 `XBrainLab/backend/application/`：
  - `commands.py`
  - `state.py`
  - `capabilities.py`
  - `results.py`
  - `errors.py`
  - `service.py`
- `ApplicationService` 提供：
  - state snapshot
  - backend-owned capability policy
  - command result envelope
  - application error boundary
  - command execution for load / attach labels / preprocess / epoch / dataset /
    training config / train / stop / reset
- `BackendFacade` 改成包 `ApplicationService`：
  - 保留舊方法名稱與舊回傳形狀，供 assistant real tools / scripts 相容。
  - 核心 workflow 不再在 facade 內重新拼裝。
- 修正 `RealListFilesTool` 在 WSL/Linux 下把不存在的 Windows fallback path
  resolve 成 repo root，導致 `tests/data` 被誤判成敏感路徑的問題。
- 補測試：
  - `tests/unit/backend/application/test_application_service.py`
  - `tests/integration/backend/test_application_service_workflow.py`
  - 更新 facade unit tests，對齊 service wrapper 行為。

### 影響範圍

- backend application layer
- agent/headless facade path
- command/capability/state contract
- backend unit and integration tests
- backend architecture / planning docs

### 驗證

- `poetry run ruff check XBrainLab/backend/application XBrainLab/backend/facade.py tests/unit/backend/application tests/integration/backend/test_application_service_workflow.py tests/unit/backend/test_facade_coverage.py tests/unit/backend/test_facade_headless.py` 通過。
- `poetry run basedpyright XBrainLab/backend/application XBrainLab/backend/facade.py` 通過。
- `poetry run pytest --capture=sys tests/unit/backend/application tests/integration/backend/test_application_service_workflow.py -q` 通過，`4 passed`。
- `poetry run pytest --capture=sys tests/unit/backend/test_facade_coverage.py tests/unit/backend/test_facade_headless.py -q` 通過，`40 passed`。
- `poetry run pytest --capture=sys tests/unit/backend -q` 通過，`2651 passed, 1 skipped, 1 xfailed`。
- `poetry run pytest --capture=sys tests/integration/backend/test_application_service_workflow.py tests/integration/io/test_io_integration.py -q` 通過，`32 passed`。
- `poetry run pytest --capture=sys tests/integration/pipeline -q` 通過，`70 passed`。
- `poetry run mkdocs build --strict` 通過。
- `git diff --check` 通過。
- `poetry run python scripts/dev/update_quality_dashboard.py` 通過，`artifacts/quality/latest.md` 更新為 `PASS`。

### 剩餘風險

- UI 仍直接使用 controllers，尚未改成 service-first。
- `set_montage()` 仍是 `BackendFacade` legacy path，因為它牽涉 UI confirmation。
- agent real tools 仍格式化 facade 舊回傳值，尚未直接消費 `CommandResult`。
- state invalidation、training readiness、facade/controller parity 還需要更多 real workflow tests。

## 2026-05-01 Documentation audit 收束

### 背景

`docs/records/documentation_audit.md` 是文件整理初期用來判斷可信度的過渡表。文件已重排成 current、target、architecture、planning、decisions、validation、records 後，這份 audit 會變成額外維護成本。

### 變更

- 刪除 `docs/records/documentation_audit.md`。
- 從 `README.md`、`docs/current.md`、`mkdocs.yml` 移除 active 入口。
- 從 `.agents/runbooks/setup.md` 和 `.agents/runbooks/autopilot.md` 移除對 audit 檔的依賴。
- 將文件可信度責任併回各 canonical 文件：現況寫 `current.md`，架構證據寫 `architecture/`，驗證邊界寫 `validation/README.md`，決策寫 `decisions/README.md`。

### 影響範圍

- 文件站 navigation
- repo root 入口
- agent reading order
- records 資料夾定位

### 驗證

- `poetry run mkdocs build --strict` 通過。
- `git diff --check -- README.md CHANGELOG.md AGENTS.md .agents docs mkdocs.yml` 通過。
- active stale reference scan 通過：排除 `docs/records/**` 後，沒有文件再引用 `documentation_audit` 或 `records/documentation_audit`。

## 2026-05-01 API / Gemini 移除決策校準

### 背景

文件原本把 API / Gemini code path 描述成待簡化或舊相容路徑。使用者確認這不是要保留的相容路徑，而是後續要拔掉的範圍。

### 變更

- 更新 `current.md`、`index.md`、`operations.md`、`decisions/README.md`。
- 更新 `planning/roadmap.md`、`planning/now.md` 和 `.agents/runbooks/active-queue.md`。
- 更新 `architecture/README.md`、`architecture/agent.md`、`architecture/validation.md`、`validation/README.md`。
- 更新 `.agents/context/project.md` 和 `.agents/runbooks/architecture-review.md`。

### 影響範圍

- assistant runtime 目標
- agent 架構複盤 checklist
- 後續 agent runtime 簡化範圍
- validation 目標邊界

### 驗證

- `poetry run mkdocs build --strict` 通過。
- `git diff --check -- docs .agents README.md CHANGELOG.md mkdocs.yml AGENTS.md` 通過。
- active wording scan 通過：active 文件已沒有 `移除或降級`、`legacy compatibility`、`compatibility path`、`待簡化殘留` 等會誤導成保留相容路線的說法。

## 2026-05-01 Target requirements 補 XBrainLab 本體

### 背景

`docs/target/requirements.md` 原本太快進入 assistant、command API 和 thesis validation，對 XBrainLab 本體作為本地 EEG 桌面分析工具的描述不足。

### 變更

- 補強產品定位：XBrainLab 的核心是本地 EEG workflow，不是聊天或模型 demo。
- 新增主要使用者描述。
- 新增 EEG workflow 本體需求。
- 新增桌面應用體驗、資料與狀態可追蹤、訓練與評估、視覺化與解釋需求。
- 將 assistant 放回 workflow 操作層，明確說明沒有 agent 時核心 EEG workflow 仍應可用。
- 修正 `target/README.md` 中 API / Gemini 殘留說法，對齊後續移除決策。

### 影響範圍

- target requirements
- target overview
- 後續全盤架構複盤的產品需求基準

### 驗證

- `poetry run mkdocs build --strict` 通過。
- `git diff --check -- docs/target docs/records/implementation_log.md docs/records/worklog.md` 通過。
- target wording scan 確認 `requirements.md` 已包含 EEG workflow、資料匯入、訓練與評估、視覺化、本地桌面 app、assistant 非唯一入口等本體需求。

## 2026-05-01 Target agent 補 State Manager / Verification Layer

### 背景

`docs/target/agent.md` 原本有寫 tool-call validation，但沒有把使用者設計的 Context Assembler、Prompt components、State Manager、Verification Layer、Self-Correction loop 明確記錄下來。

### 變更

- 新增 target control loop Mermaid 圖。
- 補 Context Assembler 的輸入：system prompt、tool definitions、RAG context、memory、state snapshot。
- 補 State Manager 的目標責任：workflow stage、data state、training state、command availability、recent tool result。
- 補 Verification Layer 的執行前檢查與失敗回饋。
- 補 tool schema 應標示 input、required state、side effect、result、error、confirmation。

### 影響範圍

- target agent 設計
- tool-call validation 目標
- 後續 agent runtime / command API 設計

### 驗證

- `poetry run mkdocs build --strict` 通過。
- `git diff --check -- docs/target/agent.md docs/records/implementation_log.md docs/records/worklog.md` 通過。
- target agent wording scan 確認 `Context Assembler`、`State Manager`、`Verification Layer`、`Self-Correction` 和 tool contract 欄位已寫入。

## 2026-05-01 Thesis evidence 改成 tool-call scoring system

### 背景

`docs/target/requirements.md` 原本只說 thesis evidence 要對到 command、test、artifact 或 experiment。使用者指出 thesis evidence 應該具體建立一套評分 agent tool-call 準確率的工具，並用它測試。

### 變更

- 更新 `target/requirements.md`，將 thesis evidence 改成 agent tool-call 評分工具與 benchmark report。
- 更新 `target/agent.md`，補 tool-call scoring system 的分項指標、case 類型與 thesis 邊界。
- 更新 `validation/README.md`，新增 Agent Tool-Call Scoring 區塊。
- 明確標示舊 `scripts/agent/benchmarks/*` 只能作歷史參考，新的 thesis evidence 要對齊 local-only runtime、State Manager、Verification Layer 和未來 Command API。

### 影響範圍

- thesis evidence 定義
- agent validation 目標
- 後續 benchmark / scorer 工具設計

### 驗證

- `poetry run mkdocs build --strict` 通過。
- `git diff --check -- docs/target/requirements.md docs/target/agent.md docs/validation/README.md docs/records/implementation_log.md docs/records/worklog.md` 通過。
- scoring wording scan 確認 `tool-call scoring system`、`benchmark cases`、`accuracy`、`score report`、`failure taxonomy` 已寫入 target / validation 文件。

## 2026-05-01 Target agent 補四個 contract 外框

### 背景

使用者確認 agent 目標應再定仔細一點，但不要把每個 tool schema 寫爆。需要先定能支撐後續實作與 thesis scoring 的 contract 外框。

### 變更

- 在 `docs/target/agent.md` 新增 Target contracts。
- 補 State Snapshot Contract。
- 補 Tool Call Contract。
- 補 Verification Result Contract。
- 補 Scoring Contract。
- 更新 backend / agent 重構順序，加入四個 contract schema 的第一版定義。

### 影響範圍

- agent target design
- State Manager / Verification Layer
- thesis tool-call scoring
- 後續 Command API schema 設計

### 驗證

- `poetry run mkdocs build --strict` 通過。
- `git diff --check -- docs/target/agent.md docs/records/implementation_log.md docs/records/worklog.md` 通過。
- contract wording scan 確認 State Snapshot、Tool Call、Verification Result、Scoring 四個 contract 已寫入。

## 2026-05-01 Command gate 與多資源 workflow 校準

### 背景

使用者指出 `available_commands` 不應只是把所有 tool 和可選 tool 丟給 agent，讓 agent 自己決定。更合理的是 backend / Application Service 根據目前狀態產生 capability policy。使用者也指出 workflow 不能假設成單一路徑：第一筆資料 train 完後，可能同時看 visualization / saliency，或開始下一筆資料的 training。

### 變更

- 更新 `docs/target/agent.md`：
  - `available_commands` 改成 backend capability policy 的輸出。
  - State Snapshot 補 `capability_policy`、`active_jobs`、`completed_runs`。
  - 補 workflow state 不應是單一路徑，而應以 resources / jobs / results 為核心。
  - Tool Call / Verification / Scoring contract 補 target resource 與 policy source。
- 更新 `docs/target/architecture.md`：
  - Command API 需提供 backend-controlled capability policy。
  - 目標 workflow 需支援多資源 / 多任務狀態。
- 更新 `docs/architecture/agent.md`：
  - 標明目前 stage gate 是現況限制，不足以描述多 run / visualization / 下一筆 training 並行情境。

### 影響範圍

- target agent state model
- Application Service / Command API target
- tool availability / verification 設計
- 後續多資料、多 run、visualization / saliency workflow

### 驗證

- `poetry run mkdocs build --strict` 通過。
- `git diff --check -- docs/target/agent.md docs/target/architecture.md docs/architecture/agent.md docs/records/implementation_log.md docs/records/worklog.md` 通過。
- capability wording scan 確認 capability policy、active jobs、completed runs、target resource、policy source、多資源 / 多任務狀態已寫入。

## 2026-05-01 多資源不等於任意並行

### 背景

前一版文字容易讓人誤解成支援多資源 / 多任務後，每個 tool 都可以並行。使用者指出 load data 前不能 run train，command 仍必須受前置條件控制。

### 變更

- 更新 `docs/target/agent.md`，補 dependency gate：
  - 沒 loaded data 不能 preprocess。
  - 沒 label / event 對齊，不能產生可信 dataset。
  - 沒 dataset 不能 training。
  - 沒 trained result 不能 saliency / model-based visualization。
  - long-running job 寫入某 resource 時，不能同時對同一 resource 做破壞性操作。
- 更新 `docs/target/architecture.md` 和 `docs/architecture/agent.md`，明確區分多資源共存與任意並行。

### 影響範圍

- capability policy
- target state model
- command dependency gate
- agent verification rule

### 驗證

- `poetry run mkdocs build --strict` 通過。
- `git diff --check -- docs/target/agent.md docs/target/architecture.md docs/architecture/agent.md docs/records/implementation_log.md docs/records/worklog.md` 通過。
- dependency wording scan 確認沒有 loaded data / dataset / trained result 時的禁止條件已寫入。

## 2026-05-01 Active dataset pipeline 邊界校準

### 背景

前一版文字仍可能被理解成 XBrainLab 目標要同時開多個 dataset。使用者指出一次只能開一個 dataset，epoch 後不該讓 agent 開新的資料集。

### 變更

- 更新 `docs/target/agent.md`：
  - State Snapshot 改成一個 active dataset pipeline。
  - 多資源說法改成同一 dataset 上的多個 training run / evaluation / visualization result。
  - epoch / dataset 形成後，`load_data` / 開新 dataset 不應是一般 available command。
  - 若要載入新資料，必須走 reset / new session / fork 類高風險 command，且需要使用者確認。
- 更新 `docs/target/architecture.md` 和 `docs/architecture/agent.md`，同步 active dataset pipeline 邊界。

### 影響範圍

- state model
- capability policy
- load data / generate dataset command gate
- reset / new session / fork 邊界

### 驗證

- `poetry run mkdocs build --strict` 通過。
- `git diff --check -- docs/target/agent.md docs/target/architecture.md docs/architecture/agent.md docs/records/implementation_log.md docs/records/worklog.md` 通過。
- active dataset wording scan 確認一個 active dataset pipeline、epoch / dataset 後阻擋一般 load new data、reset / new session / fork 高風險邊界已寫入。

## 2026-05-01 blocked commands 定位

### 背景

使用者詢問 `blocked_commands` 是否需要。結論是保留，但不應完整餵給 LLM。它主要用於 verifier、scorer、debug 和 UI 診斷；Context Assembler 只在與當前 user intent 相關時摘要 blocked reason。

### 變更

- 更新 `docs/target/agent.md`：
  - `blocked_commands` 定位為 Verification Layer、scorer、debug、UI diagnostics 使用。
  - 明確寫出完整 blocked list 不應直接塞進 LLM prompt。
  - Context Assembler 只摘要和當前 user intent 相關的 blocked reason。

### 影響範圍

- State Snapshot Contract
- Context Assembler
- Verification Layer
- Scoring / debug report

### 驗證

- `poetry run mkdocs build --strict` 通過。
- `git diff --check -- docs/target/agent.md docs/records/implementation_log.md docs/records/worklog.md` 通過。
- blocked command wording scan 確認完整 blocked list 不直接塞給 LLM、只摘要相關 blocked reason 的邊界已寫入。

## 2026-05-01 .agents skills / workflows 第一版

### 背景

使用者指出目前 `.agents` 設計仍不滿意，缺少 skill / workflow。現有 `.agents` 主要是 runbooks 和 context，還不像可重用 agent operating layer。

### 變更

- 新增 `.agents/skills/README.md`。
- 新增五個 repo-local skills：
  - `docs-curator`
  - `architecture-reviewer`
  - `validation-runner`
  - `refactor-slicer`
  - `agent-toolcall-designer`
- 新增 `.agents/workflows/README.md`。
- 新增四個 workflows：
  - `documentation-review.md`
  - `architecture-review.md`
  - `refactor-slice.md`
  - `agent-toolcall-scoring.md`
- 更新 `.agents/README.md`、`.agents/stack.md`、setup / autopilot / active queue。

### 影響範圍

- agent 操作入口
- reusable skills
- multi-step workflows
- 後續架構複盤與重構開工流程

### 驗證

- `poetry run mkdocs build --strict` 通過。
- `git diff --check -- .agents docs/records/implementation_log.md docs/records/worklog.md` 通過。
- agent skill/workflow scan 確認 TDD、test-quality、code-review、software-design skills，以及 `tdd-change` / `test-audit` workflows 已寫入。
- context scan 確認 `.agents/context/*` 已標示為導讀，不保存 current / target / architecture 的第二份 truth。

## 2026-05-01 .agents 工程 workflow skill pack 校準

### 背景

使用者補充希望 skills 參考 TDD、軟體設計、測試品質等已被實際使用過的 workflow，而不是只由本專案即興發明。使用者也指出 context 可能和 architecture 產生多個 truth。

### 變更

- 新增工程 workflow skills：
  - `tdd-guard`
  - `test-quality-reviewer`
  - `code-reviewer`
  - `software-design-reviewer`
- 新增 workflows：
  - `tdd-change.md`
  - `test-audit.md`
- 更新 `refactor-slice.md` 和 `architecture-review.md`，串接新的工程 skills。
- 更新 `.agents/skills/README.md`，標出 skills 參考 OpenAI / Codex skill-creator、GitHub Copilot best practices、Claude Code workflows / best practices 與社群 TDD 經驗。
- 將 `.agents/context/*` 降級成導讀，不保存完整 architecture truth。

### 影響範圍

- repo-local skills
- repo-local workflows
- context source-of-truth 邊界
- 後續 TDD / refactor / test audit 工作流

### 驗證

- 待本輪 final validation 補記。

## 2026-05-01 Workspace 搬遷與文件可信度稽核

### 背景

XBrainLab 原本位於 `/mnt/d/repos/XBrainLab`。為了納入目前的 `workspace_v2/projects` 結構，將 active repo 搬到：

- `/mnt/d/workspace_v2/projects/lab/XBrainLab`

### 變更

- 使用 `rsync` 完整複製 repo 到新 workspace。
- 舊路徑因 Windows 拒絕 rename / move，所以保留為備援副本。
- 新增 repo 內文件可信度稽核：
  - `docs/records/documentation_audit.md`
- 開始建立新的 canonical docs 架構。

### 影響範圍

- workspace path
- documentation entry points
- quality dashboard path assumptions
- Poetry virtualenv selection

### 驗證

- `git rev-parse --show-toplevel` 顯示新 active path。
- branch 保持 `codex/stabilization-autopilot`。
- remote 保持 `https://github.com/hxin-an/XBrainLab.git`。
- `rsync --dry-run` 沒列出新舊差異。
- `poetry check` exit 0，但有 metadata deprecation warnings。
- `poetry install --with dev,test,docs` 已在新 workspace env 完成。
- import probe 已通過 `PIL`、`mne`、`PyQt6`、`torch`、`pytest`、`XBrainLab`。
- `poetry run mkdocs build --strict` 通過。

### 剩餘風險

- 舊文件裡仍有大量舊絕對路徑；後續已把 `docs/legacy/` 從 repo 閱讀面移除。
- optional `llm` dependency group 尚未納入這輪標準驗證，`torchinfo` 仍未安裝。
- 舊文件中仍有大量 `/mnt/d/repos/XBrainLab` 絕對路徑。

## 2026-05-01 Runtime 驗證與 UI test 修正

### 背景

搬到新 workspace 後，需要重新建立今天的 runtime evidence。第一次 dashboard refresh 顯示兩個 UI unit failure 和一個 UI baseline reference mismatch。

### 變更

- 修正 `tests/unit/ui/test_model_summary.py`：
  - 用 fake `torchinfo` module 測 lazy optional dependency 行為。
  - 避免標準 `dev,test` 環境被 optional `llm` dependency group 綁住。
- 修正 `tests/unit/ui/test_ui_misc.py`：
  - 將 `AgentManager.set_model("Gemini")` 的 expectation 改成 runtime mode key `gemini`。
  - 這和 `LLMConfig.normalize_backend_mode()`、`ChatPanel._set_model()` 目前行為一致。

### 影響範圍

- UI unit tests
- agent manager model mode normalization
- quality dashboard evidence
- active 文件狀態

### 驗證

- targeted UI tests：
  - `2 passed`
- fast quality dashboard：
  - generated at `2026-05-01 19:16:09 UTC+08:00`
  - workspace `/mnt/d/workspace_v2/projects/lab/XBrainLab`
  - Ruff Lint `PASS`
  - Basedpyright `PASS`
  - Architecture Compliance `PASS`
  - Startup Smoke `PASS`
  - UI Dialog Acceptance `PASS`
  - UI Unit Suite `PASS` (`799 passed`)
  - Real-Data IO Integration `PASS` (`31 passed`)
- docs build：
  - `poetry run mkdocs build --strict` 通過。

### 剩餘風險

- `llm` optional group 沒納入這輪，因此不要把 local LLM / transformer / `torchinfo` runtime 說成已驗證。

## 2026-05-01 UI baseline 決策與 clean dashboard

### 背景

fast dashboard 第二次刷新後只剩 `ai-assistant-open.png` baseline mismatch。live artifact 和 repo HEAD reference 都是 `(1428, 800)`，但 dirty worktree reference 是 `(1523, 800)`。

### 變更

- 接受 `(1428, 800)` 作為 `tests/baselines/ui/ai-assistant-open.png` 的 approved baseline。
- 重新刷新 fast quality dashboard。
- 將 clean dashboard 判定規則寫入 `validation/README.md`。

### 影響範圍

- UI baseline reference
- quality dashboard artifact
- active validation 文件

### 驗證

- fast quality dashboard：
  - generated at `2026-05-01 19:28:48 UTC+08:00`
  - overall `PASS`
  - 所有 checks 都是 `pass`
  - UI Baseline Capture `PASS`
  - UI Unit Suite `PASS` (`799 passed`)
  - Real-Data IO Integration `PASS` (`31 passed`)

### 剩餘風險

- clean dashboard 仍只是 fast engineering health gate。
- optional `llm` group、local LLM runtime、完整 thesis validation 尚未完成。

## 2026-05-01 Roadmap 與 pipeline validation 分層

### 背景

fast dashboard clean 後，下一個問題是完整 pipeline 是否可信，以及路線規劃要放在哪裡才不會讓文件膨脹。

### 變更

- 新增 `docs/planning/roadmap.md`。
- 在 `validation/README.md` 補上 pipeline validation 分層：
  - fast dashboard
  - tiny E2E pipeline smoke
  - public fixture pipeline smoke
  - scientific validation
- 對齊 `/mnt/d/workspace_v2/core/lab/meetings/progress/reports/2026-04-26.md` 的 To Do List：
  - GUI 重構
  - 建立新 Agent 架構
  - 後端重構
  - 穩定化
  - tool call 驗證
  - 優化迭代
- 在 `records/worklog.md` 補上 pipeline smoke 抽樣紀錄。

### 影響範圍

- active 文件入口
- MkDocs nav
- validation evidence taxonomy

### 驗證

- targeted pipeline smoke：
  - `tests/integration/pipeline/test_full_pipeline.py::TestFullPipeline::test_train_and_evaluate_metrics`
  - `tests/integration/pipeline/test_study_training_e2e.py::TestStudyTrainCycle::test_full_cycle_eegnet`
  - 結果：`2 passed in 7.54s`

### 剩餘風險

- tiny pipeline smoke 目前還沒有納入 fast dashboard。
- public cross-source training smoke 和 scientific reproducibility 還沒在本輪驗證。
- repo legacy status 仍可作輔助脈絡，但 active roadmap 以 2026-04-26 會議進度報告為主要來源。

## 2026-05-01 Agent 架構文件與 local-only runtime 決策

### 背景

agent 文件原本只描述高層方向，沒有清楚說明目前 UI、controller、worker、tool、backend 之間的實際接線。整理時也確認新的產品方向要簡化為 local-only assistant，不再把 API / Gemini 當成未來目標。

### 變更

- 重寫 `docs/architecture/agent.md`：
  - 記錄目前實際路徑是 UI -> AgentManager -> LLMController -> Worker / Parser / Verifier / Tools -> BackendFacade -> Study。
  - 標記目前是可工作的中間狀態，不是最終架構。
  - 將未來目標改成 local-only runtime + shared Application Service / Command API。
- 更新 `docs/decisions/README.md`：
  - 新增 `assistant runtime local-only`。
- 更新 `docs/validation/README.md`：
  - agent runtime 後續只驗證 local model、optional `llm` group、GPU/CPU fallback、local tool-call output。
- 對齊兩個 agent unit test：
  - `LLMController.set_model("Gemini")` 目前會 normalize 成 `gemini`。
  - `AgentWorker.generate_from_messages()` 的 thread 啟動測試明確 mock local backend ready，避免被本機 optional `llm` dependency 缺失影響。

### 影響範圍

- agent architecture 文件
- active decisions
- validation strategy
- agent unit tests

### 驗證

- docs build：
  - `poetry run mkdocs build --strict` 通過。
- targeted agent tests：
  - `poetry run pytest --capture=sys tests/unit/llm/test_pipeline_state.py tests/unit/llm/agent/test_controller.py tests/unit/llm/agent/test_worker.py tests/unit/llm/tools/real/test_real_tools.py tests/unit/ui/components/test_agent_manager.py tests/unit/ui/chat/test_chat_panel.py -q`
  - 結果：`157 passed in 7.61s`

### 剩餘風險

- 程式碼目前仍保留 API / Gemini runtime，尚未移除。
- optional `llm` group、本地模型 cache、GPU readiness 尚未完成 runtime 驗證。
- RAG 品質和真實多步 tool-call workflow 尚未驗證。

## 2026-05-01 Active / Architecture 文件校準

### 背景

使用者希望先把文件整理完，再 review，接著清 legacy 文件；後端與 agent 實作先不開工。

### 變更

- 重寫 / 校準 active 入口：
  - `docs/current.md`
  - `docs/operations.md`
- 校準 architecture 入口與剩餘架構文件：
  - `docs/architecture/README.md`
  - `docs/architecture/ui.md`
  - `docs/architecture/validation.md`
- 更新總入口與可信度稽核：
  - `docs/index.md`
  - `docs/planning/roadmap.md`
  - `docs/records/documentation_audit.md`

### 影響範圍

- 文件閱讀順序
- 操作指令入口
- UI 架構說明
- validation architecture
- legacy cleanup 前的 canonical 文件基準

### 驗證

- 各 sub-agent 分別跑過 `poetry run mkdocs build --strict`。
- 主流程最後再跑一次總 `poetry run mkdocs build --strict`，結果通過。
- `git diff --check` 針對本輪文件變更通過。

### 剩餘風險

- legacy 文件尚未清理。
- `ui.md` 已對照主要 UI wiring，但尚未逐一審所有 dialog。
- 後端重構還沒開始；目前文件只描述現況與目標。

## 2026-05-01 Docs / agent legacy 刪除與 test mock 邊界

### 背景

使用者確認 legacy cleanup 的目標不是永久保留短期快照，而是把有用內容整合到目前文件系統後刪除。多數 legacy 文件只是近兩天 AI / agent 工作產物，不應繼續污染閱讀面。

同時，使用者追問 test 是否 mock 太多、能不能真的測到問題。

### 變更

- 刪除 `docs/legacy/current/`、`decisions/`、`workflows/`、`guides/`、`api/`、`thesis/`、`history/`。
- 從 MkDocs nav 移除 deleted legacy sections。
- 更新 `docs/legacy/README.md`，改成「整合後刪除」策略。
- 更新 active audit，將非 archive legacy 標記為 `deleted-after-integration`。
- 刪除 `.agents/legacy/` 舊 role、skill、AQ queue、workflow、multi-session prompt。
- 更新 `AGENTS.md`、`.agents/stack.md`、`.agents/runbooks/*`，讓 agent 入口不再指向 `.agents/legacy/`。
- 在 `validation/README.md` 和 `validation.md` 補上 mock-heavy test 邊界。

### 影響範圍

- legacy 文件結構
- agent 操作層
- MkDocs nav
- validation 文件
- 文件可信度 audit

### 驗證

- `poetry run mkdocs build --strict` 通過。

### 剩餘風險

- mock-heavy tests 仍是現況；文件已標出邊界，但測試結構尚未改。

## 2026-05-01 Docs legacy archive 收掉

### 背景

使用者決定連 `docs/legacy/archive/` 也不要留在目前文件站，避免新文件和舊設計混在一起。

### 變更

- 刪除整個 `docs/legacy/`。
- 從 `mkdocs.yml` 移除 Legacy nav。
- 更新 `README.md`、`AGENTS.md`、`.agents/stack.md`、canonical docs、architecture 入口和 audit。

### 影響範圍

- 文件站 navigation
- repo 文件入口
- agent reading order
- 文件可信度 audit

### 驗證

- `poetry run mkdocs build --strict` 通過。
- `git diff --check -- AGENTS.md .agents README.md docs mkdocs.yml` 通過。
- stale link scan 沒有 active nav / markdown link 指回 `docs/legacy/`。

### 剩餘風險

- mock-heavy tests 仍是現況；文件已標出邊界，但測試結構尚未改。

## 2026-05-01 Active folder 收掉

### 背景

使用者決定 `docs/active/` 這一層也不需要保留。canonical 文件直接放在 `docs/` 根層，避免文件入口被資料夾層級切得太碎。

### 變更

- 將 `current.md`、`planning/roadmap.md`、`validation/README.md`、`operations.md`、`decisions/README.md`、`records/documentation_audit.md`、`records/implementation_log.md`、`records/worklog.md` 從 `docs/active/` 移到 `docs/`。
- 刪除 `docs/active/README.md`。
- 更新 `mkdocs.yml`，將 nav 從 Active 改成 Core。
- 更新 `README.md`、`AGENTS.md`、`.agents/*`、`docs/index.md`、architecture 文件中的路徑。

### 影響範圍

- 文件站 navigation
- repo 文件入口
- agent reading order
- thesis context links

### 驗證

- `poetry run mkdocs build --strict` 通過。
- `git diff --check -- AGENTS.md .agents README.md docs mkdocs.yml` 通過。
- `test ! -e docs/active`、`test ! -e docs/legacy`、`test ! -e .agents/legacy` 通過。
- stale path scan 沒有 active markdown link 指向已刪除資料夾。

## 2026-05-01 Root homepage 文件收斂

### 背景

root README 仍列出 root `ROADMAP.md` 和 `CHANGELOG.md`，但 root `ROADMAP.md` 是舊 Track A/B 大計畫，和現在的 `docs/planning/roadmap.md` 衝突。

### 變更

- 刪除 root `ROADMAP.md`。
- 更新 `README.md`，改指向 `docs/planning/roadmap.md`。
- 更新 `CHANGELOG.md` 開頭，標明它只保留歷史版本紀錄，現況、路線、接手後工程紀錄以 `docs/*` canonical 文件為準。
- 更新 `records/documentation_audit.md` 和 `current.md`。

### 影響範圍

- GitHub root homepage
- roadmap source-of-truth
- historical changelog framing

### 驗證

- `test ! -e ROADMAP.md` 通過。
- `poetry run mkdocs build --strict` 通過。
- `git diff --check -- README.md CHANGELOG.md planning/roadmap.md AGENTS.md .agents docs mkdocs.yml` 通過。

## 2026-05-01 文件資訊架構第一版

### 背景

使用者指出文件仍然擠在同一層，短期、長期、決策、紀錄、需求與理想架構混在一起。需要重新建立文件資訊架構，並補 `.agents` 的操作文件。

### 變更

- 將 docs 重排為：
  - `current.md`
  - `operations.md`
  - `target/`
  - `architecture/`
  - `planning/`
  - `decisions/`
  - `validation/`
  - `records/`
- 新增 `docs/target/README.md`、`requirements.md`、`architecture.md`、`agent.md`。
- 新增 `docs/planning/now.md`，並將 roadmap 移到 `docs/planning/roadmap.md`。
- 將 decisions、validation、implementation log、worklog、documentation audit 移入對應資料夾。
- 將 `architecture/validation_architecture.md` 改名為 `architecture/validation.md`。
- 新增 `.agents/README.md`、`.agents/context/project.md`、`.agents/context/architecture-target.md`。
- 新增 `.agents/runbooks/architecture-review.md`、`.agents/runbooks/refactor-gate.md`。
- 更新 `README.md`、`AGENTS.md`、`.agents/*`、`mkdocs.yml` 和文件連結。

### 影響範圍

- 文件站 navigation
- 文件 source-of-truth
- agent reading order
- 後續架構複盤流程

### 驗證

- `poetry run mkdocs build --strict` 通過。
- `git diff --check -- README.md CHANGELOG.md AGENTS.md .agents docs mkdocs.yml` 通過。
- stale path scan 沒有 active markdown link 指向舊大寫 canonical 檔名、`docs/active/`、`docs/legacy/` 或 `validation_architecture.md`。

## 2026-05-02 Product delivery stabilization slice

### 背景

使用者要求把 partial assistant fix 往可直接使用的桌面產品收斂。人工驗收指出 AI
Assistant 仍像 developer/debug dock，raw command names 污染主 UI，user bubble 會吃掉
最後一個字，且缺少真正從 UI button path 走 pipeline 的 product E2E evidence。

### 變更

- Assistant product UI：
  - 新增 `XBrainLab/ui/product_language.py`，集中 stage、command、runtime、mode 的使用者語言。
  - ChatPanel header 改成 `XBrainLab Assistant` + workflow guidance + compact readable badges。
  - Retry / Clear / Stop / Settings 從說明文字旁拆成 controls。
  - `Coder / Local / Multi` 重新表達為 `Workflow guide`、`Local model`、`Single step`、`Auto steps`。
  - 第一層 UI 移除 `load_data`、`configure_training`、`reset_session` 這類 raw command name；
    raw diagnostics 只放 tooltip / advanced details。
  - 修正 message bubble padding、max width、right margin、word wrap，避免 user bubble 截字。
- Backend / UI alignment：
  - `XBrainLab/ui/application_capabilities.py` 新增 `execute_application_command(...)`。
  - Dataset import 走 `LoadDataCommand`。
  - Dataset reset / clear 走 `ResetSessionCommand(confirmed=True)`。
  - Preprocess filter / resample / rereference / normalize 走 `PreprocessCommand`。
  - Epoching 走 `CreateEpochCommand`。
  - Training start / stop 走 `TrainCommand` / `StopTrainingCommand`。
  - mock / incomplete `Study` 保留 controller fallback，避免測試假物件誤觸 service contract。
- Agent alignment：
  - `XBrainLab/llm/tools/application_surface.py` 新增 direct command execution helper。
  - `LLMController._execute_tool_no_loop()` 先嘗試 mapped ApplicationService command，再 fallback real tool。
  - `attach_labels`、preprocess tools、`epoch_data`、`generate_dataset`、`set_model`、
    `configure_training`、`start_training`、`clear_dataset` 可直接回 structured
    `ToolCommandResult.from_command_result(...)`。
  - `load_data` 仍保留 directory expansion / safety legacy path；`set_montage`、`switch_panel`
    仍保留 UI request path。
- Product validation：
  - 新增 `tests/integration/ui/test_product_walkthrough.py`。
  - `test_assistant_product_click_through_layout` 覆蓋 assistant header/status/control row、
    command diagnostics、message bubble、composer、panel navigation。
  - `test_pipeline_product_walkthrough_uses_user_facing_actions` 用 synthetic FIF 走 Dataset import
    button、Preprocess filter、epoching、Training split/model/settings、dry-run Start Training、
    Evaluation result-ready 狀態。
- Docs：
  - 更新 current、planning、backend/ui/agent/validation architecture、validation README、
    worklog、implementation log，區分已完成 baseline、service-first migration 完成範圍和剩餘風險。

### 驗證

- Assistant UI product slice：
  - `timeout 240s scripts/dev/run_ui_pytest.sh tests/unit/ui/chat/test_chat_panel.py tests/unit/ui/chat/test_message_bubble.py tests/unit/ui/components/test_agent_manager.py tests/unit/ui/test_agent_manager_coverage.py -q`
  - `78 passed`
- UI command adapter / backend slice：
  - `timeout 240s scripts/dev/run_ui_pytest.sh tests/unit/ui/test_application_capabilities.py tests/unit/ui/dataset/test_panel.py tests/unit/ui/dataset/test_dataset_sidebar.py tests/unit/ui/preprocess/test_preprocess_panel.py tests/unit/ui/preprocess/test_preprocess_panel_normalize.py tests/unit/ui/training/test_training_sidebar.py tests/unit/ui/test_sidebars_and_components.py -q`
  - `74 passed`
  - `timeout 180s poetry run pytest --capture=sys tests/unit/backend/application tests/integration/backend/test_application_service_workflow.py -q`
  - `11 passed`
- Agent command result slice:
  - `timeout 180s poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/unit/llm/agent/test_controller.py -q`
  - `60 passed`
- Product walkthrough:
  - `timeout 240s scripts/dev/run_ui_pytest.sh tests/integration/ui/test_product_walkthrough.py -q`
  - `2 passed`
- Combined gates after implementation:
  - UI product gate: `62 passed`
  - agent / backend gate: `95 passed`
  - IO integration: `31 passed, 8 warnings`
  - selected pipeline smoke: `2 passed`
  - launcher startup smoke: `MainWindow initialized` appeared before expected GUI timeout.

### 剩餘風險

- UI service-first migration 尚未覆蓋 label import、smart parse、channel selection、split /
  model / training setting dialog submit、evaluation / visualization query actions。
- Agent `load_data`、`set_montage`、`switch_panel` 仍有 legacy / UI request semantics。
- `evaluate` / `visualize` / `saliency` / `new_session` 仍是 disabled future command contract。
- 真 Windows launcher click-through 和 true local model UI walkthrough 尚未人工驗收。
- deterministic tool-call eval 不是 local LLM 真實 performance claim。

## 2026-05-03 Backend Workflow Contract v2 first slice

### 背景

Backend 已有 `ApplicationService` command spine，但 reset / cleanup / eval / visualization /
saliency / split audit 仍有 service bypass 或過寬 policy。這個切片目標是先消除高風險
mutating/lifecycle bypass，並讓 thesis evidence path 不會把 invalid split 當成功。

### 變更

- Command contract：
  - 新增 `ClearDatasetsCommand`、`ClearTrainingHistoryCommand`、`ResetPreprocessCommand`。
  - 更新 command export、handler routing、capability policy、confirmation gate 和
    `BackendFacade` wrapper compatibility。
- Dataset audit：
  - `GenerateDatasetCommand` 會執行 split audit，回傳 `split_audit`、`protocol`、
    `rolled_back` 等 structured diagnostics。
  - empty train/validation/test 或 leakage 會變成 `DATA_MISMATCH` command failure。
  - audit failure 會 rollback dataset / generator / trainer state，避免 failure 後仍可 train。
  - custom UI generator 會從 `test_splitter_list` 推斷 audit protocol，避免 trial split
    被 default subject-wise audit 誤擋。
- Query/readiness：
  - `evaluate`、`visualize`、`saliency` 不再於 empty state 無條件 available。
  - blocked query / lifecycle commands 仍回 `CommandResult` envelope。
  - `saliency` 回傳 `action=configure/query`；configure 可先保存參數，但 saliency view
    readiness 仍依 finished evaluation + configured params。

### 驗證

- `poetry run ruff check XBrainLab tests`
  - pass
- `poetry run basedpyright XBrainLab/backend/application XBrainLab/backend/facade.py`
  - `0 errors, 0 warnings, 0 notes`
- `poetry run pytest tests/unit/backend/application/test_application_service.py tests/integration/backend/test_application_service_workflow.py tests/integration/ui/test_product_walkthrough.py tests/integration/pipeline/test_public_cross_source_training_smoke.py`
  - `32 passed, 3 warnings`
- `poetry run pytest tests/unit/backend/application tests/integration/backend tests/integration/pipeline`
  - `95 passed, 4 warnings`
- `poetry run basedpyright`
  - `0 errors, 0 warnings, 0 notes`

### 剩餘風險

- 這是 Backend Workflow Contract v2 + Evidence-Ready Pipeline 的第一個可交付切片，不是終局。
- UI service-first migration 還有剩餘 bypass；本切片沒有完成整個 UI service-first migration。
- thesis evidence 還需要 external dataset runner、repeat/baseline/statistics 和 artifact emission policy。

## 2026-05-03 Assistant UI single-toolbar product correction

### 背景

人工驗收指出上一輪 Assistant UI 仍不夠像使用者產品：chat panel 內還有 `Conversation`
標題、composer 底下狀態列、兩組功能列、未設計完成的 `Assistant mode` / `Step behavior`
選項，以及過大的短訊息 bubble。

### 變更

- ChatPanel 內移除可見 header、第二條 status footer、developer mode controls 和第二個
  options menu；對話區第一視覺回到 empty state / transcript。
- Dock title bar 成為唯一第一層功能列：`XBrainLab`、retry icon、new conversation、
  settings menu、float/dock。`Clear conversation` 收進 settings menu。
- Retry 沒有上一則 request 時 disabled；有上一則 request 時只在 title bar 單一位置啟用。
- tool/debug output 由 `AgentManager` 攔截並轉成 notice，不再把 `Tool list_files completed...`
  或 schema/internal class name 放進 visible transcript。
- user / assistant short message bubble 降低 minimum width，避免 `hello` 形成過大的框，同時
  保留窄 dock 可讀文字欄。

### 驗證

- `poetry run ruff check XBrainLab/ui/chat XBrainLab/ui/components/agent_manager.py tests/unit/ui/chat tests/integration/ui/test_product_walkthrough.py`
  - pass
- `poetry run pytest --capture=sys tests/unit/ui/chat tests/integration/ui/test_product_walkthrough.py -q`
  - `50 passed`
- combined assistant UI + backend workflow contract gate：
  - `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`
  - `poetry run pytest --capture=sys tests/unit/ui/chat tests/integration/ui/test_product_walkthrough.py tests/unit/backend/application/test_application_service.py tests/integration/backend/test_application_service_workflow.py tests/unit/backend/test_facade_headless.py tests/integration/pipeline/test_public_cross_source_training_smoke.py -q` -> `80 passed, 3 warnings`
