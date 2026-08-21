# XBrainLab Now

最後更新：`2026-08-21`

## 目前焦點

`refactor/test-quality-runtime-v1` 已由 PR #43 在 exact head
`f97f0be636f9465a4303581f0943e29ae9a4150e` 完成 40/40 canonical handoff、remote CI 與使用者核心
workflow 手測，並以 merge commit `616eda0a261560d17cfa35dc93e5906115e5c14e` 合併至 `main`。

目前唯一 active slice 是 branch `ci/native-platform-reliability-v1`：先讓 CI 能對 **原生 Windows
source checkout** 提供可信、可追溯、fail-closed 的啟動與小型產品 lifecycle 證據；macOS 以相同
source-run 方式提供 best-effort 支援。這條 branch 完成、經使用者 Windows 真人手測並合併後，才開始
Braindecode vendoring。Data Import 與 4B Assistant 模型均不在本 slice。

目前 checkpoint：A／B／C 的本地施工已完成；exact-source provenance、locked bootstrap/cache、native
Windows／macOS source smoke、clean owned-tree shutdown及required artifact逐項驗證均已落地。Focused CI／
startup contracts共131項通過，changed developer scripts的BasedPyright為0 error；本機offscreen另完成真
五panel／ApplicationService／clean shutdown與真`run.py` entrypoint smoke。下一個也是唯一 remaining step是
freeze exact branch head、取得remote Windows／macOS／Linux current-head CI與artifacts，然後交使用者做原生
Windows手測；remote evidence與使用者批准前仍只稱checkpoint，不稱handoff-ready或可merge。

## 問題與證據

- Current GitHub Actions 已在 Windows／macOS 跑 `platform-core-contracts` 與
  `platform-product-lifecycle`，Windows 另有原生 Qt `windows` plugin 的 100／125／150% DPI capture；
  這些是有價值的 component／lifecycle 證據。
- PR jobs 預設 checkout GitHub merge ref，但 artifact 沒有記錄 checked-out HEAD、PR head／base、run ID
  或 attempt；green check 不能單獨證明 repo policy 要求的 exact PR head。
- Linux 八 shard aggregate 能拒絕 missing／unknown result與coverage fragment，但 aggregate artifact未保存
  每個 shard 的 source provenance，Windows／macOS／UI／public artifacts 多數仍允許
  `if-no-files-found: warn`。
- CI 每個 job 執行未固定版本的 `pip install poetry`；`.venv` cache key 缺少architecture與Poetry
  version，並以 broad restore key復用舊lock環境。Current lock由Poetry `2.3.4`產生。
- `scripts/dev/run_startup_smoke.py` 看到 `MainWindow initialized` 後，即使 GUI 只能由25秒timeout強制
  終止仍可判定passed；它不能證明Qt event loop、MainWindow workers與owned children能乾淨關閉。
- 近期存在兩種必須分開的失敗：Windows assertion／lifecycle failure屬repo failure；GitHub
  ArtifactService、codeload、429／503／timeout屬provider control-plane failure。Provider failure可在服務
  恢復後重跑，但不能改寫為pass，也不能藉retry pytest掩蓋真紅。

## Observable outcome

1. PR workflow明確測試PR head SHA；每個authoritative job保存同一schema的source provenance，Linux
   aggregate拒絕missing、stale、duplicate或互相矛盾的provenance。Final merge另核對current base。
2. Poetry固定為`2.3.4`；cache identity含OS、architecture、Python、Poetry與lock hash，跨lock不再復用
  舊`.venv`；安裝使用`poetry sync --no-interaction`清掉stale packages。
3. Existing GitHub actions固定到其已核准major目前解析出的immutable commit SHA；不在本slice猜測或
   升級未知major。
4. 原生Windows以Qt `windows` plugin真正啟動`run.py`／MainWindow、materialize五個主要panels、走一條
   真ApplicationService小型lifecycle，並由正常Qt close path以return code 0結束；timeout、強制kill、
   native abort、殘留worker或owned process全部失敗。
5. Windows native source-run使用獨立Windows-only step，不繼承platform matrix的
   `QT_QPA_PLATFORM=offscreen`；它必須保持該變數unset，記錄並要求
   `QGuiApplication.platformName() == "windows"`，且把`TEMP`、`TMP`、application settings與cache
   roots隔離在同一個含空格與非ASCII字元的owned path。Windows完整platform tests保留Python 3.11；
   另以Python 3.12跑source startup smoke。
6. macOS在current ARM runner完成locked source install、platform tests與bounded clean startup／shutdown；
   startup probe記錄並要求native `cocoa` plugin；headless CI不宣稱互動式3D、notarization或真人desktop
   acceptance。
7. Linux八shards、Windows／macOS lifecycle、Windows DPI與其provenance都是required evidence；缺少
   required artifact必須fail。Provider transport failure以清楚分類保留為incomplete evidence，不能讓job
   通過。
8. Final exact branch head的focused contracts、remote CI與required artifacts全部成功後，才交使用者在
   原生Windows做source install、啟動、panel navigation、小型資料流程、close／reopen。使用者明確同意
   前不合併。

## Scope／non-goals

- In scope：`.github/workflows/`、CI scope／attestation／provenance developer scripts、startup smoke、
  platform-focused tests、直接必要的`run.py` developer-only clean-exit seam，以及準確文件。
- Non-goals：不做installer、signing、notarization、WSLg launcher redesign、GPU／CUDA、Local Assistant、
  Braindecode、Data Import、test shard刪除、timeout放寬或generic retry system。
- 正常產品啟動、UI layout、copy與workflow行為不得改變；本slice不修改`XBrainLab/ui/`。User-visible UI
  modification authorization：not applicable。使用者已明確授權原生Windows source-run與CI施工。
- Owners before／after不變：GitHub workflow仍是remote routing owner；`run_tests.py`仍是platform test
  membership owner；`run.py`仍是產品entrypoint。新增的provenance／smoke資料只是pure DTO／validator，
  不建立第二套CI scheduler、product state或lifecycle owner。
- Deletion candidates：timeout-is-success startup判定、unversioned Poetry bootstrap、cross-lock restore key、
  required artifact的warn policy與過時PyVista workflow註解。

## 施工順序

### A. Exact-source與bootstrap contract

1. 建立最小immutable CI provenance payload與validator：event、run／attempt、expected ref、PR head／base、
   checked-out HEAD／tree。所有authoritative jobs使用同一helper；PR checkout明確指定head SHA。
2. 擴充Linux aggregate，保存八個raw shard attestations／provenance並拒絕不一致source；不修改八組
   membership、coverage與pytest outcome policy。
3. 固定Poetry與cache identity，移除broad restore fallback，改用sync install；用workflow contract tests
   保護Windows、macOS、Linux與public lanes。
4. 將現有official action major解析成審查過的immutable SHA並保留version註解；無官方核實時停止該項，
   不自行猜測版本。

### B. Native startup與小型產品lifecycle

1. 先建立current startup smoke characterization：`MainWindow initialized`但timeout仍passed。
2. 新增developer-only bounded startup選項，使MainWindow顯示並進入event loop後由產品close path關閉；
   timeout改為failure，artifact記錄initialized、close requested、return code、timed out與bounded log tails。
3. 在Windows native Qt `windows` plugin執行startup；Python 3.11沿用完整platform groups，Python 3.12只跑
   startup smoke避免複製整套suite。Native step不得設定`QT_QPA_PLATFORM`，並以含空格／非ASCII字元的
   owned temp／settings／cache roots執行；macOS probe同樣驗證`cocoa`而非offscreen。
4. 新增一條lower-mock platform smoke：真MainWindow／ApplicationService、五panel materialization、
   `QueryStateCommand(query="state")`的initial publication、空session的`NewSessionCommand()`既有
   no-confirmation安全執行與generation transition，以及clean shutdown。非空session的destructive
   confirmation由既有ApplicationService contract測試保護，不在native smoke繞過command spine偽造資料。
   這條流程不得讀取EEG fixture或進Data Import；macOS跑相同非3D範圍。

### C. Artifact policy與final candidate

1. Required producer在upload前驗證artifact schema／source，並將`if-no-files-found`改為`error`；producer
   command本身仍須return 0，artifact不能取代測試結果。
2. 保留`cancel-in-progress: true`；cancelled舊SHA不能認列。只允許GitHub action本身對idempotent
   transport做bounded retry，不在repo重跑pytest、coverage或attestation。
3. 每個meaningful checkpoint由最多兩個唯讀subagent gate：release／platform reviewer與
   validation reviewer。Blocker以後續commit關閉，不讓subagent與root同時改同檔。
4. Branch freeze後只push一次final candidate；核對所有scope-derived non-skipped checks與required
   artifacts。提供原生Windows手測指令與預期結果；source再變即撤銷批准。

## Focused validation

- CI scope／provenance：`tests/unit/scripts/test_ci_change_scope.py`與新增provenance contracts。
- Linux evidence：`tests/unit/scripts/test_run_tests.py`、pytest completion／aggregate attestation contracts。
- Workflow／artifact：既有CI public、human-like、UI visual contracts與新增platform artifact contract。
- Startup：`run_startup_smoke` unit／subprocess contracts，加Windows／macOS platform smoke selectors；後者
  精確驗證五panel、native Qt plugin、隔離roots、initial query publication、空session New Session
  no-confirmation capability與generation transition、clean exit；非空destructive confirmation另由focused
  ApplicationService contract驗證。
- Static：changed Python files的Ruff／format；workflow YAML parse與action／cache contract。
- 中途不跑complete regression或canonical handoff；remote platform workflow才是本slice的final evidence。

## Stop conditions

- 任一變更縮小Linux八shards、coverage、Windows／macOS、public-data或UI evidence範圍。
- 新增skip／xfail／deselect allowance、提高timeout或重跑pytest以取得green。
- Startup只能靠kill、worker／child未釋放、native abort、cache hit／miss結果不同或provenance不一致。
- 需要UI可見修改、新authoritative owner、installer／packaging或超出直接platform blocker的產品修正。
- GitHub provider outage：保留exact run／step evidence，等待Status恢復後重跑同SHA；不修改source追綠。
