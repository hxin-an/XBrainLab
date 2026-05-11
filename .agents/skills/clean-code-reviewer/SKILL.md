---
name: clean-code-reviewer
description: Use when reviewing or steering XBrainLab implementation work for maintainability, responsibility boundaries, god objects, legacy/fallback creep, duplicated workflow truth, and code-health regression after features or tests pass.
---

# clean-code-reviewer

## 用途

用於檢查 XBrainLab 變更是否讓 code health 變好。

這個 skill 不取代 `code-reviewer`。`code-reviewer` 先找 bug、regression 和 missing tests；
`clean-code-reviewer` 專門判斷「功能雖然能跑，但架構是否變髒、是否更難維護」。

## 設計來源

已消化參考：

- Google Engineering Practices：code review 的核心目標是讓整體 code health 持續變好；能前進，
  但不能接受明確降低 maintainability / readability / understandability 的變更。
- Refactoring code smells：特別關注 Large Class、Long Method、Shotgun Surgery、Feature Envy、
  Duplicate Code、Speculative Generality、Message Chains。
- Readability / maintainability practice：可讀性不是 polish；不清楚的策略、命名、責任邊界和
  不一致寫法會直接增加維護成本。

在 XBrainLab 中，clean code 不是教條式把每個 function 拆很小，而是讓 workflow truth、
side effect、state lifecycle 和 product path 容易追蹤、測試、交接。

## 先讀

1. `docs/current.md`
2. `docs/target/architecture.md`
3. `docs/architecture/backend.md`
4. `docs/architecture/ui.md`
5. `docs/architecture/agent.md`
6. `.agents/runbooks/refactor-gate.md`
7. 相關 diff / touched files

## 核心判斷

一個 change 即使 tests pass，也不可接受，如果它：

- 讓 `ApplicationService`、controller、facade、UI panel 或 agent controller 承擔更多不相干責任。
- 把 temporary compatibility path 變成永久 product path。
- 新增 fallback 讓 real product runtime 默默繞過 command / policy / validation。
- 讓 UI、agent、MCP、headless 各自判斷 workflow readiness、label/event meaning 或 state truth。
- 把 legacy `load_data` / `attach_labels` / ad hoc label import 留在新使用者心智模型裡。
- 用 mock-heavy tests 掩蓋 real side effect、UI refresh、thread、state lifecycle 或 data mutation。
- 只補文件說明「之後會清」，但 code boundary 沒改善。

## XBrainLab Clean Code Gate

### Responsibility Boundary

檢查：

- `ApplicationService` 是否只做 command dispatch、capability / confirmation gate、state/result
  envelope 和 orchestration？
- Data Interpretation scan / preview / validate / apply / recipe / label carrier / metadata apply 是否
  能被明確定位到 handler / service / planner / validator？
- `BackendFacade` 是否只是 compatibility / headless wrapper，而不是新增 business logic？
- controller 是否逐步走向 UI adapter / observer bridge，而不是繼續承載新 workflow logic？
- UI component 是否只負責收集 human choice、顯示 state、發 command，而不是自己重建 backend policy？
- agent 是否只做 intent / tool selection / verification / visible response，而不是自己維護第二套 backend state？

### Legacy And Fallback Boundary

檢查：

- legacy path 是否有明確 owner、call site、tests、移除條件？
- fallback 是否只給 mock / unit-test compatibility，而不是 real product runtime？
- product UI / agent / MCP 是否以 Data Interpretation flow 為主？
- legacy path 若仍存在，是否被 command capability / taxonomy / docs 標成 compatibility，而且不出現在新使用者主流程？
- 新增 fallback 前，是否先問：為什麼不能修正主 path？

### Source Of Truth

檢查：

- capability policy 是否由 backend / ApplicationService 產生？
- UI enablement、agent tool exposure、MCP tools/list 是否讀同一套 command capability？
- State snapshot 是否從 backend truth 讀出，而不是 agent / UI 自己維護？
- Data Interpretation validation、Workflow State validation、Agent Tool-call validation 是否分層清楚？
- recipe、applied interpretation、loaded data metadata、label imports 是否保持一致？

### Shape Smells

以下不是自動失敗，但要觸發審查：

- 單檔持續變大，尤其超過約 `800-1000` 行且責任不單一。
- 單一 class 同時處理 dispatch、validation、IO、state mutation、UI/event notification、artifact/report。
- method 超過約 `40-60` 行且混合多個 abstraction level。
- 同一 workflow 變更需要同時摸很多互不相鄰檔案，顯示 shotgun surgery。
- method 大量讀寫別的 object internals，顯示 feature envy。
- 新增抽象只有一個 trivial caller，且沒有降低複雜度或隔離邊界。
- 新增 helper 只是為了藏住混亂流程，沒有讓 domain language 更清楚。

### Tests And Evidence

Clean code 不是只看檔案大小。拆分後必須保護行為：

- extracted handler / service 要有 focused unit tests。
- 至少一條 non-mocked product workflow 要持續通過。
- UI / agent / MCP 主流程若受影響，要跑對應 walkthrough 或 tool-call eval。
- tests 應驗證 state delta、CommandResult、capability / blocked reason、visible response 或 artifact，
  不只驗證 method 被呼叫。

## Review Output

輸出要先講結論：

```md
## Clean Code Verdict

- verdict: clean / acceptable with debt / not clean
- reason:

## Blocking Code-Health Issues

- file:line - issue

## Architecture Debt

- debt:
- why it matters:
- suggested direction:

## Legacy / Fallback Audit

- path:
- product or test-only:
- remove / isolate plan:

## Required Validation
```

## 打回條件

遇到以下情況，應要求 worker / goal 繼續，而不是標記完成：

- `ApplicationService` 或其他核心檔案因新增功能更膨脹，沒有拆出合理邊界。
- legacy 被重新包裝成 compatibility，但產品主流程仍依賴它。
- UI / agent / MCP 有任一入口繞過 `ApplicationService` 或 capability policy。
- fallback 讓 real runtime 在 command 失敗時默默改走 controller mutation。
- 文件宣稱架構乾淨，但 source code 仍有明顯 god object / duplicated truth。
- tests pass 但沒有 coverage 對應新邊界或 real side effect。

## 使用時機

- 大型 goal 開始前：先讀此 skill，避免只追功能清單。
- worker 回報完成後：用此 skill 做架構乾淨度驗收。
- 新增 Data Interpretation / backend command / agent tool / MCP tool 時：檢查是否放在正確邊界。
- 發現單檔持續膨脹、fallback 變多、legacy path 越掛越久時：立即使用。
