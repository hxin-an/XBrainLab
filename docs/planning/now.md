# XBrainLab Now

最後更新：`2026-08-15`

這頁只保存目前主要目標、施工邊界與 exit condition。產品事實看
[Current](../current.md)，長期順序看 [Roadmap](roadmap.md)，驗證契約看
[Validation](../validation/README.md)。

## 目前焦點

**關閉真人手測追加確認的四個 UI follow-up：Training Settings 與 BIDS Subject 的 primary action
順序、Visualization 已計算 Saliency method 的精準投影，以及 Select Channels 對 BIDS montage
背景 publication 的假 stale rejection。**

Working desktop foundation 已經由 PR `#16` 合回 `main`；前一輪真人 UI follow-up 已由 PR `#19`
合回 `main`。舊 checkpoint 繼續留在 remote 作 provenance。Repo-root `settings.json` 是使用者本機
設定，永遠不 stage、commit、revert 或覆寫。

## Active Delivery Context

| 項目 | Current value |
| --- | --- |
| Product baseline | 最新 `main`；實際 merge-base / SHA 由 Git 取得。 |
| Candidate | Manual UI follow-up v2 branch；實際 branch / pushed SHA 由 Git 與 PR 取得。 |
| Primary goal | 固定三個明確 opt-in dialog 的 primary action 順序、只呈現目前可用的已計算 Saliency methods，並讓 montage-only publication drift 不再誤擋 channel selection。 |
| Non-goals | 不改 Saliency 數學或 backend coverage schema、不放寬真實 stale-data 防護、不全域重排所有 dialogs、不改 channel selection 語意、Reset Session、Data Split、label semantics 或 dataset storage；不重跑 15-dataset GUI campaign、不刪資料。 |
| Current classification | 前一輪修復已有使用者真人 checkpoint 並合回 `main`；這四項仍須完成 TDD、artifact、exact-head CI 與 Windows native acceptance。 |

## 本 branch 的產品邊界

- Training Settings、BIDS Subject 與 Select Channels 三個明確 opt-in dialogs 固定 `Cancel` 在左、
  `OK`／`Continue` 在最右；roles、copy、enable、focus 與 selection contract 不變，其他 dialogs 不重排。
- Visualization method selector 只列 active accepted result 對目前 view 真正可 render 的已計算 methods；
  compute settings 與 render selector 分離，pending／failed／cancelled method 不提早出現。
- Select Channels 在 reviewed publication 與 current publication 只差 BIDS montage preparation 狀態時，
  以 current boundary 正常套用；raw、metadata、channel、pipeline 或其他實質變更仍 fail closed 且不 mutation。

## 施工與 exit signal

| 順序 | 工作 | Exit signal |
| --- | --- | --- |
| 1 | TDD | 三個修復 slice 的 observable regression 各自先紅後綠；不以 mock choreography 取代 Qt render、backend publication truth 或真實 state transition。 |
| 2 | UI artifacts | Training、BIDS Subject、Visualization Method 與 Select Channels 的 standard / narrow 截圖由主 agent檢查 geometry、text fit、primary action、empty state 與 method membership。 |
| 3 | Regression | Focused 與直接相鄰 Qt / Visualization / Preprocess tests、same-class sweep、Ruff、Basedpyright、diff check通過。 |
| 4 | Product gate | Exact-head required public multi-dataset gate 與適用 visualization evidence通過；不跑 15-dataset GUI campaign。 |
| 5 | PR integration | Focused commit push；PR base `main`；exact-head CI 所有 non-skipped checks completed/success後才合回 `main`。 |

這條 branch 不包含 dataset cleanup；任何 destructive storage 工作仍須另外取得使用者授權。

## Claim boundary

- 使用者回報 PhysionetMI 與 BNCI2014_001／009 手動流程可完成，是重要人工 checkpoint，但不是
  exact-head automated receipt，也不能外推成所有 BIDS / MI acceptance。
- 本輪只修 Saliency method 的 publication-backed 顯示集合；不改 attribution 計算，也不宣稱 P300
  scientific saliency quality。
- Offscreen Qt、Linux command-spine與 source guards 不取代 Windows native DPI、interactive 3D、
  long-session 或真人 usability acceptance。
- Dataset cleanup 在 PR merge、copy verification 與使用者確認前不執行；本 branch 不會讓目前資料或可運作程式消失。

## 本輪不做

- 不重新打開前一輪已合併的 Subject primary style、Data Split first-frame、Channel warning removal／footer
  或 Reset Session surface-retirement 問題；只有本頁列出的新 observable defects 進入本 branch。
- 不重新引入舊 reliability campaign。
- 不刪除 datasets、outputs、logs 或 worktrees。
- 不新增 facade、silent fallback、第二套 capability / state / status truth。
- 不用單一 PASS、聊天回報或舊 receipt 宣稱 handoff closure。
