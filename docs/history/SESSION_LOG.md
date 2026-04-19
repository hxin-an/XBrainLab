# XBrainLab 工作日誌

這份日誌記錄重要進展，讓修復與穩定化工作可以在不同 session 之間順利接續。

## 2026-04-19

### 品質看板改成快慢雙軌型別 gate

- 將 `basedpyright` 加入 Poetry dev 依賴，並在 `pyproject.toml` 補上 repo-local 設定
- 建立 `.basedpyright/baseline.json`，把目前既有的 repo-wide 型別債記成 baseline，而不是假裝它們不存在
- `scripts/dev/update_quality_dashboard.py` 現在預設跑 fast dashboard：
  - `ruff`
  - `basedpyright`
  - `architecture compliance`
  - startup / UI / real-data runtime slices
- 新增 `--include-slow-checks`，讓 full dashboard 可以額外把 `mypy` 一起跑進來
- 在 `pyproject.toml` 補上：
  - `poe quality-dashboard-full`
  - `poe typecheck-fast`
  - `poe mypy-daemon`
  - `poe check-full`
- 這次的策略不是把舊 `mypy` 問題藏起來，而是把：
  - 「高頻抓新退化」
  - 「較慢持續還舊債」
  拆成兩條明確流程
- 途中也修正了一個新的 dashboard 自己的環境問題：
  - `update_quality_dashboard.py` 一度把 matplotlib cache 放到 repo 內 `.codex/matplotlib-codex`
  - 但這個 workspace 已經存在一個 `.codex` 檔案，因此會直接觸發 `NotADirectoryError`
  - 現在已改回 `/tmp/matplotlib-codex`
- 另外補上 live report 的 `profile` 欄位，讓 `artifacts/quality/latest.md` 能明確標出本次是 `fast` 還是 `full`
- 這一輪驗證結果：
  - `tests/unit/scripts/test_update_quality_dashboard.py` -> `7 passed`
  - `basedpyright` -> `0 errors, 0 warnings, 0 notes`
  - `python scripts/dev/update_quality_dashboard.py` -> `FAIL`
    - fast profile 的紅燈是 `ruff check .` 與 real-data IO integration 的 default-capture teardown
  - `python scripts/dev/update_quality_dashboard.py --include-slow-checks` -> `FAIL`
    - full profile 另外還會顯示 `mypy XBrainLab/` 的 `7 errors in 5 files`

## 2026-04-18

### 環境與接手基線

- 為專案準備好 WSL2 開發環境
- 安裝 Poetry 與專案依賴
- 安裝 PyQt headless GUI 所需工具
- 驗證 app 可以啟動到 `MainWindow`
- 在 WSL headless 模式下驗證 UI 單元測試基線

### 接手治理文件

- 建立：
  - `AGENTS.md`
  - `docs/workflows/TAKEOVER.md`
  - `docs/workflows/TESTING_STRATEGY.md`
  - `docs/workflows/UI_BASELINE.md`
  - `docs/workflows/WORKFLOWS.md`
  - `docs/current/BUG_TRIAGE.md`
  - `docs/workflows/RISK_CLUSTERS.md`
  - `docs/workflows/DIALOG_MATRIX.md`
  - `docs/workflows/COVERAGE_GAPS.md`
  - `docs/history/BACKLOG.md`

### 共用 shell 安全性

- 擴充 `tests/unit/ui/test_main_window_sync.py`
- 新增 smoke protection，涵蓋：
  - 導覽狀態同步
  - 僅目標 panel 刷新行為
  - 當 panel 缺少 `update_panel()` 時仍可安全導覽
- 驗證：
  - `tests/unit/ui/test_main_window_sync.py`
  - `tests/integration/ui/test_ui_refresh.py`

### 視覺基線工作

- 新增 `scripts/dev/capture_ui_baseline.py`
- 建立 `artifacts/ui/`
- 產生第一份基線產物
- 確認目前 screenshot 輸出是全黑，因此暫時不可信

### 匯入與 label 穩定性修復

- 改善 `.mat` label 載入，優先選擇像 `classlabel` 這種較像 label 的變數，而不是盲目取第一個變數
- 補上 multi-variable `.mat` 檔的 coverage，避免第一個變數不是實際 label array 時誤判
- 改善 UI 回饋，避免 label import 套用 0 個 label 時無聲失敗
- 新增後端警告紀錄，用於舊版 label 數量不一致情況
- 讓 `EventLoader` 在以下情況清楚失敗：
  - 載入的 label sequence 是空的
  - event filtering 選完後把所有 EEG events 都移除了
- 收斂 alignment truncation warning 邏輯，讓 mismatch 記錄更準確
- 移除 `ImportLabelDialog` 對純數字 label 的假設，讓字串型 sequence label 可以被檢查與 mapping，而不是在 `int(...)` 時直接失敗
- 更新 `EventLoader` sequence mode，讓類別 / 字串 labels 能轉成穩定整數 event ID，同時保留帶引號數字字串的原始 code
- 擴充 label import service typing，讓修復後的路徑端到端一致
- 修正匯入 label 檔只用 basename 當 key 的問題，讓不同資料夾裡的同名檔可以共存
- 在 label mapping 相關畫面加入完整路徑 tooltip，讓多資料夾匯入仍可檢查，同時不改變 layout 結構
- 修正 `LabelMappingDialog` 的 auto-sort，讓它優先使用正規化後的精確匹配，而不是像 `sub01` vs `sub010` 這種脆弱的 substring-first 比對
- 修正 `EventFilterDialog`，避免不同 dataset 的舊選擇殘留，導致新 dataset 開啟時所有 event 都被默默取消勾選
- 阻止 `EventFilterDialog` 接受空的 keep-list，避免無聲地同步成零事件
- 移除 `DatasetActionHandler.import_label()` 假設第一個 label file 能代表整批 label 的做法
- 讓混合 timestamp / sequence 的 label batch 清楚失敗，而不是被第一個檔誤分類
- 修正 batch mapping dialog 取消時被誤顯示成假的 "No Labels Applied" warning
- 重構 `BackendFacade.attach_labels()`，改用共用 label-import 行為，而不是維持自己的 basename-only / numeric-only attach 路徑
- 新增對 epoch-style `.fif` 的支援：當 `read_raw_fif()` 失敗時，回退到 `mne.read_epochs()`
- 新增 `.fif.gz` 支援：raw-data loader factory 改成比對最長已註冊副檔名，而不是只看最後一段副檔名
- 調整 event-filter smart suggestion，改成彙整所有 candidate raw file，而不是只信任第一個
- 改善 dataset mismatch diagnostics，讓 channel / sfreq / type / duration mismatch 現在都會同時報出 expected 與 actual 值，並附上檔名
- 補上聚焦 coverage，涵蓋：
  - `ImportLabelDialog` 的字串 sequence label
  - `EventLoader` 的類別字串 label
  - 帶引號數字字串保留原始 event code
  - 不同資料夾的同 basename label files
  - `LabelMappingDialog` 的模糊 label auto-match
  - `EventFilterDialog` 的 stale 與 empty selection
  - `DatasetActionHandler` 的 batch import mode 分析
  - facade attach-label delegation 與 full-path mapping
  - `.fif` epoch fallback 與 `.fif.gz` 支援
  - `DatasetActionHandler` 的 multi-file smart-filter suggestion
  - `RawDataLoader` 更詳細的 mismatch diagnostics

### 驗證結果

- `tests/unit/backend/load_data/test_label_loader.py` 與 `test_label_loader_coverage.py`：通過
- `tests/unit/backend/services/test_label_import_service.py`：通過
- `tests/unit/backend/controller/test_dataset_ctrl.py` 與 `test_dataset_controller.py`：通過
- `tests/unit/ui/test_ui_misc.py`：通過
- `tests/unit/backend/load_data/test_event_loader.py` 與 `test_event_loader_strict.py`：通過
- `tests/unit/backend/load_data/test_label_import.py`：通過
- `tests/unit/ui/dataset/test_import_label.py`：通過

### 下一步建議

1. 檢查 raw-loader 對其他常見壓縮格式或 sidecar-based 格式是否仍有假設
2. 尋找由 channel-name 一致性而不是 channel-count 一致性引起的 dataset import 問題
3. 開始規劃 local-only AI 模式清理與 remote API 移除方向

## 2026-04-19

### 品質看板強化與 UI reference gate

- 將 `ruff`、`mypy`、`architecture compliance` 正式接進 `scripts/dev/update_quality_dashboard.py`
- 將核心 UI baseline 從「檔案存在且不是黑圖」升級成和 `tests/baselines/ui/` approved references 比較
- 重新以 live capture 重產：
  - `artifacts/ui/main-window-initial.png`
  - `artifacts/ui/panel-dataset.png`
  - `artifacts/ui/panel-preprocess.png`
  - `artifacts/ui/panel-training.png`
  - `artifacts/ui/panel-evaluation.png`
  - `artifacts/ui/panel-visualization.png`
  - `artifacts/ui/ai-assistant-open.png`
- 將同一批核心畫面升格為 repo 內 reference baseline：
  - `tests/baselines/ui/*.png`
- 在這個 checkout 真正安裝 pre-commit hook：
  - `pre-commit installed at .git/hooks/pre-commit`
- 聚焦驗證：
  - `tests/unit/scripts/test_update_quality_dashboard.py` -> `7 passed`
  - `python tests/architecture_compliance.py` -> `PASS`
  - `python scripts/dev/update_quality_dashboard.py` -> `overall FAIL`
- 這次 dashboard refresh 明確暴露的紅燈：
  - `ruff check .` -> `21 errors`, `10` 可 auto-fix
  - `mypy XBrainLab/` -> `7 errors in 5 files`
  - `tests/integration/io/test_io_integration.py -q` 的 default capture teardown 仍失敗

### UI baseline 定義澄清

- 明確把目前的 UI baseline 分成三層：
  - `docs/workflows/UI_BASELINE.md` 是人類可讀的結構基準
  - `artifacts/ui/` 是每次驗證時重產的 live evidence
  - `tests/baselines/ui/` 是未來正式 reference screenshots 的固定位置
- 明確記錄當時 quality dashboard 對 UI 做的是 structural-health check，不是 golden screenshot diff
- 把「把 UI baseline 升級成真正 regression gate」加入 prep queue
- 這讓後續的 UI 監測不會再把「現在能重產 screenshot」和「我們已經有正式對照基準」混為一談

### 真實資料基線確認

- 確認 repo 已帶有三個 checked-in 的真實 EEG fixture：
  - `tests/data/A01T.gdf`
  - `tests/data/A02T.gdf`
  - `tests/data/A03T.gdf`
- 確認對應 label fixture 位於 `tests/data/label/`
- 確認目前真實資料體積仍相對節制，三個 GDF 檔總共約 98 MB

### 訓練 / 執行期穩定化

- 重現了一個非 load-data 類錯誤：這台主機上 `torch.cuda.is_available()` 回傳 `True`，但實際 training 仍會失敗，因為目前安裝的 PyTorch build 無法在偵測到的 RTX 5070 Ti 上真正執行
- 更新 `TrainingOption`，讓它在要求 CUDA device 時先做 probe；若 device 雖存在但不可用，則以 warning 方式回退到 CPU
- 在 `tests/unit/backend/training/test_option.py` 補上此 fallback path 的單元測試
- 直接在這台機器上驗證，要求 GPU 的 `TrainingOption` 現在會解析成：
  - `use_cpu=True`
  - `gpu_idx=None`
  - `device=cpu`

### 真實資料整合測試修復

- 修正兩個 integration test，它們原本誤找 `tests/integration/data/`，而不是 repo 內實際存在的 `tests/data/`
- 解除以下測試對 real-data coverage 的 skip：
  - `tests/integration/pipeline/test_real_data_pipeline.py`
  - `tests/integration/io/test_io_integration.py`

### 驗證結果

- `tests/unit/backend/training/test_option.py`：42 passed
- `tests/integration/pipeline/test_pipeline_integration.py`
- `tests/integration/pipeline/test_real_data_pipeline.py`
- `tests/integration/io/test_io_integration.py`
  - 結果：5 passed
- `tests/integration/controller/test_preprocess_controller.py`
- `tests/integration/pipeline/test_all_real_tools.py`
  - 結果：15 passed

### 重要執行期訊號

- 真實 GDF workflow 仍會持續噴出 MNE duplicate channel name warning（`EEG`），這是下一個很值得深入調查的 real-data 問題
- PyTorch 的 CUDA compatibility warning 在 fallback 前仍然會出現，但 training 路徑至少不再因此直接 crash，而是降級到 CPU

### 下一步建議

1. 研究重複 channel name warning 是否會進一步影響 channel selection、montage 或儲存後 diagnostics
2. 擴大 real-data validation，補上對 checked-in fixture 的 label-attached dataset generation 與 training smoke
3. 在 load-data 之外持續做 broader stabilization，例如 local-only AI mode cleanup 或黑圖 screenshot baseline 問題

### 多格式真實資料 fixture 擴充

- 在 `tests/data/multiformat/` 下建立一組體積小的 cross-format fixture pack
- 所有 fixture 都取自真實 `A01T.gdf` 記錄中的 15 秒、8 channel 片段，兼顧真實訊號與小體積
- 新增以下 checked-in 副檔名：
  - `.fif`
  - `.fif.gz`
  - epoch-style `.fif`
  - `.edf`
  - `.bdf`
  - `.vhdr` 搭配 `.eeg` 與 `.vmrk`
  - `.set`
- 在 `tests/data/multiformat/README.md` 記錄 fixture 的來源與用途
- 新增資料量保持很小，整組約 696 KB

### 多格式驗證結果

- 手動確認 `load_raw_data()` 可成功載入：
  - `A01T.gdf`
  - `A01T-mini-real_raw.fif`
  - `A01T-mini-real_raw.fif.gz`
  - `A01T-mini-real.edf`
  - `A01T-mini-real.bdf`
  - `A01T-mini-real.vhdr`
  - `A01T-mini-real.set`
  - `A01T-mini-real-epo.fif`
- 手動確認 `BackendFacade.load_data()` 也能成功處理同一批副檔名
- 擴充 `tests/integration/io/test_io_integration.py`，讓 real-data integration slice 同時涵蓋：
  - 所有 compact real fixture 的 direct loader validation
  - 同一批副檔名的 facade-level dataset import

### 補充驗證結果

- `tests/integration/io/test_io_integration.py`：19 passed

### 新的執行期訊號

- 真實 BCI Competition GDF fixture 仍會因重複 channel name 觸發 MNE warning，現在已在 triage 裡成為獨立條目，適合作為下一個 real-data 問題

### Codex 執行環境與本地 workspace 基線

- 建立並切換到工作分支 `codex/stabilization-autopilot`
- 建立 thread heartbeat automation `xbrainlab-autopilot`，最初採 30 分鐘節奏，讓穩定化工作能在同一對話中持續進行
- 為目前 `/mnt/d/repos/XBrainLab` workspace 安裝 Poetry environment，使本地 Codex thread 可以直接從這份 checkout 執行專案
- 以以下指令確認目前 workspace 的 startup smoke：
  - `timeout 25s xvfb-run -a /home/administrator/.local/bin/poetry run python run.py`
  - 結果：可以啟動到 `MainWindow initialized`，並存活到 timeout
- 再次確認視覺基線阻塞點：
  - `xvfb-run -a /home/administrator/.local/bin/poetry run python scripts/dev/capture_ui_baseline.py`
  - 結果：仍以 `Captured screenshot is nearly all black` 結束
- 確認聚焦驗證切片在這個 workspace 中用 `-s` 可通過：
  - `tests/unit/backend/training/test_option.py`：42 passed
  - `tests/unit/ui/test_main_window_sync.py`：8 passed
  - `tests/integration/io/test_io_integration.py`：19 passed
- 同時辨識出新的本地驗證 blocker：
  - 預設 `pytest` capture 會在 `/mnt/d` Codex workspace 的 teardown 階段失敗，但同一批 slice 用 `-s` 可通過

### 下一步建議

1. 更新 repo 文件，反映新的 Codex harness、prep gate、branch policy 與本地驗證假設
2. 修掉黑色 screenshot baseline，讓 `artifacts/ui/` 重新可信
3. triage 或修復目前 workspace 的預設 pytest capture teardown failure

### 視覺基線修復

- 將脆弱的 `scrot` 路徑改成直接抓取 Qt main window 的方式，更新 `scripts/dev/capture_ui_baseline.py`
- 在 `tests/unit/scripts/test_capture_ui_baseline.py` 補上聚焦的黑圖 heuristic 測試
- 重新執行：
  - `xvfb-run -a /home/administrator/.local/bin/poetry run python scripts/dev/capture_ui_baseline.py`
  - 結果：`artifacts/ui/main-window-initial.png` 已從全黑畫面變成可見的 main-window artifact
- 執行組合驗證：
  - `tests/unit/scripts/test_capture_ui_baseline.py`
  - `tests/unit/backend/training/test_option.py`
  - `tests/unit/ui/test_main_window_sync.py`
  - `tests/integration/io/test_io_integration.py`
  - 結果：`71 passed, 5 warnings`

### 五個主 panel 擷取與公開 fixture 擴充

- 更新 capture helper，讓它現在會輸出：
  - `artifacts/ui/main-window-initial.png`
  - `artifacts/ui/panel-dataset.png`
  - `artifacts/ui/panel-preprocess.png`
  - `artifacts/ui/panel-training.png`
  - `artifacts/ui/panel-evaluation.png`
  - `artifacts/ui/panel-visualization.png`
- 建立 `scripts/dev/fetch_public_eeg_fixtures.py`，下載小型跨來源 EEG fixture 組到 `tests/data/public/`
- 在 `tests/data/public/README.md` 記錄這批 public fixture
- 本地下載並驗證三個外部 fixture：
  - PhysioNet `physionet-eegmmidb-S008R01.edf`
  - BBCI `bbci-competition-iii-O3VR.gdf`
  - SCCN `sccn-eeglab_data.set`
- 擴充 `tests/integration/io/test_io_integration.py`，讓 real-data IO 驗證切片在 fixture 存在時，也會涵蓋這些公開 EDF / GDF / SET
- 驗證結果：
  - `tests/integration/io/test_io_integration.py`
  - 結果：`25 passed, 7 warnings`

### 讓使用者能追得上的報告頁

- 新增 `docs/current/STATUS_REPORT.md` 作為精簡的人類可讀進度快照
- 更新 Codex 執行環境文件，要求之後工作循環與 heartbeat run 都維護這份報告
- 將 heartbeat cadence 從 30 分鐘改成 10 分鐘
- 重新整理 `docs/current/STATUS_REPORT.md`，讓它按已同意的長期計畫分段，而不是平鋪式筆記
- 在重整報告後重新驗證：
  - `xvfb-run -a /home/administrator/.local/bin/poetry run python scripts/dev/capture_ui_baseline.py`
    - 結果：六張 baseline image 全部成功重產
  - `/home/administrator/.local/bin/poetry run pytest -s tests/unit/scripts/test_capture_ui_baseline.py tests/integration/io/test_io_integration.py -q`
    - 結果：`27 passed, 7 warnings`

### 控制面澄清

- 澄清兩種 assistant 介面不應再被混在一起：
  - Codex 是這個 repo 外部的開發助手
  - app 內 assistant 是 XBrainLab 裡的具 workflow awareness 的軟體操作 agent
- 澄清 human user 與 app 內 assistant 應視為操作同一組軟體能力面的兩種控制模式
- 澄清目前的 tool-call taxonomy 可以重設，不應因慣性被保留；未來應回到 workflow intent 重新思考
- 新增 `docs/decisions/ADR-013-in-app-assistant-product-definition.md`，作為未來 app 內 assistant 重設計的產品定義錨點

### Heartbeat 執行層中斷

- 有幾個 heartbeat 週期一度無法持續工作，因為 thread 暫時無法啟動基本 shell process
- 恢復後確認：
  - `/bin/sh` 與 `/bin/bash` 都重新可用
  - repo 內的 autopilot docs 與 active-queue 內容不是根因
  - 因此，先前 heartbeat 卡住比較符合暫時性的 Codex / desktop 執行層問題，而不是 repo 設定錯誤

### 真實 GDF 重複 channel 可觀測性

- 直接重跑 `load_gdf_file('tests/data/A01T.gdf')`，確認匯入後 channel list 內會出現像 `EEG-0`、`EEG-1` 這種產生式名稱，只有少數明確名稱如 `EEG-Fz`、`EEG-C3`、`EEG-Cz`、`EEG-C4`、`EEG-Pz`
- 確認這個執行期訊號不只是 MNE 的一般 warning：
  - `load_gdf_file()` 現在會在 GDF import 依賴 MNE 自動重命名重複 channel name 時，額外記錄 XBrainLab 自己的 warning
- 在 `tests/unit/backend/load_data/test_raw_data_loader.py` 補上這個 signal 的單元測試
- 重新執行：
  - `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/unit/backend/load_data/test_raw_data_loader.py -q`
    - 結果：`5 passed`
  - `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/integration/io/test_io_integration.py -q`
    - 結果：`25 passed, 7 warnings`
- 目前結論：
  - 這仍然是開放中的 dataset / workflow 問題，不是 crash
  - 可觀測性雖然變好了，但底層不明確的 channel identity 仍未真正解決

### Agent stack 澄清

- 澄清明確的 agent 端 stack 應該放在 `.agents/` 下，而不只是 `docs/`
- 新增 `.agents/stack.md`，記錄：
  - 預設採用的 skills
  - 僅在條件成立時使用的 skills
  - 規則政策
  - heartbeat 閱讀順序
- 更新 `AGENTS.md`、`.agents/runbooks/setup.md`、`.agents/runbooks/autopilot.md`，讓 unattended work 在繼續前先讀 `.agents/stack.md`
- 擴充外部設置依據，納入：
  - OpenAI Codex docs
  - Anthropic Claude Code docs
  - GitHub agent-skill docs
  - vendor-neutral `agentmd` repository

### 完整的人類文件 / agent 文件切分

- 將 canonical agent runtime surface 移到：
  - `.agents/runbooks/setup.md`
  - `.agents/runbooks/autopilot.md`
  - `.agents/runbooks/active-queue.md`
- 保留 `docs/` 作為人類閱讀面，並新增 `docs/current/PLAN.md`
- 將這些 root-level doc 改為相容性 stub：
  - `.agents/runbooks/setup.md`
  - `.agents/runbooks/autopilot.md`
  - `.agents/runbooks/active-queue.md`
- 為重複性 workflow 建立 repo-local skills：
  - `.agents/skills/xbrainlab-prep-gate/SKILL.md`
  - `.agents/skills/xbrainlab-repair-loop/SKILL.md`
- 更新正式閱讀順序，讓 unattended work 先讀 `.agents/`，再讀人類計畫與進度文件

### Skill stack 擴充

- 更深入檢視官方與高訊號 skill 生態：
  - OpenAI Codex docs 的 skills 與 Docs MCP
  - Anthropic 關於 focused subagent 與 project-scoped versioned assets 的文件
  - `anthropics/skills`
  - Awesome GitHub Copilot 的公開 skill directory
- 新增更窄、更聚焦的 repo-local skills，而不只停留在 `prep` 與 `repair`：
  - `.agents/skills/xbrainlab-workflow-baseline/SKILL.md`
  - `.agents/skills/xbrainlab-dialog-audit/SKILL.md`
  - `.agents/skills/xbrainlab-real-data-validation/SKILL.md`
  - `.agents/skills/xbrainlab-refresh-smoke/SKILL.md`
- 為 repo-local skills 新增 `agents/openai.yaml` metadata，讓本地 skill surface 更完整
- 在 `docs/reference/AGENT_SKILLS.md` 記錄選型理由，以及檢視過但未選用的 skill 生態

### 人類文件整理

- 移除人類文件的 compatibility-stub 方案，讓 `docs/` 能保持更乾淨
- 將主要使用者狀態文件移到：
  - `docs/current/PLAN.md`
  - `docs/current/STATUS_REPORT.md`
  - `docs/current/BUG_TRIAGE.md`
- 將 workflow 比較重的支撐文件移到 `docs/workflows/`
- 將長期累積紀錄移到 `docs/history/`
- 將 skill selection 背景移到 `docs/reference/AGENT_SKILLS.md`
- 重寫 `docs/index.md`，讓它成為人類優先的 docs 入口，直接告訴使用者先看哪三份文件
- 更新 agent 端 references 與 `XBrainLab Autopilot` heartbeat prompt，讓 unattended work 跟著新的 doc layout，而不是舊的 root-level doc 路徑

### 頂層 panel 基線與 AI shell 訊號

- 擴充 `scripts/dev/capture_ui_baseline.py`，讓 helper 也會抓 `artifacts/ui/ai-assistant-open.png`
- 在 `tests/unit/scripts/test_capture_ui_baseline.py` 補上這個擷取步驟的聚焦單元 coverage
- 重新產生 headless 基線產物：
  - `xvfb-run -a /home/administrator/.local/bin/poetry run python scripts/dev/capture_ui_baseline.py`
  - 結果：shell、五個主 panel、AI assistant 開啟狀態都成功擷取
- 重新執行 helper 的聚焦驗證：
  - `/home/administrator/.local/bin/poetry run pytest -s tests/unit/scripts/test_capture_ui_baseline.py -q`
  - 結果：`4 passed`
- 重新執行 shell 層級 workflow 證據的 Qt integration 切片：
  - `xvfb-run -a /home/administrator/.local/bin/poetry run pytest -s tests/integration/ui/test_e2e_qtbot.py -q`
  - 結果：`20 passed`
- 同一個 integration 切片也暴露了已確認的 AI assistant 執行期問題：
  - 第一次開啟時的 local model 初始化會因缺少 `accelerate` 而失敗
- 將這個執行期訊號記錄為 `BUG-AGENT-001`
- 同時記下一個新的設計邊界例外：
  - 使用者已明確同意可以對 AI assistant panel 做有意識的重設計

### 高優先 dialog acceptance coverage

- 新增 `tests/integration/ui/test_dialog_acceptance.py`，透過真實 widget 互動與 OK-button 路徑，驗證四個 prep-gate 高優先 dialog：
  - `LabelMappingDialog`
  - `EventFilterDialog`
  - `EpochingDialog`
  - `TrainingSettingDialog`
- 驗證結果：
  - `xvfb-run -a /home/administrator/.local/bin/poetry run pytest -s tests/integration/ui/test_dialog_acceptance.py -q`
  - 結果：`4 passed`
- 這大幅縮小了 prep gate 在 modal 路徑上的盲區：
  - 這些 dialog 已不再只靠 direct method call 或 patched dialog-entry mock 來覆蓋
  - 剩餘限制是更大的測試 harness 仍 patch 了 `QDialog.exec`，因此這代表的是很強的 headless acceptance coverage，而不是完整的手動桌面行為驗證

### 共用 refresh 傳播 coverage

- 新增 `tests/unit/ui/test_panel_event_bridges.py`，直接驗證最高價值的 observer-bridge 傳播路徑：
  - dataset events -> `PreprocessPanel.update_panel()`
  - dataset events -> `TrainingPanel.update_panel()`
  - `training_stopped` -> `EvaluationPanel.update_panel()`
  - `training_stopped` -> `VisualizationPanel.update_panel()`
- 驗證結果：
  - `/home/administrator/.local/bin/poetry run pytest -s tests/unit/ui/test_panel_event_bridges.py -q`
  - 結果：`4 passed`
- 這補強了既有的 `MainWindow.switch_page()` smoke test，因為它直接驗了 event-driven 路徑，而不只是 tab 導覽

### AI shell triage 收斂

- 確認 `accelerate` 雖然已在 `pyproject.toml` 宣告，但只存在於可選的 Poetry `llm` group
- 這讓 `BUG-AGENT-001` 更聚焦：
  - 問題不只是「原始碼裡少了依賴」
  - 更精確地說，是活躍本地環境與 UI 對 local-model startup readiness 的假設不一致，加上 UI 在 local backend 啟動前缺少 preflight 行為

### Pytest capture triage 收斂

- 再次以以下指令重現 `BUG-ENV-003`：
  - `/home/administrator/.local/bin/poetry run pytest tests/unit/backend/training/test_option.py -q`
  - 結果：在 `_pytest/capture.py` teardown 階段失敗
- 進一步拆分 capture backend：
  - `--capture=fd` 仍然失敗
  - `--capture=sys` 可通過
  - `--capture=tee-sys` 可通過
  - `-s` 也可通過
- 以代表性切片驗證 `--capture=sys` workaround：
  - `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/unit/backend/training/test_option.py -q`
  - `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/unit/ui/test_main_window_sync.py -q`
  - `xvfb-run -a /home/administrator/.local/bin/poetry run pytest --capture=sys tests/integration/ui/test_dialog_acceptance.py -q`
- 結論：
  - 目前 workspace 的問題明確是 `fd` capture，不是整體 pytest collection 或 execution 壞掉
  - `--capture=sys` 是目前較推薦的本地 workaround，因為它保留了 capture 行為，又不會在 teardown crash

### unattended UI 驗證環境再收斂

- 重新檢查 heartbeat 真正卡住的 UI 驗證路徑，發現目前更穩定的 blocker 不是 `BUG-ENV-003`，而是 unattended Qt 啟動環境
- 直接執行以下指令時，UI pytest 會在 `pytest-qt` 的 `qapp` fixture 初始化階段 abort：
  - `xvfb-run -a /home/administrator/.local/bin/poetry run pytest tests/integration/ui/test_dialog_acceptance.py -q`
- runtime signal 顯示：
  - Qt 嘗試載入 `wayland` / `xcb` plugin 後失敗
  - matplotlib 預設 cache path 在目前本地 Codex run 中也不可寫
- 以以下最小 workaround 重跑同一條 slice：
  - `MPLCONFIGDIR=/tmp/matplotlib-codex QT_QPA_PLATFORM=offscreen /home/administrator/.local/bin/poetry run pytest --capture=sys tests/integration/ui/test_dialog_acceptance.py -q`
  - 結果：`4 passed`
- 再用相同環境前置驗證既有 UI runner：
  - `QT_QPA_PLATFORM=offscreen MPLCONFIGDIR=/tmp/matplotlib-codex /home/administrator/.local/bin/poetry run python scripts/dev/run_tests.py ui`
  - 結果：`742 passed, 15 skipped, 1 warning`
- 因此新增 repo-local helper：
  - `scripts/dev/run_ui_pytest.sh`
- helper 會固定套用：
  - `QT_QPA_PLATFORM=offscreen`
  - `MPLBACKEND=Agg`
  - `MPLCONFIGDIR=/tmp/matplotlib-codex`
  - `--capture=sys`
- 同步更新：
  - `scripts/dev/run_tests.py` 的 `ui` 路徑
  - `.agents/runbooks/setup.md`
  - `docs/workflows/TESTING_STRATEGY.md`
  - triage / queue / status report
- 這代表目前 heartbeat 自動化若要跑 UI pytest，應該直接走 repo-local helper，而不是裸跑 pytest 指令

### 品質看板與定期監測入口

- 新增 `scripts/dev/update_quality_dashboard.py`
- 新增 `docs/current/QUALITY_DASHBOARD.md` 作為人看的固定入口
- live dashboard output 現在會寫到：
  - `artifacts/quality/latest.md`
  - `artifacts/quality/latest.json`
  - `artifacts/quality/history.jsonl`
- 新增 `artifacts/quality/.gitignore`，避免自動刷新把 generated report 變成長期 git 噪音
- 新增單元測試：
  - `tests/unit/scripts/test_update_quality_dashboard.py`
- 第一輪完整 dashboard refresh 的檢查集包含：
  - startup smoke
  - UI baseline capture
  - dialog acceptance
  - UI unit suite
  - real-data IO integration
- 第一輪 live 結果：
  - `overall FAIL`
  - 失敗點不是 UI，而是 `Real-Data IO Integration`
  - 這次看板刷新重新證明 `BUG-ENV-003` 還在，因為預設 capture 再次於 `_pytest/capture.py` teardown 階段失敗
- 這代表 dashboard 不是單純展示綠燈，而是真的能把目前 workspace 最脆弱的驗證路徑抓出來

### AI assistant 本地啟動強化

- 將 `BUG-AGENT-001` 從單一缺少 `accelerate` 的表面症狀，收斂成兩個獨立問題：
  - 第一次啟動時的 worker path 忽略 persisted settings，直接建立全新的預設 `LLMConfig()`
  - local backend 太晚才發現缺少 runtime package，等進入 backend initialization 後才失敗
- 更新 `AgentWorker.initialize_agent()`，讓第一次初始化時也會先載入 persisted settings，再決定 backend
- 在以下位置加入 local-runtime readiness helper：
  - `AgentWorker`
  - `ChatPanel.update_model_menu()`
  - `ModelSettingsDialog`
- 將目前 assistant 方向改成 local-only startup，而不是用 Gemini fallback 去掩蓋 bootstrap failure
- 用以下測試驗證這次強化：
  - `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/unit/llm/core/test_config.py tests/unit/llm/agent/test_worker.py -q`
  - `xvfb-run -a /home/administrator/.local/bin/poetry run pytest --capture=sys tests/unit/ui/chat/test_chat_panel.py tests/unit/ui/dialogs/test_model_settings.py -q`
  - `xvfb-run -a /home/administrator/.local/bin/poetry run pytest --capture=sys tests/integration/ui/test_e2e_qtbot.py -q`
- 這個 workspace 目前剩下的 local-only 阻塞點：
  - 尚未有 local model cache
  - 仍缺一次乾淨的真實下載模型 end-to-end local startup 驗證

### 純本地環境收斂

- 以以下指令在目前 Poetry environment 安裝可選的 local-LLM 依賴：
  - `/home/administrator/.local/bin/poetry install --with llm --no-interaction`
- 之後確認 `LLMConfig.missing_local_runtime_packages()` 已回傳 `[]`
- 確認下一個 local-only 阻塞點不是缺套件，而是主機 CUDA 不相容：
  - `torch.cuda.is_available()` 仍回傳 `True`
  - 但直接做 CUDA allocation probe 會失敗，拋出 `RuntimeError: CUDA error: no kernel image is available for execution on the device`
- 更新 `LocalBackend`，讓它在 model load 前先 probe 指定 CUDA device；若 GPU 不可用，就回退到 CPU，並關閉 4-bit loading
- 用以下測試驗證 CUDA fallback 強化：
  - `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/unit/llm/core/test_local_backend.py tests/unit/llm/core/test_config.py tests/unit/llm/agent/test_worker.py -q`
  - 結果：`50 passed`
- 確認目前設定的 local model 預期 cache path 仍不存在：
  - `/mnt/d/repos/XBrainLab/XBrainLab/llm/core/models/Qwen_Qwen2.5-7B-Instruct`
- 在環境變更後曾嘗試單獨重跑 `tests/integration/ui/test_e2e_qtbot.py`，但因在 AI-dock 區塊後 hang 太久而中止，因此那次執行不算 accepted evidence

### App 內 assistant 的文獻定位修正

- 依使用者澄清，修正對 app 內 assistant 的工作理解：
  - 開發助手是 app 外的 Codex
  - app 內 assistant 是用來操作 XBrainLab 本身
- 目標架構應是以 tool call 為中心，讓較弱的本地模型在產品內仍能有效工作
- 依以下來源重新比對目前定位：
  - OpenAI 的 tool 與 function-calling 文件
  - Anthropic 的 tool-definition 與 agent-architecture 指南
  - ReAct 論文
- 將工作結論記錄在 `docs/history/LITERATURE_LOG.md`
- 同步更新 agent 端記憶文件：
  - `AGENTS.md`
  - `.agents/stack.md`
  - `.agents/runbooks/setup.md`
  讓 heartbeat run 之後也會保留這個區分
- 目前產品立場：
  - tool calling 是執行骨幹，不是附帶功能
  - app 內 assistant 應被視為 workflow operator，而不是 developer copilot
  - 對終端使用者不應預設提供無限制 local-model choice；更合理的是有限、可驗證的 curated model set

### 更新後的下一步建議

1. 驗證頂層 panel 的 happy path，並收集超越初始 shell 的更多基線產物
2. triage 或修復目前 workspace 的預設 pytest capture teardown failure
3. 持續處理 prep-gate 中高風險 dialog acceptance flow 與 downstream refresh propagation

### 碩論主線文件收斂

- 在 `AGENTS.md` 中明確寫出這個 repo 是碩論實作 workspace
- 記錄目前碩論工作順序：
  - 先穩定化
  - 再重設 tool-call agent 架構
  - 並持續補上嚴謹驗證
- 簡化 `docs/index.md`，讓人類入口只強調 current status、plan、triage、decision-record 這幾份文件
- 新增 `docs/decisions/README.md` 作為 decision-record 入口
- 新增 `docs/decisions/ADR-011-thesis-direction.md`，讓之後的 tool-call agent redesign 有明確主設計錨點，而不是散落在各處
- 更新 `docs/current/PLAN.md` 與 `docs/current/STATUS_REPORT.md`，讓它們反映碩論主線，而不只是穩定化循環

### Repo 結構盤點與重整提案

- 完成整個 repo 的結構盤點，涵蓋：
  - 根目錄資料夾
  - `docs/`
  - `XBrainLab/`
  - `tests/`
  - `scripts/`
  - `ROADMAP.md`、`CHANGELOG.md`、`mkdocs.yml` 這類根目錄入口檔
- 確認核心問題是資訊膨脹，而不是某一個資料夾單獨設計不好：
  - 現行文件
  - 歷史筆記
  - API / reference material
  - thesis decisions
  - 對外文件導覽
  都在競爭近似的可見度
- 新增 `docs/decisions/ADR-012-project-structure-redesign.md`，作為 repo / 文件資訊架構重整的提案
- 更新 `docs/decisions/README.md` 與 `docs/current/STATUS_REPORT.md`，讓這份結構提案能從 active docs surface 被找到

### Repo 結構遷移第一階段

- 新增 root `README.md`，讓 repo 現在有標準的人類入口
- 更新 `pyproject.toml`，讓 package readme 指向根目錄 `README.md`，而不是 `docs/index.md`
- 建立：
  - `docs/guides/README.md`
  - `docs/api/README.md`
  - `docs/archive/README.md`
  - `docs/archive/` 各子資料夾的 README
- 移動：
  - `docs/getting-started/installation.md` -> `docs/guides/installation.md`
  - `docs/getting-started/quickstart.md` -> `docs/guides/quickstart.md`
  - `docs/contributing.md` -> `docs/guides/contributing.md`
  - `docs/architecture/` -> `docs/archive/architecture/`
  - `docs/agent/` -> `docs/archive/agent/`
  - `docs/development/` -> `docs/archive/development/`
  - `docs/reference/` -> `docs/archive/reference/`
- 更新 `docs/index.md` 與 `mkdocs.yml`，讓對外導覽對齊新結構
- 更新內部仍指向舊路徑的 doc links
- 驗證：
  - 本地 markdown link scan：`BROKEN=0`
  - MkDocs nav target existence check：`MISSING=0`

### Status report 改版

- 將 `docs/current/STATUS_REPORT.md` 重寫成最新優先的快照，而不是照著 plan 鏡像展開的敘事型報告
- 明確將它與 `CHANGELOG.md` 區分：
  - `STATUS_REPORT.md` 回答「現在真實狀態是什麼」
  - `CHANGELOG.md` 回答「某個版本正式改了什麼」
- 把最新、最實際的進展移到報告最前面，讓使用者一打開就能先看到最近改了什麼

### Public EEG fixture 多樣性擴充

- 重新檢查目前資料集準備狀態後，確認缺口不在 repo 內 compact multiformat pack，而是在 public-source baseline 還不夠多樣
- 更新 `scripts/dev/fetch_public_eeg_fixtures.py`，讓它從單檔下載清單升級成 fixture-group 下載：
  - 保留既有的 PhysioNet EDF、BBCI GDF、SCCN EEGLAB `.set`
  - 新增 MNE testing-data 的 `scan41_short.cnt`
  - 新增 MNE testing-data 的 BrainVision `test_NO.vhdr`，並一併下載 sidecars `test_NO.eeg`、`test_NO.vmrk`
- 更新 `tests/data/public/README.md`，明確記錄目前 public baseline 的來源與覆蓋格式
- 更新 `tests/integration/io/test_io_integration.py`，讓 public real-data slice 也會覆蓋：
  - CNT
  - BrainVision `.vhdr`
- 在實作前先用暫存目錄驗證：
  - `scan41_short.cnt` 可被 `load_raw_data()` 成功載入
  - `test_NO.vhdr` 可在 sidecar 齊全時被 `load_raw_data()` 成功載入
- 實際下載到 `tests/data/public/` 後，再執行：
  - `/home/administrator/.local/bin/poetry run python scripts/dev/fetch_public_eeg_fixtures.py`
  - `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/integration/io/test_io_integration.py -q`
  - 結果：`29 passed, 11 warnings`
- 目前新增 public fixtures 後可觀察到的非阻塞 warning：
  - `scan41_short.cnt` 會出現 meas date 與 byte-width 相關 MNE warning
  - 既有 `bbci-competition-iii-O3VR.gdf` 的 annotation-range warning 仍存在
  - 兩者目前都不阻止 import 與 facade import 通過
- 這讓目前 workspace 的 public real-data baseline 來源擴大到：
  - PhysioNet
  - BBCI
  - SCCN
  - MNE testing-data
- 檔案型別則擴大到：
  - EDF
  - GDF
  - EEGLAB `.set`
  - CNT
  - BrainVision `.vhdr`

### Thesis 文件面集中

- 新增 `docs/thesis/`，把原本分散在 `current/`、`decisions/`、`history/`、`workflows/` 的碩論材料整理成 thesis-facing surface
- 新增以下文件：
  - `docs/thesis/README.md`
  - `docs/thesis/problem-statement.md`
  - `docs/thesis/system-design.md`
  - `docs/thesis/dataset-baseline.md`
  - `docs/thesis/validation-plan.md`
  - `docs/thesis/results-log.md`
  - `docs/thesis/threats-to-validity.md`
- 更新 `docs/index.md`，讓人類入口現在能直接導向 thesis surface
- 更新 `mkdocs.yml`，讓文件站導覽正式包含 Thesis 區
- 這次整理後的分工變成：
  - `current/` = 現在狀態
  - `decisions/` = 正式決策
  - `history/` = 工作過程
  - `thesis/` = 論文材料整理面
