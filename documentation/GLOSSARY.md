# 術語表 (Glossary)

本文件解釋 XBrainLab 專案中常用的領域術語。

## EEG 相關
*   **Epoch**: 從連續腦波訊號中切分出的特定時間片段，通常以事件 (Event) 為中心。
*   **Montage**: 電極在頭皮上的配置方式 (如 10-20 系統)。
*   **ICA (Independent Component Analysis)**: 獨立成分分析，常用於去除眼動 (EOG) 或肌肉 (EMG) 雜訊。
*   **Artifact**: 雜訊，指非腦源性的訊號干擾。

## 系統相關
*   **Study**: XBrainLab 的核心管理類別，負責統籌 Dataset、Model 與 Training Process。
*   **Agent**: 系統中的 AI 助手，負責回答使用者問題與執行指令。
