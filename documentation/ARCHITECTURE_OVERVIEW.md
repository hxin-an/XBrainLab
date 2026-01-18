# XBrainLab 架構總覽 (Architecture Overview)

本文檔說明 XBrainLab 的核心架構，特別是 **UI**, **Agent**, 與 **Backend** 三者之間的互動關係。

## 核心概念：雙核心驅動 (Dual-Core Driver)

XBrainLab 的架構設計允許 **人類使用者 (透過 UI)** 與 **AI Agent (透過 Facade)** 同時操作同一個後端系統，且互不衝突。

### 1. Backend Layer (後端層) - 唯一的真理
後端是整個系統的核心，負責資料儲存與邏輯運算。
*   **特性**：純 Python 實作，完全不依賴圖形介面 (Headless)。
*   **Study (狀態)**：持有所有載入的資料 (Raw Data) 和訓練模型。它是唯一的「狀態來源」。
*   **Controllers (邏輯)**：負責具體的操作流程，例如「載入資料」、「開始訓練」。
*   **Facade (門面)**：專為 Agent 設計的統一入口，簡化了與 Controller 的互動。

### 2. UI Layer (介面層) - 被動觀察者
UI 負責將後端的狀態顯示給人類使用者。
*   **特性**：被動 (Passive)。它不持有邏輯，只負責顯示。
*   **拉取模式 (Pull Model)**：UI 不會直接修改畫面。當它發送指令給後端後，它會等待後端通知，然後重新從後端「拉取」最新的資料來刷新畫面。
*   **觀察者 (Observer)**：UI 訂閱了後端的通知。如果 Agent 在背景修改了資料，UI 會收到通知並自動刷新，使用者會看到畫面同步更新。

### 3. Agent Layer (代理層) - 盲眼操作者
AI Agent 是一個在背景運作的智慧體。
*   **特性**：看不見 UI。
*   **操作方式**：它透過 `BackendFacade` (遙控器) 直接對後端下達指令 (如 `load_data`)。
*   **獨立性**：Agent 可以在沒有 UI 的情況下獨自運作 (例如在伺服器上跑腳本)。

---

## 互動流程範例

### 場景：載入資料
1.  **Agent 發起**：Agent 呼叫 `facade.load_data("file.edf")`。
2.  **後端執行**：`DatasetController` 讀取檔案，更新 `Study` 中的資料列表。
3.  **發送通知**：`DatasetController` 完成後，發出 `data_changed` 通知。
4.  **UI 響應**：
    *   UI 收到 `data_changed` 通知。
    *   UI 呼叫 `controller.get_loaded_data_list()` 重新抓取資料。
    *   UI 更新列表顯示，使用者看到新檔案出現。

透過這種架構，我們確保了無論是誰操作，系統狀態永遠保持一致，且具備高度的可測試性與擴展性。
