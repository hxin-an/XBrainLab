# ADR-007：Real Tool Call 測試策略

- **狀態**: 已實作 (Implemented)
- **日期**: 2026-02-02（更新: 2026-02-25）
- **作者**: XBrainLab 團隊

> **實作狀況**: `--tool-debug` CLI 旗標已實作，Debug JSON 腳本已建立（`scripts/agent/debug/`），Headless 驗證工具已完成。

---

## 背景

開發者難以驗證 Real Tool Call 執行後 UI 是否正確呈現。接入 LLM 測試太慢、太貴、不穩定。

---

## 決策

採用雙軌測試策略：

1. **Interactive Debug Mode**：手動逐步驗證
2. **Headless UI Testing**：自動化 CI/CD 驗證

---

## 方法 1：Interactive Debug Mode（互動式偵錯）

### 使用方式

```bash
python run.py --tool-debug workflow.json
```

### 行為

1. 應用程式正常啟動（含完整 UI）
2. 開發者在 Agent 對話框**按 Enter**
3. 系統執行 `workflow.json` 中的**下一個 Tool Call**
4. 開發者**肉眼驗證** UI 是否正確
5. 再按 Enter → 執行下一個
6. 重複直到腳本結束

### 實作設計

```python
class ToolDebugMode:
    def __init__(self, script_path: str):
        with open(script_path) as f:
            self.script = json.load(f)
        self.index = 0

    def on_enter_pressed(self) -> Optional[ToolCall]:
        """Chat 輸入框按 Enter 時觸發"""
        if self.index >= len(self.script["calls"]):
            return None  # 腳本結束

        call = self.script["calls"][self.index]
        self.index += 1
        return ToolCall(name=call["tool"], params=call["params"])

# 在 ChatPanel 中
def on_send_clicked(self):
    if self.debug_mode:
        tool_call = self.debug_mode.on_enter_pressed()
        if tool_call:
            self.execute_tool(tool_call)
            self.show_message(f"[DEBUG] Executed: {tool_call.name}")
    else:
        # 正常 LLM 流程
        ...
```

### 用途

- 開發時手動驗證 UI
- Demo 展示預定義流程
- 調試特定工具的 UI 呈現

---

## 方法 2：Headless UI Testing（自動化測試）

### 使用方式

```bash
pytest tests/test_ui_integration.py
```

### 測試範例

```python
import pytest
from PyQt6.QtTest import QTest

def test_filter_updates_preview(test_app, sample_data):
    """驗證濾波後 Preview 正確更新"""
    controller = test_app.controller

    # 載入資料
    controller.execute_tool("load_data", {"path": sample_data})

    # 執行濾波
    result = controller.execute_tool("apply_filter", {"low": 0.5, "high": 50})
    assert result.success

    # 驗證 UI 狀態
    preview = test_app.preprocess_panel.preview_widget
    assert preview.plot_time.listDataItems()  # 有資料
    assert "0.5-50 Hz" in test_app.info_panel.get_summary()

def test_training_shows_progress(test_app, prepared_data):
    """驗證訓練中顯示進度"""
    controller = test_app.controller

    controller.execute_tool("start_training", {"epochs": 2})
    QTest.qWait(1000)  # 等待 UI 更新

    training_panel = test_app.training_panel
    assert training_panel.is_training_visible()
    assert training_panel.get_current_epoch() >= 0
```

### 用途

- CI/CD 自動化驗證
- 防止 UI 回歸
- 快速回饋（秒級完成）

---

## 腳本格式

```json
{
  "version": "1.0",
  "description": "Filter + Epoch workflow",
  "calls": [
    {"tool": "load_data", "params": {"path": "${TEST_DATA}/sample.fif"}},
    {"tool": "apply_filter", "params": {"low": 0.5, "high": 50}},
    {"tool": "create_epochs", "params": {"tmin": -0.5, "tmax": 1.0}}
  ]
}
```

---

## 實作階段

### Phase 1：Interactive Debug Mode
- [ ] 實作 `ToolDebugMode` 類別
- [ ] 修改 ChatPanel 支援 `--tool-debug` 模式
- [ ] 建立範例腳本 `scripts/debug_filter.json`

### Phase 2：Headless UI Testing
- [ ] 設定 pytest + QtTest 整合
- [ ] 建立 `test_app` fixture
- [ ] 撰寫核心工作流程測試

### Phase 3：CI/CD 整合
- [ ] GitHub Actions 執行 headless 測試
- [ ] 測試覆蓋率報告

---

## 影響評估

### 正面影響
- **手動驗證簡化**：不需 LLM 即可逐步測試
- **自動化驗證**：CI/CD 捕捉 UI 回歸
- **開發效率**：快速迭代工具開發

### 負面影響
- **腳本維護**：工具介面變更時需更新腳本
- **不涵蓋 LLM 決策**：只測「工具執行」，不測「LLM 選擇」
