# XBrainLab Now

最後更新：`2026-08-20`

## 目前焦點

從已手測並合併的 `main` merge commit `99d4bdfb9b746a26bddd379eb4ef48af32e66db7`
建立 `refactor/test-quality-runtime-v1`，全面清理測試、CI、handoff evidence 與本機 regression
runtime。這條 branch 會審查全部 tracked tests，不只處理幾個 E2E 檔；完成完整 handoff 與
remote CI 後才交使用者做核心產品 walkthrough，通過前不合併。

目前 phase：`CI artifact de-dup complete; measured runner candidate next`

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
  產生 29 次串行 pytest collection/process。低 CPU 利用率主要來自 fixed phase、process isolation、
  長尾 group 與 wait／IO，不是 GPU 沒被使用。
- GPU 只適合 Granite runtime、stable model eval 與 resource calibration；unit、Qt、IO、MNE
  與 CPU training tests 不得為提高 utilization 改用 GPU。

## Observable outcome

1. 全部 534 個 baseline test files 都取得 `keep | rewrite | move_rename | delete` disposition；
   family ledger 無未審查項目。每個 delete 都有 exact replacement 與 count delta。
2. 每個保留測試都對應 reachable defect、observable transition、real side effect 或明確 claim；
   mocked delegation 不稱 E2E，integration mock 不得取代同一 authoritative owner。
3. Root conftest 不再全域決定 modal outcome或 renderer availability。Fake renderer、accepted modal
   與 real modal 各由明確 opt-in fixture 擁有。
4. 重要 workflow 保留 lower-mock ladder：ApplicationService command、real EEG／public format、
   real artifact/history/reload、native UI／renderer與model gates各自只宣稱自己的 boundary。
5. Linux complete regression 仍執行相同八個 authoritative groups、coverage、completion
   attestation 與完整 collection。相同環境的 focused pytest 不再重跑；不同 environment／artifact
   claims 仍獨立執行。
6. Runtime work不以固定分鐘取代品質，但 complete regression 與 full handoff 的兩輪 warm median
   都必須有至少 10% 可重複改善；不得靠 skip、提高 timeout、縮小 denominator 或移除 unique
   evidence 達成。
7. Final exact branch head 的 focused baselines、完整 regression、canonical handoff、remote CI與
   artifact inventory全部通過後，才交使用者手測 Data Import → Preprocess → Epoch／Split →
   one-epoch Training → Evaluation／Saliency。

## 全量 family ledger

Git與pytest collection是 denominator authority；本表在每個 checkpoint 更新，Git commits保留 exact
file／replacement mapping，不建立另一份萬筆 test manifest。

| Family | Baseline files | Reviewed | Keep | Rewrite | Move／rename | Delete | Status |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| unit/backend | 186 | 1 | 0 | 1 | 0 | 0 | in progress |
| unit/llm | 77 | 0 | 0 | 0 | 0 | 0 | pending |
| unit/scripts | 70 | 1 | 0 | 1 | 0 | 0 | in progress |
| unit/ui | 120 | 3 | 0 | 3 | 0 | 0 | in progress |
| unit/root | 10 | 1 | 0 | 1 | 0 | 0 | in progress |
| integration/agent | 5 | 0 | 0 | 0 | 0 | 0 | pending |
| integration/backend | 10 | 0 | 0 | 0 | 0 | 0 | pending |
| integration/controller | 3 | 0 | 0 | 0 | 0 | 0 | pending |
| integration/debug | 1 | 0 | 0 | 0 | 0 | 0 | pending |
| integration/io | 9 | 0 | 0 | 0 | 0 | 0 | pending |
| integration/llm | 1 | 0 | 0 | 0 | 0 | 0 | pending |
| integration/pipeline | 14 | 6 | 1 | 0 | 4 | 1 | in progress |
| integration/training | 1 | 0 | 0 | 0 | 0 | 0 | pending |
| integration/ui | 25 | 5 | 0 | 3 | 1 | 1 | in progress |
| regression | 2 | 0 | 0 | 0 | 0 | 0 | pending |

## Scope／non-goals

- In scope：全部 test families、fixtures、mock scope、obsolete／duplicate tests、lower-mock
  replacements、source guards、CI／handoff duplicate execution、fixed runner topology、resource timing、
  orphan test/dev assets與validation docs。
- Non-goals：不修改產品行為、不把所有 unit 改成 integration、不追求 GPU 高使用率、不建立通用
  scheduler／distributed control plane、不用 test count 或 LOC reduction 當成功標準。
- 產品 owner 數前後均不變。Test policy 從 root-global substitutions 收斂成 scoped fixtures；runner仍由
  既有 `run_tests.py`／`run_local_handoff_regression.py` 擁有。
- CI 與 local handoff 是不同環境 claim；Windows、macOS、public-data、native、model與人工驗收不能
  被 Linux complete regression 取代。

## 施工順序

### A. Exact inventory and evidence taxonomy

1. 固定 exact tracked files、pytest node collection、八組 Linux partition、42-gate registry與 baseline
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
