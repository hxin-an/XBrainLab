# XBrainLab Now

最後更新：`2026-08-24`

## 目前焦點：WSLg 中文輸入可用性

### 問題與證據

- WSLg／XCB 下 Assistant 輸入框完全無法輸入中文，不是送出或 Enter 語意問題。
- 使用者使用台灣注音／ㄅㄆㄇㄈ，不是漢語拼音；初始診斷安裝的
  `ibus-libpinyin`／Intelligent Pinyin 不是本次驗收 engine。
- WSL 已安裝 IBus base，但尚未安裝或驗證專用的 `ibus-chewing`／Chewing
  注音 engine。
- `AssistantComposer` 已開啟 Qt input-method attribute 並處理 preedit；先修復環境輸入鏈，
  再用標準 Qt editor 對照判定是否有 product defect。

### Outcome

WSLg 使用者透過現有 Windows launcher 啟動後，可在 XBrainLab Qt 輸入中文，並能從
launcher 的可操作訊息判斷 IBus 套件／daemon／engine 缺失。

### Scope／non-goals

- Scope：WSLg Ubuntu 24.04、XCB、IBus Chewing（酷音／注音）、標準大千鍵盤、
  現有 WSL launcher、必要的使用文件。
- 只在標準 Qt editor 可輸入而 `AssistantComposer` 仍失敗時，才使用已取得的
  UI 授權做最小 Composer 修復。
- Non-goals：Wayland 切換、Windows native IME 認證、launcher 自動 sudo／安裝／全域
  engine 選擇、新 launcher、Assistant 視覺改版。

### 假設與施工步驟

1. 建立 launcher 特徵測試，要求啟動 Qt 前輸出 IBus 環境變數、做有上限的 daemon
   readiness check，缺失時繼續英文啟動並顯示修復方式。
2. 實作最小 launcher 修正；不記錄輸入內容，不中止非本 launcher 建立的程序。
3. 在本機安裝／設定 IBus 後，比較標準 Qt editor 與 `AssistantComposer`。
4. 若環境修復即可用，不修 Composer；若只有 Composer 失敗，先加最小 red
   reproduction 再修復。
5. 同步 WSLg 使用文件，明確區分 Windows IME 與 WSL IBus。

### Focused validation

- Launcher 特徵／privacy tests 與 PowerShell parser check。
- 現有 Composer IME、Enter、多空白與 New Chat 回歸測試。
- WSLg 手測：中文組字、候選字、退格、中英切換、Enter 選字／送出，以及
  重複啟動。

### Stop condition 與 UI 確認

- 若標準 Qt editor 也無法輸入，停在 IBus／DBus／Qt plugin 診斷，不改 product UI。
- 只有全部 focused evidence 通過並交付使用者 WSLg 手測後才稱為 handoff candidate。
- 使用者已條件式授權最小 Composer 行為修復；其他可見 UI／文案變更未獲授權。

### 目前狀態

- 本機已安裝 `ibus 1.5.29` 與 `ibus-chewing 2.0.0`，Qt 6 的 IBus
  input-context plugin 已實際載入；daemon 刷新後可列出 `chewing`，本次手測
  session 也已選為 `chewing`。
- Launcher 已以 red／green 改為 `ibus-chewing`／`chewing` discoverability，不宣稱能驗證
  或自動選擇大千鍵盤；non-replace lifecycle、bounded poll 與英文 fallback 保持不變。
- Local setup authority 已改為 Chewing／酷音／注音，大千設定仍由使用者掌握；
  launcher focused tests `12/12` 與 strict MkDocs build 通過。
- 獨立 final audit 已關閉全部 blocker；2026-08-24 使用者已在標準 Qt editor
  完成 Chewing／大千注音組字並回報正常，因此不觸發 `AssistantComposer` 程式修復。
- Next：freeze exact commit，從現有 Windows／WSLg launcher 開啟完整 XBrainLab，交付
  `AssistantComposer` 注音組字、Enter、多空白與重複啟動手測。
