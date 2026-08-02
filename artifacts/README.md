# XBrainLab Artifacts

最後更新：`2026-08-01`

`artifacts/` 保存可重建的測試、walkthrough 與 UI review 產物。它們是 checkpoint evidence，
不是 current truth，也不能單靠資料夾名稱推論為目前 release candidate。

目前狀態請讀 `docs/current.md`；完整驗證契約請讀 `docs/validation/README.md`。

## Evidence 層級

| 位置 | 用途 | 證據邊界 |
| --- | --- | --- |
| `build/handoff-evidence/<full-SHA>/` | clean pushed commit 的完整 handoff dossier；由 canonical runner 產生且不追蹤。 | 唯一可支撐 automated handoff-candidate 的 artifact root；仍不取代 Windows 人工驗收。 |
| `build/dev-artifacts/<family>/` | standalone capture、除錯與本地 UI review；不追蹤。 | 只能支撐開發期觀察，不能直接升格為 final dossier。 |
| `artifacts/quality/` | 本機 dashboard 與開發期摘要。 | 只能代表 dashboard 實際執行的 checks。 |
| `artifacts/ui/<family>/` | 人工檢視用的 UI checkpoint。 | 只有 manifest 記錄的畫面、viewport、source identity 與狀態；沒有 exact identity 時一律視為 historical checkpoint。 |
| `artifacts/validation/<family>/` | format、runtime 或 workflow 的開發期驗證輸出。 | 不得升格為 clean-SHA dossier，也不得外推成 scientific accuracy。 |
| `tests/baselines/ui/` | 自動化視覺 regression baseline。 | 用來偵測差異，不代表產品美觀或真人驗收。 |

目前尚未產生通過的 clean-SHA handoff dossier。任何名稱包含 `current`、`final`、
`release-candidate` 或 `passed` 的舊檔，都必須先核對 manifest 的 commit、dirty state、generator
與 limitations；名稱本身不構成證據。

## 保留的 checkpoint 入口

| Family | 用途 | 不能代表 |
| --- | --- | --- |
| `ui/data-import-wizard-steps/` | Data Import wizard 與 Match Labels 的可見 checkpoint。 | final UX、任意 EEG 格式支援或 Windows acceptance。 |
| `data_interpretation/` | format capability 與 event/label interpretation evidence。 | full BIDS validator、任意 sidecar labels 或 class semantics。 |
| `agent_evals/` | agent/tool-call benchmark 開發輸出。 | UI usability、EEG model accuracy 或 thesis conclusion。 |
| `launcher/` | launcher/startup checkpoint。 | signed installer 或 release approval。 |
| `mcp/` | 歷史或明確 opt-in 的 MCP evidence。 | active product roadmap 或 handoff prerequisite。 |

## 產物規則

- generated artifact 不手改成 PASS；修 source 或 generator 後重跑。
- final handoff 只執行 `docs/validation/README.md` 指定的 canonical runner，不手動拼接較弱 gate。
- clean-SHA evidence 必須包含 branch、完整 commit、dirty state、generator、environment、claims、
  limitations 與 artifact hashes。
- UI evidence 必須記錄 viewport / scale，並由主 agent 逐張檢查 text fit、overlap、scroll、
  primary action、dialog geometry 與 responsive behavior。
- 不同副檔名不等於不同資料集；format coverage 不取代 dataset-source diversity。
- artifact 與 canonical docs 衝突時，以目前 source/runtime 重新驗證，不沿用舊截圖結論。
- 大型、可重建或暫時產物放 D 槽或 ignored `build/`，不放 WSL root filesystem。

## 清理規則

可以從 current tree 移除並留在 Git history：

- byte-identical duplicate screenshots；
- `debug`、`tmp`、`review-runs` 或失敗重跑的中間資料夾；
- 沒有 source identity、已被較完整 walkthrough 取代的 `current` / `final` family；
- canonical docs 沒有引用且 generator 可重建的 dated checkpoint；
- 僅是 dashboard 複本、又與 `tests/baselines/ui/` 完全相同的 PNG。

清理時禁止使用 broad `git clean`。先用 `git ls-files`、文件引用與 manifest 確認 ownership，
再逐一刪除明確可重建的 family。Repo root `settings.json` 不屬於 artifact，永遠不得 stage、
commit、revert 或覆寫。

## 新 artifact 最低欄位

```text
status:
generator:
branch:
commit:
dirty:
environment:
supports:
does_not_support:
next_human_or_runtime_gate:
```
