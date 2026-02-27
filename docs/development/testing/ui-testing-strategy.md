# XBrainLab UI Testing Strategy

這份文件說明 XBrainLab 專案目前的 UI 測試策略與實作細節。

## 核心理念

我們的 UI 測試採用 **Unit Testing** 層級的策略，旨在驗證 UI 邏輯與後端互動的正確性，而非進行端對端 (E2E) 的視覺回歸測試。我們隔離了外部依賴 (如資料庫、硬體、複雜運算)，專注於測試：

1.  **使用者互動**: 點擊按鈕、切換分頁是否觸發預期行為。
2.  **狀態更新**: UI 是否正確反映後端資料的變化。
3.  **後端呼叫**: UI 是否攜帶正確參數呼叫後端 API (Study/Controller)。

## 測試工具

專案主要使用以下工具：

-   **pytest**: 測試框架核心。
-   **pytest-qt**: 提供 `qtbot` fixture，允許在 headless 環境下模擬 PyQt 事件 (點擊、輸入、等待)。
-   **unittest.mock**: 用於模擬後端物件 (`Study`, `Controller`) 和彈出視窗 (`QMessageBox`, `QDialog`)。

## 測試模式範例

### 1. 隔離後端與 UI 互動

我們不會在 UI 測試中啟動真實的 backend 邏輯，而是將 `Study` 物件 Mock 起來。

```python
@pytest.fixture
def panel(self, qtbot):
    # 建立 Mock 的 MainWindow 和 Study
    main_window = QMainWindow()
    main_window.study = MagicMock()

    # 初始化要測試的 Panel (注入 mock 依賴)
    panel = TrainingPanel(main_window)
    qtbot.addWidget(panel)
    return panel

def test_start_training(self, panel):
    # 模擬後端狀態
    panel.study.is_training.return_value = False

    # 觸發 UI 動作
    panel.start_training()

    # 驗證是否正確呼叫後端方法
    panel.controller.start_training.assert_called_once()
```

### 2. 處理彈出視窗 (Modal Dialogs)

PyQt 的彈出視窗 (如 `exec()`) 會阻塞執行緒，導致測試卡死。我們使用 `patch` 來攔截這些呼叫並模擬使用者回應。

```python
# 模擬使用者在設定視窗點擊 "OK" 並回傳模擬結果
with patch('XBrainLab.ui.training.panel.ModelSelectionWindow') as MockWindow:
    instance = MockWindow.return_value
    instance.exec.return_value = True  # 模擬 Dialog 回傳 Accepted
    instance.get_result.return_value = mock_holder

    # 模擬跳出的 Success 訊息框
    with patch('XBrainLab.ui.training.panel.QMessageBox.information'):
        panel.select_model()

    # 驗證結果是否被傳遞給 Study
    panel.study.set_model_holder.assert_called_once_with(mock_holder)
```

### 3. 使用 qtbot 操作元件

雖然在這個修復任務中沒用到，但 `qtbot` 是操作真實 Widget 的關鍵：

```python
def test_button_click(panel, qtbot):
    # 模擬滑鼠點擊
    qtbot.mouseClick(panel.btn_start, Qt.MouseButton.LeftButton)

    # 等待訊號或狀態改變
    # qtbot.waitSignal(panel.task_finished)
```

## 注意事項 (Lessons Learned)

在本次修復 `TestTrainingPanel` 時，我們學到了：

-   **Mock 的狀態不會自動更新**: 呼叫 `mock.set_value(x)` 不會自動讓 `mock.value` 變成 `x`。必須在測試中手動設定 Mock 的屬性來模擬狀態改變。
-   **檢查依賴關係**: 重構代碼時，必須檢查測試中 Mock 的對象是否還存在。例如 `TrainingPanel` 改為直接操作 `Study`，測試卻還在檢查 `Controller`，導致失敗。
