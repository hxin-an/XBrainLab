# XBrainLab Now

最後更新：`2026-09-01`

## Current baseline and release decision

`d60e9cac528014dc9b4e1e36f1b0339c92e9519f` 是目前 `main`／`origin/main` 的產品基線，已包含
PR #107 與 PR #108；兩者的 exact source、CI 與適用的使用者驗收都已閉合。Repo-root `settings.json`
的本機修改由使用者擁有，
不得 stage、commit、revert、覆寫或隱藏。

下一個工作目標不是 signed installer，而是可從乾淨 checkout 重建的 **Windows source/developer
environment**：Poetry 管理 repo-root `.venv`，Windows CUDA 使用者完成一次明確同步後，日常可直接執行
`poetry run python run.py --model local`。Windows 必須明確選擇 `cpu` 或 `cuda` extra，Windows CI 選擇
CPU contract；不得把 WSL／offscreen evidence 當成 Windows desktop acceptance。

## Active program — Windows Poetry/CUDA convergence

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
- 新環境與 native app 驗證通過後，移除已吸收的 worktree、舊 manual/dev env 與精確列出的暫存產物；保留
  dataset、Granite model cache、Poetry wheel cache、logs、使用者輸出與有獨立未合併工作的 branch ref。

### Scope, non-goals, assumptions, and ownership

- Poetry slice 只改 dependency metadata／lock、既有安裝文件與能直接證明 resolver contract 的 focused test；
  不改 product runtime、Assistant model catalog、UI、launcher behavior、模型 cache 或 `.python-version`。
- 官方 package source使用 explicit priority；CPU/CUDA 以 Windows platform 與 `cpu`／`cuda` extras 的互斥 marker解析。
  Poetry contract 為 `>=2.3,<3`，lock 由 Poetry 2.3.4 產生。
- 同一 checkout 若同時供 Windows 與 WSL 開發，repo-root `.venv` 只屬於 Windows；WSL 以
  `POETRY_VIRTUALENVS_IN_PROJECT=false` 使用自己的 cached environment，不操作 Windows `.venv`。
- 現有 packaging/runtime owner 不變，production owner delta `0`，產品 runtime LOC delta `0`。若需要 runtime
  fallback、第二個 installer owner、post-sync pip patch、全平台 CUDA 或 signed installer claim，立即停止另行決策。
- 本 program 沒有 UI 修改；UI確認狀態為 **not applicable**。Windows native launch仍須真人驗收。

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

5. **Current**：新 `.venv` 與 exact branch通過 automated＋Windows native acceptance後建立 PR；source再變即重驗。使用者明確
   手測通過並同意 merge後才合併。最後回到 latest main重驗並刪除 fallback／task worktree／精確暫存項目。

### Focused validation

- Dependency contract：focused TOML／lock test、`poetry check --lock`、package build、Ruff、Linux／macOS／Windows
  explicit CPU CI，且 CUDA source只能在 Windows `-E cuda` 被選取。
- Windows clean env：`poetry env info --path` 指向 repo-root `.venv`，Python 3.12，三件套皆為 `+cu130`，
  `torch.version.cuda == "13.0"`、`torch.cuda.is_available() is True`，PyQt6／Transformers／BitsAndBytes可 import；
  同一 sync連跑兩次仍保持 CUDA。
- Native walkthrough：以 `poetry run` 啟動，檢查 Assistant、Training Settings、3D Plot、關閉生命週期、第二次啟動、
  offline既有模型 cache與含空白路徑。自動／WSLg evidence不取代 Windows真人驗收。

### Stop and completion conditions

- Resolver 若同時安裝 CPU/CUDA variants、非 Windows解析 CUDA、需要 silent fallback、或 clean second sync退回 CPU，
  停止；不以手動 pip掩蓋。
- 刪除前若發現真實未提交差異、活動程序、唯一資料／模型／log或未合併工作，保留並回報；不用廣泛 glob刪除。
- 完成時 `main == origin/main`、Git只剩使用者的 `settings.json`、`git worktree list`只剩主目錄、Poetry指向
  repo-root `.venv`，且 `poetry run python run.py --model local` 使用 CUDA成功啟動。準確宣稱仍是可重建的
  Windows source/developer environment，不是 signed installer。
