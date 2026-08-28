# XBrainLab Now

最後更新：`2026-08-28`

## 目前焦點

目前 pre-plan `main` 基線是 `c9d55495`。PR #68 已完成，不再是 active slice；完成的
Visualization 入口整理不再保留為 dispatch 工作。

下一步是雙線：**Import correctness 為主交付**，**Assistant 3B 效果迭代並行**。本計畫 PR 合併後，兩條
產品 branch 都從當時的 exact `main` 建立；`c9d55495` 只記錄 pre-plan baseline。主 agent 擁有 scope、exact
SHA、PR／CI、獨立 review 與手測交付；worker 不自行 merge 或宣稱 merge-ready。

## Active lane A：Import correctness v2（主交付）

- 舊候選 `fix/windows-import-correctness-v1` 的 `5493bca9` 僅是歷史證據，不能整支同步或作 performance
  claim。fresh `fix/windows-import-correctness-v2` 只移植 `e75eab61`、`b17a5675`、`cc565e06`、`919a2b7f` 的
  correctness cleanup；明確不移植 rejected parallel experiment `d9fa1c8a` 或舊 checkpoint `5493bca9`。
- scope 納入 6 個 Windows parsed-cache expectations 的校準：跨平台一律驗 semantic result、change invalidation、
  parse reuse與 no stale reuse；只有明確模擬 reliable change-time 時才驗 exact reopen／read count；Windows
  conservative full-read 則驗完整重讀與同尺寸中段替換。目標是 Windows 17-case module 全數通過，不是保留
  6 failure 作 follow-up。
- 保留 regular-file check、actual byte count、final full SHA-256、Review→Apply digest、
  `SourceFileBoundary`、scope 與 rollback；不以速度交換 correctness／安全 invariant，也不作 performance claim。
- validation：移植 commits 的 focused Import tests、17-case Windows parsed-cache module、canonical
  source-diverse dataset gate，以及同一 exact SHA 的 file／folder／BIDS Review→Apply 手測。reviewer 確認
  invariant、source scope、recipe／digest與 rollback；candidate-only failure、invariant 放寬或非預期 platform
  semantic 差異即 root-cause checkpoint，不擴大修理。

## Active lane B：Assistant 3B effect iteration v3（並行）

- 舊候選 `fix/assistant-effect-iteration-v2` 的 `85249548` 僅保留失敗／觀察證據。fresh
  `fix/assistant-effect-iteration-v3` 從本計畫 PR 合併後的 exact main 建立；Import 先 merge，Assistant 在交
  PR 前同步已合併的 Import main。
- 只移植 `22bf84e8` 與 `c3c35401` 的最終 product/test delta；不移植 `ea3b407d`、`17fdb557`、`3597ea66`、
  `beb22367` 或任何 merge commit。不得換模型、新增 semantic router、變更 public tool contract、弱化 evaluator
  或降低 assertion。
- evaluator harness：`NO_TOOL` 必走 `_begin_typed_tool_input`，`VALID` 的 exact proposal 必走
  `_begin_model_selected_tool_input`；receipt 不可由 fixture 代填。canonical strict gate 保持
  `36/36 + 10/10 + 5/5 + 24/24 + 7/7`，不得只報選擇性分數。
- 最多兩次 failure-driven iteration：第一輪處理 receipt-local context；若只剩 generic bare bandpass origin，
  第二輪只作 bounded proof：model-selected same-tool、unique exact alias，且無 negation／question／multi／history。
  兩輪後未過 strict gate 即 root-cause checkpoint，列出 failures、能力邊界與需要的新決策；不得偽裝成可手測
  candidate。
- 既有一般 Assistant bubble UI 核准保留；本 lane 不做其他 UI。strict gate 全過後才進 safe E2E、PR與手測。

## 協作、收尾與 handoff

- 主 agent 維持本 plan、建立 branches、核對 exact base／head、整合 PR／CI、安排手測與 merge。Import worker 與
  Assistant worker 各只處理自己的 lane；**independent reviewer slot** 另設，不由兩位 worker 互審，檢查 scope、
  invariants、claims與 evidence。
- Import 先完成 independent review → PR／同一 exact head 的 non-skipped CI → canonical dataset gate與 exact-SHA
  手測 → 明確 merge 同意；之後才處理 Assistant 的同步／交付。任何 source 改動都使既有手測失效。
- 不碰使用者 root `settings.json`。PR merged 或 abandoned 後保留必要 evidence，再清理對應 branch／worktree；只留
  `main` 作下一輪產品基線。兩條 lane 都不可因時程略過 reviewer、exact-head CI或手測規則。
