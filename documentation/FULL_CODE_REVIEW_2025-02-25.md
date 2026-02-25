# XBrainLab 完整程式碼審查報告

**日期**: 2026-02-25
**審查範圍**: 全部原始碼（Backend / UI / LLM Agent / Tests）
**審查結果統計**:

| 嚴重度    | Backend Core | Controllers | Training | Preprocessor/Viz | UI     | LLM/Agent | Tests  | **Total** |
|-----------|:------------:|:-----------:|:--------:|:----------------:|:------:|:---------:|:------:|:---------:|
| CRITICAL  | 3            | 0           | 3        | 0                | 3      | 3         | 4      | **16**    |
| HIGH      | 9            | 5           | 8        | 1                | 7      | 9         | 4      | **43**    |
| MEDIUM    | 12           | 11          | 12       | 9                | 15     | 12        | 3      | **74**    |
| LOW       | 11           | 11          | 7        | 12               | 14     | 10        | 1      | **66**    |
| **Total** | **35**       | **27**      | **30**   | **22**           | **39** | **34**    | **12** | **199**   |

---

## 目錄

1. [CRITICAL 嚴重問題（16 項）](#1-critical-嚴重問題)
2. [HIGH 高優先問題（43 項，精選 TOP 20）](#2-high-高優先問題)
3. [MEDIUM 中等問題（要點摘要）](#3-medium-中等問題)
4. [架構層級問題](#4-架構層級問題)
5. [測試覆蓋缺口](#5-測試覆蓋缺口)
6. [建議修復優先順序](#6-建議修復優先順序)

---

## 1. CRITICAL 嚴重問題

### 1.1 Backend Core

| ID  | 檔案 | 行號 | 說明 |
|-----|------|------|------|
| BC-C01 | `backend/dataset/epochs.py` | 414-416 | **KFOLD 類型不匹配**: `_get_real_num` 檢查 `isinstance(value, int)` 但 `DataSplitter.get_value()` 永遠回傳 `float`。KFOLD 分割永遠 raise `ValueError`，此功能不可使用。**修正**: `value = int(value)` |
| BC-C02 | `backend/dataset/epochs.py` | 615-616 | **KFOLD 浮點數運算**: `pick_trial` KFOLD 分支用 float 做 `%` 和 `//`，結果不穩定。**修正**: 同上，先轉 int |
| BC-C03 | `backend/facade.py` | 95-96 | **假事件位置**: `attach_labels` 使用 `np.arange(n_labels)` 作為事件 onset 樣本數（0,1,2...），不是真實位置，Epoching 會切到錯誤區段 |

### 1.2 Training

| ID  | 檔案 | 行號 | 說明 |
|-----|------|------|------|
| TR-C01 | `model_base/SCCNet.py` | 126-127 | **`torch.log(0)` → `-inf` → NaN**: `x**2` → `Dropout` → `AvgPool` 可輸出 0，`torch.log(0) = -inf`。**修正**: `torch.log(torch.clamp(x, min=1e-7))` |
| TR-C02 | `model_base/ShallowConvNet.py` | 100 | **同上**: `x**2` → `AvgPool` → `torch.log(x)` 也有同樣的 `log(0)` 風險 |
| TR-C03 | `training/record/train.py` | 297-316 | **`load()` 恢復 epoch 但不恢復模型**: 若啟用 resume，模型仍是隨機初始化，訓練歷史不一致。目前為死碼但存在誤導 |

### 1.3 UI

| ID  | 檔案 | 行號 | 說明 |
|-----|------|------|------|
| UI-C01 | `ui/components/plot_figure_window.py` | 58-66 | **未呼叫 `super().__init__()`**: `PlotFigureWindow` 繼承 `SinglePlotWindow` 但 `__init__` 從未呼叫 parent `__init__`。`self.main_layout`、`self.figsize`、`self.dpi` 等屬性未被初始化。首次呼叫 `init_ui()` 中存取這些屬性時**必定 `AttributeError` 崩潰**。 |
| UI-C02 | `ui/dialogs/dataset/data_splitting_preview_dialog.py` | 全檔 | **使用 `threading.Thread` 而非 `QThread`**: 背景執行緒可能跨執行緒存取 Qt 物件，在非 macOS 平台可能造成 segfault |
| UI-C03 | `ui/dialogs/model_settings_dialog.py` | 520-540 | **`.env` 使用相對路徑**: API 金鑰寫入位置依 CWD 而異，可能寫入錯誤目錄 |

### 1.4 LLM/Agent

| ID  | 檔案 | 行號 | 說明 |
|-----|------|------|------|
| LLM-C01 | `llm/core/config.py` + `llm/agent/worker.py` | 105-120, 131-142 | **推理模式被每次生成重置**: `generate_from_messages()` 重新載入 config，但 `load_from_file()` 不還原 `inference_mode`，使用者切換 Gemini 後下次訊息會被靜默切回 `local` |
| LLM-C02 | `llm/agent/controller.py` | 613-620 | **`stop_generation()` 中斷錯誤的執行緒**: 中斷發到 worker_thread，但實際生成在 GenerationThread 內，不會收到中斷 |
| LLM-C03 | `llm/agent/controller.py` | 613-620 | **`stop_generation()` 未發出 `processing_finished` 信號**: UI 會永久卡在 busy 狀態 |

---

## 2. HIGH 高優先問題

### 2.1 Backend Core (9)

| ID | 檔案 | 說明 |
|----|------|------|
| BC-H01 | `load_data/raw.py:147` | `print()` 做警告而非 `logger.warning()` |
| BC-H02 | `dataset/epochs.py:95-104` | `Epochs.__init__` 會修改輸入的 events/event_id（副作用） |
| BC-H03 | `load_data/label_loader.py:56` | 檔案未指定 `encoding="utf-8"`，Windows 上可能解碼錯誤 |
| BC-H04 | `load_data/label_loader.py:58-59` | `suppress(ValueError)` 靜默丟棄非數字 token，壞檔案不會警告 |
| BC-H05 | `facade.py:375` | `output_dir` 永遠 fallback 到 `"./output"`，使用者設定無效 |
| BC-H06 | `utils/observer.py:54-56` | `notify` 迭代中若 callback 觸發 subscribe/unsubscribe 會修改 list |
| BC-H07 | `data_manager.py:192-199` | `clean_datasets` 未重置 `dataset_generator = None`，殘留引用 |
| BC-H08 | `services/label_import_service.py:107-108` | `n = 100` 硬編碼作為 epoch count 回退值 |
| BC-H09 | `dataset/epochs.py:118-127` | 迴圈內 `np.concatenate` → O(n²) 效能 |

### 2.2 Controllers (5)

| ID | 檔案 | 說明 |
|----|------|------|
| CT-H01 | `controller/preprocess_controller.py:119` | `_apply_processor` 未傳 `force_update=True`，已 split 後無法重新預處理 |
| CT-H02 | `controller/preprocess_controller.py:185-197` | `apply_montage` 未檢查 epoch_data 存在就呼叫 `set_channels()` |
| CT-H03 | `controller/training_controller.py:77-82` | Race condition: 訓練可能在 monitor 啟動前結束，UI 不會看到任何更新 |
| CT-H04 | `controller/training_controller.py:168-175` | `get_formatted_history` 跨執行緒讀取 `current_idx` 非原子性 |
| CT-H05 | `controller/visualization_controller.py:143-146` | `avg_dict` 假設所有 record 的 gradient keys 相同，缺少 key 會 KeyError |

### 2.3 Training (8)

| ID | 檔案 | 說明 |
|----|------|------|
| TR-H01 | `training/training_plan.py:337-358` | GPU 模型建立後若無 best model 就設 None，GPU 記憶體洩漏 |
| TR-H02 | `training/record/train.py:217-223` | `deepcopy(state_dict())` 在 GPU 上複製，浪費 GPU 記憶體 |
| TR-H03 | `training/record/train.py:410-414` | 圖表使用全域 `plt.clf()` / `plt.plot()`，多圖時會操作到錯誤的圖 |
| TR-H04 | `training/record/eval.py:186-200` | `get_auc()` 計算 softmax **兩次**，且不處理單一類別 |
| TR-H05 | `training/record/eval.py:13-27` | `calculate_confusion` 用 `np.unique` 計算類別數，若有缺失類別則 confusion matrix 維度錯誤 |
| TR-H06 | `training/trainer.py:162-168` | `clean(force_update)` 不 join 訓練執行緒，可能在訓練仍在跑時返回 |
| TR-H07 | `training/option.py:127-153` | `validate()` 多個錯誤只保留最後一個，使用者要逐一修正 |
| TR-H08 | `training/record/eval.py:204-209` | `get_kappa()` 在 `pe == 1` 時 ZeroDivisionError |

### 2.4 Visualization (1)

| ID | 檔案 | 說明 |
|----|------|------|
| VZ-H01 | `visualization/saliency_spectrogram_map.py:42` | `nperseg=sfreq` 傳入 float，scipy ≥ 1.12 會 TypeError |

### 2.5 UI (7)

| ID | 檔案 | 說明 |
|----|------|------|
| UI-H01 | `ui/components/agent_manager.py:416` | `pyqtSignal` 未定義在類別頂層，Qt 元物件系統可能無法識別 |
| UI-H02 | `ui/components/agent_manager.py:82-84` | `__init__` 存取尚未建立的 `visualization_panel` |
| UI-H03 | `ui/dialogs/model_settings_dialog.py` | 直接繼承 `QDialog` 而非 `BaseDialog`，架構不一致 |
| UI-H04 | `ui/components/info_panel_service.py:120-131` | `update_single()` 缺少 C++ 物件銷毀的 try/except 保護 |
| UI-H05 | `ui/panels/preprocess/plotters/preprocess_plotter.py:250-280` | Worker 閉包捕獲可變狀態，回調時可能已 stale |
| UI-H06 | `ui/core/observer_bridge.py:58-59` | Lambda 連接無法 disconnect，多次 connect 會累積 |
| UI-H07 | `ui/panels/training/training_manager.py:145-162` | 表格更新每次建立新 QTableWidgetItem 而非重用 |

### 2.6 LLM/Agent (9)

| ID | 檔案 | 說明 |
|----|------|------|
| LLM-H01 | `llm/agent/controller.py:196-233` | `_emitted_len` 和 `_is_buffering` 未在 `__init__` 初始化 |
| LLM-H02 | `llm/agent/controller.py:434-447` | 迴圈偵測後重新生成可無限反彈，無上限計數 |
| LLM-H03 | `llm/agent/worker.py:119-165` | `generate_from_messages` 不防並發，前一生成未完成就覆寫 |
| LLM-H04 | `llm/core/backends/local.py:77` | `trust_remote_code=True` 允許任意遠端程式碼執行 |
| LLM-H05 | `llm/agent/controller.py:389` | 工具輸出未消毒即回饋 LLM（間接提示注入向量） |
| LLM-H06 | `llm/tools/real/dataset_real.py:38-62` | `list_files` 無路徑沙箱，可遍歷系統任意目錄 |
| LLM-H07 | `llm/agent/controller.py:149-178` | `handle_user_input` 異常時 `is_processing` 永不重設 |
| LLM-H08 | `llm/rag/retriever.py:108-128` | `_auto_initialize` 建立第二個 QdrantClient，可能造成檔案鎖衝突 |
| LLM-H09 | `llm/rag/indexer.py:39-44` | 依賴未安裝時 `None()` 造成 TypeError |

---

## 3. MEDIUM 中等問題

### 3.1 Backend Core (12)
- `Dataset.SEQ` 類別計數器無同步 (M-01)
- `DatasetGenerator` 跨實例重置 `Dataset.SEQ = 0` (M-02)
- `mne_helper.get_montage_channel_positions` 無 KeyError 防護 (M-03)
- `raw.get_raw_event_list` 三層 try/except 靜默吞異常 (M-04)
- `DataSplitter` MANUAL 驗證邏輯混亂 (M-05)
- `label_loader._load_csv_tsv` 回傳型別不一致 (M-06)
- `dataset.get_all_trial_numbers` 用 Python sum 而非 np.sum (M-07)
- `epochs._get_filtered_mask_pair` 使用 getattr 動態 dispatch (M-08)
- `RawDataLoader` 繼承 `list` 反模式 (M-10)
- `facade.generate_dataset` 永遠設 `is_cross_validation=False` (M-11)
- `raw.set_mne` 事件數不一致只 print 不處理 (M-12)

### 3.2 Controllers (11)
- `ChatController.messages` 無執行緒同步 (C-04)
- `DatasetController.import_files` 不驗證 filepaths 為 None (D-01)
- `DatasetController.update_metadata` 不通知 data_changed (D-03)
- `DatasetController.apply_smart_parse` 錯誤解鎖 (D-04)
- `DatasetController.get_data_at_assignments` 不防護 None list (D-05)
- `EvaluationController.get_pooled_eval_result` shape 不一致時 crash (E-01)
- `EvaluationController.train_shape` 硬編碼第二維為 1 (E-03)
- `EvaluationController` 不檢查 record.model 是否 None (E-04)
- `TrainingController.start_training` 不捕捉 generate_plan 例外 (T-04)
- `VisualizationController.get_averaged_record` 使用第一 fold 的 label/output (V-02)
- 跨 Controller 的雙事件系統（Observable + Qt Signal）不一致 (X-01)

### 3.3 Training (12)
- `trainer.interrupt` 屬性無同步機制 (M-01)
- 每 epoch 呼叫 `torch.cuda.empty_cache()` 導致快取抖動 (M-02)
- 訓練迴圈 `torch.cat` 逐 batch 累積 O(n²) (M-03)
- `parse_optim_name` 用 truthiness 過濾掉 `weight_decay=0` (M-04)
- SCCNet size 公式重複計算 (M-05)
- `evaluate_with_saliency` 多一次冗餘 forward pass (M-06)
- `get_confusion_figure` 疊加 subplot 不先清除 (M-08)
- `RecordKey.__iter__` 用 `dir(self)` 脆弱 (M-09)
- `SharedMemoryDataset.__getitem__` 建立多餘中間 tensor (M-10)
- `PooledRecordWrapper` duck-typing 呼叫極脆弱 (M-11)
- `TestOnlyOption.__init__` 呼叫 `validate()` 兩次 (M-12)

### 3.4 Preprocessor / Visualization (9)
- `pick_channels()` deprecated (P-1)
- 未知 `norm` 值靜默被忽略 (P-2)
- `np.multiply(…, np.ones_like(…))` 浪費記憶體 (P-3)
- 直接存取 MNE 私有 `._data` 屬性 (P-4)
- `edit_event` duplicate branch `new_event_ids[k]` 可 KeyError (P-5)
- `export.py` 不建立目錄 (P-7)
- `base.py` `plt.clf()` 可能清除錯誤的圖 (V-1)
- `saliency_spectrogram_map.py` `freqs % 10 == 0` 浮點比較不可靠 (V-3)
- `saliency_3d_engine.py` 迴圈內重複計算 scaling (V-9)

### 3.5 UI (15)
- MainWindow 死碼 `elif index == 1: pass` (11)
- EventBus 信號從未被使用（死碼）(12)
- PreprocessPanel 冗餘 epoched 分支 (13)
- `confusion_matrix.py` 用 `print` 而非 `logger` (16)
- `base_dialog.py` `if width and height` falsy 問題 (17)
- 重複 `training_completed_shown = False` (18)
- `TrainingManagerWindow` 與 `TrainingPanel` 功能重複 (19)
- `closeEvent` 引用不存在的 `self.timer` (20)
- `TrainingSidebar.__init__` 未傳 parent (21)
- `preview_widget` 猴子補丁覆蓋 `leaveEvent` (22)
- `ModelSummaryWindow` double `init_ui()` (23)
- QTimer lambda 捕獲可能存取已銷毀物件 (24)
- `base_saliency_view.clear_plot` 不關閉 figure (25)
- `MainWindow.update_info_panel` 引用不存在的 `info_panel` (39)

### 3.6 LLM/Agent (12)
- `active_mode` 與 `inference_mode` 欄位重複 (M-01)
- 工具雙重註冊（ToolRegistry + AVAILABLE_TOOLS）(M-02)
- `BackendResolver` 與 `ToolRegistry` class 命名衝突 (M-03)
- `load_from_file` 不載入 temperature/max_tokens 等參數 (M-04)
- `api.py` `generate_stream` 空 `choices` 時 IndexError (M-05)
- `gemini.py` 假設最後一條訊息是 user (M-06)
- `switch_backend` 對 API/Gemini 不 load (M-07)
- 下載進度只顯示 0% 和 100% (M-08)
- `_process_tool_calls` 無批次大小限制 (M-09)
- settings.json 使用相對路徑 (M-10)
- `AVAILABLE_TOOLS` 在 import 時觸發重量級載入 (M-11)
- `parser.py` 回傳類型標註不一致 (M-12)

---

## 4. 架構層級問題

### 4.1 事件/通知系統三頭馬車
- **Observable**（backend）、**Qt Signals**（ChatController, EventBus）、**ObserverBridge**（UI→Backend 映射）三套系統並存
- UI 層需同時處理 `subscribe` callback 和 Qt `connect`
- **建議**: 統一為一種機制，或明確文件化何時使用何者

### 4.2 `RawDataLoader` 繼承 `list`
- 暴露 40+ 個 list 方法（`insert`, `sort`, `extend` 等）繞過一致性檢查
- **建議**: 改為 composition，用 `_data: list[Raw]` 內部屬性

### 4.3 Facade 層過厚/漏洞並存
- `BackendFacade` 包含 450 行，混合了 UI 輸入格式轉換、狀態組裝、錯誤捕捉
- 部分設定永遠使用預設值（`output_dir`, `is_cross_validation`），使用者設定被忽略
- **建議**: 拆分為 `DataFacade`、`TrainingFacade`、`EvalFacade`

### 4.4 LLM 工具安全邊界不足
- `list_files` 無路徑沙箱
- 工具輸出未消毒即回饋 LLM
- `trust_remote_code=True` 預設啟用
- **建議**: 實作路徑白名單、工具輸出消毒、trust_remote_code 預設 False

### 4.5 Matplotlib 全域狀態管理
- 多處使用 `plt.clf()`, `plt.plot()`, `plt.figure()` 全域 API
- 多視窗/多緒時會互相干擾
- **建議**: 統一使用物件導向 API（`fig.clf()`, `ax.plot()`）

---

## 5. 測試覆蓋缺口

### 5.1 完全無測試的模組（CRITICAL）
| 模組 | 說明 |
|------|------|
| `LabelImportService` | 標籤匯入核心服務，6 個方法完全無測試 |
| `BackendFacade` 大部分 API | 只測 3 個方法的委派，其餘 15+ 方法無覆蓋 |
| Saliency Viz classes | `SaliencyMapViz`, `SaliencyTopoMapViz`, `SaliencySpectrogramMapViz` 核心繪圖邏輯 |
| `Saliency3DEngine` | 3D 繪圖引擎完全無測試 |
| `model_settings_dialog.py` | 最複雜的 UI 對話框無測試 |
| `backend_resolver.py` | LLM 工具→Backend 橋接 |

### 5.2 測試品質問題
| 問題 | 檔案 |
|------|------|
| 空殼測試（`pass`） | `test_training_setting.py:150` |
| 被 Skip 的核心 smoke test | `test_main_window.py`, `test_workflow.py` |
| 過弱斷言（只 `isinstance(result, str)`） | `test_mock_tools.py` (13+ 測試) |
| `tempfile.mkdtemp` 未用 `tmp_path` | `test_training_fix.py`, `test_logger.py` |
| unittest.TestCase 與 pytest 混用 | `test_training_fix.py` |
| `qtbot.wait(N)` 固定等待 | `test_event_bus.py`, `test_multi_model.py` 等 |

### 5.3 缺少的負面/錯誤路徑測試
- `ChatController`: 空字串/None 訊息、並發存取
- `VisualizationController.get_averaged_record`: 全部 record 無效
- `EvaluationController.get_pooled_eval_result`: fold 有不同類別數
- KFOLD splitting: value 為 float 的情況

---

## 6. 建議修復優先順序

### Tier 0 — 立即修復（會造成崩潰或資料錯誤）

| 優先 | ID | 說明 | 預估工時 |
|------|----|------|----------|
| 1 | TR-C01/C02 | SCCNet/ShallowConvNet `torch.log` 加 clamp | 15 min |
| 2 | UI-C01 | `PlotFigureWindow` 加 `super().__init__()` | 15 min |
| 3 | BC-C01/C02 | KFOLD `int(value)` 轉型 | 15 min |
| 4 | LLM-C02/C03 | `stop_generation` 修正中斷目標 + 發出信號 | 30 min |
| 5 | LLM-C01 | Config 統一 inference_mode / active_mode | 45 min |
| 6 | TR-H08 | `get_kappa()` 防護 pe==1 除零 | 5 min |
| 7 | VZ-H01 | `nperseg=int(sfreq)` | 5 min |
| 8 | UI-C03/23 | ModelSummaryWindow double init_ui + .env 路徑 | 20 min |

### Tier 1 — 本週修復（資源洩漏、安全、狀態不一致）

| 優先 | ID | 說明 | 預估工時 |
|------|----|------|----------|
| 9 | TR-H01 | GPU model 孤兒化修復 | 20 min |
| 10 | TR-H02 | state_dict deepcopy 到 CPU | 15 min |
| 11 | LLM-H02 | 迴圈偵測加上限計數 | 15 min |
| 12 | LLM-H07 | `handle_user_input` try/finally | 15 min |
| 13 | LLM-H04 | `trust_remote_code` 預設 False | 10 min |
| 14 | LLM-H06 | `list_files` 路徑沙箱 | 30 min |
| 15 | CT-H01 | `_apply_processor` 加 `force_update=True` | 5 min |
| 16 | BC-H06 | observer `notify` 迭代快照 | 10 min |
| 17 | BC-H09 | epochs 迴圈 concatenate → 收集後一次 concat | 20 min |

### Tier 2 — 近期改善（正確性、效能、架構）

| 優先 | ID | 說明 | 預估工時 |
|------|----|------|----------|
| 18 | TR-H03 | 圖表改用物件導向 matplotlib API | 1 hr |
| 19 | TR-H05 | `calculate_confusion` 接受 `n_classes` | 20 min |
| 20 | TR-M03 | 訓練迴圈 torch.cat O(n²) → list + concat | 20 min |
| 21 | BC-H05 | `output_dir` 從 Study 取得 | 20 min |
| 22 | BC-H07 | `clean_datasets` 清除 generator | 5 min |
| 23 | UI-H06 | observer_bridge lambda 連接洩漏 | 30 min |
| 24 | P-1 | `pick_channels` → `pick` | 5 min |
| 25 | P-2 | normalize 加 else raise | 5 min |

### Tier 3 — 長期改善（架構重構）

- 統一事件系統（Observable vs Qt Signals）
- `RawDataLoader` 從 list 繼承改為 composition
- Facade 拆分為領域子 Facade
- 全面改用 OOP matplotlib API
- LLM 工具安全框架（沙箱、消毒、審計）
- 填補測試覆蓋缺口（LabelImportService, Facade, Viz）

---

*報告結束。共發現 199 項問題，其中 16 項 CRITICAL、43 項 HIGH。*
