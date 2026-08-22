# XBrainLab Now

最後更新：`2026-08-22`

## 目前焦點

GUI polish integration的product implementation與focused validation已完成，但第一個candidate
`ab52ebb2` 在canonical handoff的Basedpyright gate fail closed，因此目前是checkpoint。下一個active
repair只修正本次modal／saliency新增的typed boundary；只有新clean exact source的replacement
handoff、Windows／Linux真人手測、PR applicable non-skipped checks全部success後才能merge。

本candidate整合三個已取得明確UI授權、可獨立回退的checkpoint：

- XBrainLab-styled Modal presentation foundation：第一批只遷移Model Settings、VRAM warning與
  Local Runtime first-run。Caller仍決定copy、recovery與mutation；Cancel是default、Escape reject，
  destructive confirm必須explicit accept。
- Data Import loading presentation：使用單一presentation session投影既有backend operation，移除
  admission／discovery內部術語與重複0–100；cancel、late-callback fence、rollback與Apply-cancel
  exact-review reopen仍由既有ApplicationService／OwnedWork owner決定。
- Saliency readability：2D views在共享色階下支援`All classes`與`Single class`，class selection使用
  canonical key；Map提供必要的垂直scroll與detail zoom／pan／reset，colorbar不得覆蓋plot或sidebar。
  3D controls位於Qt layout，時間只稱`Epoch time (s)`；沒有reviewed anchor DTO時不顯示event marker。

## Claim boundary

- 不宣稱所有native warning dialogs都已遷移；其餘call sites留給後續bounded product slice。
- 不改Data Interpretation、BIDS、label、event或loader semantics；profiling只比較同process中的first／
  repeat fresh-service pass，不控制OS page cache，也不支持效能預算或cache／hash／loader重構結論。
- `All classes`是多個class-specific plots的同頁比較，不是跨class數學aggregate。
- Saliency不代表科學有效性、brain source localisation或因果；offscreen evidence不代表Windows native
  focus／DPI或interactive 3D acceptance。

## Complexity與ownership

整合相對`main`為20個production files、`+923/-262/net +661`，觸發跨surface complexity review但未新增
authoritative owner。Deletion／reuse包括raw first-run QDialog與第一批QMessageBox construction、第二個
Data Import polling timer與重複loading fields、PyVista slider／checkbox／text overlays。Backend仍擁有
command、publication、cancel、rollback與saliency data；UI只擁有presentation與native canvas lifecycle。

## Candidate validation與人工驗收

Focused suites、Ruff、format、diff check、MkDocs strict及clean exact-source Visualization walkthrough已
通過。Public-fixture cases在獨立worktree缺資料時只記為skip，不能替代canonical source-diverse dataset gate。
`ab52ebb2` handoff在完成identity／Ruff後停於Basedpyright：17個new diagnostics只來自本次
ModalAlert Qt button Optional、Saliency Matplotlib dynamic attributes／mouse event typing、Visualization
widget dispatch與optional cancel binding；完整regression與後續gate未執行。

下一步固定為：

1. 只修正上述17個typed boundaries，不改可見行為；用直接Basedpyright與modal／saliency focused
   behavior tests驗證，並由新clean pushed SHA執行一次replacement canonical handoff。
2. 自動evidence完整後交付Windows／Linux手測：modal default／Escape／destructive action；single-file、
   folder、BIDS review/cancel/retry且status不重複跑百分比；Saliency All／Single、long class／many channel、
   zoom／pan／reset、3D class／epoch-time／camera controls與close lifecycle。
3. 使用者明確確認final source產品行為正常並同意merge後才開PR；PR head、base與所有applicable checks
   必須精確一致且completed/success。

## Stop conditions

- 任一owner、command／publication identity、cancel／rollback或artifact identity改變；
- modal destructive action無法accept，Cancel／Escape semantics改變或raw exception漏出；
- Data Import出現假overall percentage、Cancel作用到stale operation、late dialog或partial commit；
- All／Single切換不重繪、重名class選錯identity、colorbar不可見／疊圖或stale 3D controls可操作；
- 新skip／xfail／deselect、native abort、leaked process、source identity不符、required artifact缺失，或
  final check不是exact current head。

任一條件發生即停在checkpoint；不得以其他family已通過、provider outage、retry或人工目測掩蓋。
