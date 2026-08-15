# XBrainLab Now

最後更新：`2026-08-15`

這頁只保存目前主要目標、施工邊界與 exit condition。產品事實看
[Current](../current.md)，長期順序看 [Roadmap](roadmap.md)，驗證契約看
[Validation](../validation/README.md)。

## 目前焦點

**關閉真人手測追加確認的三個 product follow-up：所有標準 edit/settings dialogs 的 primary
action 順序、同一 completed training lineage 的累加式 Saliency 明確重算，以及 Time Epoching
在可用螢幕空間內完整展開。**

Working desktop foundation 已經由 PR `#16` 合回 `main`；前兩輪真人 UI follow-up 已由 PR `#19`
與 `#20` 合回 `main`。本輪從最新 `main` 建立短 branch；舊 checkpoint 繼續留在 remote 作
provenance。Repo-root `settings.json` 是使用者本機設定，永遠不 stage、commit、revert 或覆寫。

## Active Delivery Context

| 項目 | Current value |
| --- | --- |
| Product baseline | 最新 `main`；實際 merge-base / SHA 由 Git 取得。 |
| Candidate | Manual UI / Saliency follow-up v3 branch；實際 branch / pushed SHA 由 Git 與 PR 取得。 |
| Primary goal | 統一標準 Dialog 的 Cancel／primary 順序、讓 explicit Saliency 重算累加已完成 methods，並讓 Time Epoching 在有空間時完整展開。 |
| Non-goals | 不改 attribution 數學或公開 state schema、不合併舊 attribution arrays、不放寬 active/newer Saliency ownership、不重排 QMessageBox 或特殊 multi-role footer、不改 Epoch backend 語意、dataset storage 或其他 workflow；不重跑 15-dataset GUI campaign、不刪資料。 |
| Current classification | 前一輪修復已有使用者真人 checkpoint 並合回 `main`；這三項須完成 TDD、artifact、exact-head CI 與 Windows native acceptance。 |

## 本 branch 的產品邊界

- 所有經 shared standard OK／Cancel helper 建立的產品 dialogs 固定 `Cancel` 在左、primary action 在
  最右；copy、roles、enable、focus 不變。QMessageBox、特殊 multi-role／manual footer 與 primary-only
  dialogs 不新增或重排動作。
- Explicit Saliency recompute 在 resource admission 前形成「verified complete 舊 methods + 本次選擇」
  的 canonical union，對所有 targeted finished records 完整重算並 atomic publish；partial/stale method
  不累加，失敗／取消／OOM／stale 保留舊結果。Automatic baseline 行為不變。
- Time Epoching 在首幀前依 polished content 只向上擴張到螢幕安全邊界；有空間時完整顯示，真正
  超出螢幕時才由固定 footer 上方的單一 content scroll 承接。

## 施工與 exit signal

| 順序 | 工作 | Exit signal |
| --- | --- | --- |
| 1 | TDD | Dialog order、Saliency terminal recompute／union、Epoch available-space sizing 的 observable regressions 各自先紅後綠；不以 mock choreography 取代 Qt geometry、resource receipt、atomic publication 或真實 lifecycle。 |
| 2 | UI artifacts | 標準 dialogs 的 standard／narrow contact sheet、Time Epoching full／bounded states 與 Saliency method before／after evidence 由主 agent檢查 geometry、primary action、scroll、首幀穩定與 method membership。 |
| 3 | Regression | Focused 與直接相鄰 Qt / Training / Visualization / ApplicationService tests、same-class sweep、Ruff、Basedpyright、diff check通過。 |
| 4 | Product gate | Exact-head required public multi-dataset gate 與適用 visualization evidence通過；不跑 15-dataset GUI campaign。 |
| 5 | PR integration | Focused commit push；PR base `main`；exact-head CI 所有 non-skipped checks completed/success後才合回 `main`。 |

這條 branch 不包含 dataset cleanup；任何 destructive storage 工作仍須另外取得使用者授權。

## Claim boundary

- 使用者回報 PhysionetMI 與 BNCI2014_001／009 手動流程可完成，是重要人工 checkpoint，但不是
  exact-head automated receipt，也不能外推成所有 BIDS / MI acceptance。
- 本輪只改 Saliency 明確重算的 lifecycle admission 與 effective method set；不改 attribution
  演算法，也不宣稱 P300 scientific saliency quality。
- Offscreen Qt、Linux command-spine與 source guards 不取代 Windows native DPI、interactive 3D、
  long-session 或真人 usability acceptance。
- Dataset cleanup 在 PR merge、copy verification 與使用者確認前不執行；本 branch 不會讓目前資料或可運作程式消失。

## 本輪不做

- 不重新打開前一輪已合併的 computed-only selector、Channel stale handling、Data Split first-frame、
  Reset Session surface-retirement 或其他 workflow；只有本頁列出的三個 observable defects 進入本 branch。
- 不重新引入舊 reliability campaign。
- 不刪除 datasets、outputs、logs 或 worktrees。
- 不新增 facade、silent fallback、第二套 capability / state / status truth。
- 不用單一 PASS、聊天回報或舊 receipt 宣稱 handoff closure。
