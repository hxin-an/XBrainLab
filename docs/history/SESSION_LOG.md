# XBrainLab 工作日誌

這份日誌記錄重要進展，讓修復與穩定化工作可以在不同 session 之間順利接續。

## 2026-04-19

### Phase-3/4 audit closure：fast dashboard 的最後一個 prep-style red point 是過期的 AI shell reference，不是新的 runtime regression

- 這輪是針對 `PLAN.md` 的 phase 3 / 4 做回頭 audit，而不是再往 phase 5 開新工作
- 直接 rerun 的 phase-3/4 evidence 目前都還是健康：
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/integration/ui/test_e2e_qtbot.py -q` -> `20 passed`
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/integration/ui/test_dialog_acceptance.py -q` -> `4 passed`
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_main_window_sync.py tests/unit/ui/test_panel_event_bridges.py -q` -> `19 passed`
  - `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/integration/io/test_io_integration.py -q` -> `31 passed, 13 warnings`
- 但 fast dashboard refresh 一開始並沒有回到全綠，而是卡在：
  - `UI baseline drift: ai-assistant-open.png (size (1428, 800) vs ref (1440, 800))`
- 這不是新的 startup / dialog / data regression，而是 `AQ-006` 把 AI shell 改成 local-first 之後，approved reference 還停在舊的 Gemini-default shell
- 本輪處理：
  - 將 `tests/baselines/ui/ai-assistant-open.png` 升級為目前已驗證的 local-first reference
  - `tests/baselines/ui/README.md` 補上這個 reference promotion 的原因
  - `.agents/runbooks/active-queue.md` 的 `AQ-PREP-008` 結果補上這次 baseline re-promotion
  - `/home/administrator/.local/bin/poetry run python scripts/dev/update_quality_dashboard.py` rerun 後已回到 `Overall status: PASS`
- reviewer-ready status correction：
  - `docs/current/STATUS_REPORT.md` 目前仍停在 `AQ-003`，已和 queue / triage / session log 脫節
  - 下次 reviewer sync 應至少改成：
    - `Current queue head`: no active repair item remains
    - `Queue Summary`: reflect `AQ-001` to `AQ-006` all done
    - `Main Risks To Watch`: replace stale `AQ-003` wording with current risks (`BUG-AGENT-001`, remaining 3 UI skips, slower mypy debt, and future phase-5 gating)

### 第四階段 Repair Loop queue closure：AQ-001 到 AQ-006 現在都已收口，repair queue 暫時清空

- 這輪不是只補文件，而是先重新跑完 phase-4 尾段的 focused slices 與 shared UI sweep，再把 queue/triage/log 一次對齊
- 最新驗證基線：
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_visualization_panel_coverage.py -q` -> `20 passed`
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_visualization_panel_redesign.py -q` -> `6 passed`
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/components/test_agent_manager.py tests/unit/ui/test_agent_manager_coverage.py tests/unit/ui/chat/test_chat_panel.py tests/unit/ui/dialogs/test_model_settings.py tests/unit/ui/test_ui_misc.py -q` -> `191 passed`
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui -q` -> `782 passed, 3 skipped, 1 warning`
- queue 已同步成：
  - `.agents/runbooks/active-queue.md` -> `Repair Loop current queue is complete. No active repair items remain.`
  - `AQ-005` -> `Done`
  - `AQ-006` -> `Done`
- 這代表第四階段目前定義的六個 repair items 都已有 focused evidence 與 shared UI 回歸驗證，不再停留在「只在 code 裡看起來修過」
- 尚未自動打開下一階段 queue；目前只把 phase-4 current queue truthfully 收成完成狀態

### AQ-006 closure：user-facing AI shell 不再默默把 local-first flow 洗成 Gemini remote fallback

- 這輪把 phase-4 最後一條 agent-facing repair 面正式收掉
- 最新固定的是 `BUG-AGENT-002`：
  - active local model deletion 不再默默切去 Gemini
  - `ModelSettingsDialog` 會尊重 deletion precondition failure
  - chat model menu 現在把 `Local` 維持為主路徑，Gemini 只在明確啟用時出現，而且標成 `Gemini (Remote)`
- focused validation：
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/components/test_agent_manager.py tests/unit/ui/test_agent_manager_coverage.py tests/unit/ui/chat/test_chat_panel.py tests/unit/ui/dialogs/test_model_settings.py tests/unit/ui/test_ui_misc.py -q` -> `191 passed`
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui -q` -> `782 passed, 3 skipped, 1 warning`
- triage 現在的 boundary 更清楚了：
  - `BUG-AGENT-002` fixed = user-facing silent remote fallback / remote-menu honesty
  - `BUG-AGENT-001` still in progress = local model cache 缺口與 dedicated local bootstrap validation

### AQ-005 closure：visualization selection drift 與過期 redesign-suite skip 現在都已收口

- 這輪把 visualization 的最後兩塊 phase-4 repair 面一起收掉，而不是只修單一 panel bug
- 最新固定的是 `BUG-VIZ-004`：
  - harmless refresh (`training_stopped`) 不會再把使用者從有效的 fold/run selection 洗回第一個 trainer
- 同輪也正式關掉 `BUG-ENV-001`：
  - 舊的 `tests/unit/ui/test_visualization_panel_redesign.py` class-level skip 已被完全移除
  - 該檔現在是 headless-safe、current-architecture-aligned 的 regression suite，而不是靠 skip 蓋住 stale patch/harness/API drift
- focused validation：
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_visualization_panel_coverage.py -q` -> `20 passed`
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_visualization_panel_redesign.py -q` -> `6 passed`
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui -q` -> `782 passed, 3 skipped, 1 warning`
- 重要結果：
  - shared UI skip surface 已從先前的 visualization redesign debt 縮到其他檔案中的 3 個既有 skip
  - 這代表 AQ-005 不只改善 runtime behavior，也真的把 validation surface 打開了
  - phase-4 現在不再卡在「visualization 還有一整塊被 skip 蓋住」這種文件層假完成

### AQ-004 第一批 evaluation-consistency closure：training complete refresh 不再把分析上下文洗回第一個 fold/run

- 這輪正式把 queue head 從 AQ-003 往下推到 `AQ-004 Tighten evaluation consistency`
- 最新收掉的是 `BUG-EVAL-004`：Evaluation panel 過去即使只是收到 harmless 的 `training_stopped` refresh，也會把使用者已經選好的 fold/run 重設成第一筆
- 修正前的直接 offscreen repro：
  - `before Fold 2: Plan B Average (Finished Runs)`
  - `after Fold 1: Plan A Repeat 1 (Finished)`
- 這條缺口不只是 average path，對剛完成後 label 會從 `Repeat 2` 變成 `Repeat 2 (Finished)` 的 specific run 也一樣會發生；根本原因是 `update_panel()` / `on_model_changed()` 每次都無條件回到 index `0`
- 這輪修法保持很窄：
  - `XBrainLab/ui/panels/evaluation/panel.py`
    - `update_panel()` 現在會先記住目前的 plan/run selection
    - refresh 後會先嘗試以 plan / record identity 保留選擇
    - 再以 text label 當 fallback
    - `on_model_changed()` 也同步接受 preferred run，避免在同一個 plan 內又被重設回第一筆
- 新增 focused coverage：
  - `tests/unit/ui/test_evaluation_panel_redesign.py`
    - preserve `Fold 2 / Average` across `training_stopped`
    - preserve a specific repeat even when its label changes from unfinished to finished
- focused validation：
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_evaluation_panel_redesign.py -q` -> `7 passed`
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_panel_event_bridges.py -q` -> `11 passed`
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui -q` -> `771 passed, 12 skipped, 1 warning`
  - `ruff check XBrainLab/ui/panels/evaluation/panel.py tests/unit/ui/test_evaluation_panel_redesign.py` -> `All checks passed!`
- 同輪同步：
  - `.agents/runbooks/active-queue.md`
    - `Repair Loop is active. Work AQ-005 first.`
    - `AQ-004` -> `Done`
  - `docs/current/BUG_TRIAGE.md`
    - 新增 `BUG-EVAL-004`
- reviewer-ready status wording suggestion：
  - `最新變更`: `AQ-004` 已完成；Evaluation panel 現在會在 harmless refresh 後保留仍然有效的 fold/run selection，不再每次 training complete 就跳回第一個 plan
  - `目前風險`: evaluation consistency 的第一條真 drift 已收口；剩餘高風險 UI 面改回 `AQ-005` 的 visualization runtime / validation surface
  - `立刻下一步`: 依 queue 轉到 `AQ-005 Stabilize visualization validation and runtime behavior`，先找 visualization 是否也有對稱的 selection reset 或其他 runtime drift

### AQ-003 第六批 training-state fanout closure：stale log 收掉後，AQ-003 可以正式關單

- 這輪沒有再往別的 queue item 漂，而是把 AQ-003 最後一個「看起來小、但其實還在誤導 panel state」的缺口收掉
- 最新確認的是 `BUG-TRAINING-007`：training panel 的 `Log` tab 過去只會在 `training_started` / `training_stopped` append 事件訊息，但在 `history_cleared` 或 `config_changed` 後不會同步清掉舊 log
- 修正前的直接 offscreen repro：
  - `before_clear Training started (event). | Training stopped (event).`
  - `after_history_cleared Training started (event). | Training stopped (event).`
  - `after_config_changed Training started (event). | Training stopped (event). | Training started (event). | Training stopped (event).`
- 這輪修法保持很窄：
  - `XBrainLab/ui/panels/training/panel.py`
    - `_on_history_cleared()` 現在會先清 `log_text`
    - `_on_config_changed()` 也會先清 `log_text`，避免舊 trainer / 舊 run 的 event log 殘留到新的 training state
- 這輪不只補 stale-log regression，也把先前還只停在推測的 live-refresh 面做成直接覆蓋：
  - `tests/unit/ui/training/test_training_panel.py` 新增 `training_updated` live progress / plot refresh case
  - focused assertion 現在直接驗證 history-table progress 由 `1/5` 變成 `2/5`
  - 同時驗證 plot epochs 由 `[1]` 變成 `[1, 2]`
- focused validation：
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/training/test_training_panel.py -q` -> `16 passed`
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_evaluation_panel_redesign.py -q` -> `5 passed`
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_visualization_panel_coverage.py -q` -> `19 passed`
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_panel_event_bridges.py -q` -> `11 passed`
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui -q` -> `769 passed, 12 skipped, 1 warning`
  - `ruff check XBrainLab/ui/panels/training/panel.py tests/unit/ui/training/test_training_panel.py` -> `All checks passed!`
- 同輪同步：
  - `.agents/runbooks/active-queue.md`
    - `Repair Loop is active. Work AQ-004 first.`
    - `AQ-003` -> `Done`
  - `docs/current/BUG_TRIAGE.md`
    - 新增 `BUG-TRAINING-007`
- queue closure wording：
  - `AQ-003` 現在可視為完整收口
  - result 應明確寫成：`BUG-EVAL-002/003`, `BUG-VIZ-002/003`, `BUG-TRAINING-003/004/005/006/007` 已固定；目前沒有再重現新的 training-state synchronization drift
- reviewer-ready status wording suggestion：
  - `最新變更`: `AQ-003` 已完成；最後一批 closure 收掉的是 `BUG-TRAINING-007`，training panel 的 stale event log 不會再在 `history_cleared` / `config_changed` 後殘留，並且 `training_updated` 的 live progress / plot refresh 現在有直接 focused coverage
  - `目前風險`: training-state synchronization 這條線目前沒有再重現新的 drift；剩餘已知 UI 風險改回 `BUG-ENV-001` 的 visualization redesign stale coverage，以及下一個 queue head `AQ-004` 的 evaluation-consistency 面
  - `立刻下一步`: 依 queue 轉到 `AQ-004 Tighten evaluation consistency`，先找 training-complete 後 cross-screen state alignment 的最小 drift

### AQ-003 第五批 training-state fanout closure：training_updated 下的 auto-follow 與 manual pin 現在分清楚了

- 這輪繼續留在 AQ-003，直接往 `training_updated` 的 selection semantics 深挖
- 最新收掉的是 `BUG-TRAINING-006`：training panel 過去沒有一致區分 auto-managed plotting selection 和 user-pinned selection
- 這條缺口在 repeat 轉換時最明顯：
  - 如果太保守，panel 會一直卡在舊 selected record，錯過新的 active run
  - 如果太積極，則會把使用者刻意選來看的舊 run 覆蓋掉
- 這輪修法仍然保持很窄：
  - `XBrainLab/ui/panels/training/panel.py`
    - 新增 `_selection_pinned_by_user`
    - `on_history_selection_changed()` 現在會把手動選擇標成 pinned
    - `_select_preferred_plot_record()` 現在會區分 auto-managed 與 pinned selection
    - `training_started` 仍可透過 `force_active=True` 強制切到新 active run
    - `history/config` 清理路徑會把 pinned state 一起重置
- 直接 symptom repro：
  - auto-follow：`auto_before True [1, 2, 3]` / `auto_after True [1]`
  - manual pin：`manual_after True True`
- focused validation：
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/training/test_training_panel.py -q` -> `13 passed`
  - `ruff check XBrainLab/ui/panels/training/panel.py tests/unit/ui/training/test_training_panel.py` -> `All checks passed!`
- shared UI regression sweep：
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui -q` -> `766 passed, 12 skipped, 1 warning`
- triage sync：
  - `BUG-TRAINING-006` = training panel now auto-follows new active runs during `training_updated`, while preserving user-pinned historical selections
- reviewer-ready queue/status wording suggestion：
  - `AQ-003` should now reflect that ongoing-run selection policy itself is materially stronger, not just event bridges
  - exact suggested wording:
    - `Current focus: training-state fanout hardening now covers immediate active-run selection, trainer-invalidating clears, stale-selection replacement, and explicit auto-follow vs manual-pin behavior during training updates`
    - `Evidence: /mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/training/test_training_panel.py -q ; /mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_evaluation_panel_redesign.py -q ; /mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_visualization_panel_coverage.py -q ; /mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_panel_event_bridges.py -q ; /mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui -q`
    - `Result: BUG-TRAINING-003/004/005/006, BUG-EVAL-002/003, and BUG-VIZ-002/003 are fixed; training panel selection semantics now distinguish between active-run auto-follow and user-pinned historical inspection`
    - `Next step: probe whether any remaining AQ-003 drift still lives in live progress/log refresh itself, rather than in record-selection or invalidation semantics`

### AQ-003 第四批 training-state fanout closure：training panel 不再被舊 selected record 卡住

- 這輪繼續留在 AQ-003，同一條 training-state sync 線再往內層收了一個比較隱蔽的缺口
- 最新收掉的是 `BUG-TRAINING-005`：training panel 的 plotting selection 過去太保守，只要已經有 `current_plotting_record`，後續即使有新的 active run 或 replacement history，也不會自動切走
- 修正前可直接重現的兩個症狀：
  - 舊 record 還在選中時，`training_started` 後不會切到新的 active run
  - 舊 record 已不在新的 history 內，但 history 仍非空時，panel 也不會換掉它
- 這輪修法仍然保持很窄：
  - `XBrainLab/ui/panels/training/panel.py`
    - 新增 `_select_preferred_plot_record()`
    - `update_loop()` 現在會先根據當前 history 決定應該追哪個 record
    - `training_started` 會用 `force_active=True` 優先切到新的 active run
    - 當切換 plotting record 時會重置 `_last_epoch_count`，避免因 epoch 數碰巧相同而漏刷 plot
- 直接 symptom repro：
  - `before_switch True [1, 2, 3]`
  - `after_switch True [1]`
  - `after_replace True [1, 2]`
- focused validation：
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/training/test_training_panel.py -q` -> `11 passed`
  - `ruff check XBrainLab/ui/panels/training/panel.py tests/unit/ui/training/test_training_panel.py` -> `All checks passed!`
- shared UI regression sweep：
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui -q` -> `764 passed, 12 skipped, 1 warning`
- triage sync：
  - `BUG-TRAINING-005` = training panel now switches off stale selected records when a new active run starts or replacement history arrives
- reviewer-ready queue/status wording suggestion：
  - `AQ-003` should now reflect four concrete closure batches, with training panel selection-sync no longer lagging behind history changes
  - exact suggested wording:
    - `Current focus: training-state fanout hardening now covers immediate active-run selection, trainer-invalidating clears, and stale-selection replacement across the training/evaluation/visualization surfaces`
    - `Evidence: /mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/training/test_training_panel.py -q ; /mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_evaluation_panel_redesign.py -q ; /mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_visualization_panel_coverage.py -q ; /mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_panel_event_bridges.py -q ; /mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui -q`
    - `Result: BUG-TRAINING-003/004/005, BUG-EVAL-002/003, and BUG-VIZ-002/003 are fixed; stale selected records no longer block the training panel from following new active runs or replacement histories`
    - `Next step: probe whether any remaining AQ-003 drift still depends on training_updated polling semantics, especially for live progress text, log growth, or delayed plot refresh during an ongoing run`

### AQ-003 第三批 training-state fanout closure：training panel 自己的 active-run / stale-history sync 也收掉了

- 這輪沒有離開 AQ-003，而是把 fanout 焦點從下游 evaluation/visualization 再拉回 training 主畫面自己
- 最新收掉的是同一條 training-state sync 線上的兩個 training-panel 缺口：
  - `BUG-TRAINING-003`：`training_started` 後不會立刻顯示 active run
  - `BUG-TRAINING-004`：`config_changed` 後仍會保留 stale history / plotting state
- 修法仍然保持很窄：
  - `XBrainLab/ui/panels/training/panel.py`
    - `_on_training_started()` 現在會立刻 `update_loop()`
    - `_on_config_changed()` 現在不只重算 ready state，也會同步 `update_loop()`
    - 新增 `_clear_training_display()`，統一清理 plots、selected record、epoch counter 與 history table
    - `update_loop()` 在 controller history 變空時現在會主動走清理路徑，而不是留著舊 plotting state
- 直接 symptom repro：
  - `started_before 0 None`
  - `started_after 1 Running True`
  - `config_after 0 None -1`
- focused validation：
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/training/test_training_panel.py -q` -> `9 passed`
  - `ruff check XBrainLab/ui/panels/training/panel.py tests/unit/ui/training/test_training_panel.py` -> `All checks passed!`
- shared UI regression sweep：
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui -q` -> `762 passed, 12 skipped, 1 warning`
- triage sync：
  - `BUG-TRAINING-003` = training panel now populates the active run immediately on `training_started`
  - `BUG-TRAINING-004` = training panel now clears stale history / plotting state on trainer-invalidating `config_changed`
- reviewer-ready queue/status wording suggestion：
  - `AQ-003` should now reflect three concrete closure batches, not just downstream result panels
  - exact suggested wording:
    - `Current focus: training-state fanout hardening is underway across both the training panel and downstream result panels; history_cleared, config_changed, and training_started immediate-sync gaps are now narrowed substantially`
    - `Evidence: /mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/training/test_training_panel.py -q ; /mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_evaluation_panel_redesign.py -q ; /mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_visualization_panel_coverage.py -q ; /mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_panel_event_bridges.py -q ; /mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui -q`
    - `Result: BUG-TRAINING-003/004, BUG-EVAL-002/003, and BUG-VIZ-002/003 are fixed; active-run and trainer-invalidating event sync is now substantially stronger across the training/evaluation/visualization surfaces`
    - `Next step: probe whether any remaining AQ-003 drift still depends on training_updated polling semantics, especially where live progress or log/plot refresh still waits on a page switch or delayed tick`

### AQ-003 第二批 training-state fanout closure：config_changed 現在也會把 evaluation / visualization 的舊 plan/run 清掉

- 這輪沿著 AQ-003 同一條 training-state fanout 線再往前推一格，沒有換主題
- 最新確認的第二批 drift 不是 `training_started`，而是 `config_changed`
- 這條比較像真產品面缺口，因為 training sidebar 的 data-splitting flow 會清 trainer；但修正前 `EvaluationPanel` / `VisualizationPanel` 都沒有聽 `config_changed`
- 修正前的實際情況：
  - Evaluation：`eval_before 1 Fold 1: Plan A 2` / `eval_after 1 Fold 1: Plan A 2`
  - Visualization：`viz_before 2 Fold 1 (EEGNet) 2` / `viz_after 2 Fold 1 (EEGNet) 2`
  - 也就是說，training-side config 變更就算已讓 trainer list 變空，下游 result panels 還是會把舊 plan/run 留在畫面上
- 這輪修法仍然保持很窄：
  - `XBrainLab/ui/panels/evaluation/panel.py` 補上 `config_changed -> update_panel`
  - `XBrainLab/ui/panels/visualization/panel.py` 補上 `config_changed -> update_panel`
  - 沒有碰 controller semantics，也沒有動 layout
- 修正後的直接 symptom repro：
  - Evaluation：`eval_before 1 Fold 1: Plan A 2` / `eval_after 1 No Data Available 0`
  - Visualization：`viz_before 2 Fold 1 (EEGNet) 2` / `viz_after 1 Select a plan 0`
- focused validation：
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_evaluation_panel_redesign.py -q` -> `5 passed`
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_visualization_panel_coverage.py -q` -> `19 passed`
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_panel_event_bridges.py -q` -> `11 passed`
  - `ruff check XBrainLab/ui/panels/evaluation/panel.py XBrainLab/ui/panels/visualization/panel.py tests/unit/ui/test_evaluation_panel_redesign.py tests/unit/ui/test_visualization_panel_coverage.py tests/unit/ui/test_panel_event_bridges.py` -> `All checks passed!`
- shared UI regression sweep：
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui -q` -> `760 passed, 12 skipped, 1 warning`
- triage sync：
  - `BUG-EVAL-003` = evaluation stale selection after `config_changed`
  - `BUG-VIZ-003` = visualization stale selection after `config_changed`
- reviewer-ready queue/status wording suggestion：
  - `AQ-003` should now reflect that the first two concrete fanout batches are already closed
  - exact suggested wording:
    - `Current focus: keep downstream result surfaces honest when training-controller events invalidate or erase trainer state; the history_cleared and config_changed fanout gaps are now fixed`
    - `Evidence: /mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_evaluation_panel_redesign.py -q ; /mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_visualization_panel_coverage.py -q ; /mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_panel_event_bridges.py -q ; /mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui -q`
    - `Result: BUG-EVAL-002/003 and BUG-VIZ-002/003 are fixed; downstream evaluation/visualization selections no longer stay stale after history clears or trainer-invalidating config changes`
    - `Next step: probe whether any remaining AQ-003 drift still depends on training_started or training_updated to expose active-run progress without requiring a page switch`

### AQ-003 第一批 training-state fanout closure：history_cleared 現在會把 evaluation / visualization 的舊 plan/run 一起清掉

- 這輪正式從 `AQ-003 Stabilize training state synchronization` 起跑，而且不是只收一個單點 bug，而是把同一條 training-history fanout 線上的兩個對稱 stale-state 一起收掉
- 最新找到的第一批 drift 不是 `training_started` 或 `training_updated`，而是 `history_cleared`
- 修正前的實際情況：
  - `TrainingController.clear_history()` 會發 `history_cleared`
  - `TrainingPanel` 自己有聽這個事件
  - 但 `EvaluationPanel` / `VisualizationPanel` 都只聽 `training_stopped`
  - 結果是 clear history 之後，下游 result panels 仍會保留舊的 plan/run，看起來像還有結果存在
- 這輪修法保持很窄：
  - `XBrainLab/ui/panels/evaluation/panel.py` 補上 `history_cleared -> update_panel`
  - `XBrainLab/ui/panels/visualization/panel.py` 補上 `history_cleared -> update_panel`
  - 沒有重做 controller，也沒有改動 layout / widget 結構
- 直接 symptom repro：
  - Evaluation 修正前：`eval_before 1 Fold 1: Plan A 2` / `eval_after 1 Fold 1: Plan A 2`
  - Evaluation 修正後：`eval_before 1 Fold 1: Plan A 2` / `eval_after 1 No Data Available 0`
  - Visualization 修正前：`viz_before 2 Fold 1 (EEGNet) 2` / `viz_after 2 Select a plan 2`
  - Visualization 修正後：`viz_before 2 Fold 1 (EEGNet) 2` / `viz_after 1 Select a plan 0`
- focused validation：
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_evaluation_panel_redesign.py -q` -> `4 passed`
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_visualization_panel_coverage.py -q` -> `18 passed`
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_panel_event_bridges.py -q` -> `9 passed`
  - `ruff check XBrainLab/ui/panels/evaluation/panel.py XBrainLab/ui/panels/visualization/panel.py tests/unit/ui/test_evaluation_panel_redesign.py tests/unit/ui/test_visualization_panel_coverage.py tests/unit/ui/test_panel_event_bridges.py` -> `All checks passed!`
- shared UI regression sweep：
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui -q` -> `756 passed, 12 skipped, 1 warning`
- triage sync：
  - `BUG-EVAL-002` = evaluation stale selection after `history_cleared`
  - `BUG-VIZ-002` = visualization stale selection after `history_cleared`
- reviewer-ready queue/status wording suggestion：
  - `AQ-003` current result should no longer say only "find the first training-event fanout drift"; the first batch is now closed
  - exact suggested wording:
    - `Current focus: keep downstream result surfaces honest when training-controller events invalidate or erase training history; continue from the first history-cleared fanout closure into the remaining training-event sync gaps`
    - `Evidence: /mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_evaluation_panel_redesign.py -q ; /mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_visualization_panel_coverage.py -q ; /mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_panel_event_bridges.py -q ; /mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui -q`
    - `Result: BUG-EVAL-002 and BUG-VIZ-002 are fixed; history_cleared now clears stale evaluation/visualization plan-run state immediately instead of leaving old selections visible until manual refresh`
    - `Next step: probe the remaining AQ-003 fanout surface for training_started / training_updated / config_changed gaps, starting with any downstream view that still depends on page switches or manual refresh to reflect active training progress`

### AQ-002 第三個 downstream propagation closure：Visualization panel 現在會隨 preprocess invalidation 清掉舊的 plan/run

- 這輪沿著 AQ-002 的同一條線，把第三個對稱的 downstream result surface 也收掉了
- 最新找到的第三個真 drift 是：`VisualizationPanel` 只聽 `training_stopped`，沒聽 `preprocess_changed`
- 而且這條比 evaluation 更深一點：舊版 `refresh_combos()` 在 trainers 消失時會直接 return，所以 stale plan/run 就算手動 refresh 也不會完整清掉
- 修法仍然保持很窄：
  - `XBrainLab/ui/panels/visualization/panel.py` 新增可注入的 `preprocess_controller`
  - main-window 正常路徑下會自動 resolve parent study 的 preprocess controller
  - `VisualizationPanel` 現在會對 `preprocess_changed` 走 `update_panel()`
  - `refresh_combos()` 也會在沒有 trainers 時清空 plan/run combo，而不是保留舊 selection
- 直接 symptom repro：
  - 修正前：`initial 2 Fold 1 (EEGNet) 2` / `after_notify 2 Fold 1 (EEGNet) 2` / `after_manual_refresh 2 Select a plan 2`
  - 修正後：`initial 2 Fold 1 (EEGNet) 2` / `after_notify 1 Select a plan 0`
- focused validation：
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_visualization_panel_coverage.py -q` -> `17 passed`
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_panel_event_bridges.py -q` -> `7 passed`
  - `ruff check XBrainLab/ui/panels/visualization/panel.py tests/unit/ui/test_visualization_panel_coverage.py tests/unit/ui/test_panel_event_bridges.py` -> `All checks passed!`
- 同輪同步：
  - [active-queue.md](/mnt/d/repos/XBrainLab/.agents/runbooks/active-queue.md) 把 `AQ-002` 收成 `Done`
  - [BUG_TRIAGE.md](/mnt/d/repos/XBrainLab/docs/current/BUG_TRIAGE.md) 新增 `BUG-VIZ-001`
  - [STATUS_REPORT.md](/mnt/d/repos/XBrainLab/docs/current/STATUS_REPORT.md) 最新變更 / 目前風險 / 立刻下一步，並把下一個 head 切到 `AQ-003`

### AQ-002 第二個 downstream propagation closure：Evaluation panel 現在會隨 preprocess invalidation 清掉舊的 fold/run

- 這輪延續 AQ-002，但沒有一口氣碰 visualization；先把下一個更小的 downstream result surface 收掉
- 最新找到的第二個真 drift 是：`EvaluationPanel` 只聽 `training_stopped`，沒聽 `preprocess_changed`
- 這讓 preprocess 一旦把 trainer/dataset downstream state 清掉，evaluation panel 仍可能保留舊的 fold/run selection，直到手動 refresh
- 修法同樣保持很窄：
  - `XBrainLab/ui/panels/evaluation/panel.py` 新增可注入的 `preprocess_controller`
  - main-window 正常路徑下會自動 resolve parent study 的 preprocess controller
  - `EvaluationPanel` 現在會對 `preprocess_changed` 走 `update_panel()`
- 直接 symptom repro：
  - 修正前：`initial 1 Fold 1: Plan A` / `after_preprocess_notify 1 Fold 1: Plan A` / `after_manual_refresh 1 No Data Available`
  - 修正後：`initial 1 Fold 1: Plan A` / `after_notify 1 No Data Available 0`
- focused validation：
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_evaluation_panel_redesign.py -q` -> `3 passed`
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_panel_event_bridges.py -q` -> `6 passed`
  - `ruff check XBrainLab/ui/panels/evaluation/panel.py tests/unit/ui/test_evaluation_panel_redesign.py tests/unit/ui/test_panel_event_bridges.py` -> `All checks passed!`
- 同輪同步：
  - [active-queue.md](/mnt/d/repos/XBrainLab/.agents/runbooks/active-queue.md) `AQ-002`
  - [BUG_TRIAGE.md](/mnt/d/repos/XBrainLab/docs/current/BUG_TRIAGE.md) 新增 `BUG-EVAL-001`
  - [STATUS_REPORT.md](/mnt/d/repos/XBrainLab/docs/current/STATUS_REPORT.md) 最新變更 / 目前風險 / 立刻下一步

### AQ-002 第一個 downstream propagation closure：Training panel 現在會隨 preprocess invalidation 即時重算 ready state

- 這輪先沒有擴大到 training/evaluation 的整條狀態鏈，而是把 `AQ-002` 收成一個最小可驗證閉環
- 最新找到的第一個真 drift 是：`TrainingPanel` 只聽 `data_changed/import_finished`，沒聽 `preprocess_changed`
- 這讓 preprocess 一旦把 epoch/dataset downstream state 清掉，training sidebar 的 `Start Training` 按鈕可能還停在舊的 ready state，直到切頁或手動 refresh
- 修法保持很窄：
  - `XBrainLab/ui/panels/training/panel.py` 新增可注入的 `preprocess_controller`
  - main-window 正常路徑下會自動 resolve parent study 的 preprocess controller
  - `TrainingPanel` 現在會對 `preprocess_changed` 走 `update_panel()`
- 直接 symptom repro：
  - 修正前：`initial True Start Training` / `after_notify True Start Training`
  - 修正後：`initial True Start Training` / `after_notify False Please configure: Data Splitting`
- focused validation：
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/training/test_training_panel.py -q` -> `7 passed`
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_panel_event_bridges.py -q` -> `5 passed`
  - `ruff check XBrainLab/ui/panels/training/panel.py tests/unit/ui/training/test_training_panel.py tests/unit/ui/test_panel_event_bridges.py` -> `All checks passed!`
- 同輪同步：
  - [active-queue.md](/mnt/d/repos/XBrainLab/.agents/runbooks/active-queue.md) `AQ-002`
  - [BUG_TRIAGE.md](/mnt/d/repos/XBrainLab/docs/current/BUG_TRIAGE.md) 新增 `BUG-TRAINING-002`
  - [STATUS_REPORT.md](/mnt/d/repos/XBrainLab/docs/current/STATUS_REPORT.md) 最新變更 / 目前風險 / 立刻下一步

### AQ-PREP-009 收口，`Prep Complete` 重新成立

- 這輪先把 `AQ-PREP-009` 的 `ruff` blocker 清到綠燈，再補上最貼近的驗證切片：
  - `ruff check .` -> `PASS`
  - `basedpyright` -> `0 errors, 0 warnings, 0 notes`
  - `tests/unit/backend/load_data/test_event_loader_strict.py tests/unit/backend/load_data/test_raw_data_loader.py -q` -> `12 passed`
  - `tests/unit/ui/dataset/test_import_label.py tests/unit/llm/tools/real/test_real_tools.py -q` -> `43 passed`
  - `tests/unit/llm/core/test_config.py tests/unit/llm/agent/test_worker.py tests/unit/scripts/test_capture_ui_baseline.py -q` -> `39 passed`
- 接著在同一輪把 `BUG-ENV-003` 的 accepted workaround 正式升級成 dashboard command：
  - `scripts/dev/update_quality_dashboard.py` 的 real-data IO slice 現在預設走 `pytest --capture=sys tests/integration/io/test_io_integration.py -q`
  - `docs/current/QUALITY_DASHBOARD.md` 也同步寫明這是目前 workspace 的 accepted path
- 刷新後的 fast dashboard：
  - `python scripts/dev/update_quality_dashboard.py` -> `PASS`
  - generated at `2026-04-19 16:16:52 UTC+08:00`
- 同輪同步：
  - [active-queue.md](/mnt/d/repos/XBrainLab/.agents/runbooks/active-queue.md) phase 切回 `Repair Loop`
  - `AQ-PREP-009` -> `Done`
  - `AQ-002` -> `In progress`
  - `BUG-ENV-005` 改成已收口的 fast-gate blocker
  - `BUG-ENV-003` 改成 monitored flaky capture issue，accepted command 已從 workaround 升級成 dashboard truth
- `AQ-002` kickoff baseline:
  - `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/unit/backend/controller/test_preprocess_controller.py -q` -> `10 passed`
  - `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/unit/backend/test_facade_coverage.py -q` -> `39 passed`

### AQ-PREP-002 收口：six-workflow baseline 已重新變成 host-safe accepted evidence

- 這輪沒有再重跑會把主機拖進 local-model bootstrap 的舊 AI-shell 路徑，而是直接把 `tests/integration/ui/test_e2e_qtbot.py` 的 AI dock toggle case 收成更窄、更安全的 shell baseline
- `TestAIAssistantDock.test_toggle_ai_dock` 現在在測試內 stub `AgentManager.start_system()`，所以它驗證的是：
  - AI button checked state
  - dock visibility toggle
  - 不再在 Prep Gate baseline 裡直接初始化 local backend
- 驗證結果：
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/integration/ui/test_e2e_qtbot.py -q` -> `20 passed`
- 同輪同步：
  - [active-queue.md](/mnt/d/repos/XBrainLab/.agents/runbooks/active-queue.md) 把 `AQ-PREP-002` 改回 `Done`
  - `AQ-PREP-009` 成為目前唯一剩餘的 prep blocker
  - `BUG-AGENT-001` 改成不再把 `test_e2e_qtbot.py` 當作當前 accepted repro；Prep Gate shell baseline 與 local-startup bug 現在已分離

### Prep Gate recheck: `Repair Loop` claim revoked pending fresh prep evidence

- 這輪沒有接受 shared docs 先前已寫下去的 `Repair Loop` 敘事，而是重新逐條對照 prep-complete criteria、queue/status/triage/session log 與 fresh command evidence
- 重新確認仍然成立的 prep evidence：
  - `timeout 25s xvfb-run -a /home/administrator/.local/bin/poetry run python run.py` -> 到 `MainWindow initialized`
  - `xvfb-run -a /home/administrator/.local/bin/poetry run python scripts/dev/capture_ui_baseline.py` -> 重新生成 shell、五個 panel、`ai-assistant-open.png`
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/integration/ui/test_dialog_acceptance.py -q` -> `4 passed`
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_main_window_sync.py tests/unit/ui/test_panel_event_bridges.py -q` -> `12 passed`
  - `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/integration/io/test_io_integration.py -q` -> `31 passed, 13 warnings`
  - `/home/administrator/.local/bin/poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`
- 但這輪也確認兩條不能帶著進 Repair Loop 的 prep gap：
  - six-workflow 既有 accepted command `xvfb-run -a /home/administrator/.local/bin/poetry run pytest -s tests/integration/ui/test_e2e_qtbot.py -q` 在本輪 recheck 會走進 AI-shell local startup，記錄 `Loading local model: Qwen/Qwen2.5-7B-Instruct on cpu` / `Loading checkpoint shards`，並把 host 拖到不安全狀態，所以這條證據目前不能當作「六條 workflow 已安全 runtime-verified」
  - `/home/administrator/.local/bin/poetry run ruff check .` 這輪直接重跑是 `22 errors`，而 shared docs 自己先前已把 fast static gate 定義為 prep-exit blocker，所以 phase 不能一邊保留 blocker，一邊又宣稱 prep complete
- 同輪同步：
  - [active-queue.md](/mnt/d/repos/XBrainLab/.agents/runbooks/active-queue.md) phase 改回 `Prep Gate`
  - reopened `AQ-PREP-002`：重建 host-safe 的 six-workflow / AI-shell baseline evidence
  - reopened `AQ-PREP-009`：處理或重判仍為紅燈的 `ruff` prep-exit blocker
  - `BUG-AGENT-001` 新增這次 AI-shell workflow rerun 造成 host 不安全的證據
  - `BUG-ENV-005` 更新到這輪最新的 `ruff` direct rerun truth

### AQ-001 收口：preprocess guardrail 已補上，normalization 暫時 defer

- 這輪把 `BUG-DATASET-007` 的 ambiguity detail 再往前接到 preprocess stage，而不是直接衝進高風險 normalization
- 新增共用 `collect_runtime_diagnostics()` helper，讓 dataset controller 與 preprocess controller 能用同一套 aggregation 邏輯
- `PreprocessController.get_runtime_diagnostics()` 現在會暴露：
  - `runtime_signals`
  - `gdf_duplicate_channel_files`
  - `gdf_duplicate_channel_details`
- `BackendFacade.get_preprocess_diagnostics()` 也已接上同一份 preprocess-stage diagnostics
- channel-sensitive real preprocess tools 現在會附加 guardrail note：
  - `RealStandardPreprocessTool`
  - `RealRereferenceTool`
  - `RealChannelSelectionTool`
  - `RealSetMontageTool`
- 這讓 real GDF ambiguity 不只停在 import / dataset summary，而會在 channel selection、re-reference、standard preprocess、montage confirmation 的 agent-facing path 直接被說明
- 驗證結果：
  - `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/unit/backend/controller/test_preprocess_controller.py -q` -> `10 passed`
  - `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/unit/backend/test_facade_coverage.py -q` -> `39 passed`
  - `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/unit/llm/tools/real/test_real_tools.py -q` -> `21 passed`
  - `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/integration/pipeline/test_all_real_tools.py::TestAllRealTools::test_channel_selection_tool tests/integration/pipeline/test_all_real_tools.py::TestAllRealTools::test_set_montage_tool -q` -> `2 passed, 2 warnings`
  - `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/integration/io/test_io_integration.py -q` -> `31 passed, 13 warnings`
  - `poetry run ruff check ...` on the touched code/test files -> `All checks passed!`
- 同輪已同步：
  - [active-queue.md](/mnt/d/repos/XBrainLab/.agents/runbooks/active-queue.md) 把 `AQ-001` 改成 `Done`
  - `AQ-002` 現在成為新的 active queue head
  - `BUG-DATASET-007` 的 notes 改成「guardrail 先到位，normalization defer」

### AQ-001 再往上接一層：dataset summary 與 real dataset-info tool 現在會暴露 GDF ambiguity

- 這輪沒有去碰高風險的 duplicate-name normalization，而是把既有 `Raw` detail 再接到更高層的 dataset diagnostics
- 新增 `DatasetController.get_runtime_diagnostics()`
  - 聚合：
    - `runtime_signals`
    - `gdf_duplicate_channel_files`
    - `gdf_duplicate_channel_details`
- `BackendFacade.get_data_summary()` 現在會把這些 diagnostics 帶上去
- `RealGetDatasetInfoTool` 也開始直接把 GDF duplicate-channel ambiguity 說出來，而不是只回傳載入數量
- 同輪已把 [active-queue.md](/mnt/d/repos/XBrainLab/.agents/runbooks/active-queue.md) 的 `AQ-001` wording 同步到這個新 closure，不再留 pending queue sync
- 驗證結果：
  - `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/unit/backend/controller/test_dataset_controller.py -q` -> `18 passed`
  - `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/unit/backend/test_facade_coverage.py -q` -> `38 passed`
  - `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/unit/llm/tools/real/test_real_tools.py -q` -> `19 passed`
  - `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/integration/io/test_io_integration.py -q` -> `31 passed, 13 warnings`

### AQ-001 再收一格：把 GDF duplicate-channel detail 變成 typed Raw API

- 這輪沒有直接進入高風險的 duplicate-name normalization，而是先把現有 `gdf_duplicate_channel_names` structured detail 再收斂成 `Raw` 的 typed convenience API
- `Raw` 現在新增：
  - `has_gdf_duplicate_channel_detail()`
  - `get_gdf_duplicate_channel_detail()`
- 這讓後續 dataset / preprocess diagnostics 不需要再硬編碼 runtime-detail key，就能拿到 duplicate-channel ambiguity；比較符合 AQ-001 現階段先做 guardrail、再決定是否 normalization 的節奏
- 同步更新了 unit / integration coverage：
  - `tests/unit/backend/load_data/test_raw.py`
  - `tests/unit/backend/load_data/test_raw_data_loader.py`
  - `tests/integration/io/test_io_integration.py`
- 驗證結果：
  - `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/unit/backend/load_data/test_raw.py -q` -> `32 passed`
  - `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/unit/backend/load_data/test_raw_data_loader.py -q` -> `5 passed`
  - `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/integration/io/test_io_integration.py -q` -> `30 passed, 12 warnings`
- 同輪嘗試把 AQ-001 的新 wording 寫回 `.agents/runbooks/active-queue.md` 時，目標路徑仍回 `OSError: [Errno 30] Read-only file system`
- 依目前 executor 規則，這代表 host write failure，而不是 repo 權限錯誤；因此本輪先把 pending queue sync 明寫在 human-facing docs，等下個可寫 cycle 再回補 queue

### 控制面簡化：回到 `active-queue + STATUS_REPORT`

- 這輪把三角色機制的共享控制面做了收斂
- 原因是先前的 `reviewer-handoff.md` / `pending-sync.md` 中心化機制，在 heartbeat host write failure 下太容易和 `active-queue.md`、`STATUS_REPORT.md` 分裂，讓 executor 被 stale handoff 綁住
- 新規則：
  - `active-queue.md` 是主要 queue / phase surface
  - `STATUS_REPORT.md` 是主要人類可讀 correction / current-truth surface
  - reviewer 透過更新 queue/status 做定期校正，不再用 handoff 檔逐步遙控 executor
  - `reviewer-handoff.md`、`pending-sync.md` 只保留成過渡/診斷用途
- 同步把 repo role docs、runbooks、session prompts 都改成這個簡化版，避免文件和 heartbeat prompt 繼續分裂
- 這輪也把 human-facing phase 重新對齊到 `Repair Loop`，避免 `active-queue.md` 已進 repair loop、但 `STATUS_REPORT.md` 還停在較舊的 prep-gate 控制敘事

### `Prep Gate` 已明確切到 `Repair Loop`

- 這輪先依 queue 現況與 prep-complete criteria 做 explicit prep-exit review，確認目前列出的 prep items 都已完成，沒有新的 same-phase blocker 需要再掛回 prep item
- 隨後同步 [active-queue.md](/mnt/d/repos/XBrainLab/.agents/runbooks/active-queue.md)：
  - `Current phase` -> `Repair Loop`
  - `AQ-001 Strengthen dataset import and label import reliability` -> `In progress`
- 這讓 queue 不再停在 pseudo-prep limbo；`AQ-001` 現在正式成為新的 queue head

### AQ-001 第一個 repair-loop closure：GDF duplicate-channel ambiguity 升級成 structured runtime detail

- 這輪沒有直接做高風險 channel-name normalization，而是先把 `BUG-DATASET-007` 往更可操作的 guardrail 推一格
- `Raw` 現在除了保留 `runtime_signals`，也能保存 structured runtime details
- `load_gdf_file()` 在偵測到 MNE duplicate-name auto-rename 後，現在會把 `gdf_duplicate_channel_names` detail 寫進 `Raw`
  - 內容包含：
    - `generated_bases`
    - `generated_channels`
    - `message`
- 這讓 downstream dataset / preprocess / diagnostics work 不需要再靠 logger/stderr 或字串 parsing 才能知道 real GDF import 曾依賴 MNE auto-rename
- 驗證結果：
  - `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/unit/backend/load_data/test_raw.py -q` -> `32 passed`
  - `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/unit/backend/load_data/test_raw_data_loader.py -q` -> `5 passed`
  - `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/integration/io/test_io_integration.py -q` -> `30 passed, 12 warnings`

### Reviewer fallback：host write failure 下的暫代 handoff

- 這輪 reviewer 重新檢查後，判定目前仍屬於 `3. Prep Gate Before Stable Bug Fixing`，但 phase alignment 已是 `drifting`
- 主要原因不是 executor 跑偏，而是 queue 已把 `AQ-PREP-005`、`AQ-PREP-006`、`AQ-PREP-009`、`AQ-PREP-010` 都關閉，下一個正確動作應該是 explicit prep-exit review / queue refresh；現存 `reviewer-handoff.md` 仍停在較舊的 prep-item 指令
- 本輪 same-session write probe 結果：
  - `.agents/runbooks/reviewer-handoff.md` -> `OSError: [Errno 30] Read-only file system`
  - `.agents/runbooks/pending-sync.md` -> `OSError: [Errno 30] Read-only file system`
  - `docs/current/STATUS_REPORT.md` -> `WRITE_OK`
  - `docs/history/SESSION_LOG.md` -> `WRITE_OK`
- 因此依 reviewer fallback 規則，這輪把 pending directive 直接鏡射到 human-facing docs，並明確標記為 host environment write failure，而不是 repo 檔案權限問題
- 暫代 reviewer 指令：
  - `Current phase`: `3. Prep Gate Before Stable Bug Fixing`
  - `Primary emphasis`: `3. Prep Gate Before Stable Bug Fixing`
  - `Phase alignment`: `drifting`
  - `Status`: `reprioritize`
  - `Required action for executor`: 下一輪先做 explicit prep-exit review 和 queue refresh，而不是再做一輪泛化的 `AQ-PREP-005`。若 prep-complete criteria 已滿足，就正式切到 repair loop 並讓 `AQ-001` 成為新 queue head；若仍有未滿足條件，就新開一條具體 prep item 明確命名剩餘 blocker。
  - `Risks to watch`: pseudo-prep limbo、重開已關閉 prep item、以及在未寫下 phase / queue transition 前就滑進 repair-loop 或 redesign work

### AQ-PREP-010 也已收口，prep item list 全數關閉

- 在確認 `scripts/dev/update_quality_dashboard.py` 已經支援 `--skip-if-fresh-minutes 60`、而 `docs/current/QUALITY_DASHBOARD.md` 也已經把這條 command 寫進人類入口之後，這輪直接處理 `AQ-PREP-010` 的最後閉環
- 先用 `automation_update` 檢視並更新現有 thread heartbeat `xbrainlab-executor`
- 更新後的 automation prompt 現在明確寫著：
  - 當 `AQ-PREP-010` 是 top eligible item 時
  - 先跑 `/home/administrator/.local/bin/poetry run python scripts/dev/update_quality_dashboard.py --skip-if-fresh-minutes 60`
  - 若 saved dashboard artifact 與 direct rerun 衝突，以 direct rerun 為準
- 隨後同步 `.agents/runbooks/active-queue.md`，把 `AQ-PREP-010` 改成 `Done`
- 到這一步為止，queue 內目前列出的 prep items 都已經關閉；剩下不再是新的 prep triage item，而是顯式 phase / queue refresh 是否要切出 `Prep Gate`

### AQ-PREP-005 / AQ-PREP-006 / AQ-PREP-009 一起收口，AQ-PREP-010 成為下一個 top eligible item

- 這輪沒有停在單一 bug wording，而是把三個 prep item 一次收成完成態：
  - `AQ-PREP-005` -> `Done`
  - `AQ-PREP-006` -> `Done`
  - `AQ-PREP-009` -> `Done`
- `AQ-PREP-005` 的收口結果：
  - real GDF duplicate-name ambiguity 已穩定落在 `BUG-DATASET-007`
  - default-capture teardown 只維持 `BUG-ENV-003` 的 flaky workspace signal framing
  - unattended UI pytest blocker 維持 `BUG-ENV-004`
  - AI local startup 維持 `BUG-AGENT-001`，而且這輪又用 config probe 把剩餘 blocker 縮到「local model cache 不存在」
  - visualization 則維持單一 `BUG-ENV-001`，不另拆第二條 VTK runtime bug
- `AQ-PREP-006` 的收口依據是 repo 內的 local-only / Codex assumptions 現在都已有穩定入口：
  - `AGENTS.md`
  - `.agents/stack.md`
  - `.agents/runbooks/setup.md`
  - `.agents/runbooks/autopilot.md`
  - `.agents/runbooks/pending-sync.md`
  - `docs/index.md`
  - `docs/thesis/`
- `AQ-PREP-009` 的收口依據是直接 gate truth 已固定：
  - `/home/administrator/.local/bin/poetry run ruff check .` -> `20 errors`
  - `/home/administrator/.local/bin/poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`
  - `/home/administrator/.local/bin/poetry run mypy XBrainLab/` -> `7 errors in 5 files`
  - `/home/administrator/.local/bin/poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`
- 因為 005/006/009 都已關掉，queue 內下一個 top eligible prep item 現在變成 `AQ-PREP-010 Keep the quality dashboard refreshed automatically`

### AQ-PREP-005 / AQ-PREP-009 wording 再對齊成同一組 current truth

- 這輪先重新讀回 shared runbooks、reviewer handoff、queue、status、triage 與 session log，確認目前仍要留在 `AQ-PREP-005`
- 再把 `tests/unit/ui/test_visualization_panel_redesign.py` 與現行 visualization panel code 對照一遍，讓 `BUG-ENV-001` 的剩餘 stale surface 不再只停在籠統的 `stale API/test drift`
- 目前更具體的三個 drift cluster 已經能說清楚：
  - sidebar extraction drift：`AggregateInfoPanel` 與 `btn_montage` 都已搬到 `ControlSidebar`
  - 缺少 Qt harness：這份 unittest-style redesign file 的 no-skip 路徑沒有自己的 `QApplication`
  - legacy widget/panel API expectations：`refresh_data`、`plot_layout`、`plot_3d_head.os`、combo assumptions、以及 topomap close semantics 都與現行實作不符
- 同一輪也重新直接重跑 static gate，避免 human docs 還同時引用互相衝突的 `basedpyright` 敘述：
  - `/home/administrator/.local/bin/poetry run ruff check .` -> `20 errors`
  - `/home/administrator/.local/bin/poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`
- 這讓 `BUG-ENV-005` 的 current truth 再次收斂：
  - fast static gate 這個類別仍是 prep-exit blocker
  - 但目前 concrete red fast blocker 是 `ruff`
  - `basedpyright` 這輪是綠燈，不該再被當成目前紅燈引用
  - slower `mypy` 仍維持 monitored full-gate debt
- 同一輪直接同步：
  - `.agents/runbooks/active-queue.md`
  - `docs/current/STATUS_REPORT.md`
  - `docs/current/BUG_TRIAGE.md`

### AQ-PREP-005 queue wording 已補齊

- 這輪在宿主切回可寫後，再次重試 `.agents/runbooks/active-queue.md` 的 current-item recordkeeping
- same-session write probe 這次已通過：
  - `.agents/runbooks/active-queue.md` -> `ACTIVE_QUEUE_WRITE_OK`
- 隨後把 `AQ-PREP-005 -> visualization headless fragility and skip boundaries` 真正同步到最新 framing：
  - repo-visible boundary 仍是 redesign suite `9 skipped`
  - current boundary 是 collection/import pollution 已隔離、`TestSaliency3DEngine` 已綠燈、仍無獨立重現的 VTK runtime-ordering crash
  - bug-record decision 維持單一 `BUG-ENV-001`，不拆第二條獨立 VTK runtime bug
  - next step 改成把這個剩餘 surface 當成 stale-test repair boundary 繼續收斂
- 同一輪也把 `docs/current/STATUS_REPORT.md` 裡舊的 pending queue-sync 註記收掉，避免 human-facing docs 還停在 host write-failure fallback 狀態

### AQ-PREP-005 redesign-suite class skip 再收斂成 stale-coverage surface

- 這輪沿著 `AQ-PREP-005` 裡 `visualization headless fragility and skip boundaries` 的剩餘 next step，直接檢查 `tests/unit/ui/test_visualization_panel_redesign.py` 那條 class-level skip 背後到底是 monitored debt 還是已可落成更具體的 bug 面
- 先做 temp no-skip 對照，不修改 repo 本體：
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh /tmp/test_visualization_panel_redesign_noskip.py -q`
  - 結果：`9 failed`
  - 九個 case 都先卡在過期 patch target `XBrainLab.ui.panels.visualization.panel.AggregateInfoPanel`
- 接著在第二個 temp copy 只修正這個 patch target：
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh /tmp/test_visualization_panel_redesign_noskip_patchfix.py -q`
  - 結果：process `Aborted`
  - traceback 停在 `self.MockAggregateInfoPanel.return_value = QWidget()`，代表這份 unittest file 在 no-skip 路徑下連最基本的 Qt app harness 都還沒補上
- 最後在第三個 temp copy 同時補上：
  - 正確的 `AggregateInfoPanel` patch target
  - 最小 `QApplication` bootstrap
  - 驗證：
    - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh /tmp/test_visualization_panel_redesign_noskip_qapp.py -q`
    - 結果：`8 failed, 1 passed`
- 這個 no-skip + qapp 路徑揭露的已是更具體的 stale API/test drift，而不是先撞到獨立的 VTK/Qt segfault：
  - `XBrainLab.ui.panels.visualization.plot_3d_head.os` patch target 無效
  - `VisualizationPanel.refresh_data` 不存在
  - `VisualizationPanel.btn_montage` 不存在
  - `SaliencyTopographicMapWidget.plot_layout` 不存在
  - `plan_combo.count()` 等舊 UI 假設已不再成立
  - topomap `plt.close` 的行為預期也已過期
- 這讓 `BUG-ENV-001` 又往前縮一格：
  - collection-time pollution 已隔離
  - `TestSaliency3DEngine` engine-basics slice 已在正常 pytest path 綠燈
  - redesign suite 的 class-level skip 現在更像是在遮住 stale coverage surface，而不是在隔離一條已證實的第二條 VTK runtime bug
- 同一輪把這個 framing 同步回：
  - `docs/current/BUG_TRIAGE.md`
  - `docs/current/STATUS_REPORT.md`
- 同輪也把 bug-record decision 先收斂成：`BUG-ENV-001` 目前維持單一 bug record，不另拆第二條獨立的 VTK runtime bug；因為 no-skip 路徑仍先暴露 stale patch/harness/API drift，而不是 post-harness-corrected runtime crash
- 另外做了 same-session write probe：
  - `docs/current/STATUS_REPORT.md`、`docs/current/BUG_TRIAGE.md`、`docs/history/SESSION_LOG.md` 都可正常寫入
  - 只有 `.agents/runbooks/active-queue.md` 持續回 `OSError: [Errno 30] Read-only file system`
- 依 autopilot / executor fallback，這輪把 pending queue sync wording 明確鏡射到 human-facing docs，避免下一個可寫循環退回舊 framing：
  - repo-visible boundary：redesign suite 仍是 `9 skipped`
  - current boundary：collection/import pollution 已隔離、`TestSaliency3DEngine` 已綠燈、仍無獨立重現的 VTK runtime-ordering crash
  - next step：把剩餘 surface 當成 stale-test repair boundary 繼續收斂，而不是第二條 VTK bug

### AQ-PREP-005 stale engine skip 已退休

- 在確認 collection-time pollution 已被隔離之後，這輪直接處理剩下最明顯的過期邊界：`tests/unit/ui/test_visualization.py` 內 `TestSaliency3DEngine` 的硬編碼 `@pytest.mark.skipif(True, ...)`
- 先重新確認同一個 UI / integration 範圍裡已沒有其他 collection-time `saliency_3d_engine` 汙染源；`rg` 結果顯示 relevant mock surface 仍集中在 `tests/unit/ui/test_visualization_panel_redesign.py`
- 接著移除 `TestSaliency3DEngine` 上那層過期 skip guard，直接用現有 headless-safe pytest 路徑驗證：
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_visualization.py -q`
  - 結果：`14 passed`
- 對照確認 redesign suite 本身仍維持原有窄邊界：
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_visualization_panel_redesign.py -q`
  - 結果：`9 skipped`
- 這讓 `BUG-ENV-001` 再往前縮一格：
  - engine-basics slice 已不再依賴硬編碼 skip
  - collection-time pollution 已被隔離
  - 剩餘可見的 headless visualization risk 已收斂到 redesign suite 的 class-level skip，而不是 `TestSaliency3DEngine` 或獨立重現的 runtime-ordering fail
- 同一輪也把這個新 framing 直接同步回：
  - `.agents/runbooks/active-queue.md`
  - `docs/current/BUG_TRIAGE.md`
  - `docs/current/STATUS_REPORT.md`

### AQ-PREP-005 runtime-signal triage 再次縮小兩條邊界

- 先前 `BUG-ENV-003` 曾在完整 real-data IO slice 上重現 default-capture teardown failure
- 但本輪重新切分後，`test_io_integration.py` 的四個大群各自單跑都能在預設 capture 下通過：
  - 基本 GDF / invalid-file group -> `4 passed`
  - supported real-format load group -> `8 passed`
  - supported real-format facade group -> `8 passed`
  - public real-format load + facade group -> `10 passed`
- 接著直接重跑完整指令：
  - `/home/administrator/.local/bin/poetry run pytest tests/integration/io/test_io_integration.py -q`
  - 結果：`30 passed, 12 warnings`
- 同一條完整指令在同一 workspace 再連跑 `3` 次，也全部通過：
  - `RUN=1` -> `30 passed, 12 warnings`
  - `RUN=2` -> `30 passed, 12 warnings`
  - `RUN=3` -> `30 passed, 12 warnings`
- 這讓 `BUG-ENV-003` 的定位從「目前穩定重現的 blocker」收斂成「先前曾明確出現、但目前尚未能穩定再現的 flaky workspace signal」
- 用 repo 內的 headless-safe helper 重新收斂 visualization 風險：
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_visualization.py -q`
  - 結果：`11 passed, 3 skipped`
  - 三個 skip 全都集中在 `TestSaliency3DEngine`
  - skip reason 明確指出這是 ordering-dependent 的 VTK / Qt global state 問題，而不是整個 visualization test slice 普遍壞掉
- 這一輪沒有修功能碼；主要成果是把 `AQ-PREP-005` 的兩條剩餘 runtime signal 從「模糊風險」推進成更可行動的 triage 邊界
- 同步更新：
  - `docs/current/BUG_TRIAGE.md`
  - `docs/current/STATUS_REPORT.md`
- 補充限制：
  - `.agents/runbooks/active-queue.md` 在目前 sandbox 下是唯讀，因此這輪 evidence 先寫回 human-facing docs 與 session log

### BUG-ENV-001 skip-policy evidence 收斂

- 這輪重新檢查後，發現 `TestSaliency3DEngine` 目前不是「在 suite 裡才 skip、單跑就會過」
- 直接跑 nodeid：
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_visualization.py::TestSaliency3DEngine -q`
  - 結果：`3 skipped`
- 原因也更清楚了：該 class 現在被 `@pytest.mark.skipif(True, ...)` 無條件跳過，所以註解裡的 workaround 說明已經過期
- 但在 repo 的 Poetry 環境中跑等價 isolation snippet：
  - `/home/administrator/.local/bin/poetry run python - <<'PY' ... Saliency3DEngine ... PY`
  - 結果：`isolated-engine-check: PASS`
- 這讓 `BUG-ENV-001` 的描述更精確：
  - 目前真正的缺口不是 engine case 本身已確認壞掉
  - 而是 pytest coverage 還依賴硬編碼 skip，尚未把 VTK / Qt global-state ordering 風險收斂成可重現的最小 fail path
- 同步更新：
  - `docs/current/BUG_TRIAGE.md`
  - `docs/current/STATUS_REPORT.md`

### BUG-ENV-001 最小污染源再收斂

- 這輪把 visualization 風險從「模糊 ordering 問題」再縮到更具體的 import 污染證據
- 在乾淨的 Poetry process 內：
  - `/home/administrator/.local/bin/poetry run python - <<'PY' ... Saliency3DEngine ... PY`
  - 結果：`baseline_engine_type Saliency3DEngine`
- 但只要先 import `tests.unit.ui.test_visualization_panel_redesign`：
  - `/home/administrator/.local/bin/poetry run python - <<'PY' ... import tests.unit.ui.test_visualization_panel_redesign ... PY`
  - 結果：
    - `saliency_engine_module_type MagicMock`
    - `engine_attr_type MagicMock`
- 後續再 import engine 時也只會拿到：
  - `post_redesign_import <MagicMock ...>`
- 這代表目前更具體的污染源不是抽象的「VTK/Qt 有時候會亂掉」，而是 `test_visualization_panel_redesign.py` 在模組層對 `sys.modules` 的全域 mock 會直接改寫 backend visualization import surface
- 因此 `BUG-ENV-001` 現在應拆成兩層來看：
  - policy side：`TestSaliency3DEngine` 仍被硬編碼 skip
  - pollution side：visualization redesign test module 會污染後續 import surface
- 同步更新：
  - `docs/current/BUG_TRIAGE.md`
  - `docs/current/STATUS_REPORT.md`

### AQ-PREP-005 collection-pollution 最小隔離面已驗證

- 這輪沒有停在 triage wording，而是直接驗證 queue 裡寫出的最小 repair-facing direction
- 針對 `tests/unit/ui/test_visualization_panel_redesign.py`，將原本會在模組層發生的 `sys.modules` mock 與 UI imports 收進 class lifecycle，讓 collection 階段不再觸發 import side effect
- 驗證結果：
  - `/home/administrator/.local/bin/poetry run python - <<'PY' ... pytest.main(['--collect-only', '--capture=sys', '-q', 'tests/unit/ui/test_visualization_panel_redesign.py']) ... PY`
  - 結果：`9 tests collected`
  - `after_collect_module_type MISSING`
- 進一步對照：
  - 先 collect redesign test，再在同一 process 暫時中和 `pytest.mark.skipif` 執行 `TestSaliency3DEngine`
  - 結果現在變成：
    - `test_creates PASS`
    - `test_update_scalars_returns_none_when_no_data PASS`
    - `test_on_download_complete_error PASS`
- 另外也用現有 headless-safe harness 重跑 redesign test file 本身：
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_visualization_panel_redesign.py -q`
  - 結果：`9 skipped`
- 這讓 `BUG-ENV-001` 的邊界再前進一格：先前已確認的 collection/import pollution 現在已有最小隔離方式，而且隔離後沒有再看到獨立的 runtime-ordering fail；剩餘更明確的缺口回到過期的 `TestSaliency3DEngine` skip policy

### AQ-PREP-005 queue sync 後的 forced-engine validation 再收斂

- 先依角色校正把 `.agents/runbooks/active-queue.md` 的 `AQ-PREP-005` 當前項目同步完成
- 這輪更新的是同一個 queue item 裡的兩段 current focus：
  - `unattended UI pytest in the current /mnt/d Codex workspace now has a clearer blocker than the older capture note`
  - `visualization headless fragility and skip boundaries`
- 對 `BUG-ENV-001`，queue 現在已同步最新 evidence、boundary wording、workaround 與 next-step 描述，不再停在較舊的 ordering-failure 說法
- 接著直接完成 queue 裡寫的下一步：驗證在排除 `test_visualization_panel_redesign.py` collection pollution 後，`TestSaliency3DEngine` 是否還能單獨重現真正的 runtime fail
- 乾淨 Poetry process 內，暫時中和 `pytest.mark.skipif` 後直接執行三個 engine cases：
  - `test_creates PASS`
  - `test_update_scalars_returns_none_when_no_data PASS`
  - `test_on_download_complete_error PASS`
- 對照組：先用 `pytest --collect-only --capture=sys -q tests/unit/ui/test_visualization_panel_redesign.py` 讓 redesign test 走過 collection，再在同一 process 執行同樣三個 engine cases：
  - `test_creates FAIL:AssertionError`
  - `test_update_scalars_returns_none_when_no_data FAIL:AssertionError`
  - `test_on_download_complete_error PASS`
- 這讓目前邊界更清楚：
  - 在排除 collection/import pollution 的前提下，還沒有獨立重現出真正的 runtime fail
  - 目前穩定可重現的是 redesign test 在 collection/import 階段就把 engine surface 汙染成 `MagicMock`，再加上 `TestSaliency3DEngine` 本身仍被過期 skip policy 蓋住
- 因此這輪最小閉環的結論是：queue、triage、status、session log 現在都一致指向同一個 framing，不再把這條問題描述成已確認的獨立 VTK/Qt runtime ordering crash

### AQ-PREP-005 collect-only pollution evidence 再收斂

- 這輪把 `BUG-ENV-001` 從「手動 import redesign test 會污染」再往前縮成更接近 pytest 真實行為的證據
- 在同一 Poetry process 內直接跑 collect-only：
  - `/home/administrator/.local/bin/poetry run python - <<'PY' ... pytest.main(['--collect-only', '-q', 'tests/unit/ui/test_visualization_panel_redesign.py']) ... PY`
  - 結果：`9 tests collected`
  - `after_collect_module_type MagicMock`
- 對照組：
  - `/home/administrator/.local/bin/poetry run python - <<'PY' ... pytest.main(['--collect-only', '-q', 'tests/unit/ui/test_visualization.py']) ... PY`
  - 結果：`14 tests collected`
  - `after_collect_module_type MISSING`
- 這代表現在更精確的說法不是「也許執行 redesign tests 後會留下奇怪狀態」，而是「pytest collection 只要 import `test_visualization_panel_redesign.py`，就已經會把 `saliency_3d_engine` 污染成 `MagicMock`」
- 也因此 `@unittest.skip("Segfaults in headless environment due to VTK/Qt interaction")` 並不能阻止這條污染路徑，因為 side effect 早在 skip 判斷之前就發生在模組層
- 這讓 `BUG-ENV-001` 更穩地收斂成 collection-time import pollution 加上過期 skip policy，而不是已經分離乾淨的獨立 runtime crash

### AQ-PREP-005 queue sync 嘗試與第二 bug 判斷再收斂

- 依 reviewer handoff，這輪先嘗試把 `.agents/runbooks/active-queue.md` 的 `AQ-PREP-005` 記錄補齊成和 triage/status 一致
- 但在目前宿主環境中，對 `.agents/runbooks/active-queue.md` 的實際寫入仍回報 `OSError: [Errno 30] Read-only file system`，所以 queue 端本輪無法同步
- 在 queue 仍無法寫入的前提下，這輪先把同一結論寫進 human-facing docs：
  - `BUG-ENV-003` 目前維持 flaky workspace signal，而不是當前穩定 blocker
  - `BUG-ENV-001` 目前確認的 bug surface 是過期 skip policy 加上 `test_visualization_panel_redesign.py` 的模組層 `sys.modules` 污染
- 這輪也把「是否需要第二個獨立 bug record」先收斂成暫不拆分：
  - 乾淨 Poetry process 下 `Saliency3DEngine` 可正常 import
  - 先 import redesign test module 後，engine import 會變成 `MagicMock`
  - 清掉 `XBrainLab.backend.visualization` 與 `XBrainLab.backend.visualization.saliency_3d_engine` 後，真實 import surface 可恢復
- 因此目前最穩的結論不是「已經找到獨立的 VTK/Qt runtime ordering crash」，而是「舊 skip reason 仍混著尚未分離的歷史假說」
- 現階段更安全的記錄方式是先不另開第二個 bug，等之後真的把 import pollution 排除後還能單獨重現 runtime fail path，再拆成新的 bug ID

### BUG-ENV-001 workaround evidence 再收斂

- 這輪確認 `test_visualization_panel_redesign.py` 的模組層污染不只是能觀察到，還能在同一 Poetry process 內被局部清理
- 指令結果：
  - import redesign 後先檢查 engine module -> `before_cleanup MagicMock`
  - 清掉：
    - `XBrainLab.backend.visualization`
    - `XBrainLab.backend.visualization.saliency_3d_engine`
  - 再重新 import -> `after_cleanup module`
  - `after_cleanup_engine_type wrappertype`
- 這代表目前對 `BUG-ENV-001` 已經有比「重開 process 試試看」更具體的 workaround：
  - 最穩定的做法還是 fresh Poetry process
  - 但若同一 process 已受 `test_visualization_panel_redesign.py` 污染，也可以先清掉那兩個 `sys.modules` 鍵再驗證真實 engine import
- 同步更新：
  - `docs/current/BUG_TRIAGE.md`
  - `docs/current/STATUS_REPORT.md`

### BUG-ENV-005 prep-exit 決策收斂

- 依 reviewer handoff 的要求，這輪沒有直接修靜態品質債，而是先把 `BUG-ENV-005` 的 queue 含義定清楚
- 最新直接指令證據：
  - `/home/administrator/.local/bin/poetry run ruff check .` -> `20 errors`, `9` fixable
  - `/home/administrator/.local/bin/poetry run basedpyright` -> `107 errors, 1 warning, 0 notes`
  - `artifacts/quality/latest.md` 仍顯示較早的 `basedpyright PASS` 快照，因此 human-facing status 不能再直接照抄舊 dashboard snapshot
- 這輪決策是：
  - fast static gate 屬於 prep-exit blocker，因為 prep gate 需要可信的高頻驗證指令
  - slower `mypy` 仍維持 monitored debt，持續留在 full gate 監控，但不單獨卡住其他 runtime-signal triage 的收尾
- 同步更新：
  - `docs/current/BUG_TRIAGE.md`
  - `docs/current/STATUS_REPORT.md`
- 補充限制：
  - `.agents/runbooks/active-queue.md` 在目前 sandbox 下仍是唯讀，因此 queue 端的同一決策這輪無法直接寫回

### GDF duplicate-channel ambiguity 正式進入 `Raw` metadata 面

- 將 real GDF import 的 duplicate-channel signal 從「只有 MNE warning / XBrainLab logger warning」提升成 `Raw` wrapper 的 runtime metadata
- `Raw` 現在有：
  - `add_runtime_signal()`
  - `get_runtime_signals()`
  - `has_runtime_signals()`
- `load_gdf_file()` 在偵測到 MNE duplicate-name auto-rename 後，除了 re-emit 原始 warning 與記錄 repo warning，也會把同一條訊號附著到回傳的 `Raw`
- 這讓後續的 triage、整合測試、甚至未來 UI/summary surface 可以不用依賴 stderr/logger，就能知道該資料的 channel identity 有 ambiguity
- 聚焦驗證：
  - `tests/unit/backend/load_data/test_raw_data_loader.py` -> `5 passed`
  - `tests/integration/io/test_io_integration.py` -> `30 passed, 12 warnings`
- 這一輪沒有解決 duplicate channel naming 本身，但把 prep-gate runtime-signal triage 從「觀察到 warning」往「formalized, testable signal」推進了一步

### 品質看板改成快慢雙軌型別 gate

- 將 `basedpyright` 加入 Poetry dev 依賴，並在 `pyproject.toml` 補上 repo-local 設定
- 建立 `.basedpyright/baseline.json`，把目前既有的 repo-wide 型別債記成 baseline，而不是假裝它們不存在
- `scripts/dev/update_quality_dashboard.py` 現在預設跑 fast dashboard：
  - `ruff`
  - `basedpyright`
  - `architecture compliance`
  - startup / UI / real-data runtime slices
- 新增 `--include-slow-checks`，讓 full dashboard 可以額外把 `mypy` 一起跑進來
- 在 `pyproject.toml` 補上：
  - `poe quality-dashboard-full`
  - `poe typecheck-fast`
  - `poe mypy-daemon`
  - `poe check-full`
- 這次的策略不是把舊 `mypy` 問題藏起來，而是把：
  - 「高頻抓新退化」
  - 「較慢持續還舊債」
  拆成兩條明確流程
- 途中也修正了一個新的 dashboard 自己的環境問題：
  - `update_quality_dashboard.py` 一度把 matplotlib cache 放到 repo 內 `.codex/matplotlib-codex`
  - 但這個 workspace 已經存在一個 `.codex` 檔案，因此會直接觸發 `NotADirectoryError`
  - 現在已改回 `/tmp/matplotlib-codex`
- 另外補上 live report 的 `profile` 欄位，讓 `artifacts/quality/latest.md` 能明確標出本次是 `fast` 還是 `full`
- 這一輪驗證結果：
  - `tests/unit/scripts/test_update_quality_dashboard.py` -> `7 passed`
  - `basedpyright` -> `0 errors, 0 warnings, 0 notes`
  - `python scripts/dev/update_quality_dashboard.py` -> `FAIL`
    - fast profile 的紅燈是 `ruff check .` 與 real-data IO integration 的 default-capture teardown
  - `python scripts/dev/update_quality_dashboard.py --include-slow-checks` -> `FAIL`
    - full profile 另外還會顯示 `mypy XBrainLab/` 的 `7 errors in 5 files`

## 2026-04-18

### 環境與接手基線

- 為專案準備好 WSL2 開發環境
- 安裝 Poetry 與專案依賴
- 安裝 PyQt headless GUI 所需工具
- 驗證 app 可以啟動到 `MainWindow`
- 在 WSL headless 模式下驗證 UI 單元測試基線

### 接手治理文件

- 建立：
  - `AGENTS.md`
  - `docs/workflows/TAKEOVER.md`
  - `docs/workflows/TESTING_STRATEGY.md`
  - `docs/workflows/UI_BASELINE.md`
  - `docs/workflows/WORKFLOWS.md`
  - `docs/current/BUG_TRIAGE.md`
  - `docs/workflows/RISK_CLUSTERS.md`
  - `docs/workflows/DIALOG_MATRIX.md`
  - `docs/workflows/COVERAGE_GAPS.md`
  - `docs/history/BACKLOG.md`

### 共用 shell 安全性

- 擴充 `tests/unit/ui/test_main_window_sync.py`
- 新增 smoke protection，涵蓋：
  - 導覽狀態同步
  - 僅目標 panel 刷新行為
  - 當 panel 缺少 `update_panel()` 時仍可安全導覽
- 驗證：
  - `tests/unit/ui/test_main_window_sync.py`
  - `tests/integration/ui/test_ui_refresh.py`

### 視覺基線工作

- 新增 `scripts/dev/capture_ui_baseline.py`
- 建立 `artifacts/ui/`
- 產生第一份基線產物
- 確認目前 screenshot 輸出是全黑，因此暫時不可信

### 匯入與 label 穩定性修復

- 改善 `.mat` label 載入，優先選擇像 `classlabel` 這種較像 label 的變數，而不是盲目取第一個變數
- 補上 multi-variable `.mat` 檔的 coverage，避免第一個變數不是實際 label array 時誤判
- 改善 UI 回饋，避免 label import 套用 0 個 label 時無聲失敗
- 新增後端警告紀錄，用於舊版 label 數量不一致情況
- 讓 `EventLoader` 在以下情況清楚失敗：
  - 載入的 label sequence 是空的
  - event filtering 選完後把所有 EEG events 都移除了
- 收斂 alignment truncation warning 邏輯，讓 mismatch 記錄更準確
- 移除 `ImportLabelDialog` 對純數字 label 的假設，讓字串型 sequence label 可以被檢查與 mapping，而不是在 `int(...)` 時直接失敗
- 更新 `EventLoader` sequence mode，讓類別 / 字串 labels 能轉成穩定整數 event ID，同時保留帶引號數字字串的原始 code
- 擴充 label import service typing，讓修復後的路徑端到端一致
- 修正匯入 label 檔只用 basename 當 key 的問題，讓不同資料夾裡的同名檔可以共存
- 在 label mapping 相關畫面加入完整路徑 tooltip，讓多資料夾匯入仍可檢查，同時不改變 layout 結構
- 修正 `LabelMappingDialog` 的 auto-sort，讓它優先使用正規化後的精確匹配，而不是像 `sub01` vs `sub010` 這種脆弱的 substring-first 比對
- 修正 `EventFilterDialog`，避免不同 dataset 的舊選擇殘留，導致新 dataset 開啟時所有 event 都被默默取消勾選
- 阻止 `EventFilterDialog` 接受空的 keep-list，避免無聲地同步成零事件
- 移除 `DatasetActionHandler.import_label()` 假設第一個 label file 能代表整批 label 的做法
- 讓混合 timestamp / sequence 的 label batch 清楚失敗，而不是被第一個檔誤分類
- 修正 batch mapping dialog 取消時被誤顯示成假的 "No Labels Applied" warning
- 重構 `BackendFacade.attach_labels()`，改用共用 label-import 行為，而不是維持自己的 basename-only / numeric-only attach 路徑
- 新增對 epoch-style `.fif` 的支援：當 `read_raw_fif()` 失敗時，回退到 `mne.read_epochs()`
- 新增 `.fif.gz` 支援：raw-data loader factory 改成比對最長已註冊副檔名，而不是只看最後一段副檔名
- 調整 event-filter smart suggestion，改成彙整所有 candidate raw file，而不是只信任第一個
- 改善 dataset mismatch diagnostics，讓 channel / sfreq / type / duration mismatch 現在都會同時報出 expected 與 actual 值，並附上檔名
- 補上聚焦 coverage，涵蓋：
  - `ImportLabelDialog` 的字串 sequence label
  - `EventLoader` 的類別字串 label
  - 帶引號數字字串保留原始 event code
  - 不同資料夾的同 basename label files
  - `LabelMappingDialog` 的模糊 label auto-match
  - `EventFilterDialog` 的 stale 與 empty selection
  - `DatasetActionHandler` 的 batch import mode 分析
  - facade attach-label delegation 與 full-path mapping
  - `.fif` epoch fallback 與 `.fif.gz` 支援
  - `DatasetActionHandler` 的 multi-file smart-filter suggestion
  - `RawDataLoader` 更詳細的 mismatch diagnostics

### 驗證結果

- `tests/unit/backend/load_data/test_label_loader.py` 與 `test_label_loader_coverage.py`：通過
- `tests/unit/backend/services/test_label_import_service.py`：通過
- `tests/unit/backend/controller/test_dataset_ctrl.py` 與 `test_dataset_controller.py`：通過
- `tests/unit/ui/test_ui_misc.py`：通過
- `tests/unit/backend/load_data/test_event_loader.py` 與 `test_event_loader_strict.py`：通過
- `tests/unit/backend/load_data/test_label_import.py`：通過
- `tests/unit/ui/dataset/test_import_label.py`：通過

### 下一步建議

1. 檢查 raw-loader 對其他常見壓縮格式或 sidecar-based 格式是否仍有假設
2. 尋找由 channel-name 一致性而不是 channel-count 一致性引起的 dataset import 問題
3. 開始規劃 local-only AI 模式清理與 remote API 移除方向

## 2026-04-19

### AQ-001 再收一格：把 GDF duplicate-channel detail 變成 typed Raw API

- 這輪沒有直接進入高風險的 duplicate-name normalization，而是先把現有 `gdf_duplicate_channel_names` structured detail 再收斂成 `Raw` 的 typed convenience API
- `Raw` 現在新增：
  - `has_gdf_duplicate_channel_detail()`
  - `get_gdf_duplicate_channel_detail()`
- 這讓後續 dataset / preprocess diagnostics 不需要再硬編碼 runtime-detail key，就能拿到 duplicate-channel ambiguity；比較符合 AQ-001 現階段先做 guardrail、再決定是否 normalization 的節奏
- 同步更新了 unit / integration coverage：
  - `tests/unit/backend/load_data/test_raw.py`
  - `tests/unit/backend/load_data/test_raw_data_loader.py`
  - `tests/integration/io/test_io_integration.py`
- 驗證結果：
  - `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/unit/backend/load_data/test_raw.py -q` -> `32 passed`
  - `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/unit/backend/load_data/test_raw_data_loader.py -q` -> `5 passed`
  - `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/integration/io/test_io_integration.py -q` -> `30 passed, 12 warnings`

### AQ-PREP-005 redesign-suite class skip 再收斂成 stale-coverage surface

- 這輪沿著 `AQ-PREP-005` 裡 `visualization headless fragility and skip boundaries` 的剩餘 next step，直接檢查 `tests/unit/ui/test_visualization_panel_redesign.py` 那條 class-level skip 背後到底是 monitored debt 還是已可落成更具體的 bug 面
- 先做 temp no-skip 對照，不修改 repo 本體：
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh /tmp/test_visualization_panel_redesign_noskip.py -q`
  - 結果：`9 failed`
  - 九個 case 都先卡在過期 patch target `XBrainLab.ui.panels.visualization.panel.AggregateInfoPanel`
- 接著在第二個 temp copy 只修正這個 patch target：
  - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh /tmp/test_visualization_panel_redesign_noskip_patchfix.py -q`
  - 結果：process `Aborted`
  - traceback 停在 `self.MockAggregateInfoPanel.return_value = QWidget()`，代表這份 unittest file 在 no-skip 路徑下連最基本的 Qt app harness 都還沒補上
- 最後在第三個 temp copy 同時補上：
  - 正確的 `AggregateInfoPanel` patch target
  - 最小 `QApplication` bootstrap
  - 驗證：
    - `/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh /tmp/test_visualization_panel_redesign_noskip_qapp.py -q`
    - 結果：`8 failed, 1 passed`
- 這個 no-skip + qapp 路徑揭露的已是更具體的 stale API/test drift，而不是先撞到獨立的 VTK/Qt segfault：
  - `XBrainLab.ui.panels.visualization.plot_3d_head.os` patch target 無效
  - `VisualizationPanel.refresh_data` 不存在
  - `VisualizationPanel.btn_montage` 不存在
  - `SaliencyTopographicMapWidget.plot_layout` 不存在
  - `plan_combo.count()` 等舊 UI 假設已不再成立
  - topomap `plt.close` 的行為預期也已過期
- 這讓 `BUG-ENV-001` 又往前縮一格：
  - collection-time pollution 已隔離
  - `TestSaliency3DEngine` engine-basics slice 已在正常 pytest path 綠燈
  - redesign suite 的 class-level skip 現在更像是在遮住 stale coverage surface，而不是在隔離一條已證實的第二條 VTK runtime bug
- 同一輪把這個 framing 同步回：
  - `docs/current/BUG_TRIAGE.md`
  - `docs/current/STATUS_REPORT.md`

### 品質看板強化與 UI reference gate

- 將 `ruff`、`mypy`、`architecture compliance` 正式接進 `scripts/dev/update_quality_dashboard.py`
- 將核心 UI baseline 從「檔案存在且不是黑圖」升級成和 `tests/baselines/ui/` approved references 比較
- 重新以 live capture 重產：
  - `artifacts/ui/main-window-initial.png`
  - `artifacts/ui/panel-dataset.png`
  - `artifacts/ui/panel-preprocess.png`
  - `artifacts/ui/panel-training.png`
  - `artifacts/ui/panel-evaluation.png`
  - `artifacts/ui/panel-visualization.png`
  - `artifacts/ui/ai-assistant-open.png`
- 將同一批核心畫面升格為 repo 內 reference baseline：
  - `tests/baselines/ui/*.png`
- 在這個 checkout 真正安裝 pre-commit hook：
  - `pre-commit installed at .git/hooks/pre-commit`
- 聚焦驗證：
  - `tests/unit/scripts/test_update_quality_dashboard.py` -> `7 passed`
  - `python tests/architecture_compliance.py` -> `PASS`
  - `python scripts/dev/update_quality_dashboard.py` -> `overall FAIL`
- 這次 dashboard refresh 明確暴露的紅燈：
  - `ruff check .` -> `21 errors`, `10` 可 auto-fix
  - `mypy XBrainLab/` -> `7 errors in 5 files`
  - `tests/integration/io/test_io_integration.py -q` 的 default capture teardown 仍失敗

### UI baseline 定義澄清

- 明確把目前的 UI baseline 分成三層：
  - `docs/workflows/UI_BASELINE.md` 是人類可讀的結構基準
  - `artifacts/ui/` 是每次驗證時重產的 live evidence
  - `tests/baselines/ui/` 是未來正式 reference screenshots 的固定位置
- 明確記錄當時 quality dashboard 對 UI 做的是 structural-health check，不是 golden screenshot diff
- 把「把 UI baseline 升級成真正 regression gate」加入 prep queue
- 這讓後續的 UI 監測不會再把「現在能重產 screenshot」和「我們已經有正式對照基準」混為一談

### 真實資料基線確認

- 確認 repo 已帶有三個 checked-in 的真實 EEG fixture：
  - `tests/data/A01T.gdf`
  - `tests/data/A02T.gdf`
  - `tests/data/A03T.gdf`
- 確認對應 label fixture 位於 `tests/data/label/`
- 確認目前真實資料體積仍相對節制，三個 GDF 檔總共約 98 MB

### 訓練 / 執行期穩定化

- 重現了一個非 load-data 類錯誤：這台主機上 `torch.cuda.is_available()` 回傳 `True`，但實際 training 仍會失敗，因為目前安裝的 PyTorch build 無法在偵測到的 RTX 5070 Ti 上真正執行
- 更新 `TrainingOption`，讓它在要求 CUDA device 時先做 probe；若 device 雖存在但不可用，則以 warning 方式回退到 CPU
- 在 `tests/unit/backend/training/test_option.py` 補上此 fallback path 的單元測試
- 直接在這台機器上驗證，要求 GPU 的 `TrainingOption` 現在會解析成：
  - `use_cpu=True`
  - `gpu_idx=None`
  - `device=cpu`

### 真實資料整合測試修復

- 修正兩個 integration test，它們原本誤找 `tests/integration/data/`，而不是 repo 內實際存在的 `tests/data/`
- 解除以下測試對 real-data coverage 的 skip：
  - `tests/integration/pipeline/test_real_data_pipeline.py`
  - `tests/integration/io/test_io_integration.py`

### 驗證結果

- `tests/unit/backend/training/test_option.py`：42 passed
- `tests/integration/pipeline/test_pipeline_integration.py`
- `tests/integration/pipeline/test_real_data_pipeline.py`
- `tests/integration/io/test_io_integration.py`
  - 結果：5 passed
- `tests/integration/controller/test_preprocess_controller.py`
- `tests/integration/pipeline/test_all_real_tools.py`
  - 結果：15 passed

### 重要執行期訊號

- 真實 GDF workflow 仍會持續噴出 MNE duplicate channel name warning（`EEG`），這是下一個很值得深入調查的 real-data 問題
- PyTorch 的 CUDA compatibility warning 在 fallback 前仍然會出現，但 training 路徑至少不再因此直接 crash，而是降級到 CPU

### 下一步建議

1. 研究重複 channel name warning 是否會進一步影響 channel selection、montage 或儲存後 diagnostics
2. 擴大 real-data validation，補上對 checked-in fixture 的 label-attached dataset generation 與 training smoke
3. 在 load-data 之外持續做 broader stabilization，例如 local-only AI mode cleanup 或黑圖 screenshot baseline 問題

### 多格式真實資料 fixture 擴充

- 在 `tests/data/multiformat/` 下建立一組體積小的 cross-format fixture pack
- 所有 fixture 都取自真實 `A01T.gdf` 記錄中的 15 秒、8 channel 片段，兼顧真實訊號與小體積
- 新增以下 checked-in 副檔名：
  - `.fif`
  - `.fif.gz`
  - epoch-style `.fif`
  - `.edf`
  - `.bdf`
  - `.vhdr` 搭配 `.eeg` 與 `.vmrk`
  - `.set`
- 在 `tests/data/multiformat/README.md` 記錄 fixture 的來源與用途
- 新增資料量保持很小，整組約 696 KB

### 多格式驗證結果

- 手動確認 `load_raw_data()` 可成功載入：
  - `A01T.gdf`
  - `A01T-mini-real_raw.fif`
  - `A01T-mini-real_raw.fif.gz`
  - `A01T-mini-real.edf`
  - `A01T-mini-real.bdf`
  - `A01T-mini-real.vhdr`
  - `A01T-mini-real.set`
  - `A01T-mini-real-epo.fif`
- 手動確認 `BackendFacade.load_data()` 也能成功處理同一批副檔名
- 擴充 `tests/integration/io/test_io_integration.py`，讓 real-data integration slice 同時涵蓋：
  - 所有 compact real fixture 的 direct loader validation
  - 同一批副檔名的 facade-level dataset import

### 補充驗證結果

- `tests/integration/io/test_io_integration.py`：19 passed

### 新的執行期訊號

- 真實 BCI Competition GDF fixture 仍會因重複 channel name 觸發 MNE warning，現在已在 triage 裡成為獨立條目，適合作為下一個 real-data 問題

### Codex 執行環境與本地 workspace 基線

- 建立並切換到工作分支 `codex/stabilization-autopilot`
- 建立 thread heartbeat automation `xbrainlab-autopilot`，最初採 30 分鐘節奏，讓穩定化工作能在同一對話中持續進行
- 為目前 `/mnt/d/repos/XBrainLab` workspace 安裝 Poetry environment，使本地 Codex thread 可以直接從這份 checkout 執行專案
- 以以下指令確認目前 workspace 的 startup smoke：
  - `timeout 25s xvfb-run -a /home/administrator/.local/bin/poetry run python run.py`
  - 結果：可以啟動到 `MainWindow initialized`，並存活到 timeout
- 再次確認視覺基線阻塞點：
  - `xvfb-run -a /home/administrator/.local/bin/poetry run python scripts/dev/capture_ui_baseline.py`
  - 結果：仍以 `Captured screenshot is nearly all black` 結束
- 確認聚焦驗證切片在這個 workspace 中用 `-s` 可通過：
  - `tests/unit/backend/training/test_option.py`：42 passed
  - `tests/unit/ui/test_main_window_sync.py`：8 passed
  - `tests/integration/io/test_io_integration.py`：19 passed
- 同時辨識出新的本地驗證 blocker：
  - 預設 `pytest` capture 會在 `/mnt/d` Codex workspace 的 teardown 階段失敗，但同一批 slice 用 `-s` 可通過

### 下一步建議

1. 更新 repo 文件，反映新的 Codex harness、prep gate、branch policy 與本地驗證假設
2. 修掉黑色 screenshot baseline，讓 `artifacts/ui/` 重新可信
3. triage 或修復目前 workspace 的預設 pytest capture teardown failure

### 視覺基線修復

- 將脆弱的 `scrot` 路徑改成直接抓取 Qt main window 的方式，更新 `scripts/dev/capture_ui_baseline.py`
- 在 `tests/unit/scripts/test_capture_ui_baseline.py` 補上聚焦的黑圖 heuristic 測試
- 重新執行：
  - `xvfb-run -a /home/administrator/.local/bin/poetry run python scripts/dev/capture_ui_baseline.py`
  - 結果：`artifacts/ui/main-window-initial.png` 已從全黑畫面變成可見的 main-window artifact
- 執行組合驗證：
  - `tests/unit/scripts/test_capture_ui_baseline.py`
  - `tests/unit/backend/training/test_option.py`
  - `tests/unit/ui/test_main_window_sync.py`
  - `tests/integration/io/test_io_integration.py`
  - 結果：`71 passed, 5 warnings`

### 五個主 panel 擷取與公開 fixture 擴充

- 更新 capture helper，讓它現在會輸出：
  - `artifacts/ui/main-window-initial.png`
  - `artifacts/ui/panel-dataset.png`
  - `artifacts/ui/panel-preprocess.png`
  - `artifacts/ui/panel-training.png`
  - `artifacts/ui/panel-evaluation.png`
  - `artifacts/ui/panel-visualization.png`
- 建立 `scripts/dev/fetch_public_eeg_fixtures.py`，下載小型跨來源 EEG fixture 組到 `tests/data/public/`
- 在 `tests/data/public/README.md` 記錄這批 public fixture
- 本地下載並驗證三個外部 fixture：
  - PhysioNet `physionet-eegmmidb-S008R01.edf`
  - BBCI `bbci-competition-iii-O3VR.gdf`
  - SCCN `sccn-eeglab_data.set`
- 擴充 `tests/integration/io/test_io_integration.py`，讓 real-data IO 驗證切片在 fixture 存在時，也會涵蓋這些公開 EDF / GDF / SET
- 驗證結果：
  - `tests/integration/io/test_io_integration.py`
  - 結果：`25 passed, 7 warnings`

### 讓使用者能追得上的報告頁

- 新增 `docs/current/STATUS_REPORT.md` 作為精簡的人類可讀進度快照
- 更新 Codex 執行環境文件，要求之後工作循環與 heartbeat run 都維護這份報告
- 將 heartbeat cadence 從 30 分鐘改成 10 分鐘
- 重新整理 `docs/current/STATUS_REPORT.md`，讓它按已同意的長期計畫分段，而不是平鋪式筆記
- 在重整報告後重新驗證：
  - `xvfb-run -a /home/administrator/.local/bin/poetry run python scripts/dev/capture_ui_baseline.py`
    - 結果：六張 baseline image 全部成功重產
  - `/home/administrator/.local/bin/poetry run pytest -s tests/unit/scripts/test_capture_ui_baseline.py tests/integration/io/test_io_integration.py -q`
    - 結果：`27 passed, 7 warnings`

### 控制面澄清

- 澄清兩種 assistant 介面不應再被混在一起：
  - Codex 是這個 repo 外部的開發助手
  - app 內 assistant 是 XBrainLab 裡的具 workflow awareness 的軟體操作 agent
- 澄清 human user 與 app 內 assistant 應視為操作同一組軟體能力面的兩種控制模式
- 澄清目前的 tool-call taxonomy 可以重設，不應因慣性被保留；未來應回到 workflow intent 重新思考
- 新增 `docs/decisions/ADR-013-in-app-assistant-product-definition.md`，作為未來 app 內 assistant 重設計的產品定義錨點

### Heartbeat 執行層中斷

- 有幾個 heartbeat 週期一度無法持續工作，因為 thread 暫時無法啟動基本 shell process
- 恢復後確認：
  - `/bin/sh` 與 `/bin/bash` 都重新可用
  - repo 內的 autopilot docs 與 active-queue 內容不是根因
  - 因此，先前 heartbeat 卡住比較符合暫時性的 Codex / desktop 執行層問題，而不是 repo 設定錯誤

### 真實 GDF 重複 channel 可觀測性

- 直接重跑 `load_gdf_file('tests/data/A01T.gdf')`，確認匯入後 channel list 內會出現像 `EEG-0`、`EEG-1` 這種產生式名稱，只有少數明確名稱如 `EEG-Fz`、`EEG-C3`、`EEG-Cz`、`EEG-C4`、`EEG-Pz`
- 確認這個執行期訊號不只是 MNE 的一般 warning：
  - `load_gdf_file()` 現在會在 GDF import 依賴 MNE 自動重命名重複 channel name 時，額外記錄 XBrainLab 自己的 warning
- 在 `tests/unit/backend/load_data/test_raw_data_loader.py` 補上這個 signal 的單元測試
- 重新執行：
  - `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/unit/backend/load_data/test_raw_data_loader.py -q`
    - 結果：`5 passed`
  - `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/integration/io/test_io_integration.py -q`
    - 結果：`25 passed, 7 warnings`
- 目前結論：
  - 這仍然是開放中的 dataset / workflow 問題，不是 crash
  - 可觀測性雖然變好了，但底層不明確的 channel identity 仍未真正解決

### Agent stack 澄清

- 澄清明確的 agent 端 stack 應該放在 `.agents/` 下，而不只是 `docs/`
- 新增 `.agents/stack.md`，記錄：
  - 預設採用的 skills
  - 僅在條件成立時使用的 skills
  - 規則政策
  - heartbeat 閱讀順序
- 更新 `AGENTS.md`、`.agents/runbooks/setup.md`、`.agents/runbooks/autopilot.md`，讓 unattended work 在繼續前先讀 `.agents/stack.md`
- 擴充外部設置依據，納入：
  - OpenAI Codex docs
  - Anthropic Claude Code docs
  - GitHub agent-skill docs
  - vendor-neutral `agentmd` repository

### 完整的人類文件 / agent 文件切分

- 將 canonical agent runtime surface 移到：
  - `.agents/runbooks/setup.md`
  - `.agents/runbooks/autopilot.md`
  - `.agents/runbooks/active-queue.md`
- 保留 `docs/` 作為人類閱讀面，並新增 `docs/current/PLAN.md`
- 將這些 root-level doc 改為相容性 stub：
  - `.agents/runbooks/setup.md`
  - `.agents/runbooks/autopilot.md`
  - `.agents/runbooks/active-queue.md`
- 為重複性 workflow 建立 repo-local skills：
  - `.agents/skills/xbrainlab-prep-gate/SKILL.md`
  - `.agents/skills/xbrainlab-repair-loop/SKILL.md`
- 更新正式閱讀順序，讓 unattended work 先讀 `.agents/`，再讀人類計畫與進度文件

### Skill stack 擴充

- 更深入檢視官方與高訊號 skill 生態：
  - OpenAI Codex docs 的 skills 與 Docs MCP
  - Anthropic 關於 focused subagent 與 project-scoped versioned assets 的文件
  - `anthropics/skills`
  - Awesome GitHub Copilot 的公開 skill directory
- 新增更窄、更聚焦的 repo-local skills，而不只停留在 `prep` 與 `repair`：
  - `.agents/skills/xbrainlab-workflow-baseline/SKILL.md`
  - `.agents/skills/xbrainlab-dialog-audit/SKILL.md`
  - `.agents/skills/xbrainlab-real-data-validation/SKILL.md`
  - `.agents/skills/xbrainlab-refresh-smoke/SKILL.md`
- 為 repo-local skills 新增 `agents/openai.yaml` metadata，讓本地 skill surface 更完整
- 在 `docs/reference/AGENT_SKILLS.md` 記錄選型理由，以及檢視過但未選用的 skill 生態

### 人類文件整理

- 移除人類文件的 compatibility-stub 方案，讓 `docs/` 能保持更乾淨
- 將主要使用者狀態文件移到：
  - `docs/current/PLAN.md`
  - `docs/current/STATUS_REPORT.md`
  - `docs/current/BUG_TRIAGE.md`
- 將 workflow 比較重的支撐文件移到 `docs/workflows/`
- 將長期累積紀錄移到 `docs/history/`
- 將 skill selection 背景移到 `docs/reference/AGENT_SKILLS.md`
- 重寫 `docs/index.md`，讓它成為人類優先的 docs 入口，直接告訴使用者先看哪三份文件
- 更新 agent 端 references 與 `XBrainLab Autopilot` heartbeat prompt，讓 unattended work 跟著新的 doc layout，而不是舊的 root-level doc 路徑

### 頂層 panel 基線與 AI shell 訊號

- 擴充 `scripts/dev/capture_ui_baseline.py`，讓 helper 也會抓 `artifacts/ui/ai-assistant-open.png`
- 在 `tests/unit/scripts/test_capture_ui_baseline.py` 補上這個擷取步驟的聚焦單元 coverage
- 重新產生 headless 基線產物：
  - `xvfb-run -a /home/administrator/.local/bin/poetry run python scripts/dev/capture_ui_baseline.py`
  - 結果：shell、五個主 panel、AI assistant 開啟狀態都成功擷取
- 重新執行 helper 的聚焦驗證：
  - `/home/administrator/.local/bin/poetry run pytest -s tests/unit/scripts/test_capture_ui_baseline.py -q`
  - 結果：`4 passed`
- 重新執行 shell 層級 workflow 證據的 Qt integration 切片：
  - `xvfb-run -a /home/administrator/.local/bin/poetry run pytest -s tests/integration/ui/test_e2e_qtbot.py -q`
  - 結果：`20 passed`
- 同一個 integration 切片也暴露了已確認的 AI assistant 執行期問題：
  - 第一次開啟時的 local model 初始化會因缺少 `accelerate` 而失敗
- 將這個執行期訊號記錄為 `BUG-AGENT-001`
- 同時記下一個新的設計邊界例外：
  - 使用者已明確同意可以對 AI assistant panel 做有意識的重設計

### 高優先 dialog acceptance coverage

- 新增 `tests/integration/ui/test_dialog_acceptance.py`，透過真實 widget 互動與 OK-button 路徑，驗證四個 prep-gate 高優先 dialog：
  - `LabelMappingDialog`
  - `EventFilterDialog`
  - `EpochingDialog`
  - `TrainingSettingDialog`
- 驗證結果：
  - `xvfb-run -a /home/administrator/.local/bin/poetry run pytest -s tests/integration/ui/test_dialog_acceptance.py -q`
  - 結果：`4 passed`
- 這大幅縮小了 prep gate 在 modal 路徑上的盲區：
  - 這些 dialog 已不再只靠 direct method call 或 patched dialog-entry mock 來覆蓋
  - 剩餘限制是更大的測試 harness 仍 patch 了 `QDialog.exec`，因此這代表的是很強的 headless acceptance coverage，而不是完整的手動桌面行為驗證

### 共用 refresh 傳播 coverage

- 新增 `tests/unit/ui/test_panel_event_bridges.py`，直接驗證最高價值的 observer-bridge 傳播路徑：
  - dataset events -> `PreprocessPanel.update_panel()`
  - dataset events -> `TrainingPanel.update_panel()`
  - `training_stopped` -> `EvaluationPanel.update_panel()`
  - `training_stopped` -> `VisualizationPanel.update_panel()`
- 驗證結果：
  - `/home/administrator/.local/bin/poetry run pytest -s tests/unit/ui/test_panel_event_bridges.py -q`
  - 結果：`4 passed`
- 這補強了既有的 `MainWindow.switch_page()` smoke test，因為它直接驗了 event-driven 路徑，而不只是 tab 導覽

### AI shell triage 收斂

- 確認 `accelerate` 雖然已在 `pyproject.toml` 宣告，但只存在於可選的 Poetry `llm` group
- 這讓 `BUG-AGENT-001` 更聚焦：
  - 問題不只是「原始碼裡少了依賴」
  - 更精確地說，是活躍本地環境與 UI 對 local-model startup readiness 的假設不一致，加上 UI 在 local backend 啟動前缺少 preflight 行為

### Pytest capture triage 收斂

- 再次以以下指令重現 `BUG-ENV-003`：
  - `/home/administrator/.local/bin/poetry run pytest tests/unit/backend/training/test_option.py -q`
  - 結果：在 `_pytest/capture.py` teardown 階段失敗
- 進一步拆分 capture backend：
  - `--capture=fd` 仍然失敗
  - `--capture=sys` 可通過
  - `--capture=tee-sys` 可通過
  - `-s` 也可通過
- 以代表性切片驗證 `--capture=sys` workaround：
  - `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/unit/backend/training/test_option.py -q`
  - `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/unit/ui/test_main_window_sync.py -q`
  - `xvfb-run -a /home/administrator/.local/bin/poetry run pytest --capture=sys tests/integration/ui/test_dialog_acceptance.py -q`
- 結論：
  - 目前 workspace 的問題明確是 `fd` capture，不是整體 pytest collection 或 execution 壞掉
  - `--capture=sys` 是目前較推薦的本地 workaround，因為它保留了 capture 行為，又不會在 teardown crash

### unattended UI 驗證環境再收斂

- 重新檢查 heartbeat 真正卡住的 UI 驗證路徑，發現目前更穩定的 blocker 不是 `BUG-ENV-003`，而是 unattended Qt 啟動環境
- 直接執行以下指令時，UI pytest 會在 `pytest-qt` 的 `qapp` fixture 初始化階段 abort：
  - `xvfb-run -a /home/administrator/.local/bin/poetry run pytest tests/integration/ui/test_dialog_acceptance.py -q`
- runtime signal 顯示：
  - Qt 嘗試載入 `wayland` / `xcb` plugin 後失敗
  - matplotlib 預設 cache path 在目前本地 Codex run 中也不可寫
- 以以下最小 workaround 重跑同一條 slice：
  - `MPLCONFIGDIR=/tmp/matplotlib-codex QT_QPA_PLATFORM=offscreen /home/administrator/.local/bin/poetry run pytest --capture=sys tests/integration/ui/test_dialog_acceptance.py -q`
  - 結果：`4 passed`
- 再用相同環境前置驗證既有 UI runner：
  - `QT_QPA_PLATFORM=offscreen MPLCONFIGDIR=/tmp/matplotlib-codex /home/administrator/.local/bin/poetry run python scripts/dev/run_tests.py ui`
  - 結果：`742 passed, 15 skipped, 1 warning`
- 因此新增 repo-local helper：
  - `scripts/dev/run_ui_pytest.sh`
- helper 會固定套用：
  - `QT_QPA_PLATFORM=offscreen`
  - `MPLBACKEND=Agg`
  - `MPLCONFIGDIR=/tmp/matplotlib-codex`
  - `--capture=sys`
- 同步更新：
  - `scripts/dev/run_tests.py` 的 `ui` 路徑
  - `.agents/runbooks/setup.md`
  - `docs/workflows/TESTING_STRATEGY.md`
  - triage / queue / status report
- 這代表目前 heartbeat 自動化若要跑 UI pytest，應該直接走 repo-local helper，而不是裸跑 pytest 指令

### 品質看板與定期監測入口

- 新增 `scripts/dev/update_quality_dashboard.py`
- 新增 `docs/current/QUALITY_DASHBOARD.md` 作為人看的固定入口
- live dashboard output 現在會寫到：
  - `artifacts/quality/latest.md`
  - `artifacts/quality/latest.json`
  - `artifacts/quality/history.jsonl`
- 新增 `artifacts/quality/.gitignore`，避免自動刷新把 generated report 變成長期 git 噪音
- 新增單元測試：
  - `tests/unit/scripts/test_update_quality_dashboard.py`
- 第一輪完整 dashboard refresh 的檢查集包含：
  - startup smoke
  - UI baseline capture
  - dialog acceptance
  - UI unit suite
  - real-data IO integration
- 第一輪 live 結果：
  - `overall FAIL`
  - 失敗點不是 UI，而是 `Real-Data IO Integration`
  - 這次看板刷新重新證明 `BUG-ENV-003` 還在，因為預設 capture 再次於 `_pytest/capture.py` teardown 階段失敗
- 這代表 dashboard 不是單純展示綠燈，而是真的能把目前 workspace 最脆弱的驗證路徑抓出來

### AI assistant 本地啟動強化

- 將 `BUG-AGENT-001` 從單一缺少 `accelerate` 的表面症狀，收斂成兩個獨立問題：
  - 第一次啟動時的 worker path 忽略 persisted settings，直接建立全新的預設 `LLMConfig()`
  - local backend 太晚才發現缺少 runtime package，等進入 backend initialization 後才失敗
- 更新 `AgentWorker.initialize_agent()`，讓第一次初始化時也會先載入 persisted settings，再決定 backend
- 在以下位置加入 local-runtime readiness helper：
  - `AgentWorker`
  - `ChatPanel.update_model_menu()`
  - `ModelSettingsDialog`
- 將目前 assistant 方向改成 local-only startup，而不是用 Gemini fallback 去掩蓋 bootstrap failure
- 用以下測試驗證這次強化：
  - `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/unit/llm/core/test_config.py tests/unit/llm/agent/test_worker.py -q`
  - `xvfb-run -a /home/administrator/.local/bin/poetry run pytest --capture=sys tests/unit/ui/chat/test_chat_panel.py tests/unit/ui/dialogs/test_model_settings.py -q`
  - `xvfb-run -a /home/administrator/.local/bin/poetry run pytest --capture=sys tests/integration/ui/test_e2e_qtbot.py -q`
- 這個 workspace 目前剩下的 local-only 阻塞點：
  - 尚未有 local model cache
  - 仍缺一次乾淨的真實下載模型 end-to-end local startup 驗證

### 純本地環境收斂

- 以以下指令在目前 Poetry environment 安裝可選的 local-LLM 依賴：
  - `/home/administrator/.local/bin/poetry install --with llm --no-interaction`
- 之後確認 `LLMConfig.missing_local_runtime_packages()` 已回傳 `[]`
- 確認下一個 local-only 阻塞點不是缺套件，而是主機 CUDA 不相容：
  - `torch.cuda.is_available()` 仍回傳 `True`
  - 但直接做 CUDA allocation probe 會失敗，拋出 `RuntimeError: CUDA error: no kernel image is available for execution on the device`
- 更新 `LocalBackend`，讓它在 model load 前先 probe 指定 CUDA device；若 GPU 不可用，就回退到 CPU，並關閉 4-bit loading
- 用以下測試驗證 CUDA fallback 強化：
  - `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/unit/llm/core/test_local_backend.py tests/unit/llm/core/test_config.py tests/unit/llm/agent/test_worker.py -q`
  - 結果：`50 passed`
- 確認目前設定的 local model 預期 cache path 仍不存在：
  - `/mnt/d/repos/XBrainLab/XBrainLab/llm/core/models/Qwen_Qwen2.5-7B-Instruct`
- 在環境變更後曾嘗試單獨重跑 `tests/integration/ui/test_e2e_qtbot.py`，但因在 AI-dock 區塊後 hang 太久而中止，因此那次執行不算 accepted evidence

### App 內 assistant 的文獻定位修正

- 依使用者澄清，修正對 app 內 assistant 的工作理解：
  - 開發助手是 app 外的 Codex
  - app 內 assistant 是用來操作 XBrainLab 本身
- 目標架構應是以 tool call 為中心，讓較弱的本地模型在產品內仍能有效工作
- 依以下來源重新比對目前定位：
  - OpenAI 的 tool 與 function-calling 文件
  - Anthropic 的 tool-definition 與 agent-architecture 指南
  - ReAct 論文
- 將工作結論記錄在 `docs/history/LITERATURE_LOG.md`
- 同步更新 agent 端記憶文件：
  - `AGENTS.md`
  - `.agents/stack.md`
  - `.agents/runbooks/setup.md`
  讓 heartbeat run 之後也會保留這個區分
- 目前產品立場：
  - tool calling 是執行骨幹，不是附帶功能
  - app 內 assistant 應被視為 workflow operator，而不是 developer copilot
  - 對終端使用者不應預設提供無限制 local-model choice；更合理的是有限、可驗證的 curated model set

### 更新後的下一步建議

1. 驗證頂層 panel 的 happy path，並收集超越初始 shell 的更多基線產物
2. triage 或修復目前 workspace 的預設 pytest capture teardown failure
3. 持續處理 prep-gate 中高風險 dialog acceptance flow 與 downstream refresh propagation

### 碩論主線文件收斂

- 在 `AGENTS.md` 中明確寫出這個 repo 是碩論實作 workspace
- 記錄目前碩論工作順序：
  - 先穩定化
  - 再重設 tool-call agent 架構
  - 並持續補上嚴謹驗證
- 簡化 `docs/index.md`，讓人類入口只強調 current status、plan、triage、decision-record 這幾份文件
- 新增 `docs/decisions/README.md` 作為 decision-record 入口
- 新增 `docs/decisions/ADR-011-thesis-direction.md`，讓之後的 tool-call agent redesign 有明確主設計錨點，而不是散落在各處
- 更新 `docs/current/PLAN.md` 與 `docs/current/STATUS_REPORT.md`，讓它們反映碩論主線，而不只是穩定化循環

### Repo 結構盤點與重整提案

- 完成整個 repo 的結構盤點，涵蓋：
  - 根目錄資料夾
  - `docs/`
  - `XBrainLab/`
  - `tests/`
  - `scripts/`
  - `ROADMAP.md`、`CHANGELOG.md`、`mkdocs.yml` 這類根目錄入口檔
- 確認核心問題是資訊膨脹，而不是某一個資料夾單獨設計不好：
  - 現行文件
  - 歷史筆記
  - API / reference material
  - thesis decisions
  - 對外文件導覽
  都在競爭近似的可見度
- 新增 `docs/decisions/ADR-012-project-structure-redesign.md`，作為 repo / 文件資訊架構重整的提案
- 更新 `docs/decisions/README.md` 與 `docs/current/STATUS_REPORT.md`，讓這份結構提案能從 active docs surface 被找到

### Repo 結構遷移第一階段

- 新增 root `README.md`，讓 repo 現在有標準的人類入口
- 更新 `pyproject.toml`，讓 package readme 指向根目錄 `README.md`，而不是 `docs/index.md`
- 建立：
  - `docs/guides/README.md`
  - `docs/api/README.md`
  - `docs/archive/README.md`
  - `docs/archive/` 各子資料夾的 README
- 移動：
  - `docs/getting-started/installation.md` -> `docs/guides/installation.md`
  - `docs/getting-started/quickstart.md` -> `docs/guides/quickstart.md`
  - `docs/contributing.md` -> `docs/guides/contributing.md`
  - `docs/architecture/` -> `docs/archive/architecture/`
  - `docs/agent/` -> `docs/archive/agent/`
  - `docs/development/` -> `docs/archive/development/`
  - `docs/reference/` -> `docs/archive/reference/`
- 更新 `docs/index.md` 與 `mkdocs.yml`，讓對外導覽對齊新結構
- 更新內部仍指向舊路徑的 doc links
- 驗證：
  - 本地 markdown link scan：`BROKEN=0`
  - MkDocs nav target existence check：`MISSING=0`

### Status report 改版

- 將 `docs/current/STATUS_REPORT.md` 重寫成最新優先的快照，而不是照著 plan 鏡像展開的敘事型報告
- 明確將它與 `CHANGELOG.md` 區分：
  - `STATUS_REPORT.md` 回答「現在真實狀態是什麼」
  - `CHANGELOG.md` 回答「某個版本正式改了什麼」
- 把最新、最實際的進展移到報告最前面，讓使用者一打開就能先看到最近改了什麼

### Public EEG fixture 多樣性擴充

- 重新檢查目前資料集準備狀態後，確認缺口不在 repo 內 compact multiformat pack，而是在 public-source baseline 還不夠多樣
- 更新 `scripts/dev/fetch_public_eeg_fixtures.py`，讓它從單檔下載清單升級成 fixture-group 下載：
  - 保留既有的 PhysioNet EDF、BBCI GDF、SCCN EEGLAB `.set`
  - 新增 MNE testing-data 的 `scan41_short.cnt`
  - 新增 MNE testing-data 的 BrainVision `test_NO.vhdr`，並一併下載 sidecars `test_NO.eeg`、`test_NO.vmrk`
- 更新 `tests/data/public/README.md`，明確記錄目前 public baseline 的來源與覆蓋格式
- 更新 `tests/integration/io/test_io_integration.py`，讓 public real-data slice 也會覆蓋：
  - CNT
  - BrainVision `.vhdr`
- 在實作前先用暫存目錄驗證：
  - `scan41_short.cnt` 可被 `load_raw_data()` 成功載入
  - `test_NO.vhdr` 可在 sidecar 齊全時被 `load_raw_data()` 成功載入
- 實際下載到 `tests/data/public/` 後，再執行：
  - `/home/administrator/.local/bin/poetry run python scripts/dev/fetch_public_eeg_fixtures.py`
  - `/home/administrator/.local/bin/poetry run pytest --capture=sys tests/integration/io/test_io_integration.py -q`
  - 結果：`29 passed, 11 warnings`
- 目前新增 public fixtures 後可觀察到的非阻塞 warning：
  - `scan41_short.cnt` 會出現 meas date 與 byte-width 相關 MNE warning
  - 既有 `bbci-competition-iii-O3VR.gdf` 的 annotation-range warning 仍存在
  - 兩者目前都不阻止 import 與 facade import 通過
- 這讓目前 workspace 的 public real-data baseline 來源擴大到：
  - PhysioNet
  - BBCI
  - SCCN
  - MNE testing-data
- 檔案型別則擴大到：
  - EDF
  - GDF
  - EEGLAB `.set`
  - CNT
  - BrainVision `.vhdr`

### Thesis 文件面集中

- 新增 `docs/thesis/`，把原本分散在 `current/`、`decisions/`、`history/`、`workflows/` 的碩論材料整理成 thesis-facing surface
- 新增以下文件：
  - `docs/thesis/README.md`
  - `docs/thesis/problem-statement.md`
  - `docs/thesis/system-design.md`
  - `docs/thesis/dataset-baseline.md`
  - `docs/thesis/validation-plan.md`
  - `docs/thesis/results-log.md`
  - `docs/thesis/threats-to-validity.md`
- 更新 `docs/index.md`，讓人類入口現在能直接導向 thesis surface
- 更新 `mkdocs.yml`，讓文件站導覽正式包含 Thesis 區
- 這次整理後的分工變成：
  - `current/` = 現在狀態
  - `decisions/` = 正式決策
  - `history/` = 工作過程
  - `thesis/` = 論文材料整理面

### Monitoring artifact freshness 規則補強

- 這輪把一次流程上的 miss 補成明文規則：如果某個 monitoring artifact 已經影響 `Prep Gate`、gate truth、queue/status/handoff framing，就不能只留在 backlog 或 status prose
- 更新 `.agents/roles/reviewer.md`
  - reviewer 現在需要檢查被拿來當 current truth 的 monitoring artifact 是否夠新
  - 如果 stale artifact 已經開始影響 prep-exit 或 queue/status 判斷，必須要求 refresh path 或升格成 active same-phase work
- 更新 `.agents/roles/idea-desk.md`
  - idea-desk 現在要辨認「保持 monitoring evidence 新鮮」是不是其實已經是缺失的執行項，而不是單純新想法
  - 若它已影響 gate truth，預設不應只留在 backlog/status
- 更新 `.agents/runbooks/autopilot.md` 與 `.agents/runbooks/reviewer-handoff.md`
  - direct rerun 和 saved artifact 分岔時，不能再把舊 snapshot 當 current truth
  - stale monitoring artifact 若開始影響 phase/gate framing，就應視為 active same-phase work
- 同步更新 `.agents/runbooks/session-prompts.md`
  - reviewer heartbeat prompt 與 idea-desk opening prompt 現在都明確要求處理這種 freshness drift
