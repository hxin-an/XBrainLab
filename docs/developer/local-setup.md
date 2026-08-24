# 本機開發環境

## 需求

- Python 3.11 或 3.12
- Poetry
- Git
- Qt、MNE、PyTorch 與本次要使用的 dataset reader 所需平台函式庫

選用的本機 Assistant 需要較多相依套件與儲存空間。只有任務涉及 Assistant runtime 時才安裝。

## 安裝相依套件

在 repository root 執行：

```bash
poetry install
```

需要本機 LLM 時加入對應 dependency group：

```bash
poetry install --with llm
```

不得隱式下載或替換模型。模型 identity、license、quantization、cache 位置與容量上限都屬於產品
決策。

## 啟動應用程式

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
