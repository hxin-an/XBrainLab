# 本機開發環境

## 需求

- Python 3.11 或 3.12
- Poetry `>=2.3,<3`
- Git
- Qt、MNE、PyTorch 與本次要使用的 dataset reader 所需平台函式庫

選用的本機 Assistant 需要較多相依套件與儲存空間。只有任務涉及 Assistant runtime 時才安裝。

## 安裝相依套件

Linux／macOS 在 repository root 執行：

```bash
poetry sync
```

需要本機 LLM 時加入對應 dependency group：

```bash
poetry sync --with llm
```

Windows source checkout 的一般入口是下方的 `setup-windows.cmd`，不是這組手動指令。只有 bootstrap 的
明確錯誤需要人工恢復時，才手動選擇一套 PyTorch wheel；沒有 NVIDIA CUDA 需求時使用：

```powershell
poetry config installer.re-resolve true --local
poetry sync -E cpu
```

若 CPU 環境也要執行本機 Assistant，改為 `poetry sync --with llm -E cpu`。不要同時選取 `cpu` 與
`cuda` extras。

### Windows：一個命令建立 source Assistant 環境

對已下載的 Windows 10／11 x64 source checkout，從 repository root 的 PowerShell 執行：

```powershell
.\setup-windows.cmd
```

這是 source/developer bootstrap，**不是 signed installer**。若電腦沒有 CPython 3.12 x64，bootstrap 會先以
WinGet 安裝該小型 prerequisite；其後顯示計畫並只詢問一次。回答 `Y` 才會下載 Poetry 2.3.4、建立 repository-root
`.venv`、同步相依套件及下載 local model。它不會更新 Git、覆寫 `settings.json`、安裝／更新 NVIDIA driver，或在
確認前建立／替換 project environment。

Bootstrap 以 NVIDIA driver major version 判斷：R580 或更新版本選取 CUDA 13.0 的 `+cu130` PyTorch wheels；沒有
相容 NVIDIA driver 則選 CPU `+cpu` wheels。它只選取其中一個 Windows extra。預設 Granite 4.0 Micro 3B 模型約
6.82 GB，cache 目的地是 `%LOCALAPPDATA%\XBrainLab\models`；若使用者現有設定已選另一個支援模型，會保留該模型。
`.venv` 位於 checkout root，Poetry cache、model cache 與 setup log 不在 checkout 內。首次安裝通常還需要數 GB
給 `.venv` 和 wheel cache，請先確認磁碟空間。

成功後會啟動 XBrainLab。重跑同一命令會檢查並重用有效 `.venv` 和完整 model cache，而不是重複下載；若 `.venv`
不完整，會在確認後以可辨識的 `.venv.invalid-<timestamp>` 名稱保留，再重新建立。可用的參數如下：

```powershell
# 強制 CPU，即使可使用 CUDA
.\setup-windows.cmd -Cpu

# 已由自動化系統明確授權時才略過唯一確認；不建議日常手動使用
.\setup-windows.cmd -Yes

# 完成 setup 但不啟動 GUI
.\setup-windows.cmd -NoLaunch

# 只顯示計畫；不安裝 Python、不下載、不建立 environment 或啟動
.\setup-windows.cmd -PlanOnly
```

清理只針對確定不再需要的 local state：關閉 XBrainLab 後可刪除 checkout 的 `.venv` 來重建環境；刪除
`%LOCALAPPDATA%\XBrainLab\models` 會使下次 setup 重新下載模型；Poetry cache 與 `%LOCALAPPDATA%\XBrainLab\logs`
可依磁碟需求清理。不要從 WSL 刪除 Windows `.venv`，也不要刪除 dataset、training outputs 或使用者設定。

### Windows advanced recovery：手動 Poetry

若 bootstrap 的明確錯誤訊息需要人工診斷，才改用下列手動恢復步驟。這會在 repository root 建立 Poetry 管理的
`.venv`，並從官方 PyTorch CUDA 13.0 wheel source 安裝 `torch`、`torchvision`、`torchaudio` 的 `+cu130` 版本：

```powershell
poetry config virtualenvs.in-project true --local
poetry config installer.re-resolve true --local
$python = py -3.12 -c "import sys; print(sys.executable)"
poetry env use $python
poetry sync --with llm -E cuda
```

Project-local `installer.re-resolve=true` 讓 Poetry 依本次選取的 extra 只安裝一套 PyTorch wheel；產生的
`poetry.toml` 是 ignored machine state，不是第二份 dependency truth。可確認 CUDA 是否可用：

```powershell
poetry run python -c "import torch; print(torch.__version__); print(torch.version.cuda); print(torch.cuda.is_available())"
```

日常啟動不必再指定 Python executable：

```powershell
poetry run python run.py --model local
```

Windows CPU 同步使用 `-E cpu`，CUDA 同步使用 `-E cuda`；之後要保留 CUDA 環境時，仍使用
`poetry sync --with llm -E cuda`。這兩個 extra 只適用 Windows，Linux/macOS 維持 PyPI 解析，CI 明確
選取 `cpu`。

同一個 checkout 若同時從 Windows 與 WSL 開發，repo-root `.venv` 是 Windows environment，不能由 WSL
執行或同步。WSL 應覆寫 machine-local 位置，使用自己的 Poetry cached environment：

```bash
POETRY_VIRTUALENVS_IN_PROJECT=false poetry sync
POETRY_VIRTUALENVS_IN_PROJECT=false poetry run python run.py
```

這不會替換 repo-root 的 Windows `.venv`。不要從 WSL 刪除或修改該目錄；Windows 的同步與啟動仍回到
PowerShell 執行。
若要完整重建，先關閉 XBrainLab，以 `poetry env info --path` 確認目標確實是本 repository 的 `.venv`，
再執行 `poetry env remove --all`；這只刪除 Poetry environment，不刪 dataset、Granite model cache或輸出。

不得隱式下載或替換模型。模型 identity、license、quantization、cache 位置與容量上限都屬於產品
決策。

## 啟動應用程式

### 多 worktree：固定手測環境

重複手測不在每個 worktree 執行 bootstrap／`poetry sync`。Windows 共用一套已驗證的原生
`.venv`；WSL 共用另一套 Linux environment，不能交叉使用。新 worktree 只放 source。
依賴真的改變時，先關閉使用共用環境的程序，再明確同步；日常啟動不安裝、不下載。

Windows 固定手測 checkout 位於 `D:\workspace_v2\projects\lab\xbrainlab-manual`，不放在
可清理的 `build` 裡。預設 Python 為主 checkout 的 `.venv\Scripts\python.exe`，模型與
embedding 共用 `D:\XBrainLabCache`；其他機器可用 `-Source`、`-Python`、`-Cache` 指定。
使用本次交付的完整 SHA，不以 branch 名稱或「最新」代替：

```powershell
$candidate = '<完整 40 字元 commit SHA>'
# entrypoint 可由 agent 複製至固定 Windows tools 目錄；兩個檔案須來自同一版本。
$entrypoint = '.\scripts\dev\manual_windows.ps1'
& $entrypoint -Sha $candidate -Action prepare
& $entrypoint -Sha $candidate -Action check
& $entrypoint -Sha $candidate
```

`prepare` 不 fetch、不 force checkout，先檢查 source 乾淨與目標的 Python／直接依賴 lock
版本；環境不符時拒絕切換，請診斷後明確同步。此檢查不是全部 transitive dependencies 或
產品 workflow 的驗證。`launch` 另檢查實際 import provenance 與 pinned cache 完整性，強制
Windows Qt 和 offline model mode。只有一個 PowerShell console 作為即時 log。
OS lock 與同一使用者的程序檢查阻擋同時 prepare／launch／clean；這不是跨帳號管理工具。
不要繞過入口手動切換執行中的 source。

每個 SHA 的 settings、Qt settings、logs、一般 data/cache 與工作目錄隔離於
`build/manual-runs/<SHA>/`，不覆寫主 checkout 的 `settings.json`。預設 training output
位於該 run 的 `work/output/`。重要結果應另存到此目錄之外；自訂 output 路徑不會自動清理。
失敗保留重現資料；真人明確驗收且應用程式退出後，先預覽再清理：

```powershell
& $entrypoint -Sha $candidate -Action clean
& $entrypoint -Sha $candidate -Action clean -Apply -Accepted
```

只刪除身份相符 run 的 `work/output/`，不刪 data／cache／logs／settings／evidence，也不掃描 `.pth` 等
副檔名。刪掉的測試權重需重新訓練；尚未匯出的重要結果不可加入清理。

WSL worktree 直接使用保留的 interpreter；不要因目錄 hash 不同建立另一套 Poetry env：

```bash
export VIRTUAL_ENV=/home/administrator/.cache/pypoetry/virtualenvs/xbrainlab-IiX9BmR2-py3.12
export PATH="$VIRTUAL_ENV/bin:$PATH"
python -m pre_commit install
python -m pytest --capture=sys tests/path/test_file.py -q
```

其他機器改用其已驗證環境。Hook 遷移並驗證、確認無程序／設定引用後才能刪舊環境。
Granite／embedding snapshots、原始資料與未知研究結果不屬於可拋棄的安裝 cache。

### WSL 原地壓縮：離線 Windows 步驟

刪 Linux 檔案不代表 Windows 的 VHDX 立即縮小。`scripts/dev/compact_wsl.ps1` 只處理目前
Windows 使用者註冊的 `Ubuntu-24.04`，不搬家、不 unregister、不處理 `Ubuntu-24.04-clean`。
將腳本複製到 Windows 磁碟，再從 PowerShell 執行；不能依賴即將停止的 WSL UNC 路徑。

```powershell
# 預設只讀預覽
& D:\XBrainLabCache\tools\compact_wsl.ps1
# 保存工作並自行停止 WSL；再以同一使用者的系統管理員 PowerShell 執行
& D:\XBrainLabCache\tools\compact_wsl.ps1 -Apply -Verbose
```

腳本不替你 shutdown／terminate WSL。Apply 要求所有 WSL 已停止、磁碟未被占用，且
`E:\XBrainLabBackups` 的 NTFS 空間足以容納完整 VHDX。完整備份及多次 hash 可能耗時數十分鐘，
`-Verbose` 會在同一 PowerShell 顯示目前階段。先建立私有、不可覆寫且 hash 驗證
成功的備份，才允許 DiskPart 原地壓縮；失敗時保留備份與診斷，不自動還原或刪除。
任何占用／身份／備份／壓縮驗證不明確時停止，不回報成功。操作期間不得重開 WSL／Docker。
原理與限制見 [Microsoft compact vdisk](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/compact-vdisk)。

成功後最小啟動檢查不等於資料驗收。仍需核對 WSL 使用者、Git／SSH、共用環境、資料與模型
存取。備份至少保留 7 天，確認正常並取得明確同意後才清除。只有實際執行前後的磁碟量測
能代表回收量；腳本測試或預覽不代表已把空間還給 C 槽。

### 一般單 checkout 啟動

```bash
poetry run python run.py
```

Repository root 的 `settings.json` 保存本機 runtime 設定，不屬於 feature change，必須維持
uncommitted。

## Windows 上透過 WSLg 輸入中文

這個步驟只適用於已配置的開發 checkout：Windows launcher 會在 WSL 的 Qt/XCB runtime 中啟動
XBrainLab，不是 signed Windows installer。Windows 的輸入法不會直接成為 WSLg 內 Linux Qt 視窗的
輸入法；請在 WSL Ubuntu 內設定 IBus Chewing（酷音／注音）。

### 第一次設定（Ubuntu 24.04）

在 WSL Ubuntu terminal 執行一次：

```bash
sudo apt update
sudo apt install ibus ibus-chewing
```

接著在有 WSLg 圖形環境的 WSL terminal 執行：

```bash
ibus-setup
```

在 **Input Method** 分頁選 **Add**，加入 **Chinese → Chewing（酷音／注音）**，再到 Chewing 設定
選取 **標準大千** 鍵盤配置；完成後關閉設定視窗。這是使用者選擇及切換的 IBus engine 與鍵盤配置。
launcher 只檢查 IBus／engine 是否可用；它不會替你執行 `sudo`、安裝套件、選取或改寫全域 engine。

若設定程式沒有立即顯示候選字視窗，先確認 daemon 是否已存在：

```bash
ibus address
```

若此命令失敗，才啟動目前使用者尚未執行的 daemon：

```bash
ibus-daemon --daemonize --xim
```

不要使用 `--replace` 或停止既有 IBus 程序；已有 daemon 時保留它的現況與使用者選取的 engine。
然後重新啟動 XBrainLab。請在 Assistant 輸入框確認可組字、選候選字、退格及切換中英文；組字時
的 Enter 應先確認候選字，而不是送出訊息。

### 正常啟動

從 Windows PowerShell 在 repository root 執行：

```powershell
$env:XBRAINLAB_REPO_WIN = (Get-Location).Path
& .\scripts\launchers\xbrainlab_wsl_launcher.cmd
```

launcher 會在 Qt 啟動前設定 `QT_IM_MODULE=ibus`、`GTK_IM_MODULE=ibus` 及
`XMODIFIERS=@im=ibus`，並檢查 IBus 是否可使用。它仍預設使用 XCB；不要為了輸入法自行改成
Wayland。

### 無法輸入中文時的恢復方式

先關閉 XBrainLab，依序檢查：

1. launcher 是否指出缺少 `ibus` 或 `ibus-chewing`；缺少時執行上方安裝命令。
2. 執行 `ibus engine`；若不是 `chewing`，再次執行 `ibus-setup`，確認已加入並選取
   Chewing（酷音／注音）與標準大千；engine 與鍵盤配置的選取／切換始終由使用者完成。
3. 執行 `ibus address`。只有它失敗時才執行 `ibus-daemon --daemonize --xim`，之後重新從
   launcher 啟動；不要 replace 或終止既有 daemon。若 daemon 無法啟動，保留 terminal 輸出供診斷。
4. 若標準 Qt 文字框與 Assistant 輸入框都不能組字，這仍是 WSLg／IBus／Qt input-method 環境問題，
   不要把它當成 Assistant tool-call 或 Enter 行為問題。

IBus 缺少或暫時失效時，launcher 應保留英文啟動路徑；它不會記錄輸入內容，也不會停止既有的
IBus 程序。WSLg 的成功手測只能支持 WSLg 環境，不能替代 Windows native IME、鍵盤或 DPI
驗收。

## 驗證環境

安裝完成後，不要從完整 regression 開始。到[測試與驗證](testing.md)選擇與預計修改區域相符的
focused test 或 domain runner；該頁也說明 Qt／MNE／PyTorch、文件網站與本機 Granite 的執行條件。

## 產生檔與本機資料

- 開發 artifact 放在 ignored `build/dev-artifacts/`。
- 最終 handoff evidence 放在 ignored `build/handoff-evidence/<full-SHA>/`。
- Dataset storage、model／RAG cache、training output 與 evidence 各有獨立 owner。
- 不提交 cache、本機 dataset、臨時 screenshot 或複製的 runtime output。

把任何產生物解讀成 evidence 前，先閱讀[驗證契約](../validation/README.md)。
