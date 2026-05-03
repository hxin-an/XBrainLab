# Backend Product Goal

最後更新：`2026-05-03`

這份 goal 給長時間 Codex runner 使用。它不是 checklist 型小任務，而是工程級交付目標。

## Runner 定位

你是 XBrainLab 的 senior backend / product engineer。你的任務不是做一小段就回報，
而是把目前明確已知的 backend / UI / agent integration 缺口推進到可交付狀態。

Milestone 是最低門檻，不是工作上限。若你草草達成文字 checklist，但仍有明顯
架構旁路、產品流程不通、測試用 mock 假裝成功、或文件與現況不一致，工作沒有完成。

## 必读

先讀：

1. `AGENTS.md`
2. `.agents/README.md`
3. `.agents/runbooks/autopilot.md`
4. `docs/current.md`
5. `docs/architecture/backend.md`
6. `docs/architecture/ui.md`
7. `docs/architecture/agent.md`
8. `docs/planning/now.md`
9. `docs/validation/README.md`

以 runtime evidence 和 source code 為準；文件衝突時先修 code truth，再修文件。

## 硬性邊界

- 不 push。
- 不碰 `.vscode/settings.json`。
- 不碰 root `settings.json`。
- 不把 `/mnt/d/repos/XBrainLab` 當 active repo。
- 不下載中國公司或中國來源模型。
- 不下載大型模型；local LLM 相關工作要先做 cache / VRAM / disk preflight。
- 不把 deterministic tool-call eval 當 local LLM 真實能力證明。
- 不把 patched / mocked UI walkthrough 當真產品 E2E。
- 若需要長時間測試，先選最小可行 real-data slice，不要把 WSL 撐爆。

## 產品目標

把 XBrainLab 推到這個方向：

```text
PyQt UI actions
  -> UI application adapter
  -> ApplicationService.execute(command)
  -> typed CommandResult / state snapshot / capability policy
  -> UI refresh from the same state truth

Agent tools
  -> ContextAssembler reads capability policy
  -> tool execution guard reads same capability policy
  -> ApplicationService command where possible
  -> visible transcript shows user language only
  -> structured payload remains in diagnostics/history
```

理想上，UI 和 agent 不應各自判斷「現在能不能做某件事」。同一個 workflow 的 readiness、
blocked reason、success/failure、state refresh，都應該來自 `ApplicationService` contract。

## 必做 Milestone

### 1. Backend Workflow Contract v2

完成條件：

- 盤點所有 real `Study` mutating paths。
- 已有 service command 的 real product mutation，不可再直接由 UI/agent 繞 controller 改 state。
- 例外只能是：
  - mock/unit-test compatibility fallback
  - read-only UI population
  - human-in-the-loop UI request before confirmed command
- `evaluate`、`visualize`、`saliency`、`reset`、`new_session`、`clear_*` 要有清楚 typed result。
- destructive commands 要有 confirmation boundary 和 product walkthrough。
- `BackendFacade` 只能是 compatibility/headless wrapper，不新增 business logic。

### 2. Evidence-Ready Data / Training Pipeline

完成條件：

- Dataset split command 要保存可審計 split protocol：seed、protocol、ratios、unit、expected train/val/test policy。
- split audit blocking issue 必須 fail command 並 rollback，不可留下半成功狀態。
- Empty validation/test 不可默默進 formal pipeline evidence；若允許 exploratory mode，要明確標記。
- Training / evaluation 不能在 formal pipeline evidence path 默默 fallback 到 train loader 當 test。
- 每次 real training/evaluation smoke 要能產出 JSON/Markdown evidence。
- 注意：EEG training/evaluation accuracy 不是目前 thesis 主評分。這一段只是在確保產品資料流程
  可靠，讓後續 tool-call eval 有可信 workflow 環境。

### 3. Real UI Product E2E

完成條件：

- 新增或改造一條不靠 patched training 的 UI acceptance：
  import/load fixture -> preprocess -> epoch -> split -> configure model/training -> start real training
  -> wait completion -> evaluation state has real record -> visualization/saliency query returns typed result.
- 若完整 real UI test 太慢，建立 resource-safe profile，並清楚標出：
  - fast synthetic UI smoke 是什麼
  - real product E2E 是什麼
  - thesis-grade tool-call validation 是什麼
- 不可再讓 `tests/integration/ui/test_product_walkthrough.py` 的 patched training 被文件描述成完整產品 E2E。

### 4. Agent Surface Alignment

完成條件：

- Agent available tools / blocked reasons 來自 `ApplicationService` capability policy。
- Tool call 前必須重新 guard。
- mutating agent tools 不可直接包 controller；能走 service command 的 workflow 必須走
  `ApplicationService` command。
- 建立或補齊 Verification Layer contract：schema、required parameter、state precondition、
  resource existence、confirmation boundary、unsafe / destructive action、confidence threshold。
- Raw schema/backend wording 不可進 visible transcript。
- `list_files` missing directory 這類錯誤要轉成使用者語言。
- Tool output 保留 structured diagnostics。

### 5. Tool-Call Evaluation Architecture

完成條件：

- 建立可重跑 tool-call scorer / runner，輸出 JSON 和 Markdown report。
- case schema 至少保存 user command、initial state、available command summary、expected tool /
  no-call、expected parameters、expected verification result、expected state delta、actual model
  output、parsed tool call、verification result、backend result、visible response 和 score breakdown。
- engineering baseline 至少 `50` 個 cases；thesis candidate 至少 `100` 個 cases。
- 每個主要 workflow stage 至少 `10` 個 cases。
- negative / blocked / missing-parameter / recovery cases 至少佔 `30%`。
- multi-turn workflow cases 至少 `15` 個。
- local LLM primary / fallback runner 至少重跑 `3` 次；不足時只能標成 exploratory。
- 資料級支撐要覆蓋 checked-in compact fixtures、event-rich public fixture slice；external EEG dataset
  只作 pipeline support，不當 thesis 主評分。

### 6. Documentation Closure

完成條件：

- `docs/current.md` 寫目前真相。
- `docs/architecture/backend.md`、`ui.md`、`agent.md` 和 code 對齊。
- `docs/planning/now.md` 只寫短期 blocker，不膨脹成 roadmap。
- `docs/records/worklog.md` 記流水帳。
- `docs/records/implementation_log.md` 記重要工程交接。
- 不新增大型新文件，除非現有 canonical docs 放不下。

## 驗證門檻

至少跑：

```bash
git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run mkdocs build --strict
poetry run pytest --capture=sys tests/unit/backend/application tests/integration/backend -q
poetry run pytest --capture=sys tests/unit/llm/tools tests/integration/agent -q
poetry run pytest --capture=sys tests/unit/ui/chat tests/integration/ui/test_product_walkthrough.py -q
```

若新增 real UI E2E 或 pipeline evidence，必須跑對應 targeted test。若太慢或資源不足，
你要留下明確 evidence：跑了什麼、沒跑什麼、為什麼、下一個人怎麼重跑。

## Commit 制度

- 每完成一個可驗證 milestone，commit 一次。
- commit message 要描述實際成果，不要寫 vague progress。
- commit 前確認 `.vscode/settings.json` 和 root `settings.json` 沒被 staged。
- 不 push。
- 不用 destructive git command。

## Final Response 要求

最後只回報：

- commits
- changed files summary
- validation results
- remaining blockers
- 明確說哪些仍不能宣稱完成

不要用「大致完成」掩蓋 known blockers。
