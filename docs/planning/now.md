# XBrainLab Now

最後更新：`2026-08-22`

## 目前焦點

GUI polish integration的product implementation、focused validation與subagent gate已完成。前三個
canonical handoff checkpoint揭露的typed boundary、private renderer all-class compatibility與臨時
worktree editable-environment問題都已收旂。目前只等待新clean exact source的replacement
handoff；完成後交付Windows／Linux真人手測，PR applicable non-skipped checks全部
success後才能merge。

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

整合相對`main`為20個production files、`+963/-266/net +697`，觸發跨surface complexity review但未新增
authoritative owner。Deletion／reuse包括raw first-run QDialog與第一批QMessageBox construction、第二個
Data Import polling timer與重複loading fields、PyVista slider／checkbox／text overlays。Backend仍擁有
command、publication、cancel、rollback與saliency data；UI只擁有presentation與native canvas lifecycle。

## Candidate validation與人工驗收

Focused suites、Ruff、format、diff check、MkDocs strict及clean exact-source Visualization walkthrough已
通過。Public-fixture cases在獨立worktree缺資料時只記為skip，不能替代canonical source-diverse dataset gate。
`ab52ebb2` handoff在完成identity／Ruff後停於Basedpyright：17個new diagnostics只來自本次
ModalAlert Qt button Optional、Saliency Matplotlib dynamic attributes／mouse event typing、Visualization
widget dispatch與optional cancel binding；完整regression與後續gate未執行。

`1d9a5d04` 的direct analyzer雖為0 error，replacement recorded gate仍在sanitized environment辨識出13個
new diagnostics：Matplotlib callback需要接受base Event、axis limit需收斂成built-in float，另有窄幅
PyVista actor／scalar-bar external typing seam。這些仍屬同一typed-boundary repair；不得更新baseline或加入
ignore來放行。
`ac85437c` 的recorded Basedpyright已通過；完整regression其後揭露兩類checkpoint：(a) 三個舊private
Topo／Spectrogram renderer tests未帶新增的class display參數；(b) 臨時worktree借用main editable venv，
11個scripts tests被active-checkout guard正確阻擋。前者以等同既有all-class行為的default arguments收斂；
後者只用lock-exact worktree Poetry sync修正執行環境，不修改或放寬checkout guard。
`1640d683` replacement handoff通過static／architecture後，complete regression在scripts shard揭露
三個測試環境contract：兩個capture tests觸發確定性download-failure alert卻未明確interaction
fixture；一個missing-fixture test沒有隔離handoff提供的`XBRAINLAB_DATA_DIR`。只在這三個
tests明確declare modal與空cache環境，不變更product modal、public fixture resolver或runner policy。
這三個red nodes已在handoff同款`XBRAINLAB_DATA_DIR`環境下通過；Modal／Data Import／Saliency
focused behavior suites為`407 passed`，authoritative scripts shard為`1155 passed`，兩個非重疊
subagent closure gate無新blocker／major。Saliency的舊capture不屬於final integration SHA，因此不用它
作為candidate evidence；由final canonical visualization gate重產exact-source artifact。
final handoff的`chatpanel-dpi`進一步暴露standalone capture仍patch舊`QMessageBox.critical`，
未隔離新`show_alert`，因此在download-failure evidence卡住至180秒timeout。Pytest不得以
`auto_accept_modals`掩蓋此問題；capture script改為明確patch已遷移的presentation seam，原測試維持
unexpected-modal fail-fast。不改product modal或DPI gate timeout／artifact policy。
原三個red nodes在此fail-fast設定下再次`3 passed`，standalone ChatPanel DPI gate的三個scale
subprocess全部完成並在22秒內通過；Ruff、format與Basedpyright無新diagnostic。

下一步固定為：

1. 凍結與push新clean exact source，執行一次replacement canonical handoff。失敗時只修復
   記錄的owner，不為追時間重跑。
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
