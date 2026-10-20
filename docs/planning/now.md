# XBrainLab Now

最後更新：`2026-10-20`

## Active — BIDS 審查缺陷整合修復

### 授權、基線與 outcome

使用者已於 2026-10-20 批准六類缺陷修復計畫，做到整合驗證、獨立覆核後集中手測。
2026-10-20 fetch origin/main 後建立
`audit/bids-import`，基線 `52d3a615`（已合併 PR #163）。舊 Training／Preprocess 施工紀錄
留在 Git；不重新啟動已合併工作。研究 checkout 與文件預覽 worktree 均保持原狀。

既有 134 個資料入口／1,205 recordings 證據屬歷史 source，不能算本版本通過。
Outcome：六類已確認缺陷修復，有直接回歸證據；Preview／Validate／Apply／recipe 語意一致，
metadata 與使用者選項不靜默遺失，取消／失敗／重試保留既有資料與 freshness 保護。
不承諾任何 BIDS 零缺陷，也不把沒有例外等同資料語意正確。

### Scope / non-goals

- 主流程：選 root → subject selection → 五步 wizard → Confirm and Import →
  Dataset／Preprocess 就緒；延伸到 recipe fresh-service 重播與必要 epoch 語意檢查。
- 六面向：發現與範圍、metadata／伴隨檔繼承配對、events／labels、
  時間／波形保真、確認／取消／失敗恢復、recipe／GUI／Assistant／Command 一致性。
- 同時審查相關 production、tests／fixtures、scripts、設定與文件；核對 oracle、mock、
  漏選／多載、stale review、半套 publication、重複掃描／資料複製與等待。
- 修復 inherited events/channels TSV 配對、JSON 欄位覆寫、BIDS/generic review 一致性、
  sample-index recipe、Preview 已發布後取消 Validate 的 retry、Command alias choices。
  補齊實際 metadata 輸入身分與 Assistant 成功開窗匯入測試。
- 已批准補齊上述通用 BIDS 繼承，不按資料集名稱加特例；以 BIDS 1.11.1 為界，
  保留既有五步 wizard，歧義透過現有 validation surface 明確拒絕，不新增流程／確認頁。
- 不改原始 EEG、研究封存、模型／RAG、使用者 settings.json；不下載新資料、
  自動接受授權、搬移／刪除資料或新建環境。不跑全部訓練。單一主題 PR、小 commit；
  merge 必須待手測與另外批准。超出既有複雜度門檻先 review，不暗中擴張 scope。

### 執行與分工

1. 保留審查探針及原失敗，以正式測試先重現，再修正。基線仍為 52d3a615。
2. 主 agent 負責 index 繼承、腳本與整合；分工 recipe/review、UI cancellation、
   JSON suggestions/alias choices，各自專屬寫入檔案。獨立覆核由非實作者進行。
3. 依序整合 sidecar、review/apply、recipe、cancel、JSON、alias；必要相依界面先協調。
   使用非零波形與獨立事件／通道預期值，避免 product 自己產生 oracle。
4. 補來源變動／新增 sidecar freshness、participants input binding，維持現有 owners，
   不新增 state machine、receipt 或 compatibility 層；移除重複／錯誤政策取代旁掛補丁。
5. focused／IO／epoch 相鄰檢查後，D 槽 261 recordings 逐份匯入＋fresh recipe，
   E 可用時補 canonical134／expanded1205，缺資料不算通過。重型 native 串行、明確 timeout。
6. 同一版本 Windows native wizard／Assistant 完整成功與取消流程、必要 CI／source-diverse，
   獨立資料與 lifecycle/test 覆核，主 agent 核對實際 diff／artifacts。
7. 同步 current/target/support/validation 的實際事實；直接開 Windows app 與 PowerShell log
   交一次集中手測。既有使用者程式不得未確認關閉。

### 責任與複雜度檢查

Owners before/after 維持 BidsDatasetIndex（發現／配對）、既有 candidate/review/apply、
recipe serializer、UI coordinator、ApplicationService publication。DTO／純 helper 不另成 owner。
刪除候選為同層專用配對的限制、first-nonempty Levels fallback、重複時間驗證與
忽略最新 review state 的 closures；保留 freshness、root containment、atomic apply 及明確確認。
每切片回報實際 production +/-，有 >300 net／>8 product files／新 module 等觸發時先獨立
complexity review；整合不以行數少取代語意完整。每小 commit 可獨立回退。

### 驗證與停止條件

使用現有 Windows shared Python；Qt／MNE／native 測試採 prlimit --core=0 與明確 timeout。
不並行多個重型 native suite。重用既有 gates，不建新驗證平台。

完成：六類缺陷都有 regression，相關資料／狀態邊界經實際流程與獨立覆核，
無未分類失敗，同 exact commit 必要 gates 通過才稱 handoff-ready。
若必要資料／資源不可得，完成其他檢查後精確列 blocker；不得拿舊134/134補成本次通過。
UI 狀態：已批准修正既有 validation／取消重試行為；layout／五步流程維持。

### Current / next

六類修復與直接相依邊界已完成施工，進入固定 source 的整合驗證。
[修復前審查](../validation/bids-import-audit-20261020.md) 與原 red artifacts 保留，
不把歷史發現改寫為修復後證據。`build/bids-audit` 保存本輪測試輸出；PR 記錄 exact head、
適用 CI／native／retained-campaign 結果，恢復工作時先核對實際結果，不依計畫推定通過。

Focused 證據：最終資料／recipe／header suite 299 passed；JSON/alias 109 passed；
conformance script 24 passed；shared BIDS widget 14 passed；取消四分支 real-Command
red/green 與既有 async suite 81 passed。這些組有重疊，不能相加作唯一測試數。
原 junction 的路徑字串假設已改為 exact resolved file identities；仍需重跑原 junction IO。

獨立覆核已涵蓋資料、取消／publication、測試 oracle、腳本、文件與複雜度。
並修正審查再現的直接缺口：catalog 不被未選 subject 的 sidecar 歧義擋住；
共用 events 逐 recording 保留證據／原始 rows；selected sample anchor 與 onset 不一致時
重用既有 converter／duration parser，使 Validate 與 Apply 一致。既有 header admission
傳遞 first_samp，非零 origin、異取樣率、end field、unknown duration 有直接測試。
Negative absolute sample coordinates 維持拒絕；不宣稱新增任意座標或 BIDS format 能力。
腳本補綁 participants 與 generic inherited metadata，未列入 inputs 時在 admission 拒絕。

Production 相對 52d3a615：16 files、net +335，已觸發並完成獨立 complexity
review。Owners、production modules/classes 與 receipts 均不增加；換算函式由 Apply 移至既有
loader 共用，不保留第二套；既有 duration parser 只改為可共用入口。額外檔案是同一資料流的
admission／recipe／render 接線，不另建平台。主 agent 已核對實際 diff。

剩餘交付步驟：固定 clean head → 最終 Windows native／junction IO、D261、CI/source-diverse；
對實際失敗修復後驗受影響邊界。原生檢查中不執行會 stash 工作樹的 commit hooks。
E 槽於 2026-10-20 再查未掛載，G 槽也不是既有資料根目錄；canonical134／expanded1205
仍因必要資料不可得而 blocked。已詢問接回或提供新位置，不重新下載、不拿 D261 或舊134
冒充通過。完成其他檢查後若此 blocker 仍存在，明確交代未達 handoff-ready 與所需資源；
待同版本必要 gate 齊備才開 Windows app 交集中手測，未經另外批准不 merge。

首輪 CI f0330d07 發現四項型別診斷（index helper 接收 list／tuple 宣告、selected timing
nullable narrowing）。逐筆 campaign 已停止，保留不完整證據；不改 baseline 或弱化 gate。
修正 helper 的 iterable 契約並明確拒絕 unavailable timing；獨立覆核無阻擋，
locked Basedpyright 1.39.2 回到零診斷、直接回歸 87 passed。以新 head 重啟必要檢查。
完整 CI 同時抓到兩項舊測試契約需同步（JSON field replacement、mock 缺 run identity）；
已保留 admission／讀取次數等原 assertions 並補明確預期，39 個 focused tests 通過。
另有實際相鄰回歸：recipe 指向已搬走的 label carrier 時，新的 alias 拒絕會讓 reload 提前
失敗，無法進入既有明確 remap 流程。已恢復「有缺檔 blocker 的可修復 review」，保留對任意
未知 choice 的拒絕、不讀取不存在檔案、不允許未完成 remap 的 Apply。108 項相關測試通過，
含明確 remap 後實際 Apply 的 sample 檢查；獨立覆核無阻擋，最終 Basedpyright 零診斷。
下一步提交此修正並重啟同 head CI、Windows native／junction IO 與完整 D261 campaign。
