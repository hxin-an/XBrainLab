# XBrainLab 驗證策略

最後更新：`2026-05-09`

這頁說明 evidence 能證明什麼，也說明不能證明什麼。

## 原則

不要把一種 evidence 放大成所有 claim。

| Evidence | 能支撐 | 不能支撐 |
| --- | --- | --- |
| CI green | branch 基本可 review，跨平台測試目前通過。 | product complete、human desktop acceptance。 |
| `mkdocs build --strict` | 文件站可建。 | 文件內容一定正確。 |
| architecture guard | 沒有已知 forbidden path regression。 | 所有 runtime flow 都已人工驗收。 |
| backend focused tests | command / state / result contract。 | UI 使用者體驗完整。 |
| automated UI walkthrough | 可觀察 UI baseline、截圖、按鈕狀態。 | 人手 Windows acceptance、DPI / dual-monitor、長時間 local model session。 |
| tool-call eval | tool selection / parameter / state transition 的 benchmark slice。 | EEG training quality、UI completion、產品完成。 |
| MCP walkthrough | adapter baseline、tools/list、tools/call、HTTP / stdio path。 | full client certification、remote production security。 |
| launcher smoke | launcher / startup baseline。 | signed installer、release approval。 |

## MVP Gate

| Phase | 需要的最低 evidence |
| --- | --- |
| 1A Backend Cleanup | architecture guard、focused command tests、UI refresh tests。 |
| 1B Data Interpretation | scan / preview / validate / apply tests，加 representative format artifact。 |
| 1C Tool-Call Baseline | agent tool tests、MCP adapter tests、blocked reason / structured result checks。 |
| 1D Desktop Acceptance | human Windows click-through notes，加 automated walkthrough screenshot evidence。 |

## Artifact 解讀

`artifacts/` 是機器產物和 evidence，不是 current truth。

current truth 以這些文件為準：

- [current.md](../current.md)
- [planning/roadmap.md](../planning/roadmap.md)
- [architecture/README.md](../architecture/README.md)
- [validation/README.md](README.md)

## 常用 docs gate

```bash
poetry run mkdocs build --strict
git diff --check
```

如果改 CSS / layout，還要留下 built site screenshot 或可視覺審核 artifact。
