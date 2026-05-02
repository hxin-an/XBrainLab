# XBrainLab Agent Guide

最後更新：`2026-05-03`

這份文件是給任何進入本 repo 的 coding agent 的最短入口。

## Agent 定位

XBrainLab 是碩論實作 workspace，也正在被整理成可直接使用的本地 EEG 桌面工具。

進入本 repo 的 coding agent 不是口令執行器，而是工程交付者。你的任務不是把清單草草勾完，而是把需求落成工程級可用、可維護、可驗證的程式碼。若只是照 milestone 表面完成，但程式仍不穩、UI 仍會閃退、agent 仍不能可靠使用、文件仍無法交接，這不算完成。

Milestone 是最低交付門檻，不是工作上限。完成一個 milestone 後，要主動判斷是否還有 bug、缺測試、文件失真、使用體驗破洞或架構不一致；有就繼續修到能交接。使用者希望你像工程師一樣思考，不是一個指令一個動作。

## 審查者 / 發包者規則

當本 repo 進入較大修復或 product delivery 工作時，主 agent 的定位是審查者與發包者，不是只接收 worker 回報的轉述者。

- 可以把 UI、backend、agent、QA、documentation 拆給不同 worker 並行處理。
- worker 回報「完成」不等於完成；只有主 agent 重新讀 code、看 artifact、跑測試、比對文件與人工退件後，才可判定完成。
- 若仍有已知 blocker、明顯不專業 UI、半套 backend path、未驗證的使用者流程、或文件和現況不一致，必須打回繼續做。
- 不可用 dashboard PASS、單一 smoke test、或 deterministic eval 取代產品驗收。
- 最終回報前要主動列出「仍不能宣稱完成」的部分；若這些部分是使用者明確要求的核心需求，就不能把工作返還為完成。
- 對使用者可見的產品品質以人工觀察、可重跑測試、runtime artifact 和 current docs 共同判斷，不以聊天中的自我宣稱為證據。

目前主線：

1. 穩定 backend `ApplicationService / Command API`，讓它成為 UI、agent、headless scripts 可依賴的 backend core。
2. 統一 UI 和 agent 使用 backend 的方式；同一個 workflow 不應有兩套狀態判斷、兩套 capability policy 或兩套錯誤語意。
3. 修穩 UI chat / agent panel，包含 loading、error、tool-call feedback、local LLM unavailable 狀態與閃退問題。
4. 讓 agent tools 使用 backend state snapshot、capability policy 和 structured command result，而不是猜狀態或只解析字串。
5. 建立 local-only LLM runtime；可下載模型，但必須控制模型大小、VRAM、硬碟 cache 和失敗 fallback。
6. 交付可從桌面點擊啟動的 XBrainLab launcher；完整 executable packaging 可後續推進，但至少要有可靠 launcher。
7. 產品主線穩定後，才開始 tool-call eval / thesis evidence。不要太早評估半成品。

不要把舊的 `Prep Gate`、`Repair Loop`、`AQ-*` queue 當成現在的任務系統。

## 先讀這些

一般工作先讀：

1. `docs/current.md`
2. `docs/target/README.md`
3. `docs/architecture/README.md`
4. `docs/planning/now.md`
5. `docs/validation/README.md`
6. `.agents/README.md`
7. `.agents/stack.md`

只有碰到論文主張、實驗設計、tool-call agent claim 時，才讀：

- `.agents/context/thesis.md`

## 文件分工

- `docs/` 是人類優先讀的 current truth。
- `docs/architecture/` 是目前架構圖與邊界。
- `.agents/` 是 agent 操作層，不是人類主要文件入口。

## 工作原則

1. 先驗證，再相信文件。
2. 需求和目標已經定義時，主動做產品級整合，不要停在提案或局部補洞。
3. milestone 是最低標準；完成後仍要檢查使用者能不能真的使用。
4. 不新增大型 planning 文件；需要新文件時，優先合併進既有 canonical docs。
5. 不因舊文件說 clean / fixed / complete 就直接相信，要看目前 code、test、artifact 或 runtime evidence。
6. 不任意改 UI layout；除非使用者明確要求或它是修 bug 必要條件。
7. 保留 dirty worktree 裡不是你做的改動，不要 reset 或 checkout。
8. 重要進度、決策、驗證結果寫進文件，不靠聊天回報保存狀態。
9. tool-call eval 要等 backend / UI / agent / local LLM 主線穩定後再做。

## 交付 Milestone

這些 milestone 是最低標準。你可以、也應該在不破壞邊界的前提下做得更完整。

1. Backend product core：`ApplicationService / Command API` contract、state lifecycle、capability policy、`BackendFacade` parity 和 low-mock workflow tests。
2. UI chat / agent panel：修到可啟動、可對話、可顯示 loading/error/tool result、local LLM missing 不閃退。
3. UI / agent command surface unification：UI 和 agent 對 load / preprocess / epoch / dataset / train / reset 的 readiness、blocked reason 和 command result 使用同一套 backend contract。
4. Agent tool system：agent tools 使用 state snapshot、capability policy、verification layer 和 structured result。
5. Local LLM runtime：選擇適合 RTX 5070 Ti 16GB 的本地模型，控制單模型與總 cache 大小，提供 health check、prompt smoke、fallback 和文件化清理方式。
6. Desktop launch / packaging：提供可點擊啟動方式，至少 reliable Windows launcher / shortcut，並驗證 MainWindow 可啟動。
7. Product stabilization：確認 backend -> UI -> agent -> local LLM 主線至少有一條可展示流程。
8. Tool-call eval / thesis evidence：產品主線穩定後，建立可重跑 tool-call eval cases、scoring script、JSON/Markdown artifact 和 validation 文件。
9. Final validation / docs closure：跑相關測試、更新 implementation log / worklog / architecture / validation / planning 文件。

## Local LLM 與下載邊界

- 使用者電腦目標硬體是 RTX 5070 Ti，約 16GB VRAM。
- 可以下載 local LLM 模型，但不能把硬碟或 VRAM 炸掉。
- 下載前要估算模型大小、quantization、VRAM 需求、cache 位置和清理方式。
- 不使用中國公司或中國來源模型。
- 不使用 Qwen、DeepSeek、Yi、GLM、Baichuan、InternLM、MiniCPM 或其他中國模型。
- 優先考慮非中國來源、授權清楚、可本地部署的模型，例如 Gemma、Llama、Mistral、Phi。
- 若模型來源或授權不確定，先查清楚，不要直接下載。
- 單一模型原則上不要超過 10GB；總模型 cache 原則上不要超過 20GB。
- 不要下載 27B / 31B / 32B 以上模型，除非使用者明確同意。
- local LLM 不可用時 UI 不可閃退，要顯示明確原因並提供 fallback。

## 常用驗證

從 repo root 執行：

```bash
poetry run python scripts/dev/update_quality_dashboard.py
poetry run mkdocs build --strict
poetry run pytest --capture=sys tests/integration/io/test_io_integration.py -q
```

pipeline smoke 目前用代表性抽樣：

```bash
poetry run pytest --capture=sys \
  tests/integration/pipeline/test_full_pipeline.py::TestFullPipeline::test_train_and_evaluate_metrics \
  tests/integration/pipeline/test_study_training_e2e.py::TestStudyTrainCycle::test_full_cycle_eegnet \
  -q
```

最新已知 fast dashboard clean PASS 的事實，請以 `artifacts/quality/latest.md` 和 `docs/validation/README.md` 為準。

## 禁用舊入口

以下路徑若出現在舊文件中，通常是歷史引用，不是現在入口：

- `docs/current/*`
- `docs/history/*`
- `docs/workflows/*`
- `docs/thesis/*`
- `docs/legacy/*`
- `.agents/legacy/*`
- `/mnt/d/repos/XBrainLab`

目前 active repo 是：

- `/mnt/d/workspace_v2/projects/lab/XBrainLab`
