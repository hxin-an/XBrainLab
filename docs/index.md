# XBrainLab 工程文件

這個網站說明目前產品如何組成、哪些事實可以宣稱，以及變更需要哪些驗證。內容主要提供給
貢獻者與維護者；桌面應用程式使用者請從 <a href="guide/">使用者指南</a>開始。

## 開始貢獻

第一次接觸這個 repository 時：

1. [建立本機開發環境](developer/local-setup.md)。
2. [找到預計修改行為的 owner](developer/repository-map.md)。
3. [選擇能直接證明變更的測試](developer/testing.md)。
4. [規劃、驗證並提交一個聚焦的變更](developer/change-workflow.md)。

## 我該跑哪個測試？

不需要每次把所有測試都跑一遍。先依這次修改的範圍選一個入口：

| 這次修改 | 測試入口 |
| --- | --- |
| 一個明確行為或錯誤 | [執行對應的 pytest test file 或 test node](developer/testing.md#focused-test) |
| Backend | [Backend 測試集](developer/testing.md#domain-test) |
| 桌面 UI | [UI 測試集](developer/testing.md#domain-test) |
| Assistant 或 tool call | [先跑 LLM suite，再選擇是否需要真模型或 GUI](developer/testing.md#tool-call-tests) |
| 文件網站 | [文件 portal build](developer/testing.md#docs-test) |
| 候選版本 | [執行完整 handoff manifest](developer/testing.md#handoff) |

完整命令、適用時機，以及每項結果可以證明到什麼程度，見[測試與驗證](developer/testing.md)。

## 找到權威答案

| 問題 | 權威來源 |
| --- | --- |
| 產品基線目前有哪些事實？ | [目前狀態](current.md) |
| 現在優先處理什麼？ | [Now](planning/now.md) |
| 現行系統如何實作？ | [目前架構](architecture/README.md) |
| 已核准的目標邊界是什麼？ | [目標架構](target/README.md) |
| 哪些證據足以支持一項宣稱？ | [驗證契約](validation/README.md) |
| 哪些長期決策仍然有效？ | [決策紀錄](decisions/README.md) |

這些來源回答不同問題。目標文件不能證明功能已經存在；歷史 artifact 或通過的測試，也不能
取代目前 source、對應 exact source 的證據，或必要的人工作業驗收。

## 產品邊界

XBrainLab 是本機 EEG 桌面產品。GUI、Assistant 與開發 scripts 共用
`ApplicationService / Command API` command spine。目前交付的是 source／GUI 基線，不是已簽章
安裝程式，也不構成科學認證。

歷史實作細節仍可透過 Git history 與 [records 索引](records/README.md)查閱，但不參與目前的
active dispatch。
