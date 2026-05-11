# Workflow: Architecture Review

## 目的

完成架構複盤，校準 product-delivery 順序。這個 workflow 可用於重新評估方向，
但不取代 `AGENTS.md` 和 `docs/planning/now.md` 的目前 product-delivery 主線。

## 使用 Skills

- `software-design-reviewer`
- `architecture-reviewer`
- `validation-runner`
- `agent-toolcall-designer`

## 步驟

1. 讀 `docs/target/README.md`、`docs/target/architecture.md`、`docs/target/agent.md`。
2. 讀 `docs/architecture/README.md` 和相關 current architecture 文件。
3. 分別檢查 UI、backend、data pipeline、agent、validation。
4. 每個區域輸出 current、target gap、risk、suggested first slice、required validation。
5. 將結論整理到 `docs/planning/now.md` 或使用者指定文件。
6. 若形成決策，更新 `docs/decisions/README.md`。
7. 更新 worklog。

## Done

- 使用者可以根據輸出校準 product-delivery milestone 或下一個工程 slice。
- 如果任務是純 review，沒有直接開工重構；如果任務是 delivery，已把 review 結論落到實作計畫或程式碼。
- 有列出 validation floor。
