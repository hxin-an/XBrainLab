# XBrainLab Now

最後更新：`2026-08-27`

## 目前焦點

### Active slice：`2026-08-27-ui-montage-accuracy / shared-alert-single-surface`

- **Branch / base**：`ui/shared-alert-card-v1`，base `main` @
  `2c51d7b1e6ff83475f285f0db331becd3f87f5c1`。
- **問題與證據**：使用者手測否決現行 acknowledgement alert 的「dialog 裡再包一張卡」外觀：
  `ModalAlertContentCard` 的 background／border／accent left edge 使單一警告被看成卡片中又有卡片。
  雖然 severity、標題、正文與單一 OK 已存在，這個內層 surface 破壞原本產品 dialog 的清楚層級。
  本 slice 以 default／narrow／long-text offscreen screenshots 作 layout evidence；它們不能取代
  WSLg 手測。
- **Review refinement**：single-surface 初版的 icon/title/severity 與 message 有兩個不同的左邊界：
  icon 後的 title/severity 在右側 column，但 message 回到 dialog 左邊界，long-text 時尤其破壞閱讀軸線。
  將全部文字 copy（含透明 scroll viewport）放入 icon 右側同一 content column；footer OK 仍維持右對齊。
- **Review refinement 2**：初次 column 修正仍讓 copy column 的 available height 均分給 title／severity／message，
  造成視覺上的大段空白。column 使用 `AlignTop` 收斂其內容，讓行間只保留 layout 的小 spacing，將剩餘空白
  留在 compact copy block 與 footer 之間；不加固定 screenshot pixel size。
- **Observable outcome**：所有既有 acknowledgement alert（Information、Warning、Error）維持
  `show_*` call contract、severity icon、標題、severity、正文、單一 `OK`、Enter／Escape 與長文
  捲動，但只使用 dialog 的一個表面：不得有 bordered／background 的內層 content card 或 styled
  panel。
- **Scope**：只改共用 acknowledgement-alert presentation 與其直接 focused tests/screenshots；
  覆蓋三種 severity、長文、窄視窗、DPI、Enter／Escape／close。
- **Non-goals**：不改 confirmation、destructive modal、安全預設、side effect、modal ownership、
  public `show_*` API、其他 Dataset／Electrode／Assistant UI；不新增 bitmap asset 或第二套
  modal framework。
- **UI approval**：使用者已明確批准此 acknowledgement alert UI 修改；confirmation/destructive
  modal 明確不在 scope。任何擴至其他可見流程的變更必須重新取得批准。

### Ownership、complexity 與 deletion/reuse

- **Owner before/after**：既有 `ModalAlertDialog` 繼續是 acknowledgement presentation owner；
  existing callers 繼續決定何時顯示何種 alert。不得新增 authoritative owner、state machine 或
  compatibility path。
- **Reuse/delete first**：沿用既有 dialog、`show_*` API、theme primitives 與 keyboard handling；
  優先刪除/整併散落的 plain-text severity presentation，而非新增 alert framework。若 source
  inspection 發現只有單一 caller 的 legacy severity helper，應在同一 diff 移除或收斂。
- **Actual / deletion intent**：既有 `ModalAlertDialog` 是唯一 owner。刪除 acknowledgement-only
  `ModalAlertContentCard`／`content_card` presentation path，將現有 icon/title/severity/message 直接
  放在 dialog layout；不新增 class、API、owner、state machine 或 compatibility path。confirmation
  的既有 heading/message path 完全不動。目前 production delta 是 `+17/-34`（net `-17`），不觸發
  complexity review。

### 實作與驗證

1. 加入一個最小 red UI-observable test：acknowledgement 不含 `ModalAlertContentCard`／styled panel，
   同時保留 icon/title/severity/message、單一 OK、Enter／Escape 與 long-text scroll。不得以 mock
   choreography 取代 UI-observable state。
2. 只在既有 `ModalAlertDialog` 做 deletion-first repair，讓 acknowledgement content 直接位於
   dialog layout；再將 title/severity/message（含 scroll viewport）放入 icon 右側的一個 copy column，
   以 layout parentage 而非 brittle absolute pixels 保護共同左軸。confirmation path 不動。
3. 重跑 focused tests、Ruff、diff check，並重新產出／檢視 default offscreen artifacts。
4. 交付 root review；此 branch 不 push、merge 或記錄新的 manual acceptance。source 改動使先前
   WSLg acceptance 無效，必須重新手測。

### Builder evidence（待 reviewer / root exact-SHA）

- **Red**：新的
  `test_acknowledgement_alert_has_single_surface_hierarchy_without_inner_card` 在 pre-repair source
  對 Information／Warning／Error 三個 parametrized cases 都因 `dialog.content_card` 不是 `None`
  失敗；這直接重現被否決的 nested-card surface。
- **Green**：
  `timeout 90s prlimit --core=0 -- env PYTHONPATH="$PWD:<locked site-packages>" MNE_DONTWRITE_HOME=true MPLCONFIGDIR=/tmp/xbrainlab-alert-green-final2 QT_QPA_PLATFORM=offscreen <locked python> -S -m pytest --capture=sys tests/unit/ui/components/test_modal_presentation.py tests/unit/ui/test_dialog_button_policy.py -q`
  → `19 passed`。single-surface test 保留 icon/title/severity/message，驗證沒有
  `ModalAlertContentCard` 或 `StyledPanel`；shown dialog 的 `message_label`／long-text scroll
  viewport 都與 title 共享相對左軸，long-text icon 與 title 共用 top edge；short alert 三個 text
  labels 都不超過其 natural `minimumSizeHint` height，防止 column 再把空白分散到 text rows。long-text
  test 也驗證透明 scroll viewport、vertical movement。confirmation 的 Escape/default/click/button policy
  維持通過。
- **Static**：Ruff 對 `modal_presentation.py`、focused test 與 capture script 的 check／format
  皆通過；`git diff --check` 通過。
- **Artifacts**：以 `PYTHONPATH=$PWD QT_QPA_PLATFORM=offscreen` 執行
  `scripts/dev/capture_modal_alert_presentation.py --output-dir
  build/dev-artifacts/modal-alert-presentation-single-surface-compact`，產生
  `information.png`、`warning.png`、`error.png`、`long-text.png`、`narrow.png` 與 source-bound
  `modal-alert-presentation-evidence.json`。builder 檢視 warning／narrow／long-text：icon、title、
  severity、message 與單一 OK 直接位在 outer dialog；long-text viewport 為透明、無 inner card，
  scrollbar 可見且文字沒有 clipping。所有 copy 在 icon 右側的單一 top-aligned compact column 左對齊、
  icon top-aligned；severity 字樣維持為次要黃色 metadata，沒有與白色 title 競爭。
- **Claim boundary**：Linux Qt offscreen layout evidence不能取代 WSLg／Windows native DPI 或人類手測。
- **Status**：builder checkpoint。worktree 尚未 commit，不能稱 exact-SHA evidence；等待 root
  review、commit 後的 exact-SHA verification、新的 WSLg manual acceptance 與使用者 merge approval。

### Roles、review 與停止條件

- **Builder**：Alert builder 只寫本 branch 的 alert route、直接 tests 與本 active plan；不得碰
  root `settings.json`、Dataset/Electrode 或 Assistant source。
- **Independent reviewer**：UI Product Reviewer 唯讀檢查 hierarchy、contrast、wrapping、
  clipping、focus、keyboard、default/narrow/DPI，以及 confirmation 沒有被誤改；不得 edit 或
  approve merge。
- **Root**：唯一負責 scope、branch/base identity、review finding admission、exact-SHA rerun、PR/
  CI 與 handoff gate；root 不以 reviewer finding 靜默擴張 scope，也不能自動 merge。
- **Stop condition**：當 focused tests、visual artifacts、independent reviewer 與 root
  exact-SHA verification 都完成時到 `checkpoint`，等待 WSLg 使用者手測。僅使用者在相同 source
  SHA 明確通過並同意 merge 才能合併；source 改動使 manual acceptance 失效。

### Preserved non-active checkpoint：Data Import performance

- 在 WSL `/mnt/d` 的 OpenNeuro ds003061 `sub-001`（一次 warm-up、三次 fresh
  `ApplicationService` catalog → review → apply → background idle）中，final net `-5` candidate
  blocking median 是 `12.046162s`，background median 是 `1.530436s`，stable-idle median 是
  `13.558181s`。10 秒 performance gate 未通過。
- exact `31b79daf` read-only audit：Review 約 `4.6s`，有 241 次 `resolve`、627 次 `stat`；
  `_scan_after_resource_preflight` cumulative `3.523s`，兩次 `bids_summary` cumulative
  `1.534s`。`/mnt/d` repeated `lstat` 是 dominant cost；約 190 MB 的 Review identity hash、
  EEGLAB load 與 session copy 不是主因。
- 新 characterization 證明 preflight BIDS summary（`materialize=False`、無 metadata guard）與
  admitted materialization（`materialize=True`、有 admitted guard）是不同安全階段；後者才可
  產生 participants／sidecar metadata。symlink/containment 行為維持既有 focused test。
- 因此不能安全 deduplicate：preflight 的 layout/events/channels selected scope 是 resource
  admission 輸入；以 materialized output 取代它會倒置 admission，重用 preflight output 會讓
  未 admitted metadata 進入 candidate。沒有 production change。
- Apply final full rehash 與 `SourceFileBoundary` 維持必要安全邊界；不為速度弱化它們。

### Preserved non-active follow-up：Data Import performance

- 依使用者要求，下一步將目前 baseline 做 exact-source handoff：clean/explained exact source
  commit 後執行 canonical handoff manifest、source-diverse dataset gate、push PR/CI，再交 WSLg
  使用者手測與明確 merge approval。
- 已知限制是 blocking 約 `12.046s`；不宣稱 performance gate 達成或 handoff-ready。root
  `settings.json` 是使用者本機設定，不納入此 slice。
