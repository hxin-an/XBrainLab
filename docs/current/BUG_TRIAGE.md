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

#### [BUG-ENV-001] Visualization 相關測試在 headless 模式下不穩定

- Priority: P2
- Area: Visualization
- Type: Test infrastructure
- Status: Confirmed
- Source: Test failure/skips

### 症狀

某些 visualization 與 main-window 測試在 headless 執行時會被刻意 skip，因為 VTK / Qt 互動不穩定。

### 重現方式

執行：

```bash
/home/administrator/.local/bin/poetry run pytest tests/unit/ui -q
```

### 預期

Visualization 相關測試應該要嘛穩定可跑，要嘛明確隔離並記錄其限制。

### 實際情況

目前這個 suite 會以 `15 skipped` 結束，其中包含與 headless 環境下 VTK / Qt 行為有關的 skip。

### 影響

這會降低我們對 visualization 相關修改的信心，也代表某些 layout / rendering regression 可能躲過日常快速測試。

### 可能範圍

- `tests/unit/ui/test_visualization.py`
- `tests/unit/ui/test_visualization_panel_redesign.py`
- `tests/unit/ui/test_main_window.py`
- visualization widgets and VTK/PyVista integration

### 證據

在 WSL2 本地於 `2026-04-18` 觀察到：`718 passed, 15 skipped`。

### 測試覆蓋

目前仍有行為層 coverage，但沒有完整 rendering 信心。

### 備註

它本身未必是 release blocker，但確實是之後修復工作中的常駐風險區。

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
- Status: Confirmed
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
- 但在新的 quality dashboard refresh 中再次失敗：
  - `/home/administrator/.local/bin/poetry run pytest tests/integration/io/test_io_integration.py -q`
  - 結果：在 `_pytest/capture.py` teardown 階段再次拋出 `FileNotFoundError`
- 同樣地，`tests/unit/scripts/test_update_quality_dashboard.py -q` 也再次踩中同一條 capture teardown 問題

目前在這個 workspace 裡，建議優先使用 `--capture=sys` 作為 local validation workaround，`-s` 只保留作為 fallback。

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

#### [BUG-AGENT-001] AI assistant 的 local startup 忽略已儲存設定，並把 local runtime failure 延後到初始化時才暴露

- Priority: P1
- Area: Agent
- Type: Broken interaction
- Status: In progress
- Source: Runtime log

### 症狀

打開 AI assistant 時，dock 可能先被打開，接著才在 backend startup 階段失敗，因為第一次初始化路徑會預設走 local mode，而且要等 backend load 已開始後，才發現缺少 local runtime 套件。

### 重現方式

執行：

```bash
xvfb-run -a /home/administrator/.local/bin/poetry run pytest -s tests/integration/ui/test_e2e_qtbot.py -q
```

`TestAIAssistantDock.test_toggle_ai_dock` 這條路徑會觸發第一次開啟初始化；當 local startup 尚未準備好時，就會在這裡發出 failure signal。

### 預期

打開 AI assistant 時應該尊重已儲存的 startup mode；而依目前 local-only 方向，應該在真正嘗試 local backend load 之前，就先以清楚的 preflight 訊息快速失敗。

### 實際情況

先前 dock toggle 路徑會進到 local-model startup，並記錄：

```text
Model Load Error: ... requires `accelerate`
```

但整體 UI integration slice 仍然會通過。

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

### 測試覆蓋

- `tests/integration/ui/test_e2e_qtbot.py`
- `tests/unit/llm/core/test_config.py`
- `tests/unit/llm/agent/test_worker.py`
- `tests/unit/ui/chat/test_chat_panel.py`
- `tests/unit/ui/dialogs/test_model_settings.py`

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

`2026-04-19` 的額外環境收斂：

- `/home/administrator/.local/bin/poetry install --with llm --no-interaction` now succeeds in the current workspace
- `LLMConfig.missing_local_runtime_packages()` now returns `[]`
- the host still reports `torch.cuda.is_available() == True`, but a direct CUDA probe fails with `RuntimeError: CUDA error: no kernel image is available for execution on the device`
- 這個 workspace 裡預期的 `Qwen/Qwen2.5-7B-Instruct` local model cache path 仍不存在

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

### 影響

這不會立即造成 crash，但可能扭曲跨檔 channel matching，也會讓後續與 selection、montage、mismatch diagnostics 相關的失敗更難判讀。

### 可能範圍

- `XBrainLab/backend/load_data/raw_data_loader.py`
- `XBrainLab/backend/load_data/raw.py`
- 對 channel name 敏感的 preprocess 與 dataset workflow

### 證據

於 `2026-04-19` 本地在建立新 multi-extension fixture baseline 的過程中，於 GDF real-data import 與 real-data integration test 持續觀察到。

同日進一步確認：

- `/home/administrator/.local/bin/poetry run python - <<'PY' ... load_gdf_file('tests/data/A01T.gdf') ... PY`
  - 結果：
    - `nchan 25`
    - `unique 25`
    - first channels include `EEG-0`, `EEG-1`, ...
    - logger now emits an explicit XBrainLab warning describing the MNE auto-rename dependency
- `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/integration/io/test_io_integration.py -q`
  - 結果：`25 passed, 7 warnings`
  - 其中 `A01T.gdf` 相關 warning 仍存在，但 import slice 持續通過

### 測試覆蓋

- `tests/integration/io/test_io_integration.py`
- `tests/integration/controller/test_preprocess_controller.py`
- `tests/integration/pipeline/test_all_real_tools.py`
- `tests/unit/backend/load_data/test_raw_data_loader.py`

### 備註

這個問題目前已從「模糊的第三方 warning」提升成「XBrainLab import layer 會明確記錄的 runtime signal」，但 underlying channel identity 問題本身還沒解決。

下一步應在兩條方向中擇一：

- 對 GDF duplicate/generic channel names 做更有意識的 normalization
- 或把這類 ambiguous channel identity 以更正式的 metadata / UI signal 暴露給 downstream workflow
