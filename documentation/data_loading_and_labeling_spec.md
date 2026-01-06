# 資料載入與標籤對齊系統規格書 (Data Loading & Label Alignment Specification)

**日期**: 2026-01-06
**狀態**: 草案 (Draft)
**目標**: 重構現有的資料載入與標籤匯入流程，提升系統對真實世界腦波資料（含雜訊、遺失 Trigger、無硬體 Trigger）的相容性與強健性。

---

## 1. 支援檔案格式規格 (Supported File Formats)

### 1.1 腦波原始資料 (Raw EEG Data)
後端需提供統一介面 `load_raw_data(filepath)`，並支援以下格式：

| 格式 | 副檔名 | 載入引擎 (Backend) | 備註 |
| :--- | :--- | :--- | :--- |
| EEGLAB | `.set` | `mne.io.read_raw_eeglab` | 優先嘗試 Raw，失敗則嘗試 Epochs |
| GDF (BIOSIG) | `.gdf` | `mne.io.read_raw_gdf` | 常見於 BCI Competition 資料 |
| MNE-Python | `.fif` | `mne.io.read_raw_fif` | MNE 原生格式 |
| European Data Format | `.edf` | `mne.io.read_raw_edf` | 通用格式 |
| BioSemi | `.bdf` | `mne.io.read_raw_bdf` | 24-bit 格式 |
| Neuroscan | `.cnt` | `mne.io.read_raw_cnt` | |
| BrainVision | `.vhdr` | `mne.io.read_raw_brainvision` | 需搭配 .eeg 和 .vmrk |

### 1.2 標籤/事件檔案 (Label/Event Data)
需支援「純序列」與「含時間戳記」兩種模式。對於含時間戳記的格式，預設時間單位為 **秒 (Seconds)**。

| 類型 | 副檔名 | 格式範例 | 處理邏輯 |
| :--- | :--- | :--- | :--- |
| **純序列 (Sequence)** | `.txt` | `1 2 1 3 ...` (空白或換行分隔) | 需與 EEG 硬體 Trigger 對齊 |
| **純序列 (Sequence)** | `.mat` | MATLAB 陣列/矩陣 | 需與 EEG 硬體 Trigger 對齊 |
| **簡易時間戳 (Simple)** | `.csv` | `time, label` | **忽略** EEG 硬體 Trigger，直接依時間建立事件。Duration 預設為 0。 |
| **BIDS 風格 (Standard)** | `.tsv`, `.csv` | `onset, duration, trial_type` | 符合 BIDS 標準。`onset` 為開始時間(秒)，`duration` 為持續時間(秒)。 |

---

## 2. 系統架構優化 (Architecture Improvements)

### 2.1 後端工廠模式 (Backend Factory)
*   **類別**: `RawDataLoaderFactory` (新增)
*   **職責**: 接收檔案路徑，自動判斷格式並回傳 `Raw` 物件。
*   **改動**: 移除 `DatasetPanel` 中的 `if .set ... elif .gdf ...` 邏輯。

### 2.2 記憶體優化 (Lazy Loading)
*   **機制**: 預設使用 `preload=False` 呼叫 MNE 讀取函數。
*   **影響**: 僅讀取 Header 資訊，大幅縮短開啟時間，避免 OOM。僅在 Preprocessing 或 Visualization 需要數據時才載入片段。

### 2.3 錯誤處理 (Error Handling)
*   **定義異常**:
    *   `FileCorruptedError`: 檔案損毀。
    *   `UnsupportedFormatError`: 格式不支援。
    *   `DataMismatchError`: 資料參數不一致 (如 Sampling Rate 不同)。
*   **UI 行為**: 捕捉上述異常，彈出具體錯誤訊息視窗，而非通用的 "Load failed"。

---

## 3. 標籤匯入詳細流程 (Label Import Workflow)

這是本次改動的核心，分為三個階段。

### 階段一：格式偵測與分流 (Detection & Branching)
1.  使用者選擇標籤檔。
2.  後端解析檔案內容：
    *   **若包含時間欄位 (Timestamp Mode)**: 進入 **流程 A**。
        *   包含 `time` 或 `latency` 欄位 (簡易格式)。
        *   包含 `onset` 欄位 (BIDS 格式)。
    *   **若僅含標籤數值 (Sequence Mode)**: 進入 **流程 B**。

### 階段二：匯入執行 (Execution)

#### **流程 A: 時間戳記匯入 (Timestamp-based)**
1.  讀取列表：
    *   簡易格式：讀取 `(time, label)`。
    *   BIDS 格式：讀取 `(onset, duration, trial_type)`。
2.  直接在 `Raw` 物件中建立新的 `mne.Annotations` 或 Events。
    *   若為 BIDS，將 `trial_type` 作為標籤名稱，`onset` 作為時間點，`duration` 作為持續時間。
3.  **完成**。 (不需對齊，不需過濾)

#### **流程 B: 序列對齊匯入 (Sequence-based)**
此流程需解決「外部標籤序列」與「內部 EEG Trigger」不一致的問題。

1.  **智慧過濾 (Smart Filtering)**:
    *   **輸入**: 外部標籤數量 $N_{label}$，內部各 Event ID 的計數 $\{ID_1: C_1, ID_2: C_2, ...\}$。
    *   **演算法**: 尋找子集 $S \subseteq \{ID_i\}$ 使得 $\sum_{ID \in S} C_{ID} \approx N_{label}$。
    *   **UI**: 彈出 `EventFilterDialog`，**預設勾選** 集合 $S$ 中的 ID。
    *   **使用者確認**: 使用者按 OK (或手動修改)。

2.  **序列對齊 (Sequence Alignment)**:
    *   **輸入**: 過濾後的內部 Trigger 序列 $Seq_{EEG}$，外部標籤序列 $Seq_{Label}$。
    *   **檢查**: 若 $Length(Seq_{EEG}) == Length(Seq_{Label})$，直接一對一映射。
    *   **演算法 (若長度不符)**: 執行 **LCS (Longest Common Subsequence)** 或 **DTW**。
        *   找出最佳匹配路徑，標記出「多餘的 EEG Trigger (Noise)」或「遺失的 Label」。
    *   **自動修復**: 根據演算法結果，跳過雜訊 Trigger，將標籤填入正確位置。

3.  **視覺化修正 (Visual Correction) - (Fallback)**:
    *   **觸發條件**: 若演算法信心分數過低，或使用者選擇「手動修正」。
    *   **UI**: 顯示雙軌時間軸 (EEG Triggers vs Labels)。
    *   **操作**: 使用者拖曳連線至少一個關鍵點 (Anchor)，系統依此重新執行對齊。

---

## 4. UI 介面需求 (UI Requirements)

### 4.1 DatasetPanel
*   移除檔案格式判斷邏輯。
*   增加錯誤訊息視窗的詳細度。

### 4.2 ImportLabelDialog
*   新增 `.csv`, `.tsv` 檔案過濾器。
*   若偵測到 CSV，隱藏 "Event Mapping" 表格 (因 CSV 通常已包含類別名稱)，或自動填入。

### 4.3 EventFilterDialog (增強版)
*   新增「自動偵測」按鈕 (或預設執行)。
*   顯示每個 Event ID 的出現次數與目標標籤數量的對比。

### 4.4 VisualAlignmentDialog (新增 - 選配)
*   **畫布**: 繪製兩條序列的時間軸。
*   **互動**: 支援滑鼠點擊配對。
*   **預覽**: 顯示對齊後的誤差統計。

---

## 5. 單元測試案例 (Unit Test Cases)

### 5.1 資料載入測試 (Data Loading Tests)
*   **Test 1: Factory Pattern**: 驗證 `RawDataLoaderFactory` 能正確根據副檔名回傳對應的 Loader。
*   **Test 2: Lazy Loading**: 驗證 `preload=False` 時，資料未被讀入記憶體，但 Metadata (n_times, sfreq) 正確。
*   **Test 3: Error Handling**: 傳入損毀檔案或不支援格式，驗證是否拋出正確的自定義異常。

### 5.2 標籤匯入測試 (Label Import Tests)
*   **Test 4: Timestamp Import**: 匯入 CSV `(time, label)`，驗證 `Raw` 物件中的 Annotations 是否在正確時間點建立。
*   **Test 5: Smart Filter (Perfect Match)**: 模擬 EEG 有 `ID:1 (100次), ID:255 (5次)`，標籤有 100 個。驗證過濾器自動選取 `ID:1`。
*   **Test 6: Sequence Alignment (Noise)**: 模擬 EEG 序列 `[A, B, X, C]` (X為雜訊)，標籤序列 `[A, B, C]`。驗證演算法能正確忽略 X 並對齊。
*   **Test 7: Sequence Alignment (Missing)**: 模擬 EEG 序列 `[A, C]` (B遺失)，標籤序列 `[A, B, C]`。驗證演算法能標記 B 為遺失。
