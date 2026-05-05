# Now

最後更新：`2026-05-06`

這份文件只放短期施工焦點。

它不是：

- roadmap：產品主線看 `docs/planning/roadmap.md`。
- current truth：目前完整狀態看 `docs/current.md`。
- worklog：流水帳看 `docs/records/worklog.md`。

目前 `now.md` 的用途是：記錄 Goal 1 engineering baseline 的 closure 狀態、剩餘不能宣稱的事，
以及下一輪應優先處理的產品硬化方向。

## 目前位置

文件設計與 Goal 1 baseline 已進入可交接狀態：

- `docs/planning/roadmap.md` 已重寫為成品主線。
- `docs/target/data_interpretation_system.md` 已定義資料解讀終局設計。
- `docs/target/agent.md` 已定義 agent control loop、Verification Layer、Autonomy Policy /
  Decision Boundary 和成熟 tool taxonomy。
- `docs/target/architecture.md` 已把 Data Interpretation command surface、capability policy
  和 autonomy decision 寫成理想架構。
- `docs/validation/thesis_protocol.md` 已校正 thesis 主 evidence：tool-call accuracy，不是
  EEG training accuracy。
- Goal 1 長跑 runbook 已建立：`artifacts/goal/goal-1-product-autopilot.md`。

目前實作狀態要保守判斷：

- `ApplicationService / Command API` baseline 已存在，可作為後續重構骨架。
- 最新 backend cleanup 已把 Data Interpretation scan / preview / validate / apply / recipe lifecycle
  從 `ApplicationService` 拆到 `DataInterpretationCommandService`，並把 reviewed metadata /
  label carrier side effects 拆到 `DataInterpretationApplyService`；`ApplicationService` 仍是
  dispatch / capability-confirmation gate / result envelope。這是第一個 god-object cleanup slice，
  不代表 backend architecture 已全面完成。
- 下一個 cleanup slice 已把 `evaluate`、`visualize`、`saliency` 和 confirmed `apply_montage`
  拆到 `AnalysisCommandService`；analysis / visualization readiness 不再直接堆在
  `ApplicationService`。
- 最新 cleanup slice 已把 `configure_training`、`train`、`stop_training`、
  `clear_training_history` 和 reset-time training config clear 拆到
  `TrainingCommandService`；training lifecycle / option snapshot 不再直接堆在
  `ApplicationService`。
- 最新 dataset cleanup slice 已把 `generate_dataset`、`clear_datasets`、split config、
  split audit、rollback 和 dataset split summary 拆到 `DatasetGenerationCommandService`。
- 最新 lifecycle cleanup slice 已把 `reset_preprocess`、`reset_session`、`new_session`、
  downstream rollback 和 reset-time dependent-state clear 拆到 `LifecycleCommandService`。
- 最新 compatibility cleanup slice 已把舊 `load_data`、`attach_labels`、`import_labels` 和
  label helper 拆到 `DataCompatibilityCommandService`；它仍是 compatibility path，不是新資料入口
  心智模型。
- 最新 data-table cleanup slice 已把 `update_metadata`、`apply_smart_parse` 和 `remove_files`
  拆到 `DataTableCommandService`；loaded-data table mutation 不再直接堆在 `ApplicationService`。
- 最新 preprocess cleanup slice 已把 preprocessing operations 和 `create_epoch` 拆到
  `PreprocessCommandService`；preprocess / epoch handler 不再直接堆在 `ApplicationService`。
- 最新 state/query cleanup slice 已把 state snapshot assembly 和 `query_state` diagnostics 拆到
  `StateSnapshotService` / `QueryStateCommandService`；`ApplicationService` 主要回到 dispatch /
  gate / result envelope。
- 最新 UI runtime bypass audit 修掉 Dataset direct file import 和 Preprocess reset 的
  service-success fallback：successful `LoadDataCommand` / `ResetPreprocessCommand` 不再再呼叫
  controller mutation，controller fallback 只留給 mock / legacy `None` adapter 情境。
- 最新 legacy raw-loader boundary slice 已把 `DatasetPanel.apply_loader()` 改成 mock /
  legacy-only adapter；real `Study` runtime 會拒絕 direct `loader.apply(study)` 並提示走
  Data Interpretation workflow。`tests/architecture_compliance.py` 也新增 direct loader apply
  guard，避免 UI 新增 raw loader mutation 旁路。
- Reviewer follow-up：UI refresh 目前仍是 controller observer events、panel-local manual
  refresh、tab switch refresh、command-result local refresh 和 ChatPanel / agent Qt signal 的
  混合模式。第一個 cleanup slice 已建立 `refresh_after_command()`，real `Study`
  `execute_application_command()` 會依 `CommandResult.changed_state` 集中刷新 dataset /
  preprocess / training / analysis panels、main info panel 和 assistant backend status；query-only
  evaluation / visualization refresh 關閉二次 refresh，coordinator 也有 re-entrancy guard。這是
  first slice，不是 target closure；下一步仍是 `UI Command Refresh Coordinator + Controller
  Fallback Audit` 的剩餘盤點：把 product runtime controller fallback 與 mock / legacy
  compatibility fallback 明確分離，並持續收斂 observer/manual refresh。2026-05-05 最新 reviewer
  finding 將這列為 follow-up，而不是目前 validation / local eval closure 的中斷點；在
  product-complete 前仍不可宣稱 UI refresh 或 controller fallback 已 fully aligned。
- 最新 Training sidebar refresh cleanup 已把 generate dataset、configure model/settings、start
  training 和 clear history 的 post-command `check_ready_to_train()` 改成 legacy fallback-only；
  real `Study` success path 由 coordinator 依 `CommandResult.changed_state` refresh readiness。
- 最新 Dataset action refresh cleanup 已把 smart parse、batch metadata 和 remove files 的
  post-command `panel.update_panel()` 改成 legacy fallback-only；real `Study` success path 由
  coordinator 依 changed state 刷新 Dataset panel。
- 最新 Data Interpretation apply refresh cleanup 已把 EEG file / folder-BIDS import apply 與 saved
  recipe reload apply 的 service-success `panel.update_panel()` 移除；這些 path 由
  `execute_application_command()` 的 refresh coordinator 依 `ApplyInterpretationCommand`
  `changed_state` 刷新 Dataset panel。
- 最新 label compatibility refresh cleanup 已把 post-load `ImportLabelsCommand` service-success
  refresh 改成 coordinator-owned；只有 mock / legacy `None` fallback 才手動呼叫
  `panel.update_panel()`。這不改變它作為 compatibility path 的產品定位。
- 最新 direct load compatibility refresh cleanup 已把 Data Interpretation unavailable 時的
  `LoadDataCommand` service-success `panel.update_panel()` 移除；controller import fallback 仍只允許
  mock / legacy `None` helper path。
- 最新 Dataset sidebar refresh cleanup 已把 channel selection 與 clear dataset service-success
  `panel.update_panel()` 移除；mock / legacy `None` fallback 才手動刷新。
- 最新 Dataset inline metadata refresh cleanup 已把 subject/session inline edit 的
  `UpdateMetadataCommand` service-success `update_panel()` 移除；mock / legacy `None` fallback 才
  手動刷新。
- 最新 Preprocess sidebar refresh cleanup 已把 filter / resample / rereference / normalize /
  epoch / reset service-success `notify_update()` / `update_info_panel()` 移除；mock / legacy
  `None` fallback 才手動刷新。
- 最新 Visualization control sidebar refresh cleanup 已把 montage / saliency service-success
  `on_update()` 移除；saliency mock / legacy `None` fallback 才手動刷新。
- 最新 post-command refresh architecture guard 已寫進 `tests/architecture_compliance.py`：UI action
  在 service-backed `execute_application_command()` 後不可再直接呼叫 local refresh method；只允許
  explicit `refresh=False` query path 或 failure / legacy fallback branch。這能防止剛清掉的
  duplicated service-success refresh 回流，但不代表 observer/manual/tab-switch refresh 已全部收斂。
- 最新 post-command legacy refresh guard hardening 已區分 `result.failed` 和 `result is None`：
  failure branch 仍可做 UI restore，missing-result compatibility branch 不可直接呼叫 local refresh
  method，必須走 explicit legacy-result helper。
- 最新 tab-switch refresh cleanup 已把 `MainWindow.switch_page()` 的 hard-coded panel refresh mapping
  移到 `refresh_after_navigation()`；navigation refresh scope 現在也由
  `XBrainLab.ui.refresh_coordinator` 定義。最新 follow-up 也把 navigation shared-status refresh
  補進 coordinator：tab switch 會刷新 selected panel、aggregate info panel 和 assistant backend
  status。最新 navigation guard slice 又把 same-main-window re-entrancy guard 補到
  `refresh_after_navigation()`。這是小切片，還不代表 observer / callback refresh 已收斂。
- 最新 observer refresh cleanup 已把 Dataset / Preprocess / Training / Evaluation / Visualization
  的單純 observer `event -> update_panel()` bridge 改成 `refresh_from_observer()`，再委派
  `refresh_after_observer()`；simple observer refresh 現在會刷新事件來源 panel、aggregate info
  panel 和 assistant backend status。callback-specific handlers 仍保留，例如 import-finished、
  TrainingPanel start/stop 和 live training update loop。
- 最新 Dataset import-finished callback cleanup 已把 success refresh 移回 `data_changed`
  simple refresh bridge；`import_finished` callback 只保留 warnings，避免 legacy controller import
  成功時二次刷新 Dataset panel。
- 最新 duplicate observer cleanup 已移除 PreprocessPanel / TrainingPanel 對 dataset
  `import_finished` 的 simple refresh listener；legacy import success refresh 只由 dataset
  `data_changed` observer 擁有。
- 最新 InfoPanelService duplicate refresh cleanup 已移除 dataset `import_finished` bridge；aggregate
  info panel 的成功資料變更 refresh 由 `data_changed` / `preprocess_changed` 擁有。
- 最新 import-finished observer guard 已寫進 `tests/architecture_compliance.py`：新的
  `_create_refresh_bridge(..., "import_finished")` 或 direct `QtObserverBridge(...,
  "import_finished", ...)` 會 fail；`import_finished` 只能透過 named callback handler 處理
  warnings / event-specific behavior。
- 最新 observer refresh helper cleanup 已新增 `BasePanel._create_refresh_bridge()`，並把 Dataset /
  Preprocess / Training / Evaluation / Visualization 的 simple observer refresh call sites 改用
  這個 helper。這是 maintainability cleanup，仍不代表 UI refresh 已完全 command-driven。
- 最新 observer event-scope cleanup 已讓 `data_changed` / `preprocess_changed` 使用 coordinator
  changed-state scope：DatasetPanel owner bridge owns `data_changed` downstream refresh，
  PreprocessPanel owner bridge owns `preprocess_changed` downstream refresh；其他同事件 subscriber
  no-op，避免同一 backend observer event 重複刷新整組 panels。後續同 slice 也把
  `training_started` / `training_stopped` / `config_changed` / `history_cleared` 交給 TrainingPanel
  owner callback 觸發 Training / Evaluation / Visualization scope。
- 最新 visualization observer cleanup 已把 `montage_changed` / `saliency_changed` 納入同一套
  coordinator-owned scope；VisualizationPanel 是 owner，helper / secondary context 不再刷新錯誤 panel。
- 最新 shared info refresh cleanup 修正了 `MainWindow.update_info_panel()`：refresh coordinator 的
  shared info refresh 現在會呼叫 `InfoPanelService.notify_all()`，更新所有已註冊 aggregate info panels。
- 最新 Aggregate Info query-failure cleanup 也讓 real `Study` `InfoPanelService` 在
  `QueryStateCommand(query="data_lists", include_objects=True)` 失敗時回空 summary 並記 log，不再
  fallback 到 dataset / preprocess controller list reads 顯示 stale truth。
- 最新 Preprocess compatibility refresh cleanup 把 epoch / reset 的 mock-legacy shared status
  fallback 改走 `refresh_shared_status()`，避免只刷新 aggregate info 而漏掉 assistant backend status。
- 最新 downstream refresh coordinator cleanup 已讓 `training_changed` 刷新 Evaluation /
  Visualization readiness、`epoch_changed` 刷新 Visualization readiness、`evaluation_changed`
  也刷新 Visualization readiness。這把一部分 analysis panel readiness 從 observer-only 補刷新
  收回 `CommandResult.changed_state` scope。
- 最新 TrainingPanel high-level callback cleanup 已讓 `training_started`、`training_stopped`、
  `config_changed` 和 `history_cleared` 在各自 event-specific UI 更新後刷新 aggregate info panel
  和 assistant backend status；`training_updated` 仍保留為 high-frequency live update path，不走
  shared status refresh。
- 最新 observer refresh architecture guard 已寫進 `tests/architecture_compliance.py`：新增的
  `_create_bridge(..., self.update_panel)` 或 direct
  `_create_bridge(..., self.refresh_from_observer)` 都會 fail；simple refresh 要走
  `_create_refresh_bridge()`，event-specific behavior 要用 named callback handler。
- 最新 Training sidebar fallback audit slice 已建立 `run_legacy_controller_fallback()`，並把 split
  cleanup / generate dataset、model selection、training settings、start / stop training 和 clear
  history 的 controller fallback 改成 mock / legacy non-`Study` only。real `Study` context 若
  command helper 意外回 `None`，會拒絕 fallback。
- 最新 Training model-selection cleanup 又把 service-success branch 從 stale controller echo 裡拿出來：
  `ConfigureTrainingCommand` 成功後不再回讀 `TrainingController.get_model_holder()` 才決定是否
  顯示 success；controller verification 只留在 explicit mock / legacy fallback branch。
- 最新 architecture guard follow-up 已把這條 pattern 寫入 `tests/architecture_compliance.py`，
  防止 service-backed success path 在 `execute_application_command()` 後用 controller echo
  重新判定 command success。
- 最新 Training split cleanup 又把 existing-dataset replacement preflight 收回 backend
  capability truth：real `Study` path 不再依賴 stale `TrainingController.has_datasets()` /
  `get_trainer()` 來決定是否要先確認並送 `ClearDatasetsCommand`。
- 最新 Training split dialog context cleanup 新增
  `QueryStateCommand(query="dataset_generation_context", include_objects=True)`；real `Study`
  `DataSplittingDialog` 初始化使用 service-backed epoch/generator context，stale
  `TrainingController.get_epoch_data()` / `get_dataset_generator()` 只留在 query unavailable 的
  mock / legacy dialog fallback。
- 最新 Data Splitting preview thread cleanup 讓 preview restart / dialog close 會 interrupt
  active `DatasetGenerator` 並 short-join preview worker；這是 focused lifecycle smoke，不是
  long-running dataset-generation soak test。
- 最新 local model downloader lifecycle cleanup 讓 `DownloadWorker` 在 terminal queue message 後
  join subprocess，cancel path 使用 bounded terminate / kill join，並讓 AI Assistant settings
  dialog teardown 走 bounded `ModelDownloader.shutdown()`；這降低關閉下載視窗後 QThread /
  subprocess 殘留風險。這仍只是 focused lifecycle smoke，不是長時間 local model soak。
- 最新 local runtime shutdown cleanup 讓 `LocalBackend.unload()` 釋放 model / tokenizer 並在 CUDA
  可用時清 cache；`LLMEngine.close()` 會卸載 cached backend；`AgentWorker.shutdown()` 會停止
  timeout timer、bounded interrupt / wait generation thread，並在 controller close 時執行。這是
  assistant lifecycle resource cleanup，不是 GPU leak-proof soak。
- 最新 training lifecycle cleanup 讓 `Trainer.clean(force_update=True)` 對 running job 設 interrupt
  後 bounded join background thread；若 training thread 未停止會 raise，讓
  `TrainingManager.clean_trainer()` 保留 trainer handle，避免失去後續取消 / status 查詢入口。
  這是 thread-handle safety guard，不是 long-running training soak。
- 最新 Start Training cleanup 又把 start gate 收回 backend `train` capability truth：capability
  enabled 時不再因 stale `TrainingController.is_training()` 跳過 `TrainCommand`。
- 最新 architecture guard follow-up 已把 pre-command stale readiness pattern 納入
  `tests/architecture_compliance.py`：有 capability surface 的 UI command path 不可再用
  `controller.is_training()`、`has_datasets()`、`get_trainer()` gating，除非在 explicit
  `capability is None` legacy branch。最新 extension 也覆蓋 `validate_ready()`、`has_model()`、
  `has_training_option()`；`TrainingSidebar.check_ready_to_train()` 已改成 explicit
  service-capability / no-capability legacy branch。
- 最新 Training settings cleanup 也讓 settings dialog defaults 先走
  `QueryStateCommand(query="state")` 的 `state.training.training_option`；stale
  `TrainingController.get_training_option()` 只留在 query unavailable 的 mock / legacy path。
- 最新 Training history cleanup 新增 `QueryStateCommand(query="training_history",
  include_objects=True)`；real `Study` `TrainingPanel.update_loop()` 會用 service-backed
  history rows 更新 table / plot selection，不再從 stale injected
  `TrainingController.get_formatted_history()` 讀 history。controller formatted-history read
  只留在 query unavailable 的 mock / legacy path。
- 最新 Dataset sidebar render cleanup 也把 `is_locked()` / `has_data()` 納入同一 guard：
  有 backend capability 時，button state / tooltip 不再先讀 stale controller lock/data state；
  legacy lock/data reads 只留在 explicit no-capability branch。
- 最新 Preprocess sidebar render cleanup 也把 `update_sidebar()` 的 epoched/lock state 收回
  backend capability surface：有 `preprocess` / `create_epoch` capability 時不再讀 stale
  `PreprocessController.get_preprocessed_data_list()`；該 controller read 只留在 no-capability
  mock / legacy render branch，並已納入 architecture compliance guard。
- 最新 Dataset smart-parse cleanup 也讓 parser dialog file list 先走
  `QueryStateCommand(query="state")` 的 `state.raw.files`；stale
  `DatasetController.get_filenames()` 只留在 query unavailable 的 mock / legacy fallback helper。
- 最新 Evaluation panel query cleanup 已讓 real `Study` `EvaluateCommand` result gate display：
  evaluation blocked / unavailable 時不再讀 stale injected controller plans，而是顯示
  `No Data Available`。最新 object-payload follow-up 也讓 successful
  `EvaluateCommand(include_objects=True)` 攜帶 plan objects、pooled metrics 和 model summaries；
  real `Study` Evaluation panel 有 service payload 時不再回讀 stale injected
  `EvaluationController.get_plans()` / `get_pooled_eval_result()` /
  `get_model_summary_str()`。`include_objects` 是 UI-only，automation / MCP `evaluate` schema
  不暴露也不接受它。
- 最新 Visualization panel query cleanup 已讓 real `Study` `VisualizeCommand` result gate controls /
  render：visualization blocked / unavailable 時不再讀 stale injected controller trainers，而是保留
  `Select a plan` 並顯示 user-facing readiness message。最新 object-payload follow-up 也讓
  successful `VisualizeCommand(include_objects=True)` 攜帶 trainer objects 和 averaged records；
  real `Study` Visualization panel 有 service payload 時不再回讀 stale injected
  `VisualizationController.get_trainers()` / `get_averaged_record()`。`include_objects` 是
  UI-only，automation / MCP `visualize` schema 不暴露也不接受它。這仍不是 saliency/canvas
  screenshot acceptance。
- 最新 Visualization sidebar export cleanup 也讓 `Export Saliency` 先走 readonly
  `SaliencyCommand` gate；saliency output unavailable 時不再讀 stale trainer list 開 export dialog。
- 最新 Visualization export trainer cleanup 又讓 saliency 可匯出時改用
  `VisualizeCommand(include_objects=True)` 的 service-backed `trainer_objects`；real `Study`
  export dialog 不再從 `panel.get_trainers()` / `VisualizationController.get_trainers()` 取 stale
  trainer list，controller read 只留在 query unavailable 的 mock / legacy fallback helper。
- 最新 Visualization saliency settings cleanup 也讓 settings dialog defaults 先走 readonly
  `SaliencyCommand` summary diagnostics；stale `VisualizationController.get_saliency_params()`
  只留在 query unavailable 的 mock / legacy fallback helper。
- 最新 Visualization montage setup cleanup 也讓 channel-name dialog defaults 先走
  `QueryStateCommand(query="state")` 的 `state.epoch.channel_names`；stale
  `VisualizationController.get_channel_names()` 只留在 query unavailable 的 mock / legacy
  fallback helper。
- 最新 Preprocess panel render cleanup 也讓 history / preview / plotter refresh 先走
  `QueryStateCommand(query="data_lists", include_objects=True)`；real `Study`
  `PreprocessPanel.update_panel()` 不再直接讀 stale
  `PreprocessController.get_preprocessed_data_list()`。
- 最新 Dataset table render cleanup 也讓 `DatasetPanel.update_panel()` 先走
  `QueryStateCommand(query="data_lists", include_objects=True)`；real `Study` table rows 不再直接讀
  stale `DatasetController.get_loaded_data_list()`。
- 最新 Preprocess epoching cleanup 也把 epoch dialog gating 收回 `create_epoch` capability：
  `create_epoch` enabled 時不再被 separate `preprocess` capability blocked reason 誤擋，
  legacy `check_lock()` / `check_data_loaded()` 只留給 no-capability path。最新 guard follow-up
  又讓 epoch dialog data list 先走 `QueryStateCommand(query="data_lists", include_objects=True)`；
  `PreprocessController.get_preprocessed_data_list()` 只留在 no-capability mock / legacy path。
- 最新 Preprocess sidebar fallback audit slice 已把 filter / resample / rereference / normalize /
  epoch / reset 的 controller fallback 改成同一個 mock / legacy-only helper。剩餘 Dataset /
  Visualization / AgentManager fallback 還要沿同一模式盤點。
- 最新 Dataset fallback audit slice 已把 metadata edit / batch metadata、smart parse、remove files、
  direct file import、clear dataset、channel selection 和 post-load label compatibility fallback 改成
  同一個 mock / legacy-only helper。最新 file-import boundary follow-up 也讓 `scan_source`
  capability 存在時不再從 Data Interpretation unavailable 旁路到 `LoadDataCommand` / legacy
  `import_files`。剩餘 Visualization / AgentManager fallback 還要沿同一模式盤點。
- 最新 Visualization / AgentManager fallback audit slice 已把 saliency settings、Visualization
  sidebar `Set Montage` 和 assistant montage confirmation fallback 改成同一個 mock / legacy-only
  helper。剩餘 `result is None` path 主要是
  Data Interpretation service-unavailable critical / false return 或已顯式 helper fallback。
- 最新 montage argument cleanup slice 又把 AgentManager 與 Visualization sidebar 的 confirmed
  positions 正規化收斂到同一 helper；dialog 回傳 list / dict / numpy-like coordinates 時，command
  path 會得到 JSON-safe float tuples，malformed vectors 會在 UI adapter boundary 被擋下。
- 最新 architecture guard slice 已把這條 boundary 寫進 `tests/architecture_compliance.py`：UI 的
  `result is None` branch 若直接呼叫 controller mutation，會 fail；mock / legacy fallback 必須透過
  `run_legacy_controller_fallback()`。
- 最新 direct controller mutation guard 又把 UI product path 直接呼叫
  `controller.update_metadata()` / `controller.start_training()` 這類 mutating controller method
  擋住；只有 `run_legacy_controller_fallback()` 或明確 legacy / fallback helper 可以保留 controller
  mutation。這是 fallback audit guardrail，不是 controller 退場完成。
- 後續 Training sidebar bypass cleanup 修掉重新 split 前清 datasets 和 Clear History 的 direct
  controller mutation；destructive cleanup 會走 `ClearDatasetsCommand` /
  `ClearTrainingHistoryCommand`，且 Clear History 現在有 user confirmation。
- 最新 UI autonomy cleanup 讓 Training sidebar `Start Training` button 在 backend `train`
  capability 需要 confirmation 時先顯示 long-running confirmation；拒絕時不執行 command，service
  success path 不再 fallback 到 controller。Automated Qt replay artifact：
  `artifacts/ui/training-start-confirmation/`。
- 最新 backend command-gate cleanup 已把 long-running `train` confirmation 下沉到 Command API。
  `TrainCommand(confirmed=False)` 在 backend ready 時會回 `confirmation_required` 且不啟動訓練；
  backend unready 時仍先回 precondition blocked reason。UI / agent confirmation 後會注入
  `confirmed=True`。
- 最新 Data Interpretation boundary cleanup 已把 format capability taxonomy 抽到
  `data_interpretation_formats.py`，讓 scanner / candidate lifecycle 與 format matrix 邊界分離。
- 後續 Data Interpretation boundary cleanup 已把 metadata resolution / BIDS summary / recipe
  metadata rehydration 抽到 `data_interpretation_metadata.py`；下一步可繼續拆 recipe
  serialization 或 label carrier planner。
- 最新 Data Interpretation boundary cleanup 已把 recipe serialization / rehydration 抽到
  `data_interpretation_recipe.py`；下一步可聚焦 label carrier planner 或 preview / validator。
- 最新 Data Interpretation boundary cleanup 已把 label carrier planner 抽到
  `data_interpretation_label_carriers.py`。
- 最新 Data Interpretation boundary cleanup 已把 preview payload builder 和 safe /
  needs-confirmation / blocked validator 抽到 `data_interpretation_review.py`；下一步可聚焦
  metadata override helper 或 scanner/candidate builder。
- 最新 Data Interpretation boundary cleanup 已把 source scanner / source classification 抽到
  `data_interpretation_scan.py`；下一步可聚焦 candidate builder 或 metadata override helper。
- 最新 Data Interpretation boundary cleanup 已把 candidate builder / metadata override /
  event-class choice mapping 抽到 `data_interpretation_candidate.py`；`data_interpretation.py`
  目前主要只保留 shared decision enum、applied lifecycle dataclass 和 compatibility re-exports。
- 最新 Data Interpretation session-state cleanup 已把 lifecycle stores、latest-id resolver、
  snapshot assembly、clear 和 post-load label-import recipe recording 抽到
  `data_interpretation_state.py`；`DataInterpretationCommandService` 目前主要保留 command handler
  orchestration。
- 最新 agent tool-surface cleanup 已把 `load_data` / `attach_labels` 從 Empty / Data Loaded /
  Preprocessed stage prompt 和 primary tool exposure 移除；Context Assembler 現在用 backend
  capability policy 與 stage allowlist 取交集，避免 compatibility tool 被 policy 重新帶回主
  prompt。legacy tools 仍保留在 schema taxonomy / parser / verification 裡作 compatibility
  path，不是新 agent 資料入口主語言。
- 最新 RAG prompt cleanup 已讓 `RAGIndexer`、`BM25Index` 和 `RAGRetriever` 過濾含
  `load_data` / `attach_labels` / `import_labels` 的 legacy examples；這同時保護新建 RAG
  index 和已存在的舊 local Qdrant collection。
- 最新 ChatPanel product-status cleanup 已把 assistant empty-state / next-step status 從 visible
  legacy `Load EEG data` / `Attach labels` 收斂成 `Scan data source`，並在 ChatPanel status
  rendering 層過濾 `load_data` / `attach_labels` / `import_labels` compatibility commands。
- 最新 automation / MCP schema cleanup 已把 `load_data` / `attach_labels` / `import_labels`
  在 `AutomationCommandSpec` 和 MCP `tools/list` metadata 中標為 legacy compatibility、非
  primary workflow，並提供 Data Interpretation preferred commands；MCP/headless client 仍可呼叫
  相容工具，但 schema 不再把它們包成新資料入口主線。
- 最新 agent/headless remap schema cleanup 已把 Data Interpretation preview choices schema 抽成
  `data_interpretation_choice_schema.py`，讓 agent `preview_interpretation` tool definition、
  headless `command_specs()` 和 MCP `tools/list` 共用 `choices.eeg_file_remap` /
  `choices.label_carrier_remap` / `label_carrier_choices` / `metadata_overrides` contract。
  Tool-call normalizer / prompt 現在可把 recipe reload remap request 收斂到
  `preview_interpretation(choices=...)`，缺 replacement 時要求 clarification，不改走 legacy
  load / attach labels。
- 最新 agent execution boundary cleanup 已讓 real `Study` mapped workflow tools 在缺少必要參數而
  不能組成 ApplicationService command 時，回 structured input failure 並避免 legacy real-tool
  fallback。這補上 runtime safety；同日後續 release / thesis gate 已刷新 deterministic、primary
  local 和 fallback local `121` case artifacts，三者仍為 `121 / 121`。fallback full x3
  resource artifact 顯示 RTX 5070 Ti 16GB 幾乎滿載，後續小修不可預設重跑 fallback x3。
- Data Interpretation 的 backend command baseline 已新增。
- agent tool surface 已暴露 Data Interpretation tools，並能使用 backend dynamic confirmation
  boundary。
- Dataset panel 的主要資料入口已從 `Import Data` 改為 `Interpret Data Source`，並走
  scan -> preview -> validate -> confirm/apply；preview dialog 現在提供 apply 後保存 recipe
  的選項，並透過 `SaveInterpretationRecipeCommand` 寫入 recipe。舊 label import 入口已改成
  `Add Labels to Loaded Data`，定位為 service-backed compatibility path；label import 成功後
  會寫入 applied interpretation 的 label carrier / class map / selected event / recipe trace，
  UI 也可提示保存更新後 recipe。
- Dataset sidebar 現在也明確提供 `Interpret Folder / BIDS` 和 `Reload Import Recipe` 入口；
  folder/BIDS root 與 saved recipe 不再隱含在 file picker 裡。Artifact：
  `artifacts/ui/data-source-entry-options/`。
- Data Interpretation wizard 的 label carrier review cells 已使用 selector controls；最新 slice
  也把 event role rows 改成 selector，不再要求使用者手打 role text。Replay artifact 現在保存
  `event_rows`，可見 `trial_type -> Class cue`，recipe choices 仍保存 backend value
  `class cue`。
- 最新 event display polish 已把 visible `label_carrier` / `trial_type` event-role item
  humanized 成 `Label carrier` / `Trial type`，backend choices 仍保存原始 key。Label / event
  group title 也改成 `Label and Event Interpretation`，recipe trace 留在 `Review Summary`。
- 最新 wizard selector polish 也把 label carrier combo 顯示從 raw `trial_type` / `onset` 改成
  `Trial type` / `Onset`，並把 `Review Summary` alternate row contrast 再降低；recipe choices
  仍保存 raw source column value。後續欄位權重 polish 又讓 label-carrier `Format` 欄在
  product-width dialog 中完整顯示 `BIDS events`，不再被擠成 `BIDS ...`。
- 最新 decision-copy polish 已把 wizard 頂部狀態從 `Validation needs confirmation...` 改成
  `Review and confirm these choices before applying.` / `Ready to apply.` / replacement-file
  guidance，減少 backend wording 暴露。
- 最新 Dataset / Data Interpretation table-fit slice 已把 Dataset 主表和 wizard tree table 改成依
  viewport 等比例重算欄寬：整體欄位會填滿主 panel，文字用 elide 處理，不再用高對比
  `Review Summary` 條紋或綠色 success 語意顯示 external labels。Artifact：
  `artifacts/ui/data-interpretation-preview.png`、`data-interpretation-remap.png`、
  `data-interpretation-applied.png`。最新 artifact refresh 又把 dialog table geometry 寫進
  `artifacts/ui/data-interpretation-replay.json`，包含 preview/remap metadata、label carrier、event
  role 和 review summary 的 `header_length == viewport_width`、`horizontal_scrollbar_max=0`、
  `column_widths` 和 `text_elide_mode` evidence。後續 Dataset table fill guard 又把
  `right_gap_to_boundary=0` 寫進 replay / walkthrough artifact，確認載入資料後 table widget
  本身貼齊 sidebar，不只是欄位填滿一個內縮 viewport。
- 最新 human-like walkthrough refresh 也把 table geometry 納入 top-level UI quality gate：
  `artifacts/ui/human-like-walkthrough/human-like-walkthrough.json` 目前 `status=passed`，
  table geometry review 檢查 `15` 個 table/tree widgets、`0` findings；載入資料後 Dataset
  table 記錄 `header_length=509`、`viewport_width=510`、`horizontal_scrollbar_max=0`。
- Recipe reload 現在不只重掃 source path：`ReloadInterpretationRecipeCommand` 會把 saved
  selected files、metadata overrides、label carrier choices、event roles 和 class map rehydrated
  回 candidate `choices` 後再 preview / validate。Human-like walkthrough reload command result
  可見 `choices:event_roles` / `choices:label_carriers` trace；`07-recipe-reloaded.png` 現在是
  reload preview dialog，notes 含 `Reloaded recipe / Reapplied` row。完整 user-facing recipe diff
  UI 仍未完成。
- `apply_interpretation` capability 現在會套用 raw-edit blockers；已有 epoch / dataset /
  trainer 或 locked raw data 時，agent / MCP 不能繞過 UI lock 直接 apply 新資料，必須先 reset
  或 new session。
- headless / MCP-ready automation adapter 已新增：
  `backend.application.automation` 產生 command schema / MCP-shaped tool specs，並把 JSON
  payload 轉回 typed `ApplicationService` command。
- stdio MCP server baseline 已新增：
  `XBrainLab.mcp.server` / `scripts/dev/run_mcp_server.py` 支援 MCP `initialize`、
  `tools/list`、`tools/call`，並在同一個 `ApplicationService` session 中執行工具。
- deterministic engineering eval 已擴到 `54` cases，包含 `15` 個 multi-turn cases 和
  `34 / 54` negative / blocked / confirmation / missing-input / recovery cases。
- 真 local LLM tool-call runner 已新增，使用同一份 `54` cases / scorer 接 primary /
  fallback 模型 raw output 並各重跑 `3` 次。前一輪 full rerun：
  - primary `microsoft/Phi-4-mini-instruct`：`53 / 54` pass。
  - fallback `microsoft/Phi-3.5-mini-instruct`：`53 / 54` pass。
  這是 engineering evidence，不是 thesis-ready accuracy；case 數仍不足 `100`，且仍有
  bandpass-vs-standard preprocess 語意 failure。
- `VerificationLayer` 已補 registered tool schema / required / type / enum 檢查，controller
  會在 execution 前攔可解析但不可執行的 tool JSON。
- local assistant guardrail slice 已補 placeholder path rejection、requested-intent boundary、
  parser 對 top-level array / OpenAI function-call shape 的支援、以及 standard preprocess /
  dataset split prompt/schema 規則。後續 normalizer slice 已把 command-only JSON、bare tool
  name、latest-turn substitute、query_state、BIDS hint、subject override、placeholder prose path
  和 result interpretation 接到 verifier / ApplicationService 語意。探索性 smoke artifact：
  - primary guardrail smoke：`6 / 6` pass。
  - fallback guardrail smoke：`6 / 6` pass。
  前一輪正式 `54` cases x `3` full rerun：
  - primary `microsoft/Phi-4-mini-instruct`：`53 / 54` pass。
  - fallback `microsoft/Phi-3.5-mini-instruct`：`53 / 54` pass。
  這仍不是 thesis-ready；case 數不足 `100`，且剩餘 bandpass-vs-standard preprocess 語意
  failure。
- 最新 tool-call best-practices / thesis-candidate slice 已把同一 scorer 擴到 `118` cases，
  並用 cached primary / fallback local models 各重跑 `3` 次：
  - deterministic baseline：`118 / 118` pass。
  - primary `microsoft/Phi-4-mini-instruct`：`118 / 118` pass。
  - fallback `microsoft/Phi-3.5-mini-instruct`：`118 / 118` pass。
  - runtime classification：primary / fallback 都是 `gpu-ready`；cache `15.34 GB`；no download。
  - dashboard：`artifacts/agent_evals/dashboard.md`，含 model comparison、case family pass
    rate、metric pass rate、failure taxonomy、worst cases、artifact paths 和 thesis claim boundary。
  - scorer 已收緊 blocked-intent handling：direct blocked command 可被 verifier / capability
    policy 擋下；blocked state 下改叫 scan / reset / configure 等替代 tool 會算 failure。
  這支撐 thesis-candidate tool-call benchmark evidence；仍不能取代 ChatPanel walkthrough、
  Windows launcher walkthrough、MCP HTTP / long-running tool calls、human desktop acceptance 或成熟
  import wizard 驗收。
- 2026-05-05 follow-up 已把 downstream-locked `apply_interpretation` wrong-tool temptation case
  納入 deterministic、primary 和 fallback local rerun；dashboard 已同步刷新。
- 2026-05-05 remap schema follow-up 又把 suite 擴到 `121` cases：recipe reload EEG file
  remap、label carrier remap、missing remap target clarification 全部進
  `artifacts/agent_evals/latest.json` / `.md`，deterministic `121 / 121` x `3` pass。primary /
  fallback 真 local model也已用 cached non-China models 各重跑 `3` 次，兩者都是 `121 / 121`；
  dashboard 已刷新為 deterministic / primary / fallback 同套 cases。
- Tool-call eval gate 已分層：fast dev gate 只跑 deterministic changed / failed cases、repeat `1`
  且不跑 fallback；candidate gate 才跑 primary affected families、repeat `1` 或 `2`；release /
  thesis gate 才跑 deterministic full suite、primary full x3、fallback full x3 和 dashboard。
  full local gate 前必須記錄 disk / cache / VRAM preflight；本輪 fallback rerun 的 resource pressure
  已保存到 `artifacts/agent_evals/local-eval-resource-pressure-2026-05-05.*`。
- MCP stdio external-client walkthrough 已新增：
  - `scripts/dev/capture_mcp_stdio_walkthrough.py` 是只依賴 Python standard library 的 client。
  - client 會啟動 prepared XBrainLab runtime 內的 `scripts/dev/run_mcp_server.py`，並保存
    `artifacts/mcp/stdio-walkthrough.json` / `.md`。
  - evidence 覆蓋 `initialize`、`tools/list`、`scan_source`、`preview_interpretation`、
    `validate_interpretation`；tool schema taxonomy 仍來自 ApplicationService automation
    surface。
  - `tools/call` structured result 現在包含 `adapter` boundary：`mode=headless_mcp_stdio`、
    `transport=stdio`、stable `session_id`、`ui_refresh_supported=False`，明確表示 stdio MCP
    是 headless ApplicationService session，不刷新 desktop UI。
  - `train` over stdio 現在先保留 backend readiness：unready training 會回 shared
    precondition reason，不會被 job-boundary error 遮掉；只有 backend-ready / enabled 的
    long-running `train` 才回 structured `long_running_job_required`。artifact 會標出
    `train result boundary` 和是否真的到達 job boundary。
  - 這支撐 external stdio client path，不代表 Windows release registration、HTTP transport
    或 long-running training through MCP 已完成。
- MCP Inspector-style release config baseline 已新增：
  - `artifacts/mcp/xbrainlab-mcp.json` 是標準 `mcpServers` / `stdio` config，含
    `default-server` 和 `xbrainlab-windows-wsl` entries。
  - `scripts/dev/run_mcp_server_for_client.sh` 會切回 prepared repo runtime，再啟動
    `scripts/dev/run_mcp_server.py`。
  - `scripts/dev/write_mcp_client_config.py` 可重生 config / Markdown，並驗證 client config
    沒有把 Python / EEG / PyQt / PyTorch dependencies 放到 client side。
  - integration test 會用 committed config command 重跑 stdio walkthrough。
  - Windows-side official Inspector CLI 已用 `xbrainlab-windows-wsl` entry 跑過
    `tools/list`，artifact 在 `artifacts/mcp/inspector-cli-tools-list.json` / `.md`。
  - 這支撐 Inspector CLI / external client release config baseline；仍不是 HTTP transport 或
    long-running training through MCP。
- MCP Inspector GUI click-through baseline 已新增：
  - script：`scripts/dev/capture_mcp_inspector_gui_walkthrough.py`。
  - artifact：`artifacts/mcp/inspector-gui-walkthrough.json` / `.md` 和
    `artifacts/mcp/inspector-gui-connected.png`。
  - evidence 顯示 official Inspector GUI 透過 `xbrainlab-windows-wsl` entry 連上 `xbrainlab`
    server，`Connect` / `Connected` / `Disconnect` / `Tools` / `List Tools` 可見，並能看到
    `Scan Source`、`Preview Interpretation`、`Validate Interpretation`、`Apply Interpretation`。
  - 這支撐 automated Inspector GUI click-through，不是 human GUI session、full MCP client
    certification、HTTP transport 或 long-running training through MCP。
- Windows launcher automated command walkthrough 已新增：
  - `scripts/dev/capture_windows_launcher_walkthrough.py` 會從 Windows `cmd.exe` 執行 Desktop
    `XBrainLab.cmd` smoke，確認它指向 active repo。
  - 同一 artifact 會從 PowerShell launcher 進 WSL，驗證 stdout / stderr mirror 到 launcher
    output/log。
  - `startup` smoke 經 Windows launcher path 執行 bounded `run.py --model local`，artifact 顯示
    `MainWindow initialized` 和 timeout 後正常收束。
  - 最新 artifact 也會啟用 startup geometry diagnostics，確認 screen count、screen detail、
    splash geometry 和 main-window geometry 都寫進 launcher stdout / log。
  - artifact：`artifacts/launcher/windows-launcher-walkthrough.json` / `.md`。
  - 這支撐 Windows launcher command path，不代表真人 Desktop click-through、packaged release
    approval 或多螢幕實際使用體驗已完成。
- ChatPanel true local-model one-turn walkthrough 已新增：
  - `scripts/dev/capture_chatpanel_local_walkthrough.py` 在 `HF_HUB_OFFLINE=1` /
    `TRANSFORMERS_OFFLINE=1` 下打開真 MainWindow / ChatPanel。
  - prompt 從 UI composer 送出，路徑是 AgentManager -> LLMController -> AgentWorker ->
    LLMEngine local backend。
  - artifact：`artifacts/ui/chatpanel-local-ready.png`、`chatpanel-local-response.png`、
    `chatpanel-local-walkthrough.json` / `.md`。
  - primary `microsoft/Phi-4-mini-instruct` `gpu-ready`、cache `15.34 GB`、visible transcript
    不含 raw tool/debug syntax，UI 回到 idle。
  - 這支撐真 local model 能在 ChatPanel 產生可見回覆；仍不代表 multi-turn tool-command
    workflow、Windows launcher click-through 或長時間 assistant 操作已完成。
- ChatPanel true local-model tool-command walkthrough 已新增：
  - artifact：`artifacts/ui/chatpanel-local-tool/chatpanel-local-ready.png`、
    `artifacts/ui/chatpanel-local-tool/chatpanel-local-response.png`、
    `artifacts/ui/chatpanel-local-tool/chatpanel-local-walkthrough.json` / `.md`。
  - prompt 從 UI composer 要求檢查目前 workflow readiness；local model 實際執行
    `query_state`，artifact 的 `executed_tools` 記錄 `query_state` `ok`。
  - visible transcript 只顯示使用者語言：assistant 回覆 `Application state snapshot ready.`；
    artifact 未出現 raw `Tool Output`、schema 或 traceback，UI 回到 idle。
  - 這支撐單步 tool execution 可以經 ChatPanel 以產品語言回覆；仍不代表 multi-turn
    workflow、長時間 tool-command chain 或 Windows launcher click-through 已完成。
- ChatPanel true local-model two-turn workflow walkthrough 已新增：
  - 首次嘗試暴露真 blocker：`query_state` 成功後，完整 state JSON 被寫回 conversation
    history，第二 turn prompt 約 `10.7k` input tokens，local model timeout。
  - controller 已改成 compact tool-history feedback：下一輪只保留 message、capability、
    `state_summary` 和 small diagnostics，不再餵 full state / raw result。
  - artifact：`artifacts/ui/chatpanel-local-workflow/chatpanel-local-workflow-walkthrough.json` /
    `.md`，含 ready / turn screenshots。
  - evidence 顯示 turn 1 執行 `query_state`，turn 2 在同一 conversation 正常回答 preprocessing
    follow-up，UI idle，visible transcript 無 raw tool/debug syntax。
  - 這支撐 basic multi-turn local ChatPanel continuity；仍不是長時間 tool-command chain、完整
    workflow 自動操作或人工 release walkthrough。
- ChatPanel true local-model Data Interpretation tool-chain walkthrough 已新增：
  - script：`scripts/dev/capture_chatpanel_local_tool_chain_walkthrough.py`。
  - artifact：`artifacts/ui/chatpanel-local-tool-chain/chatpanel-local-tool-chain-walkthrough.json` /
    `.md`，含 ready / turn screenshots。
  - flow：synthetic FIF -> visible ChatPanel prompt -> local model -> `scan_source` ->
    `preview_interpretation` -> `validate_interpretation`，每個 turn 一個 verified
    ApplicationService-backed tool。
  - 首次真跑暴露 blocker：local model 會輸出 `latest_scan_id` / current-style placeholder id，
    使 backend 不能使用 latest scan/candidate state；`tool_call_normalizer` 現在只保留
    backend 真 id 格式 `scan-<n>` / `candidate-<n>`，其他 generated id 移除。
  - 最新 artifact：primary `microsoft/Phi-4-mini-instruct` `gpu-ready`、cache `15.34 GB`、
    三個 expected tools 都是 `ok`，final interpretation state 有 validation decision
    `needs_confirmation`，UI 回到 idle。
  - 這支撐短鏈 Data Interpretation tool-command workflow；仍不是 confirm/apply、preprocess、
    epoch、dataset、training 的長鏈 autonomous workflow，也不是 Windows launcher
    click-through。
- ChatPanel true local-model import-to-dataset pipeline-chain walkthrough 已新增：
  - script：`scripts/dev/capture_chatpanel_local_pipeline_chain_walkthrough.py`。
  - artifact：`artifacts/ui/chatpanel-local-pipeline-chain/chatpanel-local-pipeline-chain-walkthrough.json` /
    `.md`，含 ready / 7 turn screenshots。
  - flow：synthetic FIF -> `scan_source` -> `preview_interpretation` ->
    `validate_interpretation` -> auto-observed `apply_interpretation` confirmation dialog ->
    `apply_standard_preprocess` -> `epoch_data` -> `generate_dataset`。
  - `apply_standard_preprocess` 現在會由 agent application surface 直接建
    `PreprocessCommand(operation=STANDARD)`，不再落回 legacy real-tool string path。
  - 首次真跑被 dataset split audit 擋下：只有 `left` 單一 event 時 3 epochs 會造成 empty
    validation split；修正方式不是放寬 audit，而是讓 `tool_call_normalizer` 可從
    `events left and right` 抽多個 event ids。
  - 最新 artifact：primary `microsoft/Phi-4-mini-instruct` `gpu-ready`、cache `15.34 GB`、
    expected tools 全部 `ok`、confirmation dialog observed `1`、epoch count `6`、dataset
    available `True`、dataset count `1`、UI 回到 idle。
  - 這支撐真 local ChatPanel 可以走到 dataset ready；仍不代表 model selection / training /
    evaluation / saliency 長鏈完成，也不是真人 Windows launcher click-through。
- Agent analysis-tool exposure 已補齊：
  - `evaluate`、`visualize`、`saliency` 現在有 definitions / mock / real tools，並會註冊到
    ChatPanel controller 的 tool registry。
  - `application_surface.py` 會把三個 tool 直接建成 `EvaluateCommand`、`VisualizeCommand`、
    `SaliencyCommand`，回傳 typed `ToolCommandResult`，並受 ApplicationService capability
    policy 控制。
  - `CommandParser` 支援三個 bare tool names；intent mapping 也補上 `evaluate`。
  - 這解除 analysis commands 的 agent 旁路，但仍不代表 ChatPanel dataset -> train ->
    evaluate / visualize / saliency 長鏈已完成。
- ChatPanel true local-model training-readiness boundary walkthrough 已新增：
  - script：`scripts/dev/capture_chatpanel_local_training_readiness_walkthrough.py`。
  - artifact：`artifacts/ui/chatpanel-local-training-readiness/chatpanel-local-training-readiness-walkthrough.json` /
    `.md`，含 ready / 6 turn screenshots。
  - flow：ApplicationService 準備 synthetic dataset-ready state -> visible ChatPanel `set_model` ->
    `configure_training` -> `start_training` confirmation observed/rejected -> `visualize` ->
    `saliency` -> evaluate blocked reason。
  - final state：dataset available、model `EEGNet`、training option present、trainer not created、
    training not running、evaluation unavailable。
  - 這支撐 training high-impact confirmation boundary 和 analysis-readiness tools；仍不代表真
    training completion、evaluation metrics 或 saliency render 完成。
- ChatPanel true local-model controlled tiny training-completion walkthrough 已新增：
  - script：`scripts/dev/capture_chatpanel_local_training_completion_walkthrough.py`。
  - artifact：`artifacts/ui/chatpanel-local-training-completion/chatpanel-local-training-completion-walkthrough.json` /
    `.md`，含 ready / trained / 7 turn screenshots。
  - flow：ApplicationService 準備 training-safe synthetic dataset-ready state -> visible ChatPanel
    `set_model` -> `configure_training` with controlled temp `output_dir` -> observed/approved
    `start_training` confirmation -> wait for 1 epoch CPU training completion -> `evaluate` ->
    `saliency` configure -> `visualize` -> saliency readiness query。
  - final state：dataset available、model `EEGNet`、training option present、trainer present、
    training not running、finished run count `1`、evaluation metrics available、saliency configured /
    available。
  - 同 slice 修正 saliency flat params normalization、`visualization` intent 判斷、saliency
    readiness query stale params cleanup，以及 tiny metrics / missing `torchinfo` UI fallback。
  - 這支撐 true local ChatPanel controlled tiny training completion 和 post-training analysis
    readiness summary；仍不代表完整 saliency / visualization canvas render、真人 Windows launcher
    click-through、MCP HTTP / long-running client workflow 或 mature import wizard label editor 完成。
- MainWindow VisualizationPanel render walkthrough 已新增：
  - script：`scripts/dev/capture_visualization_render_walkthrough.py`。
  - artifact：`artifacts/ui/visualization-render/visualization-render-walkthrough.json` /
    `.md`，含 ready / Saliency Map / Spectrogram / Topographic Map screenshots。
  - flow：ApplicationService 準備 synthetic source -> Data Interpretation apply -> preprocess ->
    epoch -> dataset -> `ConfigureTrainingCommand` -> `SaliencyCommand` -> `ApplyMontageCommand`
    -> 1 epoch CPU `TrainCommand` -> true MainWindow VisualizationPanel render。
  - final evidence：finished runs `1`、metrics available、saliency available、montage available；
    三個 tab 均有 visible canvas、無 error label、axes / rendered image artist。
  - headless/offscreen `3D Plot` tab 現在會顯示 interactive OpenGL desktop session 的 blocked
    reason，artifact 含 `visualization-render-3d-blocked.png`，且 `plotter_created=False`。
  - 這支撐 post-training Matplotlib saliency render UI evidence 和 headless 3D blocked UX；仍不代表
    interactive desktop 3D / PyVista render、ChatPanel UI-routing render、真人 Windows launcher
    click-through、MCP HTTP / long-running client workflow 或 mature import wizard label editor 完成。
- Goal 1 要求的 Data Interpretation baseline 已可走 source -> scan -> preview -> validate ->
  confirm/apply -> recipe，且有 backend non-mocked source -> recipe -> preprocess -> epoch ->
  dataset workflow evidence 和 UI-observable preview / applied artifact。
- Data Interpretation wizard review surface 已硬化：
  - dialog title 改為 `Interpret Data Source`。
  - 可見流程為 `Select source | Scan result | Preview | Confirm | Apply | Save recipe`。
  - 顯示 source/readiness、BIDS status、metadata preview、label/event/recipe trace、
    confirmation 和 save recipe state。
  - warnings、confirmations、blocked reasons、downstream impact 和 format boundaries 已改成
    `Review Summary` table，不再是大段 plain text review dump；Data Interpretation replay JSON
    保存 `review_summary_rows`。
  - Recipe reload preview 現在會把 saved recipe 與重新 scan 的 comparison 顯示為
    `EEG files`、`Label carriers`、`Saved choices` rows，區分 matched / changed，不再只顯示
    一句 `reapplied`。
  - Recipe reload 若發現 saved selected EEG file 不在 current scan 中，validation 會是
    `blocked`，不允許 apply 進入 runtime import failure。
  - Recipe reload 若發現 saved label/event carrier 不在 current scan 中，也會 `blocked`，避免
    recipe replay 靜默丟失 external labels。
  - Backend 已支援 explicit `eeg_file_remap` / `label_carrier_remap`，可把 saved EEG file 或
    saved carrier 映射到 current scan replacement，並沿用原本 metadata / label / anchor / role
    choices；UI selector 已接上，blocked reload dialog 可讓使用者選 replacement，並在 apply 前
    re-preview / re-validate。
  - Agent / headless / MCP schema 也已共用同一份 preview choices contract；assistant 應把 remap
    request 走 `preview_interpretation(choices=...)`，缺 saved/replacement pair 時要求補充。
  - 最新 UI table-fit polish 讓 label / event / recipe trace tables 用 stretch + elide 控制欄寬，
    `Review Summary` 使用較低對比的 dark alternate row；Dataset table 的 `File` 欄承接剩餘寬度
    並填滿主 panel，其他欄保留穩定寬度，避免載入後表格內縮。
  - 最新 confirmation-copy polish 讓底部提示只顯示短 action cue；具體 metadata / label carrier
    confirmation 留在 `Review Summary` rows，避免 raw filename 長句在 dialog 底部重複。
  - Dataset table `Events` 欄現在用 `Events (n)` 表示 recording events、`Labels (n)` 表示外部
    labels；external labels 使用中性文字，不再用綠色表示成功狀態。
  - Dataset sidebar `Channel Selection` 也已改成中性 sidebar action；它會修改資料，不再用
    success-green 表示尚未發生的成功狀態。
  - subject / session / task / run 和 class map review cells 已可產生 dialog `choices`。
  - Dataset action 會在 apply 前用使用者 review choices re-preview / re-validate，再套用新
    candidate。
  - label carrier review rows 現在可審查 / 編輯 label field、MAT variable、anchor、time model
    和 granularity；backend recipe 會保存 `label_carrier_plan`、metadata override、event
    roles、class map 和 recipe trace。
  - label carrier role 和 event role 現在也能在同一 wizard 裡編輯並回寫 recipe choices；
    replay JSON 顯示 `class cue labels` 與 `trial_type -> class cue`。
  - label carrier review cells 已從手打文字升級成 selector controls；UI 顯示 `Seconds` /
    `Trial` / `Class cue labels`，recipe choices 仍保存 backend value。
  - replay artifact `artifacts/ui/data-interpretation-preview.png` 已刷新，JSON 也記錄
    `metadata_overrides` 和 TSV / BIDS-events label carrier choices；backend unit test 也覆蓋
    MAT `classlabel` / `cue_onset` recipe trace。
  - scan / preview 現在會列出 format capability boundaries，覆蓋 GDF、EDF / BDF、EEGLAB、
    BrainVision、MNE FIF、MAT labels、CSV / TSV / BIDS events、TXT labels 和 XDF / LSL；dialog
    `Review Summary` 會顯示 XDF / LSL stream selection 尚未在 wizard 內可用的 blocked reason。
  - Generated Data Interpretation format capability matrix 已新增：
    `scripts/dev/report_data_interpretation_format_matrix.py` 透過 live `ApplicationService`
    command path 產生 `artifacts/data_interpretation/format-capability-matrix.json` / `.md`，
    覆蓋 GDF、EDF、BDF、EEGLAB、BrainVision VHDR / VMRK、MNE FIF、MAT、CSV、TSV、
    BIDS events、TXT 和 XDF / LSL 的 supported / needs-review / context / blocked matrix。
    這是 capability-boundary evidence，不是 XDF parser 或 real-data manual certification。
  - `apply_interpretation` 現在會在單一 EEG + 單一 reviewed timestamp CSV / TSV / BIDS events
    carrier、已確認且 time model 為 seconds / relative time 時，自動套用 external labels，並保存
    `label_apply` diagnostics / `label_import:timestamp:<n>` recipe trace；UI replay JSON 已顯示
    labels applied。
  - 單一 EEG + 單一 reviewed MAT / TXT trial-order sequence carrier + confirmed class map 也會走
    legacy label import，並保存 `label_import:legacy:<n>` recipe trace。
  - shared state snapshot 已同步 import review truth：`ApplicationStateSnapshot.interpretation`、
    `query_state`、automation / MCP envelope 和 agent `query_state` tool surface 現在都會暴露
    `label_carrier_plan`、`format_capabilities`、`event_roles` 和 `class_map`。
  - reviewed timestamp label carriers 已支援安全多檔 mapping：多個 loaded EEG file 若可用唯一
    normalized stem 對應各自的 CSV / TSV / BIDS events carrier，會一次 batch apply；generic
    `events.tsv` 或無法唯一對應時仍 skipped，不自動猜。
  - reviewed MAT / TXT trial-order sequence carriers 也支援安全多檔 stem mapping；每個 target file
    逐檔呼叫既有 `apply_labels_legacy`，generic `labels.mat` 或無法唯一對應時仍 skipped。
  - Data Interpretation wizard label carrier table 現在有 `Matched EEG` 欄位；UI replay
    artifact 已刷新成 generic `events.tsv` 對到 `sub-01_task-mi_run-2_raw.fif`，不再只讓使用者看
    carrier 名稱和欄位設定。
  - 使用者在 `Matched EEG` 欄位手動指定 target 後，`label_carrier_choices` 會保存
    `target_file`，backend 會只對該 loaded EEG file apply reviewed timestamp 或 trial-order labels。
  - Ambiguous `Matched EEG` cell 現在會顯示 target selector，選項來自 scanned EEG files，避免
    使用者手打 filename。
  - Post-load `Add Labels to Loaded Data` dialog 現在會顯示 target EEG files 和 recipe trace
    impact，避免使用者在 compatibility label flow 中看不到 labels 會套到哪裡。
  - Post-load label compatibility target selection 現在優先使用 Dataset table row 的 `UserRole`
    data；selected/all-row target files 不再為了開 dialog 回讀 stale
    `DatasetController.get_loaded_data_list()`。
  - `Add Labels to Loaded Data` compatibility path 現在會在 empty state disable，tooltip 引導
    使用者先 interpret data source；action 也會尊重 backend `ImportLabelsCommand`
    capability block。
  - Channel Selection dialog 的 loaded data list 現在先走
    `QueryStateCommand(query="data_lists", include_objects=True)`；controller loaded-list read 只留在
    no-capability mock / legacy path。
  - Reviewed MAT sample-index anchor apply 已新增窄路徑：當 wizard 明確選定 MAT label field、
    MAT anchor、`time_model=sample_index`、`granularity=trial` 和 class map 時，backend 會把
    MAT labels + anchor 轉成 MNE-style event array，透過 `apply_labels_batch` 套用，並保存
    `label_import:anchored:<n>` recipe trace。
  - PyVistaQt runtime probe 已新增：目前 runner session 有 `DISPLAY=:0` / `WAYLAND_DISPLAY`，
    但最小 PyVistaQt plotter 仍以 X `BadWindow` blocked；interactive 3D render 仍不可宣稱完成。
- 剩餘非 Goal 1 closure blockers：label import 已能寫入 recipe trace，但尚未成為成熟 import
  wizard 內嵌 label import editor；任意 raw trigger selection / complex MAT-GDF anchor
  reconciliation、full real-data manual compatibility certification、MCP HTTP / long-running
  tool calls、interactive 3D render、Windows launcher 真人驗收尚未完成，UI replay coverage
  還不是完整真人 walkthrough。

## 下一個 Goal

下一個 goal 應聚焦在產品硬化，而不是重做 Goal 1 baseline：

```text
True local LLM ChatPanel long-running tool-command workflow
  + label/recipe wizard hardening
  + MCP HTTP / long-running tool-call hardening
  + Windows launcher click-through
```

這不是單純讓 deterministic eval 分數漂亮。下一輪要把真 UI、真 local model、可見 blocked
reason、tool execution transcript、recipe editing 和 external-agent adapter 邊界一起驗證。

MCP 也應納入設計，但 Goal 1 的最低要求是 **MCP-ready command surface**：先確保 command
taxonomy、capability policy、autonomy policy、result schema 足以支撐 MCP server。若 runner
能安全完成 MCP server，可作為 Goal 1 延伸；若無法完成，不能因此延後 Data Interpretation
主線。

## Goal 1 Scope

Goal 1 至少要包含：

1. **Data Interpretation command surface**
   - `scan_source`
   - `preview_interpretation`
   - `validate_interpretation`
   - `apply_interpretation`
   - `save_interpretation_recipe`
   - `reload_interpretation_recipe`

2. **Data Interpretation lifecycle**
   - `ScanResult`
   - `InterpretationCandidate`
   - `InterpretationPreview`
   - `ValidationDecision`
   - `AppliedInterpretation`
   - `ImportRecipe`

3. **Metadata resolution**
   - subject / session / task / run preview。
   - filename / folder / BIDS / header metadata source。
   - user confirmation / override。
   - recipe 保存 metadata rule 與 override。

4. **Validation decisions**
   - `safe`
   - `needs_confirmation`
   - `blocked`
   - BIDS metadata 的 `warning` / `limited` / `blocked`

5. **Autonomy policy / decision boundary**
   - command-specific autonomy policy。
   - `allow_auto`、`confirm`、`ask_user`、`stop`、`repair`、`block`。
   - `continue_allowed_after_success`。
   - decision boundary taxonomy：semantic、high-impact、long-running、destructive、
     missing-input、resource-lock、blocked。

6. **Agent tool taxonomy migration**
   - Discovery / Query。
   - Data Interpretation。
   - Metadata Resolution。
   - Data Transform。
   - Experiment Setup。
   - Execution。
   - Lifecycle / Destructive。
   - UI Routing。

7. **UI import entry redesign**
   - 使用者給 file / folder / BIDS root / recipe。
   - UI 顯示 scan / preview / validation / confirmation。（preview dialog 已完成第一版。）
   - 不再以 `Imported` / `Labels attached` 作為資料可信主語言。（主 import entry 已改；
     label import messaging 仍待收斂。）
   - 使用者已允許為新 Data Interpretation / load data 機制修改資料入口 UI；不能因為 UI
     會大改就只做 backend 或把新流程塞回舊 import 外殼。

8. **Agent alignment**
   - Context Assembler 暴露 Data Interpretation tools。（agent surface slice 已完成。）
   - Agent registry 暴露 `evaluate` / `visualize` / `saliency` analysis-readiness tools。（analysis
     tool exposure slice 已完成。）
   - Verification Layer 檢查 capability policy、Data Interpretation decision 和 autonomy policy。
     （目前已檢查 backend capability / dynamic confirmation boundary；deterministic eval cases
     已納入 Data Interpretation decision / blocked / confirmation / recovery。）
   - visible response 不暴露 raw schema、snake_case command、traceback 或 debug payload。

9. **Evaluation baseline**
   - deterministic / engineering tool-call cases 覆蓋 Data Interpretation、metadata resolution、
     autonomy boundary、blocked、confirmation、missing parameter、recipe reload。
     （目前 deterministic baseline 已擴為 `121 / 121` pass；新增三個 recipe remap cases。）
   - local LLM runner 使用同一份 cases 接 primary / fallback raw output，各重跑 `3` 次；
     目前 deterministic / primary / fallback 都是 `121 / 121`。apply-lock case 的 local raw output
     仍可能提出 direct blocked
     `apply_interpretation`，但 scorer / verifier 只把它當 capability-policy blocked response；
     任何 scan / reset / configure 等替代工具會被計為 failure。
   - dashboard 必須能顯示 overall pass rate、case family、metric breakdown、failure taxonomy、
     worst cases、model comparison、repeat stability、fixture / source path、artifact path 和
     thesis claim boundary；目前入口是 `artifacts/agent_evals/dashboard.md`。
   - scripted replay 要分 backend replay 和 UI-observable replay；不能只看文字報告就宣稱 UI 行為正確。
     目前 consolidated human-like walkthrough artifact 已刷新到 `26 / 26` required phases、`20`
     screenshots，且 artifact 會 top-level index visible text、button state、workflow/backend
     snapshot、UI quality review 和 resource smoke；reset / new-session boundary 已不再顯示
     stale chat bubbles 或 stale workflow status。最新 20:11 rerun 也已把 Data Interpretation
     decision copy 刷到 `Review and confirm these choices before applying.`，並把 ChatPanel
     composer placeholder 縮成 `Ask about EEG workflow`；resource smoke 會
     gate close 後 Python / Qt thread cleanup 和 coarse RSS high-water delta；仍不能替代 human
     desktop acceptance 或長時間 leak / local model soak。
   - 正式 local LLM thesis eval 可以晚一點，但 scorer schema 與 case shape 不能再用舊
     `load_data / attach_labels` 作為主設計；agent primary stage prompt 和 MCP/headless schema
     已先降權 legacy tools，後續 UI language 仍要繼續盤點。

10. **MCP-ready automation surface**
    - CLI / headless runner 保留給 CI、eval、batch 和 artifact generation。
      （`scripts/dev/run_application_command.py` 已新增。）
    - MCP server 作為 external agent adapter，使用同一套 command taxonomy。
      （目前已有 stdio MCP server baseline：`scripts/dev/run_mcp_server.py`。）
    - MCP client 不應需要安裝 XBrainLab 的 EEG / PyQt / PyTorch 依賴；MCP server 跑在 prepared
      XBrainLab runtime。
    - MCP calls 不能繞過 ApplicationService、capability policy 或 autonomy policy。

## Goal 1 Done Definition

Goal 1 不能只做文件或小 patch。至少要達到：

- UI、agent、headless path 都能走同一套 Data Interpretation command surface。
- 資料入口 UI 已反映新 Data Interpretation 心智模型；不是舊 `Import Data` / `Import Label`
  外殼加 backend adapter。
- 舊 `load_data / attach_labels` 不能再是新 UI / agent 的主要心智模型；若保留，只能是
  legacy adapter 或底層 compatibility path。
- subject / session / task / run metadata 會在資料解讀 preview 中顯示，且能保存進 recipe；
  reviewed subject/session 也會同步到 loaded Raw wrapper，讓 Dataset table 和 downstream split
  使用確認過的 metadata。
- Data Interpretation validation 會產生 `safe`、`needs_confirmation`、`blocked`。
- command result 或 verification result 能表達 autonomy decision / decision boundary。
- agent 可以規劃完整 workflow，但每一步都一個 command 一個 command 地 verify / execute /
  refresh state。
- decision boundary 會強制停下來問使用者，不依賴 LLM 自己「夠聰明」。
- 至少一條 non-mocked synthetic workflow 走過：

```text
source_path
  -> scan
  -> preview metadata / label-event interpretation
  -> validate
  -> confirm / apply
  -> recipe
  -> preprocess
  -> epoch
  -> dataset
```

- tests / artifacts 能證明上述行為，不只靠人工讀程式碼。
  （backend integration test 已覆蓋；UI-observable artifact 已覆蓋 Data Interpretation preview /
  applied dataset panel。）
- scripted replay 至少能產生 backend report；涉及 UI 的 replay 必須有 transcript、visible state、
  screenshot 或 UI artifact，不能只看 backend JSON。
- command / result schema 已足以包成 MCP tools，且 MCP 設計不會變成第三套 workflow truth。
- 文件同步更新 `target/`、`architecture/`、`validation/`、`records/`。

## Goal 前必做

啟動 goal 前先做：

1. 跑一次文件一致性檢查。
   - 確認 `target/architecture.md`、`target/data_interpretation_system.md`、`target/agent.md`、
     `validation/thesis_protocol.md`、`planning/roadmap.md`、本文件不互相矛盾。

2. 建立 docs checkpoint。
   - 目前文件變更很多；goal runner 開工前應先有一個清楚 checkpoint。
   - 不要把 `.vscode/settings.json` 或 root `settings.json` 的本機變更混入 checkpoint。

3. 確認 goal runbook。
   - 目前 runbook 位於 `artifacts/goal/goal-1-product-autopilot.md`。
   - runner 不應頻繁回報，應改用 `records/worklog.md` 和
     `records/implementation_log.md` 留狀態。
   - runner 必須遵守 commit discipline；每個可驗收切片完成後 commit。

4. 設定驗收 gate。
   - 不只跑 dashboard。
   - 需要 backend command tests、agent tool / verifier tests、UI import walkthrough、
     non-mocked synthetic workflow、UI-observable scripted replay、mkdocs strict。

## Validation Gates

Goal runner 回報完成前至少要跑：

```bash
git diff --check
poetry run mkdocs build --strict
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
```

還需要依實作範圍跑 targeted tests，例如：

```bash
poetry run pytest --capture=sys tests/unit/backend/application -q
poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q
poetry run pytest --capture=sys tests/integration/backend tests/integration/io/test_io_integration.py -q
```

若改 UI / import flow，還要跑相關 UI tests / walkthrough。若改 launcher / local runtime，還要跑
Windows launcher 或 local model resource-safe smoke。

若新增 MCP server，還要至少驗證：

```bash
poetry run pytest --capture=sys tests/unit/mcp tests/integration/mcp -q
```

實際 test path 可依實作調整，但不能只靠手動 MCP 呼叫宣稱完成。

## 不能宣稱

- 不能宣稱 Data Interpretation System 已完成，除非 source path 到 recipe 的流程真的可用。
- 不能宣稱 agent 已達理想架構，除非它已遷移到新 tool taxonomy 並受 autonomy policy 約束。
- 不能把 prompt smoke 當成真 local LLM ChatPanel walkthrough。
- 不能把 deterministic eval 當成 local LLM 真實 tool-call accuracy；目前 primary / fallback
  真模型已用同一 `121` case suite 各重跑 `3` 次並得到 `121 / 121` evidence。這只支撐已重跑
  tool-call benchmark slice，不代表 ChatPanel / launcher / import wizard 產品驗收完成。
- 不能把 backend scripted replay 的文字報告當成 UI 行為正確；UI replay 要有人眼可審查 artifact。
- 不能把 mock-heavy tests 當成真實 workflow evidence。
- 不能把 dashboard PASS 當成產品完成或 thesis claim 成立。
- 不能讓 API / Gemini / remote LLM 回到 product execution path。
- 不能使用中國公司或中國來源模型。
- 不能讓 MCP 直接操作 controller 或繞過 ApplicationService / autonomy policy。

## 下一步

現在最應該做的是：

```text
1. 繼續 backend / UI architecture cleanup：ApplicationService 已拆出 Data Interpretation、
   Analysis、Training、Dataset Generation、Lifecycle、Data Compatibility 和 Data Table command
   services、Preprocess command service，以及 State / Query services。`UI Command Refresh
   Coordinator + Controller Fallback Audit` 已完成 first slice；下一步是擴大盤點剩餘
   observer/manual refresh 和 real `Study` mutating workflow。Training / Preprocess / Dataset /
   Visualization / AgentManager fallback 已先改成 explicit mock / legacy-only helper；下一步應
   audit 剩餘 `result is None` branches 是否全部是 service-unavailable UI error / blocked return，
   並繼續收斂 observer/manual refresh。Training sidebar readiness refresh、Dataset action
   panel refresh、Data Interpretation apply / recipe reload refresh、post-load label
   compatibility service-success refresh、direct load compatibility service-success refresh，以及
   Dataset sidebar channel-selection / clear-dataset refresh、Dataset inline metadata refresh 已先
   收回 coordinator；Training model-selection service-success controller echo 也已收斂到
   command-success path。Preprocess sidebar service-success refresh 和 Visualization control sidebar
   montage / saliency service-success refresh 也已收回 coordinator。Suggested follow-up milestone
   remains non-blocking for current validation closure but required for product-complete:
   `CommandResult.changed_state` -> expected panel/sidebar/assistant refresh tests, no silent
   controller mutation in product runtime, and controller reduced to adapter / read-only rendering /
   legacy compatibility boundaries.
2. Data Interpretation mature wizard：embedded label / anchor / MAT variable editor，避免
   post-load compatibility label import 繼續主導心智模型。
3. 進入下一輪 UI polish：mature import wizard editing、assistant main-window narrow composition、
   analysis page compact controls。
4. 清楚標記 remaining human desktop acceptance：Windows launcher、雙螢幕、DPI、真人長時間
   local model session。
```
