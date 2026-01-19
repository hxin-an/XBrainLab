# ADR-004: UI 刷新機制演進 (UI Refresh Mechanism Evolution: Pull -> Bridge -> Event-Driven)

## 狀態 (Status)
**已修訂 (Revised)** - 2026-01-18
**原始接受 (Accepted)** - 2026-01-17 (Pull Model)

## 背景 (Context)
在 2026-01-17 的決策中，為了避免 Backend 依賴 PyQt6，我們選擇了 **Pull Model (輪詢)**。然而，在整合 **LLM Agent** 後，發現 Pull Model 存在嚴重問題：
1. **Agent 背景執行緒問題**：Agent 在 Worker Thread (QThread) 更新 Backend 狀態，但 UI 輪詢通常發生在主執行緒，且 Qt 無法感知背景的變更時機，導致資料載入後表格呈現空白。
2. **延遲與資源**：輪詢機制在 Agent 操作期間造成不必要的 CPU 開銷，且反應有延遲。

## 決策 (Decision)

**採用 `QtObserverBridge` 實現 Event-Driven (Push) 架構，同時保持 Backend 與 UI 的解耦。**

### 核心概念：Observer Bridge Pattern

我們引入了一個中間層 `QtObserverBridge` (`XBrainLab/ui/utils/observer_bridge.py`)：

1. **Backend (Pure Python)**:
   - 使用 `XBrainLab/backend/utils/observer.py` 中的 `Observable` 類別。
   - **完全不依賴 Qt**。
   - 僅發出純 Python 事件通知 (`self.notify("data_changed")`)。

2. **Bridge (PyQt)**:
   - 位於 UI 層 (依賴 Qt)。
   - 訂閱 Backend 的 `Observable`。
   - 當收到通知 (來自任意執行緒) 時，發射 `pyqtSignal`。
   - 利用 Qt 的 **Signal/Slot (QueuedConnection)** 自動處理跨執行緒通信。

3. **UI (PyQt)**:
   - 連接 Bridge 的信號來觸發 `update_panel`。
   - 確保所有 UI 更新都在 **Main Thread** 執行。

### 架構圖

```text
┌──────────────┐       ┌──────────────┐       ┌──────────────┐
│ Backend (Thread A) │   Notify   │ QtObserverBridge │   Signal   │ UI (Main Thread) │
│   (Pure Python)    ├───────────►│     (PyQt)       ├───────────►│   (PyQt Slot)    │
└──────────────┘       └──────────────┘       └──────────────┘
      Observable.notify()        Bridge._on_event()       Bridge.triggered.emit()
```

## 理由 (Rationale)

### 為什麼推翻 Pull Model (Polling)?
- **Agent 相容性**: Agent 在背景執行緒操作 Backend，Polling 機制容易因為線程競爭或更新時機不對而導致 GUI 不同步 (White Screen Issue)。
- **即時性**: 使用者期望指令下達後立即看到結果 (如 `load_data`)。

### 為什麼現在可以接受 Push Model?
- 之前拒絕 Push 是因為不想讓 Backend 繼承 `QObject`。
- **解決方案**: `Observable` (Backend) + `QtObserverBridge` (UI/Utils) 完美解決了耦合問題。Backend 依然是 Pure Python，只有 Bridge 依賴 Qt。

## 實際運作方式 (Implementation Details)

### Backend (DatasetController)
```python
# 純 Python，無 Qt 依賴
from XBrainLab.backend.utils.observer import Observable

class DatasetController(Observable):
    def import_files(self, paths):
        # ... logic ...
        self.notify("data_changed")
```

### UI (DatasetPanel)
```python
# UI 層使用 Bridge 進行連接
from XBrainLab.ui.utils.observer_bridge import QtObserverBridge

class DatasetPanel(QWidget):
    def __init__(self, parent):
        # 建立 Bridge: 監聽 controller 的 "data_changed" 事件
        self.bridge = QtObserverBridge(self.controller, "data_changed", self)
        # 連接 Signal 到 UI 更新函數 (自動處理 Thread Safety)
        self.bridge.connect_to(self.update_panel)

    def update_panel(self):
        # 安全地在 Main Thread 更新表格
        self.table.reloadData()
```

## 後果 (Consequences)

### 正面影響 ✅
1. **Thread Safety**: 完美解決後台 Agent 操作導致的 UI 刷新問題。
2. **Decoupling**: Backend 依然維持 Headless 可測試性 (無 Qt)。
3. **Responsiveness**: UI 即時響應，無 Polling 延遲。

### 負面影響 ⚠️
1. **複雜度微增**: 需要理解 Bridge 模式。
2. **記憶體管理**: 需要確保 Bridge 與 Panel 生命週期一致 (通常 Bridge 為 Panel 的子物件，自動清理)。

## 相關決策 (Related Decisions)
- [0.5.0] 引入 `QtObserverBridge`。
