# XBrainLab Now

最後更新：`2026-08-28`

## 目前焦點

`main` 已合併 Dataset compatibility cutover PR #67，產品基線為 `b117e85f`。目前先完成一個
獨立、單一用途的 Visualization UI slice：Electrode Layout 只在 Dataset 提供正式入口，
Visualization 只消費已發布的 layout 狀態，不再常駐顯示相同按鈕。

完成並手測合併這個 UI slice 後，依序同步與收斂 Import correctness candidate，再回到 Assistant
效果迭代。主 agent 擁有 scope、exact SHA、review、PR／CI與手測交付；worker 不自行宣稱完成。

## Active slice：Visualization Electrode Layout 單一入口

### 問題與證據

- Dataset 與 Visualization 目前各顯示一個同名、同層級的 `Electrode Layout` 常駐按鈕，容易讓使用者
  誤以為存在兩套設定或不同 lifecycle。
- Visualization 並沒有自己的 montage owner；它的按鈕只呼叫
  `DatasetSidebar.open_electrode_layout()`，共用同一個 dialog、ApplicationService command與
  publication state。重複入口沒有提供第二項能力，只增加 UI 與測試接線。
- Visualization 的 setup-only copy 目前寫著 `Electrode Layout remains available.`；移除常駐入口後，
  這段文字必須明確指出設定位置在 Dataset，不能暗示本頁仍有操作。

### Outcome

1. Dataset 保留唯一、正式的 `Electrode Layout` 按鈕與既有功能。
2. Visualization 不建立或呈現 `btn_montage`，也不保留轉接到 Dataset 的 UI action。
3. 缺少位置而無法顯示相關視圖時，Visualization 只提供指向 Dataset 的狀態說明；不自動切頁、
   不新增快捷按鈕。
4. Backend command、ApplicationService ownership、Assistant montage handoff、dialog與已發布 layout state
   完全不變。

### Scope、non-goals、假設與 UI 確認

- Branch：`ui/visualization-layout-entry-v1`；從 exact `main` `b117e85f` 建立。
- Production scope 僅限 Visualization sidebar／直接相關 presentation cleanup；測試與 UI artifact只處理
  這個入口及其 empty/setup-only state。
- 刪除優先：移除按鈕、signal、delegation method、saliency busy-control reference與失真的 copy；不建立
  新 helper、owner、navigation route、compatibility path或 state machine。
- 不改 Dataset UI、Electrode Layout dialog、montage mapping、BIDS偵測、tool contract、Assistant或 backend
  邏輯／contracts；唯一例外是 canonical position-dependent blocked copies（topographic 與3D）也必須明確
  指向 Dataset。不得順手重排其他 Visualization controls。
- 假設 Dataset panel 是桌面產品中可到達的正式設定面；Assistant 已直接呼叫 Dataset owner，不依賴
  Visualization shortcut。
- 使用者已於 `2026-08-28` 明確確認：Dataset 是唯一入口，Visualization 移除按鈕，並以一個獨立 PR
  處理。這項確認授權上述可見 UI／copy 修改。

### 修理步驟

1. 先加／調整 observable UI test，證明 Visualization sidebar 不呈現 Electrode Layout，且 Dataset
   入口仍存在；現有 source 需因仍建立按鈕而失敗。
2. 移除 Visualization 的按鈕、signal、delegation method與 busy-state reference，更新 setup-only copy。
3. 清理只服務被刪入口的 mock-heavy／implementation-detail tests；保留 Dataset owner、Assistant handoff
   與 montage state evidence。
4. 執行 focused behavior tests、Ruff／format、相關 Visualization screenshot／walkthrough，再由獨立
   UI／test reviewer檢查 hierarchy、空／blocked state與 Dataset 唯一入口。
5. 建立 PR、等待同一 exact head 的所有 non-skipped CI成功，再交使用者 WSLg手測；只有同一SHA
   手測通過並明確同意merge後才合併。

### Focused validation 與 stop condition

- 最小 red／green：Visualization sidebar structure test、setup-only copy test，以及 Dataset sidebar
  Electrode Layout presence test。
- Adjacent：Visualization busy-state、product walkthrough與Assistant montage handoff focused tests；只在
  直接受刪除屬性影響時更新。
- Visible UI：以 exact source capture至少檢查 default與窄寬、empty／setup-only／ready state；offscreen
  artifact不取代使用者 WSLg／Windows native驗收。
- Stop condition：production owner不增加、Visualization不再含可操作 montage入口、Dataset與Assistant
  owner路徑仍通過、沒有失真copy、focused evidence與reviewer均通過。任何擴及 backend、Dataset layout
  或新導航流程的需求另開 slice。

## 其他 lane 的目前狀態

### Import correctness

- Candidate worktree：`fix/windows-import-correctness-v1`，目前 exact head `5493bca9`，基於 PR #67前的
  `main`。它保留 `919a2b7f` 的 correctness cleanup，不合併已拒絕的 parallel experiment，也不宣稱
  效能改善。
- Native Windows evidence顯示 Apply約佔 blocking median `83.6%`；既有安全平行實驗沒有達到採用門檻。
  Windows parsed-cache A/B沒有 candidate-only failure，修復兩個parent-only descriptor failure；剩餘六項
  是 Windows conservative full-read與POSIX open／reuse expectation差異。
- 下一步必須先同步最新 `main`，重跑受影響 data／CI gates與review，再交付獨立 Import手測。

### Assistant effect

- Candidate worktree：`fix/assistant-effect-iteration-v2`，目前 exact head `85249548`。
- 固定 v10 evaluator 的 core、parameter-origin、missing guard通過，但 clarification為 `0/7`，unexpected
  unsafe為 `2`，strict candidate gate失敗；目前不交使用者手測、不建立merge claim。
- 下一輪仍需在既有 verifier／receipt／prompt授權內取得可驗證改善；若要新增 semantic router、模型或
  public tool contract，必須另作使用者／architecture決策。

## Handoff、合併與收尾順序

1. Visualization單一入口：focused evidence → reviewer → PR／CI → 使用者手測 → merge。
2. Import同步最新 `main`：重跑受影響 evidence → reviewer → PR／CI → 使用者手測 → merge。
3. Assistant同步最新 `main`並繼續效果迭代；只有達到批准gate或另獲bounded-baseline批准才手測／merge。
4. 每次合併後移除已完成 active slice、清理已合併 task worktree／branch，並保留使用者 root
   `settings.json`。完成狀態只寫回真正改變的 current／architecture／validation authority。
