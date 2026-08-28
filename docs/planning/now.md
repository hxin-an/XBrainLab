# XBrainLab Now

最後更新：`2026-08-29`

## 目前焦點

`main` 基線為 `0abb8b56`；Import correctness v2 已以 PR #70 合併，exact accepted
head 為 `4cdc73a2959a1cdc9db9a193cecd49a0249662f3`。目前唯一 active product slice 是
**Assistant English prompt/context baseline v4**，branch 為 `fix/assistant-prompt-context-v4`。

目前 exact 3B evidence 顯示：production clarification prompt 的 system message 為 `11,197`
characters / `2,418` Granite tokens，LocalBackend 處理與 chat template 後為 `2,708`
tokens。`tool_input_clarification` 要求模型使用 receipt，但後續 boundary message 又說只
回答 separate latest request；receipt question 同時也在 conversation history 重複。五個
missing-parameter raw generations 全部自行發明預設值，原本 `5/5` 是 Host guard 的
safe product outcome，不是 raw-model accuracy。

## Outcome

- 用真正送入 pinned Granite 4.0 Micro 3B 的 final rendered prompt 與 raw response 作為主要
  打磨依據，不只看 aggregate score。
- Active Assistant prompt、cases、gate 與文件只支援英文；既有中文 intent／verifier
  保留為未承諾相容基礎。
- Raw model decision、Host safety 與 product outcome 分開報告；Host rescue 不回填
  model-quality claim。
- 產出可人工閱讀的 Markdown prompt dossier，並在內部收斂後只交付一個
  usable English baseline 給使用者手測。

## Scope / non-goals / authority

- 允許修改 prompt wording/order/deduplication、bounded context projection、production-path
  evaluator、English cases、developer prompt exporter 與 canonical Assistant/validation docs。
- 固定 `ibm-granite/granite-4.0-micro@56111ae135df9c53a78c99028e7bc24035a9e979`；
  不換模型、不降低檢查來製造 green result。
- ApplicationService/capability/publication 仍擁有 readiness；PromptToolPublication 仍擁有
  model-facing membership；PendingInteraction/ToolAttemptCoordinator 仍擁有 receipt admission 與
  verification。不新增 owner、semantic Host router、automatic continuation 或第二個權限來源。
- 不改 18-tool membership、tool names、side effects、confirmation、GUI handoff、UI、
  `settings.json` 或中文 intent/verifier production code。UI 確認狀態：**not applicable**。
- 不預先授權將 receipt 轉成自然 chat roles；下列 bounded 方案失敗時停止並提出
  evidence，不自動擴張 target architecture。

## Repair steps and commit checkpoints

1. `test: expose exact assistant prompt inputs`
   - 新增只使用 synthetic cases 的 Markdown exporter。
   - 量測 `ContextAssembler.get_messages` → `LocalBackend._process_messages_for_template` →
     pinned tokenizer chat template 的 exact final prompt。
   - 讓 first-turn precision/effect evidence 不再略過 production state/context path。
2. `fix: remove continuation prompt contradiction`
   - 修正 boundary 不再要求忽略解讀 latest reply 所需的 host-issued receipt context。
3. `fix: simplify assistant continuation context`
   - receipt 已含相同 question 時不再投影 duplicate assistant history。
   - 保留 original request、question、missing fields 和 verified values 的自然語意；不重複
     v3 已證明退步的過度壓縮方案。
4. `refactor: consolidate assistant decision policy`
   - 合併 prerequisite/substitute、`respond_to_user`、missing/multi-action、completion claim 與
     envelope 的重複規則；保留一套 decision order 與一個簡短 final reminder。
5. `test: establish English assistant baseline`
   - Active cases 改為英文，保留原有 tool/failure/trajectory 覆蓋。
   - Report 分開 raw model、Host safety 與 product outcome，並同步 target/validation/developer docs。

每個保留 commit 都需 before/after final-prompt dossier 與 raw response evidence；失敗實驗不留在
final tree，也不將舊 v3 branch 或其 UI delta 整支移植。

## Focused validation and prompt review

- 每個設計 family 最多兩個 wording variants：boundary、context dedup/order、system-policy
  consolidation，最多六輪 focused probes。
- 主 agent 必須親自閱讀 final rendered prompt，確認零 contradiction、零 duplicate question、
  零 invented-default 暗示、零 authority 混淆，並檢查 latest request/continuation 是否容易找到。
- Dossier 至少覆蓋：complete direct action、missing 後一次補齊、partial bandpass、
  notch `50 Hz`、resample/reference/normalize、zero-parameter GUI action、switch panel、
  ambiguous、multi-action、out-of-stage、cancel/topic switch/stale receipt 和 informational response。
- Model-quality 只看 raw decision；Host safety 另驗 hallucinated values、cancel、stale receipt、
  different tool、partial reply 與 multi-action 全部零 unsafe execution。
- Unit/integration 先驗 role sequence、production evaluator path、boundary、dedup、artifact exact rendering
  與 three-layer scoring；通過 focused probes 的版本才跑 pinned real-model suite。
- 最多三次 full model runs：English pre-change baseline、first candidate、final refinement。縮短但降低
  正確率的版本一律捨棄。

## Stop condition and handoff

Usable English baseline 只在以下條件同時成立時交付手測：

- 五個 direct preprocessing tools 的 complete、missing 與 one-reply continuation 全部由 raw
  model 做對；partial bandpass 可分兩輪補值而不重問已驗證值。
- Cancel、unrelated/topic switch、stale receipt、ambiguous、negated、multi-action、general 與
  out-of-stage 的 product outcome 皆無 unsafe execution。
- 36 positive tool coverage 不退步。其他真實 scorer failure 只能是非關鍵回覆措詞，
  不得是 tool selection、parameter、continuation 或 safety error，且最多三項並完整揭露。
- Independent reviewer 對 integrated exact commit 沒有 blocking finding；applicable CI/gates 對同一
  clean/explained exact SHA 全部 completed/success。

若六輪 focused prompt/context 實驗後仍有 critical journey failure，就停在 capability-boundary
checkpoint：提供 final prompts、raw outputs、Host outcomes 與失敗原因，不換模型、不降 gate、
不冒稱可手測。只有使用者對同一 source 手測通過並明確同意 merge 後才合併。

## Collaboration and cleanup

- Prompt/context worker 與 evidence/exporter worker 可使用分離 scratch worktree；只將通過主
  agent review 的 coherent commits 依序整合到 v4 branch。
- 主 agent 擁有 scope、plan、exact SHA、prompt 肉眼審查、model runs、PR/CI 與手測交付。
  Independent reviewer 不由實作 worker 自己擔任。
- 若 production 淨增超過 300 LOC、超過 8 個 production files 或 owner 增加，先做 complexity
  review 與拆分；本 slice 不建立新 control plane。
- v4 PR merged 或 abandoned 後才清理對應 worktree/branch；不碰使用者 root `settings.json`。
