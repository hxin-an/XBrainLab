# 開發者指南

這份指南提供從新 checkout 到完成 XBrainLab 變更審查的最短安全路徑。它不取代目前狀態、
架構或驗證等 canonical authority。

## 第一次貢獻的路徑

1. [安裝並啟動開發環境](local-setup.md)。
2. [找到負責該行為的 subsystem](repository-map.md)。
3. 閱讀該 subsystem 對應的 current 與 target 文件。
4. 在短期 task branch 上完成一個 coherent change。
5. 執行能直接觀察所改行為的 focused validation。
6. 透過 pull request 提交變更。

## 避免常見錯誤的規則

- `main` 是唯一產品基線。
- 保留 working tree 中不屬於本次任務的修改。
- 不得 stage、取代、revert 或隱藏 repository root 的 `settings.json`。
- 產品 workflow mutation 必須使用 `ApplicationService / Command API`。
- 修改使用者可見 layout、文案、互動或流程前，先取得明確核准。
- 產生的 evidence 放在 ignored `build/` 位置，不建立第二份 current truth。
- 不把 branch、測試結果或 screenshot 描述成 release。

Repository root 的 `AGENTS.md` 同時約束人工與自動化貢獻者。

## 接著閱讀

- [本機環境](local-setup.md)
- [Repository 與 owners](repository-map.md)
- [變更與驗證流程](change-workflow.md)
