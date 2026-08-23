# XBrainLab Now

最後更新：`2026-08-24`

## 目前焦點

`integration/gui-polish-v1` 的前一個 exact-source handoff 已通過，但其後 Windows／Linux 真人手測
揭露 Data Import cancel、Evaluation operation presentation、Saliency result admission／controls、2D／3D
layout 與 warning modal consistency 問題。Source 將再次修改，因此前一份 manual acceptance 與 handoff
evidence 均已失效；本 slice 完成前不得宣稱 handoff-ready 或可 merge。

本 slice 已取得明確 UI 修改授權。目標是在同一 branch 以多個可回退 commit 完成所有已列出的 GUI
缺陷、全面收斂 user-visible modal presentation，經 focused tests、非作者 subagent gate 與 canonical
handoff 後一次性交付真人手測。

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
- Run option 移除 `(Summary)`；2D detail 使用緊湊 `Reset zoom`，All classes 不顯示 reset。

### Visualization

- Spectrogram 移除 `Attribution magnitude spectrogram` suptitle，保留 class title 與 colorbar。
- 3D 只保留 top-level class selector；canvas 左下放 `Electrodes`、`Head surface`、`Reset view`，
  Epoch time slider 位於圖下，右上只有一個 orientation display。
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
