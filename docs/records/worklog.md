# XBrainLab Worklog

最後更新：`2026-05-03`

## 這份文件的用途

這是流水帳式工作紀錄，用來保留「當天實際做過什麼」。

它和其他文件的分工如下：

| 文件 | 角色 |
| --- | --- |
| `current.md` | 現在真相。只寫目前狀態、blocker、下一步。 |
| `records/implementation_log.md` | 專業交接紀錄。只收重要變更、原因、影響、驗證。 |
| `records/worklog.md` | 流水帳。記錄嘗試、驗證、踩坑、臨時判斷和未整理細節。 |

`records/worklog.md` 可以比較細，但不應該取代 current state 或 architecture。

## 記錄規則

- 新紀錄插在該日期區塊最上方，最新在上。
- 每筆只寫一件事。
- 寫清楚結果，不只寫動作。
- 失敗嘗試也要記，因為它們常常是後面判斷可信度的關鍵。
- 每隔一段時間，把真正重要的內容整理進 `records/implementation_log.md`，不要讓 worklog 變成唯一真相來源。

## Entry 格式

```md
### HH:MM 主題

- 做了什麼：
- 結果：
- 證據：
- 接續 / 本輪剩餘：
```

## 2026-05-03

### 00:40 Supervisor rule / window fallback / backend hardening review

- 做了什麼：
  - 將 repo agent 入口補上 supervisor model：worker 回報完成不算完成，主 agent 必須自己讀 diff、
    看 artifact、跑 tests、比對 current docs，仍有 blocker 就打回。
  - 發包 UI/window worker 修正 Windows/WSLg offset dual-monitor 開窗回歸；first launch、
    壞 saved geometry、post-show recovery 改成 maximized fallback，不使用 fullscreen。
  - 發包 backend worker 補 dataset generation apply/audit rollback boundary，並把
    `evaluate` / `clear_training_history` capability 改成看 actual training plan history。
  - 發包 QA explorer 只讀審核 tests 是否真的支撐 product delivery。
- 結果：
  - UI/window slice 的 regression tests 覆蓋使用者回報 geometry：
    `screen[0] x=0 y=362`、`screen[1] x=1920 y=0`、cursor `(0,0)` 在 virtual gap。
  - Backend slice 避免 split apply 例外或 split audit blocker 留下半成功 datasets /
    generator / trainer。
  - QA 審核確認仍不能宣稱完整產品完成：真 Windows launcher click-through、true local model
    UI walkthrough、real UI button-click 到 training/eval/viz completion 仍未完成。
  - 我自己的驗證中曾把 Markdown 檔誤丟給 `ruff`，該失敗是驗證命令錯誤，不是程式碼失敗；
    已改用只含 Python 檔的 ruff gate。
- 證據：
  - `git diff --check` PASS
  - `poetry run ruff check XBrainLab/ui/main_window.py XBrainLab/backend/application/capabilities.py XBrainLab/backend/application/service.py XBrainLab/backend/facade.py tests/integration/ui/test_window_geometry.py tests/unit/ui/test_window_placement.py tests/unit/backend/application/test_application_service.py tests/unit/backend/test_facade_headless.py`
    - `All checks passed!`
  - `poetry run pytest --capture=sys tests/unit/ui/test_window_placement.py tests/integration/ui/test_window_geometry.py tests/unit/test_run_splash_geometry.py -q`
    - `22 passed`
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py tests/integration/backend/test_application_service_workflow.py tests/unit/backend/test_facade_headless.py tests/unit/backend/test_facade_coverage.py tests/unit/llm/tools/test_application_surface.py -q`
    - `80 passed`
  - `poetry run pytest --capture=sys tests/unit/ui/chat/test_message_bubble.py tests/unit/ui/chat/test_chat_panel.py tests/integration/ui/test_product_walkthrough.py::test_assistant_product_click_through_layout -q`
    - `48 passed`
  - `poetry run basedpyright`
    - `0 errors, 0 warnings, 0 notes`
  - `poetry run mkdocs build --strict`
    - PASS
- 接續 / 本輪剩餘：
  - 使用者仍需在真 Windows/WSLg 雙螢幕上 click-through 確認 launcher / splash / main window。
  - 要補真 UI E2E：button click 到 real training completion、evaluation record、visualization/saliency。
  - 不可把 synthetic product walkthrough 或 deterministic eval 當完整 release evidence。

## 2026-05-02

### 22:44 Launcher visible logs / geometry diagnostics

- 做了什麼：
  - 重新讀取 repo launcher、PowerShell launcher、Desktop `XBrainLab.cmd`、`run.py`、
    `MainWindow` placement path 和既有 geometry tests。
  - 確認 Desktop `XBrainLab.cmd` 指向 `/mnt/d/workspace_v2/projects/lab/XBrainLab`，
    Desktop 上也沒有其他 XBrainLab shortcut / generated app；目前不像是跑舊 repo。
  - `.cmd` 改為 bootstrap active repo 的 PowerShell launcher，避免 Desktop command 變成
    stale generated app；terminal 會先顯示 active WSL repo、Windows repo、PowerShell launcher path。
  - `.ps1` launcher 改成 visible preamble + live tee：log path、開 log / tail log 指令、
    WSL / Python stdout/stderr 都同時出現在 terminal 和
    `%LOCALAPPDATA%\XBrainLab\logs\launcher-*.log`。
  - 新增 `XBRAINLAB_STARTUP_DIAGNOSTICS=1` safe diagnostic mode，只有開 env var 才 log
    screens、cursor、splash geometry、MainWindow restore/default placement、show event、
    post-show 0ms / 250ms geometry。
  - `showEvent()` 的 post-show recovery 從單次 `0ms` 補成 `0ms + 250ms`，覆蓋 Windows / WSLg
    show 後才 finalise native frame 或二次移動 window 的 timing。
  - 新增 `XBRAINLAB_LAUNCHER_SMOKE=1` smoke mode，用來驗證 launcher preamble / active repo
    delegation / log 寫入而不真的啟動 GUI。
- 結果：
  - Windows terminal 不應再是一片黑；一開始就會看到 repo、log path、正在啟動、如何看 log。
  - Desktop launcher 目前判斷不是 stale app；它會委派到 active repo 內的 PowerShell launcher。
  - 如果使用者再遇到「正上方」，可用 `XBRAINLAB_STARTUP_DIAGNOSTICS=1` 收到 screens /
    splash / MainWindow after-show / post-show geometry，比只猜 margin 更可定位。
- 證據：
  - `poetry run pytest --capture=sys tests/integration/ui/test_window_geometry.py tests/unit/ui/test_window_placement.py tests/unit/test_run_splash_geometry.py -q`
    - `19 passed`
  - `poetry run ruff check run.py XBrainLab/ui/main_window.py XBrainLab/ui/window_placement.py tests/integration/ui/test_window_geometry.py tests/unit/ui/test_window_placement.py tests/unit/test_run_splash_geometry.py`
    - `All checks passed!`
  - `poetry run basedpyright`
    - `0 errors, 0 warnings, 0 notes`
  - Launcher syntax / smoke：
    - PowerShell parser：`PowerShell syntax OK`
    - repo `.cmd` smoke：active repo bootstrap passed
    - Desktop `.cmd` smoke：active repo bootstrap passed
    - repo `.ps1` smoke：WSL stdout / stderr were mirrored to terminal and launcher log
- 接續 / 本輪剩餘：
  - 仍需要真人雙螢幕 Windows click-through 驗收；這輪補的是 visible diagnostics 和 timing
    recovery，不能完全替代真 window manager 行為。

### 22:14 Dual-monitor startup geometry follow-up

- 做了什麼：
  - 使用者回報第一版 geometry recovery 後仍會貼到最上方，且 loading splash 不在螢幕中央；
    判斷上一版只處理 top-left / offscreen，沒有完整處理 top-edge、native frame、
    dual-monitor startup screen。
  - 新增 `XBrainLab/ui/window_placement.py`，把 startup screen selection、saved geometry
    screen ranking、splash centering、frame-aware geometry health check 抽成可測 helper。
  - `run.py` 的 loading splash 會在 `show()` 前根據 saved geometry / cursor / primary
    選定 startup screen 並置中，並把同一個 screen hint 傳給 MainWindow。
  - MainWindow 對 restored / persisted geometry 改成 frame-aware 判斷：top-edge、
    native frame titlebar 不可達、跨螢幕 frame、尺寸不合理都會 reset / recenter。
  - 預設 window size 改為保留足夠上下視覺空間，避免小螢幕上看起來貼在最上方。
- 結果：
  - 第一版「只處理左上角」的缺口已補；loading splash 和 main window 不再各自選螢幕。
  - 正常 saved geometry 仍會保留；貼上緣 / top-center / top-right 都會視為不健康。
- 證據：
  - `poetry run pytest --capture=sys tests/integration/ui/test_window_geometry.py tests/unit/ui/test_window_placement.py tests/unit/test_run_splash_geometry.py -q`
    - `15 passed`
  - `poetry run ruff check run.py XBrainLab/ui/main_window.py XBrainLab/ui/window_placement.py tests/integration/ui/test_window_geometry.py tests/unit/ui/test_window_placement.py tests/unit/test_run_splash_geometry.py`
    - `All checks passed!`
  - `poetry run basedpyright`
    - `0 errors, 0 warnings, 0 notes`
- 接續 / 本輪剩餘：
  - 仍需要使用者在真雙螢幕 Windows launcher 上人工確認；這是 WSLg / Windows window
    manager 行為，不能只靠 xvfb 宣稱完全通過。

### 21:08 MainWindow saved geometry recovery

- 做了什麼：
  - 針對 Windows launcher 打開後主視窗卡在左上角且不可拖的退件，重看
    `MainWindow._restore_or_place_window()`、post-show clamp、`closeEvent()` geometry
    persistence，以及 Assistant dock custom titlebar。
  - 將 restore 成功和 geometry 可用拆開判斷；貼左上、offscreen、尺寸不合理、
    titlebar 不可達的 saved `main_window/geometry` 會移除並用安全預設位置重置。
  - `closeEvent()` 不再保存明顯不可用的 geometry，避免壞 QSettings 反覆自我保存。
  - 補 Assistant dock titlebar regression，確認空白 titlebar mouse events 會交回
    `QDockWidget` 原生拖曳處理，double-click 仍可 float / dock。
- 結果：
  - 既有壞 `QSettings("XBrainLab", "XBrainLab")["main_window/geometry"]` 不需要使用者手動清除；
    啟動時會 migration reset 到可見、可拖曳 titlebar 的安全位置。
  - 正常 user-resized geometry 仍會保留。
- 證據：
  - `poetry run pytest --capture=sys tests/integration/ui/test_window_geometry.py -q`
    - `6 passed`
  - `poetry run pytest --capture=sys tests/unit/ui/components/test_agent_manager.py tests/integration/ui/test_product_walkthrough.py -q`
    - `32 passed`
  - `poetry run ruff check XBrainLab/ui/main_window.py XBrainLab/ui/components/agent_manager.py tests/integration/ui/test_window_geometry.py`
    - `All checks passed!`
  - `poetry run basedpyright`
    - `0 errors, 0 warnings, 0 notes`
- 接續 / 本輪剩餘：
  - 真 Windows Desktop launcher click-through 仍需人工驗收，但 blocker 的 persisted bad
    geometry path 已有 regression protection。

### 20:35 Final validation closure

- 做了什麼：
  - 收斂最後一輪退件：local-disabled assistant startup 改成 visible reason，
    confirmation transcript 不再暴露 raw tool names，montage apply 改走 command surface，
    `run.py` startup path 維持 local-only，UI baseline geometry 穩定，UI unit legacy runtime
    expectations 改成 remote switch fail-closed / active local deletion block。
  - 刷新 deterministic tool-call eval artifact，tracked `artifacts/agent_evals/latest.json`。
  - 同步 canonical docs，避免 current truth 停在舊 dashboard 或舊 API/Gemini removal wording。
- 結果：
  - latest fast dashboard 從先前 FAIL 修到 clean `PASS`。
  - `artifacts/quality/latest.md` generated at `2026-05-02 20:35:07 UTC+08:00`，
    overall `PASS`。
  - dashboard summary：Ruff PASS，Basedpyright PASS `0 errors, 0 warnings, 0 notes`，
    Architecture PASS，Startup Smoke PASS，UI Baseline PASS，UI Dialog PASS，
    UI Unit Suite `814 passed`，Real-Data IO Integration `31 passed, 8 warnings`。
- 證據：
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
  - local model preflight：primary `microsoft/Phi-4-mini-instruct` already cached，
    current / projected cache `15.34 GB`，available disk `158.54 GB`，
    estimated download `0.00 GB`，VRAM estimate `9.0 GB`，license MIT。
  - relevant commits：
    `8b04380`、`1883d4b`、`8a6099a`、`41ec91c`、`3edee21`、`5ed1c87`、
    `4cd4d4c`、`406719c`、`e5454c7`。
- 接續 / 本輪剩餘：
  - Windows Desktop launcher click-through 尚未人工驗收。
  - true local LLM ChatPanel long walkthrough 尚未跑。
  - external thesis dataset experiment / statistical reporting 尚未完成。

### 19:28 Backend command surface migration closure

- 做了什麼：
  - 擴充 `ApplicationService` command contract：`update_metadata`、`apply_smart_parse`、
    `remove_files`、`import_labels` / `LabelImportPlan`、`apply_montage`、`query_state`。
  - 將 dataset metadata edit / smart parse / remove / label import、InfoPanel read query、
    agent montage confirmation、agent `load_data` command surface 接到 `ApplicationService.execute()`。
  - 補 capability policy：train 在 load 前明確 blocked；epoch / dataset 後 raw edit、
    label / metadata / remove / preprocess / recreate epoch / regenerate dataset 會要求 reset /
    new session。
  - 保留 mock/unit-test fallback；real `Study` path 回 `CommandResult`。
- 結果：
  - 先前列出的 label import、smart parse、remove files、metadata update、montage confirmation
    legacy mutating paths 已收斂到 service command。
  - `BackendFacade` 保留 compatibility wrapper，data summary / preprocess diagnostics 改用
    `QueryStateCommand`。
- 證據：
  - `git diff --check`
  - `poetry run ruff check XBrainLab/backend XBrainLab/llm/tools XBrainLab/ui/panels/dataset XBrainLab/ui/components/info_panel_service.py XBrainLab/ui/components/agent_manager.py tests/unit/backend tests/integration/backend tests/unit/llm/tools`
    - `All checks passed!`
  - `poetry run pytest --capture=sys tests/unit/backend/application tests/integration/backend/test_application_service_workflow.py tests/unit/backend/test_facade_coverage.py tests/unit/backend/test_facade_headless.py tests/unit/llm/tools tests/integration/io/test_io_integration.py -q`
    - `249 passed, 8 warnings`
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/dataset tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler tests/unit/ui/components/test_agent_manager.py tests/unit/ui/test_agent_manager_coverage.py tests/unit/ui/components/test_info_panel_service.py -q`
    - `133 passed`
- 接續 / 本輪剩餘：
  - `set_montage` / `switch_panel` 仍是 UI request path；montage apply 本身已 service-backed。
  - 真 Windows launcher click-through / 真 local model 長時間 walkthrough 仍需人工驗收。

### 19:20 Local-only assistant runtime enforcement

- 做了什麼：
  - 將 `LLMConfig`、`LLMEngine`、`AgentWorker` product path 改成 local-only。
  - 刪除 product package 中的 remote backend modules，model settings 移除 remote key / remote model UI。
  - `pyproject.toml` default deps 移除 remote SDK，保留 optional legacy dependency group。
  - 刪除 Gemini verify/list scripts，legacy benchmark scripts 移除 Gemini model option。
  - 加 architecture compliance guard，掃 product path 禁止 remote backend class / remote key env path。
- 結果：
  - `INFERENCE_MODE=api`、舊 settings 裡的 Gemini mode、`reinitialize_agent("Gemini")`
    都不會 instantiate remote backend。
  - worker/model switching 只接受 local catalog 裡的 Phi primary / fallback 或 generic `Local`。
- 證據：
  - `poetry run pytest --capture=sys tests/unit/llm/core/test_config.py tests/unit/llm/core/test_engine.py tests/unit/llm/agent/test_worker.py tests/unit/ui/dialogs/test_model_settings.py -q`
    - `73 passed`
  - `poetry run pytest --capture=sys tests/unit/llm -q`
    - `644 passed`
- 接續 / 本輪剩餘：
  - 跑使用者指定的完整 ruff / pytest / architecture gates。

### 19:12 Assistant product shell / window geometry rebuild

- 做了什麼：
  - 依退件回饋重做 Assistant 第一層：header 保留 `XBrainLab Assistant` 和低干擾 `...`
    menu；Retry / Clear 收進 menu / compatibility controls，不再佔第一層。
  - empty state 改成 EEG 使用者語言：`Load EEG data to begin`、`Ask what is ready`、
    `Explain why training is blocked`。
  - composer footer 改成只顯示 workflow hint，例如
    `No data loaded · Import EEG files to begin`；runtime / backend detail 只留在 tooltip /
    settings / logs，不進第一層。
  - 修 Assistant dock custom titlebar：空白 titlebar mouse events 交回 `QDockWidget`，保留
    dock drag；浮動 dock 會放在主視窗附近並 clamp 到可用螢幕。
  - 修 MainWindow geometry：首次啟動依可用螢幕置中；restore geometry 後 clamp；保留 resize /
    maximize / restore。
  - 補 `tests/integration/ui/test_window_geometry.py`，並更新 chat / walkthrough /
    AgentManager regression tests。
  - 重新 capture UI screenshots，更新 `artifacts/ui/ai-assistant-open.png` 與
    `tests/baselines/ui/ai-assistant-open.png`。
- 結果：
  - 第一層不再顯示 `General Assistant`、`Single step`、`Local model ready`、`Backend:`、
    `pipeline_stage`，visible transcript 也不曝露 raw tool/debug payload。
  - 320 / 380 / 460px dock 下 `hello` 保持可讀，composer input / Send button 不重疊。
  - status bar / footer 只保留 workflow next action，不顯示 local runtime ready。
- 證據：
  - `git diff --check`
  - `poetry run ruff check XBrainLab/ui/chat XBrainLab/ui/components/agent_manager.py XBrainLab/ui/main_window.py tests/unit/ui/chat tests/integration/ui`
    - `All checks passed!`
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/chat/test_chat_panel.py tests/integration/ui/test_product_walkthrough.py -q`
    - `42 passed in 9.22s`
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/chat/test_chat_panel.py tests/integration/ui/test_product_walkthrough.py tests/integration/ui/test_window_geometry.py tests/unit/ui/components/test_agent_manager.py tests/unit/ui/test_agent_manager_coverage.py -q`
    - `92 passed in 10.86s`
  - `xvfb-run -a poetry run python scripts/dev/capture_ui_baseline.py`
    - saved `artifacts/ui/ai-assistant-open.png`
- 接續 / 本輪剩餘：
  - 真 Windows launcher click-through / 真 local model 長時間 walkthrough 仍需人工驗收。

### 18:27 Assistant footer status removal follow-up

- 做了什麼：
  - 依最新人工不滿意回饋重看 `ChatPanel`、chat UI tests 和
    `artifacts/ui/ai-assistant-open.png`。
  - 確認舊 artifact 仍顯示 footer 狀態列文字，例如 workflow / local runtime summary。
  - 將常駐 workflow guidance band 改成隱藏相容欄位；workflow / model detail 改放
    header / Options tooltip 和 empty state。
  - 補 UI tests 鎖住 footer：composer footer 不得再出現 visible status label。
- 結果：
  - Assistant footer 只服務輸入、Retry、Clear，不再當 workflow/runtime status dashboard。
  - empty state 仍保留目前 workflow 和下一步；進入對話後不會持續把狀態文字壓在 footer。
- 證據：
  - `timeout 240s scripts/dev/run_ui_pytest.sh tests/unit/ui/chat/test_chat_panel.py tests/integration/ui/test_product_walkthrough.py -q`
    - `38 passed in 11.15s`
  - `timeout 240s scripts/dev/run_ui_pytest.sh --capture=no tests/integration/ui/test_product_walkthrough.py::test_assistant_product_click_through_layout -q`
    - `1 passed in 6.62s`
  - `timeout 240s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_ui_baseline.py`
    - updated `artifacts/ui/ai-assistant-open.png`
  - synced `tests/baselines/ui/ai-assistant-open.png` to the accepted assistant artifact
  - `git diff --check`
- 接續 / 本輪剩餘：
  - 仍需人工看圖確認 empty state 的 workflow 文案是否也要再降噪。

### 18:15 Assistant product status polish

- 做了什麼：
  - 人工審核 Goal session 產物後，確認 raw tool output 不再直接進入 visible transcript。
  - 發現 footer / runtime status 仍有 debug 感，補修 `ChatPanel`：隱藏 legacy
    `runtime_status_label`，改由 tooltip 保留完整資訊；subtitle 縮短；footer 狀態降噪；控制列高度
    由 70px 調成 64px。
  - 重新 capture `artifacts/ui/ai-assistant-open.png`，同步更新
    `tests/baselines/ui/ai-assistant-open.png`。
  - 修正 controller coverage 測試，避免 `hi` 被 greeting shortcut 接走而測不到 exception path。
- 結果：
  - Assistant dock 目前第一層資訊更接近使用者產品介面：header、guidance、empty state、
    composer footer 各自分工，不再把 workflow / runtime diagnostics 擠成一條醜的狀態列。
  - local ready / retry / clear 仍保留，但降到低干擾 footer，不把 raw backend command 或 tool
    schema 直接丟給使用者。
- 證據：
  - `git diff --check`
  - `poetry run pytest --capture=sys tests/unit/llm/agent/test_controller_cov.py tests/unit/ui/chat/test_chat_panel.py -q`
    - `67 passed`
  - `poetry run basedpyright`
    - `0 errors, 0 warnings, 0 notes`
  - `poetry run python scripts/dev/update_quality_dashboard.py`
    - overall `PASS` at `2026-05-02 18:11:29 UTC+08:00`
  - commit：`bb2c6f1 ui: polish assistant product status`
- 接續 / 本輪剩餘：
  - 真 Windows launcher click-through。
  - 真 local model 長時間 ChatPanel walkthrough。
  - API / Gemini code path 從 source code 刪除。

### 17:20 Assistant product audit follow-up

- 做了什麼：
  - 依人工驗收失敗證據重新審視 `ChatPanel`、`AgentManager`、`LLMController`、
    `application_surface.py` 和 local runtime settings。
  - 移除 assistant dock 頂部 chip dump；header 只保留 `XBrainLab Assistant`、subtitle、
    `Options`，workflow state / next step 改成單句 guidance。
  - 將 `Retry` / `Clear` 降到底部 composer footer；`Retry` 沒有上一則 request 時 disabled，
    direct call 只顯示 footer/status notice，不進 transcript。
  - 修正 message bubble minimum width，避免 380px dock 下 `hello` 被切成 `hell/o`。
  - `LLMController` 新增 greeting shortcut，`hello` 不再先亂 call tool。
  - `ToolCommandResult` 增加 product-level error bucket；read-only `list_files` 也走 typed
    normalization。
  - visible transcript 改成產品語言：missing directory 追問 folder/path，empty list 顯示空狀態，
    backend precondition 顯示 blocked reason，不再顯示 `Tool <name> completed (...)`、
    `Error: directory is required`、`[]` 或 snake_case command。
  - Gemini / remote runtime 一般產品 UI 和 startup 改由 `XBRAINLAB_SHOW_LEGACY_REMOTE_LLM=1`
    隔離，未設定時不顯示或啟動 legacy remote runtime。
  - 重跑 UI capture，更新 `artifacts/ui/ai-assistant-open.png` 和
    `tests/baselines/ui/ai-assistant-open.png`。
- 結果：
  - Assistant dock 目前像使用者產品面板，而不是 tool/debug status panel。
  - raw tool payload 仍保留在 controller history / diagnostics / logs，可供測試與 debug；
    第一層 chat transcript 不再外洩開發者語法。
- 證據：
  - `timeout 300s scripts/dev/run_ui_pytest.sh tests/unit/ui/chat/test_chat_panel.py tests/unit/ui/chat/test_message_bubble.py tests/unit/ui/dialogs/test_model_settings.py tests/unit/ui/components/test_agent_manager.py tests/unit/ui/test_agent_manager_coverage.py -q`
    - `131 passed`
  - `timeout 240s poetry run pytest --capture=sys tests/integration/agent/test_product_flow.py tests/unit/llm/agent/test_controller.py tests/unit/llm/tools/test_application_surface.py tests/unit/llm/tools/real/test_real_tools.py tests/unit/llm/core/test_config.py -q`
    - `110 passed`
  - `timeout 240s poetry run pytest --capture=sys tests/unit/backend/application tests/integration/backend/test_application_service_workflow.py tests/unit/backend/test_facade_coverage.py tests/unit/backend/test_facade_headless.py -q`
    - `57 passed`
  - `timeout 300s scripts/dev/run_ui_pytest.sh tests/integration/ui/test_product_walkthrough.py -q`
    - `2 passed`
  - `timeout 180s poetry run pytest --capture=sys tests/integration/agent/test_tool_call_eval.py tests/integration/agent/test_product_flow.py -q`
    - `7 passed`
  - `timeout 240s xvfb-run -a poetry run python scripts/dev/capture_ui_baseline.py`
    - saved `artifacts/ui/ai-assistant-open.png`
  - `timeout 420s poetry run python scripts/dev/update_quality_dashboard.py`
    - final rerun overall `PASS` at `2026-05-02 17:44:37 UTC+08:00`
- 接續 / 本輪剩餘：
  - final lint / format / mkdocs / dashboard gate。
  - local commits；不 push。
  - 真 Windows launcher click-through 和真 local model 長時間 UI walkthrough 仍未做。

### 12:02 Chat product blocker correction

- 做了什麼：
  - 接受人工驗收回報：AI Assistant UI 仍像 debug dock，且使用者輸入 `hello` 後沒有
    assistant 回覆。
  - 將 product gate 狀態從「接近完成」修正為被 chat response reliability / chat UX 擋住。
  - 追蹤 chat 路徑：`ChatPanel._on_send -> AgentManager.handle_user_input ->
    ChatController.add_user_message -> LLMController.handle_user_input -> AgentWorker ->
    LLMEngine -> chunk / finished / error -> ChatPanel bubble`。
  - 找出 automated gate 漏掉的風險：empty response 可 silent finalize；tool-only successful
    response 可被隱藏 JSON 後直接 finalize；normal `hello` product flow 沒有測 user-visible
    assistant bubble。
  - 重設計 ChatPanel 結構：header、status chips、empty state、composer、professional bubbles。
  - 補 product-flow tests：normal response、empty response fallback、worker error visible、
    local unavailable visible、UI structure。
- 結果：
  - 一般輸入 path 現在必須產生 visible assistant response 或 visible error。
  - empty response 會顯示可理解 fallback error；tool-only success 會顯示短 tool summary。
  - 文件已開始校正 automated smoke / deterministic eval / true product flow 的邊界。
- 證據：
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
    - 通過
  - `timeout 60s git diff --check`
    - 通過
  - `timeout 360s poetry run python scripts/dev/update_quality_dashboard.py`
    - overall `PASS`
- 接續 / 本輪剩餘：
  - 做 checkpoint commit。
  - 真 Windows Desktop shortcut click-through 仍需人工或可控 UI smoke。

### 07:05 Deterministic tool-call eval baseline

- 做了什麼：
  - 參考 BFCL、LangSmith trajectory evaluation、OpenAI structured-output / function-calling
    思路，落成 XBrainLab deterministic baseline，而不是先跑不穩的 local LLM eval。
  - 新增 `scripts/agent/evals/run_tool_call_eval.py`，定義 21 個 XBrainLab 專用 cases。
  - cases 覆蓋 empty state train refusal、load、preprocess、epoch、dataset、train readiness、
    reset confirmation、visualization/saliency block、invalid parameter、多輪補參數、tool result interpretation。
  - 產出 `artifacts/agent_evals/latest.json` 和 `artifacts/agent_evals/latest.md`。
- 結果：
  - deterministic baseline `21 / 21` passed。
  - 這是 eval framework / scripted baseline，不是 local LLM primary / fallback 真實成功率。
- 證據：
  - `timeout 180s poetry run pytest --capture=sys tests/integration/agent -q`
    - `1 passed`
  - `timeout 120s poetry run python scripts/agent/evals/run_tool_call_eval.py --output-dir artifacts/agent_evals`
    - wrote latest JSON / Markdown；failed cases `0`
- 本輪剩餘：
  - 若要宣稱 local LLM tool-call ability，需在下一輪用同一 case schema 接 primary / fallback runner。

### 06:46 Resource-safe final gate plan

- 做了什麼：
  - 準備進入本輪 final validation / documentation closure。
  - 依 resource-safe execution 規則，每次只跑一個重型任務，所有 pytest / UI / LLM /
    launcher / docs build 都加 `timeout`。
- 將跑哪些：
  - backend unit：`timeout 300s poetry run pytest --capture=sys tests/unit/backend -q`
  - backend + IO integration：`timeout 300s poetry run pytest --capture=sys tests/integration/backend tests/integration/io/test_io_integration.py -q`
  - pipeline integration：`timeout 600s poetry run pytest --capture=sys tests/integration/pipeline -q`
  - UI unit：`timeout 300s scripts/dev/run_ui_pytest.sh tests/unit/ui -q`
  - LLM unit：`timeout 300s poetry run pytest --capture=sys tests/unit/llm -q`
  - local runtime health/prompt/structured smoke：單獨執行，不與測試並行。
  - launcher startup smoke：`timeout 45s xvfb-run -a poetry run python run.py --model local`
  - docs / whitespace：`timeout 120s poetry run mkdocs build --strict`、`timeout 60s git diff --check`
- 為什麼：
  - 目前 backend、UI、agent、local runtime、launcher 都已有分段 evidence；final gate 要確認
    commit checkpoint 後仍能一起過。
- 預估風險：
  - pipeline integration 和 local model smoke 可能最耗時 / 最吃資源；若超時，會記錄超時點並改跑代表性抽樣。
- 結果：
  - backend unit、backend/IO integration、pipeline integration、UI unit、LLM unit、local runtime
    health/prompt/structured smoke、launcher startup smoke 皆完成。
  - local model preflight 首次發現 product bug：primary 已在 cache 中時仍被當成新增下載，
    造成 projected cache 誤判超過 20GB。已修成 already-cached model 不增加 projected cache。
  - launcher smoke 在 `MainWindow initialized` 後以 timeout 結束，屬 GUI smoke 預期結果。
- 證據：
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend -q`
    - `2661 passed, 1 skipped, 1 xfailed, 3 warnings`
  - `timeout 300s poetry run pytest --capture=sys tests/integration/backend tests/integration/io/test_io_integration.py -q`
    - `33 passed, 8 warnings`
  - `timeout 600s poetry run pytest --capture=sys tests/integration/pipeline -q`
    - `70 passed, 4 warnings`
  - `timeout 300s scripts/dev/run_ui_pytest.sh tests/unit/ui -q`
    - `811 passed`
  - `timeout 300s poetry run pytest --capture=sys tests/unit/llm -q`
    - first run found stale coverage tests expecting string-only tool results; after test/product fix:
      `649 passed`
  - `timeout 120s poetry run python scripts/dev/plan_local_model_download.py --format markdown`
    - after fix: `ok=True`, estimated download `0.00 GB`, projected cache `15.34 GB`
  - `timeout 300s poetry run python scripts/dev/inspect_local_assistant_runtime.py --format markdown --prompt-smoke --structured-smoke`
    - classification `gpu-ready`; prompt smoke `passed`; structured-output smoke `passed`
  - `timeout 45s xvfb-run -a poetry run python run.py --model local`
    - `MainWindow initialized` before expected timeout `124`
  - `timeout 60s git diff --check`
    - 通過
  - `timeout 120s poetry run mkdocs build --strict`
    - 通過
- worktree：
  - final docs closure 前仍有 local preflight fix、typed result compatibility test、validation docs 更新待 commit。

### 06:39 UI -> agent -> backend blocked-command flow test

- 做了什麼：
  - 新增 `tests/unit/ui/components/test_agent_manager.py` deterministic product-flow test。
  - 測試在不載入本地模型的情況下啟動 `AgentManager` / real `LLMController` / real `Study`，
    透過 debug tool 執行 `start_training`。
  - empty state 下 `ApplicationService` policy 擋下 train，UI chat 收到 structured
    `Tool Output`，內含 `ok=false`、`command_name=train` 和 shared blocked reason。
- 結果：
  - Milestone D/H 的「至少一條 UI -> agent -> backend blocked command flow 可測」已有 low-risk
    deterministic coverage。
  - 這不是取代真 launcher click-through；真桌面啟動後開 chat panel 的 product smoke 仍要跑。
- 證據：
  - `timeout 180s scripts/dev/run_ui_pytest.sh tests/unit/ui/components/test_agent_manager.py tests/unit/ui/chat/test_chat_panel.py -q`
    - `49 passed`
- 本輪剩餘：
  - launcher startup / chat-panel smoke。
  - final gate 前依 resource-safe 規則逐步跑 backend、UI、LLM、integration、MkDocs。

### 06:25 Agent typed result adapter

- 做了什麼：
  - 在 `XBrainLab/llm/tools/application_surface.py` 新增 `ToolCommandResult`，把 agent tool
    blocked / failed / successful result 轉成 typed payload。
  - `LLMController._execute_tool_no_loop()` 對 ApplicationService-backed tools 回傳 structured
    result，並把 legacy `"Error: ..."` / `"Failed ..."` 字串判定成 failed result。
  - 補 `test_application_surface.py` 和 `test_controller.py`，確認 blocked preprocess / blocked
    train / legacy string failure 都不再被當成成功。
  - 修正 `tests/unit/llm/agent/test_worker.py`，避免測試將 repo `settings.json` 寫回
    Gemini / API mode。
- 結果：
  - Agent tool system alignment 的 typed result adapter 缺口已收斂。
  - ApplicationService-backed tool output 會保留 `command_name`、`error_type`、`blocked_reason`、
    `state`、`capability`、`raw_result`。
- 證據：
  - `timeout 120s poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/unit/llm/agent/test_controller.py -q`
    - `55 passed`
  - `timeout 180s poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
    - `321 passed`
  - `timeout 60s git diff --check`
    - 通過
- 本輪剩餘：
  - 驗收 launcher -> MainWindow -> chat panel -> blocked-command product flow。
  - 逐步把 real tool execution 由 legacy facade string surface 推進到直接回傳 backend `CommandResult`。

### 04:46 Resource-safe autopilot 恢復與 worktree checkpoint 規劃

- 做了什麼：
  - 依使用者指示切到 resource-safe execution：重型任務一次只跑一個、所有可能卡住的測試 / UI / LLM / docs build 都要加 `timeout`。
  - 確認沒有殘留的 `pytest`、`python run.py`、local model health check、download 或 GUI 常駐 process。
  - 重新讀取 `git status --short`、`git diff --stat`、`AGENTS.md`、planning / roadmap / architecture / validation / worklog / implementation log 的恢復點。
  - 將 current-facing 文件中把本輪交付缺口寫成「後續」的語意改成「本輪剩餘 / 目前執行中」，避免下一個 agent 誤判成可延後事項。
- 結果：
  - 目前判斷不是重做 Milestone 1，而是從已完成的 backend baseline、UI/agent readiness、local LLM smoke、launcher baseline 繼續收斂。
  - `tests/unit/llm` 重新跑通；中途發現 coverage-booster tests 還停在舊 downloader / controller / worker / engine contract，已修成目前 contract 並移除無限 queue mock。
  - 接下來先跑 docs / diff 靜態驗證，再做 coherent checkpoint commit，不把整個 dirty worktree 一次吞掉。
- 證據：
  - `timeout 30s ps -ef | rg 'poetry|pytest|python run.py|inspect_local_assistant_runtime|plan_local_model_download|mkdocs|xvfb|huggingface|transformers|pip|uvicorn|jupyter'`
    - 無殘留 heavy process。
  - `timeout 60s git status --short`
    - worktree 仍有 docs cleanup、backend application service、UI / agent command surface、local LLM / launcher、validation / public fixture 等多類變更，需分批 commit。
  - `timeout 180s poetry run pytest --capture=sys tests/unit/llm/core/test_model_catalog.py tests/unit/scripts/test_plan_local_model_download.py tests/unit/scripts/test_inspect_local_assistant_runtime.py tests/unit/llm/core/test_config.py tests/unit/llm/core/test_downloader.py tests/unit/llm/core/test_local_backend.py tests/unit/llm/core/test_engine.py tests/unit/llm/agent/test_worker.py tests/unit/llm/test_controller_coverage.py tests/unit/ui/components/test_agent_manager.py tests/unit/ui/dialogs/test_model_settings.py tests/unit/ui/test_local_bootstrap_validation.py -q`
    - `183 passed`
  - `timeout 240s poetry run pytest --capture=sys tests/unit/llm -q -x`
    - `647 passed`
  - `timeout 120s poetry run mkdocs build --strict`
    - 通過
  - `timeout 60s git diff --check`
    - 通過
  - `timeout 180s poetry run pytest --capture=sys tests/unit/backend/application tests/integration/backend/test_application_service_workflow.py tests/unit/backend/test_facade_coverage.py tests/unit/backend/test_facade_headless.py -q`
    - `55 passed`
  - `timeout 120s git commit -m "backend: add application service command core"`
    - `a6f0175`
  - `timeout 240s scripts/dev/run_ui_pytest.sh tests/unit/ui/test_application_capabilities.py tests/unit/ui/chat/test_chat_panel.py tests/unit/ui/components/test_agent_manager.py tests/unit/ui/dialogs/test_model_settings.py tests/unit/ui/test_agent_manager_coverage.py tests/unit/ui/test_local_bootstrap_validation.py tests/unit/ui/test_workflow.py -q`
    - `115 passed`
  - pre-commit 首次檢查擋下 local runtime / launcher checkpoint：修正 ruff 長行、測試假 key allowlist、launcher path false positive、以及舊 coverage tests。
  - 重新跑：
    - `timeout 240s poetry run pytest --capture=sys tests/unit/llm -q -x`
      - `647 passed`
    - `timeout 240s scripts/dev/run_ui_pytest.sh tests/unit/ui/test_application_capabilities.py tests/unit/ui/chat/test_chat_panel.py tests/unit/ui/components/test_agent_manager.py tests/unit/ui/dialogs/test_model_settings.py tests/unit/ui/test_agent_manager_coverage.py tests/unit/ui/test_local_bootstrap_validation.py tests/unit/ui/test_workflow.py -q`
      - `115 passed`
  - `timeout 180s git commit -m "assistant: unify command surface and local runtime"`
    - `38d3f00`
  - `timeout 120s poetry run mkdocs build --strict`
    - 通過；用於驗收 docs cleanup / current-facing docs patch。
  - data / validation chunk：
    - `timeout 180s poetry run pytest --capture=sys tests/unit/backend/load_data/test_raw_data_loader.py tests/unit/scripts/test_report_dataset_validation_matrix.py tests/unit/scripts/test_run_public_cross_source_training_smoke.py -q`
      - `10 passed`
    - `timeout 300s poetry run pytest --capture=sys tests/integration/io/test_io_integration.py -q`
      - `31 passed, 8 warnings`
    - `timeout 300s poetry run pytest --capture=sys tests/integration/pipeline/test_checked_in_real_dataset_validation.py -q`
      - `6 passed`
    - `timeout 300s poetry run pytest --capture=sys tests/integration/pipeline/test_public_cross_source_training_smoke.py -q`
      - `4 passed, 3 warnings`
  - UI/type/artifact chunk：
    - `timeout 300s scripts/dev/run_ui_pytest.sh tests/unit/ui -q`
      - `810 passed`
- 本輪剩餘：
  - 先提交 local LLM runtime + launcher + docs correction checkpoint。
  - 再盤點並提交 backend / UI-agent / docs cleanup / validation chunks。

### 02:08 Local LLM runtime / launcher product baseline

- 做了什麼：
  - 依使用者限制移除舊 Qwen cache，並把 benchmark script 裡可執行的 Qwen local model
    entry 改成 product catalog 內的 Phi model。
  - 新增/收斂 local model catalog、下載 preflight、runtime inspection、primary/fallback
    health check。
  - 下載 primary `microsoft/Phi-4-mini-instruct` 和 fallback
    `microsoft/Phi-3.5-mini-instruct`，總 cache 約 `15.34GB`。
  - 修正 local backend 對 Phi remote code / Transformers cache API 的 compatibility，
    並讓 generation thread exception 能回傳錯誤，不再讓 smoke 卡住。
  - AgentManager 第一次開 chat panel 不再強迫 settings modal；runtime 不可用時面板仍可開，
    並顯示明確原因。
  - 建立 Windows launcher `.cmd` / `.ps1`，並複製 `.cmd` 到 Desktop。
- 結果：
  - 中國公司或中國來源模型不再是 product local runtime 候選；Qwen cache 已刪。
  - primary / fallback local model 都可在 CUDA 上完成 prompt smoke 和 structured-output smoke。
  - startup smoke 顯示 `MainWindow initialized`，GUI timeout 結束屬預期。
- 證據：
  - `poetry run python scripts/dev/plan_local_model_download.py --model microsoft/Phi-3.5-mini-instruct --format markdown`
    - `ok: True`，projected cache `15.33 GB`
  - `poetry run python scripts/dev/inspect_local_assistant_runtime.py --format markdown --prompt-smoke --structured-smoke`
    - primary prompt smoke `passed`
    - primary structured-output smoke `passed`
  - `poetry run python scripts/dev/inspect_local_assistant_runtime.py --model microsoft/Phi-3.5-mini-instruct --format markdown --prompt-smoke --structured-smoke`
    - fallback prompt smoke `passed`
    - fallback structured-output smoke `passed`
  - `timeout 35s xvfb-run -a poetry run python run.py --model local`
    - `MainWindow initialized` 後 timeout
  - `poetry run pytest --capture=sys tests/unit/llm/core/test_config.py tests/unit/llm/agent/test_worker.py tests/unit/ui/components/test_agent_manager.py -q`
    - `66 passed`
  - `poetry run pytest --capture=sys tests/unit/llm/core/test_local_backend.py -q`
    - `18 passed`
- 本輪剩餘：
  - 需要完成 launcher -> chat panel -> agent blocked-command 的互動式 walkthrough。
  - API / Gemini code path 仍是待移除殘留，不是產品目標。

### 01:38 Product delivery 文件指令校準

- 做了什麼：
  - 全面掃描 `docs/`、`.agents/`、`AGENTS.md`、`README.md` 的 current-facing 文件。
  - 找到 `docs/planning/now.md`、`docs/index.md`、`docs/planning/roadmap.md`、
    `docs/validation/README.md`、`.agents/runbooks/*` 等仍殘留文件整理期 /
    全盤架構複盤期的保守指令。
  - 將這些入口統一改成 product-delivery engineering：backend、UI、agent、
    local LLM、desktop launcher、product stabilization，且 tool-call eval 等產品主線穩定後再做。
- 結果：
  - 下一個 agent 不應再被「不開工 / 先全盤複盤 / 只做後端 baseline」的舊文字拉回保守模式。
  - milestone 被明確定位為最低交付門檻，不是工作上限。
- 證據：
  - `poetry run mkdocs build --strict`
    - 通過
  - `git diff --check -- docs .agents AGENTS.md README.md mkdocs.yml`
    - 通過
  - stale instruction scan：
    - current-facing 文件已沒有過期停止條件；records 內歷史語句保留為歷史紀錄。
- 本輪剩餘：
  - 下一個工程 agent 可直接按 `AGENTS.md` 和 `docs/planning/now.md` 推進 product delivery。

### 01:04 UI / Agent command surface unification

- 做了什麼：
  - 依成熟工程驗收標準回頭檢查 Milestone 1，發現 `preprocess` capability 原本用
    `has_preprocessed_data` 當前置條件，會讓 raw-only state 的 readiness 判斷失真。
  - 修正 capability policy：preprocess 現在要求 raw data，而 create epoch 才要求
    preprocessed data。
  - 新增 `XBrainLab/llm/tools/application_surface.py`，把 agent tools 對映到
    ApplicationService commands，讓 prompt tool list 與 execution guard 都讀同一套
    backend capability policy。
  - Chat panel 補 retry / clear controls、compact backend/model status；AgentManager
    補 retry、debug tool 接線和 backend diagnostics refresh。
  - UI readiness 第一批接到 ApplicationService policy：dataset import、preprocess、
    epoching、start training。
  - Agent tool output 寫回 structured JSON payload，保留 `ok`、`tool_name`、
    `message`、`raw_result`。
  - 補 UI / agent command surface tests。
- 結果：
  - load / preprocess / epoch / dataset / train / reset 主 workflow 的 availability 判斷
    已由 ApplicationService capability policy 產生。
  - UI 和 Agent 對同一 blocked command 會看到同一套 backend reason。
  - UI action execution 仍有 legacy controller path，但 UI-facing decision 已開始共用
    service policy。
- 證據：
  - `poetry run pytest --capture=sys tests/unit/backend/application -q`
    - `9 passed`
  - `poetry run pytest --capture=sys tests/unit/backend/test_facade_coverage.py tests/unit/backend/test_facade_headless.py -q`
    - `44 passed`
  - `poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
    - `318 passed`
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui -q`
    - `807 passed`
  - `poetry run pytest --capture=sys tests/integration/backend/test_application_service_workflow.py -q`
    - `2 passed`
  - `poetry run mkdocs build --strict`
    - 通過
  - `git diff --check`
    - 通過
- 本輪剩餘：
  - 下一步要把更多 UI action execution 改成 command adapter，而不是只讀 policy。
  - Agent real tools 仍需要更完整地直接消費 `CommandResult`，目前 history 已保留
    structured tool output，但 UI side effects 還是 `Request:` 字串協定。

### 00:23 Backend Application Service contract 驗收收斂

- 做了什麼：
  - 跑第二輪基準驗收：targeted backend/facade tests、MkDocs strict、diff whitespace 都先通過。
  - 開四個 auditor 檢查 command contract、facade parity、workflow test depth、dirty worktree scope。
  - 補齊 `evaluate` / `visualize` / `saliency` / `new_session` 的 future command objects，並在 policy 中標成 unavailable。
  - 將 service 內 `set_montage` 從假成功改成 confirmation-required failure，保留 `BackendFacade.set_montage()` legacy path。
  - 補強 `reset_session`，讓它清掉 active session 的 raw / preprocess / epoch / dataset / trainer / model option / saliency config。
  - 修正 `BackendFacade.load_data()` total failure 的舊 `(count, errors)` shape，並讓 inactive `stop_training()` 不再靠錯誤訊息字串判斷。
  - 補 application unit tests、low-mock integration workflow tests、facade parity tests。
- 結果：
  - CommandName、command dataclass、CapabilityPolicy、execute router 已對齊。
  - 未實作 command 不再被 policy 宣稱可用，也不會掉進 router `KeyError`。
  - workflow test 已覆蓋 load -> epoch -> dataset -> training readiness -> reset invalidation，以及 failed command last_error lifecycle。
- 證據：
  - `poetry run pytest --capture=sys tests/unit/backend/application tests/integration/backend/test_application_service_workflow.py tests/unit/backend/test_facade_coverage.py tests/unit/backend/test_facade_headless.py -q`
    - `54 passed`
  - `poetry run pytest --capture=sys tests/unit/backend -q`
    - `2660 passed, 1 skipped, 1 xfailed`
  - `poetry run pytest --capture=sys tests/integration/backend tests/integration/io/test_io_integration.py -q`
    - `33 passed`
  - `poetry run pytest --capture=sys tests/integration/pipeline -q`
    - `70 passed`
  - `poetry run ruff check XBrainLab/backend/application XBrainLab/backend/facade.py tests/unit/backend/application tests/integration/backend/test_application_service_workflow.py tests/unit/backend/test_facade_coverage.py tests/unit/backend/test_facade_headless.py`
    - 通過
  - `poetry run basedpyright XBrainLab/backend/application XBrainLab/backend/facade.py`
    - `0 errors`
  - `poetry run mkdocs build --strict`
    - 通過
  - `git diff --check`
    - 通過
  - `poetry run python scripts/dev/update_quality_dashboard.py`
    - `Overall status: PASS`
- 後續：
  - 下一輪補 facade/controller parity real workflow，並設計 evaluation / visualization / saliency query command contract。

## 2026-05-01

### 23:49 Backend refactor validation 收尾

- 做了什麼：
  - 跑完 backend unit、backend+IO integration、full pipeline、MkDocs strict、diff whitespace 和 quality dashboard。
  - 修正 `RealListFilesTool` 在 WSL/Linux 下把不存在的 Windows fallback path resolve 成 repo root，導致 `tests/data` 被誤判為敏感目錄的問題。
- 結果：
  - 後端 Application Service slice 與既有 IO / pipeline smoke 都通過。
  - `artifacts/quality/latest.md` 已更新為 `PASS`。
- 證據：
  - `poetry run pytest --capture=sys tests/unit/backend -q`
    - `2651 passed, 1 skipped, 1 xfailed`
  - `poetry run pytest --capture=sys tests/integration/backend/test_application_service_workflow.py tests/integration/io/test_io_integration.py -q`
    - `32 passed`
  - `poetry run pytest --capture=sys tests/integration/pipeline -q`
    - `70 passed`
  - `poetry run mkdocs build --strict`
    - 通過
  - `git diff --check`
    - 通過
  - `poetry run python scripts/dev/update_quality_dashboard.py`
    - `Overall status: PASS`
- 後續：
  - UI service-first migration、`set_montage()` command 化、agent tools 直接消費 `CommandResult`。

### 23:41 Backend Application Service 第一版

- 做了什麼：
  - 先盤點 dirty worktree：文件整理 / validation / backend / UI+LLM 變更混在一起，保留既有合理成果，不清空 worktree。
  - 開 subagents 盤點 backend 架構、test quality、Application Service 設計與 implementation readiness。
  - 新增 `XBrainLab/backend/application/`，包含 commands、state snapshot、capability policy、command result、error boundary 和 `ApplicationService`。
  - 將 `BackendFacade` 核心 workflow 改成透過 `ApplicationService` 執行，保留舊 API 形狀給 assistant tools / scripts。
  - 新增 service contract unit tests 和 synthetic real backend workflow integration test。
- 結果：
  - `BackendFacade` 不再是核心 workflow 邏輯聚集點；它現在是 command API wrapper。
  - backend 可由 state snapshot 判斷 raw / preprocess / epoch / dataset / training / evaluation / visualization 狀態。
  - capability policy 可由 backend state 阻擋缺前置條件 command。
- 證據：
  - `XBrainLab/backend/application/`
  - `tests/unit/backend/application/test_application_service.py`
  - `tests/integration/backend/test_application_service_workflow.py`
  - `poetry run pytest --capture=sys tests/unit/backend -q`
    - `2651 passed, 1 skipped, 1 xfailed`
  - `poetry run basedpyright XBrainLab/backend/application XBrainLab/backend/facade.py`
    - `0 errors`
- 後續：
  - 跑 pipeline / IO / docs validation。
  - 補更多 state invalidation、training readiness、facade/controller parity tests。

### 23:04 .agents 工程 workflow skill pack 校準

- 做了什麼：
  - 新增 TDD、測試品質、code review、software design review skills。
  - 新增 `tdd-change` 和 `test-audit` workflows。
  - 將 context 文件降級成 source-of-truth 導讀，不重寫架構。
- 結果：
  - `.agents` 從專案文件操作層，補上更通用的軟體工程 workflow。
  - skills 設計方向改成參考成熟 AI coding / TDD / review workflow，再套到 XBrainLab。
- 證據：
  - `.agents/skills/`
  - `.agents/workflows/`
  - `.agents/context/`
- 後續：
  - MkDocs strict、diff whitespace、agent skill/workflow scan 已通過。

### 22:55 .agents skills / workflows 第一版

- 做了什麼：
  - 新增 `.agents/skills/` 與 `.agents/workflows/`。
  - 建立 docs-curator、architecture-reviewer、validation-runner、refactor-slicer、agent-toolcall-designer 五個 skill。
  - 建立 documentation-review、architecture-review、refactor-slice、agent-toolcall-scoring 四個 workflow。
  - 更新 `.agents/README.md`、`.agents/stack.md`、setup、autopilot、active queue。
- 結果：
  - `.agents` 不再只有 runbook / context，而有可重用能力與多步驟流程。
  - 舊 `xbrainlab-*` skills 仍不恢復；新 skills 對齊目前 canonical docs。
- 證據：
  - `.agents/skills/`
  - `.agents/workflows/`
- 後續：
  - 跑 MkDocs strict、diff whitespace、agent file scan。

### 22:52 blocked commands 定位

- 做了什麼：
  - 補充 `blocked_commands` 的用途與暴露邊界。
  - 明確寫出完整 blocked list 不應直接塞給 LLM。
- 結果：
  - `blocked_commands` 保留給 verifier、scorer、debug、UI diagnostics。
  - Context Assembler 只在和使用者當前意圖相關時摘要 blocked reason。
- 證據：
  - `docs/target/agent.md`
- 後續：
  - MkDocs strict、diff whitespace 檢查與 blocked command wording scan 已通過。

### 22:48 Active dataset pipeline 邊界校準

- 做了什麼：
  - 將多 dataset 的說法收斂成一個 active dataset pipeline。
  - 明確寫出 epoch / dataset 形成後，不應讓 agent 一般性地 load new data / 開新 dataset。
  - 將載入新資料改成 reset / new session / fork 類高風險 command，需要確認。
- 結果：
  - 目標狀態支援同一 dataset 上多個 run / result，但不支援同時任意開多個 active dataset。
  - capability policy 需在 epoch / dataset 後阻擋一般 load new data。
- 證據：
  - `docs/target/agent.md`
  - `docs/target/architecture.md`
  - `docs/architecture/agent.md`
- 後續：
  - MkDocs strict、diff whitespace 檢查與 active dataset wording scan 已通過。

### 22:47 多資源不等於任意並行

- 做了什麼：
  - 修正 target agent / architecture 對多資源 workflow 的描述。
  - 補明確 dependency gate：沒 data 不能 preprocess、沒 dataset 不能 training、沒 trained result 不能 saliency。
- 結果：
  - 多資源 / 多 job 表示狀態可以共存，不代表所有 command 都能同時或任意執行。
  - capability policy 需要針對每個 target resource 判斷可執行性。
- 證據：
  - `docs/target/agent.md`
  - `docs/target/architecture.md`
  - `docs/architecture/agent.md`
- 後續：
  - MkDocs strict、diff whitespace 檢查與 dependency wording scan 已通過。

### 22:45 Command gate 與多資源 workflow 校準

- 做了什麼：
  - 將 `available_commands` 改成 backend / Application Service capability policy 的輸出。
  - 在 State Snapshot 補 `capability_policy`、`active_jobs`、`completed_runs`。
  - 補上 workflow state 不應是單一路徑，而應支援多資料、多 training run、visualization / saliency 和下一筆 training 並行。
  - 同步 `target/architecture.md` 和 `architecture/agent.md`。
- 結果：
  - agent 不再被設計成拿全部 tool 自己猜；backend 應控制可用 capability。
  - target state model 開始支援 resources / jobs / results，而不是只靠 `workflow_stage`。
- 證據：
  - `docs/target/agent.md`
  - `docs/target/architecture.md`
  - `docs/architecture/agent.md`
- 後續：
  - MkDocs strict、diff whitespace 檢查與 capability wording scan 已通過。

### 22:42 Target agent 補四個 contract 外框

- 做了什麼：
  - 將 State Snapshot、Tool Call、Verification Result、Scoring 四個 contract 寫進 `docs/target/agent.md`。
  - 保持在外框規格，不展開每個具體 tool schema。
- 結果：
  - target agent 從流程概念變成可開工前討論的 contract 草案。
  - 後續可以在 backend command surface 定下來後補實際 schema。
- 證據：
  - `docs/target/agent.md`
- 後續：
  - MkDocs strict、diff whitespace 檢查與 contract wording scan 已通過。

### 22:40 Target agent Mermaid 圖修正

- 做了什麼：
  - 將 `docs/target/agent.md` 的 Mermaid 從 subgraph-heavy layout 改成 left-to-right 單線流程。
  - 移除造成圖面拉歪的 Prompt subgraph 與交叉回饋線。
- 結果：
  - 圖面更接近：prompt inputs -> Context Assembler -> LLM -> Verification -> Backend / Self-correction -> State feedback。
- 證據：
  - `docs/target/agent.md`
- 後續：
  - 跑 MkDocs strict 和 diff whitespace 檢查。

### 22:37 Thesis evidence 改成 tool-call scoring system

- 做了什麼：
  - 將 thesis evidence 從泛稱 evidence 改成要建立 agent tool-call scoring system。
  - 在 `target/agent.md` 補分項準確率、benchmark case 類型與失敗 taxonomy。
  - 在 `validation/README.md` 補 Agent Tool-Call Scoring 區塊。
- 結果：
  - thesis evidence 的目標更具體：要有可重跑 benchmark、scorer、report / artifact。
  - 舊 Gemini/API benchmark 被標成歷史參考，新的 scorer 要對齊 local-only runtime 和新 command surface。
- 證據：
  - `docs/target/requirements.md`
  - `docs/target/agent.md`
  - `docs/validation/README.md`
- 後續：
  - MkDocs strict、diff whitespace 檢查與 scoring wording scan 已通過。

### 22:35 Target agent 補 State Manager / Verification Layer

- 做了什麼：
  - 在 `docs/target/agent.md` 加入 target control loop Mermaid 圖。
  - 補 Context Assembler、State Manager、Verification Layer、Self-Correction 的目標責任。
  - 補 tool schema 應標示的 contract 欄位。
- 結果：
  - agent 目標文件不再只描述 tool-call，而是記錄完整狀態管理與驗證閉環。
  - 使用者提供的設計被納入 target 文件，後續可作為 agent redesign 的基準。
- 證據：
  - `docs/target/agent.md`
- 後續：
  - MkDocs strict、diff whitespace 檢查與 target agent wording scan 已通過。

### 22:32 Target requirements 補 XBrainLab 本體

- 做了什麼：
  - 補強 `docs/target/requirements.md` 對 XBrainLab 本體的描述。
  - 將需求從 assistant / command API 前移到 EEG desktop workflow 本身。
  - 修正 `docs/target/README.md` 仍殘留的 API / Gemini 待簡化說法。
- 結果：
  - requirements 現在先說清楚資料匯入、label/event、preprocess、dataset、training、evaluation、visualization 這些本體需求。
  - assistant 被定位成同一套 workflow 的操作層，不再壓過 XBrainLab 本體。
- 證據：
  - `docs/target/requirements.md`
  - `docs/target/README.md`
- 後續：
  - MkDocs strict、diff whitespace 檢查與 target wording scan 已通過。

### 22:30 API / Gemini 移除決策校準

- 做了什麼：
  - 將 API / Gemini code path 從「待簡化 / compatibility」改成「後續要移除」。
  - 同步 current、architecture、validation、planning、decisions 和 `.agents` 文件。
- 結果：
  - local-only 不再只是抽象方向，而是排除 API / Gemini 產品路線的明確決策。
  - 實作上仍不在本輪文件整理直接拔除，避免在架構複盤前擴大改動。
- 證據：
  - `docs/decisions/README.md`
  - `docs/architecture/agent.md`
  - `docs/planning/roadmap.md`
  - `.agents/runbooks/active-queue.md`
- 後續：
  - MkDocs strict、diff whitespace 檢查與 active wording scan 已通過。

### 22:26 Documentation audit 收束

- 做了什麼：
  - 刪除 `docs/records/documentation_audit.md`。
  - 移除 README、MkDocs nav、`docs/current.md`、`.agents/runbooks/*` 對它的 active 引用。
- 結果：
  - `records/` 回到只承載 implementation log 和 worklog。
  - 文件可信度不再獨立成一張表，而是回到 current、architecture、validation、decisions 各自維護。
- 證據：
  - `README.md`
  - `docs/current.md`
  - `mkdocs.yml`
  - `.agents/runbooks/setup.md`
  - `.agents/runbooks/autopilot.md`
- 後續：
  - MkDocs strict、diff whitespace 檢查與 active stale reference scan 已通過。

### Workspace 搬遷確認

- 做了什麼：
  - 將 active repo 建立在 `/mnt/d/workspace_v2/projects/lab/XBrainLab`。
  - 舊 `/mnt/d/repos/XBrainLab` 保留為備援 / 參考副本。
- 結果：
  - active repo path 已確認。
  - branch 和 remote 保留。
- 證據：
  - branch: `codex/stabilization-autopilot`
  - remote: `https://github.com/hxin-an/XBrainLab.git`
- 後續：
  - active 文件中避免再把舊路徑當成 current truth。

### 文件結構重整

- 做了什麼：
  - 將文件切成 `docs/`、`docs/architecture/`、`docs/legacy/`。
  - 舊 agent 文件、舊 current、舊 ADR、history、archive 移到 `legacy/`。
- 結果：
  - current truth 和 historical reference 已分離。
- 證據：
  - `docs/index.md`
  - `docs/README.md`
  - `docs/legacy/README.md`
- 後續：
  - 從 legacy 抽可信內容時，先對 source code / runtime evidence。

### 新 Poetry 環境建立

- 做了什麼：
  - 在新 workspace 執行 `poetry install --with dev,test,docs`。
- 結果：
  - 標準開發、測試、文件工具鏈可用。
- 證據：
  - Poetry env: `/home/administrator/.cache/pypoetry/virtualenvs/xbrainlab-TKrzxeIe-py3.12`
  - import probe 通過：`PIL`、`mne`、`PyQt6`、`torch`、`pytest`、`XBrainLab`
- 後續：
  - optional `llm` group 尚未安裝，local LLM / `torchinfo` 不能算已驗證。

### Dashboard 第一次刷新

- 做了什麼：
  - 執行 `scripts/dev/update_quality_dashboard.py`。
- 結果：
  - dashboard 可在新 workspace 產生。
  - 第一次結果有兩個 UI unit failure 和一個 UI baseline failure。
- 證據：
  - `test_on_plan_select_success` 因缺 `torchinfo` 失敗。
  - `test_set_model` 期待 `Gemini`，但實際 runtime key 是 `gemini`。
  - `ai-assistant-open.png` live artifact 尺寸和 current worktree reference 不同。
- 後續：
  - 判斷 UI unit failure 是測試邊界問題，不是 app 行為壞掉。

### UI unit test 修正

- 做了什麼：
  - `tests/unit/ui/test_model_summary.py` 改用 fake `torchinfo` module。
  - `tests/unit/ui/test_ui_misc.py` 對齊 `LLMConfig.normalize_backend_mode()`，期待 `gemini`。
- 結果：
  - targeted UI tests 通過。
- 證據：
  - `2 passed`
- 後續：
  - `torchinfo` 保持 optional `llm` dependency，不要求標準 `dev,test` env 安裝。

### Dashboard 第二次刷新

- 做了什麼：
  - 重新執行 fast quality dashboard。
- 結果：
  - dashboard overall 仍是 `FAIL`。
  - 失敗只剩 `UI Baseline Capture`。
- 證據：
  - generated at: `2026-05-01 19:16:09 UTC+08:00`
  - workspace: `/mnt/d/workspace_v2/projects/lab/XBrainLab`
  - Ruff Lint: `PASS`
  - Basedpyright: `PASS`
  - Architecture Compliance: `PASS`
  - Startup Smoke: `PASS`
  - UI Dialog Acceptance: `PASS`
  - UI Unit Suite: `PASS` (`799 passed`)
  - Real-Data IO Integration: `PASS` (`31 passed`)
- 後續：
  - 決定 `tests/baselines/ui/ai-assistant-open.png` 要採用哪個 approved reference。

### UI baseline 待決策

- 做了什麼：
  - 比對 `ai-assistant-open.png` 尺寸來源。
- 結果：
  - live artifact 是 `(1428, 800)`。
  - repo HEAD reference 是 `(1428, 800)`。
  - current dirty worktree reference 是 `(1523, 800)`。
- 證據：
  - `artifacts/ui/ai-assistant-open.png`
  - `tests/baselines/ui/ai-assistant-open.png`
- 後續：
  - 建議接受 `(1428, 800)` 作為 approved baseline，再重跑 dashboard 取得 clean `PASS`。

### 文件站點驗證

- 做了什麼：
  - 修正 legacy current README 的 active 文件連結。
  - 讓 MkDocs 排除 legacy API stub。
  - 執行 `poetry run mkdocs build --strict`。
- 結果：
  - MkDocs strict build 通過。
- 證據：
  - active / architecture 連結檢查：`MISSING=0`
  - `mkdocs build --strict` exit 0
- 後續：
  - legacy 裡沒有進 nav 的頁面保留為 reference，不當成 active 文件站點核心內容。

### UI baseline 決策

- 做了什麼：
  - 接受 `artifacts/ui/ai-assistant-open.png` 作為 `tests/baselines/ui/ai-assistant-open.png` 的 approved baseline。
- 結果：
  - baseline reference 從 dirty worktree 的 `(1523, 800)` 對齊到 `(1428, 800)`。
  - 這個尺寸和 live artifact、repo HEAD reference 一致。
- 證據：
  - live artifact: `(1428, 800)`
  - repo HEAD reference: `(1428, 800)`
  - current reference: `(1428, 800)`
- 後續：
  - 重跑 fast quality dashboard。

### Dashboard clean PASS

- 做了什麼：
  - 執行 `/home/administrator/.local/bin/poetry run python scripts/dev/update_quality_dashboard.py`。
- 結果：
  - dashboard overall 從 `FAIL` 變成 `PASS`。
  - 所有 fast checks 都是 `pass`。
- 證據：
  - generated at: `2026-05-01 19:28:48 UTC+08:00`
  - workspace: `/mnt/d/workspace_v2/projects/lab/XBrainLab`
  - Ruff Lint: `PASS`
  - Basedpyright: `PASS`
  - Architecture Compliance: `PASS`
  - Startup Smoke: `PASS`
  - UI Baseline Capture: `PASS`
  - UI Dialog Acceptance: `PASS`
  - UI Unit Suite: `PASS` (`799 passed`)
  - Real-Data IO Integration: `PASS` (`31 passed`)
- 後續：
  - 進入 legacy 文件抽樣驗證，不再卡在工程基準是否健康。

### Pipeline smoke 抽樣

- 做了什麼：
  - 檢查現有 `tests/integration/pipeline/`。
  - 跑兩個代表性的 tiny pipeline smoke。
- 結果：
  - 已有 synthetic train/evaluate 和 Study facade train cycle 測試。
  - targeted smoke 通過。
- 證據：
  - `tests/integration/pipeline/test_full_pipeline.py::TestFullPipeline::test_train_and_evaluate_metrics`
  - `tests/integration/pipeline/test_study_training_e2e.py::TestStudyTrainCycle::test_full_cycle_eegnet`
  - `2 passed in 7.54s`
- 後續：
  - 在 `validation/README.md` 定義 pipeline validation 分層。
  - 在 `planning/roadmap.md` 記錄是否要把 tiny pipeline smoke 加入 fast dashboard。

### Roadmap 對齊 repo legacy 進度報告

- 做了什麼：
  - 對照 `docs/legacy/current/STATUS_REPORT.md` 的 `Next Review Focus`。
  - 對照 `docs/legacy/current/PLAN.md` 的高層順序。
- 結果：
  - `planning/roadmap.md` 不再只用臨時整理路線，而是對齊舊進度報告的方向：
    - stabilization first
    - agent redesign second
    - validation throughout
  - 下一階段改成 dataset / pipeline reproducibility baseline、supported desktop/runtime matrix，然後才進 phase-5 tool-call redesign。
- 證據：
  - `STATUS_REPORT.md` 指出 phase 5 尚未開始。
  - `STATUS_REPORT.md` 的候選下一步包含 local-only cross-source evidence、desktop/local runtime matrix、bounded phase-5 item。
- 後續：
  - 審 `BUG_TRIAGE.md` 和 `STATUS_REPORT.md` 時，優先確認這些方向還有哪些 claims 需要降級或補 evidence。

### 21:07 Agent 架構文件整理

- 做了什麼：
  - 對照 `ChatPanel`、`AgentManager`、`LLMController`、`AgentWorker`、`LLMConfig`、`pipeline_state`、tool registry 和 real tools。
  - 重寫 `docs/architecture/agent.md`。
- 結果：
  - agent 文件改成描述目前真實路徑：UI -> AgentManager -> LLMController -> worker / parser / verifier / tools -> BackendFacade -> Study。
  - 文件明確標出目前是可工作的中間狀態，未來目標是 UI / Agent / Script 共用 Application Service / Command API。
- 證據：
  - `docs/architecture/agent.md`
  - `docs/records/documentation_audit.md`
- 後續：
  - local LLM、RAG 品質、多步 tool-call workflow 仍要做 runtime 驗證；Gemini/API 之後不再作為產品驗證目標。

### 21:09 Assistant runtime 改為 local-only 目標

- 做了什麼：
  - 根據新的產品判斷，將未來 assistant runtime 方向改成 local-only。
  - 更新 `docs/architecture/agent.md`、`docs/decisions/README.md`、`docs/validation/README.md`。
- 結果：
  - Gemini/API 不再是未來產品驗證目標。
  - source code 目前仍保留 Gemini/API 分支，文件明確標為待簡化的 current code state。
- 證據：
  - `docs/architecture/agent.md`
  - `docs/decisions/README.md`
  - `docs/validation/README.md`
- 後續：
  - 等文件整理完成後，再把 agent runtime 簡化列入後端 / agent 重構範圍。

### 21:21 Active / architecture 文件校準

- 做了什麼：
  - 平行整理 `current.md`、`operations.md`、`ui.md`、`validation.md`。
  - 同步更新 `docs/index.md`、`docs/architecture/README.md`、`planning/roadmap.md`、`records/documentation_audit.md`。
- 結果：
  - active 入口現在清楚標示：先看 canonical 文件，使用者 review 後清 legacy，legacy 清完再審後端。
  - UI 架構文件已記錄 `MainWindow`、五個 panels、controller 取得方式、observer bridge、AgentManager、InfoPanelService。
  - validation architecture 已更新為 2026-05-01 dashboard 現況，不再停在 2026-04-19。
- 證據：
  - `docs/current.md`
  - `docs/operations.md`
  - `docs/architecture/ui.md`
  - `docs/architecture/validation.md`
  - `docs/records/documentation_audit.md`
  - `poetry run mkdocs build --strict` exit 0。
  - `git diff --check` exit 0。
- 後續：
  - 使用者 review 後開始清 legacy 文件。

### 21:27 Roadmap 加入全盤架構複盤 gate

- 做了什麼：
  - 根據使用者判斷，將清完 legacy 後的下一步改為全盤架構複盤。
  - 更新 `planning/roadmap.md`、`current.md`、`decisions/README.md`。
- 結果：
  - Roadmap 不再是 legacy 清完就直接進後端。
  - 新順序是：canonical 文件 review -> legacy 清理 -> 全盤架構複盤 -> 後端重構審視。
- 證據：
  - `docs/planning/roadmap.md`
  - `docs/current.md`
  - `docs/decisions/README.md`
- 後續：
  - 使用者 review 文件後，先清 legacy；清完再一起重新討論整體架構。

### 21:39 Docs legacy 整合後刪除

- 做了什麼：
  - 依使用者指示，改用「整合後刪除」策略，而不是保留短期 snapshot。
  - 刪除 `docs/legacy/current/`、`decisions/`、`workflows/`、`guides/`、`api/`、`thesis/`、`history/`。
  - 更新 `docs/legacy/README.md`、`mkdocs.yml`、`current.md`、`records/documentation_audit.md`、`planning/roadmap.md`。
  - 補充 test mock-heavy 判讀到 `validation/README.md` 和 `validation.md`。
- 結果：
  - `docs/legacy/` 現在只保留 `archive/` 與 legacy README。
  - test health 判讀明確區分 mock-heavy regression floor 與真正 non-mocked evidence。
- 證據：
  - `docs/legacy/README.md`
  - `docs/validation/README.md`
  - `docs/architecture/validation.md`
  - `poetry run mkdocs build --strict` exit 0。
- 後續：
  - 接著處理 `.agents/legacy/`；`docs/legacy/archive/` 先保留。

### 21:50 Agent legacy 整合後刪除

- 做了什麼：
  - 刪除 `.agents/legacy/`。
  - 更新 `AGENTS.md`、`.agents/stack.md`、`.agents/runbooks/active-queue.md`、`autopilot.md`、`setup.md`、`session-prompts.md`。
  - 同步 `current.md`、`planning/roadmap.md`、`records/documentation_audit.md`、`docs/index.md`、`architecture/README.md`。
- 結果：
  - active agent 操作層只剩少數入口：stack、runbooks、thesis context。
  - 舊 role、skill、AQ queue、workflow、multi-session prompt 不再留在 repo reading surface。
  - 下一步改成全盤架構複盤，不直接跳後端重構。
- 證據：
  - `test ! -e .agents/legacy` -> `.agents/legacy removed`
  - `poetry run mkdocs build --strict` exit 0。
  - `git diff --check -- AGENTS.md .agents README.md docs mkdocs.yml` exit 0。
- 後續：
  - 開始全盤架構複盤。

### 21:58 Docs legacy 完全收掉

- 做了什麼：
  - 刪除整個 `docs/legacy/`。
  - 從 `mkdocs.yml` 移除 Legacy nav。
  - 更新 `README.md`、`AGENTS.md`、`.agents/stack.md`、`current.md`、`planning/roadmap.md`、`records/documentation_audit.md`、`docs/index.md`、`architecture/README.md`。
- 結果：
  - repo 文件閱讀面只剩 `docs/` 與 `docs/architecture/`。
  - `docs/legacy/` 和 `.agents/legacy/` 都不再存在。
  - 下一步仍是全盤架構複盤。
- 證據：
  - `test ! -e docs/legacy` -> `docs/legacy removed`
  - `test ! -e .agents/legacy` -> `.agents/legacy removed`
  - `poetry run mkdocs build --strict` exit 0。
  - `git diff --check -- AGENTS.md .agents README.md docs mkdocs.yml` exit 0。
  - stale link scan 沒有 active nav / markdown link 指回 `docs/legacy/`。
- 後續：
  - 重新審視 canonical / architecture 文件是否還有重疊、膨脹或可信度不清的地方。

### 22:02 Active folder 收掉

- 做了什麼：
  - 將 `docs/active/*.md` 搬到 `docs/` 根層。
  - 刪除 `docs/active/README.md` 和空的 `docs/active/`。
  - 將 MkDocs nav 從 `Active` 改成 `Core`。
  - 更新 `README.md`、`AGENTS.md`、`.agents/*`、`docs/index.md`、architecture 文件與 thesis context link。
- 結果：
  - docs 只剩根層 canonical 文件與 `architecture/`。
  - 文件入口少一層，讀者不需要再理解 active / legacy 分區。
- 證據：
  - `test ! -e docs/active` -> `docs/active removed`
  - `poetry run mkdocs build --strict` exit 0。
  - `git diff --check -- AGENTS.md .agents README.md docs mkdocs.yml` exit 0。
  - stale path scan 沒有 active markdown link 指向已刪除資料夾。
- 後續：
  - 重新審視 canonical / architecture 文件是否還有重疊、膨脹或可信度不清的地方。

### 22:05 Root homepage 文件收斂

- 做了什麼：
  - 刪除 root `ROADMAP.md`。
  - 更新 `README.md`，改指向 `docs/planning/roadmap.md`。
  - 更新 `CHANGELOG.md` 開頭，標成歷史版本紀錄，不再承載 current plan。
  - 更新 `current.md` 和 `records/documentation_audit.md`。
- 結果：
  - 現在只有一份 roadmap source-of-truth：`docs/planning/roadmap.md`。
  - root homepage 不再把舊 Track A/B roadmap 當重要文件。
- 證據：
  - `test ! -e ROADMAP.md` -> root `ROADMAP.md` removed。
  - `poetry run mkdocs build --strict` exit 0。
  - `git diff --check -- README.md CHANGELOG.md planning/roadmap.md AGENTS.md .agents docs mkdocs.yml` exit 0。
- 後續：
  - 重新審視 README / docs index 是否還有多餘入口。

### 22:21 文件資訊架構第一版

- 做了什麼：
  - 將 docs 重排為 current / operations / target / architecture / planning / decisions / validation / records。
  - 寫第一版 `docs/target/`：requirements、target architecture、target agent。
  - 寫第一版 `.agents/README.md`、project context、architecture target context。
  - 寫第一版 `.agents/runbooks/architecture-review.md` 與 `refactor-gate.md`。
  - 更新 MkDocs nav、README、AGENTS、`.agents/stack.md` 和 cross-links。
- 結果：
  - 需求 / 理想架構、現況架構、短期 / 長期規劃、決策、驗證、紀錄已分開。
  - 下一步可以由使用者 review 文件架構，再進全盤架構複盤。
- 證據：
  - `poetry run mkdocs build --strict` exit 0。
  - `git diff --check -- README.md CHANGELOG.md AGENTS.md .agents docs mkdocs.yml` exit 0。
  - stale path scan 沒有 active markdown link 指向舊大寫 canonical 檔名、`docs/active/`、`docs/legacy/` 或 `validation_architecture.md`。
- 後續：
  - 使用者 review 第一版文件架構。

### 19:56 Agent 文件清理

- 做了什麼：
  - 掃描 `AGENTS.md` 和 `.agents/` 裡的舊引用。
  - 先將舊 `AQ-*` queue、role、skill、workflow、multi-session prompts 從 active agent 入口移除；當時暫存到 `.agents/legacy/`，21:50 已整合後刪除。
  - 重寫 `AGENTS.md`、`.agents/stack.md`、`.agents/runbooks/setup.md`、`.agents/runbooks/autopilot.md`、`.agents/runbooks/active-queue.md`。
- 結果：
  - active agent 入口不再指向 `docs/current/*`、`docs/history/*`、`docs/workflows/*`。
  - 舊 `Prep Gate` / `Repair Loop` / `AQ-*` 控制面不再是 current surface。
  - `.agents/context/thesis.md` 保留為 agent-facing thesis context。
- 證據：
  - `.agents/runbooks/active-queue.md`
  - `AGENTS.md`
  - active stale-reference scan 沒有發現舊路徑作為 current reading order；剩下的命中都是禁用 / 歷史說明。
  - `poetry run mkdocs build --strict` exit 0。
- 後續：
  - 後續已在 21:50 完成 `.agents/legacy/` 整合後刪除。

### Roadmap 對齊 2026-04-26 會議進度報告

- 做了什麼：
  - 讀取 `/mnt/d/workspace_v2/core/lab/meetings/progress/reports/2026-04-26.md`。
  - 以其中 `To Do List` 作為 active roadmap 的主要階段來源。
- 結果：
  - `planning/roadmap.md` 的階段路線改為：
    - GUI 重構
    - 建立新 Agent 架構
    - 後端重構
    - 穩定化
    - tool call 驗證
    - 優化迭代
  - 目前主線聚焦在後端重構與資料集測試，不提前跳到大規模 agent redesign。
- 證據：
  - 進度報告前次 TODO：繼續 XBrainLab 後端架構重構。
  - 本週延續方向：回到 XBrainLab 修後端、開始整理不同資料集。
- 後續：
  - 用 `BUG_TRIAGE.md` 驗證後端重構 claims。
  - 用 dataset matrix / pipeline smoke 整理不同資料集支援狀態。

### Roadmap 瘦身與順序修正

- 做了什麼：
  - 將 `planning/roadmap.md` 瘦身成短版。
  - 修正目前位置為 `文件整理與現況盤點`。
  - 將資料集測試併入穩定化階段，不再列成目前獨立主線。
- 結果：
  - 現在的順序是先整理文件、掌握目前狀態，再審視後端重構。
  - 資料集測試不提前拆出來，而是穩定化的一環。
- 證據：
  - `docs/planning/roadmap.md`
- 後續：
  - 下一步仍是文件整理與舊文件可信度判讀。

### Thesis context 移出 active

- 做了什麼：
  - 將 `docs/THESIS.md` 移到 `.agents/context/thesis.md`。
  - 從 active 文件清單和 MkDocs nav 移除 thesis 頁。
- 結果：
  - 人類 active 入口更乾淨，只保留目前狀態、路線、驗證、操作、決策和稽核。
  - 碩論背景改成 agent context，需要時再讀。
- 證據：
  - `.agents/context/thesis.md`
  - `docs/README.md`
  - `docs/index.md`
  - `mkdocs.yml`
- 後續：
  - thesis claim 仍要在 `validation/README.md` 裡保留邊界提醒，但不再作為 active 閱讀文件。

### 20:06 Backend 架構文件驗證

- 做了什麼：
  - 對照 `docs/architecture/backend.md` 與目前 source code。
  - 查 `facade.py`、`study.py`、`data_manager.py`、`training_manager.py`、controllers、`ui/main_window.py`、LLM real tools、pipeline state。
  - 重寫 backend 架構文件，區分 UI controller path 和 assistant/headless facade path。
- 結果：
  - 確認 `BackendFacade` 不是所有 UI workflow 的入口；UI panels 目前直接透過 `Study.get_controller(...)` 拿 controller。
  - 確認 `Study` 已拆出 `DataManager` / `TrainingManager`，但仍保留 backward-compatible delegation properties。
  - 確認 controllers 不是純薄轉接，仍含 import、preprocess copy/swap、training monitor 等 workflow logic。
- 證據：
  - `XBrainLab/ui/main_window.py`
  - `XBrainLab/backend/study.py`
  - `XBrainLab/backend/facade.py`
  - `XBrainLab/backend/controller/*.py`
  - `XBrainLab/llm/tools/real/*.py`
  - `poetry run pytest --capture=sys tests/unit/test_architecture.py -q` -> `3 passed`
  - `poetry run mkdocs build --strict` exit 0
- 後續：
  - 後端重構前，先盤點 controller 內哪些 logic 要保留在 controller，哪些應下沉到 manager / service。

### Backend 目標架構記錄

- 做了什麼：
  - 將 backend 理想方向寫入 `docs/architecture/backend.md`。
  - 使用者確認未來目標是重構成 UI / Agent / Script 共用 Application Service / Command API。
- 結果：
  - 目標方向明確化：UI、agent tools、scripts 應共用同一批 command，而不是各走一套流程。
  - `BackendFacade` 的目標角色被降成 assistant / script wrapper，而不是新的平行 backend。
- 證據：
  - `docs/architecture/backend.md`
  - `docs/decisions/README.md`
- 後續：
  - 後端重構前，先盤點 controller 裡的 workflow logic，再決定哪些抽成 service / command。

### 21:01 Data pipeline 架構文件驗證

- 做了什麼：
  - 對照 `docs/architecture/data_pipeline.md` 與目前 source code。
  - 查 `RawDataLoaderFactory`、raw loaders、`LabelImportService`、preprocessor、`Epochs`、`DatasetGenerator`、`Dataset`、`Trainer`。
  - 對照 real-data IO、checked-in GDF+MAT、public cross-source training smoke 測試。
- 結果：
  - 確認目前註冊 loader 格式是 `.set`、`.gdf`、`.fif`、`.fif.gz`、`.edf`、`.bdf`、`.cnt`、`.vhdr`。
  - 將 import、label/event、preprocess、epoch/dataset、training 分層寫清楚。
  - 明確區分 import evidence、dataset generation evidence、training smoke、thesis-grade reproducibility。
- 證據：
  - `XBrainLab/backend/load_data/raw_data_loader.py`
  - `XBrainLab/backend/services/label_import_service.py`
  - `XBrainLab/backend/dataset/epochs.py`
  - `XBrainLab/backend/dataset/dataset_generator.py`
  - `tests/integration/io/test_io_integration.py`
  - `tests/integration/pipeline/test_checked_in_real_dataset_validation.py`
  - `tests/integration/pipeline/test_public_cross_source_training_smoke.py`
  - `poetry run mkdocs build --strict` exit 0
  - `poetry run pytest --capture=sys tests/integration/io/test_io_integration.py -q` -> `31 passed, 8 warnings`
  - tiny pipeline smoke -> `2 passed in 5.89s`
- 後續：
  - 下一份 architecture 文件建議清 `agent.md`，因為它會影響未來 tool-call validation 與 Application Service 目標。

### 2026-05-02 Product delivery UI / agent / validation slice

- 做了什麼：
  - 將 AI Assistant header、status chips、available next steps、persona/runtime/mode labels、
    empty state、message bubbles 和 composer 改成使用者導向語言。
  - 第一層 UI 不再顯示 raw command names；advanced command diagnostics 留在 tooltip / details。
  - 修正 user bubble right margin / word wrap，避免最後一個字被截掉。
  - 新增 `XBrainLab/ui/product_language.py`，集中 stage / command / status 的產品文字。
  - 新增 UI command adapter，讓 dataset import、reset、preprocess、epoching、training
    start / stop 優先走 `ApplicationService.execute()`，mock / legacy path 保留 controller fallback。
  - agent mapped workflow tools 優先直接執行 ApplicationService command，回傳 structured
    `CommandResult` payload；`load_data` / `set_montage` / `switch_panel` 仍保留 legacy / UI request path。
  - 新增 product UI integration smoke，覆蓋 assistant click-through layout 和 synthetic EEG
    button-driven pipeline walkthrough。
  - 更新 current / planning / architecture / validation 文件，誠實標出剩餘 release risk。
- 證據：
  - `timeout 240s scripts/dev/run_ui_pytest.sh tests/unit/ui/chat/test_chat_panel.py tests/unit/ui/chat/test_message_bubble.py tests/unit/ui/components/test_agent_manager.py tests/unit/ui/test_agent_manager_coverage.py -q` -> `78 passed`
  - `timeout 240s scripts/dev/run_ui_pytest.sh tests/unit/ui/test_application_capabilities.py tests/unit/ui/dataset/test_panel.py tests/unit/ui/dataset/test_dataset_sidebar.py tests/unit/ui/preprocess/test_preprocess_panel.py tests/unit/ui/preprocess/test_preprocess_panel_normalize.py tests/unit/ui/training/test_training_sidebar.py tests/unit/ui/test_sidebars_and_components.py -q` -> `74 passed`
  - `timeout 180s poetry run pytest --capture=sys tests/unit/backend/application tests/integration/backend/test_application_service_workflow.py -q` -> `11 passed`
  - `timeout 180s poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/unit/llm/agent/test_controller.py -q` -> `60 passed`
  - `timeout 240s scripts/dev/run_ui_pytest.sh tests/integration/ui/test_product_walkthrough.py -q` -> `2 passed`
  - combined UI product gate -> `62 passed`
  - combined agent / backend gate -> `95 passed`
  - IO integration -> `31 passed, 8 warnings`
  - selected pipeline smoke -> `2 passed`
  - launcher startup smoke printed `MainWindow initialized` before expected GUI timeout.
- commits:
  - `941efaf ui: polish assistant product language`
  - `e52687a backend: align ui command adapter slice`
  - `34816c7 agent: execute mapped tools via command results`
  - `5ede90e validation: add product walkthrough smoke`
- push status:
  - each `git push origin HEAD` failed because GitHub credentials were unavailable in this environment:
    `fatal: could not read Username for 'https://github.com': No such device or address`
- 後續：
  - 完成剩餘 service-first UI action migration：label import、smart parse、channel selection、
    split / model / training setting dialogs、evaluation / visualization query actions。
  - 做 Windows Desktop launcher 人工 click-through 與 true local model UI walkthrough。
  - 將 `evaluate` / `visualize` / `saliency` / `new_session` 從 future placeholder 推進成真 command。

### 2026-05-02 Assistant runtime consent / query commands / thesis protocol closure

- 做了什麼：
  - ChatPanel 主視覺改成使用者語言：自然語言 workflow state、next step、Options；persona、
    runtime、single/auto mode 不再佔主視覺。
  - 新增 local runtime first-run consent dialog，顯示 resource notice、estimated download、
    current/projected cache、provider/license/VRAM estimate，提供 Enable / Download /
    Use existing cache / Later / Disable。
  - `ApplicationService` 實作 `evaluate`、`visualize`、`saliency`、`new_session` typed result；
    `BackendFacade.get_latest_results()` 保留舊 caller shape。
  - UI channel selection、split/model/training dialog submit、evaluation/visualization query、
    saliency setup/query 走 service command adapter，mock / legacy path 保留 fallback。
  - 新增 split audit helper、split artifact schema、validator script 和 thesis protocol 文件。
  - deterministic tool-call eval 更新 query-command 語意並刷新 `artifacts/agent_evals/latest.json`。
- 證據：
  - `poetry run ruff check XBrainLab/ tests/ scripts/dev/validate_split_artifact.py` -> pass
  - `poetry run ruff format --check XBrainLab/ tests/ scripts/dev/validate_split_artifact.py` -> pass
  - `git diff --check` -> pass
  - `poetry run mkdocs build --strict` -> pass
  - UI product gate -> `62 passed`
  - backend / split audit / config gate -> `41 passed`
  - agent / facade / backend workflow gate -> `130 passed`
  - deterministic eval refresh -> `21 / 21` cases passed
  - full test gate -> `4386 passed, 3 skipped, 3 deselected, 1 xfailed, 14 warnings`
- 後續：
  - 真 Windows launcher click-through 和 true local model UI walkthrough 尚未跑。
  - label import、smart parse、montage confirmation 仍要做 typed/service 收斂。
  - thesis protocol 已建立；external dataset runner、repeat runs、baselines、statistics 尚未完成。

### 2026-05-03 Backend Workflow Contract v2 first slice

- 做了什麼：
  - 新增 `ClearDatasetsCommand`、`ClearTrainingHistoryCommand`、`ResetPreprocessCommand`，
    補齊 command export、service handlers、capability policy 和 `BackendFacade` compatibility wrappers。
  - `GenerateDatasetCommand` 接上 split audit；empty train/validation/test 或 leakage 會回
    structured `DATA_MISMATCH` failure，不再悄悄當成功。
  - split audit failure 會 rollback dataset / generator / trainer state，避免 failure 後仍可 train。
  - `evaluate`、`visualize`、`saliency` policy 不再在 empty state 無條件可用；blocked command
    仍透過 `CommandResult` envelope 回傳。
  - `saliency` diagnostics 分出 `action=configure/query`；configure 可先保存參數，
    saliency view/readiness 仍以 finished evaluation + configured params 為準。
- 證據：
  - `poetry run ruff check XBrainLab tests` -> pass
  - `poetry run basedpyright XBrainLab/backend/application XBrainLab/backend/facade.py` -> `0 errors, 0 warnings, 0 notes`
  - `poetry run pytest tests/unit/backend/application/test_application_service.py tests/integration/backend/test_application_service_workflow.py tests/integration/ui/test_product_walkthrough.py tests/integration/pipeline/test_public_cross_source_training_smoke.py` -> `32 passed, 3 warnings`
  - `poetry run pytest tests/unit/backend/application tests/integration/backend tests/integration/pipeline` -> `95 passed, 4 warnings`
  - `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`
- 後續：
  - 這只是 Backend Workflow Contract v2 + Evidence-Ready Pipeline 的第一個可交付切片，
    不是終局。
  - UI service-first migration 還有 remaining UI bypass，需要逐步接到 command layer。
  - thesis evidence 還需要 external dataset runner、repeat runs、baseline/statistics 和 artifact
    emission policy。

### 2026-05-03 Assistant UI single-toolbar correction

- 做了什麼：
  - 移除 chat panel 內可見 `Conversation` header、composer 底下狀態列、第二個 options menu
    和未完成的 Assistant mode / Step behavior controls。
  - dock title bar 成為唯一第一層功能列：`XBrainLab`、retry icon、new conversation、
    settings menu、float/dock；`Clear conversation` 收進 settings menu。
  - `AgentManager` 攔截 tool/debug sender 或 internal tool syntax，visible transcript 不再顯示
    `Tool list_files completed...`、schema error、`ApplicationService` / `BackendFacade`。
  - short bubble minimum width 降低，避免 `hello` 形成過大的框，同時保留窄 dock 可讀性。
- 證據：
  - `poetry run ruff check XBrainLab/ui/chat XBrainLab/ui/components/agent_manager.py tests/unit/ui/chat tests/integration/ui/test_product_walkthrough.py` -> pass
  - `poetry run pytest --capture=sys tests/unit/ui/chat tests/integration/ui/test_product_walkthrough.py -q` -> `50 passed`
  - combined assistant UI + backend workflow contract gate -> `80 passed, 3 warnings`
  - `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`
