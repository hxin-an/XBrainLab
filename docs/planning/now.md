# XBrainLab Now

最後更新：`2026-08-24`

## 目前焦點

`integration/gui-polish-v1` 的前一個 visual checkpoint 在 2026-08-24 真人手測又揭露 BIDS revalidation
Cancel、Saliency repeat-training admission 與三項 3D／提示 presentation defect。Source 將再次修改，因此
既有 manual acceptance、focused totals 與 handoff evidence 均已失效；本 slice 完成前不得宣稱
handoff-ready 或可 merge。

本輪 UI 修改已取得明確授權。先做 red/green focused protection、non-author review 與輕量 walkthrough，
凍結 exact checkpoint 交使用者確認；只有同一 source 獲得 UI／流程確認後才跑 canonical heavy handoff。

## 2026-08-24 3D Plot 水平分布 closure

### 問題、outcome 與 scope

- 前一輪把 `Epoch time (s)` 與 slider 包在固定 `360–480px` 的置中 row；這只置中了整組，沒有像
  Preprocess time navigation 一樣使用完整可用寬度。PyVista horizontal scalar bar 亦沿用預設
  `position_x=0.35`、`width=0.6`，因此 `saliency` 色條明顯偏右。
- Ready 3D view 必須讓 saliency 色條以畫布中心為中心、左右留白對稱；Epoch time label固定在左，slider
  吃滿剩餘寬度，800與1180px皆左右margin對稱、無裁切或重疊。
- 只改3D presentation與直接幾何測試；不增加spin box，不改時間換算、Saliency計算、PyVista lifecycle、
  sidebar或其他Visualization views。沿用既有Saliency3D與Saliency3DPlotWidget owner，不新增abstraction。

### Repair、validation 與 stop condition

1. 先把既有固定寬置中assert改為observable red tests：scalar bar明確對稱、Qt time row填滿可用寬度。
2. 明確設定horizontal scalar bar的對稱position／width，刪除固定寬wrapper，讓scene controls直接採用
   Preprocess同型的label + expanding slider layout。
3. 跑3D time-slider與直接相鄰Visualization focused tests、changed-file Ruff／format與diff check；產生
   ready 3D輕量screenshot目視800／1180px分布。真人確認前仍不跑canonical heavy handoff。

若scalar bar中心不在畫布中心、time slider未隨寬度擴展、左右margin不對稱，或scene clear／time update
行為退化，即停在checkpoint，不交付手測。

### 施工狀態

- Red tests分別失敗於缺少explicit scalar-bar position與slider仍由固定寬wrapper擁有；最小修正後同組
  3 passed，相鄰Visualization focused維持234 passed。
- Production只觸及既有兩個3D view files，刪除固定寬nested row並明確指定色條`0.1 + 0.8 + 0.1`
  對稱分布；owner、public interface與行為policy均未增加。
- Changed-file Ruff、format與diff check通過；800／1180px Qt screenshots確認Epoch row全寬且無overlap。
  本WSL環境沒有可用X server，不能以offscreen PyVista artifact取代Windows/native 3D scalar-bar acceptance；
  exact position由direct API test固定，真人手測仍是本checkpoint的下一個gate。

## 2026-08-24 BIDS cancel 與 Saliency repeat-training closure

### 問題、證據與 observable outcome

- BIDS subject route 在 `Confirm and Import -> Preview/Validate -> Cancel Import` 重開 review 時，staged
  `value_decisions` 會整包覆蓋 backend observed mapping，導致 occurrence count／evidence 消失；hydrated rows
  又被當作未編輯 baseline，使 recheck false、顯示 `Cannot import yet`。重開後必須保留 count、evidence、
  `Use as`、class name 與所有未修改 event values，且不需再碰 controls 即可重新驗證；取消期間不得 apply、
  rescan 或 mutation。真正 incomplete／malformed review 仍 fail closed。
- 正常 async Compute Saliency 成功 publication 漏清已套用的 pending settings。第二次 training 產生新
  generation 後，UI 因此誤要求 `Review Saliency Settings Again`。只在 matching operation `SUCCEEDED` 時把
  staged settings settle 為 applied；尚未 Compute 的 custom settings 仍綁原 result 並要求 review。
- Saliency canvas 在結果可見前的 non-error empty／ready／rendering提示統一為 warning yellow；error維持紅色。
  Ready 3D scene 在 sidebar 顯示獨立 `3D PLOT` 群組，只包含 `Electrodes` 與 `Head surface`；Reset仍在
  `CONFIGURATION`。圖下 `Epoch time (s)` 與 slider 必須整組置中，800／1180px不得偏移或重疊。

### Scope、ownership 與 complexity review

- 不改 EEG event/class 科學語意、backend validation、Apply boundary、Saliency algorithm、自動計算政策、
  public command/schema、receipt或ownership；不加入PhysionetMI dataset特例或legacy contract fallback。
- ApplicationService仍擁有validation／mutation／publication；Data Interpretation coordinator仍擁有Qt
  continuation；event editor只投影backend evidence加user semantic draft；Visualization panel/sidebar只擁有
  既有UI lifecycle與presentation。owner數前後不變，不新增module、public class或state machine。
- Deletion／reuse first：以per-value overlay取代whole-map replacement、復用既有strict submission projection，
  共用兩條success path的pending-clear transition，並移動既有3D controls而非複製callbacks。完成後production
  diff為12 files、`+352/-134/net +218`，已觸發並完成complexity review；owner delta為0，沒有新增module、
  public class或state machine。以Data Import與Visualization兩個各自coherent、低於300 net LOC的product
  commit拆分；planning/evidence closure另成docs commit。若任一批net超過300 LOC、新增owner或總diff超過
  1,500 LOC，立即停止再拆分。

### Repair、focused validation 與 stop condition

1. 先以真dialog red tests固定backend counts/evidence與staged semantics分層，再以BIDS subject cancellation
   path固定Preview／Validate cancel、no mutation、recheck與retry；保留既有真正Apply-cancel regression。
2. 修正matched async Saliency success settle，新增first compute success -> unchanged retraining -> second compute
   可dispatch；保留unapplied staged settings遇新publication仍要求review的既有contract。
3. 完成prompt warning token、`3D PLOT` contextual group與centered epoch row，驗證empty/ready/error、tab
   visibility、toggle/reset callbacks與800／1180pxgeometry。
4. 跑focused selectors、changed-file Ruff／format check、diff check及輕量UI screenshot/walkthrough；主agent目視
   hierarchy、contrast、text fit與overlap。使用者確認前不跑canonical heavy manifest、source-diverse gate或CI。

若重開後任一count/evidence或choice遺失、staged choice可未經revalidation直接Apply、真正invalid review被放行、
第二次training仍顯示Review Settings、錯誤訊息被改黃、3D群組出現在unready/非3D view，或epoch row未置中，
即停在checkpoint，不交付正式handoff。

### 施工狀態

- BIDS observed evidence與staged semantics已分層；真BIDS subject Preview-revalidation cancel會重開同一可recheck
  review，counts／class choices完整、無`Cannot import yet`且零資料mutation。Commit-source Import focused為
  227 passed、2 skipped；兩個skip只因CHB-MIT與Sleep-EDFx optional public fixture尚未下載。
- Matching async Saliency success已settle pending settings；unchanged retraining可再次Compute，unapplied staged
  settings的stale-publication gate仍保留。Visualization focused為234 passed。
- Warning-yellow prompts、`3D PLOT` contextual group與480px centered epoch row已完成；exact-source focused
  walkthrough通過並產生Map／Spectrogram／Topomap／blocked-3D artifacts，另檢查ready sidebar與800px epoch row。
- Non-author code review無blocking finding；changed-file Ruff、format與diff check通過。Data Import與
  Visualization product commits已分開收束，commit-source focused selectors均通過；目前凍結為真人手測
  checkpoint。Windows native與canonical heavy handoff仍依使用者要求留在UI／流程確認之後。

## 2026-08-24 追加手測阻擋

前一輪輕量 walkthrough 後，使用者再確認六項必須在交付手測前修完的 observable defect；任何既有
manual acceptance 與 handoff evidence 仍不可沿用。本輪 UI 修改已取得明確授權，並依使用者要求先做
focused validation／輕量 screenshot，再交真人手測；只有使用者確認 UI okay 後才執行 canonical heavy
handoff。

- Match Labels 的背景 re-preview 按橘色 `Cancel Import` 後，必須重開同一 review 並保留 label pairing、
  placement、class 與 source choices；不得 apply、rescan 或因回到預設值額外觸發 alignment 提示。
- Import Review／Apply 尚未 terminal committed publication 時可以瀏覽 Preprocess，但 Filtering、Resample、
  Re-reference、Normalize、Epoch 與 Reset 等 mutation actions 必須 disabled，並以 inline
  `Import is still finishing...` 說明；不得用 warning modal 呈現正常 pending state。
- Saliency Map 在尚未 compute 時保留完整 `Gradient saliency has not been computed...` copy，並在 action
  bar 下方的剩餘 view 中置中，不得被 hidden scroll surface 推到底部。
- `Fold Set / All Folds` 是合法 explicit Compute Saliency target：按鈕保持可按，一次 command 綁定 backend
  admitted exact members，依 canonical Fold 順序逐筆 compute，全部成功才原子發布；任一 failure／cancel
  保留舊結果。設定與 selection 未變時不得誤入 `Review Saliency Settings Again`。單一 Fold 同樣必須
  exact-targeted，不得暗中計算所有 finished records。
- Visualization 的 Fold label 移除 model name，但 item identity／model truth 保留；其他 panel 文案不變。
- Control reading order 固定為 `Fold -> Run -> Saliency -> Method -> Normalize -> Absolute`，1180px 優先
  單排，800px／窄版最多三排且不得 overlap 或留下 hidden Absolute 空洞。

### Scope、ownership 與 complexity review

- 不改 import／label／event 科學語意、Saliency algorithm、Assistant tool schema、其他 panel Fold naming，
  也不自動 compute Saliency。
- 復用 `DataInterpretationActionCoordinator` 的 cancelled-review continuation、`OwnedWorkRegistry` 的 active
  operation truth，以及 TrainingManager 現有 sequential compute／atomic publication；不新增 owner、state
  machine、receipt family或compatibility path。
- `SaliencyCommand` 增加 optional typed selection target；visible product Compute 一律帶 target，query-only與
  既有無 selection caller維持原contract。resource receipt必須包含canonical target identity。
- 預估觸及約9個production files、`+240/-70/net +170 LOC`，超過8-file complexity review門檻但不增加owner；
  拆成 Import/Preprocess、Saliency target/batch、Visualization presentation 三個可回退commit。若production
  淨增超過300 LOC、新增owner/state machine，或本追加slice接近1,500 LOC，立即停止重新切分。

### Repair、focused validation 與 stop condition

1. 先以 observable red tests固定 re-preview cancel draft、import-pending preprocess fence、Fold Set compute、
   exact target、atomic failure/cancel、placeholder geometry、short Fold label與responsive control order。
2. 完成三個bounded implementation commits；各批跑相同red/green selector與直接相鄰test，再做非作者
   cross-review，不以mock choreography或production alias換取綠燈。
3. 執行focused unit/integration、Ruff／format check、configured type check及輕量UI screenshot/walkthrough；
   主agent目視pending、empty、compute與800/1180px states後交使用者手測，不先跑heavy manifest。
4. 使用者確認UI okay且source凍結後，才重跑canonical exact-source handoff與同SHA CI。

若cancel後draft不一致、pending import仍可進preprocess mutation、All Folds Compute未建立單一owned operation、
partial saliency被發布、stale target可覆寫新selection、或任一control／placeholder overlap，即停在checkpoint；
不得把其他focused PASS或舊evidence當成完成。

### 追加 slice 施工狀態

- 三個主要可回退commit已完成：`7765c587`收斂placeholder／Fold label／control order，`5bc95369`
  修正re-preview cancel與import-pending preprocess fence，`9207b177`建立exact Fold／Fold Set target、receipt
  scope、selected-method retention與原子publication。非作者review另找出active target會掉回legacy全量路徑、
  單Fold未綁current coverage，以及三條低-mock evidence缺口；第四個follow-up commit將只收斂這些
  fail-closed與tests/evidence contract，不擴大產品scope。
- Complexity review實際production diff為12 files、`+477/-84/net +393`；分批分別為net `+27`、`+118`、
  `+230`、`+18`，每批皆低於300 LOC，owner數沒有增加。保留typed target與ApplicationService registry adapter
  是維持exact command spine所必需；已避免的刪除候選是第二套batch coordinator、state machine、partial
  publisher與UI直讀registry。總diff遠低於1,500 LOC，不需要architecture exception。
- 合併後focused denominator目前為452 passed，另有backend saliency publication lifecycle 35 passed；Ruff、
  format、diff與configured Basedpyright沒有新增diagnostic。低-mock gate涵蓋真async/Qt cancel reopen、真
  ApplicationService owned-work transition，以及selected Fold Set cancel後同members retry且零partial publish。
- 第四個review-closure commit已凍結並push；clean exact-source輕量visualization render的四張2D／3D
  候選圖、control contract、source identity與clean shutdown皆通過，主agent目視亦未發現overlap、殘影或
  hidden-control空洞。下一步停在使用者手測；使用者明確確認UI okay前不跑canonical heavy manifest、
  跨來源資料集gate或CI，也不merge。

## 問題與 observable outcome

### Import 與 operation lifecycle

- `Confirm and Import` 後按橘色 `Cancel Import`，重新開啟 Review 必須保留已確認 class、label source 與
  其他 review choices；產品資料仍未 mutation。Review 頁面的灰色 Cancel 仍只丟棄未確認編輯。
- Evaluation 的 detached render 不是 user-owned workflow，不顯示橘色 `Cancel Evaluation`；replacement、
  navigation、close 與 shutdown 仍可取消並完整 cleanup。

### Saliency publication 與 controls

- Evaluation-admitted Fold Set 必須立即列出；尚未計算 Saliency 的 Fold Set 顯示明確 Compute prompt，
  不得借用舊 Fold 圖。重新訓練後自動選最新 Fold Set；舊結果仍可手動選取。
- `Saliency view` 與 `True class` 合併成單一 `Saliency:` combo，item data 使用 backend class key。
  `All classes` 不提供單一 tile zoom；點 tile 進入該 class detail。3D 收到 All 時自動選第一個可用 class。
- controls 依可用寬度排成一至三列；順序永遠是 `Normalize` 再 `Absolute`。Spectrogram 隱藏 Absolute
  時不得保留空 slot；非負 method 的 Absolute 仍顯示 disabled 與原因 tooltip。
- Run option 移除 `(Summary)`；2D detail在右側`CONFIGURATION`顯示contextual `Reset view`，All classes不顯示
  reset。

### Visualization

- Spectrogram 移除 `Attribution magnitude spectrogram` suptitle，保留 class title 與 colorbar。
- 3D 只保留 top-level class selector；`Electrodes`、`Head surface` 與contextual `Reset view` 放在右側
  `CONFIGURATION`，canvas不放action overlay。Epoch time slider位於圖下，右上只有一個orientation display。
- `Mean over ...` 不作 visible copy，只保留 tooltip／accessible description。
- 一個 accepted terminal publication 只允許一次 3D scene update／commit。

### 全站 modal presentation

- 同步 main 後重新盤點 Dataset、Preprocess、Training、Evaluation、Visualization、Assistant 與 Main Window
  的 warning／critical／information／confirmation。所有 blocking modal 最終必須走既有
  `modal_presentation`，production UI 不再直接使用 raw `QMessageBox`。
- 共用 modal 使用內容驅動高度、compact spacing、可選取且可換行的文字；長訊息在 bounded viewport
  捲動。Warning／Error／Information 使用 orange／red／blue severity。
- confirmation 的 Cancel／安全選項為 default，Escape 一律安全 reject。Resource receipt、destructive
  command、external HTTPS link、shutdown Retry／Close 與 worker preview lifecycle 必須保留現有 command、
  receipt、retry、cancel semantics。
- Inline epoch validation、review footer、loading status、saliency canvas error 等仍留在 workflow context，
  只校準 XBrainLab theme／spacing，不改成 modal。

## Scope、non-goals 與 ownership

- 不改 EEG interpretation、label、event、loader、training、evaluation 或 saliency 科學語意。
- 不自動 compute Saliency；既有 explicit command 仍負責所有 finished runs。
- 不新增 authoritative owner、state machine、receipt、compatibility path 或 public command。
- Application Service／workflow coordinator 繼續擁有 admission、mutation、publication 與 async lifecycle；
  modal component 只擁有 presentation。
- Deletion／reuse first：移除 raw QMessageBox helpers、第二套 3D selector、duplicate 3D dispatch、
  Evaluation visible cancel presenter、分離的 Saliency view/class controls，以及 hidden Absolute retained size。
- 預估 production diff `+350/-450/net -100`，但會超過 8 個 production files；依 workflow 拆 commit，
  每批由非作者 reviewer gate。若任一 coherent batch 淨增超過 300 production LOC 或總 production diff
  超過 1,500 LOC，停止並重新做 complexity split，不以 abstraction 隱藏規模。

## 修理順序

1. Merge 最新 main，建立 compact modal foundation 與 stable raw-QMessageBox source guard。
2. Dataset／Import：exact review reopen、dataset alerts／confirmations 與 async cancel tests。
3. Evaluation／Saliency lifecycle：移除 detached-render cancel presentation，publish unavailable Fold choices，
   對最新 uncomputed choice fail closed。
4. Visualization：合併 selector、responsive controls、2D interaction、Spectrogram title、3D layout／single commit。
5. Training／Preprocess／App／Chat：分批遷移 modal，保留 receipt、destructive、external-link 與 shutdown semantics。
6. 非作者 subagent review、focused closure、canonical exact-source handoff，最後才交付真人手測。

## 目前施工狀態

- 步驟 1–5 與非作者 review closure 已完成並以可回退 commit 收斂；production UI 的 raw
  `QMessageBox` source guard 已通過，沒有加入 compatibility alias。
- Global dialog policy 的安全 Cancel default 與 3D preparation／final scene failure retry 已由
  policy-installed keyboard、same-scene retry與stale-key tests保護；非作者closure無blocking finding。
- 同一整合focused denominator為926 passed；Ruff、format、Basedpyright、diff與raw `QMessageBox` guard均通過。
  Production diff為`+887/-613`、touched 1,500，未超過強制拆分門檻；owner數不變。
- Exact-source canonical manifest已在`complete-regression` fail closed：production行為focused tests仍綠，
  但完整UI shards揭露多個測試仍patch已退役的raw `QMessageBox` seam；backend visualization shard另有一個
  測試仍要求本slice已明確移除的Spectrogram suptitle。這些是過期test contract，不以production alias
  或恢復舊copy掩蓋。
- Draft PR另確認Windows／macOS lifecycle只被同一Dataset test seams阻擋；platform native lifecycle本身
  通過。Default visual candidate只有Visualization panel改變，且符合已核准的selector/order/layout outcome，
  但CI verifier仍只接受舊schema v1，和capture的canonical schema v2不一致。
- Tests-only closure 已改到實際 `show_warning`／`show_error`／`ask_confirmation`／
  `present_unexpected_error` helper，並移除會掩蓋意外 modal 的成功路徑 patch；沒有加入 auto-accept 或
  production alias。Spectrogram no-suptitle、UI baseline schema v2 fail-closed contract、完整 unit UI
  `2,686 passed`、integration UI `115 passed / 17 optional-public-fixture skipped` 與 verifier contract
  `33 passed` 均通過。
- 唯一有意變更的 Visualization reference 已由目前 production source 重新 capture、目視審查並更新；
  本地 exact-source offscreen 與前一 Linux CI/Xvfb candidate 位元組相同，更新後七張 baseline 為
  `0.00%` diff。本機 Xvfb 因唯讀 `/tmp/.X11-unix` owner/mode 錯誤無法啟動，不以 offscreen 取代最終
  Linux CI/Xvfb、Windows native 或真人 acceptance。
- 下一步只執行 source quality gates、凍結並 push exact SHA、從頭重跑 canonical manifest，以及確認同一
  SHA 的所有 non-skipped CI completed/success；任何失敗都回到 checkpoint。若需要任何 production 修改、
  測試只能靠 auto-accept modal 或削弱 observable assertion才會通過，立即停止並使目前 evidence 失效。
- 首次重跑已讓 complete regression 的八個 authoritative Linux groups 通過，並下載、校驗 required-ci
  public fixture profile；但 escalated canonical Basedpyright 揭露 3D overlay 新增的 `resizeEvent` 參數仍
  誤標為一般 `QEvent`。先前 sandboxed type run 因未實際掃到 diagnostics 而是假綠；相關 evidence 已失效。
  修正限定同一個 3D view file：改用 `QResizeEvent`，同時刪除兩行非必要新增註解，使 owner 不變且 production
  diff 維持 `+886/-614`、touched 1,500、net +272。Focused 3D/visualization `140 passed`；canonical
  escalated Basedpyright 實際掃描 70 個既有 diagnostics、沒有新增 diagnostic並已通過。下一步重新凍結
  exact SHA、push、從 section 1 重跑完整 manifest與同 SHA CI。
- 新 SHA 的 section 1／architecture／type gate 通過；required-ci profile 完整安裝後，complete regression
  額外執行先前缺 fixture 的路徑並揭露兩個 tests-only contract：teacher preflight 把合法 required-ci
  OpenNeuro cache 誤判成 teacher profile 部分安裝；resource-receipt integration helper 仍只會操作退役的
  `QMessageBox`，無法點擊 shared modal。該 manifest 已有確定 IO failure，因此主動中止本 agent 的單一
  session，避免等待三個 modal timeout；evidence 不可沿用。
- 下一步限定修正這兩個 test contracts：teacher gate 必須區分完整 required-ci 與真正 partial teacher
  profile；resource-receipt 必須操作實際 visible shared modal buttons，不使用 auto-accept、presenter mock、
  production alias 或削弱 mutation／terminal assertions。Focused required-fixture tests與完整 affected shards
  通過後，重新凍結 SHA、push並從 section 1 重跑完整 manifest。
- Shared modal driver 整合後，confirm case另證明舊 `generation == before + 1` 把單次 import mutation與獨立
  async BIDS montage publication混為一談；實際 montage已合法進入ready並產生第二個generation。測試改保護
  generation必須前進、raw truth完成、一次loaded item、零legacy import event／panel refresh、一次terminal與
  receipt consumption；不得固定為`+2`或移除 mutation/lifecycle assertions。
- 兩個 required-fixture contracts 已 tests-only 修正並在完整 cache 重驗：integration IO `56 passed / 11`
  個 teacher／multisubject optional skips；canonical integration UI `130 passed / 2` 個 teacher-only skips，
  resource-receipt三個真 modal cases全數通過。Production diff仍為30 files、`+886/-614`、touched 1,500；
  下一步只剩final quality gates、凍結/push exact SHA、完整manifest與同 SHA CI。
- `faba9a0c` 的 manifest 已通過 section 1、完整回歸、required fixture、跨來源訓練、Assistant、import、
  human-like 與 UI baseline，最後在 visualization render fail closed。Artifact 證明產品正確移除
  Spectrogram 的 Absolute layout item 並於其他 tab 恢復，但 walkthrough validator 仍要求 hidden control
  保留原 grid slot，直接違反本 slice 的「不得留空洞」contract。下一步只做 tests／evidence contract
  校準：要求 hidden Absolute 無 grid position、Normalize slot 穩定且在 visible Absolute 前；focused validator
  與單一 visualization render 通過後才凍結新 SHA，既有 `faba9a0c` evidence 不宣稱 handoff-ready。
- `6f603e41` 已讓上述 visualization validator與真 render通過；完整回歸亦通過，但並行 post-regression
  lanes 使單獨只需53秒、`94 passed`的Assistant security suite超過1,800秒timeout。使用者要求後續UI先
  輕量手測、確認後才跑重型驗證，因此不再重跑heavy tail。Primary artifact review另在800px panel揭露
  control mode誤用整個panel寬度，導致實際約496px的control bar仍選medium並讓Fold combo／Run label重疊。
  下一步只修正既有responsive width判斷、補窄寬observable test並重拍輕量圖；通過後交使用者手測，
  不先啟動canonical heavy gates。
- Responsive width 已恢復使用 sidebar-aware 可用寬度並保留 wide／medium／narrow 三段；760px panel走三列、
  1180px panel走單列，幾何與不重疊 contract `87 passed`。15秒真render walkthrough通過且primary artifact
  review確認2D controls／canvas／colorbar正常。交付前盤點另以真實tab transition重現並修正3D blocked view：
  montage readiness現在保留已發布method、從All自動選第一個可用class，且top-level 2D detail reset不再於3D重複。
  Red reproduction已轉綠，focused visualization `236 passed`、Ruff／format與15秒真render通過；新primary artifact
  確認blocked 3D顯示`Gradient`／`left`、沒有第二個top-level reset。下一步凍結、push exact SHA並交使用者輕量手測；
  在明確UI okay前不補跑post-regression heavy tail。

## Focused validation

- Red／green tests：Cancel Import exact choices、無 visible Cancel Evaluation、Fold Set unavailable/Compute、
  old result accessibility、single 3D commit、selector identity、All/detail zoom policy、Normalize→Absolute 三段 layout。
- Modal component tests：severity、compact geometry、long text、safe default、Escape、destructive style；各 workflow
  測試 receipt replay、cancel、retry、stale callback 與 shutdown fence。
- 每批執行對應 unit／integration selectors、Ruff、format check 與 diff check；source guard 阻止 raw
  QMessageBox 回流，但不限制 intentional inline status。
- Final handoff 使用 `scripts/dev/handoff_gate_spec.py` 的唯一 registry；本 slice 涉及 import、training、
  evaluation、visualization，canonical source-diverse dataset 與 native Qt／MNE gates 均 applicable。
- 可見修改產出 exact-source screenshot／walkthrough。Offscreen 不取代 Windows native focus、Escape、DPI、
  OpenGL／3D 與真人 acceptance。

## Stop conditions

- Cancel Import 無法恢復 exact review choices，或取消後 product data 已部分 mutation；
- 未計算 Fold 顯示舊圖、自動啟動 Compute，或 stale callback 覆蓋較新 selection；
- 一次 terminal publication 觸發多次 3D commit，或 close 後仍有 worker／native wrapper；
- modal migration 改變 receipt、confirmation、retry、destructive 或 security semantics；
- raw QMessageBox source guard、focused test、Ruff、type gate、canonical data gate、native walkthrough 或 exact
  source identity 任一失敗；
- final source 修改後沿用舊 handoff 或 manual acceptance。

任一條件發生即停在 checkpoint 修正；不得以其他 family 已通過、skip、retry 或人工目測掩蓋。
