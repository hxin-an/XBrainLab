# XBrainLab Now

最後更新：`2026-08-11`

這頁只保存 active delivery context、近期施工順序和 exit condition。舊
[Product Quality Audit](../records/product_quality_audit_2026-07-30.md) 保留為此次 main checkpoint
的歷史 ledger，不再作為新的 active queue。

## 目前焦點

**以 `main@6c09c6a17bda63ec92dfa4f848bb11e995dc2da0` 為產品基線，先交付 validation
control plane；EEG workflow PR #12、guidance PR #13 與 import / training / montage polish PR #14
已合併，不再是 active candidate。**

目前不是 release 或 Assistant handoff-ready。真人資料驗收只涵蓋 Graz 2a GDF 與 OpenNeuro
ds003061 P300 BIDS 各一個資料集；其餘格式、自動化 evidence 與舊 Agent gate 不可外推。
目前 task 只改驗證基建與 canonical guidance，不改產品 runtime 或 UI，因此本輪不要求使用者
重跑 EEG/UI 手測。它必須先以 focused validation、same-class review、strict docs、push 與
exact-head CI 證明控制面可排程且 fail closed；完整 20 個 product scenarios gate 仍依使用者
指示延後，不能被記為通過。

## Active Delivery Context

| 項目 | Current value |
| --- | --- |
| Worktree | 由 `git rev-parse --show-toplevel` 與 `git branch --show-current` 現場取得；不在文件寫死本機 path。 |
| Product baseline | `main` |
| Candidate branch | 不寫死長期 branch；只有目前 task PR 的 pushed exact head 可成為候選。 |
| Baseline | `main@6c09c6a17bda63ec92dfa4f848bb11e995dc2da0` |
| Goal | 先關閉 validation control plane，再以新控制面推進 UI QA 與 guidance closure。 |
| Historical ledger | [Product Quality Audit - 2026-07-30](../records/product_quality_audit_2026-07-30.md) |
| Current classification | Local validation PR candidate；exact-head CI pending；not release / not Assistant-ready。 |

不要從舊文件推論 registered worktree 數量。需要 inventory 時執行
`git worktree list --porcelain`；其他 worktree 不得被誤認成 active candidate，也不得覆寫其
owner 的 dirty changes。

## Data / Training 目前交付邊界

本輪 BIDS label-field recommendation 必須來自 selected runs 的 bounded evidence：欄位存在與非空
coverage、觀察值、sidecar `Levels` 和跨 run consistency；若任一 selected table 的 row / byte
inspection 被截斷，或 evidence 不足，就不自動推薦，使用者明確選擇仍優先。Epoch context 只接受 reviewed import handoff 與對應 recording hints；handoff
缺少、格式錯誤、讀取失敗、source / placement 不一致，或 selected recordings 的 sampling frequency
不一致時 fail closed 且不改變既有資料。將所有 recordings resample 到同一 sampling frequency 後，
`Create Epoch` readiness 會恢復。Duration / event-locked
mode 也必須從這份 reviewed handoff 綁定的 placement / duration evidence 產生，不能由 UI fallback
猜測。

Data Splitting preview 會暫時建立 candidate datasets / masks 以計算摘要，然後恢復原狀。Confirm
先驗證 preview receipt，再只保存 lightweight typed specification、epoch revision、fingerprint 與
bounded preview summary，不發布 masks 或 training tensors。`Start Training` 才 authoritative
rematerialize datasets、執行 leakage / coverage audit、發布結果並進入 resource preflight；失敗時保留
既有 dataset / trainer / training state，不得因確認新設定先做 destructive cleanup。

本輪 Training 只實作當前已選模型的 deterministic recommended defaults，不實作計時
hyperparameter search、trial orchestration 或自動模型選擇。推薦值更新必須逐欄位處理：只更新未被
使用者編輯的欄位，並以 trusted host provenance 保留每一個已被使用者修改的值，不得因重新計算
recommendations 而整組覆寫。Recommendation 是保守 starting point；`Start Training` 的 resource
preflight 仍是最後 authority。

未來的計時搜尋必須依 [Roadmap](roadmap.md) 的 deferred contract 獨立交付；它不是本輪
candidate 的完成條件，也不可由現有 recommended-defaults UI 暗示為已有功能。

## 施工順序

| 順序 | 工作 | Exit signal |
| --- | --- | --- |
| 0 | Close validation control plane PR #15 | 在最新 `main` 上通過 focused/same-class/static/docs、blind review 與 pushed exact-head CI；不得用舊 SHA evidence。 |
| 1 | Stabilize teacher-facing GUI/data flow | 針對 GDF、BIDS 與老師新增資料逐一走 import -> preprocess -> epoch -> training；發現 blocker 就用 focused regression 修正。 |
| 1a | Preserve merged EEG workflow baseline | PR #12 已合併；後續 bug fix 以 main 上的 Braindecode catalog、BIDS subject preselection、test curve、Evaluation / Saliency cross-fold 與 Normalize contract 為 regression baseline，不重啟舊 integration branch。 |
| 2 | Measure and polish performance | 保留目前 BIDS review latency checkpoint，補 phase timing、fixture manifest、環境、至少 3 samples 的 median/p95；wall-clock ceiling 不和 semantic CI gate 混在一起。再量 load、publication refresh、plots、preprocess 與 training startup。 |
| 3 | Simplify Assistant prototype | 先建立 typed confirmation risk，讓 high-impact setting change 真的顯示 current/proposed card；再拆開 GUI handoff 與 confirmation，並把每回合 Granite 2B tool exposure 收斂成單一 canonical action contract。 |
| 4 | Recalibrate Agent gates | 盤點並修改舊 prompt/tool/gate assumptions；建立與目前 Assistant UX、Granite 2B、真實 GUI state 一致的可重跑 gate。 |
| 5 | Expand dataset acceptance | 每新增一個真人資料集都記錄來源、格式、label semantics、可完成步驟與限制；不同副檔名不冒充不同資料集。 |
| 6 | Candidate gate | 在明確候選 commit 跑 relevant regression、multi-dataset、UI artifact、static/docs 與真人 Windows acceptance，再決定 release claim。 |

## Active Quality Closure TODO

這是本輪唯一 active TODO。完成一列代表其 exit signal 已有可重跑 evidence，
不是 worker 回報「已實作」。

| Workstream | Required outcome | Exit signal | Status |
| --- | --- | --- | --- |
| Validation control plane | Change intent、affected layer、risk 與 claim stage 產生 source-bound immutable plan；traditional tools 執行與判定，昂貴 data/UI/native/resource gate 只按風險加入，local-only Granite/RAG 留在 handoff。 | Descriptor/registry/plan/receipt lineage、complete CI owner coverage、dynamic matrix、docs-only real gate 與 exact-head capability-only verdict 通過。 | Local PR candidate；exact-head CI pending |
| Assistant confirmation contract | `reset_preprocess`、`configure_dataset_split` 與影響 training 的 setting change 都使用正確 typed confirmation evidence；不得來自一般 approval 字串。 | capability/confirmation/revision/fingerprint focused tests 與 negative stale-evidence tests 通過。 | Local candidate validated; exact-head CI pending |
| Assistant decision state | GUI navigation handoff 與真正參數/危險操作 confirmation 使用 typed decision owner，不再靠未分類的 waiting presentation 猜測。 | UI presentation 能區分 navigate、confirm、blocked、error、retry，且 correlation 沒有混用。 | Local candidate validated; exact-head CI pending |
| Granite 2B tool surface | 每回合只暴露當前 intent 需要的 canonical schema，避免 `set_model` / `configure_training` 或多個 generic preprocess tool 競爭。 | representative prompts 的 schema exposure 與 selected-tool oracle 通過，且 blocked tool 無法執行。 | In progress |
| Assistant failure/retry UX | tool runtime failure 不再全部假裝成 BLOCKED；narrow panel 仍有 correlated retry / cancel 途徑。 | error、blocked、cancel、retry screenshots 與 state-transition tests 通過。 | In progress |
| Assistant handoff route ownership | command、dialog/panel surface、decision owner、target panel 與顯示文案只有一份 typed route descriptor；controller、host、presentation 不各自維護 mapping。 | route coverage/parity、request correlation、dialog/panel terminal-resolution tests 通過，重複 mapping source sweep 為 clean。 | In progress |
| Assistant turn transaction | turn orchestration、pending interaction、tool session、metrics、response buffer 與 terminal cleanup 由單一 transaction owner 管理，不靠多組手動 reset/rollback。 | error/cancel/timeout/retry/new-turn characterization 先完成；再用可回滾 slice 抽取 owner，long-session/lifecycle gate 不退步。 | Pending handoff closure |
| Chat processing state truth | typed turn presentation 是 loading/working/waiting/error/idle 唯一顯示真相；legacy boolean busy signal 不可覆寫較完整狀態。 | source guard 消除 product 雙訂閱/順序依賴，resize/stream/error screenshots 與 lifecycle tests 通過。 | Pending turn transaction |
| Qt worker lifecycle | agent/UI tests 不留下 QThread、deferred delete 或 teardown hang；不用 CI shard 隱藏 lifecycle leak。 | isolated reproducer 與 repeated bounded lifecycle test 通過，process 可正常退出。 | In progress |
| Obsolete test cleanup | 只在 unique behavior / source guard 已遷移後刪除 duplicate suites，不為縮短 CI 盲刪。 | replacement assertions 先紅後綠，relevant domain shard 仍通過。 | In progress |
| Tool-call showcase | 一個可快速看見 prompt -> snapshot/capabilities -> exposed schemas -> tool/params -> verification/confirmation -> command result -> visible feedback 的 script。 | deterministic default 輸出 JSON + Markdown，含 success、blocked、confirmation、cancel、stale、error/retry；另有可選 real Granite 2B mode。 | In progress |
| Assistant composition refactor | 在上述 behavior contract 穩定後，將約 3,100 行 `LLMController`、2,400 行 `AgentManager` 與 2,500 行 `ChatPanel` 中的 turn orchestration、confirmation、runtime lifecycle 和 presentation ownership 拆成已有 narrow owners，不改 UI 心智模型。 | 每個 slice 先有 characterization tests；product path 仍只走 ApplicationService；chat screenshots 和 tool traces 無語意差異。 | Pending contract closure |
| UI compatibility cleanup | 盤點產品 UI 仍直接讀 controller / Study-shaped compatibility 的 call sites；優先清掉會形成第二份 readiness 或 render truth 的部分，不因檔案大就大改 UI。 | source guard + 一條 non-mocked command/publication workflow 通過，與當前 screenshots 一致。 | Pending behavior closure |
| Data Import structured review truth | `ValidationDecision.action_items` 唯一決定 blocker 與 target step；UI 不從英文 summary/blocked reason 反推 readiness。 | safe/needs-confirmation/blocked/resource-blocked/edited-recheck tests 與 missing-action-items fail-closed guard 通過。 | In progress |
| Publication lifecycle boundary | 已抽出的 `ApplicationPublicationLifecycle` 直接擁有 terminal/retry/shutdown/headless wait 行為；移除只有測試綁定的 ApplicationService 私有 delegate。 | 每個 delegate 有 call-site sweep，focused owner/public-result tests 與 adjacent backend publication suites 通過。 | In progress |
| Data Import composition debt | 約 4,500 行 wizard dialog 不能再吸收 backend policy、scan 或 recipe truth；新的 MOABB / site 工作不得把 dataset-specific 規則寫回 UI。 | 本輪先用 architecture guard 阻擋新回流；真正拆分只用可回滾的獨立 refactor slice。 | Guard now; refactor later |
| User-facing site | 另一個面向 EEG 使用者的 site source，不覆寫 developer docs；流程導航、限制與資料來源清楚。 | isolated strict MkDocs build、desktop/mobile screenshot review，不存在假 metrics 或 placeholder-as-evidence。 | In progress |
| MOABB dataset journeys | Batch 1 先完成 3 個不同 source/paradigm 的真實 dataset；長期 campaign 目標約 80 個 MOABB dataset cases。每個 case 都使用 XBrainLab product path 走 load -> labels/metadata -> preprocess -> epoch -> split -> train -> evaluation -> saliency。未達品質門檻時先診斷資料量、切分與 validation-only tuning，不以反覆查看 test 或直接放棄收尾。 | pinned source/license/identity/subject/run/seed/recipe/metrics/saliency manifest，可 resume，且 batch 1 至少一個 case 非 GDF、一個非 MI。Campaign runner 必須 dataset-agnostic，後續可逐批擴到約 80 cases。 | Batch 1 in progress (3 cases) |
| Case-study evidence | 每個 dataset 一頁，只顯示實際重跑的 screenshots、training result 與 limitation，不把 format coverage 冒充 dataset diversity。 | manifest 和頁面數字可對應 exact artifacts；主 agent 逐圖檢查。 | Pending pipeline |
| Integration and review | Agent/runtime 與 user-site/evidence 使用明確的 stacked branches，不污染已綠的 EEG workflow candidate。 | 主 agent 重讀 diff、跑 combined tests、UI/product/architecture reviewers 重審，再 commit/push。 | Pending workers |

分支邊界：`main` 是唯一產品基線。每項工作從最新 `main` 建立短 task branch；只有 pushed PR
exact head 才是該 task candidate。Assistant contract、lifecycle、tool-call showcase、user-facing
site、MOABB runner 與 case evidence 不納入本次 validation PR，也不得把未審查 worker commit
混入其中。

## Evidence Rule

本次 validation candidate 的 immediate exit signal 是：descriptor/path monotonic selection、
source/base/plan/receipt lineage、CI owner schedulability、native/registry evidence re-verification、
same-class adversarial review、strict docs/static、configured upstream 與 exact-head CI 全部可追溯
到同一 commit。因沒有產品或 UI runtime diff，本輪不以新 screenshot 或 multi-dataset gate 作為
此 task 的完成條件，也不因此提升既有產品 handoff 狀態。

Final totals 不能從本頁、聊天、checkpoint notes 或多次局部 pytest output 手動加總。
唯一可用的 final totals 是同一 clean exact commit 產生的 handoff evidence，且至少要記錄：

- profile；
- worktree / branch；
- full commit SHA；
- dirty / protected-local state；
- command、return status、skip / xfail / deselection policy；
- artifact source identity 和 reviewer verdict。

`artifacts/quality/latest.md` 必須逐欄檢查 identity。若仍指向
`ux/assistant-product-v1@3869aaef`、dirty tree 或不同 commit，它只能算 baseline /
checkpoint evidence。

## Handoff Exit Condition

必須同時成立：

1. Audit 中沒有 code-controllable P0/P1 open item。
2. Focused regression、same-class/source guards、real happy path、deterministic oracle 和 strict
   multi-dataset gate 均由 final commit 重跑。
3. Granite/RAG 和 UI artifacts 是 exact-source output，必要畫面由主 agent 逐張檢視。
4. Ruff、完整 configured product-source Basedpyright、architecture checks、relevant pytest、`mkdocs build --strict` 和
   handoff dashboard 全部來自同一 commit。
5. Branch 已 push；worktree clean，或只保留規則允許且未 stage 的 protected local settings。
6. Final report 明確列出 Windows DPI/multi-monitor、interactive 3D、teacher datasets 和
   long-session 等剩餘人工風險。

未來產品候選仍需讓 Linux parallel shards、focused Windows/macOS platform gate 與 coverage
aggregation 在同一 exact head 的 GitHub Actions 完成；本機 runner tests 不能替代該結果。

達成以上條件後，狀態才能提升為下一個 **Windows handoff candidate**。目前 `main` 只是已接受
的開發 checkpoint，仍不是 product complete。

## 本輪不做

- 不把 baseline branch fast-forward 或重新命名成 current candidate。
- 不新增 facade、silent compatibility fallback 或第二套 workflow truth。
- 不做 MCP hardening、MCP client certification 或 MCP thesis evidence；除非使用者明確要求。
- 不在產品 closure 完成前 freeze thesis benchmark 或宣稱 raw-model accuracy。
- 不把 automated dashboard、offscreen screenshots 或 launcher smoke 當成人工 acceptance。
- 不實作 Training timed hyperparameter search；本輪只交付可保留使用者逐欄位編輯的 deterministic recommended defaults。
- 不新增 planning 文件；新 current truth 回寫既有 canonical pages。
