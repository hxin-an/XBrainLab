# XBrainLab Now

最後更新：2026-08-17

## 目前焦點

**在 `assistant/model-facing-tool-catalog-v1` 將 local Assistant 的 model-facing tool catalog
收斂為 21 個 backend-owned workflow actions，同時保留 30 個 runtime/debug implementations，避免
prompt、RAG 與 local eval 各自維護不同的公開清單。**

使用者已於 2026-08-17 明確授權這個 catalog 與既有 UI handoff 行為的修改。本 slice 不改
`XBrainLab/ui/` layout；`set_montage` 繼續開啟既有 Montage Settings，granular preprocessing
繼續開啟既有 Preprocess UI，不在 Assistant 裡複製表單或自動套用 standard pipeline。

## 問題與證據

- Runtime registry 目前有 30 個可執行 tools，但 model-facing prompt 只以獨立 legacy dict 隱藏
  `load_data` / `attach_labels`；preprocess compatibility tools 與 `get_dataset_info` 仍可被模型看見。
- RAG example policy 與 local tool-call eval 另有自己的 compatibility filter，model-facing authority
  因而分裂，新增或退役 tool 時容易漂移。
- Dataset information 已可由 backend-owned `query_state` 回答；`get_dataset_info` 不需要繼續成為
  model-facing proposal。細粒度 bandpass / notch / resample / normalize / reference / channel selection
  仍應由既有 Preprocess UI 取得使用者設定，不能被錯誤正規化成 `apply_standard_preprocess`。
- `set_montage` 的既有 typed UI request 已能路由到 Montage Settings；本 slice 只保護該 handoff，
  不新增自動 montage mutation。
- Worktree 只有 repo-root `settings.json` 是使用者本機 runtime 修改；不得 stage、commit、revert
  或隱藏。

## Observable outcome

- `AGENT_ACTION_CONTRACTS` 同時保有完整 30-tool runtime inventory 與唯一的 21-tool model-facing
  classification；prompt、RAG 與 local eval 全部由這個 projection 取得公開 catalog。
- Model-facing exact set 為：`list_files`、`scan_source`、`preview_interpretation`、
  `validate_interpretation`、`apply_interpretation`、`save_interpretation_recipe`、
  `reload_interpretation_recipe`、`query_state`、`apply_standard_preprocess`、`reset_preprocess`、
  `epoch_data`、`configure_dataset_split`、`set_model`、`configure_training`、`start_training`、
  `stop_training`、`evaluate`、`visualize`、`saliency`、`set_montage`、`switch_panel`。
- `load_data`、`attach_labels`、`apply_bandpass_filter`、`apply_notch_filter`、`resample_data`、
  `normalize_data`、`set_reference`、`select_channels`、`get_dataset_info` 仍可供 debug/compatibility
  runtime 使用，但不出現在 model prompt、RAG examples 或 local eval catalog，也不能由模型提案執行。
- Dataset-info request 走 `query_state`；granular preprocess request 停在既有 Preprocess UI；
  Montage request 開啟既有 Montage Settings 且 Cancel 不 mutation。
- Model / training、evaluation、visualization / saliency / montage proposal 保留既有 panel affinity；
  本 slice 不建立第二套 readiness、capability 或 UI state。

## Scope、ownership 與 complexity

- Owner before / after：ApplicationService 仍擁有 capability / command truth；ToolRegistry 仍擁有
  30 個 runtime implementations；Agent action registry 只增加 immutable classification projection。
  Owner 數不變。
- Deletion / reuse first：移除 assembler、RAG、eval 對各自 compatibility allow/deny list 的依賴；
  重用既有 RequestAdmission、UI handoff 與 panel routing，不新增 workflow owner。
- 預期 production 只觸及 action contracts 與三個既有 consumers，淨增低於 100 LOC；不新增
  production module、public class、state machine、receipt或 compatibility path。
- Non-goals：不物理刪除 9 個 runtime tools、不改 UI layout / copy、不改 ApplicationService command、
  不新增 full 21 real-model smoke、不宣稱 Assistant 或產品整體 ready。

## Ordered repair

1. 建立 exact 21 projection、prompt / RAG / local eval exclusion 與 request-routing 的 focused red tests。
2. 在既有 `AgentActionContract` 加入 model-facing immutable classification，保留完整 runtime
   validation，並提供 registry projection。
3. 讓 prompt assembler、RAG example policy 與 local eval 只讀 canonical projection；模型提出
   unpublished tool 時在 execution 前 fail closed。
4. 保護 dataset-info → `query_state`、granular preprocess → existing UI、Montage → existing UI 與
   panel affinity contracts；若既有 owner 已正確表達，只補 regression，不改 production。
5. 更新 Agent architecture current truth；跑 focused / adjacent tests、Ruff、Basedpyright 與既有
   deterministic showcase 18/18。交付 exact SHA 給使用者手測，批准前不合入 main。

## Focused validation

- Exact runtime set 仍為 30，model-facing set exact 21；三個 consumers 對 9 個 unpublished tools
  都 fail closed。
- Request admission / normalization：dataset information 不需要模型即可走 `query_state`；granular
  preprocess 不 silent execute standard pipeline。
- UI handoff / presentation：Montage Settings、Cancel no-mutation，以及 model / evaluation /
  visualization / saliency panel affinity。沒有 UI source 變更，因此不新增 screenshot baseline。
- 既有 deterministic Agent showcase 必須保持 18/18；它是 deterministic proposal + real command
  boundary regression，不代表 raw Granite 21-tool selection accuracy。
- Ruff check / format-check、targeted Basedpyright 與直接相關 pytest 必須通過；日常 slice 不自動
  升級 full handoff manifest。

## Implementation checkpoint

- Branch 從 PR #29 merge commit `95e20538` 建立；root `settings.json` 仍是使用者既有本機修改，
  未被本 slice stage、revert或隱藏。
- Red baseline 精確產生 13 個 target failures；canonical projection、三個 consumers、host-owned
  dataset query、granular preprocess UI routing 與 unpublished alias rejection完成後，focused 23 passed。
- Adjacent prompt / RAG / local-eval / admission / normalizer / controller / UI-handoff / presentation
  sweep 955 passed；完整 RAG same-class 95 passed；Montage host / Cancel path的 focused UI contracts
  52 passed。
- Existing deterministic showcase維持 18/18；它沒有使用 raw Granite selection，也不補足 full
  21-tool smoke。Ruff check / format-check、targeted Basedpyright 0 errors、MkDocs strict與 git diff check
  均通過。
- Production 觸及 6 files，72 additions / 21 deletions，net +51 LOC；owner、state machine、receipt、
  module與 UI source/layout 數量都沒有增加。尚未 push、建立 PR或取得此 source 的使用者手測，
  因此目前是 scope-complete local checkpoint，不稱 handoff-ready、不合入 main。

## Stop conditions

- 若 prompt、RAG 或 eval 仍需自行維護第二份 21-tool 名單，不得交付。
- 若 9 個 unpublished tools 能由 model proposal 通過 verification / execution，或 runtime 30-tool
  debug registry被意外刪除，不得交付。
- 若 granular preprocess request 自動套用 standard pipeline、Montage 自動 mutation、或新增另一套
  UI readiness / state owner，停止並縮回既有 handoff。
- 若 production 淨增超過 300 LOC、觸及超過 8 個 production files、增加 owner / state / receipt，
  先做 complexity review，不繼續擴張。

本 slice scope-complete 後，下一個獨立 PR 才擴充 full 21 no-LLM smoke；再下一個 bounded slice 才評估
物理移除 9 個 compatibility implementations。長期目標讀 [Roadmap](roadmap.md)，evidence contract
只讀 [Validation](../validation/README.md)。
