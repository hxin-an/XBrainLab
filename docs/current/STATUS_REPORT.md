# XBrainLab Status Report

Last updated: `2026-04-19`

這份文件是「目前狀態快照」，不是版本發布紀錄。

它主要回答這幾件事：

- 最近改了什麼
- 專案現在進度在哪
- 目前卡住什麼
- 下一步應該做什麼

版本或發布層級的變更，請看 `CHANGELOG.md`。

## 快照

- 目前階段：`Prep Gate`
- 目前分支：`codex/stabilization-autopilot`
- 碩論主線：先穩定化，再重設 `tool-call agent`，並持續補強嚴謹驗證
- 目前設計主入口：`docs/decisions/`

## 最新變更

以下依照「最新且有意義」的變化往下排：

1. real GDF duplicate-channel signal 已補上更誠實的 import-level observability：
   - `A01T.gdf` 仍會出現 MNE duplicate-name warning
   - `load_gdf_file()` 現在也會額外記錄 XBrainLab 自己的 warning，明確指出匯入依賴了 MNE auto-rename
   - 相關驗證目前是：
     - `tests/unit/backend/load_data/test_raw_data_loader.py` -> `5 passed`
     - `tests/integration/io/test_io_integration.py` -> `25 passed, 7 warnings`
2. unattended UI 驗證現在有 repo 內可重用的 heartbeat-safe 路徑：
   - heartbeat-style UI pytest 失敗點已縮小到 Qt platform plugin / matplotlib cache 環境，而不是單純 repo 測試壞掉
   - 新增 `scripts/dev/run_ui_pytest.sh`
   - `scripts/dev/run_tests.py` 的 `ui` 路徑現在也會自動套 `offscreen + --capture=sys`
   - 代表性驗證：
     - `scripts/dev/run_ui_pytest.sh tests/integration/ui/test_dialog_acceptance.py -q` -> `4 passed`
     - `python scripts/dev/run_tests.py ui` -> `742 passed, 15 skipped, 1 warning`
3. Repo 與文件結構已重整成較清楚的主工作面：
   - root `README.md`
   - `docs/current/`
   - `docs/decisions/`
   - `docs/workflows/`
   - `docs/history/`
   - `docs/guides/`
   - `docs/api/`
   - `docs/archive/`
4. 文件工具鏈已補齊並一致化：
   - markdown 本地連結掃描通過，`BROKEN=0`
   - MkDocs nav 目標檢查通過，`MISSING=0`
   - `poetry install --with docs` 已可正常使用
   - `poetry run mkdocs build` 已可在目前 workspace 成功執行
5. 內建 assistant 的產品定位已更明確：
   - Codex 是這個 repo 的外部開發助手
   - app 內 assistant 是 workflow-aware 的軟體操作 agent
   - tool calls 是 app 內 assistant 的執行骨幹
6. AI assistant 的啟動路徑變得更誠實也更穩定：
   - 更早套用已儲存設定
   - backend 載入前就先做 local runtime readiness 檢查
   - 更早偵測 CUDA 不可用，讓 local backend 能更乾淨地 fallback
7. Prep gate 的 UI 驗證已明顯補強：
   - headless panel baseline capture 可用
   - 四個高優先 dialog 已有 acceptance coverage
   - shared refresh propagation 已有直接 bridge-level smoke coverage

## 為什麼這不是 Changelog

- `STATUS_REPORT` 是碩論專案「現在狀態」的摘要
- `CHANGELOG.md` 是版本與發布歷史
- `STATUS_REPORT` 應該可以隨狀況自由重寫
- `CHANGELOG.md` 應該維持 append-only、偏 release 導向

簡單講：

- 如果你想看「現在真實狀態是什麼」，看這份
- 如果你想看「某個版本正式改了什麼」，看 `CHANGELOG.md`

## 目前狀態

### 1. 穩定化

目前位置：

- prep 工作已經把專案往較可信的穩定化基線推進不少
- app 啟動、capture baseline、dialog coverage、refresh smoke coverage、real-data IO validation 都比之前更穩

目前已完成：

- headless startup 可走到 `MainWindow initialized`
- UI baseline capture 已不再產生全黑圖，而是可用 artifact
- shell、五個主 panel、AI assistant open state 都可在 `xvfb-run` 下 capture
- top-level shell 與 panel happy paths 已有 Qt integration slice 的 runtime 證據
- 四個最高優先 dialog 已有 headless acceptance coverage：
  - `LabelMappingDialog`
  - `EventFilterDialog`
  - `EpochingDialog`
  - `TrainingSettingDialog`
- shared refresh propagation 已補到最高價值的 downstream path：
  - dataset events -> `PreprocessPanel`
  - dataset events -> `TrainingPanel`
  - `training_stopped` -> `EvaluationPanel`
  - `training_stopped` -> `VisualizationPanel`

主要驗證證據：

- `tests/unit/scripts/test_capture_ui_baseline.py`: `4 passed`
- `tests/integration/ui/test_e2e_qtbot.py`: `20 passed`
- `tests/integration/ui/test_dialog_acceptance.py`: `4 passed`
- `tests/unit/ui/test_panel_event_bridges.py`: `4 passed`
- `python scripts/dev/run_tests.py ui`: `742 passed, 15 skipped, 1 warning`
- `tests/unit/scripts/test_capture_ui_baseline.py tests/integration/io/test_io_integration.py`: `27 passed, 7 warnings`

### 2. Tool-Call Agent 方向

目前位置：

- 專案已經有比較乾淨、比較貼近碩論主線的未來 agent 重設方向

目前已完成：

- `AGENTS.md` 已明確寫出這個 repo 是碩論實作 workspace
- `docs/decisions/README.md` 已成為正式 decision-record 入口
- `ADR-011` 固定了碩論工作順序
- `ADR-012` 固定了 repo / docs 結構重整方向
- `ADR-013` 固定了 app 內 assistant 的產品定義
- 文獻定位已更清楚區分：
  - Codex 是外部開發助手
  - app 內 assistant 是 XBrainLab 上的 workflow operator
- 產品定義也更明確：
  - human user 和 in-app assistant 是同一套軟體能力面的兩種控制模式
  - tool-call surface 可以依 workflow intent 重新設計，不需要被舊工具邊界綁住

### 3. 文件系統

目前位置：

- 專案文件已從扁平混雜狀態，整理成比較專業的工作結構

目前已完成：

- root `README.md` 已存在
- package metadata 已改指向 root `README.md`
- 舊的 `architecture/`、`agent/`、`development/`、`reference/` 已搬到 `docs/archive/`
- install、quickstart、contributing 已搬到 `docs/guides/`
- MkDocs navigation 已對齊新結構

驗證證據：

- markdown 本地連結掃描：`BROKEN=0`
- MkDocs nav target existence check：`MISSING=0`
- `poetry run mkdocs build`：通過

### 4. 驗證準備度

目前位置：

- 驗證已開始被當成碩論工作流的一部分，而不是實作完之後才補的收尾

目前已完成：

- 目前計畫已明確分出：
  - stabilization
  - tool-call agent redesign
  - rigorous validation
- 現行文件入口也已更清楚標出未來實驗與設計決策該放哪裡

## 目前阻塞與風險

- unattended UI pytest 在目前 Codex workspace 仍需要顯式 headless Qt 環境；目前推薦直接走 `scripts/dev/run_ui_pytest.sh`
- 先前的 `pytest fd capture` teardown 問題目前變成間歇性 / 未穩定重現狀態，因此還留在 triage，但已不是最清楚的當前 blocker
- real GDF fixtures 仍會出現 duplicate channel name warnings；目前只是 observability 更清楚，underlying channel identity ambiguity 仍未解
- public BBCI `O3VR.gdf` 仍會出現 MNE annotation-range warning，但 import 本身是成功的
- AI assistant 現在已朝 local-first 方向前進，但這個 workspace 仍缺真正可用的 cached local model，因此還不能做完整 local end-to-end startup
- dialog realism 雖然比之前強很多，但全域 `QDialog.exec` patch 仍表示 desktop-manual 行為和 unit harness 不完全等價

## 最近最值得記住的實際進展

如果你只想記最重要的最新變化，就是這四件事：

1. docs 已整理成比較清楚的專業結構
2. docs toolchain 已修好並可 build
3. in-app assistant 的產品定位已釐清
4. prep-gate coverage 與 local-AI startup honesty 都有進步

## 立刻下一步

1. 繼續完成 prep-gate runtime-signal triage，尤其是 real GDF channel identity、unattended UI validation、visualization headless fragility 這幾條。
2. 繼續補 local-only AI bootstrap，直到這個 workspace 能用真實 local model 啟動 assistant。
3. audit 目前的 tool surface，判斷哪些邊界該合併、刪除或重設，讓它更符合 shared human/agent control。
4. 定出 redesigned tool-call agent 的 evaluation structure，讓驗證從方向性描述變成具體設計。
