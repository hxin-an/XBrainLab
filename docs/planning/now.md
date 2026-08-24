# XBrainLab Now

最後更新：`2026-08-25`

## 目前焦點：Assistant dock 向外擴張主視窗

### 問題與證據

- 一般視窗開啟 Assistant 後，既有 workflow panel 會向內縮；使用者已確認希望保留目前調整良好的預設 panel 大小。
- `AgentManager` 只建立、停靠及顯示固定右側 `QDockWidget`；真正的 presentation owner 是 `MainWindow`。
- `MainWindow._apply_assistant_dock_width()` 目前只在既有 top-level width 內，以 `resizeDocks()` 分配 320–420 px 給 Assistant；中央區 436 px 是最低保護，不是開啟前寬度，因此內縮是現行 policy 的必然結果。
- 現有測試涵蓋 320–420 px dock、中央最低寬度與重複開關，但未要求開啟前後中央區寬度一致，也未防止 top-level width 累積增長。

### Outcome

在螢幕空間足夠的一般視窗中，開啟 Assistant 時主視窗向外擴張，既有 workflow panel 維持開啟前寬度；關閉後恢復原視窗幾何，反覆開關不累積增長。

### Scope／non-goals

- Scope：`MainWindow` 既有 Assistant dock presentation policy、直接可觀察的 Qt tests、必要的 active plan truth。
- 空間足夠時可在同一螢幕內向左平移主視窗，以保留右側 Assistant 所需空間。
- 最大化、全螢幕或螢幕總空間不足時保留目前 responsive fallback：dock 維持 320–420 px，中央區至少 436 px，不把視窗推出可用畫面。
- 關閉程式時若 Assistant 仍開啟，不把暫時擴張後的幾何當成下次啟動基準。
- Non-goals：Assistant 視覺改版、dock 浮動／改側、ChatPanel 或 AgentManager 重構、視窗幾何 owner 重寫、多螢幕 policy 全面改版。

### 假設、owner 與施工步驟

- Before／after owner 都是 `MainWindow`；沿用 `WindowGeometryLifecycle` 的 screen geometry 與 persistence，不新增 state machine、receipt、public class 或 production module。
- Deletion／reuse first：重用既有 dock width policy、available screen geometry 與 bounded placement；若新策略取代舊有「只保護中央最低寬度」假設，同步刪除或改寫衝突測試，不建立第二套 dock sizing policy。

1. 先新增最小 red tests：一般視窗開啟後中央寬度維持、hide 後恢復、重複開關不累積增長。
2. 新增 responsive red test：最大化／空間不足時不擴出 available geometry，仍符合既有 dock 與中央最低寬度。
3. 在 `MainWindow` 既有 visibility／resize policy 內實作最小修正；hidden 時建立／更新本次 normal geometry 基準，visible 時只做一次 bounded outward expansion。
4. 確保 close persistence 使用未擴張的 normal geometry，且使用者於 hidden 狀態手動 resize 可成為下一次基準。
5. 跑相同 focused tests、直接相關 window geometry／walkthrough 回歸，再交付 WSLg 實畫面手測。

### Focused validation

- Assistant dock unit／integration tests：中央寬度維持、420 px 標準寬度、320 px floor、hide restore、repeat toggle、narrow／maximized fallback。
- 直接相關的 window geometry lifecycle 與 product walkthrough tests。
- `ruff check`／format 與 `git diff --check`。
- WSLg 手測：一般視窗初次及重複開關、hide 恢復、最大化 fallback、關閉後重開；確認五個 workflow panel 與 top navigation 沒有 clipping。

### Stop condition 與 UI 確認

- 若 Qt／window manager 無法在不越過 available geometry 的情況保留中央寬度，停止外推並使用既有 responsive fallback，不新增平台專屬 geometry owner。
- Source 改動後必須重新取得使用者的 WSLg 可見行為手測；offscreen 測試不取代真人驗收。
- 使用者已於 2026-08-25 明確批准：合併中文輸入 PR 後，依上述向外擴張／hide 恢復／空間不足 fallback 規格開始此 UI slice。

### 目前狀態

- WSLg 中文輸入 PR #53 已完成 exact-head CI、兩次真人手測並合併為 `064f5fc5ce56cce253b6ebe7fbeee182cefdf92f`。
- Red reproduction 已確認一般視窗開啟 dock 後，中央區從 860 px 縮為 436 px；修正後同一測試維持 860 px。
- `MainWindow` 已在螢幕空間足夠時 bounded outward expansion，hide／close 恢復原 geometry；沒有修改 `AgentManager`／`ChatPanel` 或新增 owner。
- Assistant geometry tests `7/7`、完整 MainWindow sync `99/99`、相關 product walkthrough `3/3`、window geometry `22/22` 通過。
- 隔離本機 QSettings 的 1280×800 UI baseline `7/7` 與 approved references 相符；它只證明 responsive fallback，外推仍需 WSLg 真人畫面驗收。
- 獨立 final diff review blocker `0`；production `+109/-1/net +108 LOC`，僅一個 production file，未觸發 complexity review。
- Exact commit `8fcdfeee7666188b6afac352e702a2bf953bfeeb` 的本機 authoritative
  `linux-unit-ui` gate 全部通過；既有 runtime lifecycle 疑點 test 另以 bounded process
  重跑 `5/5` 通過。
- PR #54 的 Linux Python 3.11 `components` shard 連續兩次在 1200 秒 watchdog
  timeout；兩次停在同一個既有 `test_agent_runtime_lifecycle.py` 區段但不同 case
  boundary。上一個 main baseline 同一 components domain 為 `477 passed`，本 slice
  沒有修改 `XBrainLab/ui/components/` 或其 tests，因此目前沒有 MainWindow regression
  證據，但 remote non-skipped gate 尚未成功，不能交付或合併。
- Blocker／Next：停止盲目 rerun；取得使用者同意後，以獨立 tests-only slice 隔離
  Assistant runtime lifecycle tests 的 Qt process boundary，再把通過的 main baseline
  帶回本 UI branch、重跑 exact-head gate，最後交付 WSLg normal／maximized／repeat-toggle
  手測。
