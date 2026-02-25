# Testing Architecture（測試架構詳解）

**最後更新**: 2026-02-25

## 1. 設計理念

XBrainLab 採用 **三層測試金字塔**，確保從單元到端對端的全面覆蓋：

- **Unit**: 隔離測試單一元件，Mock 外部依賴
- **Integration**: 驗證多元件協同運作（Controller ↔ Backend ↔ UI）
- **Regression**: 重現已修復的 Bug，防止回歸

額外原則：
- **Backend Headless**: Unit/Integration Phase 1-2 測試不引入 PyQt6
- **真實資料**: Integration 使用真實 EEG 錄製檔（`tests/data/`）
- **Study 入口**: 所有測試透過 `Study` / `study.get_controller()` 存取後端

---

## 2. 目錄結構

```
tests/
├── __init__.py
├── conftest.py                     # 全域 Fixture (study, facade, tmp_path)
├── architecture_compliance.py      # 架構合規性檢查
│
├── data/                           # 測試用資料
│   └── *.gdf / *.mat              # 真實 EEG 檔案（.gitignore 排除大型檔案）
│
├── fixtures/                       # 共用 Fixture 模組
│   └── *.py
│
├── unit/                           # ========== 單元測試 ==========
│   ├── backend/                    # 後端單元測試
│   │   ├── controller/             # Controller 邏輯測試
│   │   │   ├── test_dataset_controller.py
│   │   │   ├── test_preprocess_controller.py
│   │   │   ├── test_training_controller.py
│   │   │   ├── test_evaluation_controller.py
│   │   │   ├── test_visualization_controller.py
│   │   │   ├── test_chat_controller.py
│   │   │   └── test_controller_error_handling.py
│   │   ├── dataset/                # Dataset 相關
│   │   │   ├── test_dataset.py
│   │   │   ├── test_dataset_generator.py
│   │   │   ├── test_data_splitter.py
│   │   │   ├── test_epochs.py
│   │   │   └── test_option.py
│   │   ├── load_data/              # 資料載入
│   │   │   ├── test_raw_data_loader.py
│   │   │   ├── test_data_loader.py
│   │   │   ├── test_event_loader.py
│   │   │   ├── test_label_loader.py
│   │   │   └── ... (11 test files)
│   │   ├── model_base/             # 模型定義
│   │   │   └── test_model_base.py
│   │   ├── preprocessor/           # 預處理操作
│   │   │   ├── test_filtering.py
│   │   │   ├── test_resample.py
│   │   │   ├── test_normalize.py
│   │   │   ├── test_rereference.py
│   │   │   └── ... (9 test files)
│   │   ├── training/               # 訓練子系統
│   │   │   ├── test_trainer.py
│   │   │   ├── test_training_plan.py
│   │   │   ├── test_model_holder.py
│   │   │   ├── test_evaluator.py
│   │   │   ├── record/             # 訓練紀錄
│   │   │   │   ├── test_train_record.py
│   │   │   │   ├── test_eval_record.py
│   │   │   │   └── ...
│   │   │   └── ... (8 + 5 test files)
│   │   ├── utils/                  # 基礎設施
│   │   │   ├── test_observer.py
│   │   │   ├── test_logger.py
│   │   │   ├── test_error_handler.py
│   │   │   └── ... (7 test files)
│   │   └── visualization/
│   │       ├── test_saliency_map.py
│   │       └── ... (3 test files)
│   │
│   ├── llm/                        # LLM / Agent 單元測試
│   │   ├── agent/                  # Agent 邏輯
│   │   │   ├── test_agent.py
│   │   │   ├── test_context_assembler.py
│   │   │   ├── test_react_agent.py
│   │   │   └── ... (5 test files)
│   │   ├── core/                   # LLM 核心
│   │   │   ├── test_api_engine.py
│   │   │   ├── test_gemini_engine.py
│   │   │   ├── test_parser.py
│   │   │   └── ... (6 test files)
│   │   ├── rag/                    # RAG 相關
│   │   │   └── ... (3 test files)
│   │   └── tools/                  # 工具呼叫 (Mocked)
│   │       ├── test_tool_definitions.py
│   │       ├── test_tool_executor.py
│   │       └── real/               # 真實工具測試
│   │           └── test_real_tools.py
│   │
│   └── ui/                         # UI 單元測試
│       ├── core/
│       │   ├── test_base_panel.py
│       │   ├── test_observer_bridge.py
│       │   ├── test_event_bus.py
│       │   └── ... (5 test files)
│       ├── chat/
│       │   └── test_chat_panel.py
│       ├── components/
│       │   ├── test_agent_manager.py
│       │   ├── test_info_panel.py
│       │   └── test_placeholder.py
│       ├── dataset/                # 6 test files
│       ├── preprocess/             # 4 test files
│       ├── training/               # 7 test files
│       ├── visualization/          # 1 test file
│       ├── dialogs/                # 2 test files
│       └── styles/                 # 2 test files
│
├── integration/                    # ========== 整合測試 ==========
│   ├── controller/                 # Phase 1: 後端核心
│   │   ├── test_dataset_controller.py
│   │   ├── test_preprocess_controller.py
│   │   └── test_training_controller.py
│   │
│   ├── pipeline/                   # Phase 2: Agent 工具鏈 & E2E
│   │   ├── test_integration_real_tools.py   # LLM 工具鏈 (真實資料)
│   │   ├── test_all_real_tools.py           # 全工具覆蓋
│   │   ├── test_e2e_training.py             # 端對端訓練
│   │   ├── test_full_pipeline.py            # 完整管線
│   │   ├── test_multi_model.py              # 模型切換
│   │   ├── test_real_data_pipeline.py       # 真實資料管線
│   │   └── test_tool_execution_pipeline.py  # 工具執行鏈
│   │
│   ├── ui/                         # Phase 3: UI 互動
│   │   ├── test_panel_controller_binding.py # Panel ↔ Controller 綁定
│   │   ├── test_ui_headless.py              # Headless UI 穩定性
│   │   ├── test_ui_integration.py           # UI 整合
│   │   ├── test_refresh_panels.py           # 面板重新整理
│   │   ├── test_agent_manager_switch.py     # Agent 切換
│   │   └── test_dialog_integration.py       # 對話框整合
│   │
│   ├── training/                   # 訓練整合
│   │   └── test_training_integration.py
│   │
│   ├── io/                         # I/O 整合
│   │   ├── test_io_integration.py
│   │   └── test_metadata_integration.py
│   │
│   └── debug/                      # Debug 腳本
│       └── test_debug_script_execution.py
│
└── regression/                     # ========== 迴歸測試 ==========
    ├── test_reproduce_val_issue.py  # 驗證集問題重現
    └── test_epoch_duration_bug.py   # Epoch 時長 Bug 重現
```

---

## 3. 整合測試三階段策略

整合測試劃分為三個互不重疊的階段，以隔離錯誤來源：

| 階段 | 範圍 | 目標 | 目錄 |
|------|------|------|------|
| **Phase 1** | 後端核心 | Controller 業務邏輯可在無 UI 下獨立運作 | `integration/controller/` |
| **Phase 2** | Agent 介面 | LLM Tool 正確呼叫 Controller 並處理錯誤 | `integration/pipeline/` |
| **Phase 3** | 應用層 | UI 透過 Observer 正確響應後端狀態更新 | `integration/ui/` |

### Phase 1: Controller 測試
```python
def test_training_with_real_data(study):
    # 1. Setup
    controller = study.get_controller("training")

    # 2. Act
    controller.update_config({"epochs": 50})

    # 3. Assert
    assert study.training_option.epochs == 50
```

### Phase 2: Tool Chain 測試
```python
def test_full_pipeline(facade, real_data_path):
    facade.load_data([str(real_data_path)])
    facade.apply_bandpass_filter(1.0, 40.0)
    facade.epoch_data(tmin=-0.2, tmax=0.8)
    facade.set_model("EEGNet")
    facade.start_training()
    assert facade.get_training_status() == "completed"
```

### Phase 3: UI 綁定測試
```python
def test_ui_updates(qtbot, mock_study):
    mock_study.get_controller.return_value = MagicMock()
    parent = QWidget()
    parent.study = mock_study
    panel = TrainingPanel(parent=parent)
    qtbot.addWidget(panel)

    panel._on_training_started()
    assert panel.status_label.text() == "Running"
```

---

## 4. 執行方式

```bash
# 全部測試
poetry run pytest

# 依層級執行
poetry run pytest tests/unit                      # 僅單元測試
poetry run pytest tests/integration               # 僅整合測試
poetry run pytest tests/regression                # 僅迴歸測試

# 依領域執行
poetry run pytest tests/unit/backend              # 後端單元
poetry run pytest tests/unit/llm                  # LLM 單元
poetry run pytest tests/unit/ui                   # UI 單元

# 依階段執行
poetry run pytest tests/integration/controller    # Phase 1
poetry run pytest tests/integration/pipeline      # Phase 2
poetry run pytest tests/integration/ui            # Phase 3

# 常用選項
poetry run pytest -v                              # 詳細輸出
poetry run pytest -x                              # 第一個失敗即停止
poetry run pytest --tb=short                      # 簡短 Traceback
poetry run pytest -k "test_training"              # 關鍵字過濾
```

---

## 5. Fixture 規範

### 全域 Fixture (`conftest.py`)
| Fixture | 範圍 | 用途 |
|---------|------|------|
| `study` | function | 全新 Study 實例 |
| `facade` | function | BackendFacade（含 Study） |
| `tmp_path` | function | 暫存目錄（pytest 內建） |
| `real_data_path` | session | 真實 EEG 測試檔案路徑 |

### 撰寫規則
1. **使用 `Study` 入口**: 透過 `study.get_controller()` 取得 Controller，不直接實例化
2. **Phase 1-2 禁用 Qt**: 不匯入 `PyQt6` 的 Widget，保持 Headless
3. **真實資料**: 讀取使用 `tests/data/` 中的檔案；寫入使用 `tmp_path`
4. **命名規範**: `test_<功能>_<情境>.py`，例如 `test_training_with_real_data.py`

---

## 6. 常見問題排除

### "Collection Error" 或 "ImportError"
- **原因**: pytest 掃描到 `XBrainLab/` 源碼目錄或循環引用
- **解法**: 明確指定 `pytest tests/`；確認 `pyproject.toml` 設定 `norecursedirs = XBrainLab`

### "Segmentation Fault" 或 Process Crash
- **原因**: 在無模擬顯示器的環境下執行 PyQt 測試，或混合 Thread 與 Qt Signal
- **解法**: 使用 `pytest-qt` 的 `qtbot` fixture；避免 `time.sleep()`，改用 `qtbot.wait()`

### "Attributes missing on Mock"
- **原因**: `MagicMock(spec=Study)` 不自動產生 Nested attributes
- **解法**: 對 `get_controller` 等巢狀呼叫明確設定 `return_value` 或 `side_effect`

### 測試跑太久
- **解法**: 訓練相關測試設 `epochs=1`；使用 `pytest -x` 快速失敗；標記慢速測試 `@pytest.mark.slow`
