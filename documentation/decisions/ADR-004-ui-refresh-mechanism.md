# ADR-004: UI 刷新機制選擇 (UI Refresh Mechanism: Pull vs Push Model)

## 狀態 (Status)
**已接受 (Accepted)** - 2026-01-17

## 背景 (Context)
XBrainLab 採用 PyQt6 桌面應用程式架構，需要在 Backend 狀態變更時更新 UI。有兩種主要方案：

1. **Push Model (推送模式)**：Backend 透過 `pyqtSignal` 主動通知 UI
2. **Pull Model (拉取模式)**：UI 透過定時器（`QTimer`）主動輪詢 Backend 狀態

專案初期文檔（`agent_architecture.md`）描述了 Push Model 的設計，但實際實現採用 Pull Model，造成文檔與代碼不一致。

## 決策 (Decision)

**採用 Pull Model 作為主要 UI 刷新機制，在特定低頻場景下可於 Controller 層使用 Signal。**

### 具體實現
- **Backend (`Study` 類別)**：保持純 Python，不繼承 `QObject`，不發送任何 Signal
- **高頻更新場景**（如訓練中）：UI 使用 `QTimer` 每 100ms 輪詢 Controller
- **低頻事件**（如文件導入完成）：可在 Controller 層使用 Signal，但 Backend 本身不依賴 Qt

```python
# Backend: 純 Python
class Study:
    def __init__(self):
        self.loaded_data_list = []
        # 無 QObject, 無 Signal

# UI: 主動輪詢
class TrainingPanel:
    def __init__(self):
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_loop)
        self.timer.start(100)  # 每 100ms 查詢一次

    def update_loop(self):
        if self.controller.is_training():
            data = self.controller.get_formatted_history()
            self.update_ui(data)
```

## 理由 (Rationale)

### Pull Model 的優勢

#### 1. **框架獨立性** 🎯
- Backend 可用於 CLI、Web API、Jupyter Notebook
- 未來技術棧遷移成本低（PyQt → Web → Electron）
- 符合專案長期目標（多平台支援）

#### 2. **測試友好性** ✅
- 2020+ 單元測試無需 Qt 環境
- CI/CD 管線簡單（無需虛擬顯示 Xvfb）
- 純 Python Backend 測試更快速

#### 3. **架構清晰性** 📐
- 依賴方向單一：UI → Backend
- 無反向依賴（Backend 不知道 UI 存在）
- 新手容易理解（狀態查詢 vs 信號傳播）

#### 4. **調試容易性** 🐛
- 狀態查詢失敗返回錯誤值（可見）
- Signal 遺失導致靜默失敗（不可見）
- 輪詢邏輯集中在 UI 層，易追蹤

### Pull Model 的代價

1. **延遲**：最多 100ms 刷新延遲（人類感知閾值 ~150ms，可接受）
2. **CPU 開銷**：每秒 10 次狀態查詢（但讀取操作很輕量）
3. **代碼冗餘**：每個 Panel 需要實現輪詢邏輯

### Push Model 的問題

如果採用 Push Model，Backend 必須：
```python
# Backend 依賴 Qt 框架 ❌
from PyQt6.QtCore import QObject, pyqtSignal

class Study(QObject):
    data_loaded = pyqtSignal(str)
    training_finished = pyqtSignal(dict)
```

這導致：
- ❌ Backend 綁定 PyQt6，無法獨立運行
- ❌ 單元測試需要 Qt 環境
- ❌ 未來遷移到 Web 需要重寫所有 Signal 邏輯
- ❌ 多個 Panel 監聽同一信號可能引發性能問題

## 場景分析 (Context Analysis)

| 考量因素 | Pull Model | Push Model | XBrainLab 需求 | 結論 |
|---------|-----------|-----------|---------------|------|
| 更新頻率 | 訓練中每秒 10 次 | 每 Epoch 1-10 次 | 低頻 | ✅ Pull 足夠 |
| 即時性要求 | 100ms 延遲 | 即時 | 可接受 | ✅ Pull 足夠 |
| 多平台需求 | CLI + Web 計畫中 | 僅桌面版 | **有需求** | ✅ **Pull 優勢** |
| 測試覆蓋 | 高覆蓋率需求 | 一般 | **重要** | ✅ **Pull 優勢** |
| 現有代碼 | 已實現 | 需要重構 | 避免風險 | ✅ Pull 避免破壞 |

## 混合方案 (Hybrid Approach)

在某些情況下，可以在 **Controller 層**（而非 Backend）使用 Signal：

```python
# Controller 層可以依賴 Qt（職責明確）
class DatasetController(QObject):
    import_finished = pyqtSignal(int, list)  # 低頻事件

    def import_files(self, paths):
        # Backend 操作（純 Python）
        raw_list = self.study.load_data(paths)
        # Controller 發送信號（UI 層）
        self.import_finished.emit(len(raw_list), errors)
```

**原則**：
- ✅ Backend (`Study`) 保持純淨
- ✅ Controller 負責 UI 通訊
- ✅ 高頻場景用 Pull（訓練）
- ✅ 低頻場景可用 Signal（文件導入）

## 實際運作方式 (Implementation Details)

### 訓練中的輪詢機制
```python
# XBrainLab/ui/training/panel.py
def update_loop(self):
    # 1. 檢查訓練狀態
    if not self.controller.is_training():
        self.timer.stop()
        return

    # 2. 獲取最新數據
    history = self.controller.get_formatted_history()

    # 3. 更新 UI
    for data in history:
        record = data["record"]
        epoch = record.get_epoch()  # 直接讀取 Backend 狀態
        self.update_plot(epoch, record.train, record.val)
```

### Backend 無感知設計
```python
# XBrainLab/backend/training/trainer.py
class Trainer:
    def job(self):
        while self.current_idx < len(self.plans):
            plan = self.plans[self.current_idx]
            plan.train()  # 只改狀態，不通知任何人
            self.current_idx += 1
```

## 後果 (Consequences)

### 正面影響 ✅
1. Backend 完全框架無關，支持多平台部署
2. 單元測試簡單高效，覆蓋率高
3. 架構清晰，依賴單向
4. 未來遷移到 Web 成本低

### 負面影響 ⚠️
1. 100ms 刷新延遲（但可接受）
2. 定期輪詢有輕微 CPU 開銷
3. 每個 Panel 需實現輪詢邏輯

### 風險與緩解 🛡️
- **風險**：高頻輪詢可能影響性能
- **緩解**：訓練時才啟動定時器，完成後立即停止
- **風險**：輪詢邏輯重複
- **緩解**：未來可封裝為 `PollingMixin` 基類

## 相關決策 (Related Decisions)
- ADR-002: Multi-Agent Vision（Agent 不直接操作 UI）
- 未來 ADR：Controller 模式標準化

## 參考資料 (References)
- 實際代碼：`XBrainLab/ui/training/panel.py` (Lines 188-190, 617-732)
- Backend 設計：`XBrainLab/backend/training/trainer.py`
- Controller 設計：`XBrainLab/backend/controller/`

## 備註 (Notes)
- 初期文檔 (`agent_architecture.md`) 描述了 Push Model，但未實現
- 本 ADR 正式確認 Pull Model 為官方架構選擇
- 需要更新 `agent_architecture.md` 以反映實際設計
