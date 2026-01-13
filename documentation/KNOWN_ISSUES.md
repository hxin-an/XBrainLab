# 已知問題 (Known Issues)

本文件記錄目前專案中已知的 Bug、限制與待解決的問題。

## 高優先級 (High Priority)
- [ ] **測試失敗**：部分 `dataset` 與 `training` 模組的單元測試目前無法通過。
- [ ] **UI 效能**：載入大型 EEG 檔案時，主視窗可能會暫時無回應 (需優化 Threading)。

## 待改進 (Improvements)
- [ ] **Agent 回應速度**：RAG 檢索目前速度較慢，需優化向量資料庫查詢。
- [ ] **錯誤處理**：部分後端錯誤未在 UI 顯示友善的提示訊息。
