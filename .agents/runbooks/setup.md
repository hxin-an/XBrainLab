# XBrainLab Agent Setup

最後更新：`2026-05-02`

這份文件是目前 agent 在 XBrainLab repo 裡工作的 setup 規則。它取代舊的 Prep Gate / Repair Loop setup。

## Repo 位置

目前 active repo：

```text
/mnt/d/workspace_v2/projects/lab/XBrainLab
```

舊路徑 `/mnt/d/repos/XBrainLab` 只作備援 / 參考，不要在新指令中使用。

## 開始工作

1. 用 `git status --short` 看 dirty worktree。
2. 讀 `AGENTS.md`、`docs/current.md`、`docs/planning/now.md`。
3. 若工作會碰需求或理想架構，讀 `docs/target/README.md`。
4. 若工作會碰驗證、測試、dashboard，讀 `docs/validation/README.md`。
5. 若工作會碰架構，讀 `docs/architecture/README.md` 和相關架構文件。
6. 若工作可套用既有 agent 能力或流程，讀 `.agents/skills/README.md` 和 `.agents/workflows/README.md`。

## 目前不要做的事

- 不要恢復舊 `AQ-*` queue。
- 不要恢復舊 role / skill / workflow automation；新的 skills / workflows 必須對齊 `.agents/skills/` 和 `.agents/workflows/`。
- 不要把 milestone 當工作上限；清單勾完但產品不可用不算完成。
- 不要讓 UI / agent 各自維護第二套 backend workflow。
- 不要在產品主線未穩定前提前做 tool-call eval / thesis evidence。
- 不要下載超過容量邊界的大模型；單模型原則 10GB 內，總 cache 原則 20GB 內。
- 不要增加大量 planning docs。

## 驗證指令

fast quality dashboard：

```bash
poetry run python scripts/dev/update_quality_dashboard.py
```

文件站點：

```bash
poetry run mkdocs build --strict
```

real-data IO：

```bash
poetry run pytest --capture=sys tests/integration/io/test_io_integration.py -q
```

代表性 pipeline smoke：

```bash
poetry run pytest --capture=sys \
  tests/integration/pipeline/test_full_pipeline.py::TestFullPipeline::test_train_and_evaluate_metrics \
  tests/integration/pipeline/test_study_training_e2e.py::TestStudyTrainCycle::test_full_cycle_eegnet \
  -q
```

UI 測試如需 unattended headless，優先使用 repo 內 wrapper：

```bash
scripts/dev/run_ui_pytest.sh tests/unit/ui -q
```

## 文件寫入

- 工作流水帳：`docs/records/worklog.md`
- 重要工程紀錄：`docs/records/implementation_log.md`
- 現況摘要：`docs/current.md`
- 短期工作：`docs/planning/now.md`
- 長期路線：`docs/planning/roadmap.md`
- 決策：`docs/decisions/README.md`
- 驗證邊界：`docs/validation/README.md`
- agent 操作規則：`.agents/stack.md` 或 `.agents/runbooks/*.md`
- agent reusable skills：`.agents/skills/*/SKILL.md`
- agent multi-step workflows：`.agents/workflows/*.md`

更新文件時，優先修 existing file。只有在真的有新邊界需要獨立承載時才新增文件。

## 停止條件

遇到以下情況先停下來問使用者：

- 需要改產品方向或論文 claim。
- 需要大幅改 UI layout。
- 需要刪除或重塑既有 workflow。
- 需要下載超過容量邊界的模型，或下載 27B+ 模型。
- 需要危險 git 操作，例如 reset / checkout 大量檔案。
- 文件和程式碼衝突到無法用局部驗證判斷。

## Dirty Worktree 原則

這個 repo 目前有大量歷史改動。不要把不相關變更當噪音清掉。

只處理當前任務需要的文件或程式碼；若碰到同檔案內別人的改動，保留並順著它工作。
