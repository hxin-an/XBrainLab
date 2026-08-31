# XBrainLab Now

最後更新：`2026-08-31`

## Current baseline and release status

`main` 與 `origin/main` 目前同為
`9cf2637bc1f8c8f180e463ca1bbda141e2f680de`。Repo-root `settings.json` 的本機修改仍由使用者擁有，
不得提交、覆寫或隱藏。

原 `v0.9.0` candidate PR #91（head
`cacf0b86b4353b9d3023af98bbd9cc46aec28d7a`）雖然 CI 完成，但使用者在真人操作發現 Saliency
Spectrogram 排版會重疊，因此已明確否決並關閉；該 head 不得 merge 或 tag。修復進入 `main` 並完成完整
驗證前，不建立新的 release candidate。

## Active slice — Saliency Spectrogram responsive layout

### Problem and evidence

四類別 Spectrogram 初始 `640×480` 可正常顯示，但存在三個可重現觸發：

1. 切換到其他 workflow panel 再回到 Visualization；
2. 開啟 Assistant，使 Visualization controls 換行並縮小 tab 的可用高度／寬度；
3. 重新計算 Saliency，替換目前 Matplotlib figure／canvas。

可見結果是 class title、axis labels、plot 與 colorbar 疊在一起。唯讀重現已排除重複 canvas：舊 canvas
會被移除、隱藏與 detach。實際幾何證據為：

- 四類別 Spectrogram 在 `500×300` 時上下兩列 data-axis tight bounds 相交；
- `500×480` 時既有 shared colorbar 與右欄兩個 data axes 相交；
- 共用 `fit_figure_subplots_to_canvas` 從目前已調整的 margins 繼續修改，compact → normal 後不會恢復
  visualizer authored margins。

Saliency Map 已有可重用的 product pattern：scrollable canvas、row-based minimum height 與 GridSpec 專用
colorbar 欄。使用者已於 `2026-08-31` 明確批准 Spectrogram 在受限高度下沿用其垂直捲動行為；正常尺寸
外觀維持不變。

### Outcome

- 正常尺寸維持目前多欄 Spectrogram hierarchy、文案、色彩與互動。
- 高度不足時保留至少 `max(420, rows * 240)` 的 canvas，使用既有垂直 scrollbar，不壓縮到 artist overlap。
- colorbar 使用自己的 GridSpec column；在約 500px 寬的 compact canvas 不碰右欄 data axes。
- 每次 resize 從該 figure 的 authored subplot margins 重新 fitting；normal → compact → normal 不累積變形。
- panel hide/show、Assistant-like resize 與 recompute figure replacement 後仍只有一個 live canvas，且版面可讀。

### Scope, ownership, and non-goals

- 重用既有 `SaliencySpectrogramMapViz` figure layout、`BaseSaliencyView` canvas lifecycle、
  `_xbrainlab_min_canvas_height` 與 Saliency Map scroll pattern；不建立新 owner、module、public class、state
  machine、receipt 或 layout framework。
- 預計最多 3 個既有 production files，owner delta `0`，production net LOC `<100`。超出即停止並先做
  complexity review。
- 不修改 Saliency 計算、STFT/cache、class identity、ApplicationService、Assistant prompt/tool contract、
  model、其他 workflow UI、可見文案、字體縮放或自動單欄重排。
- resize 只重新 layout／draw 現有 figure，不得觸發新的 backend Saliency 計算。

## Roles and progression

- **Root coordinator**：唯一管理 plan、branch/worktree、scope／LOC、視覺 artifact、canonical gates、PR、
  manual acceptance 與 release progression；不以作者自評代替 reviewer。
- **Implementer**：先建立 observable red tests，再做最小 coherent repair；不擴張到其他 Saliency redesign。
- **Independent reviewer**：在 freeze exact SHA 後審查 overlap geometry、canvas lifecycle、sibling regression、
  test quality 與 scope；不在受審 branch 直接補功能。

完成順序：red reproduction → 最小修復 → same tests green → adjacent Saliency tests → exact-source screenshots／
walkthrough → reviewer → canonical handoff gates → PR CI → 使用者 exact-SHA 手測與 merge 批准。任何 source
改動會使舊手測失效。

## Focused validation and handoff

1. Backend 四類別 Spectrogram 證明 minimum height 至少 480px，且 dedicated colorbar column 與 data axes
   在 compact width 不相交。
2. Qt lifecycle regression 覆蓋 `640×480`、`500×480`、`500×300`、normal → compact → normal、hide/show、
   Assistant-like geometry 與 figure replacement；檢查 scrollbar、authored margin recovery、single live canvas、
   plot／label／colorbar non-overlap，以及 resize 不增加 render generation。
3. 重跑直接相鄰 Spectrogram、BaseSaliencyView、Map、Topographic Map 與 Visualization panel tests。
4. 產生 normal／compact exact-source screenshots，由 root 肉眼檢查 hierarchy、clipping、overlap、scroll 與
   normal-size regression；offscreen 不取代 WSLg／Windows 真人驗收。
5. 依 `scripts/dev/handoff_gate_spec.py` 跑 applicable Visualization walkthrough、default UI baseline、
   source-diverse dataset與 static quality gates。只有同一 clean/explained pushed SHA 的 non-skipped CI 全部
   `completed/success`，才交給使用者手測。

手測必須重現四個路徑：初次開啟 Spectrogram、切走再返回、開關 Assistant、重新計算 Saliency；正常與受限
尺寸都不得再出現標籤／圖／colorbar 疊圖。通過並取得明確 merge 同意後才合併。

## Release stop condition

本 PR 合併後先移除 task worktree與已辨識的 XBrainLab 暫存，確認唯一產品基線為最新 `main`，再執行完整
canonical handoff manifest。全部通過後才從 fixed `main` 建立全新 `v0.9.0` release branch／PR；不重用
PR #91 的 candidate identity。

新的 exact release candidate 還必須完成 Windows Python 3.12 native source launch、核心 workflow、此次
Spectrogram 四路徑、3D、Granite 3B bounded Assistant與中文輸入真人驗收。PR CI、Windows手測與 merge
批准全部對應同一 source後，才 merge並建立 annotated `v0.9.0` tag／GitHub source release。
