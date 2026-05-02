# Target Requirements

最後更新：`2026-05-01`

這份文件定義 XBrainLab 的需求與產品邊界。

它描述的是目標態，不代表目前程式碼已經全部做到。

## 產品定位

XBrainLab 是本地 EEG 分析桌面應用。它的核心不是聊天，也不是單純模型 demo，而是讓使用者在桌面環境中完成 EEG 資料分析 workflow：

```text
資料匯入 -> label / event 對齊 -> 前處理 -> epoch / dataset -> 模型訓練 -> 評估 -> 視覺化 / 解釋
```

tool-call agent 是建立在這個本體 workflow 上的操作方式。也就是說，assistant 不能取代 XBrainLab 本體需求；它只能透過同一套能力面幫使用者操作、檢查、解釋或接續 workflow。

它同時需要滿足兩種使用方式：

- 人透過 PyQt UI 操作 EEG workflow。
- app 內 assistant 透過 tool calls 操作同一套 workflow。

## 主要使用者

XBrainLab 目標使用者不是雲端 ML 平台使用者，而是需要在本機處理 EEG workflow 的研究 / 開發使用者：

- 需要載入不同 EEG 檔案格式的人。
- 需要把事件、label、channel、epoch 和資料集切分對齊的人。
- 需要跑基本模型訓練與評估的人。
- 需要檢查訓練結果、可視化結果和中間狀態的人。
- 需要讓 assistant 協助操作 workflow，但仍能理解系統目前狀態的人。

## 已確認需求

### EEG workflow 本體

XBrainLab 本體應至少覆蓋以下 workflow 能力：

- 匯入 EEG raw / epoched data。
- 顯示資料基本資訊，例如檔案、channel、sampling rate、event / label 狀態。
- 匯入或對齊 label / event mapping。
- 執行可追蹤的 preprocess 操作。
- 由 preprocessed data 產生 epoch / dataset。
- 設定模型、訓練參數和訓練計畫。
- 啟動、停止或監看訓練。
- 查看 evaluation metrics。
- 查看基本 visualizations / saliency / topomap / spectrogram 等分析結果。

這些能力要先作為 app 本體能力成立，assistant 才能可靠地調用。

### 桌面應用體驗

- XBrainLab 是本地桌面 app，不是 cloud-first service。
- 使用者應能靠 UI 理解目前所在 workflow stage。
- 長任務不能凍結 UI；loading、progress、error 要有明確 feedback。
- 同一個資料狀態不能被 UI、controller、agent 同時改到不一致。
- 常見錯誤要能回報人能理解的原因，而不是只丟 Python exception。
- 沒有 agent 時，核心 EEG workflow 仍應可用。

### 資料與狀態可追蹤

- raw data、preprocessed data、epoch、dataset、training state 應有清楚 ownership。
- 每次重要狀態轉換都應能判斷成功、失敗或尚未開始。
- UI 顯示狀態、backend state、assistant 看到的 workflow state 應一致。
- 中間資料的 copy / in-place / swap 行為要有明確邊界，避免 UI 正在讀取的資料被隱性改掉。
- dataset split、label mapping、event normalization 等會影響結果的操作要能被紀錄或重建。

### 訓練與評估

- 使用者應能設定模型與基本訓練參數。
- 訓練啟動前應能檢查資料集是否就緒。
- 訓練中應能呈現進度、錯誤和停止狀態。
- 訓練結果應能被 evaluation / visualization 讀取。
- 評估結果要能和訓練設定、資料狀態對應，不應只剩無來源的數字。

### 視覺化與解釋

- visualization 應服務 EEG workflow，不只是畫圖功能。
- 使用者應能知道圖表對應哪個資料、模型、channel 或 trial。
- saliency / topomap / spectrogram 類結果要能標示前置條件，例如是否需要訓練結果、montage、channel info。
- 視覺化失敗時要能說明缺哪個狀態或資料。

### Local-first / local-only assistant

- assistant product runtime 已 local-only，不以 Gemini / remote API 作為產品 execution path。
- 本地模型、模型 cache、GPU / CPU fallback、timeout、stop generation 必須可驗證。
- remote backend modules 已從 product package 移除；`api` / `gemini` legacy selection 必須
  migrate local 或 fail closed，不可 instantiate remote backend。
- `openai` / `google-genai` 不在 default dependencies；若歷史比較仍需要，只能放 optional
  `legacy-remote-llm` dependency group / legacy fixture，且 product code 不可 import。
- 真 local LLM 長時間 ChatPanel walkthrough 仍未完成，不能用 standalone runtime smoke 取代。

### 同一套 workflow 能力面

- UI button、agent tool、headless script 應呼叫同一套 backend capability。
- 不應讓 UI、agent、script 各自實作 import / preprocess / training / evaluation 流程。
- workflow command 的輸入、輸出、錯誤與狀態應可被測試和紀錄。

### 穩定桌面應用

- UI 不應因 agent、長任務、資料載入或訓練狀態切換而閃退。
- 背景工作和 UI 更新要有清楚 thread / event 邊界。
- 使用者可理解目前 workflow stage、資料狀態、訓練狀態和錯誤原因。
- assistant、UI 和 headless script 不應互相破壞狀態。

### 可驗證 EEG pipeline

- data import、label/event mapping、preprocess、epoch、dataset、training、evaluation 要能分層驗證。
- mock-heavy unit tests 只能作 regression floor，不能取代 non-mocked workflow evidence。
- real-data IO、tiny pipeline smoke、public fixture smoke、thesis validation 要分層處理。

### Thesis evidence

- dashboard clean 不能被宣稱為 thesis claim 成立。
- thesis evidence 需要建立一套 agent tool-call 評分工具，而不是只靠人工觀察聊天結果。
- 評分工具應能跑固定 benchmark cases，輸出可重跑的 report / artifact。
- tool-call 準確率至少要拆成 intent mapping、tool selection、parameter correctness、state transition、error recovery。
- 每個 agent / EEG workflow claim 最後都應對到 command、test、artifact、experiment、score report 或明確限制。
- 舊 Gemini/API benchmark 只能作歷史參考；新的 thesis evaluation 應對齊 local-only runtime 和新的 command surface。

## 非目標

- 不把 XBrainLab 做成 cloud-first 平台。
- 不把 assistant 做成 XBrainLab 的唯一入口。
- 不為了 agent 犧牲人類 UI 的可理解性與可操作性。
- 不在完成架構複盤前大改後端。
- 不把 dataset testing 拆成當前獨立主線；它屬於穩定化與 validation。
- 不恢復舊 AQ / Prep Gate / Repair Loop automation。
- 不讓新文件再次膨脹成大量短期 agent 產物。
