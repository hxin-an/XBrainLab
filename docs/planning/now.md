# XBrainLab Now

最後更新：`2026-09-03`

## Current baseline and release decision

`d60e9cac528014dc9b4e1e36f1b0339c92e9519f` 是目前 `main`／`origin/main` 的產品基線，已包含
PR #107 與 PR #108；兩者的 exact source、CI 與適用的使用者驗收都已閉合。Repo-root `settings.json`
的本機修改由使用者擁有，
不得 stage、commit、revert、覆寫或隱藏。

下一個工作目標不是 signed installer，而是可從乾淨 checkout 重建的 **Windows source/developer
environment**：Poetry 管理 repo-root `.venv`，Windows CUDA 使用者完成一次明確同步後，日常可直接執行
`poetry run python run.py --model local`。Windows 必須明確選擇 `cpu` 或 `cuda` extra，Windows CI 選擇
CPU contract；不得把 WSL／offscreen evidence 當成 Windows desktop acceptance。

## Active program — Windows Poetry/CUDA convergence and one-command bootstrap

### Problem and evidence

1. Windows 乾淨 Poetry 解析目前從 PyPI 取得 CPU PyTorch。先前 Windows CUDA 手測依賴
   `build/manual-windows-pr107/.venv` 內的手動 pip 覆寫，因此不可重建，之後執行 `poetry sync` 也可能退回 CPU。
2. 已吸收的 worktree、CRLF-only clone 與 `/tmp/xbrainlab-*` 驗證產物已清除。目前只刻意保留
   `build/manual-windows-pr107` 作為唯一可工作的 CUDA fallback；新的 `.venv` 驗證成功前不得刪除。
3. Windows Poetry 2.3.3 launcher 原先綁定已移除的 `C:\ProgramData\miniconda3\python.exe`，無法執行；
   已依使用者明確授權用官方 installer 重建 Poetry 2.3.4，並將官方 launcher 目錄補進 user PATH。

### Outcomes

- 從 PR #107 合併後的最新 `main` 建立一條短 setup branch，加入官方 `cuda` extra 與 explicit
  PyTorch CUDA 13.0 source；不以 post-install pip 覆寫製造第二套 dependency truth。
- Windows repo-root `.venv` 明確使用既有 CPython 3.12。`poetry sync --with llm -E cuda` 安裝
  `torch==2.11.0+cu130`、`torchvision==0.26.0+cu130`、`torchaudio==2.11.0+cu130`；CPU 環境使用
  `poetry sync -E cpu`。兩個 extra 互斥，不支援在 Windows 省略或同時選取。
- 已下載 source checkout 的 Windows 10／11 x64 使用者只執行 `setup-windows.cmd`。缺少 Python 3.12 x64 時，
  先由 WinGet 補齊這個小型 stage-0 prerequisite；之後顯示完整計畫並以唯一一次確認 gate Poetry、repo `.venv`、
  數 GB dependencies／Granite model、runtime驗證與啟動。這是 source bootstrap，不是 signed installer。
- 新環境與 native app 驗證通過後，移除已吸收的 worktree、舊 manual/dev env 與精確列出的暫存產物；保留
  dataset、Granite model cache、Poetry wheel cache、logs、使用者輸出與有獨立未合併工作的 branch ref。

### Scope, non-goals, assumptions, and ownership

- Bootstrap slice 只新增 Windows source setup／launcher、既有模型下載 lifecycle 的 CLI adapter、安裝文件與
  直接 contract tests；不改 UI、Assistant model catalog、runtime command semantics、EEG workflow、Git checkout
  或 `.python-version`。Full Ruff gate原有的12個mechanical findings只作直接validation dependency cleanup：
  移除失效noqa、整理import、改用`datetime.UTC`與固定analyzer UTF-8 decoding，不改product behavior。
- 官方 package source使用 explicit priority；CPU/CUDA 以 Windows platform 與 `cpu`／`cuda` extras 的互斥 marker解析。
  Poetry contract 為 `>=2.3,<3`，lock 由 Poetry 2.3.4 產生。
- 同一 checkout 若同時供 Windows 與 WSL 開發，repo-root `.venv` 只屬於 Windows；WSL 以
  `POETRY_VIRTUALENVS_IN_PROJECT=false` 使用自己的 cached environment，不操作 Windows `.venv`。
- Complexity review（new-feature `>800 LOC` threshold triggered）：既有 source 沒有 Windows native install owner；
  完成後只有一個 bootstrap coordinator負責 prerequisite admission 與 setup sequence（owner delta `+1`），模型下載、
  cache policy與async cleanup仍由`ModelDownloadLifecycle`擁有。實際 packaging／adapter production為
  `+1,013 / -1 / net +1,012 LOC`、10 production／tooling files，UI LOC delta `0`。增加來自stage-0 Python discovery、pinned Poetry
  supply-chain verification、CPU／CUDA env convergence、runtime/model verification與recoverable failure paths；
  沒有新增第二套download/cache policy。Deletion/reuse已把重複手動setup降為advanced recovery並沿用既有model
  owner；WSL launcher語意不同，不共用。拆分保持為兩個可審查commit（dependency/lock contract與bootstrap public
  command）但同一PR一起驗證，避免合併一個尚不能執行的半套入口；若總slice達`1,500 LOC`或再增加owner則拆PR。
  若需要第二個模型下載owner、silent pip patch、自動安裝NVIDIA driver、remote pipe-to-shell或signed installer
  claim，立即停止另行決策。
- 本 program 沒有可見 UI 修改；使用者已於`2026-09-01`明確允許刪除
  `XBrainLab/ui/main_window.py`的一個失效lint註解。它不改layout、文案、互動或runtime，故screenshot不適用；
  Windows native launch仍須真人驗收。

### PR #109 handoff blocker — Basedpyright environment discovery

#### Evidence and outcome

- PR #109 exact head `8d30b8524480af6793d83a3982e7ba9b1003f485` 的最新 handoff dossier在
  `basedpyright` gate記錄：`poetry run -- python scripts/dev/run_basedpyright_regression.py`
  以 status 2 失敗，訊息是「did not resolve the pinned PyQt6 types」；source snapshot穩定，只有
  使用者擁有的`settings.json` dirty exception。
- `scripts/dev/run_basedpyright_regression.py`以`basedpyright --pythonpath sys.executable`
  執行暫存 `PyQt6.QtCore.QObject` sentinel。唯讀 `/tmp` probe顯示即使選取有 PyQt6 6.10.2、`py.typed`與
  `QtCore.pyi` 的健康 Poetry cached env，verbose search path仍未含該 env的`site-packages`，並顯示
  `Could not import 'PyQt6.QtCore'`。repo config將`reportMissingImports`設為`none`，所以 JSON沒有
  missing-import或期待的`reportAssignmentType` diagnostic，sentinel正確 fail closed。
- 對照以 Basedpyright 的`venvPath`／`venv` route指向同一健康 env，search path會納入`site-packages`，且
  `QObject = 1` 產生預期的`reportAssignmentType`。因此不是 PyQt6 lock、stub或 product type defect，而是
  gate runner的 interpreter-to-site-packages discovery seam。PR #109的CI皆成功但 workflow未執行此
  `basedpyright` gate；CI的`poetry sync`／runtime成功不能作為此 gate的通過證據。

#### Scope, non-goals, assumptions, and ownership

- Outcome是讓 canonical handoff `basedpyright` gate以實際 gate interpreter解析已 pinned 的 PyQt6 types，
  同時保留 sentinel 的 false-green 防護。修復只限
  `scripts/dev/run_basedpyright_regression.py`與其 focused tests；不改 PyQt6／Poetry lock、baseline、
  product source、UI、CI workflow或 public contract，不新增 module、owner或第二條 command spine。
- 假設 gate可由現有 Poetry environment取得足以推導其 venv identity的資料；不得把 cached env的機器特定名稱
  寫入追蹤設定。repo-root `.venv` 是本輪 ignored 的環境殘留：WSL須維持
  `POETRY_VIRTUALENVS_IN_PROJECT=false` 使用自身 cache，Windows `.venv` 不得被此診斷／修復刪除、重建或修改。
  `settings.json`仍屬使用者，絕不可碰。沒有可見 UI 變更，UI 確認：N/A。

#### Repair sequence and validation

1. 先以 focused red test刻畫真實 analyzer resolution：健康 temporary venv route必須看見 PyQt6並取得
   sentinel `reportAssignmentType`；現有 `--pythonpath` route不可再被誤判為足夠。測試不得依賴 machine-specific
   cached env name，且維持 baseline read-only。
2. 僅在 runner內以 Basedpyright 可辨識的 venv discovery route取代失效的`--pythonpath` seam，從 gate interpreter
   推導，不另存 public config truth；保留 version pin、temporary probe、UTF-8 JSON、fail-closed error與 full
   project analyzer invocation。
3. Focused green：runner unit tests加上可重現的 CLI/environment-resolution coverage，現有 baseline、version、
   stale/empty sentinel rejection與 canonical handoff argv contract都通過；在已完整同步的正確 Poetry env重跑
   `poetry run -- python scripts/dev/run_basedpyright_regression.py`。
4. 該 exact head 的 focused gate通過後，才重跑 canonical full handoff manifest。任何 probe仍未載入
   `site-packages`、PyQt sentinel未產生`reportAssignmentType`、baseline被改寫、需改 lock／產品／UI、或依賴
   machine-specific env名稱時停止；不要以移除 sentinel、重新開啟／壓掉 missing-import或宣稱CI pass取代 gate。

#### Complete-regression handoff blocker — test-only lifecycle and lock reliability

##### Evidence, scope, and non-goals

- 在 exact `b92eecdeb1bec0b79b584450b0d11bc6761e73d1`，以 WSL cached Poetry environment、
  `POETRY_VIRTUALENVS_IN_PROJECT=false`、`POETRY_INSTALLER_RE_RESOLVE=false`及`prlimit --core=0`
  從頭執行 canonical manifest。Section 1（Git、Ruff、Basedpyright、MkDocs）與
  `architecture-compliance`通過；`complete-regression` fail closed。這與 b92 的 production diff 無關，
  但使 canonical handoff evidence 不成立。
- Red evidence 有兩條：`tests/unit/ui/test_data_splitting.py` 的三個
  `DataSplittingPreviewDialog` construction seams 以未設定`is_alive=False`的 fake `threading.Thread`
  建立自動 preview；qtbot teardown 將它視為仍存活，5 秒後 deferred retry 呼叫 blocking warning modal，
  污染後續 UI tests。另一條是
  `tests/unit/llm/rag/test_security_policy.py::test_embedding_publication_lock_is_bounded_across_processes`：
  POSIX holder-ready 15 秒在 measured parallel contention 下不足而逾時；Windows already uses 60 秒，
  product publication-lock deadline仍為 0.2 秒。
- Scope 只限上述兩個 test files 的 test-harness reliability repair。不得改 product UI、
  data-splitting preview worker owner、RAG lock owner、publication-lock deadline、local handoff scheduler、
  shard registry、aggregation policy、Poetry lock或 settings。沒有可見 UI 行為修改；UI confirmation：N/A。

##### Repair sequence and validation

1. 在三個 UI construction seams 使用 source-local preview-thread fake，並明確設定
   `is_alive=False`；不以 production timeout／warning fallback遮蔽 test ownership。
2. 只將 POSIX holder-ready test budget與既有 Windows 60 秒對齊；不放寬鎖取得／發布或 product deadline。
3. Focused green 必須重跑兩個直接 test selectors及直接相鄰 preview lifecycle tests，確認沒有 deferred modal、
   holder-ready 仍可觀察到跨 process admission；不得將 skip、auto-accept modal或 retry 當成通過。
4. 之後從頭重跑同一 exact SHA canonical full manifest，讓 eight-group attestations、coverage及 required
   selector terminal evidence 正常產生。若任一 phase-1 或尚未執行的 phase-2 group失敗，停止於其新的
   evidence，不改 aggregator 來拼接／隱藏缺失 records。

### Implementation sequence

1. **完成**：PR #107 已在 exact `c5df65fb` 通過驗證、使用者批准並合併為 `d60e9cac`。
2. **完成**：主工作目錄已同步，已吸收 worktree／branches、CRLF-only clone 與列名 `/tmp` artifacts已移除；
   manual CUDA fallback仍保留。
3. **完成**：從 clean latest main 建立單一 Poetry/CUDA branch，PEP 621 metadata、官方 CPU／cu130 explicit
   sources、互斥 variants、lock、focused contract test 與現有開發文件已更新；實際 wheel metadata 保留 base
   dependencies 與 Windows CUDA extra。
4. **完成**：Windows Poetry 已以現有 CPython 3.12 重建。第一次以預設 `installer.re-resolve=false`
   同步的實測日誌顯示 CPU/CUDA wheels 同時覆寫；同一 lock 以 `re-resolve=true` dry-run 只選 CUDA variant。
   因此以 ignored project-local Poetry config 與 CI environment固定此 installer contract。污染的 repo-root
   `.venv` 已精確移除並乾淨重建；CPU dry-run 只會切換三個官方 `+cpu` wheels，CUDA sync 連跑兩次皆為
   no-op，且目前環境只有單一 `+cu130` variant。Pre-commit 的 `poetry-check` 也固定為同一個 2.3.4：

   ```powershell
   poetry config virtualenvs.in-project true --local
   poetry config installer.re-resolve true --local
   $python = py -3.12 -c "import sys; print(sys.executable)"
   poetry env use $python
   poetry sync --with llm -E cuda
   poetry env info --path
   poetry run python run.py --model local
   ```

5. **完成**：failing contracts已固定單一入口、stage-0 WinGet Python、唯一multi-GB確認、verified Poetry 2.3.4、
   R580 CPU／CUDA選擇、recoverable invalid `.venv`、model lifecycle delegation、重跑與failure exit；實作後
   241個directly coupled tests、architecture compliance、Poetry lock、package build、MkDocs strict與full Ruff
   均通過。Windows native `-PlanOnly -Cpu`正確選CPU，`-Yes -NoLaunch`重跑為dependency no-op、CUDA 13.0
   可用且complete model cache未重下載；Windows focused tests為37 passed，native Basedpyright regression亦PASS。
   公開overrides只有`-Cpu`、`-Yes`、`-NoLaunch`、`-PlanOnly`。
6. **Current**：PR #109 的前兩個 exact heads 已通過本機與 Windows native gates，但 CI 在 macOS ARM64
   dependency install fail closed。`a461c2c8` 證明不得對非 Windows 傳入 `-E cpu`；`28643a77` 進一步證明
   即使不啟用 extra，全域 `POETRY_INSTALLER_RE_RESOLVE=true` 仍會讓 Poetry 2.3.4 錯選 cu130 local-version。
   修理只限 CI resolver admission：Windows runner 明確使用 `re-resolve=true`與`-E cpu`，Linux／macOS使用
   `re-resolve=false`且不啟用Windows-only extra，讓 lock markers選既有platform wheel；不改 lock、bootstrap
   或 runtime。修後對新 exact head 重跑全套 automated gate與Windows native launch／真人acceptance。使用者
   明確手測通過並同意 merge後才合併；最後回到 latest main重驗並刪除 fallback／task worktree／精確暫存項目。

### Focused validation

- Dependency contract：focused TOML／lock test、`poetry check --lock`、package build、Ruff；Windows CI明確
  使用`re-resolve=true`與`-E cpu`，Linux／macOS固定`re-resolve=false`且不啟用Windows-only extra，CUDA
  source只能在 Windows `-E cuda` 被選取。
- Windows clean env：`poetry env info --path` 指向 repo-root `.venv`，Python 3.12，三件套皆為 `+cu130`，
  `torch.version.cuda == "13.0"`、`torch.cuda.is_available() is True`，PyQt6／Transformers／BitsAndBytes可 import；
  同一 sync連跑兩次仍保持 CUDA。
- Bootstrap contract：behavior tests覆蓋driver `<580`／`>=580`、CPU override、唯一確認的取消／零project
  mutation、invalid `.venv` recoverable rename、Poetry checksum failure不執行、no-launch、async model terminal、
  cancellation與非零exit；model lifecycle另覆蓋pinned complete-cache skip。缺少CPython時的stage-0只允許exact
  WinGet package，`-PlanOnly`不得安裝；完整missing-Python路徑仍屬Windows native acceptance，不以source scan冒充。
- Native walkthrough：在含空白／非 ASCII checkout以 `setup-windows.cmd` 完成一次確認、環境與模型 setup並啟動；
  第二次執行不重複下載。檢查 Assistant、關閉生命週期及 offline既有 cache。自動／WSLg evidence不取代
  Windows真人驗收。

### Stop and completion conditions

- Resolver 若同時安裝 CPU/CUDA variants、非 Windows解析 CUDA、需要 silent fallback、或 clean second sync退回 CPU，
  停止；不以手動 pip掩蓋。
- Bootstrap 若必須覆寫有效環境／settings、無法把模型下載交給既有 lifecycle、需要自動 driver／reboot、或不能在
  失敗時保留可重跑狀態，停止而不以廣泛刪除掩蓋。
- 刪除前若發現真實未提交差異、活動程序、唯一資料／模型／log或未合併工作，保留並回報；不用廣泛 glob刪除。
- 完成時 `main == origin/main`、Git只剩使用者的 `settings.json`、`git worktree list`只剩主目錄、Poetry指向
  repo-root `.venv`；若缺少Python，stage-0只先補CPython 3.12 x64，之後`setup-windows.cmd`的唯一確認才允許
  Poetry／project env／dependency／model mutation並使用正確variant與完整cache啟動。準確宣稱仍是可重建的
  Windows source/developer environment，不是 signed installer。
