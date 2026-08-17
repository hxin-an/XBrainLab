# XBrainLab Now

最後更新：`2026-08-17`

## 目前焦點

**先修復 Assistant tool surface 的決策權威鏈，完成可跨 context compression 與多個 PR 保存的
target design lock；在 target intent 尚未逐項核准前，不修改產品 tool surface。**

使用者已停止並撤回 PR #32 的 manual acceptance。該 PR 已關閉且未合併；remote branch 保留，
只供 target surface 核准後選擇性回收通用 no-model walkthrough infrastructure。

## 問題與證據

- PR #30 將 runtime/debug inventory 排除九個 compatibility implementations 後的剩餘集合定義為
  21 個 model-facing actions；這是 current implementation projection，不是逐項核准的產品 target。
- PR #31 與已關閉的 PR #32 都以同一個 `model_tool_names()` projection 作 exact-coverage oracle，
  能抓 consumer drift，卻不能判斷 projection 本身是否符合使用者 workflow intent。
- `canonical catalog` 一詞同時被用來描述 current implementation single source 與 target product
  contract，讓後續 slice 將 current truth 誤升格成 durable product decision。
- `docs/planning/now.md` 會隨 active slice 更換；跨 PR 的產品決策若未回寫 decisions／target authority，
  便無法可靠抵抗 context compression。

## Observable outcome

- Decisions 明定 target tool 數量不固定，並保存已核准、延後與拒絕的產品方向。
- Target Agent 文件擁有唯一 intent ledger：每個 intent 的 owner、side effect、confirmation、visible
  result 與 decision status 都清楚；未核准 intent 不得進 model-facing projection。
- Current Agent architecture 只把現有集合稱為 `current model-facing projection v1`，不再暗示它是
  approved target surface。
- Guidance 明定 tool membership、名稱、confirmation 與 visible result 都是 public contract；runtime
  inventory 不能作 target oracle。
- Showcase 只宣稱覆蓋 current projection，不宣稱 final taxonomy、tool count 或 raw-model accuracy。

## 已確認的 target decisions

- Tool count 不固定，依 workflow intent、side effect、decision boundary 與 structured result 決定。
- `list_files` 不屬於未來產品 model-facing surface。
- Data Import 對模型只呈現一個高階入口；scan／preview／validate／apply 留在既有 backend／review
  lifecycle。
- Workflow state 由 host 每回合提供，不暴露 internal `query_state` 作 target model tool。
- Preprocessing 只在參數明確時套用，不以含糊的 standard bundle 代替使用者決策。
- Model selection 與 training configuration 的 target shape 延後到下一輪討論。

## Scope、ordered repair 與 non-goals

1. 更新 decisions、target Agent ledger 與 current Agent architecture，建立三層明確詞彙：runtime
   compatibility inventory、current model-facing projection、approved target surface。
2. 校正 deterministic showcase 的 claim boundary；歷史 PR／artifact 保留 provenance，不作 active
   dispatch。
3. 在 root guidance 與 agent-toolcall-designer workflow 加入 target-decision gate，不複製 target
   tool 清單。
4. 執行 guidance audit、文件 link/source audit與 MkDocs strict；以純 docs／guidance PR 合入 main。
5. 後續從更新後 main 繼續逐項討論完整 target ledger；全部高影響 intent 定案後才切 implementation
   PR，最後再建立 target-derived no-model walkthrough。

Non-goals：本 slice 不改 `XBrainLab/`、prompt、RAG、runtime registry、UI、tool schema、測試 catalog
或 `settings.json`；不立即 revert PR #30／#31，也不從 PR #32 cherry-pick production code。

## Focused validation

- Active Assistant docs 不得再把 21 稱為 approved／canonical target catalog。
- Decisions、target、architecture、planning 與 showcase claim 必須一致，且 unresolved intent 明確標示
  deferred。
- Repo guidance audit、direct documentation source/link audit、MkDocs strict與 diff check 必須通過。
- Final diff 只能包含 docs、guidance 與 developer-facing wording；不需要產品 manual acceptance。

## Stop conditions

- 若任何文件仍用 current registry membership 推導 target correctness，不得合併。
- 若修復需要新增 control plane、decision manifest、runtime state 或產品 compatibility path，停止並縮回
  canonical docs／guidance。
- 若 target ledger 尚有 deferred intent，不得建立 fixed-count target walkthrough或宣稱 Agent tool
  redesign 完成。
