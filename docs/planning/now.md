# XBrainLab Now

最後更新：`2026-05-06`

這份文件只放下一輪施工焦點。它不是歷史紀錄，也不是完整 roadmap。

目前策略：

```text
先把文件與架構整理到健康 baseline
-> 再討論下一批產品 completion work
```

## Current Focus

### 1. Documentation Reset

原因：目前 `current.md`、`roadmap.md`、`validation/README.md`、
`implementation_log.md` 都過長，資訊揭露層級不清楚，不適合人類閱讀。

要做：

- `current.md`：縮成 current truth、known blockers、claim boundary、入口 links。
- `roadmap.md`：只保留產品主線、完成條件、future directions。
- `now.md`：只保留下一輪施工焦點。
- `validation/README.md`：保留 evidence 分層、常用 gate、最新 artifact index。
- `implementation_log.md`：只留高層 milestone，不寫逐 slice 測試細節。
- `worklog.md`：保留詳細流水帳，但不再當人類主要入口。

完成標準：

- 人類可以從 `current.md -> roadmap.md -> now.md` 快速掌握狀態。
- implementation log 和 worklog 不再功能重複。
- 不新增大量新文件分散 truth。
- `poetry run mkdocs build --strict` 通過。

### 2. Architecture Health Baseline

原因：後續產品功能會依賴乾淨 command spine。若現在直接加功能，容易讓 UI、agent、MCP
再次分裂成多套 truth。

要做：

- 繼續保持 `ApplicationService` 不膨脹。
- 繼續 audit product runtime 是否 silent fallback 到 controller mutation。
- 擴大 `UI Command Refresh Coordinator + Controller Fallback Audit`。
- 明確分離 mock / legacy compatibility fallback 和 product runtime path。

完成標準：

- mutating UI command 成功後由 centralized coordinator refresh。
- `result is None` / legacy fallback branch 不成為 real `Study` product path。
- architecture compliance guard 能阻擋新增旁路。
- focused tests 覆蓋高價值 changed_state -> refresh scope。

### 3. Data Interpretation Mature Wizard

原因：Data Interpretation 是新資料入口主線，但目前仍是強化 baseline，不是 final import system。

要做：

- embedded label editor
- raw trigger selector
- MAT / CSV / TSV / BIDS label anchor review
- recipe diff / reload review UX
- XDF / LSL boundary 更清楚

完成標準：

- 使用者不用回到舊 Import Label 心智模型就能完成常見 label/event 確認。
- blocked / needs confirmation / safe apply 的差異清楚。
- recipe 可保存、重載、重看差異。

### 4. UI Product Walkthrough

原因：不能只靠 backend JSON 或 mock tests 宣稱 UI 可用。

要做：

- 持續用 screenshots 檢查 Data Interpretation、Dataset、ChatPanel、Training、Evaluation。
- 補 Windows launcher / DPI / dual-monitor / human desktop acceptance。
- 保持 automated walkthrough 和 human acceptance 的 claim boundary。

完成標準：

- automated walkthrough 有 screenshots、visible text、button state、workflow state。
- human desktop verification 未完成時，文件明確標成 remaining blocker。

### 5. Tool-Call Eval Gate Discipline

原因：full primary/fallback x3 local eval 很慢且吃 VRAM，不應日常小修都跑。

目前規則：

- Fast dev gate：deterministic changed / failed cases，repeat `1`，不跑 fallback。
- Candidate gate：primary affected families，repeat `1` 或 `2`。
- Release / thesis gate：deterministic full suite + primary x3 + fallback x3 + dashboard。

完成標準：

- 只有更新正式 benchmark claim 時才跑 full local release / thesis gate。
- full local gate 前做 disk / cache / VRAM preflight。
- local eval artifact 記錄 resource pressure。

## Not Now

以下先只放 roadmap future work，不開工：

- Expert Workflow Mode
- Workflow Recipe DSL
- Training Model Registry
- Training Model Node Visualization
- Training Model Compatibility Check

## Must Not Claim

- 不能宣稱 product complete。
- 不能宣稱 Data Interpretation final import system。
- 不能宣稱 backend target architecture fully aligned。
- 不能把 automated UI replay 當 human Windows desktop acceptance。
- 不能把 `121 / 121` 或 `122` deterministic case 擴張成整個產品完成。
