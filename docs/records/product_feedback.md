# Product Feedback Log

最後更新：`2026-05-10`

這份文件集中保存人工使用 XBrainLab 時看到的產品問題、UI / UX 意見和未來設計方向。
它不是 current truth、不是 target spec，也不是施工流水帳；它的角色是防止真實使用感受散落在聊天紀錄或 worklog 裡。

## 怎麼使用

- 使用者實際操作時覺得困惑、煩躁、不知道下一步、看不到主操作、或系統說法和使用者心智模型不一致時，記在這裡。
- 已修掉的問題可以移到「近期已處理」，但不要刪掉；它們是後續 regression smoke 的來源。
- 產品決策成熟後，再同步到 `docs/target/` 或 `docs/planning/`。不要直接把這份文件當成已承諾的 spec。
- 驗證方式成熟後，再同步到 `docs/validation/README.md` 或 artifact capture 腳本。

## 目前集中意見

| 主題 | 使用者觀察 | 產品判讀 | 狀態 |
| --- | --- | --- | --- |
| Dataset operations 命名不直觀 | Dataset Operations 一次露出多種 import / interpret / recipe / metadata 操作；問題不只是數量，而是名稱不像一般使用者會找的入口。 | 常用入口應用 `Import file`、`Import folder` 這類直觀命名；進階功能再用次要分組或 advanced wording。 | Open |
| Data Interpretation preview 太雜 | Preview 同時顯示 source、metadata、label carrier、event role、class map、format capability，讀起來像 debug panel。 | 第一屏應只回答「會 import 哪些檔案、label 怎麼配、還有什麼需要確認、能不能套用」。 | Open |
| Preview 有 nested scrolling | Preview 已有全域上下捲動，但每個 table 也可能各自上下捲，操作時會覺得卡在小區塊裡。 | Dialog 應保留單一主要 vertical scroll；表格自己不要再垂直捲動，必要時讓整個 preview 變長。 | In progress |
| 第一次使用不知道每個表格要做什麼 | Preview 一次揭露多個表格，初次接觸者不知道哪個是主要確認、哪個只是進階細節。 | 資訊架構要改成 task hierarchy：import scope、label matching、needs attention 是主層；event/class/raw metadata 是細節層。 | In progress |
| 選 3 個檔案卻像選整個資料夾 | 多選 `A01T/A02T/A03T` 時，畫面顯示 folder source，讓人以為整個資料夾都會被 import。 | scan root 和 selected scope 要清楚分開；使用者看到的主要範圍應是 selected files。 | Partially fixed |
| Preview 太長看不到 Apply | 內容區域太長時，主要操作按鈕會被擠出視窗。 | Primary action 必須固定可見；任何 preview table 都不能讓 apply / cancel 消失。 | Fixed, keep smoke |
| Metadata 明明空卻占很大 | `A01T.gdf` 這類非 BIDS 檔名沒有 subject/session/task/run，但 metadata table 仍占一大塊。 | 空 metadata 應該 compact、collapsed，或用一行說明「未偵測到 BIDS-style metadata」。 | Open |
| Label / Event Interpretation 難讀 | 最重要的是 `A01T.mat -> A01T.gdf` 是否配對正確，但畫面也顯示很多 event role / class map 細節。 | Carrier matching 應是主要視覺層級；role / anchor / granularity / class map 是進階確認。 | Partially fixed |
| 確認列表不夠直觀 | Attention / Review Summary 類文字仍像系統診斷；第一次使用者不知道列表是在要求確認、修正、還是只是提醒。 | 確認列表要改成使用者任務語言，例如 `Check Before Import`、`Check / Action / Why this matters`，並把 warning / confirmation / format capability 翻成可操作文字。 | In progress |
| Launcher 看起來啟動但實際不可用 | log 顯示 `MainWindow initialized`，但可能閃退或視窗跑出螢幕。 | startup smoke 不能只看 process / log；還要驗證視窗可見、可互動、在目前螢幕範圍內。 | Partially fixed |
| Loading screen 太晚出現 | App 開起來會等很久才看到載入畫面；如果 splash 幾乎快結束才跳出來，使用者感覺上等於沒有載入畫面。 | Splash 必須在 heavy backend / training / panel imports 前出現。Package `__init__`、startup helper import、top-level UI imports 都不能偷偷拖重依賴。 | In progress |
| 測試很多但抓不到實機 bug | Unit / integration / artifact tests 能證明局部正確，仍漏掉 hidden apply、offscreen window、scope confusion 等問題。 | 需要 Validation Reality-Gap Audit，補 human-observable product smoke。 | In planning |

## 近期已處理

以下項目已在目前施工中改善，但仍應轉成可重跑的 product smoke，避免回歸：

- Data Interpretation candidate 會用 selected files 過濾 metadata，不再把整個 scan folder 的 metadata 當成主要 preview。
- Preview dialog 底部確認文字、recipe checkbox、apply / cancel 按鈕改成固定 footer。
- Label carrier table 和 lower event choices 減少重複列，讓 carrier matching 更清楚。
- Review Summary format capability rows 已做初步 dedupe。
- Windows WSL launcher 預設使用 `QT_QPA_PLATFORM=xcb`，降低 WSLg / Wayland 下 Qt native segfault 風險。
- Data Interpretation preview 開始移除 per-table vertical scroll，並把 section title 往使用者任務語言收斂。
- Import 前確認列表開始改成 `Check / Action / Why this matters`，降低 `Needs review` 這類狀態字造成的誤解。
- Package root `XBrainLab` 開始避免 eager import `Study`，讓 startup helper imports 不會在 splash 前拖入 backend / training stack。

## 建議設計方向

Dataset Operations 應先按使用者心智模型整理名稱與分組：

1. **Primary import actions**：用常見語言，例如 `Import file`、`Import folder`。
2. **Guided interpretation**：把 `Interpret Data Source` 這類較抽象名稱改成更像流程入口的文字，或放在 import 後的 guided review。
3. **Advanced / reuse actions**：`Reload Import Recipe`、`Smart Parse Metadata`、`Add Labels` 這類功能可保留，但應放在次要區或 advanced menu，避免和主 import 平起平坐。

Data Interpretation preview 的預設視角應該是使用者視角，不是 importer 內部資料結構：

1. **Import scope**：清楚顯示將要 import 的檔案數和檔名。
2. **Label matching**：清楚顯示每個 label / event carrier 會配到哪個 EEG 檔。
3. **Required review**：只列真正需要使用者判斷的項目。
4. **Primary action**：固定可見，文字要讓人知道會發生什麼，例如 `Import selected files` 或 `Apply interpretation`。
5. **Advanced details**：format capability、recipe trace、raw metadata、class map 細節可摺疊或放在次要區。
6. **Single scroll model**：整個 dialog 可以上下捲，但 table 不應各自再做垂直捲動。

## 後續要補的驗證

- 一條可重跑的人工可觀察流程：desktop launcher -> main window visible -> Data Interpretation -> select 3 fixture files -> preview shows selected scope -> apply button visible -> import only selected files。
- Screenshot / geometry evidence 應檢查 primary action 是否在視窗內、metadata empty state 是否 compact、重要文字沒有被截斷。
- Review Summary 應有 visible-text guard，避免把內部 trace token、過長 format warning、或重複 capability rows 暴露成主要 UI。
