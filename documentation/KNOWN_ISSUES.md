# 已知問題 (Known Issues)

本文件記錄目前專案中已確認存在的 Bug、限制與待解決的問題。

## 🔴 高優先級 (High Priority)

### Backend & Training
- [x] **Missing Training Parameters (訓練參數缺失)**：
    - **問題**：`configure_training` 工具不支援 `optimizer` (Adam/SGD) 與 `save_checkpoints_every` (Epochs) 參數。
    - **狀態**：已修復 (v0.3.5)。已更新 `TrainingOption` 與工具鏈。

- [x] **Training VRAM Leak (記憶體洩漏)**：
    - **問題**：`train_one_epoch` 中雖然已加入 `.detach().cpu()`，但在 Epoch 結束後未呼叫 `torch.cuda.empty_cache()`，長時訓練仍可能累積片段記憶體。
    - **狀態**：已修復 (v0.3.5)。已加入 `empty_cache`。

- [x] **Dataset RAM Usage (記憶體佔用)**：
    - **問題**：`Dataset.get_training_data` 使用 Numpy Boolean Masking 直接複製數據 (`X = data[mask]`)，導致記憶體倍增。
    - **狀態**：已修復 (v0.3.5)。已新增 Index helper 並警示使用者。

### Agent
- [x] **Agent Unbounded Memory (記憶體無限增長)**：
    - **問題**：`LLMController.history` 無上限增長，會導致 Context Window Overflow 或 Memory Leak。
    - **狀態**：已修復 (v0.3.5)。已實作 Sliding Window。

## 🟠 穩定性與架構 (Stability & Architecture)

- [x] **UI Silent Failures (靜默失敗)**：
    - **問題**：`AggregateInfoPanel.update_info` 與 `VisualizationPanel` 存在 `try...except: pass`，導致錯誤無法被發現。
    - **狀態**：已修復 (v0.3.5)。已加入 Logger。

- [ ] **Architecture Coupling (架構耦合)**：
    - **問題**：雖已引入 Controller，但 `TrainingPanel` 仍偶爾直接存取 `self.study.epoch_data` 等後端物件。
    - **狀態**：建議持續重構以完全隔離。

## 🟡 環境與測試 (Environment & Tests)

- [x] **Dependency Conflict (依賴衝突)**：
    - **問題**：`requirements.txt` 同時包含 `nvidia-*-cu11` 與 `nvidia-*-cu12`，且未鎖定 PyTorch 版本。
    - **狀態**：已修復 (v0.3.5)。已統一版本與移除衝突。

- [ ] **Test File Fragmentation (測試分散)**：
    - **問題**：測試檔案散落在 `XBrainLab/tests` 與各模組目錄中。
    - **狀態**：需統一移動至根目錄 `tests/`。

- [ ] **Headless Qt/Torch Conflict**：
    - **問題**：無頭模式下需強制預載 Torch 以避免 SIGABRT。
    - **狀態**：目前以 Workaround 處理 (`tests/conftest.py`)。
