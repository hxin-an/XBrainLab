# XBrainLab Now

最後更新：`2026-08-15`

這頁只保存目前主要目標、施工邊界與 exit condition。產品事實看
[Current](../current.md)，長期順序看 [Roadmap](roadmap.md)，驗證契約看
[Validation](../validation/README.md)。

## 目前焦點

**完成這條 manual UI candidate 的最後一個真人手測修正：讓 Filtering 的 Band-pass／Notch
On/Off toggle 與 Epoch baseline 使用相同 compact pill 行為，checked `On` 立即顯示藍色。先保留
本機 checkpoint、不跑 CI；使用者完成 Windows 手測後才 push、merge 並建立 `desktop-gui-v1`
GUI baseline，接著由 tagged `main` 另開 Agent 工作。**

Working desktop foundation 已經由 PR `#16` 合回 `main`；前兩輪真人 UI follow-up 已由 PR `#19`
與 `#20` 合回 `main`。本輪從最新 `main` 建立短 branch；舊 checkpoint 繼續留在 remote 作
provenance。Repo-root `settings.json` 是使用者本機設定，永遠不 stage、commit、revert 或覆寫。

## Active Delivery Context

| 項目 | Current value |
| --- | --- |
| Product baseline | 最新 `main`；實際 merge-base / SHA 由 Git 取得。 |
| Candidate | Manual UI / Saliency follow-up v3 branch；實際 branch / pushed SHA 由 Git 與 PR 取得。 |
| Primary goal | 關閉 Filtering On/Off toggle 的 visual-state regression，同時保留本 candidate 已完成的 Dialog order、Saliency recompute、Epoch sizing 與 `Confirm` 文案。 |
| Non-goals | 不改 filter payload／validation／backend、不改 attribution 數學或公開 state schema、不重排其他 Dialog、不改 package `0.5.6`、dataset storage 或 Agent runtime；不重跑 15-dataset GUI campaign、不刪資料。 |
| Current classification | 前一輪修復已有使用者真人 checkpoint 並合回 `main`；這個 candidate 須完成 TDD、artifact、exact-head CI 與 Windows native acceptance。 |

## 本 branch 的產品邊界

- 所有經 shared standard OK／Cancel helper 建立的產品 dialogs 固定 `Cancel` 在左、primary action 在
  最右；copy、roles、enable、focus 不變。QMessageBox、特殊 multi-role／manual footer 與 primary-only
  dialogs 不新增或重排動作。
- Explicit Saliency recompute 在 resource admission 前形成「verified complete 舊 methods + 本次選擇」
  的 canonical union，對所有 targeted finished records 完整重算並 atomic publish；partial/stale method
  不累加，失敗／取消／OOM／stale 保留舊結果。Automatic baseline 行為不變。
- Time Epoching 在首幀前依 polished content 只向上擴張到螢幕安全邊界；有空間時完整顯示，真正
  超出螢幕時才由固定 footer 上方的單一 content scroll 承接。Dialog 標題與側欄功能名稱維持
  `Create EEG Epochs`，footer 主動作固定為短文案 `Confirm`。
- Filtering 的 Band-pass／Notch toggle 直接復用 shared `PreprocessToggle` contract：checked 為
  `On` + blue compact pill，unchecked 為 `Off` + neutral pill；欄位 enable、值保存、validation 與
  command payload 不變。

## 施工與 exit signal

| 順序 | 工作 | Exit signal |
| --- | --- | --- |
| 1 | Filter TDD | 真實 rendered Filter toggle 先證明 current `On` 不是 blue，再以 shared selector修正；點擊後文字、顏色、enabled fields與 validation 同步。 |
| 2 | Local evidence | Fresh initial／toggled Filter screenshots、focused Qt／adjacent Epoch、same-class sweep、Ruff、Basedpyright與 diff check通過；此階段不 push、不跑 CI。 |
| 3 | Windows acceptance | 使用者手測 Filter toggle 與 Epoch `Confirm`，明確回報 candidate 可接受。 |
| 4 | Product gate | acceptance 後一次 push 最終 head；required public multi-dataset、平台 lifecycle 與所有 non-skipped exact-head CI 成功。 |
| 5 | GUI baseline | PR 合回 `main` 且 merge SHA CI 成功後，建立 annotated `desktop-gui-v1` tag 與同名 GitHub pre-release；不附 installer。 |

這條 branch 不包含 dataset cleanup；任何 destructive storage 工作仍須另外取得使用者授權。

## Claim boundary

- 使用者回報 PhysionetMI 與 BNCI2014_001／009 手動流程可完成，是重要人工 checkpoint，但不是
  exact-head automated receipt，也不能外推成所有 BIDS / MI acceptance。
- 本輪只改 Saliency 明確重算的 lifecycle admission 與 effective method set；不改 attribution
  演算法，也不宣稱 P300 scientific saliency quality。
- Offscreen Qt、Linux command-spine與 source guards 不取代 Windows native DPI、interactive 3D、
  long-session 或真人 usability acceptance。
- `desktop-gui-v1` 只表示 Desktop GUI/source baseline；package 仍為 `0.5.6`，Agent、signed installer、
  scientific quality 與整體產品 release 尚未完成。
- Dataset cleanup 在 PR merge、copy verification 與使用者確認前不執行；本 branch 不會讓目前資料或可運作程式消失。

## 本輪不做

- 不重新打開前一輪已合併的 computed-only selector、Channel stale handling、Data Split first-frame、
  Reset Session surface-retirement 或其他 workflow；只有本頁列出的 candidate defects 進入本 branch。
- 不重新引入舊 reliability campaign。
- 不刪除 datasets、outputs、logs 或 worktrees。
- 不新增 facade、silent fallback、第二套 capability / state / status truth。
- 不用單一 PASS、聊天回報或舊 receipt 宣稱 handoff closure。
