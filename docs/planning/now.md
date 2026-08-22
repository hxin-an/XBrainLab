# XBrainLab Now

最後更新：`2026-08-22`

## 歷史 snapshot（非 active dispatch）

CI reliability 與 Braindecode full catalog 已分別由 PR #44、PR #45 合併至 `main`；PR #46
完成使用者／開發者文件整理。現在唯一 active slice 是 branch
`integration/gui-polish-v1`：整合三個已完成 focused gate 的 GUI polish checkpoint，對同一個
final source 只做一次 canonical handoff，再交付 Windows／Linux 真人手測。

使用者已明確授權以下可見變更：

- 建立 XBrainLab 風格的 warning／confirmation modal，第一批只遷移 Model Runtime 相關流程；
- Saliency 提供 `All classes` 比較與 `Single class` 細看，保留共享色階與 canonical class
  identity；
- Map／Spectrogram／Topographic colorbar 不得壓住圖，dense class／channel 初始畫面要可讀，
  single-class canvas可zoom／pan／reset；
- 3D controls移出PyVista canvas，時間明確稱為epoch-relative time；沒有reviewed anchor DTO時
  不顯示虛構event marker；
- Data Import 移除 admission／discovery 內部術語與重複0–100進度，只呈現連續且誠實的
  phase狀態；loading presentation可重構，但不改資料解讀、cancel ownership或Apply semantics。

## 問題與證據

1. Product仍有大量native `QMessageBox`；Fusion／MainWindow stylesheet不能可靠套用到top-level
   modal。第一個bounded checkpoint只建立presentation seam並遷移Model Settings、VRAM warning與
   Local Runtime first-run，不宣稱全產品220個call site已完成。
2. 舊Saliency 2D grid無class selector，所有channel labels會堆疊；共享colorbar配置可與plot
   相交。舊3D把time／checkbox overlays放在PyVista canvas，且`Time (s)`容易被誤讀為recording
   event timeline。
3. Data Import的backend checkpoints直接把`Admitting Data Import discovery`投影到使用者畫面；
   Review、Preview、Validate與Apply各自有command-local progress domain，因此status bar會看似多次
   從0跑到100。既有cancel／late-callback／rollback fence是正確owner，不應為了畫面連續性重寫。
4. 實測profile目前只支持同process中兩個fresh `ApplicationService` pass；不控制OS page cache，
   因此不能稱cold／warm benchmark，也沒有證據支持更深的loader／hashing語意優化。

## Observable outcome

- Destructive confirmation按鈕能真的回傳Accepted；Cancel仍是default，Escape仍reject。
- Saliency `All classes`同時顯示所有class-specific views；`Single class`用同一canonical key在
  Map、Spectrogram、Topographic與3D同步，重名display label不會選錯class。
- 切換All／Single或class一定使native render binding失效並重繪；clear、error或replace後沒有
  stale 3D scene controls。
- Map使用可縮放寬度與必要的垂直scroll，不以水平scroll把shared colorbar藏起來；capture也只把
  scroll viewport的可見framebuffer寫回shell，不覆蓋sidebar。
- 3D controls位於Qt layout外層，文字為`Epoch time (s)`；沒有verified anchor時只顯示class／event
  code identity，不宣稱0秒是event。
- Data Import loading只有一個presentation session；Review／revalidation／Apply使用phase＋
  indeterminate狀態，不把不同command counters偽裝成一條global百分比。Cancel仍精確作用於current
  backend operation，Apply cancel仍重開同一份review。
- Profiling artifact使用`first_fresh_service_pass`／`repeat_fresh_service_pass`，明示同process定義與
  claim boundary，不產生效能結論。

## Scope／non-goals與complexity review

Scope只包含三個已批准checkpoint的整合、直接回歸測試、current truth sync、visual artifacts與
final handoff。Non-goals：不全面替換所有warning panels、不改Data Interpretation／BIDS／label／event
semantics、不新增Saliency scientific aggregation或brain source localisation、不重新設計renderer、
不以未校準profile改cache／hash／loader、不改ApplicationService command spine。

Owners before／after不變：backend仍擁有command、publication、cancel、rollback與saliency data；
VisualizationPanel／render views只擁有可見選擇與canvas lifecycle；modal seam只呈現caller已決定的
title／message／buttons，不成為error／confirmation policy owner；Data Import coordinator只擁有連續
presentation token，不取代OwnedWorkRegistry operation identity。

Complexity由三個可獨立回退的commit family承擔，而不是一個不可分的大改：

- modal foundation刪除第一批raw QMessageBox construction與raw first-run QDialog；
- Data Import刪除第二個250ms polling timer、重複loading fields與散落projection；
- Saliency刪除PyVista slider／checkbox／text overlays，重用現有publication與renderer owners。

三條線合計觸及超過12個production files，已觸發並完成本complexity review；沒有新增authoritative
owner。Integration commit保留原checkpoint粒度，任一family可單獨revert。若整合需要新增owner、第二套
state、compatibility path或超出已批准UI行為，立即停止並向使用者取得新決策。

## 施工順序

1. 從`main`建立integration branch，依原順序cherry-pick Modal、Data Import、Saliency commits；只處理
   真實conflict，不重寫已通過的產品行為。
2. 校準`docs/planning/now.md`與`docs/current.md`；已合併的Braindecode施工紀錄留在Git／PR歷史，
   不再充當active dispatch。
3. 跑三個family的combined focused suites、Ruff／format／diff check；生成同一clean exact source的
   modal、Data Import與Visualization artifacts並人工檢視。
4. Freeze exact SHA，依`.agents/workflows/handoff-candidate.md`只跑一次canonical handoff。失敗時只修
   recorded owner，建立新SHA後做一次replacement；不為計時或成功率重跑同SHA。
5. 交付Windows／Linux手測清單。只有使用者明確回報final SHA產品行為正常並同意merge，才開PR、
   等待全部applicable non-skipped checks在同一head完成success後合併。

## Focused validation

- Modal：button role／default／Escape／long copy／VRAM／first-run／Model Settings實際click。
- Data Import：OwnedOperationPresenter、loading dialog、BIDS subject cancel、Review／Preview／Validate／
  Apply chain、Apply cancel exact-review reopen、profile schema。
- Saliency：backend visualizers、VisualizationPanel render binding、async canvas lifecycle、3D cache／worker、
  capture script scroll clipping與exact-source walkthrough。
- Static：Ruff check、Ruff format check、`git diff --check`；docs truth改變後跑MkDocs strict。
- Final：canonical handoff一次；offscreen artifact不取代Windows native modal focus／DPI、interactive 3D、
  scroll／zoom與Data Import cancel手測。

## Stop conditions

- 任一產品owner、command／publication identity、cancel／rollback或artifact identity改變；
- All／Single class選擇可繞過canonical key、切換不重繪、colorbar不可見或覆蓋plot／sidebar；
- modal destructive action無法accept，Cancel／Escape semantics改變，或raw exception漏到使用者；
- Data Import出現多次假百分比、Cancel作用到stale operation、late callback重開dialog或partial commit；
- 新skip／xfail／deselect、native abort、leaked process、source identity不符、artifact缺失或final check不是
  exact current head。

任一stop condition發生時，本slice停在checkpoint；不得以其他family已通過、provider outage、retry或
人工目測掩蓋。
