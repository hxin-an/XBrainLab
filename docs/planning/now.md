# XBrainLab Now

最後更新：2026-08-17

## 目前焦點

**在 assistant/unified-eeg-source-v1 建立一個由 Dataset 主介面與 Assistant 共用的薄 EEG
source chooser，取代分散的 file / folder / BIDS 起點，同時保留既有 Data Interpretation、BIDS
subject selection 與 async lifecycle owner。**

使用者已於 2026-08-17 明確授權本輪 UI 修改，並確認：

- 主介面與 Assistant 共用同一個薄 chooser；
- 主介面只保留 Import Data 與 Reload recipe，不保留三個舊 import 捷徑；
- chooser 只負責選擇或預填來源，不能建立第二套 import state 或繞過 Import Review；
- 後續 21-tool catalog、no-LLM smoke 與 tool architecture 刪減各自使用獨立 PR。

## 問題與證據

- Dataset sidebar 目前以 Import file、Import folder、Import BIDS 三個按鈕進入同一個
  Data Interpretation workflow；Assistant 的 SCAN_SOURCE handoff 又固定呼叫 file picker。
- Backend source_hint=auto 已能以 bounded source discovery 判斷 file、folder 或 formal BIDS；
  但一般 folder path 不會在 review 前先進入現有 BIDS subject selector。
- Native file dialog 無法可靠地跨平台同時選 files 與 folders，因此需要一個薄 Qt chooser 包裝
  既有 file / folder dialogs。它只保存 dialog-local selection，不擁有 authoritative state。
- Formal BIDS discovery 已由 immutable bounded index、subject catalog 與 selected-subject projection
  擁有；UI 不得複製 dataset_description.json 或目錄 heuristic。
- Worktree 只有 repo-root settings.json 是使用者本機 runtime 修改；不得 stage、commit、revert
  或隱藏。

## Observable outcome

- Import Data 開啟單一薄視窗，提供 Choose files...、Choose folder...、selected-source summary、
  Continue 與 Cancel。
- 可選多個 EEG files 或一個 folder；不可混合 files 與 folder。單一路徑可由使用者貼上，未按
  Continue 前不得 scan 或修改 ApplicationService state。
- Folder 先經既有 SCAN_SOURCE catalog-only read path 取得 typed source_kind。Formal BIDS 進
  既有 subject selector；generic folder 進既有 Import Review。Files 直接進既有 Import Review。
- Cancel、空 selection、無效 path、BIDS subject cancel、classification failure 都回傳 terminal
  InteractionOutcome，且不發布 partial interpretation state。
- Dataset sidebar 不再顯示三個舊 import buttons；Reload recipe、active import cancel、label 與
  channel actions不變。
- Assistant 現有 Data Import handoff 使用同一 import_data() entry；本 PR 不改 model-facing tool
  catalog，也不新增 Assistant path prefill contract。

## Scope、ownership 與 complexity

- Owner before / after：ApplicationService 擁有 scan / publication；
  DataInterpretationActionCoordinator 擁有 import async lifecycle；既有 BIDS subject dialog 與
  Import Review 擁有人類決策。Owner 數不增加。
- 新 chooser 是 private UI selection surface，只回傳 detached source selection；不是 owner、state
  machine、receipt 或 compatibility path。
- Deletion candidates：sidebar 三個 import buttons / labels / callbacks，以及不再被 production
  呼叫的 separate folder / BIDS entry wrappers。
- 必要新增：一個薄 dialog seam，因 native picker 無法跨平台表達 files-or-folder；它由主介面與
  Assistant 的共同 import_data() entry 使用。
- 預期不超過 8 個 production files，production 淨增低於 300 LOC。若新增 authoritative owner、
  總 production churn 超過 1,500 LOC，或需要另一套 BIDS heuristic，停止並重新切片。
- Non-goals：不改 label / event inference、recipe schema、preprocess、epoch、training、Saliency、
  model download、21-tool catalog、Granite prompt 或 settings.json。

## Ordered repair

1. 建立 focused red tests：單一入口、files/folder selection、auto BIDS routing、Cancel 不 mutation，
   以及 Assistant handoff 呼叫共同 entry。
2. 擴充既有 catalog-only scan read path，使 source_hint=auto 回傳 typed source_kind；BIDS 才附
   subject catalog，generic folder 不發布 interpretation state。
3. 建立薄 chooser 與 detached selection result；選擇按鈕只更新 dialog-local preview。
4. 將 DataInterpretationActionCoordinator.import_data() 收斂為唯一入口，按 typed selection
   委派既有 file review、generic folder review或BIDS subject selection。
5. Sidebar 收斂為 Import Data + Reload recipe，移除可見 separate entry 與 callbacks；既有
   non-sidebar compatibility facade 不擴張，後續有真實 caller inventory 時再獨立決定移除。
6. 跑 focused / same-class tests、Ruff、Basedpyright、UI artifact與 applicable CI；交付 exact SHA
   給使用者手測，批准前不合併。

## Focused validation

- TDD：chooser、Dataset action coordinator、BIDS catalog-only classification、sidebar與 Assistant UI
  handoff tests。
- Same-class：single / multi-file、BrainVision sidecars、generic folder、formal / nested BIDS、empty /
  missing source、cancel / retry、busy import與stale completion。
- UI artifact：default scale與 narrow width；檢查 hierarchy、text fit、focus、keyboard、button order、
  clipping、empty/error/cancel states。主 agent 必須實際查看。
- Existing platform product walkthrough 必須保留，不跳過 Windows / macOS CI；offscreen evidence 不
  取代使用者 native acceptance。
- 本 slice 只支撐「共用來源入口與既有 import lifecycle routing」，不外推 dataset diversity、
  full BIDS compliance 或 downstream scientific correctness。

## Implementation checkpoint

- PR #28 已合入 main；本 branch 從 merge commit b14dd5ea 建立，root settings.json 仍是
  使用者既有本機修改，未被本 slice 修改、stage 或隱藏。
- Exact red→green 已完成：chooser 在 accept 前只保留 detached selection；catalog-only auto
  classification 對 file、generic folder、formal BIDS 回傳 typed source_kind，missing path 不發布
  partial interpretation；BIDS classification重用既有 subject selector。
- Dataset sidebar 已只顯示 Import Data 與 Reload recipe；Assistant 現有 Open Data Import handoff
  仍呼叫共同 import_data() entry。舊 folder / BIDS facade 沒有 sidebar caller，也未新增 state。
- Focused contract 13 passed；exact-source Data Interpretation / Dataset / ApplicationService / product
  walkthrough same-class sweep 1044 passed。Ruff check/format、targeted
  Basedpyright、git diff check 與 MkDocs strict 均通過。
- Public real-fixture兩個代表案例因本機未下載 fixture而明確 skipped，沒有將 skip 說成資料集
  成功。Default 460×300 與 narrow 320×300 chooser artifacts 已由主 agent 實際查看，無 clipping、
  overlap 或錯誤 button hierarchy；offscreen evidence 不取代 native manual acceptance。
- Production 目前觸及 10 files，380 additions / 146 deletions，net +234 LOC；新增的是一個必要的
  Qt external seam，owner 數不變，沒有新增 state machine、receipt或第二套 BIDS heuristic。
- 目前仍是未提交 checkpoint；尚缺 exact commit、CI 與使用者 native 手測，因此不稱
  handoff-ready、不合併。

## Stop conditions

- 若按 Continue 前發生 filesystem scan、ApplicationService mutation或interpretation publication，
  不得交付。
- 若 generic folder / BIDS 判斷依賴 UI 自建 heuristic、exception message parsing或 direct backend
  helper call，停止並改回 command spine 的 typed result。
- 若 Cancel、failure或stale callback留下 active handoff / busy state，不得交付。
- 若 exact-source artifact未查看、required CI未 success或新 source未由使用者手測通過，只稱
  checkpoint，不合入 main。

本 PR 合併後，下一個獨立 branch 才執行 21-tool catalog、panel affinity與 deterministic no-LLM
smoke。長期目標讀 [Roadmap](roadmap.md)，evidence contract只讀
[Validation](../validation/README.md)。
