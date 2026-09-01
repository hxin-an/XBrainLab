# XBrainLab Now

最後更新：`2026-09-01`

## Current baseline and release decision

`8d5787953cf646c611ff6cc59b3355ba7a2fbd9e` 是目前 `main`／`origin/main` 的產品基線，已包含
PR #108 並經使用者 Windows native 手測通過。Repo-root `settings.json` 的本機修改由使用者擁有，
不得 stage、commit、revert、覆寫或隱藏。

下一個工作目標不是 signed installer，而是可從乾淨 checkout 重建的 **Windows source/developer
environment**：Poetry 管理 repo-root `.venv`，Windows CUDA 使用者完成一次明確同步後，日常可直接執行
`poetry run python run.py --model local`。Windows CI 與未選 CUDA extra 的開發環境仍維持 CPU dependency
contract；不得把 WSL／offscreen evidence 當成 Windows desktop acceptance。

## Active program — PR #107 closure and Windows Poetry/CUDA convergence

### Problem and evidence

1. PR #107 的 artifact writer 修正仍停在舊 parent `a426ad90`。舊 head
   `79708a0eea1bc7b640c6cbd5b3fc10db8f75530b` 的 CI 已通過，但 merge source 改變後 evidence 失效；目前只允許
   保留既有 `allow_pickle` collision 修正、精確 NumPy stub boundary 與 side-effect test。
2. Windows 乾淨 Poetry 解析目前從 PyPI 取得 CPU PyTorch。先前 Windows CUDA 手測依賴
   `build/manual-windows-pr107/.venv` 內的手動 pip 覆寫，因此不可重建，之後執行 `poetry sync` 也可能退回 CPU。
3. 本機另有舊 worktree、manual venv、CRLF-only clone 與 `/tmp/xbrainlab-*` 驗證產物。它們不是產品 authority，
   但在新的 `.venv` 驗證成功前必須保留唯一可工作的 CUDA fallback。

### Outcomes

- PR #107 先合入最新 `main`，只解決 canonical plan 衝突；新 exact head 重新跑 focused、static、docs 與 PR CI，
  取得使用者明確批准後才 merge。
- 從 PR #107 合併後的最新 `main` 建立一條短 setup branch，加入官方 `cuda` extra 與 explicit
  PyTorch CUDA 13.0 source；不以 post-install pip 覆寫製造第二套 dependency truth。
- Windows repo-root `.venv` 明確使用既有 CPython 3.12。`poetry sync --with llm -E cuda` 安裝
  `torch==2.11.0+cu130`、`torchvision==0.26.0+cu130`、`torchaudio==2.11.0+cu130`；未選 extra 時保持 CPU。
- 新環境與 native app 驗證通過後，移除已吸收的 worktree、舊 manual/dev env 與精確列出的暫存產物；保留
  dataset、Granite model cache、Poetry wheel cache、logs、使用者輸出與有獨立未合併工作的 branch ref。

### Scope, non-goals, assumptions, and ownership

- PR #107 只允許既有 artifact store validation、直接測試與本 active plan；不改 schema、reader、hash、UI、
  public artifact shape、owner、state machine、receipt 或 compatibility path。
- Poetry slice 只改 dependency metadata／lock、既有安裝文件與能直接證明 resolver contract 的 focused test；
  不改 product runtime、Assistant model catalog、UI、launcher behavior、模型 cache 或 `.python-version`。
- 官方 package source使用 explicit priority；CPU/CUDA 以 Windows platform 與 `cuda` extra 的互斥 marker解析。
  Poetry contract 為 `>=2.3,<3`，lock 由 Poetry 2.3.4 產生。
- 現有 packaging/runtime owner 不變，production owner delta `0`，產品 runtime LOC delta `0`。若需要 runtime
  fallback、第二個 installer owner、post-sync pip patch、全平台 CUDA 或 signed installer claim，立即停止另行決策。
- 本 program 沒有 UI 修改；UI確認狀態為 **not applicable**。Windows native launch仍須真人驗收。

### Implementation sequence

1. 在專用 PR #107 worktree 合入 exact `main`，解決本文件衝突，確認產品 diff仍只有 artifact修正及直接測試。
2. 跑 artifact／record focused suites、Ruff、MkDocs strict與完整 Basedpyright；commit、push並等待新 exact head 所有
   non-skipped PR checks completed/success。交付自動 side-effect evidence，等待使用者批准後 merge。
3. 同步主工作目錄 `main`，逐一核對 worktree／process／真實 diff。先移除已被 main 等價吸收的 worktree與小型
   `/tmp` artifacts；暫留 manual CUDA fallback。
4. 從 clean latest main 建立單一 Poetry/CUDA branch。在改 dependency 前以本節作 scope ceiling，實作 explicit
   `cuda` extra、官方 cu130 source、互斥 variants、lock 與現有開發文件。
5. Windows 移除會阻止 in-project env切換的舊 cached Poetry env，指定現有 CPython 3.12，建立 repo-root `.venv`：

   ```powershell
   $env:POETRY_VIRTUALENVS_IN_PROJECT = "true"
   poetry env use "C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe"
   poetry sync --with llm -E cuda
   poetry env info --path
   poetry run python run.py --model local
   ```

6. 新 `.venv` 與 exact branch通過 automated＋Windows native acceptance後建立 PR；source再變即重驗。使用者明確
   手測通過並同意 merge後才合併。最後回到 latest main重驗並刪除 fallback／task worktree／精確暫存項目。

### Focused validation

- PR #107：reserved-key side-effect test、safe artifact／TrainRecord／EvalRecord suites、Ruff check／format check、
  MkDocs strict、完整 Basedpyright、exact-head PR CI與 frozen diff review。
- Dependency contract：focused TOML／lock test、`poetry check --lock`、package build、Ruff、Linux／macOS／Windows
  default CPU CI，且 CUDA source只能在 Windows `-E cuda` 被選取。
- Windows clean env：`poetry env info --path` 指向 repo-root `.venv`，Python 3.12，三件套皆為 `+cu130`，
  `torch.version.cuda == "13.0"`、`torch.cuda.is_available() is True`，PyQt6／Transformers／BitsAndBytes可 import；
  同一 sync連跑兩次仍保持 CUDA。
- Native walkthrough：以 `poetry run` 啟動，檢查 Assistant、Training Settings、3D Plot、關閉生命週期、第二次啟動、
  offline既有模型 cache與含空白路徑。自動／WSLg evidence不取代 Windows真人驗收。

### Stop and completion conditions

- PR #107 新 head任一 required check missing／pending／stale／cancelled／failed，或未取得使用者批准，不 merge且
  不開始 CUDA product branch。
- Resolver 若同時安裝 CPU/CUDA variants、非 Windows解析 CUDA、需要 silent fallback、或 clean second sync退回 CPU，
  停止；不以手動 pip掩蓋。
- 刪除前若發現真實未提交差異、活動程序、唯一資料／模型／log或未合併工作，保留並回報；不用廣泛 glob刪除。
- 完成時 `main == origin/main`、Git只剩使用者的 `settings.json`、`git worktree list`只剩主目錄、Poetry指向
  repo-root `.venv`，且 `poetry run python run.py --model local` 使用 CUDA成功啟動。準確宣稱仍是可重建的
  Windows source/developer environment，不是 signed installer。
