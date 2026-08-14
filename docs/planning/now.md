# XBrainLab Now

最後更新：`2026-08-14`

這頁只保存目前主要目標、施工邊界與 exit condition。產品事實看
[Current](../current.md)，長期順序看 [Roadmap](roadmap.md)，驗證契約看
[Validation](../validation/README.md)。

## 目前焦點

**先修復三個真人手測可見問題：Saliency Normalize admission、Data Split 第二步展開／primary
action，以及 Select Channels dialog 外觀。**

Working desktop foundation 已經由 PR `#16` 合回 `main`；舊 reliability checkpoint 繼續留在 remote
作 provenance。Repo-root `settings.json` 是使用者本機設定，永遠不 stage、commit、revert 或覆寫。

## Active Delivery Context

| 項目 | Current value |
| --- | --- |
| Product baseline | 最新 `main`；實際 merge-base / SHA 由 Git 取得。 |
| Candidate | Manual UI regression branch；實際 branch / pushed SHA 由 Git 與 PR 取得。 |
| Primary goal | 關閉 Saliency Normalize operation identity、Data Split preview layout 與 Select Channels visual consistency 三個問題。 |
| Non-goals | 不改 saliency 數學、split 演算法、channel selection 語意、label semantics 或 dataset storage；不重跑 15-dataset GUI campaign、不刪資料。 |
| Current classification | Short-branch implementation checkpoint；使用者已明確授權三個可見 UI 修復，尚未完成 TDD、artifact、exact-head CI 或 Windows native acceptance。 |

## 本 branch 的產品邊界

- Saliency begin / prepare 必須使用相同 canonical raw render identity；Normalized variant 在該 owned
  operation 內產生，不放寬 registry admission。Absolute 仍是 display-only 語意。
- Data Split 第二步在 responsive layout 與 async preview rows 穩定後 refit；1–8 rows 在螢幕允許時
  直接可見，超過 8 rows 才由 tree scroll，Confirm 使用共用 primary style。
- Select Channels 只統一間距、surface、按鈕層級與 bounded geometry；搜尋、checkbox、全選／取消
  全選、OK／Cancel、空選擇警告及 command/state flow 全部不變。

## 施工與 exit signal

| 順序 | 工作 | Exit signal |
| --- | --- | --- |
| 1 | TDD | 三項 observable regression 各自先紅後綠；不以 mock choreography 取代 owned runtime / Qt behavior。 |
| 2 | UI artifacts | Data Split 與 Select Channels 的 standard / narrow 截圖由主 agent檢查 geometry、scroll、text fit 與 primary action。 |
| 3 | Regression | Focused 與直接相鄰 Qt / Visualization tests、same-class sweep、Ruff、Basedpyright、diff check通過。 |
| 4 | Product gate | Exact-head required public multi-dataset gate 與適用 visualization evidence通過；不跑 15-dataset GUI campaign。 |
| 5 | PR integration | Focused commit push；PR base `main`；exact-head CI 所有 non-skipped checks completed/success後才合回 `main`。 |

這條 branch 不包含 dataset cleanup；任何 destructive storage 工作仍須另外取得使用者授權。

## Claim boundary

- 使用者回報 PhysionetMI 手動流程可完成，是重要人工 checkpoint，但不是 exact-head automated
  receipt，也不能外推成所有 BIDS / MI acceptance。
- 本輪只修已定位的 render operation identity 與顯示控制；不宣稱 P300 scientific saliency quality。
- Offscreen Qt、Linux command-spine與 source guards 不取代 Windows native DPI、interactive 3D、
  long-session 或真人 usability acceptance。
- Dataset cleanup 在 PR merge、copy verification 與使用者確認前不執行；本 branch 不會讓目前資料或可運作程式消失。

## 本輪不做

- 不重新引入舊 reliability campaign。
- 不刪除 datasets、outputs、logs 或 worktrees。
- 不新增 facade、silent fallback、第二套 capability / state / status truth。
- 不用單一 PASS、聊天回報或舊 receipt 宣稱 handoff closure。
