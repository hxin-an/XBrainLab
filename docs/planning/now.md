# XBrainLab Now

最後更新：`2026-08-20`

## 目前焦點

從已手測並合併的 `main` merge commit `99d4bdfb9b746a26bddd379eb4ef48af32e66db7`
建立 `refactor/test-quality-runtime-v1`，全面清理測試、CI、handoff evidence 與本機 regression
runtime。這條 branch 會審查全部 tracked tests，不只處理幾個 E2E 檔；完成完整 handoff 與
remote CI 後才交使用者做核心產品 walkthrough，通過前不合併。

目前 phase：`Phase 2 — owner／claim deep sweep and compatibility retirement`

`7eab03e9` 的 family ledger、complete regression、canonical handoff 與 remote CI 是 Phase 1
checkpoint：它證明 global fixture scope、明顯 fake E2E／duplicate execution 與 runner topology 已
收斂，但不證明 531 個 current test files 內的每個 retained claim 都已完成深度審查。Phase 2 會在
同一條 PR #43 繼續；一旦 source 改變，Phase 1 handoff 只保留為歷史 baseline，不再作 candidate
證據。

本 branch 只修改 tests、test fixtures、developer validation／CI scripts 與直接相關文件；不修改
`XBrainLab/` 產品 UI、ApplicationService、EEG semantics、training 或 Assistant 行為。若清理揭露
產品 defect，記錄後另開 product branch。Root `settings.json` 全程不得 stage、commit、revert、
覆寫或隱藏。

## 問題與量測證據

- Exact Git inventory 為 534 個 `test_*.py`：463 unit、69 integration、2 regression，合計
  266,117 行。69 個 integration files 中有 43 個直接使用 `MagicMock`、`patch` 或
  `monkeypatch`；mock 本身不是錯誤，但不能掩蓋同一 authoritative owner 後仍宣稱 E2E。
- Root `tests/conftest.py` 在 collection 時全域替換 PyVista／PyVistaQt／VTK，且 autouse 接受
  所有 `QDialog.exec` 與 QMessageBox。普通 pytest 因此不能證明真 renderer 或 modal
  Cancel／Reject／Confirm。
- 三個 E2E-named files 共 52 tests，warm run 只需 12.22 秒；它們是 evidence-truth 問題，
  不是主要 runtime bottleneck。真正 persistence evidence 是 public cross-source training；真
  renderer 與 native lifecycle 由 dedicated subprocess gates 擁有。
- 最大測試檔包括 ApplicationService 10,618 行、architecture compliance 6,995 行、Data
  Interpretation dialog 6,845 行、human-like capture test 5,771 行與 Agent controller 5,005 行。
  這些需依既有 owner／claim 合併或拆分，不能單純按 LOC 切檔。
- Exact source `95da47f7` 的 canonical handoff 為 42/42 PASS、11,300 executed、0 failed，
  wall 2,232.165 秒（37 分 12 秒）；complete regression 1,353.293 秒（22 分 33 秒）。
- 本機有 16 logical CPUs、約 30 GiB RAM；local runner 固定最多兩個 outer groups，八組內又
  原先產生29次串行pytest collection/process。清理沒有獨立claim的integration/training shard後為28次；
  低CPU利用率主要來自fixed phase、process isolation、
  長尾 group 與 wait／IO，不是 GPU 沒被使用。
- GPU 只適合 Granite runtime、stable model eval 與 resource calibration；unit、Qt、IO、MNE
  與 CPU training tests 不得為提高 utilization 改用 GPU。

## Observable outcome

1. 全部 531 個 current `test_*.py` 都取得 exact-SHA、per-file disposition；mixed files 必須列出
   實際保留／移除的 node 或 claim，而不能只以 family-level `keep` 代表完成。每個 merge／delete
   都有 exact replacement 或同一 PR 已退役的 source contract、focused evidence 與 count delta。
2. 每個保留測試都對應 reachable defect、observable transition、real side effect 或明確 claim；
   mocked delegation 不稱 E2E，integration mock 不得取代同一 authoritative owner。
3. Root conftest 不再全域決定 modal outcome或 renderer availability。Fake renderer、accepted modal
   與 real modal 各由明確 opt-in fixture 擁有。
4. 重要 workflow 保留 lower-mock ladder：ApplicationService command、real EEG／public format、
   real artifact/history/reload、native UI／renderer與model gates各自只宣稱自己的 boundary。
5. Linux complete regression 仍執行相同八個 authoritative groups、coverage、completion
   attestation 與完整 collection。相同環境的 focused pytest 不再重跑；不同 environment／artifact
   claims 仍獨立執行。
6. Runtime work不以固定分鐘取代品質。Phase 2 中途不重跑 complete regression 或 handoff；所有
   owner slices 完成並 freeze exact SHA 後只跑一次 canonical handoff。不得靠 skip、提高 timeout、
   縮小 denominator 或移除 unique evidence 達成改善，也不為取得更好的計時數字重跑。
7. Final exact branch head 的 focused baselines、完整 regression、canonical handoff、remote CI與
   artifact inventory全部通過後，才交使用者手測 Data Import → Preprocess → Epoch／Split →
   one-epoch Training → Evaluation／Saliency。

## 全量 family ledger

Git與pytest collection是 denominator authority；本表在每個 checkpoint 更新，Git commits保留 exact
file／replacement mapping，不建立另一份萬筆 test manifest。

| Family | Baseline files | Reviewed | Keep | Rewrite | Move／rename | Delete | Status |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| unit/backend | 186 | 186 | 185 | 1 | 0 | 0 | complete |
| unit/llm | 77 | 77 | 77 | 0 | 0 | 0 | complete |
| unit/scripts | 70 | 70 | 65 | 5 | 0 | 0 | complete |
| unit/ui | 120 | 120 | 117 | 3 | 0 | 0 | complete |
| unit/root | 10 | 10 | 9 | 1 | 0 | 0 | complete |
| integration/agent | 5 | 5 | 5 | 0 | 0 | 0 | complete |
| integration/backend | 10 | 10 | 10 | 0 | 0 | 0 | complete |
| integration/controller | 3 | 3 | 2 | 0 | 0 | 1 | complete |
| integration/debug | 1 | 1 | 1 | 0 | 0 | 0 | complete |
| integration/io | 9 | 9 | 9 | 0 | 0 | 0 | complete |
| integration/llm | 1 | 1 | 1 | 0 | 0 | 0 | complete |
| integration/pipeline | 14 | 14 | 9 | 0 | 4 | 1 | complete |
| integration/training | 1 | 1 | 0 | 0 | 0 | 1 | complete |
| integration/ui | 25 | 25 | 20 | 3 | 1 | 1 | complete |
| regression | 2 | 2 | 1 | 0 | 0 | 1 | complete |

兩個新增的target-side contract files（root fixture policy與remote human-like CI gate）不屬於534個
baseline denominator；一個moved pipeline presentation file進入unit/UI。Current tree因此是531個test
files。保留的mock只證明明列的external/resource/model/UI seam；同owner成功與artifact claim仍由
ApplicationService、real EEG、native subprocess或public cross-source lower-mock gate擁有，不建立逐node
control manifest。

## Scope／non-goals

- In scope：全部 test families、fixtures、mock scope、obsolete／duplicate tests、lower-mock
  replacements、source guards、CI／handoff duplicate execution、fixed runner topology、resource timing、
  orphan test/dev assets、validation docs，以及沒有 current production／dev caller 的 non-UI
  compatibility aliases／diagnostic surfaces。
- Non-goals：不修改產品 UI／可見行為、不把所有 unit 改成 integration、不追求 GPU 高使用率、
  不建立通用 scheduler／distributed control plane、不用 test count 或 LOC reduction 當成功標準。
- 產品 owner 數前後均不變。Test policy 從 root-global substitutions 收斂成 scoped fixtures；runner仍由
  既有 `run_tests.py`／`run_local_handoff_regression.py` 擁有。
- CI 與 local handoff 是不同環境 claim；Windows、macOS、public-data、native、model與人工驗收不能
  被 Linux complete regression 取代。

## Phase 2 active execution

1. 以 current Git tree 為 denominator 產生 ignored exact-SHA per-file audit evidence：`path`、owner／
   claim、`keep-primary | keep-unique | mixed-trim | merge-into | delete-obsolete | move-support`、
   replacement、原因與 focused evidence。Canonical plan 只保存 aggregate 與 hash，不建立 531-row
   permanent control plane。
2. 先移除 caller inventory 為零的 non-UI compatibility APIs：`BackendRegistryCompat`、
   `safe_model_cache_name()`、未使用的 duplicate platform settings-path helper、fallback model-ID
   aliases，以及 `legacy_local_model_ids()` 與兩個 dev report fields。再獨立退休 Assistant registry
   無法到達的 legacy `load_data`／`attach_labels` proposal／diagnostic branches；published 18-tool
   surface 不變。
3. 保留 current v0.7 runtime boundaries：Data Compatibility label/import commands、repo-root settings
   到 per-user settings 的 one-time migration、retired model-ID migration guidance、current artifact
   schemas，以及仍由 UI callers 使用的 compatibility paths。任何需要 `XBrainLab/ui/` 修改的 retirement
   停止並另列 product follow-up。
4. Architecture policy、ApplicationService、Data Import、Training、Assistant、UI component、capture／
   script、integration／regression families 依 owner／observable claim 全盤審查；檔案大小只決定優先
   順序，不是 scope boundary。Retained high-risk side effects 必須連到 lower-mock evidence；歷史 migration
   guards 與同義 AST／pixel／private-helper assertions 在有替代後移除。
5. 每個 owner 一個可回退 checkpoint commit，只跑 identical characterization 與直接相鄰 focused
   evidence。Phase 2 不執行 standalone complete regression、full handoff或重複計時。
6. 全部 critical runtime nodes 都取得 eliminated／batched／rescheduled／retained-with-reason disposition
   後 freeze exact SHA，跑一次 canonical handoff、檢查 artifacts、push exact PR head並等待所有
   non-skipped CI success，最後交使用者做核心產品 walkthrough。任何 source change 使先前人工批准
   與 handoff 失效。

## 施工順序

### A. Exact inventory and evidence taxonomy

1. 固定 exact tracked files、pytest node collection、八組 Linux partition、40-gate registry與 baseline
   durations。每個 family 產生 ignored working inventory，ledger只記 aggregate完成度。
2. 對每個 file 決定 `keep | rewrite | move_rename | delete`：unit可 mock external collaborator但不
   mock同一 owner decision；integration side effect必經 owner public entry；native／model／public-data
   各由 dedicated gate 擁有。
3. 所有超過 2,000 行的 test file 都要取得「合併重複、按既有 owner 拆分、或保留理由」。

### B. Scope global test substitutions

1. 建立 passing characterization，盤點 global modal acceptance與renderer replacement的直接使用者。
2. 新增 opt-in `auto_accept_modals`與`allow_real_modals`。未聲明的 blocking modal fail-fast；
   Cancel／Reject／Confirm tests使用真 widget driver。PyVista／PyVistaQt在目前 pinned環境可直接
   import，故不新增共享 fake fixture；需要 renderer fake 的 component test 必須在該 test 明確 patch。
3. 按 subtree 遷移後移除 root autouse與global `sys.modules` replacement；保留 native subprocess gates。

### C. Clean every test family

1. Backend／Application tests依 existing service owner收斂；移除 private call sequence與重複 source
   assertions。巨型 monolith 先遷出 unique claim再縮減。
2. UI component tests保留 widget／visible state；mocked runtime重新分類。Assistant tests區分 parser／
   router scenario與真 command/model evidence。
3. Pipeline／training保留 public cross-source real artifact authority；direct Trainer／Study cases改稱
   compute／facade integration。Mock Dataset workflow的 unique AUC assertion遷入 real Dataset replacement
   後刪除。
4. Scripts tests只保留 deterministic policy與最小 subprocess／artifact smoke；重複 source scan使用
   process-local immutable snapshot。Regression只保留未被 general owner contract吸收的 incident。
5. 每個 family一個可回退 checkpoint commit；count delta、replacement與unsupported claim寫入 commit／ledger。

### D. Deduplicate CI and handoff execution

1. Human-like walkthrough從 `linux-integration-ui` wrapper移出，成為 product PR 的獨立平行 GitHub job；
   local handoff仍在本機執行一次。
2. 現有 pytest attestation 原子升版，保存 exact node terminal outcomes。只有同環境、同 fixture、無額外
   artifact 的 focused gates改為 strict subset validator；public/native/capture/model/platform gates保留。
3. Writer、validator、CI、GateSpec同一 checkpoint更新，不留 dual-reader compatibility。
4. 刪除 caller inventory為零的 benchmark／debug／lazy-import／retired capture資產；MCP只清殘留引用，
   不恢復 executable surface。

### E. Reduce runtime with measured topology changes

1. 在既有 runner 記錄 outer group與 inner shard wall、recursive child CPU、peak RSS、process count、
   collection/startup與coverage狀態；不新增 telemetry owner。
2. 對29次 inner process逐一分類：Qt/native/PyVista/MNE污染或 clean-start claim保留；純 Python、無
   global state且順序互換穩定者合併，減少 collection/import。
3. Fixture與isolation清理完成後，local outer runner改為固定三worker、longest-first；保留unit→integration
   barrier，不使用pytest-xdist。四worker只有量測證明仍有獨立critical path才測。
4. Handoff CPU、Xvfb、public-data、GPU/model與RAG維持resource lanes；只讓無共享cache／CUDA／native
   lifecycle衝突的 lanes重疊。
5. 同一 exact commit、warm cache比較兩次 baseline與兩次 candidate；兩個 median改善不足10%時，回退
   無效複雜度並繼續處置 remaining critical path，不弱化 evidence。

### F. Candidate and manual product regression

1. 全部 family 無未審查項目；每個 deletion／move／rewrite有 focused baseline與解釋。
2. 跑八組 complete regression、coverage、strict subset validators與所有 independent gates。
3. 在 clean／explained exact commit跑 canonical handoff，檢查 artifacts，再核對 exact PR head remote
   Linux、Windows、macOS、public-data與human-like jobs。
4. 交付不依賴 test mocks 的核心手測流程；使用者明確通過並同意後才 merge main。

## Checkpoints

- `2026-08-20` Phase 2 owner／claim sweep：相對`7eab03e9`目前47個檔案合計+440／-2,769，
  淨減2,329行；tracked `test_*.py`由531降至526。刪除兩個generic LLM coverage檔、重複的
  white-box controller coverage、兩個remote-mode分散檔，並將唯一CUDA seed、download terminal、
  retired-mode與Data Splitting edge claims移到真正owner suite。Human-like capture移除108行只讀
  private source字串的snapshot tests，保留真Qt signal、artifact tamper／atomic publish、pixel／geometry、
  resource與source-identity gates。ApplicationService、Data Import wizard、Assistant state machine與native
  lifecycle大檔因仍各自擁有unique mutation／rollback／visible lifecycle claims而保留；不以行數刪除。
- `2026-08-20` exact-node attestation去重：pytest completion schema升為v2並保存每個node的terminal
  outcome；complete regression明列architecture與persistence七個required selectors，缺少或非pass即由
  recorder fail closed。因而移除handoff中兩個同source重跑的`architecture-unit`與
  `persistence-path-stop-barrier` gate；獨立architecture source checker、完整regression、coverage與所有
  native／real-data／artifact gates不變。這是evidence重用，不是刪除測試。
- `2026-08-20` global fixture scoping：移除 root collection-time PyVista／PyVistaQt／VTK
  `sys.modules` replacement；未宣告 modal interaction 改為 fail-fast，component accepted path 與
  qtbot real-modal path各自 opt in。`linux-unit-ui` 2,684 cases全數通過；Assistant import review、
  resource refusal與visible BIDS Apply Cancel／retry三條 real-modal integration paths通過。下一步是
  pipeline／training與 E2E-named test family 的 evidence truth清理，不開始 runner parallelism。
- `2026-08-20` E2E／pipeline claim cleanup：將 mocked UI presentation移到 unit/UI，將 MainWindow
  navigation、Study facade、trainer/model compute與 real-data command-spine測試改成反映真實
  boundary的名稱。刪除唯一以 MagicMock Dataset、跳過 type validation且隔離全部 artifact writers
  的假 pipeline test；其唯一 AUC claim已移入 real MNE Dataset trainer integration。選定 family
  baseline由 61變60 tests，exact delta為這一個弱測試；連同 architecture guards共341 tests通過。
- `2026-08-20` CI artifact去重與runner candidate：刪除會在 `linux-integration-ui` 內再次啟動完整
  human-like capture的 pytest wrapper；artifact producer保留為 local handoff canonical gate，remote CI
  改成獨立平行 `human-like-product` job並上傳相同 artifact。直接執行capture成功，8個CI／partition
  contracts通過。Local regression仍保留unit→integration barrier與八組membership，候選改為固定
  三worker／longest-first，並記錄每組 wall／CPU／peak RSS／process count；目前只有5個runner unit
  contracts通過，尚未以兩輪warm full regression採用效能claim。
- `2026-08-20` complete regression量測：第一輪八組測試均通過，但telemetry與authoritative result
  同層而被final verifier正確拒絕；telemetry移入獨立子目錄後，第二輪aggregate通過，11,302
  executed／0 failed／8 optional-public skips。兩輪test-work為907.4與918.5秒，中位約913秒，較
  1,353.3秒基線改善32.5%；前三高peak RSS合計約7.6 GiB。Integration-UI降至296–303秒，符合
  移除重複human-like capture預期。Final exact source仍須再跑完整 regression與canonical handoff，
  本checkpoint不宣稱handoff-ready。
- `2026-08-20` final family／script cleanup：全部534個baseline files完成family-level disposition。
  刪除只剩mock delegation且已被unit controller覆蓋的training-controller integration、混入純float
  tautology／重複UI unit／重複ApplicationService state的integration/training file，以及已被一般三模型
  minimum-sample contract吸收的epoch-duration regression。移除format-matrix在unit suite內重跑完整CLI
  workflow；canonical strict GateSpec仍執行真CLI。Standalone checkout從10次heavy subprocess收斂為
  全script AST順序guard＋1次unrelated-cwd真啟動。Human-like payload與atomic publication tests共用一次
  exact immutable source snapshot；真capture仍在開始／結束各refresh。相對上一輪11,302 outcome，預期
  預估node delta原為31；final authoritative attestation已取代人工估算，exact denominator為11,265。
  File-level deletion仍精確是22個重複training案例所在檔、5個mock-controller案例所在檔、2個
  absorbed regression、1個duplicate CLI與1個只保護已刪不存在路徑的source-guard；pytest參數展開與
  partition aggregate只採attestation真值，不再用手算作claim。
- `2026-08-20` final complete regression：exact commit `50dd6d41` 的八組aggregate PASS，11,265
  collected／executed、11,257 passed、8個既有 `optional_public_fixture` skips，0 failed／error／
  xfail／xpass／deselect。Runner wall約790秒（13分10秒），相較baseline 1,353.293秒改善41.6%；
  `linux-unit-scripts` 由約546.7秒降至256.3秒。Phase-1 longest為UI 371.0秒，phase-2 longest為
  integration-rest 324.1秒；所有group telemetry可用，前三同時執行group peak RSS低於可用RAM的
  stop threshold。這閉合complete-regression目標，但planning更新後的final candidate仍須由下一次
  canonical handoff在同一source重跑並產生dossier。

## Focused validation 與 stop condition

- Behavior-preserving refactor先跑passing characterization，不製造人工red test。刪除前必須先有
  replacement；刪除後用同一 mutation question確認replacement會紅。
- Root conftest先跑受影響 subtrees，再跑所有 Linux groups與native lifecycle。Global fixture未收斂前
  不啟動runner parallelism。
- Runner／attestation修改不得改 eight-group membership、coverage filenames、outcome policy或允許新
  skip／xfail／deselect。任何 flaky、OOM、native abort、leaked process或無法解釋的count下降立即回退
  該 checkpoint。
- Qt、PyTorch、MNE與native驗證使用 `prlimit --core=0`和明確 timeout，只終止本 runner建立的 PID。
- `scope-complete`：全部test families、global fixtures、same-tier duplicate execution與critical path均已
  有完成 disposition，focused／complete regression通過。
- `handoff-ready`：同一 exact source的canonical dossier、remote CI、artifacts與手測指令完成；使用者
  通過前仍是待合併 candidate。
