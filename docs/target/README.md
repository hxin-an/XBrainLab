# XBrainLab Target

最後更新：`2026-05-04`

這個資料夾定義 XBrainLab 的目標態。

它不是目前實作狀態，也不是短期施工清單。它回答的是：

- XBrainLab 最終想成為什麼？
- 哪些需求已經確定？
- 理想架構應該長什麼樣子？
- agent 在產品裡應該扮演什麼角色？

## 文件分工

| 文件 | 用途 |
| --- | --- |
| [requirements.md](requirements.md) | 需求與產品邊界，不寫實作細節。 |
| [architecture.md](architecture.md) | 理想系統架構與 backend command surface。 |
| [data_interpretation_system.md](data_interpretation_system.md) | 資料匯入、label / event 解讀、BIDS、recipe、UI / agent 行為的終局設計。 |
| [agent.md](agent.md) | agent 目標、local-only runtime、tool-call 驗證方向。 |

## 核心目標

XBrainLab 的目標不是單純把 EEG GUI 加上聊天視窗，而是做成：

```text
human user 和 in-app assistant 都能操作同一套 EEG workflow 的桌面應用
```

這代表：

- UI、agent tools、headless scripts、MCP external agents 不應各走一套 workflow。
- 後端能力應收斂成共用 Application Service / Command API。
- 資料匯入目標是建立可預覽、可驗證、可重跑的 Data Interpretation，不只是 load file 或 attach label。
- assistant 是 workflow operator，不是普通 chatbot，也不是外部 coding agent。
- validation 是 thesis-critical，不是最後補上的測試。
- assistant product runtime 已 local-only；remote backend modules 已從 product package 移除。
- `openai` / `google-genai` 只允許留在 optional `legacy-remote-llm` dependency group /
  legacy fixture，不是產品 execution path。

## 和其他文件的關係

- `target/`：目標態與需求。
- `architecture/`：目前實際架構與已驗證邊界。
- `planning/`：接下來怎麼走。
- `decisions/`：已定下來的決策。
- `records/`：過去做過什麼。

如果 `target/` 和 source code 衝突，代表目標尚未實作；不能把目標文件當成已完成事實。
