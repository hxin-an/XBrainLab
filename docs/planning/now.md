# XBrainLab Now

最後更新：`2026-08-31`

## Current baseline

PR #87 已由使用者對 exact head
`b4fde30e25364f9ed42c25149129ca4010300629` 完成人工驗收並同意 merge，現已以 merge
commit `8329316e6f0f1ae7196b2e8865b4debbfb349e20` 進入 `main`。B5 training early
stopping、第一次設定 admission、分類式 Training Settings layout 與 full-edge scrollbar 均視為已完成；
B6 不屬於本輪。開始本 plan 前，root worktree 只剩使用者擁有的 `settings.json` 修改，已合併的 B5
worktree 已移除。

本輪是穩定版收斂前最後兩個已知 product issue。完成後停止新增 feature，只接受可重現的 release blocker、
資料正確性或 lifecycle defect。

## Roles and branch control

- **Root coordinator**：唯一修改本 plan、管理 base／worktree、檢查 scope／owner／LOC、整合 reviewer
  finding、執行 final gates、建立 PR、記錄 exact SHA／manual acceptance 與 merge。Root 不以作者自評取代
  reviewer。
- **Recipe implementer**：只修改 recipe save／reload lifecycle 及直接測試；不碰 3D UI、montage policy
  或其他 Import 設計。
- **3D time implementer**：只修改既有 Saliency 3D time controls 及直接測試／capture；不碰 backend
  saliency engine、Recipe 或模型推論。
- **Independent reviewer**：在各 lane freeze exact SHA 後審 observable contract、lifecycle、test quality
  與 scope。Reviewer 不在受審 branch 直接實作 finding。

允許 `main + recipe worktree + 3D time worktree`，兩個作者互不重疊。兩條線可並行施工，但 handoff、PR
merge 與 base reconciliation 由 root 串行；若實際觸及同一 production owner，立即停止並改為串行。

## R1 — Recipe save and reload lifecycle correctness

### Problem and evidence

使用者在 BIDS import review 勾選 `Save recipe` 後按 `Confirm and Import`，產品顯示
`Review Recipe Save Again`／`Workflow state changed while this confirmed action was pending`。Import
可能已成功，但 recipe 沒有寫出。Source trace 顯示 Apply 會啟動非阻塞 BIDS electrode-layout preparation；
該 advisory publication 可在 chained Save 的 review generation 建立後完成，讓 global publication gate
把「interpretation 未變、只有 layout publication 改變」誤判為 stale。第一個紅測必須以受控 background
montage completion 重現此 race；若不能重現，停止此子修正並回報，不以猜測放寬 gate。

另有一個已獨立重現的 reload defect：同一 ApplicationService 先 apply／save 一個 `safe` recipe，再 reload
同一 recipe 時，rescan／preview／validation 都成功，但新的 candidate 因
`has_applied_interpretation and not pending_confirmation` 被誤判為已套用，Apply 回
`Interpretation has already been applied.`。`pending_confirmation` 是語意確認狀態，不是 candidate
identity，不能繼續拿它判斷是否為新 review。

### Outcome

1. `Save recipe → Confirm and Import` 在 BIDS background electrode-layout publication 完成前後都保存
   使用者剛套用的同一 interpretation，不出現假的 workflow-state-changed；真正的 interpretation／source
   identity 改變仍 fail closed，不能靜默保存另一份資料。
2. Reload 產生的新 `safe` candidate 可經既有 replacement confirmation 再 Apply；同一 candidate 的第二次
   Apply 仍被阻止。
3. Reload replacement 仍保留 raw-edit blockers、resource admission、content digest、SourceFileBoundary、
   confirmation、transaction 與 rollback；BIDS montage 仍保持 advisory background lifecycle。

### Scope, deletion preference, and non-goals

- 重用既有 `DataInterpretationSessionState` candidate/applied identity、ApplicationService command spine、
  capability policy、workflow projection 與 async coordinator；不建立第二套 state、owner、receipt 或
  compatibility path。
- Save race 優先採 scoped interpretation identity／重新綁定既有 authority，不移除真正的 stale-state
  防護，不等待或取消 BIDS montage，也不把 recipe 與 electrode layout 綁成同一資料語意。
- Reload 使用一個 derived `has_pending_candidate`（或同等既有 identity projection）；不修改
  `pending_confirmation` 的語意、不清除已套用 state、不改 recipe JSON schema。
- 不改可見 layout／文案、Assistant tool membership／model-facing schema、Import source scope、label／event
  semantics、montage matching 或效能策略。
- 預計最多 6 個既有 production files、owner delta `0`、net production `+80 LOC` 內；若需新增 public
  command parameter／class、state machine、receipt，或淨增超標，root 必須先做 complexity／public-contract
  review，不自動擴張。

### TDD and focused validation

先建立會對目前 source 失敗的 observable tests：

1. BIDS Apply 完成後，在 Save admission 前只完成 background montage publication；applied interpretation
   identity 不變時 recipe 必須寫出，且保存的是該 exact applied candidate。
2. 在同一 decision window 真正替換／清除 applied interpretation 時，Save 必須維持 stale rejection且不寫檔。
3. `apply → save → same-service reload(safe) → confirmed apply` 成功；capability 與 workflow next step 都是
   Apply。
4. 原 candidate 重複 Apply、未確認 replacement、downstream raw-edit blockers 與 forced replacement failure
   rollback 維持原行為。

實作後重跑相同紅測、既有 recipe round-trip／missing source／remap／resource preflight／Qt async tests，再跑
canonical source-diverse Data gate。Handoff 手測至少涵蓋 BIDS Save recipe 實際產檔、fresh-session reload，
以及 same-session safe reload replacement。

## V1 — Epoch 3D visible time control

### Problem and approved UI outcome

3D Plot 已能用 slider 改變 selected epoch 的 saliency sample，但目前只顯示 `Epoch time (s):` 與無刻度
slider，看不到或不能精確輸入當前時間。使用者已於 `2026-08-31` 明確批准下列可見 UI：

```text
Epoch time    [────────●────────]  [ -0.125 s ]
```

保留既有 slider，右側增加小型 `QDoubleSpinBox`。它顯示 selected epoch 的 epoch-relative seconds，可輸入、
以箭頭調整，並回寫實際 nearest sample time；負 `tmin` 必須正確顯示。Slider 維持即時更新，spin box 使用
`keyboardTracking=False`，只在完成輸入後 render。兩者使用 sample interval 作 step，換 scene 時重設為新
engine range／initial time。

### Scope and non-goals

- 唯一 production owner 是既有 `Saliency3DPlotWidget`；預計只修改
  `XBrainLab/ui/panels/visualization/saliency_views/plot_3d_view.py`，owner delta `0`、net production
  `+60 LOC` 內。
- 重用 engine 的 epoch-relative range、nearest-sample selection 與 scene scalar-update path；用既有
  `QSignalBlocker` 防止 slider／spin 遞迴。
- 不重新跑模型、不重建 PyVista interactor／mesh、不 reset camera，不修改 backend engine、ApplicationService、
  Assistant tool、3D tab structure、色彩或其他 Visualization controls。
- 不新增 card、toolbar、獨立時間 state 或共用 control framework。

### TDD, visual evidence, and validation

先在既有 `tests/unit/ui/visualization/test_saliency_3d_time_slider.py` 建立紅測，證明 scene ready 後 numeric
control 必須可見且 range／step 正確；slider 更新 spin；spin 更新既有 scene time route並顯示 nearest
sample；single-sample epoch 鎖定；scene replacement 重設；不重建 engine／interactor。既有 800／1180px
geometry contract 更新為 label、slider、spin box 都可見、不重疊並保留邊界。

實作後重跑相同測試與直接相鄰 3D engine／widget tests。Handoff 時擴充既有 Visualization native capture，
由 root 肉眼檢查 normal／narrow、100／125／150% DPI 的 hierarchy、spacing、suffix、負值、focus 與 clipping；
offscreen 不取代 Windows native 人工驗收。

## Progression and stop condition

1. Root 先提交本 plan，再由該共同 plan commit 建立 R1／V1 worktree；兩位作者各自完成 red→green 與
   focused evidence。
2. 每條 lane freeze exact clean/explained SHA 後由非作者 reviewer 審查。Finding 只有可重現的本 scope
   contract、資料／lifecycle regression 或證據失真才能 blocker；其他列為後續，不擴大 diff。
3. Root 依 `scripts/dev/handoff_gate_spec.py` 執行 applicable gates。若一條先合併，另一條 handoff 前必須
   reconcile 最新 `main` 並重跑 source-sensitive evidence。
4. R1 與 V1 分別建立 PR；所有 non-skipped checks 必須在 exact head `completed/success`。產品行為仍需使用者
   對 exact SHA 手測通過並明確同意 merge，任何 source 變更使舊手測失效。
5. 兩個 PR 合併後移除 task／plan worktree與已合併 local branches，確認唯一 `main` 最新且只保留使用者
   `settings.json` 修改。此時本 plan 移除兩個 active slice，轉入 stable convergence：不啟動 B6 或新 feature，
   只處理可重現 release blocker。

任一 lane 若需要新 public tool contract、owner、state machine、receipt、超過 scope／LOC ceiling，或無法以
紅測重現使用者 defect，標記 checkpoint 並停止該擴張方向；另一條獨立 lane 繼續，不因單線問題全部停工。
