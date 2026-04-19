# XBrainLab Bug Triage

這份文件是目前 PyQt 應用穩定化工作的即時問題收集面。

它的用途是避免 bug 修復工作變成沒有結構的混亂累積。

## Triage 原則

- 先描述使用者可見的問題
- 把重現事實和推測拆開
- 先記錄影響，再談解法
- 明確分類這是 UI、workflow 還是 structural 問題
- 只要可行，就優先留下窄而清楚的 failing test 或 observable signal

## 優先級

### P0

程式無法啟動、資料可能損壞，或多數使用者的核心 workflow 被阻塞。

### P1

重要 panel 或 dialog 不可靠、會誤導，或功能上已經壞掉。

### P2

某條 workflow 品質下降但仍有 workaround，或問題是局部且不具破壞性。

### P3

低影響的 polish 問題、非關鍵排版不一致，或沒有緊急使用者故障的維護債。

## 問題模板

每個新確認的問題都用這個格式記錄：

```md
## [BUG-XXX] 短標題

- Priority:
- Area:
- Type:
- Status:
- Source:

### 症狀

### 重現方式

### 預期

### 實際情況

### 影響

### 可能範圍

### 證據

### 測試覆蓋

### 備註
```

## 分類方式

### Area

- Startup
- Dataset
- Preprocess
- Training
- Evaluation
- Visualization
- Agent
- Shared UI
- Backend integration
- Test infrastructure

### Type

- Crash
- Incorrect state
- Broken interaction
- Data sync issue
- Rendering/layout
- Performance
- Architecture/coupling
- Missing observability

### Status

- New
- Confirmed
- In progress
- Blocked
- Fixed
- Needs verification

### Source

- User report
- Manual exploration
- Test failure
- Runtime log
- Code review

## 初始問題列

這個區塊會隨著接手與穩定化工作持續補充。

### 已確認的環境層問題

#### [BUG-ENV-001] Visualization redesign suite coverage 曾被過期 headless skip 隱藏

- Priority: P2
- Area: Visualization
- Type: Test infrastructure
- Status: Fixed
- Source: Test failure/skips

### 症狀

當時的 visualization redesign suite 在 headless pytest 路徑中被 class-level `@unittest.skip(...)` 整段遮住，讓過期 patch target、缺少 Qt harness、以及 stale API/test drift 都被一條舊的 VTK/Qt skip reason 一起蓋住。

### 重現方式

修正前執行：

```bash
/home/administrator/.local/bin/poetry run pytest tests/unit/ui -q
```

### 預期

Visualization redesign suite 應該要嘛穩定可跑，要嘛因為仍然成立的限制而被窄而誠實地隔離；skip reason 不應掩蓋其實已可直接修復的測試漂移問題。

### 實際情況

修正前 repo 內可直接觀察到的狀態是：

- `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_visualization.py -q`
  - 結果：`14 passed`
  - `TestSaliency3DEngine` 的過期硬編碼 skip 已退休，engine-basics slice 能在正常 pytest 路徑中跑綠
- `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_visualization_panel_redesign.py -q`
  - 結果：`9 skipped`
  - redesign suite 仍被 class-level `@unittest.skip("Segfaults in headless environment due to VTK/Qt interaction")` 整段跳過
- 最新 no-skip 對照顯示，這個 skip reason 已不再能準確描述真正的 failure surface：
  - 去掉 class-level skip 的 temp copy 先是 `9 failed`，全部卡在過期 patch target `XBrainLab.ui.panels.visualization.panel.AggregateInfoPanel`
  - 補上 patch target 後，還會先撞到缺少 `QApplication` harness
  - 再補上最小 Qt harness 後，主因則是 stale API/test drift，而不是先重現一條獨立的 VTK/Qt segfault path
- 這代表實際缺口不是「不要碰 VTK」，而是被舊 skip 蓋住的 stale coverage surface。

### 影響

這會降低我們對 visualization 相關修改的信心，也代表 redesign 相關 regression 可能被一條過期 skip reason 蓋住，看起來像是「先不要碰 VTK」，實際上卻同時隱藏了多個已可重現的測試基礎設施問題。

### 可能範圍

- `tests/unit/ui/test_visualization_panel_redesign.py`
- `XBrainLab/ui/panels/visualization/panel.py`
- `XBrainLab/ui/panels/visualization/control_sidebar.py`
- visualization widgets and VTK/PyVista integration

### 證據

於 `2026-04-19` 先確認舊 surface，再完成修復：

- `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh /tmp/test_visualization_panel_redesign_noskip.py -q`
  - 結果：`9 failed`
  - 第一層 failure 全都集中在過期 patch target `XBrainLab.ui.panels.visualization.panel.AggregateInfoPanel`
- `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh /tmp/test_visualization_panel_redesign_noskip_patchfix.py -q`
  - 結果：process `Aborted`
  - traceback 停在 `self.MockAggregateInfoPanel.return_value = QWidget()`，顯示這份 unittest file 在 no-skip 路徑下連基本 Qt app harness 都還沒補齊
- `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh /tmp/test_visualization_panel_redesign_noskip_qapp.py -q`
  - 結果：`8 failed, 1 passed`
  - 具體失敗面是 stale API/test drift：`plot_3d_head.os` patch target 無效、`refresh_data` / `btn_montage` / `plot_layout` 不存在、combo population 假設已過期、以及 topomap `plt.close` 行為預期不再相符
- 完成 AQ-005 後：
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_visualization_panel_redesign.py -q`
    - 結果：`6 passed`
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_visualization_panel_coverage.py -q`
    - 結果：`20 passed`
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui -q`
    - 結果：`782 passed, 3 skipped, 1 warning`
  - 剩餘三個 skip 位於 `tests/unit/ui/test_main_window.py` 與 `tests/unit/ui/test_workflow.py`，不再屬於這條 redesign-suite coverage bug

### 測試覆蓋

這條 coverage surface 已恢復可見：

- `tests/unit/ui/test_visualization_panel_redesign.py`
- `tests/unit/ui/test_visualization_panel_coverage.py`
- `tests/unit/ui -q` shared regression sweep

### 備註

這條 bug 現在可視為已修復的測試基礎設施問題：

- `TestSaliency3DEngine` 的過期 skip 已退休
- redesign suite 的 collection-time 汙染已被隔離
- 整份 `tests/unit/ui/test_visualization_panel_redesign.py` 已改寫成 headless-safe、現行架構對齊的 regression suite
- 剩餘 visualization skip surface 已縮到其他檔案中的三個既有 skip，應另立後續風險而不是繼續算在這條 bug 上

#### [BUG-ENV-002] Baseline screenshot capture 曾產生全黑圖片

- Priority: P1
- Area: Test infrastructure
- Type: Missing observability
- Status: Fixed
- Source: Manual exploration

### 症狀

當時的 baseline capture helper 雖然能寫出圖片檔，但內容幾乎全黑，因此無法作為 UI 檢視依據。

### 重現方式

執行：

```bash
xvfb-run -a /home/administrator/.local/bin/poetry run python scripts/dev/capture_ui_baseline.py
```

接著檢查：

```text
artifacts/ui/main-window-initial.png
```

### 預期

存下來的截圖應該能清楚顯示 XBrainLab 主視窗，足以判斷 layout 結構。

### 實際情況

圖片檔雖然建立了，但捕捉到的內容是黑的。

### 影響

這會阻斷可信的 visual baseline capture，也削弱我們非同步檢查 UI layout 變化的能力。

### 可能範圍

- `scripts/dev/capture_ui_baseline.py`
- `xvfb-run` screenshot timing or window targeting
- display/render synchronization under headless capture

### 證據

在 `2026-04-18` 本地產生 `artifacts/ui/main-window-initial.png` 後觀察到此問題。

已於 `2026-04-19` 修復並重新驗證：

```bash
xvfb-run -a /home/administrator/.local/bin/poetry run python scripts/dev/capture_ui_baseline.py
```

### 測試覆蓋

- `tests/unit/scripts/test_capture_ui_baseline.py`
- runtime validation of `artifacts/ui/main-window-initial.png`

### 備註

現在 helper 已改成直接捕捉已渲染的 Qt main window，因此 baseline artifact 已恢復可用。剩餘追蹤是繼續把 baseline coverage 從初始 shell 擴大出去。

#### [BUG-ENV-003] 目前 `/mnt/d` Codex workspace 的預設 pytest capture 仍會間歇性失敗

- Priority: P1
- Area: Test infrastructure
- Type: Broken interaction
- Status: Needs verification
- Source: Manual exploration

### 症狀

在目前 `/mnt/d/repos/XBrainLab` 的 Codex workspace 中，pytest 預設 capture mode 仍會在 teardown 階段於 `_pytest/capture.py` 內拋出 `FileNotFoundError`，只是重現並不是每條 slice 都一樣穩定。

### 重現方式

執行：

```bash
/home/administrator/.local/bin/poetry run pytest tests/unit/backend/training/test_option.py -q
```

### 預期

測試應該在專案預設 pytest 設定下正常完成。

### 實際情況

Pytest 先顯示 `no tests ran`，接著在解除 global capture 設定時失敗：

```text
FileNotFoundError: [Errno 2] No such file or directory
```

同樣的 targeted slice 若改用 `--capture=sys`、`--capture=tee-sys` 或 `-s` 重跑，則可成功。

### 影響

如果它再次穩定出現，會讓目前 workspace 中的預設快速驗證指令不再可靠，尤其不利於 unattended local work，也會削弱對自動化循環的信心，因為那些流程通常假設 pytest capture 能正常運作。

### 可能範圍

- current `/mnt/d/repos/XBrainLab` Codex desktop workspace
- `pytest` default capture teardown
- local temp-file or mount-path interaction under WSL/Codex local execution

### 證據

於 `2026-04-19` 本地先前確認：

- 失敗指令：
  `/home/administrator/.local/bin/poetry run pytest tests/unit/backend/training/test_option.py -q`
- 可通過的 `sys` capture workaround：
  `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/unit/backend/training/test_option.py -q`
- 可通過的 `tee-sys` 驗證：
  `/home/administrator/.local/bin/poetry run pytest --capture=tee-sys tests/unit/backend/training/test_option.py -q`
- 可通過的 fallback：
  `/home/administrator/.local/bin/poetry run pytest -s tests/unit/backend/training/test_option.py -q`

### 測試覆蓋

targeted slice 本身仍有 coverage，但這條問題的重現具有 slice-sensitive 特性，因此需要把 evidence 一起記清楚。

### 備註

目前已將問題縮小到 `fd` capture，而不是 pytest collection 整體壞掉。

`2026-04-19` 的代表性確認如下：

- `--capture=sys` 可通過：
  - `tests/unit/backend/training/test_option.py`
  - `tests/unit/ui/test_main_window_sync.py`
  - `tests/integration/ui/test_dialog_acceptance.py`
- 最新 recheck 中，以下預設 capture 指令也已通過：
  - `/home/administrator/.local/bin/poetry run pytest tests/unit/backend/training/test_option.py -q`
  - `/home/administrator/.local/bin/poetry run pytest tests/integration/io/test_io_integration.py -q`
- 但在新的 quality dashboard refresh 中，若仍沿用預設 capture 指令也會再次失敗：
  - `/home/administrator/.local/bin/poetry run pytest tests/integration/io/test_io_integration.py -q`
  - 結果：在 `_pytest/capture.py` teardown 階段再次拋出 `FileNotFoundError`
- 但最新 recheck 已不再穩定重現：
  - `/home/administrator/.local/bin/poetry run pytest tests/integration/io/test_io_integration.py -q`
  - 結果：`30 passed, 12 warnings`
  - 同一條完整指令在同一 workspace 連跑 `3` 次也都通過：
    - `RUN=1` -> `30 passed, 12 warnings`
    - `RUN=2` -> `30 passed, 12 warnings`
    - `RUN=3` -> `30 passed, 12 warnings`
- 同樣地，`tests/unit/scripts/test_update_quality_dashboard.py -q` 也再次踩中同一條 capture teardown 問題
- 之後已把 accepted workaround 升級成正式 dashboard command：
  - `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/integration/io/test_io_integration.py -q`
  - `2026-04-19 16:16:52 UTC+08:00` 的 fast dashboard refresh 以此路徑通過：`31 passed, 13 warnings`

目前這條訊號更接近「曾明確出現過、但目前尚未能穩定再現」的 flaky capture issue，而不是當前每次都會重現的 blocker。
在這個 workspace 裡，`--capture=sys` 現在已不只是 local workaround，也已升級成 dashboard / heartbeat 的 accepted command；`-s` 只保留作為 fallback，直到新的穩定重現條件被找出來。

#### [BUG-ENV-004] unattended UI pytest 在目前 Codex workspace 需要顯式 offscreen Qt 環境

- Priority: P1
- Area: Test infrastructure
- Type: Broken interaction
- Status: Confirmed
- Source: Manual exploration

### 症狀

在目前 `/mnt/d/repos/XBrainLab` 的 Codex workspace 中，UI pytest slice 若直接走一般命令路徑，可能會在 `pytest-qt` 的 `qapp` fixture 初始化時直接 abort，而不是進入測試本體。

### 重現方式

執行：

```bash
xvfb-run -a /home/administrator/.local/bin/poetry run pytest tests/integration/ui/test_dialog_acceptance.py -q
```

### 預期

同一條 UI slice 應該要能在 unattended / heartbeat 路徑中穩定啟動 Qt 並完成測試。

### 實際情況

Qt 會在啟動時嘗試載入 `wayland` 或 `xcb` plugin，接著在 `pytestqt.plugin.qapp` 階段 abort；同時 matplotlib 也會抱怨預設 cache 目錄不可寫。

### 影響

這會讓 heartbeat 與 unattended UI 驗證看起來像是 repo 測試壞掉，但實際上是執行環境沒有先把 Qt 與 matplotlib 設成適合本地 Codex workspace 的 headless 模式。

### 可能範圍

- current `/mnt/d/repos/XBrainLab` Codex desktop workspace
- `pytest-qt` `qapp` startup
- Qt platform plugin resolution (`offscreen` vs `xcb` / `wayland`)
- matplotlib cache path in unattended local runs

### 證據

於 `2026-04-19` 本地確認：

- 失敗指令：
  - `xvfb-run -a /home/administrator/.local/bin/poetry run pytest tests/integration/ui/test_dialog_acceptance.py -q`
- 可通過的 workaround：
  - `MPLCONFIGDIR=/tmp/matplotlib-codex QT_QPA_PLATFORM=offscreen /home/administrator/.local/bin/poetry run pytest --capture=sys tests/integration/ui/test_dialog_acceptance.py -q`
  - 結果：`4 passed`
  - `QT_QPA_PLATFORM=offscreen MPLCONFIGDIR=/tmp/matplotlib-codex /home/administrator/.local/bin/poetry run python scripts/dev/run_tests.py ui`
  - 結果：`742 passed, 15 skipped, 1 warning`

### 測試覆蓋

目前已新增 repo-local helper：

- `scripts/dev/run_ui_pytest.sh`
- `scripts/dev/run_tests.py` 的 `ui` 路徑也已套用同一組環境前置

它會套用：

- `QT_QPA_PLATFORM=offscreen`
- `MPLBACKEND=Agg`
- `MPLCONFIGDIR=/tmp/matplotlib-codex`
- `--capture=sys`

### 備註

這條問題比 `BUG-ENV-003` 更接近目前 heartbeat 自動化的真實 blocker，因為它穩定影響 unattended UI pytest，而不是只影響早期那個已變得不穩定的 capture teardown 訊號。

#### [BUG-ENV-005] 品質看板的 fast static gates 曾是紅燈

- Priority: P2
- Area: Test infrastructure
- Type: Architecture/coupling
- Status: Fixed
- Source: Test failure

### 症狀

在把 static quality gates 納入品質看板後，dashboard 不只回報 runtime signal，也開始如實顯示 repo 既有的靜態品質債。
目前策略已改成 two-speed：

- 預設 dashboard 跑 `ruff`、baseline-backed `basedpyright`、`architecture compliance`
- `mypy` 保留在 slower full gate，專門持續暴露舊債而不是淹沒每輪高頻回饋

### 重現方式

執行：

```bash
/home/administrator/.local/bin/poetry run python scripts/dev/update_quality_dashboard.py
```

或分別執行：

```bash
/home/administrator/.local/bin/poetry run ruff check .
/home/administrator/.local/bin/poetry run basedpyright
/home/administrator/.local/bin/poetry run mypy XBrainLab/
/home/administrator/.local/bin/poetry run python tests/architecture_compliance.py
```

### 預期

品質看板應該同時做到兩件事：

- 高頻模式能清楚抓出新的靜態回歸
- 較慢的 full mode 仍能持續提醒我們清掉既有靜態品質債

### 實際情況

- `ruff check .` 與 `basedpyright` 目前都已回到綠燈
- `mypy XBrainLab/` 目前仍回報 `7 errors in 5 files`
- `python tests/architecture_compliance.py` 通過
- `2026-04-19 16:16:52 UTC+08:00` 的 fast dashboard refresh 目前整體為 `PASS`

### 影響

這代表 quality dashboard 雖然比較完整，但靜態品質債現在需要用兩種節奏處理：

- fast gate 保護日常開發不再引進新的型別回歸
- full gate 仍會持續把舊的 `mypy` 問題留在視野內，直到它們被拆解和修掉

### 可能範圍

- repo-wide import ordering / line-length / minor lint debt
- selected type-safety issues in:
  - `XBrainLab/ui/core/observer_bridge.py`
  - `XBrainLab/ui/panels/visualization/saliency_views/base_saliency_view.py`
  - `XBrainLab/llm/agent/worker.py`
  - `XBrainLab/backend/load_data/raw_data_loader.py`
  - `XBrainLab/ui/panels/dataset/actions.py`

### 證據

於 `2026-04-19` 本地觀察到：

- 先前 blocker evidence：
  - `ruff check .` -> `FAIL` (`22 errors`)
  - `basedpyright` -> `PASS` (`0 errors, 0 warnings, 0 notes`)
- 最新 closure evidence：
  - `ruff check .` -> `PASS`
  - `basedpyright` -> `PASS` (`0 errors, 0 warnings, 0 notes`)
  - `python tests/architecture_compliance.py` -> `PASS`
  - `python scripts/dev/update_quality_dashboard.py` -> fast dashboard `PASS`
- `mypy XBrainLab/` 仍是 slower full gate 的 monitored debt

### 測試覆蓋

目前不是 runtime test 缺失，而是 static gate 已被接到 dashboard 並可穩定重現。

### 備註

這不是 dashboard 額外製造的新 regression，比較接近是原本就存在的品質債終於被正式納入可見 gate。
需要注意的是：`.basedpyright/baseline.json` 不是豁免清單，而是讓高頻 gate 有可操作價值的暫時 debt ledger。

Prep-exit decision：

- `BUG-ENV-005` 不應被當成一整包模糊的「品質債」。
- fast static gate 這個類別本身屬於 prep-exit blocker，因為 prep gate 需要可信的高頻驗證指令。
- 這輪 closure 後，快檢查紅燈已經清掉：`ruff`、`basedpyright`、architecture compliance 與 fast dashboard 都回到綠燈。
- slower `mypy` debt 則維持 monitored debt；它必須持續被 full gate 看見，但不單獨阻止 `Repair Loop` 啟用。

#### [BUG-AGENT-001] AI assistant 的 local startup 忽略已儲存設定，並把 local runtime failure 延後到初始化時才暴露

- Priority: P1
- Area: Agent
- Type: Broken interaction
- Status: In progress
- Source: Runtime log

### 症狀

打開 AI assistant 時，dock 可能先被打開，接著才在 backend startup 階段失敗，因為第一次初始化路徑會預設走 local mode，而且要等 backend load 已開始後，才發現缺少 local runtime 套件。

### 重現方式

先前會沿著下列 prep-baseline command 進到 local startup：

```bash
xvfb-run -a /home/administrator/.local/bin/poetry run pytest -s tests/integration/ui/test_e2e_qtbot.py -q
```

但這條路徑現在不再是當前 accepted repro，因為 `TestAIAssistantDock.test_toggle_ai_dock` 已改成在 prep baseline 中 stub `AgentManager.start_system()`，只驗證 shell-open / dock visibility，不再直接帶起 local backend。

### 預期

打開 AI assistant 時應該尊重已儲存的 startup mode；而依目前 local-only 方向，應該在真正嘗試 local backend load 之前，就先以清楚的 preflight 訊息快速失敗。

### 實際情況

先前 dock toggle 路徑會進到 local-model startup，並記錄：

```text
Model Load Error: ... requires `accelerate`
```

在 `2026-04-19` 的 prep recheck 中，沿用 queue 舊記錄的 exact command 重新執行時，流程再次走進 local startup，記錄了 `Initializing LLM Engine...`、`Switching backend to: local`、`Loading local model: Qwen/Qwen2.5-7B-Instruct on cpu`、`Loading checkpoint shards`，並把 host 拖到不安全狀態，導致該次 rerun 被放棄。這條風險之後已從 Prep Gate baseline 中分離出去：同日 `tests/integration/ui/test_e2e_qtbot.py` 的 AI dock toggle case 改成只驗證 shell-open，不再直接初始化 backend。

### 影響

AI assistant 在 shell 上看起來像是可用的，但底層 agent backend 其實無法使用，這會讓 panel 對手動使用和自動 baseline 檢查都顯得誤導且脆弱。

### 可能範圍

- `XBrainLab/ui/components/agent_manager.py`
- `XBrainLab/ui/chat/panel.py`
- `XBrainLab/ui/dialogs/model_settings_dialog.py`
- `XBrainLab/llm/agent/worker.py`
- `XBrainLab/llm/core/config.py`
- `XBrainLab/llm/core/backends/local.py`
- AI assistant stack 的 local dependency / readiness 檢查與 saved-config sync

### 證據

於 `2026-04-19` 本地觀察到：

- `xvfb-run -a /home/administrator/.local/bin/poetry run pytest -s tests/integration/ui/test_e2e_qtbot.py -q`

這個 slice 最後是 `20 passed`，但 log 同時出現：

```text
ValueError: ... requires `accelerate`
```

並於 `2026-04-19` 經以下驗證後確認有改善：

- `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/unit/llm/core/test_config.py tests/unit/llm/agent/test_worker.py -q`
- `xvfb-run -a /home/administrator/.local/bin/poetry run pytest --capture=sys tests/unit/ui/chat/test_chat_panel.py tests/unit/ui/dialogs/test_model_settings.py -q`
- `xvfb-run -a /home/administrator/.local/bin/poetry run pytest --capture=sys tests/integration/ui/test_e2e_qtbot.py -q`
- `2026-04-19` prep recheck:
  - `xvfb-run -a /home/administrator/.local/bin/poetry run pytest -s tests/integration/ui/test_e2e_qtbot.py -q`
  - partial log reached:
    - `Initializing LLM Engine...`
    - `Switching backend to: local`
    - `Loading local model: Qwen/Qwen2.5-7B-Instruct on cpu`
    - `Loading checkpoint shards`
  - the rerun then had to be abandoned because it made the host unresponsive, so this exact command should no longer be treated as safe prep-exit evidence
- `2026-04-19` host-safe shell-baseline split:
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/integration/ui/test_e2e_qtbot.py -q`
  - 結果：`20 passed`
  - `TestAIAssistantDock.test_toggle_ai_dock` now stubs `AgentManager.start_system()` so Prep Gate can validate AI shell-open behavior without invoking local-model bootstrap

### 測試覆蓋

- `tests/integration/ui/test_e2e_qtbot.py`
- `tests/unit/llm/core/test_config.py`
- `tests/unit/llm/agent/test_worker.py`
- `tests/unit/ui/chat/test_chat_panel.py`
- `tests/unit/ui/dialogs/test_model_settings.py`

補充：

- `tests/integration/ui/test_e2e_qtbot.py` 現在只承擔 Prep Gate 的 shell-level workflow baseline，不再作為這條 local-startup bug 的直接重現路徑
- 這條 bug 後續需要 dedicated local-startup validation，而不是再次借用 top-level workflow baseline

### 備註

這現在已是確認過的 AI shell / runtime 問題。使用者也已明確同意必要時可對 AI assistant panel 做有意識的重設計，而目前方向是 local-only startup，不再依賴 Gemini fallback。

`2026-04-19` 補充 triage 發現：

- `pyproject.toml` already declares `accelerate`, but only inside the optional Poetry `llm` group
- that means the current failure is likely a mismatch between the active local environment and the UI's assumption that local-model startup is ready
- the first-start bug also included a config-sync problem: `AgentWorker.initialize_agent()` was ignoring saved settings and constructing a fresh default `LLMConfig()`
- the current fix surface therefore includes persisted-config sync plus preflight checks before the AI dock presents local inference as usable

最新 patch 後的現況：

- the worker now loads persisted settings before first initialization
- the local startup path now fails fast with a clearer preflight message when optional `llm` packages are missing
- the chat menu and settings dialog now surface local-runtime unavailability earlier instead of deferring it to worker startup
- the local backend now probes CUDA usability and falls back to CPU while disabling 4-bit loading if the host GPU cannot actually execute PyTorch work
- 這個 workspace 現已安裝可選的 Poetry `llm` 套件，因此下一個具體 blocker 是缺少 local model cache，以及 end-to-end local bootstrap validation
- 這也代表 `BUG-AGENT-001` 仍是有效的 local-startup bug，但它現在不再阻止 Prep Gate 的 shell baseline；目前更聚焦的剩餘 blocker 是缺少 local model cache，以及 dedicated local bootstrap validation
- `AQ-006` 另行修掉了 user-facing silent remote fallback / remote-menu honesty 問題，該部分現在轉到已固定的 `BUG-AGENT-002`

`2026-04-19` 的額外環境收斂：

- `/home/administrator/.local/bin/poetry install --with llm --no-interaction` now succeeds in the current workspace
- `LLMConfig.missing_local_runtime_packages()` now returns `[]`
- `/home/administrator/.local/bin/poetry run python - <<'PY' ... LLMConfig.load_from_file() ... PY`
  - 結果：
    - `startup_mode local`
    - `model_name Qwen/Qwen2.5-7B-Instruct`
    - `cache_root_exists True`
    - `cache_candidate_exists False`
- the host still reports `torch.cuda.is_available() == True`, but a direct CUDA probe fails with `RuntimeError: CUDA error: no kernel image is available for execution on the device`
- 這個 workspace 裡預期的 `Qwen/Qwen2.5-7B-Instruct` local model cache path 仍不存在

#### [BUG-AGENT-002] AI shell 曾把 remote Gemini 當成隱性 fallback 或等價主選項暴露給使用者

- Priority: P1
- Area: Agent
- Type: Broken interaction
- Status: Fixed
- Source: Manual exploration

### 症狀

修正前，user-facing AI shell 仍把 Gemini remote mode 當成一條太容易誤觸的 fallback path：

- 刪除目前正在使用中的 local model 時，流程會默默把 assistant 切去 Gemini
- chat model menu 也會把 Gemini 暴露成看起來和 local mode 等價的選項，而不是一個明確標示為 remote 的次要路徑

### 重現方式

修正前可從這幾條 UI slice 觀察到：

```bash
/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/components/test_agent_manager.py tests/unit/ui/test_agent_manager_coverage.py tests/unit/ui/chat/test_chat_panel.py tests/unit/ui/dialogs/test_model_settings.py tests/unit/ui/test_ui_misc.py -q
```

### 預期

在 local-first 方向下，user-facing shell 應該：

- 對 active local model deletion fail closed，而不是默默切成 remote
- 只有在 remote mode 明確可用時才顯示 Gemini，而且應清楚標示它是 remote 路徑

### 實際情況

修正前的 `AgentManager.prepare_model_deletion()` 會在 local model 還活躍時自動切去 Gemini；`ModelSettingsDialog` 也會沿著這個路徑繼續刪除。`ChatPanel` 的 model menu 則沒有把 Gemini 清楚降級成次要 remote affordance。

### 影響

這會讓 local-only 方向變得不誠實：使用者以為自己仍在 local-first flow 裡，實際上 UI 已默默幫他切去 remote mode，或把 remote surface 包裝成正常主路徑的一部分。

### 可能範圍

- `XBrainLab/ui/components/agent_manager.py`
- `XBrainLab/ui/dialogs/model_settings_dialog.py`
- `XBrainLab/ui/chat/panel.py`

### 證據

於 `2026-04-19` 完成 AQ-006 後再次驗證：

- `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/components/test_agent_manager.py tests/unit/ui/test_agent_manager_coverage.py tests/unit/ui/chat/test_chat_panel.py tests/unit/ui/dialogs/test_model_settings.py tests/unit/ui/test_ui_misc.py -q`
  - 結果：`191 passed`
- `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui -q`
  - 結果：`782 passed, 3 skipped, 1 warning`

### 測試覆蓋

- `tests/unit/ui/components/test_agent_manager.py`
- `tests/unit/ui/test_agent_manager_coverage.py`
- `tests/unit/ui/chat/test_chat_panel.py`
- `tests/unit/ui/dialogs/test_model_settings.py`
- `tests/unit/ui/test_ui_misc.py`

### 備註

目前最小修復面已完成：

- `AgentManager.prepare_model_deletion()` 在 local model 仍活躍時會直接阻擋刪除
- `ModelSettingsDialog` 會尊重這個 failed precondition
- `ChatPanel` 會把 `Local` 維持為主路徑，只在明確啟用時才顯示 `Gemini (Remote)`

這條 bug 修掉後，`BUG-AGENT-001` 可以更專注在 local bootstrap readiness 本身，而不是混著 user-facing remote fallback confusion。

#### [BUG-DATASET-001] Sequence label import 曾假設 label code 只能是數字

- Priority: P1
- Area: Dataset
- Type: Broken interaction
- Status: Fixed
- Source: Code review

### 症狀

當 sequence-style labels 來自 CSV / TSV，且 label 值是類別字串而不是整數時，匯入流程可能會失敗。

### 重現方式

修復前，像這樣的 sequence label flow 會失敗：

```python
loader.label_list = ["left", "right"]
loader.create_event({"left": "Left", "right": "Right"})
```

dialog 路徑在讀取 mapping row 時也會直接做 `int(code_text)`。

### 預期

字串型或類別型 sequence labels 應該能一路通過 mapping dialog，並在真正套用到 MNE events 時再轉成穩定的整數 event ID。

### 實際情況

UI 和 backend 都假設 label code 必須是數字，導致 `ValueError` 或直接無法抽取 mapping。

### 影響

這會讓外部 label import 看起來像是 dataset-specific 的問題，但實際上底層只是類別型 label 格式沒被正確支援。

### 可能範圍

- `XBrainLab/ui/dialogs/dataset/import_label_dialog.py`
- `XBrainLab/backend/load_data/event_loader.py`
- `XBrainLab/backend/services/label_import_service.py`

### 證據

於 `2026-04-18` 本地觀察到：修復前 `EventLoader.create_event()` 會對字串 sequence label 拋出 `ValueError: invalid literal for int() with base 10: 'left'`。

### 測試覆蓋

- `tests/unit/ui/dataset/test_import_label.py`
- `tests/unit/backend/load_data/test_event_loader_strict.py`
- `tests/unit/ui/test_ui_misc.py`

### 備註

修復後的路徑已支援類別字串 labels，也會保留像 `"769"` 這種帶引號數字字串的原始 event code。

#### [BUG-DATASET-002] Label import 曾只用 basename 當作檔案 key

- Priority: P1
- Area: Dataset
- Type: Data sync issue
- Status: Fixed
- Source: Code review

### 症狀

若從不同資料夾匯入兩個同名 label 檔，mapping 之前就可能默默掉其中一個。

### 重現方式

修復前，在 label import dialog 同時選這兩個檔案時，第二個會被當成 duplicate：

```text
/tmp/sub01/labels.txt
/tmp/sub02/labels.txt
```

### 預期

label 檔應該用完整路徑追蹤，讓不同資料夾裡的同名檔能同時存在並正確 mapping。

### 實際情況

`ImportLabelDialog` 用 `os.path.basename(path)` 當 storage key，因此最後只能保留一個 `labels.txt`。

### 影響

這會破壞很常見的 batch label import 場景，尤其是每個 subject / session 資料夾都放同名 label 檔的結構。

### 可能範圍

- `XBrainLab/ui/dialogs/dataset/import_label_dialog.py`
- `XBrainLab/ui/dialogs/dataset/label_mapping_dialog.py`

### 證據

於 `2026-04-18` 本地透過檢查 dialog code path 並新增 same-basename regression test 確認此問題。

### 測試覆蓋

- `tests/unit/ui/dataset/test_import_label.py`
- `tests/unit/ui/test_ui_misc.py`

### 備註

現在 dialog 已改成用完整路徑當 key，也透過 item tooltip 顯示完整路徑，而不改變既有 layout 結構。

#### [BUG-DATASET-003] Event filter 會記住與目前 dataset 無關的過期選擇

- Priority: P1
- Area: Dataset
- Type: Broken interaction
- Status: Fixed
- Source: Code review

### 症狀

如果上一次儲存的 event selection 來自另一個事件名稱不同的 dataset，event filter dialog 打開時可能會出現所有 event 都未勾選的狀況。

### 重現方式

1. Save a previous filter selection such as `["Left"]`.
2. Open the dialog for a dataset whose available events are `["769", "770"]`.

### 預期

如果儲存歷史和目前 dataset 完全沒有重疊，dialog 應該預設為全部勾選。

### 實際情況

因為歷史記錄雖然不相干但不是空的，所以目前 event 可能全部以未勾選呈現；若使用者沒發現並手動重選，後續同步就會失敗。

### 影響

這會讓 label import 看起來像是壞掉或 dataset-specific，但實際上只是 UI 記憶殘留造成的假象。

### 可能範圍

- `XBrainLab/ui/dialogs/dataset/event_filter_dialog.py`
- dataset label import flow that depends on selected event names

### 證據

於 `2026-04-18` 本地透過 dialog code review 與 stale selection / empty selection regression tests 確認。

### 測試覆蓋

- `tests/unit/ui/dataset/test_import_label.py`
- `tests/unit/ui/test_ui_misc.py`

### 備註

現在 dialog 在 saved history 與目前 dataset 完全無重疊時，會回退成全部勾選，且不允許接受空的 keep-list。

#### [BUG-DATASET-004] Batch label import 曾只用第一個 label 檔推斷整批模式

- Priority: P1
- Area: Dataset
- Type: Broken interaction
- Status: Fixed
- Source: Code review

### 症狀

Batch label import 以前會只看第一個載入的 label 檔，就決定整批匯入是 timestamp-mode 還是 sequence-mode，以及要採用哪個 event-count hint。

### 重現方式

修復前：

- mixed timestamp and sequence label batches could be misclassified by whichever file appeared first
- inconsistent sequence-label lengths could still drive smart-filter suggestions from the first file only

### 預期

mode detection 與 smart-filter hints 應該根據整批 label set 推導，而不是任意一個檔案。

### 實際情況

`DatasetActionHandler.import_label()` 以前使用 `next(iter(label_map.values()))` 來分類整個 batch。

### 影響

這讓 multi-file label import 變得脆弱，也可能對真實 dataset 產生誤導性的 filtering suggestion 或錯誤的 mode 判斷。

### 可能範圍

- `XBrainLab/ui/panels/dataset/actions.py`

### 證據

於 `2026-04-18` 本地在 import workflow review 時確認；後續以 mixed-mode rejection 與 sequence-length 不一致 batch 的測試完成修復。

### 測試覆蓋

- `tests/unit/ui/test_ui_misc.py`

### 備註

現在 handler 會分析整個 label map，明確拒絕 mixed mode，且只有在 batch 內部一致時才提供 target-count hint。

#### [BUG-DATASET-005] Raw-data factory 曾拒絕 `.fif.gz` 與 epoch-style `.fif` 匯入

- Priority: P1
- Area: Dataset
- Type: Broken interaction
- Status: Fixed
- Source: Code review

### 症狀

某些合法的 MNE 檔案會匯入失敗，因為 `.fif.gz` 被當成 `.gz` 處理，而 `.fif` 匯入流程又假設它只能是 raw 檔。

### 重現方式

- `RawDataLoaderFactory.get_loader("subject01-epo.fif.gz")`
- `load_fif_file("epochs.fif")` where raw loading fails but epoch loading would succeed

### 預期

壓縮後的 `.fif.gz` 應該正確走 FIF loader，而 `.fif` 匯入在 raw reader 失敗時應嘗試 epochs fallback。

### 實際情況

factory 只對最後一個副檔名做 `os.path.splitext()`，而 FIF loader 也沒有 epoch fallback。

### 影響

這會讓原本合法的 MNE dataset 因為儲存方式不同而看起來像是不支援或損壞。

### 可能範圍

- `XBrainLab/backend/load_data/factory.py`
- `XBrainLab/backend/load_data/raw_data_loader.py`

### 證據

於 `2026-04-18` 本地透過 code review 確認，並以 `.fif.gz` lookup 與 `.fif` epochs fallback 的 regression coverage 完成修復。

### 測試覆蓋

- `tests/unit/backend/load_data/test_factory.py`
- `tests/unit/backend/load_data/test_raw_data_loader_coverage.py`
- `tests/unit/backend/load_data/test_loaders.py`

### 備註

現在 factory 會選擇最長且已註冊的副檔名匹配；FIF 載入也會在宣告檔案損壞之前，先回退到 `mne.read_epochs()`。

#### [BUG-DATASET-006] Event-filter suggestion 曾只依賴第一個 raw file

- Priority: P2
- Area: Dataset
- Type: Incorrect state
- Status: Fixed
- Source: Code review

### 症狀

在多個 raw file 一起匯入 labels 時，預設的 event-filter suggestion 可能只受到第一個檔案的 event map 影響。

### 重現方式

對多個 event-name map 不相同的 raw file 開啟 label import，並直接依賴 event filter dialog 裡的 suggested selection。

### 預期

建議選項應該反映所有將被同步的 target raw files，而不是只看第一個。

### 實際情況

`DatasetActionHandler._filter_events_for_import()` 以前只會對 `raw_files[0]` 呼叫 smart-filter suggestion。

### 影響

這會讓預設建議選擇變得誤導，使 batch import 即使存在正確的跨檔選擇，也會顯得不可靠。

### 可能範圍

- `XBrainLab/ui/panels/dataset/actions.py`

### 證據

於 `2026-04-18` 本地在 workflow review 中確認，並以 multi-file suggestion aggregation 的 regression coverage 完成修復。

### 測試覆蓋

- `tests/unit/ui/test_ui_misc.py`

### 備註

現在 dialog 會先彙整所有 candidate raw files 的 suggested event names，再做預選。

#### [BUG-TRAINING-001] CUDA capable detection 曾把 training 導到實際不可用的 GPU

- Priority: P1
- Area: Training
- Type: Crash
- Status: Fixed
- Source: Test failure

### 症狀

在某些機器上，即使 `torch.cuda.is_available()` 回傳 `True`，但如果安裝的 PyTorch build 實際上無法在偵測到的 GPU 上執行 kernel，training 仍可能一開始就失敗。

### 重現方式

- 在這台 WSL 主機上執行 `tests/integration/pipeline/test_pipeline_integration.py`
- 或建立 `TrainingOption(use_cpu=False, gpu_idx=0, ...)`，並在目前 RTX 5070 Ti 環境中啟動 training

### 預期

如果指定的 CUDA device 實際上無法執行工作，training 應該安全降級到 CPU，而不是在執行中途崩潰。

### 實際情況

training 路徑以前只信任 availability check，結果最後以 `CUDA error: no kernel image is available for execution on the device` 崩潰。

### 影響

在這台機器上，只要隱性選到 GPU mode，training 幾乎就會被阻塞，即便其他 workflow 本身是合法的。

### 可能範圍

- `XBrainLab/backend/training/option.py`
- `XBrainLab/backend/training/training_plan.py`
- 所有根據 `torch.cuda.is_available()` 推導 device choice 的 training flow

### 證據

於 `2026-04-19` 本地透過失敗的 `tests/integration/pipeline/test_pipeline_integration.py` 與目前 WSL 主機上的直接 `TrainingOption` smoke check 確認。

### 測試覆蓋

- `tests/unit/backend/training/test_option.py`
- `tests/integration/pipeline/test_pipeline_integration.py`

### 備註

現在 `TrainingOption` 會主動 probe 指定的 CUDA device；若 device 雖存在但不可用，則會以 warning 方式回退到 CPU。

#### [BUG-TRAINING-002] Training panel 的 ready state 曾不會隨 preprocess invalidation 即時更新

- Priority: P1
- Area: Training
- Type: Data sync issue
- Status: Fixed
- Source: Manual exploration

### 症狀

當 preprocess 變更把 epoch / dataset downstream state 清掉時，Training panel 的 `Start Training` 按鈕可能還停在舊的 ready 狀態，直到使用者切頁或手動 refresh。

### 重現方式

在 offscreen Qt session 中建立 `TrainingPanel`，先讓 controller 回報 ready，再模擬 preprocess invalidation：

```bash
/home/administrator/.local/bin/poetry run python - <<'PY'
# create TrainingPanel -> initial Start Training enabled
# notify preprocess_changed after validate_ready flips false
PY
```

### 預期

只要 preprocess invalidation 讓 training prerequisites 失效，Training panel 應立即重算 ready state，讓 `Start Training` 按鈕與 tooltip 同步反映新的缺項。

### 實際情況

修正前的 `TrainingPanel` 只訂閱 `data_changed` / `import_finished`，沒有聽 `preprocess_changed`，所以這類 invalidation 不會主動觸發 `update_panel()`。

### 影響

這會讓 training workflow 的 UI readiness 判斷變得誤導：使用者可能看到仍可按的 `Start Training`，但底層 dataset state 其實已被 preprocess 變更清掉。

### 可能範圍

- `XBrainLab/ui/panels/training/panel.py`
- preprocess invalidation 後依賴 Training panel ready state 的 workflow

### 證據

於 `2026-04-19` 本地以 offscreen Qt repro 確認：

- 修正前：
  - `initial True Start Training`
  - `after_notify True Start Training`
- 修正後：
  - `initial True Start Training`
  - `after_notify False Please configure: Data Splitting`

### 測試覆蓋

- `tests/unit/ui/training/test_training_panel.py`
- `tests/unit/ui/test_panel_event_bridges.py`

### 備註

目前最小修復面就是補上 `TrainingPanel <- preprocess_changed` bridge，而不是先改 training controller 的 readiness 定義。

#### [BUG-TRAINING-003] Training panel 曾不會在 training_started 後立即顯示 active run

- Priority: P1
- Area: Training
- Type: Data sync issue
- Status: Fixed
- Source: Manual exploration

### 症狀

當 training 開始後，Training panel 的 history table 與目前選中的 plotting record 曾不會立刻切到 active run，而是要等下一次 `training_updated` poll tick 才同步。

### 重現方式

在 offscreen Qt session 中建立 `TrainingPanel`，先讓 controller 的 `get_formatted_history()` 已能回傳一筆 active run，再模擬 `training_started`：

```bash
/home/administrator/.local/bin/poetry run python - <<'PY'
# create TrainingPanel with active history ready in controller
# notify training_started
PY
```

### 預期

只要 training 已經開始，Training panel 應立即把 active run 掛進 history table，並切到可用的 plotting record，而不是等下一個 polling cycle。

### 實際情況

修正前的 `TrainingPanel` 在 `training_started` 時只更新 log/sidebar，沒有同步呼叫 `update_loop()`，所以 active run 要等後續 `training_updated` 才會顯示。

### 影響

這會讓 training workflow 的即時狀態呈現變得遲滯：使用者按下開始後，UI 短時間內看起來像還沒真正進入 training。

### 可能範圍

- `XBrainLab/ui/panels/training/panel.py`
- 依賴 Training panel immediate active-run state 的 workflow

### 證據

於 `2026-04-19` 本地以 offscreen Qt repro 確認修正後行為：

- `started_before 0 None`
- `started_after 1 Running True`

focused validation：

- `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/training/test_training_panel.py -q`
  - 結果：`9 passed`
- `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui -q`
  - 結果：`762 passed, 12 skipped, 1 warning`

### 測試覆蓋

- `tests/unit/ui/training/test_training_panel.py`
- `tests/unit/ui -q` shared regression sweep

### 備註

目前最小修復面就是在 `training_started` handler 立刻觸發一次 `update_loop()`，不需要改 training controller 的 event 模型。

#### [BUG-TRAINING-004] Training panel 曾在 training config change 後保留過期 history/plot state

- Priority: P1
- Area: Training
- Type: Data sync issue
- Status: Fixed
- Source: Manual exploration

### 症狀

當 training-side config change 使 trainer/history 失效後，Training panel 曾仍保留舊的 history rows、舊的 plotting record，直到手動 refresh 或其他後續事件介入。

### 重現方式

在 offscreen Qt session 中建立 `TrainingPanel`，先讓 controller 回報一筆 history，再模擬 `config_changed` 後 controller history 已清空：

```bash
/home/administrator/.local/bin/poetry run python - <<'PY'
# create TrainingPanel with one history entry
# notify config_changed after get_formatted_history() flips empty
PY
```

### 預期

只要 training-side config change 讓 trainer/history 失效，Training panel 應立刻清空 stale history rows、清掉目前 plotting record，並重置 epoch counter。

### 實際情況

修正前的 `TrainingPanel` 在 `config_changed` 時只重算 ready state，沒有同步 refresh/clear history view；而 `update_loop()` 也不會在 history 空掉時主動清掉目前選中的 plotting state。

### 影響

這會讓 training workflow 的主畫面自己也變得不誠實：UI 仍顯示舊的 history/plot，但底層 trainer 已經被 config change 清掉。

### 可能範圍

- `XBrainLab/ui/panels/training/panel.py`
- 依賴 Training panel history / plot state 的 workflow

### 證據

於 `2026-04-19` 本地以 offscreen Qt repro 確認修正後行為：

- `config_after 0 None -1`

focused validation：

- `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/training/test_training_panel.py -q`
  - 結果：`9 passed`
- `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui -q`
  - 結果：`762 passed, 12 skipped, 1 warning`

### 測試覆蓋

- `tests/unit/ui/training/test_training_panel.py`
- `tests/unit/ui -q` shared regression sweep

### 備註

目前最小修復面有兩段：

- `config_changed` handler 立刻觸發 `update_loop()`
- `update_loop()` 在 history 變空時主動清掉 stale plot selection / epoch counter，而不是只把 table row count 降到 0

#### [BUG-TRAINING-005] Training panel 曾被舊 selected record 卡住，錯過新 active run 或新 history

- Priority: P1
- Area: Training
- Type: Data sync issue
- Status: Fixed
- Source: Manual exploration

### 症狀

當 panel 已經選著舊的 plotting record 時，後續新的 active run 開始，或整個 history 被新 trainer/history 取代後，Training panel 曾仍停在舊 record 上，不會自動切到新的 active run 或新的唯一 record。

### 重現方式

在 offscreen Qt session 中建立 `TrainingPanel`，先讓 controller 回報一筆舊 history，再模擬兩種情境：

```bash
/home/administrator/.local/bin/poetry run python - <<'PY'
# 1. old selected record exists, then training_started with a new active run
# 2. old selected record exists, then config_changed with replacement history
PY
```

### 預期

- 新的 active run 開始時，panel 應切到新的 active record
- 舊 history 被新的 trainer/history 取代時，panel 應丟掉過期 selection，改追新的有效 record

### 實際情況

修正前的 `update_loop()` 只在 `current_plotting_record` 為空時才會自動選 record，所以：

- 舊 record 若仍被選中，`training_started` 後不會切到新的 active run
- 舊 record 若已不在新的 history 內，但 history 仍非空，panel 也不會自動換掉它

### 影響

這會讓 training workflow 的圖表與目前選中的 run 出現更隱蔽的不同步：即使 history table 已經有新 active run，plot 仍可能卡在舊 run；更換 trainer/history 後，也可能繼續看著已失效的舊 record。

### 可能範圍

- `XBrainLab/ui/panels/training/panel.py`
- 依賴 Training panel current plotting record 的 workflow

### 證據

於 `2026-04-19` 本地以 offscreen Qt repro 確認修正後行為：

- 舊 record -> 新 active run：
  - `before_switch True [1, 2, 3]`
  - `after_switch True [1]`
- 舊 record -> replacement history：
  - `after_replace True [1, 2]`

focused validation：

- `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/training/test_training_panel.py -q`
  - 結果：`11 passed`
- `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui -q`
  - 結果：`764 passed, 12 skipped, 1 warning`

### 測試覆蓋

- `tests/unit/ui/training/test_training_panel.py`
- `tests/unit/ui -q` shared regression sweep

### 備註

目前最小修復面是讓 `update_loop()` 先根據當前 history 決定「最合理的 plotting record」，而不是只在沒有 selection 時才自動選。`training_started` 則明確以 active run 為優先。

#### [BUG-TRAINING-006] Training panel 曾無法同時兼顧 active-run auto-follow 與手動 pin 的歷史檢視

- Priority: P1
- Area: Training
- Type: Data sync issue
- Status: Fixed
- Source: Manual exploration

### 症狀

在 `training_updated` 驅動的 repeat 轉換期間，Training panel 曾缺少一個一致的 selection policy：

- 若保持完全保守，就會讓 panel 卡在舊 selected record，錯過新的 active run
- 若一律切到新 active run，又可能覆蓋掉使用者手動選來檢視的舊 run

### 重現方式

在 offscreen Qt session 中建立 `TrainingPanel`，模擬兩種 `training_updated` 路徑：

```bash
/home/administrator/.local/bin/poetry run python - <<'PY'
# 1. auto-managed selection, then repeat transition via training_updated
# 2. user manually selects old run, then training_updated fires
PY
```

### 預期

- auto-managed selection 應在 repeat 轉換時跟上新的 active run
- user-pinned 的歷史 run 應在普通 `training_updated` 下被保留，不該被自動切走

### 實際情況

修正前的 `TrainingPanel` 沒有明確區分 auto-managed selection 與 user-pinned selection，所以無法同時滿足這兩個需求。

### 影響

這會讓 ongoing training 的 plot 跟隨策略不穩定：不是錯過新的 active run，就是很容易把使用者刻意選來看的舊 run 覆蓋掉。

### 可能範圍

- `XBrainLab/ui/panels/training/panel.py`
- 依賴 Training panel plotting selection policy 的 workflow

### 證據

於 `2026-04-19` 本地以 offscreen Qt repro 確認修正後行為：

- auto-follow 路徑：
  - `auto_before True [1, 2, 3]`
  - `auto_after True [1]`
- manual pin 路徑：
  - `manual_after True True`

focused validation：

- `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/training/test_training_panel.py -q`
  - 結果：`13 passed`
- `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui -q`
  - 結果：`766 passed, 12 skipped, 1 warning`

### 測試覆蓋

- `tests/unit/ui/training/test_training_panel.py`
- `tests/unit/ui -q` shared regression sweep

### 備註

目前最小修復面是引入「user-pinned selection」概念：

- auto-managed selection 會在 `training_updated` 下跟隨新的 active run
- user 手動選中的 record 則在普通 `training_updated` 下保持 pinned
- `training_started` 仍可透過 `force_active=True` 明確切回新的 active run

這讓 training panel 的 selection policy 從「碰到新 history 就全自動」或「永遠保守不切換」收斂成比較可預期的混合策略。

#### [BUG-TRAINING-007] Training panel 曾在 history/config reset 後保留過期 event log

- Priority: P2
- Area: Training
- Type: Data sync issue
- Status: Fixed
- Source: Manual exploration

### 症狀

Training panel 的 `Log` tab 過去只會在 `training_started` / `training_stopped` append 事件訊息，但在 `history_cleared` 或 `config_changed` 清空 / 取代 training state 後，不會同步清掉舊 log。

### 重現方式

在 offscreen Qt session 中建立 `TrainingPanel`，先觸發一次 start/stop event，再依序觸發：

```bash
/home/administrator/.local/bin/poetry run python - <<'PY'
# 1. training_started -> training_stopped
# 2. history_cleared
# 3. training_started -> training_stopped
# 4. config_changed
PY
```

### 預期

當 training history 被清空，或 training config 讓舊 trainer / history 失效時，`Log` tab 應回到空白狀態，而不是繼續顯示已失效 run 的事件訊息。

### 實際情況

修正前的 `TrainingPanel` 只會清 plots/table selection state，不會清 `log_text`，所以：

- `history_cleared` 後仍會留下舊的 `Training started/stopped` 事件
- `config_changed` 即使已經切到新的 history，也仍會把舊 run 的 event log 留在畫面上

### 影響

這會讓 training panel 在「目前沒有那個 run 了」的情況下，仍顯示舊 event log，看起來像舊 training session 仍然是當前 state；AQ-003 原本要收的 logs/plots/state sync 也因此少了一塊。

### 可能範圍

- `XBrainLab/ui/panels/training/panel.py`
- `tests/unit/ui/training/test_training_panel.py`

### 證據

於 `2026-04-19` 本地以 offscreen Qt repro 確認修正前後差異：

- 修正前：
  - `before_clear Training started (event). | Training stopped (event).`
  - `after_history_cleared Training started (event). | Training stopped (event).`
  - `after_config_changed Training started (event). | Training stopped (event). | Training started (event). | Training stopped (event).`
- focused validation：
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/training/test_training_panel.py -q`
    - 結果：`16 passed`
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui -q`
    - 結果：`769 passed, 12 skipped, 1 warning`

### 測試覆蓋

- `tests/unit/ui/training/test_training_panel.py`
- `tests/unit/ui -q` shared regression sweep

### 備註

這一輪除了把 stale log 收掉，也順手補上 `training_updated` live refresh 的直接 focused coverage：

- 最新 targeted test 會驗證 history-table progress 由 `1/5` 變成 `2/5`
- 同時確認 plot epochs 由 `[1]` 變成 `[1, 2]`

因此目前 AQ-003 的剩餘風險已不再是「training panel 的 live progress / log / plot 會不會漏刷」，而是下一個 queue item `AQ-004` 的 evaluation-consistency 問題。

#### [BUG-EVAL-001] Evaluation panel 曾在 preprocess invalidation 後保留過期的 fold/run 選擇

- Priority: P1
- Area: Evaluation
- Type: Data sync issue
- Status: Fixed
- Source: Manual exploration

### 症狀

當 preprocess 變更把 trainer / dataset downstream state 清掉時，Evaluation panel 可能還保留舊的 fold/run selection，看起來像還有可分析的結果，直到手動 refresh。

### 重現方式

在 offscreen Qt session 中建立 `EvaluationPanel`，先讓 controller 回報一個 plan，再模擬 preprocess invalidation：

```bash
/home/administrator/.local/bin/poetry run python - <<'PY'
# create EvaluationPanel -> initial Fold 1 visible
# notify preprocess_changed after controller.get_plans() flips empty
PY
```

### 預期

只要 preprocess invalidation 讓 trainer 結果失效，Evaluation panel 應立刻清掉舊的 fold/run 選擇，回到 `No Data Available`。

### 實際情況

修正前的 `EvaluationPanel` 只訂閱 `training_stopped`，沒有聽 `preprocess_changed`，所以這類 invalidation 不會主動觸發 `update_panel()`。

### 影響

這會讓 evaluation workflow 的狀態呈現變得誤導：UI 仍顯示舊的 fold/run 選擇，但底層 trainer 結果其實已因 preprocess 變更失效。

### 可能範圍

- `XBrainLab/ui/panels/evaluation/panel.py`
- preprocess invalidation 後依賴 Evaluation panel selection state 的 workflow

### 證據

於 `2026-04-19` 本地以 offscreen Qt repro 確認：

- 修正前：
  - `initial 1 Fold 1: Plan A`
  - `after_preprocess_notify 1 Fold 1: Plan A`
  - `after_manual_refresh 1 No Data Available`
- 修正後：
  - `initial 1 Fold 1: Plan A`
  - `after_notify 1 No Data Available 0`

### 測試覆蓋

- `tests/unit/ui/test_evaluation_panel_redesign.py`
- `tests/unit/ui/test_panel_event_bridges.py`

### 備註

目前最小修復面就是補上 `EvaluationPanel <- preprocess_changed` bridge，先讓 downstream result view 對 preprocess invalidation 說實話，再決定是否要往 visualization 做對稱修補。

#### [BUG-EVAL-002] Evaluation panel 曾在 training history clear 後保留過期的 fold/run 選擇

- Priority: P1
- Area: Evaluation
- Type: Data sync issue
- Status: Fixed
- Source: Manual exploration

### 症狀

當 training history 被清空後，Evaluation panel 可能還保留舊的 fold/run selection，看起來像仍有結果可分析，直到手動 refresh。

### 重現方式

在 offscreen Qt session 中建立 `EvaluationPanel`，先讓 controller 回報一個 plan，再模擬 training history clear：

```bash
/home/administrator/.local/bin/poetry run python - <<'PY'
# create EvaluationPanel -> initial Fold 1 visible
# notify history_cleared after controller.get_plans() flips empty
PY
```

### 預期

只要 training history 被清空，Evaluation panel 應立刻清掉舊的 fold/run selection，回到 `No Data Available`。

### 實際情況

修正前的 `EvaluationPanel` 只訂閱 `training_stopped`，沒有聽 `history_cleared`，所以清空 training history 不會主動觸發 `update_panel()`。

### 影響

這會讓 evaluation workflow 的狀態呈現變得誤導：UI 仍顯示舊的 fold/run 選擇，但底層 training history 已經被清掉。

### 可能範圍

- `XBrainLab/ui/panels/evaluation/panel.py`
- training history clear 後依賴 Evaluation panel selection state 的 workflow

### 證據

於 `2026-04-19` 本地以 offscreen Qt repro 確認：

- 修正前：
  - `eval_before 1 Fold 1: Plan A 2`
  - `eval_after 1 Fold 1: Plan A 2`
- 修正後：
  - `eval_before 1 Fold 1: Plan A 2`
  - `eval_after 1 No Data Available 0`
- focused validation：
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_evaluation_panel_redesign.py -q`
    - 結果：`4 passed`
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_panel_event_bridges.py -q`
    - 結果：`9 passed`

### 測試覆蓋

- `tests/unit/ui/test_evaluation_panel_redesign.py`
- `tests/unit/ui/test_panel_event_bridges.py`

### 備註

目前最小修復面就是補上 `EvaluationPanel <- history_cleared` bridge，不需要先重做 evaluation controller 或 training history model。

#### [BUG-EVAL-003] Evaluation panel 曾在 training config change 後保留過期的 fold/run 選擇

- Priority: P1
- Area: Evaluation
- Type: Data sync issue
- Status: Fixed
- Source: Manual exploration

### 症狀

當 training-side config change 使 trainer 結果失效後，Evaluation panel 可能還保留舊的 fold/run selection，看起來像仍有結果可分析，直到手動 refresh。

### 重現方式

在 offscreen Qt session 中建立 `EvaluationPanel`，先讓 controller 回報一個 plan，再模擬 `config_changed` 後下游 planner/trainer 已經清空：

```bash
/home/administrator/.local/bin/poetry run python - <<'PY'
# create EvaluationPanel -> initial Fold 1 visible
# notify config_changed after controller.get_plans() flips empty
PY
```

### 預期

只要 training config change 讓 trainer 結果失效，Evaluation panel 應立刻清掉舊的 fold/run selection，回到 `No Data Available`。

### 實際情況

修正前的 `EvaluationPanel` 沒有聽 `config_changed`，所以像 data splitting 這類會清 trainer 的 training-side config 變更不會主動觸發 `update_panel()`。

### 影響

這會讓 evaluation workflow 的狀態呈現變得誤導：UI 仍顯示舊的 fold/run 選擇，但底層 trainer 已因 training config 變更而被清掉。

### 可能範圍

- `XBrainLab/ui/panels/evaluation/panel.py`
- training-side config changes 後依賴 Evaluation panel selection state 的 workflow

### 證據

於 `2026-04-19` 本地以 offscreen Qt repro 確認：

- 修正前：
  - `eval_before 1 Fold 1: Plan A 2`
  - `eval_after 1 Fold 1: Plan A 2`
- 修正後：
  - `eval_before 1 Fold 1: Plan A 2`
  - `eval_after 1 No Data Available 0`
- focused validation：
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_evaluation_panel_redesign.py -q`
    - 結果：`5 passed`
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_panel_event_bridges.py -q`
    - 結果：`11 passed`

### 測試覆蓋

- `tests/unit/ui/test_evaluation_panel_redesign.py`
- `tests/unit/ui/test_panel_event_bridges.py`

### 備註

目前最小修復面就是補上 `EvaluationPanel <- config_changed` bridge。這條 event 不代表所有 training config 變更都會清 trainer，但對會清掉 plan/history 的路徑而言，現在至少不會再把 stale selection 留在畫面上。

#### [BUG-EVAL-004] Evaluation panel 曾在 harmless refresh 後把使用者選擇重設回第一個 fold/run

- Priority: P1
- Area: Evaluation
- Type: Data sync issue
- Status: Fixed
- Source: Manual exploration

### 症狀

當使用者已經在 Evaluation panel 切到其他 fold/run，之後只要 `training_stopped` 觸發一次 `update_panel()`，畫面就會把 selection 重設回第一個 plan 與第一個 run，即使原本選擇的 plan/run 仍然有效。

### 重現方式

在 offscreen Qt session 中建立 `EvaluationPanel`，先手動切到第二個 fold 與 average run，再觸發 `training_stopped`：

```bash
/home/administrator/.local/bin/poetry run python - <<'PY'
# create EvaluationPanel -> select Fold 2 / Average
# notify training_stopped without removing plans
PY
```

### 預期

如果原本的 fold/run 仍然存在，`training_stopped` 這類 harmless refresh 不應把使用者正在看的分析上下文洗掉。

### 實際情況

修正前的 `EvaluationPanel.update_panel()` 每次都會重新把 `model_combo` 設回 index `0`，然後 `on_model_changed()` 也會把 `run_combo` 設回 index `0`，所以：

- 原本在看的 `Fold 2: Plan B / Average (Finished Runs)` 會被重設成 `Fold 1: Plan A / Repeat 1 (Finished)`
- 如果原本在看的是剛完成的特定 repeat，該筆 record 雖然還存在，但 selection 仍會被沖掉

### 影響

這會讓 evaluation workflow 缺少穩定的分析上下文。使用者在比較不同 fold 或 average 結果時，只要 training-complete refresh 一來，畫面就跳回第一筆資料，看起來像是自己選錯或資料變掉。

### 可能範圍

- `XBrainLab/ui/panels/evaluation/panel.py`
- 依賴 Evaluation panel selection state 的 cross-screen analysis workflow

### 證據

於 `2026-04-19` 本地以 offscreen Qt repro 確認：

- 修正前：
  - `before Fold 2: Plan B Average (Finished Runs)`
  - `after Fold 1: Plan A Repeat 1 (Finished)`
- focused validation：
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_evaluation_panel_redesign.py -q`
    - 結果：`7 passed`
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_panel_event_bridges.py -q`
    - 結果：`11 passed`
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui -q`
    - 結果：`771 passed, 12 skipped, 1 warning`

### 測試覆蓋

- `tests/unit/ui/test_evaluation_panel_redesign.py`
- `tests/unit/ui/test_panel_event_bridges.py`
- `tests/unit/ui -q` shared regression sweep

### 備註

目前最小修復面是讓 `EvaluationPanel` 在 `update_panel()` / `on_model_changed()` 期間保留「仍然有效的 selection」：

- 先盡量以 plan / record identity 保留選擇
- 再用 label 當 fallback
- 因此 `Average (Finished Runs)` 與剛完成後 label 會改變的 specific repeat 都能在 harmless refresh 後保留下來

這讓 AQ-004 不再只是「清掉 stale selection」，也補上了「不要把 valid selection 白白洗掉」這個對稱一致性缺口。

#### [BUG-VIZ-001] Visualization panel 曾在 preprocess invalidation 後保留過期的 plan/run 選擇

- Priority: P1
- Area: Visualization
- Type: Data sync issue
- Status: Fixed
- Source: Manual exploration

### 症狀

當 preprocess 變更把 trainer / epoch downstream state 清掉時，Visualization panel 可能還保留舊的 plan/run 選擇；更糟的是，舊版 `refresh_combos()` 在 trainers 消失時不會清掉這些 stale entries，所以連手動 refresh 都可能留下殘影。

### 重現方式

在 offscreen Qt session 中建立 `VisualizationPanel`，先讓 controller 回報一個 trainer，再模擬 preprocess invalidation：

```bash
/home/administrator/.local/bin/poetry run python - <<'PY'
# create VisualizationPanel -> initial Fold 1 visible
# notify preprocess_changed after controller.get_trainers() flips empty
PY
```

### 預期

只要 preprocess invalidation 讓 visualization 上游結果失效，Visualization panel 應立刻清掉舊的 plan/run 選擇，回到 placeholder 狀態。

### 實際情況

修正前的 `VisualizationPanel` 只訂閱 `training_stopped`，沒有聽 `preprocess_changed`；而且 `refresh_combos()` 在 `get_trainers()` 為空時直接 `return`，不會先清空既有 combo 內容。

### 影響

這會讓 visualization workflow 的狀態呈現變得誤導：UI 仍顯示可選的舊 plan/run，但底層 trainer 結果其實已因 preprocess 變更失效。

### 可能範圍

- `XBrainLab/ui/panels/visualization/panel.py`
- preprocess invalidation 後依賴 Visualization panel selection state 的 workflow

### 證據

於 `2026-04-19` 本地以 offscreen Qt repro 確認：

- 修正前：
  - `initial 2 Fold 1 (EEGNet) 2`
  - `after_notify 2 Fold 1 (EEGNet) 2`
  - `after_manual_refresh 2 Select a plan 2`
- 修正後：
  - `initial 2 Fold 1 (EEGNet) 2`
  - `after_notify 1 Select a plan 0`

### 測試覆蓋

- `tests/unit/ui/test_visualization_panel_coverage.py`
- `tests/unit/ui/test_panel_event_bridges.py`

### 備註

目前最小修復面是兩段一起做：

- 補上 `VisualizationPanel <- preprocess_changed` bridge
- 讓 `refresh_combos()` 在 trainer list 變空時也會主動清掉 stale plan/run

#### [BUG-VIZ-002] Visualization panel 曾在 training history clear 後保留過期的 plan/run 選擇

- Priority: P1
- Area: Visualization
- Type: Data sync issue
- Status: Fixed
- Source: Manual exploration

### 症狀

當 training history 被清空後，Visualization panel 可能還保留舊的 plan/run selection，看起來像仍有 saliency 結果可檢視，直到手動 refresh。

### 重現方式

在 offscreen Qt session 中建立 `VisualizationPanel`，先讓 controller 回報一個 trainer，再模擬 training history clear：

```bash
/home/administrator/.local/bin/poetry run python - <<'PY'
# create VisualizationPanel -> initial Fold 1 visible
# notify history_cleared after controller.get_trainers() flips empty
PY
```

### 預期

只要 training history 被清空，Visualization panel 應立刻清掉舊的 plan/run selection，回到 placeholder 狀態。

### 實際情況

修正前的 `VisualizationPanel` 只訂閱 `training_stopped`，沒有聽 `history_cleared`，所以清空 training history 不會主動觸發 `update_panel()`。

### 影響

這會讓 visualization workflow 的狀態呈現變得誤導：UI 仍顯示可選的舊 plan/run，但底層 training history 已經被清掉。

### 可能範圍

- `XBrainLab/ui/panels/visualization/panel.py`
- training history clear 後依賴 Visualization panel selection state 的 workflow

### 證據

於 `2026-04-19` 本地以 offscreen Qt repro 確認：

- 修正前：
  - `viz_before 2 Fold 1 (EEGNet) 2`
  - `viz_after 2 Select a plan 2`
- 修正後：
  - `viz_before 2 Fold 1 (EEGNet) 2`
  - `viz_after 1 Select a plan 0`
- focused validation：
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_visualization_panel_coverage.py -q`
    - 結果：`18 passed`
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_panel_event_bridges.py -q`
    - 結果：`9 passed`
- shared UI regression sweep：
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui -q`
    - 結果：`756 passed, 12 skipped, 1 warning`

### 測試覆蓋

- `tests/unit/ui/test_visualization_panel_coverage.py`
- `tests/unit/ui/test_panel_event_bridges.py`
- `tests/unit/ui -q` shared regression sweep

### 備註

目前最小修復面就是補上 `VisualizationPanel <- history_cleared` bridge；因為 `refresh_combos()` 本身已在 AQ-002 被修成會清掉 stale selections，所以這輪不需要再改 combo 清理邏輯本體。

#### [BUG-VIZ-003] Visualization panel 曾在 training config change 後保留過期的 plan/run 選擇

- Priority: P1
- Area: Visualization
- Type: Data sync issue
- Status: Fixed
- Source: Manual exploration

### 症狀

當 training-side config change 使 trainer 結果失效後，Visualization panel 可能還保留舊的 plan/run selection，看起來像仍有 saliency 結果可檢視，直到手動 refresh。

### 重現方式

在 offscreen Qt session 中建立 `VisualizationPanel`，先讓 controller 回報一個 trainer，再模擬 `config_changed` 後 trainer list 已經清空：

```bash
/home/administrator/.local/bin/poetry run python - <<'PY'
# create VisualizationPanel -> initial Fold 1 visible
# notify config_changed after controller.get_trainers() flips empty
PY
```

### 預期

只要 training config change 讓 trainer 結果失效，Visualization panel 應立刻清掉舊的 plan/run selection，回到 placeholder 狀態。

### 實際情況

修正前的 `VisualizationPanel` 沒有聽 `config_changed`，所以像 data splitting 這類會清 trainer 的 training-side config 變更不會主動觸發 `update_panel()`。

### 影響

這會讓 visualization workflow 的狀態呈現變得誤導：UI 仍顯示可選的舊 plan/run，但底層 trainer 已因 training config 變更而被清掉。

### 可能範圍

- `XBrainLab/ui/panels/visualization/panel.py`
- training-side config changes 後依賴 Visualization panel selection state 的 workflow

### 證據

於 `2026-04-19` 本地以 offscreen Qt repro 確認：

- 修正前：
  - `viz_before 2 Fold 1 (EEGNet) 2`
  - `viz_after 2 Fold 1 (EEGNet) 2`
- 修正後：
  - `viz_before 2 Fold 1 (EEGNet) 2`
  - `viz_after 1 Select a plan 0`
- focused validation：
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_visualization_panel_coverage.py -q`
    - 結果：`19 passed`
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_panel_event_bridges.py -q`
    - 結果：`11 passed`
- shared UI regression sweep：
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui -q`
    - 結果：`760 passed, 12 skipped, 1 warning`

### 測試覆蓋

- `tests/unit/ui/test_visualization_panel_coverage.py`
- `tests/unit/ui/test_panel_event_bridges.py`
- `tests/unit/ui -q` shared regression sweep

### 備註

目前最小修復面就是補上 `VisualizationPanel <- config_changed` bridge；因為 `refresh_combos()` 的 stale-selection 清理已在 AQ-002 修好，所以這輪只需要把事件 fanout 接到 panel 即可。

#### [BUG-VIZ-004] Visualization panel 曾在 harmless refresh 後把使用者選擇重設回第一個 plan/run

- Priority: P1
- Area: Visualization
- Type: Data sync issue
- Status: Fixed
- Source: Manual exploration

### 症狀

當使用者已經在 Visualization panel 切到其他 fold/run，之後只要 `training_stopped` 觸發一次 harmless refresh，畫面就會把 selection 重設回第一個 plan 與第一個 run，即使原本選擇的 plan/run 仍然有效。

### 重現方式

在 offscreen Qt session 中建立 `VisualizationPanel`，先切到第二個 fold 與 average run，再觸發 `training_stopped`：

```bash
/home/administrator/.local/bin/poetry run python - <<'PY'
# create VisualizationPanel -> select Fold 2 / Average
# notify training_stopped without removing plans
PY
```

### 預期

如果原本的 plan/run 仍然存在，`training_stopped` 這類 harmless refresh 不應把使用者正在看的 saliency 分析上下文洗掉。

### 實際情況

修正前的 `VisualizationPanel.refresh_combos()` / `on_plan_changed()` 每次 refresh 都會無條件回到第一個 trainer 與第一個 run，所以：

- 原本在看的 average path 會被重設回第一個 trainer
- 即使只是完成訓練、並沒有讓既有結果失效，畫面仍會跳回第一筆資料

### 影響

這會讓 visualization workflow 缺少穩定的分析上下文。使用者在比較不同 fold 或 average saliency 時，只要來一次 harmless refresh，畫面就跳回第一筆資料，看起來像是自己選錯或結果被覆蓋。

### 可能範圍

- `XBrainLab/ui/panels/visualization/panel.py`
- 依賴 Visualization panel selection state 的 cross-screen analysis workflow

### 證據

於 `2026-04-19` 本地以 focused slices 確認：

- `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_visualization_panel_coverage.py -q`
  - 結果：`20 passed`
- `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_visualization_panel_redesign.py -q`
  - 結果：`6 passed`
- `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui -q`
  - 結果：`782 passed, 3 skipped, 1 warning`

### 測試覆蓋

- `tests/unit/ui/test_visualization_panel_coverage.py`
- `tests/unit/ui/test_visualization_panel_redesign.py`
- `tests/unit/ui -q` shared regression sweep

### 備註

目前最小修復面是讓 `VisualizationPanel` 在 refresh 前記住目前 selection，refresh 後優先以 plan/run identity 保留選擇，再以 label 當 fallback。這樣 average path 與具體 run 都能在 harmless refresh 後保留，而不會再被洗回第一個 trainer。

#### [BUG-ENV-004] 兩個 real-data integration test 曾指向不存在的 fixture 目錄

- Priority: P2
- Area: Test infrastructure
- Type: Missing observability
- Status: Fixed
- Source: Test failure

### 症狀

某些原本要驗證真實 EEG 檔案的 integration test 會被默默 skip，因為它們去找 `tests/integration/data/`，但 repo 實際把 fixture 放在 `tests/data/`。

### 重現方式

- 執行 `tests/integration/pipeline/test_real_data_pipeline.py`
- 執行 `tests/integration/io/test_io_integration.py`

### 預期

這兩個測試都應該使用 repo 內已存在的 real GDF fixture，並提供 import 與 pipeline 行為的 real-data signal。

### 實際情況

在修正路徑之前，這兩個測試都會因為 "test data not found" 而被 skip。

### 影響

這會降低 real-data coverage，也會讓穩定化循環看起來比實際更健康，因為兩個有價值的檢查從來沒有真正執行。

### 可能範圍

- `tests/integration/pipeline/test_real_data_pipeline.py`
- `tests/integration/io/test_io_integration.py`

### 證據

於 `2026-04-19` 本地確認：修復前兩個測試都被 skip，當 fixture path 改成 `tests/data/` 後即通過。

### 測試覆蓋

- `tests/integration/pipeline/test_real_data_pipeline.py`
- `tests/integration/io/test_io_integration.py`

### 備註

目前 repo 已帶有三個 checked-in 的 real GDF fixture 和對應 label 檔，總量約 98 MB，仍足以作為實用的 real-data baseline。

#### [BUG-DATASET-007] Real GDF import 仍依賴 MNE 自動重新命名重複的 EEG channel names

- Priority: P2
- Area: Dataset
- Type: Incorrect state
- Status: Confirmed
- Source: Runtime log

### 症狀

匯入 repo 內已帶的 BCI Competition GDF fixture 時，MNE 會發出 warning，因為許多 channel 都以同樣的通用名稱 (`EEG`) 進來，迫使 MNE 自動把它們改成像 `EEG-0`、`EEG-1` 這類產生式名稱。

### 重現方式

執行任何使用 `tests/data/A01T.gdf` 的 real-data import flow，例如：

```bash
/home/administrator/.local/bin/poetry run pytest tests/integration/io/test_io_integration.py -q
```

### 預期

real import 應該要嘛有意識地正規化 channel name，要嘛把 duplicate-name 狀況以可依賴的方式暴露出來，讓 downstream 的 channel selection、montage 邏輯與 diagnostics 可以正確處理。

### 實際情況

匯入雖然成功，但 MNE 會發出 duplicate-name warning，並默默產生替代名稱。

在目前 checked-in 的 `A01T.gdf` 上，實際 channel names 會變成像：

```text
EEG-Fz, EEG-0, EEG-1, ..., EEG-C3, EEG-Cz, EEG-C4, ..., EEG-Pz
```

也就是說，真正有 identity 的少數 channel name 和 MNE 自動補出的 `EEG-0`、`EEG-1` 類名稱會混在一起。

`2026-04-19` 補充：`load_gdf_file()` 現在已額外記錄 repo-specific warning，明確指出這次匯入依賴了 MNE 的 duplicate-name auto-rename，讓 downstream triage 不會只看到一條泛用 runtime warning。

同日進一步補強：這個 signal 現在不只會寫進 `Raw` wrapper 的 runtime signals，還會保存成 structured runtime detail `gdf_duplicate_channel_names`，其中包含 `generated_bases` 與 `generated_channels`。再往上一層，dataset summary 與 real dataset-info tool 也已能直接暴露這份 ambiguity，所以整合測試與後續 workflow 不必只依賴 logger/stderr 或字串 parsing，才能知道這份資料曾經歷 channel-name auto-rename。

同日 repair-loop 再往前一格後，preprocess stage 也不再是盲區：`PreprocessController.get_runtime_diagnostics()` 與 `BackendFacade.get_preprocess_diagnostics()` 現在會保留同一份 ambiguity detail，而 channel-sensitive real preprocess tools 會在 `select_channels`、`set_reference`、`standard_preprocess`、`confirm_montage` 這些 agent-facing 路徑上附加 guardrail note，提醒目前仍存在 generated channel names。

### 影響

這不會立即造成 crash，但可能扭曲跨檔 channel matching，也會讓後續與 selection、montage、mismatch diagnostics 相關的失敗更難判讀。

### 可能範圍

- `XBrainLab/backend/load_data/raw_data_loader.py`
- `XBrainLab/backend/load_data/raw.py`
- 對 channel name 敏感的 preprocess 與 dataset workflow
- channel-sensitive real preprocess tools and montage confirmation flow

### 證據

於 `2026-04-19` 本地在建立新 multi-extension fixture baseline 的過程中，於 GDF real-data import 與 real-data integration test 持續觀察到。

同日進一步確認：

- `/home/administrator/.local/bin/poetry run python - <<'PY' ... load_gdf_file('tests/data/A01T.gdf') ... PY`
  - 結果：
    - `nchan 25`
    - `unique 25`
    - first channels include `EEG-0`, `EEG-1`, ...
    - logger now emits an explicit XBrainLab warning describing the MNE auto-rename dependency
- `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/unit/backend/load_data/test_raw.py -q`
  - 結果：`32 passed`
- `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/unit/backend/load_data/test_raw_data_loader.py -q`
  - 結果：`5 passed`
- `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/unit/backend/controller/test_dataset_controller.py -q`
  - 結果：`18 passed`
- `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/unit/backend/controller/test_preprocess_controller.py -q`
  - 結果：`10 passed`
- `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/unit/backend/test_facade_coverage.py -q`
  - 結果：`39 passed`
- `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/unit/llm/tools/real/test_real_tools.py -q`
  - 結果：`21 passed`
- `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/integration/pipeline/test_all_real_tools.py::TestAllRealTools::test_channel_selection_tool tests/integration/pipeline/test_all_real_tools.py::TestAllRealTools::test_set_montage_tool -q`
  - 結果：`2 passed, 2 warnings`
  - real GDF path 現在會在 channel selection 與 montage confirmation 直接附帶 ambiguity guardrail wording
- `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/integration/io/test_io_integration.py -q`
  - 結果：`31 passed, 13 warnings`
  - 其中 `A01T.gdf` 相關 warning 仍存在，但 import slice 持續通過，且高層 summary 現在也會帶出 `gdf_duplicate_channel_files` / `gdf_duplicate_channel_details`

### 測試覆蓋

- `tests/integration/io/test_io_integration.py`
- `tests/integration/controller/test_preprocess_controller.py`
- `tests/integration/pipeline/test_all_real_tools.py`
- `tests/unit/backend/load_data/test_raw_data_loader.py`
- `tests/unit/backend/load_data/test_raw.py`
- `tests/unit/backend/controller/test_dataset_controller.py`
- `tests/unit/backend/controller/test_preprocess_controller.py`
- `tests/unit/backend/test_facade_coverage.py`
- `tests/unit/llm/tools/real/test_real_tools.py`
- `Raw.get_runtime_signals()` / `Raw.has_runtime_signals()`
- `Raw.get_runtime_detail()` / `Raw.has_runtime_detail()`
- `PreprocessController.get_runtime_diagnostics()`
- `BackendFacade.get_preprocess_diagnostics()`

### 備註

這個問題目前已從「模糊的第三方 warning」提升成「XBrainLab import layer 會明確記錄，且 `Raw` 物件可程式化讀取的 runtime signal + structured detail」，但 underlying channel identity 問題本身還沒解決。

目前更窄的 repair decision 已經做完：

- preprocess-side diagnostics / guardrails 現在已接上，所以 `AQ-001` 不再卡在「下游看不到 ambiguity」
- 下一步不再是預設直接做 normalization，而是把較高風險的 GDF duplicate/generic channel-name normalization 留在 deferred decision；只有當後續 preprocess / montage / mismatch evidence 顯示 guardrail 仍不足時，再重新升級
