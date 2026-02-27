# UI Architecture

## Overview

UI 層採用 **事件驅動 + 組合式元件** 架構，基於 PyQt6。

- **純呈現層**: 不直接存取 Backend 資料，僅透過 Controller 取得
- **事件驅動更新**: Controller 透過 Observable 推送狀態變更
- **執行緒安全**: 透過 `QtObserverBridge` 將背景執行緒事件安全傳入主執行緒
- **統一 Bridge 模式**: `BasePanel._create_bridge()` 簡化 Observer 橋接建立

## BasePanel

所有面板繼承 `BasePanel(QWidget)`，提供標準介面：

```python
class BasePanel(QWidget):
    def init_ui(self): ...              # 建立 UI 元件
    def update_panel(self, *args): ...  # Controller 事件觸發更新
    def _setup_bridges(self): ...       # 綁定 Controller 事件
    def _create_bridge(self, controller, event, handler):
        # 便利 helper — 自動建立、連接並管理 QtObserverBridge
        bridge = QtObserverBridge(controller, event, self)
        bridge.connect_to(handler)
        self._bridges.append(bridge)
        return bridge
    def set_busy(self, busy: bool): ... # 忙碌狀態
    def cleanup(self): ...              # 清理資源
```

## Panel 架構

```
MainWindow (QMainWindow)
└── QStackedWidget
    ├── DatasetPanel       # 2 bridges (data_changed, dataset_locked)
    ├── PreprocessPanel    # 3 bridges (preprocess_changed, data_changed, ...)
    ├── TrainingPanel      # 7 bridges (training_started/stopped/updated, ...)
    ├── EvaluationPanel    # 1 bridge
    ├── VisualizationPanel # 1 bridge
    └── ChatPanel          # 透過 AgentManager 與 LLMController 通訊
```

## QtObserverBridge — 執行緒安全

```
Backend Thread               Qt Main Thread
     │                            │
Controller.notify("event")        │
     │                            │
     ▼                            │
QtObserverBridge                  │
  ├── pyqtSignal.emit() ──────►  │
  │   (AutoConnection)            ▼
  │                         slot: panel.update_panel()
```

詳見 [完整 UI 文檔](../../documentation/ui/ARCHITECTURE_2_0.md)。
