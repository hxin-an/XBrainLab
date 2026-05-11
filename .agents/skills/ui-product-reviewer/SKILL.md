---
name: ui-product-reviewer
description: Use when reviewing or steering XBrainLab UI/UX work for desktop product quality, user-facing workflow clarity, visual polish, status/error language, screenshot evidence, and avoiding developer/debug-oriented panels.
---

# ui-product-reviewer

## 用途

用於檢查 XBrainLab UI 是否像可交付的 EEG 桌面產品，而不是 debug 面板或工程工具殼。

## 設計來源

已消化參考：

- Nielsen Norman usability heuristics：visibility of system status、match with real world、
  user control、error prevention、recognition over recall。
- Microsoft Windows design guidance：command surfaces、content hierarchy、spacing、lists/grids、
  避免 redundant wording，錯誤訊息要能幫使用者採取行動。
- XBrainLab 人工審核經驗：ChatPanel 曾無回覆、raw tool output 外洩、status 重複、bubble
  遮字、window geometry 失控，這些 automated PASS 不能自動發現。

## 先讀

1. `docs/current.md`
2. `docs/architecture/ui.md`
3. `docs/target/requirements.md`
4. `docs/target/data_interpretation_system.md`
5. 最新 UI screenshots / walkthrough artifacts

## Review Gate

檢查：

- 第一眼是否像使用者工具，而不是 developer console。
- 主要畫面是否直接支援 EEG workflow，而不是用說明文字代替功能。
- 同一狀態是否重複出現在多個位置，造成干擾。
- 使用者是否看得到目前可做什麼、下一步是什麼、為什麼被擋。
- 錯誤訊息是否用人話說明問題與修復方向，不顯示 traceback / snake_case / raw schema。
- button、menu、status bar、dialog、dock title 是否各司其職。
- 空狀態、loading、busy、failed、blocked、done 是否都有可見且一致的表達。
- text 是否在 narrow / docked / multi-monitor / high DPI 情境下不遮字、不溢出。
- screenshots 是否覆蓋初次啟動、資料匯入、ChatPanel、blocked state、reset/new session。

## XBrainLab 特別注意

- ChatPanel 不應顯示 `Conversation`、tool names、backend command names 或 developer mode
  controls 作為第一層 UI。
- 主 UI 已有底部 status bar 時，ChatPanel 不應再塞第二條重複 status footer。
- Data Interpretation wizard 要讓使用者確認 label/event/metadata，不只顯示 imported。
- UI artifact 必須是人能看懂的 product evidence，不只是 pixel baseline。
- Windows/WSLg geometry 問題不能只靠 Linux offscreen test 宣稱完成。

## 打回條件

- UI 明顯像 debug panel，卻標記 product complete。
- transcript 顯示 raw tool syntax、schema error、empty list、traceback。
- 重要操作沒有 visible feedback 或 disabled reason。
- 新增不存在的 mode / menu option 佔據使用者注意力。
- 只用 screenshot size / baseline match 宣稱 UX 完成。

## 輸出格式

```md
## UI Product Verdict

- verdict: polished / acceptable with UX debt / not product-ready

## Findings

- screen/artifact - issue

## Required Screenshots Or Walkthrough

## Suggested UI Direction
```
