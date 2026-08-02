# XBrainLab Agent Setup

最後更新：`2026-07-31`

這份文件是目前 agent 在 XBrainLab repo 裡工作的 setup 規則。它取代舊的 Prep Gate / Repair Loop setup。

## Repo 與 Worktree 核對

不要從 prompt、shell history 或舊文件假設 checkout 路徑。先在目前 shell 執行：

```bash
repo_root="$(git rev-parse --show-toplevel)"
branch="$(git branch --show-current)"
printf 'repo_root=%s\nbranch=%s\n' "$repo_root" "$branch"
git worktree list --porcelain
```

將 `repo_root` 和 `branch` 與 `docs/current.md`、`docs/planning/now.md` 的 Active Delivery
Context 逐字核對。兩者不一致時，不得在目前 checkout 執行 active goal；先停止並回報
worktree/branch mismatch。canonical context 變更時更新 canonical 文件，不把絕對路徑複製到
runbook 或 session prompt。

## 開始工作

1. 執行上面的 repo/worktree 核對，再用 `git status --short --branch` 確認 dirty ownership。
2. 讀 `AGENTS.md`、`docs/current.md`、`docs/planning/now.md`。
3. 讀 active goal `docs/agent_goals/product_quality_closure_goal.md` 和 active audit
   `docs/records/product_quality_audit_2026-07-30.md`。
4. 若工作會碰需求或理想架構，讀 `docs/target/README.md`。
5. 若工作會碰驗證、測試、dashboard，讀 `docs/validation/README.md`。
6. 若工作會碰架構，讀 `docs/architecture/README.md` 和相關架構文件。
7. 若工作可套用既有 agent 能力或流程，讀 `.agents/skills/README.md` 和
   `.agents/workflows/README.md`。

## 目前不要做的事

- 不要恢復舊 queue，或從 superseded goal / worklog / feedback record dispatch。
- 不要恢復舊 role / skill / workflow automation；新的 skills / workflows 必須對齊 `.agents/skills/` 和 `.agents/workflows/`。
- 不要把 milestone 當工作上限；清單勾完但產品不可用不算完成。
- 不要讓 UI / agent 各自維護第二套 backend workflow。
- 不要在產品主線未穩定前提前做 tool-call eval / thesis evidence。
- 不要下載超過容量邊界的大模型；單模型原則 10GB 內，總 cache 原則 20GB 內。
- 不要增加大量 planning docs。

## 驗證

所有 current handoff commands、timeout、`prlimit --core=0`、fixture profile 和 claim boundary
只定義在 `docs/validation/README.md` 的 **Handoff Command Manifest**。本 runbook 不複製命令；
focused 驗證也必須從該 manifest 選 slice，不能另寫較弱替代命令後宣稱同一 gate。

## 文件寫入

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
- 需要刪除或重塑 active product workflow。
- 需要下載超過容量邊界的模型，或下載 27B+ 模型。
- 需要危險 git 操作，例如 reset / checkout 大量檔案。
- 文件和程式碼衝突到無法用局部驗證判斷。

## Dirty Worktree 原則

這個 repo 目前有大量歷史改動。不要把不相關變更當噪音清掉。

只處理當前任務需要的文件或程式碼。若同一授權檔案在本輪檢查後出現其他 agent 的新
改動，立即停止並回報 ownership conflict，不猜測合併。
