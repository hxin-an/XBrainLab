# XBrainLab Now

最後更新：`2026-08-27`

## 目前焦點

### Active slice：`2026-08-27-ui-montage-accuracy / shared-alert-card`

- **Branch / base**：`ui/shared-alert-card-v1`，base `main` @
  `2c51d7b1e6ff83475f285f0db331becd3f87f5c1`。
- **問題與證據**：目前共用的 pure-text Information／Warning／Error acknowledgement dialogs
  是平鋪文字與等權按鈕的 presentation，缺少 severity、標題與內容層級；使用者已多次指出
  warning panel 視覺品質不符合產品風格。此 slice 的可見證據為既有警告 dialog 截圖與本次
  completion 後的 default／narrow／long-text screenshots；offscreen 僅供 layout evidence，不能
  取代 WSLg 手測。
- **Observable outcome**：所有既有 acknowledgement alert（Information、Warning、Error）維持
  現有 `show_*` call contract 與單一確認行為，但以一致的 severity icon、明確標題、accent card、
  正文層級與單一 `OK` 呈現；長文可閱讀／選取／捲動，且 keyboard close 行為不退步。
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
- **Actual**：1 production file，`+108/-31` production LOC（net `+77`），無 public API、owner delta 或
  complexity trigger；另有 1 focused test file 與 1 ignored-dev-artifact capture script。未新增
  public class、state machine 或 compatibility path。

### 實作與驗證

1. Builder 先定位共用 alert route、theme tokens 與所有 acknowledgement callers，確認
   confirmation branch 未共用欲改的 presentation path。
2. 用最小可觀察的 red test 描述 severity/title/one-acknowledgement/keyboard/long-text behavior；
   不以 mock choreography 取代 UI-observable state。
3. 只在既有 `ModalAlertDialog` 內做最小 coherent presentation repair，重跑相同 focused tests
   與直接 adjacent evidence。
4. 產出 Information／Warning／Error、long-text、narrow/DPI screenshot 及 user-like walkthrough。
   Offscreen screenshot 只能證明 geometry；WSLg manual acceptance 仍由使用者完成。
5. 交付 exact HEAD、base、clean/explained status、production LOC、focused command/output、
   screenshots 與已知限制；再進入 independent UI review 和 root exact-SHA verification。

### Builder evidence（待 reviewer / root exact-SHA）

- **Red**：`test_acknowledgement_alert_has_severity_card_icon_and_visible_title_hierarchy`
  在 pre-repair source 對三種 severity 都因缺少 `content_card` 失敗；其餘既有 coverage 通過。
- **Green**：
  `timeout 90s prlimit --core=0 -- /home/administrator/.cache/pypoetry/virtualenvs/xbrainlab-xaLO7TCQ-py3.12/bin/python -m pytest --capture=sys tests/unit/ui/components/test_modal_presentation.py -q`
  → `16 passed`。新增 acknowledgement Escape-close 與 long-message vertical scrollbar movement
  assertion；既有 destructive confirmation Escape/default/click/public mapping tests 維持通過。
- **Static**：Ruff 對 `modal_presentation.py`、focused test 與 capture script 通過；`git diff --check`
  通過。
- **Artifacts**：default offscreen run 以 `PYTHONPATH=$PWD QT_QPA_PLATFORM=offscreen` 執行
  `scripts/dev/capture_modal_alert_presentation.py`，產生
  `build/dev-artifacts/modal-alert-presentation/{information,warning,error,long-text,narrow}.png`
  與 source-bound manifest。另以 `QT_SCALE_FACTOR=1.5 --scale-label 150-percent
  --expected-device-pixel-ratio 1.5` 產生相同檔名於
  `build/dev-artifacts/modal-alert-presentation-150pct/`；manifest 記錄 observed DPR `1.5`、
  logical DPI `96.0`。Builder 已檢視 long-text/narrow 150%：無 clipping，scroll viewport 保持
  dark card background。
- **Claim boundary**：兩組都是 Linux Qt offscreen layout evidence；150% run 只證明 Qt reported
  DPR 與此 capture path 的 geometry，不能取代 WSLg／Windows native DPI 或人類手測。
- **Status**：產品碼、focused test 與 default/150% offscreen layout evidence 已完成；仍是
  `checkpoint`，缺 independent UI review、root exact-SHA verification、WSLg manual acceptance
  和使用者 merge approval。

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
