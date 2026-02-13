# XBrainLab 整合測試指南

這份文件概述了 XBrainLab 的整合測試策略、結構與規範。我們的目標是確保 **後端控制器 (Backend Controllers)**、**LLM 工具 (LLM Tools)** 以及 **UI 面板 (UI Panels)** 不論是單獨運作或協同工作時都能正常執行，讓開發者能安心地同時開發桌面應用程式與 Headless Agent。

## 1. 測試策略

我們將整合測試明確劃分為三個不重疊的階段，以隔離錯誤來源：

| 階段 (Phase) | 範圍 (Scope) | 目標對象 (Target) | 目的 (Goal) |
|---|---|---|---|
| **Phase 1** | **後端核心** | `Backend Controllers` | 驗證業務邏輯 (訓練、資料、預處理) 能在不依賴 UI 的情況下獨立運作。 |
| **Phase 2** | **Agent 介面** | `LLM Tools` | 驗證 LLM Agent 的工具層能否正確呼叫控制器並處理錯誤。 |
| **Phase 3** | **應用層** | `UI Panels` | 驗證 UI 是否能透過觀察者模式 (Observer Pattern) 正確響應後端狀態更新。 |

---

## 2. 目錄結構

所有的整合測試都位於 `tests/integration/` 目錄下：

```
tests/integration/
├── controller/          # Phase 1: 直接針對 Controller API 的測試
│   ├── test_training_controller.py
│   ├── test_dataset_controller.py
│   └── test_preprocess_controller.py
│
├── pipeline/            # Phase 2 & E2E: 工具鏈與完整流程測試
│   ├── test_integration_real_tools.py      # LLM 工具鏈 (使用真實資料)
│   ├── test_multi_model.py     # 模型切換測試
│   └── test_e2e_training.py    # (舊版) 完整端對端訓練測試
│
├── ui/                  # Phase 3: Headless UI 邏輯測試
│   ├── test_panel_controller_binding.py # UI 與 Controller 的綁定測試
│   └── test_ui_headless.py     # 一般 UI 穩定性測試
│
└── data/                # 測試資料
    └── A01T.gdf         # 真實 EEG 錄製資料 (請勿提交大型檔案)
```

---

## 3. 如何執行測試

### 執行所有整合測試
```bash
poetry run pytest tests/integration/ -v
```

### 執行特定階段測試
**Phase 1 (Controllers - 後端核心):**
```bash
poetry run pytest tests/integration/controller/ -v
```

**Phase 2 (Tools - 工具層):**
```bash
poetry run pytest tests/integration/pipeline/test_integration_real_tools.py -v
```
> **包含完整路徑驗證**: Loading (GDF) -> Bandpass Filter (MNE) -> Epoching -> Dataset Generation -> Training Execution (Backend).

**Phase 3 (UI Binding - 介面綁定):**
```bash
poetry run pytest tests/integration/ui/ -v
```

---

## 4. 撰寫新測試的指南

### 通用規則 (General Rules)
1.  **使用 `Study` Fixture**: 永遠使用 `XBrainLab.backend.study.Study` 作為測試的入口點。盡量避免直接實例化 Controller，請使用 `study.get_controller()` 來取得。
2.  **避免使用 `QApplication`**: 對於 Phase 1 和 Phase 2 的測試，**不要**匯入 `PyQt6` 的 Widget。請保持後端測試是 Headless (無圖形介面) 的。
3.  **真實資料 (Real Data)**: 讀取測試請使用 `tests/integration/data/` 中的檔案。若需寫入檔案，請使用 `tmp_path` fixture。

### 範例：Controller 測試 (Phase 1)
```python
def test_my_feature(study):
    # 1. Setup (設定)
    controller = study.get_controller("training")

    # 2. Act (執行)
    controller.update_config({"epochs": 50})

    # 3. Assert (驗證狀態)
    assert study.training_option.epochs == 50
```

### 範例：UI 綁定測試 (Phase 3)
```python
def test_ui_updates(qtbot, mock_study):
    # 1. Mock Backend (模擬後端)
    mock_study.get_controller.return_value = MagicMock()

    # 2. Init Panel with Mocked Backend (初始化面板)
    # 必須使用 QWidget 作為 parent
    parent = QWidget()
    parent.study = mock_study
    panel = TrainingPanel(parent=parent)
    qtbot.addWidget(panel)

    # 3. Trigger Event manually (手動觸發事件)
    panel._on_training_started()

    # 4. Assert UI Change (驗證 UI 變化)
    assert panel.status_label.text() == "Running"
```

## 5. 常見問題排除 (Troubleshooting)

### "Collection Error" 或 "ImportError"
- **原因**: Pytest 試圖掃描 `XBrainLab/` 源碼目錄或發生循環引用。
- **解法**: 指定目錄執行 pytest，例如 `pytest tests/`。並確保 `pytest.ini` 設定了 `norecursedirs = XBrainLab`。

### "Segmentation Fault" 或 "Process Crash"
- **原因**: 試圖在沒有模擬顯示器的情況下執行 PyQt 測試，或者在測試中混合了 Thread 與 Qt Signal。
- **解法**: 使用 `pytest-qt` 提供的 `qtbot` fixture。避免使用 `time.sleep()`，改用 `qtbot.wait(100)`。

### "Attributes missing on Mock"
- **原因**: 使用 `MagicMock(spec=Study)` 建立的 Mock 物件雖然允許方法呼叫，但不會自動產生嵌套屬性 (Nested attributes)。
- **解法**: 對於複雜的嵌套呼叫 (如 `get_controller`)，請明確設定 `return_value` 或 `side_effect`。
