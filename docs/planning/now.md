# XBrainLab Now

最後更新：`2026-08-14`

這頁只保存目前主要目標、施工邊界與 exit condition。產品事實看
[Current](../current.md)，長期順序看 [Roadmap](roadmap.md)，驗證契約看
[Validation](../validation/README.md)。

## 目前焦點

**關閉真人手測追加發現的三個 follow-up 區域：Subject／Channel action consistency、Data
Split 第二步首幀尺寸穩定，以及 desktop／Assistant 的 Reset Session surface 退役。**

Working desktop foundation 已經由 PR `#16` 合回 `main`；舊 reliability checkpoint 繼續留在 remote
作 provenance。Repo-root `settings.json` 是使用者本機設定，永遠不 stage、commit、revert 或覆寫。

## Active Delivery Context

| 項目 | Current value |
| --- | --- |
| Product baseline | 最新 `main`；實際 merge-base / SHA 由 Git 取得。 |
| Candidate | Manual UI regression branch；實際 branch / pushed SHA 由 Git 與 PR 取得。 |
| Primary goal | 讓 Subject／Channel primary actions 一致、Data Split 首次顯示不跳動，並移除 desktop／Assistant 的 Reset Session 入口。 |
| Non-goals | 不改 saliency 數學、split 演算法、channel selection 語意、Reset Preprocessing、internal ResetSessionCommand、label semantics 或 dataset storage；不重跑 15-dataset GUI campaign、不刪資料。 |
| Current classification | 原三項修復已有使用者真人 checkpoint；本輪 follow-up 仍須完成 TDD、artifact、exact-head CI 與 Windows native acceptance。 |

## 本 branch 的產品邊界

- Subject 的 `Continue` 與其他共用 confirm actions 必須在實際 render 後保有 primary style；selection
  與 enable contract 不變。
- Select Channels footer 固定 `Cancel` 在左、`OK` 最右；移除進 dialog 前的重複修改資料警告，
  以 dialog `OK` 作唯一確認。空選擇、blocked、stale 與 failure 提示保留。
- Data Split 第二步在首次 paint 前選定正確 responsive flow；async result refit 必須保持 top-level
  geometry 不變，1–8 rows 與超過 8 rows 的既有 scroll contract 保留。
- Dataset sidebar 與 Assistant 不再提供 Reset Session。Backend `ResetSessionCommand` 保留給 internal
  automation；Reset Preprocessing 與未啟用的 MCP compatibility surface 不在本輪。

## 施工與 exit signal

| 順序 | 工作 | Exit signal |
| --- | --- | --- |
| 1 | TDD | 三個 follow-up 區域的 observable regression 各自先紅後綠；不以 mock choreography 取代 Qt render、temporal geometry 或 Assistant tool exposure。 |
| 2 | UI artifacts | Subject、Data Split、Select Channels 與 Dataset sidebar 的 standard / narrow 截圖由主 agent檢查 geometry、scroll、text fit、primary action 與 surface removal。 |
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
