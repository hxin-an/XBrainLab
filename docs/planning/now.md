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

修復前已完成獨立資料語意／生命週期審查與主 agent 重現；
168 focused unit passed、canonical fixture IO 30 passed／8 缺資料 skipped。
原 junction IO 的 2 failures 保留：一個是測試字串假設，一個確認 Command alias choices 遺失。
D 槽 15 roots／261 recordings 完成清單與事件表結構檢查，每 root 一個 recording
實際匯入＋fresh recipe 共 15 passed；不等同全 cohort。

Windows native wizard／Assistant cancel 共 11 passed（13 個非本輪案例 deselected）。
兩位獨立 reviewer 已覆核報告，主 agent 已核對實際 artifacts 與 diff。
審查報告：[BIDS 深度檢查](../validation/bids-import-audit-20261020.md)，含六類確認發現、
測試品質缺口及修正邊界；不是產品已修好或 handoff-ready。

現有可用資源的審查已完成，現進入已批准修復。Windows 上次確認未掛載 E 槽，canonical134／expanded1205 仍因
資料不可得而 blocked；已詢問使用者接回或提供新位置，不推定資料已刪除，不用舊結果補通過。
正式 red 證據已建立：recipe/review 10 failed、cancel 3 failed、JSON/alias 6 failed、
inheritance/input-binding 13 failed（各自含正向 controls）。失敗 artifacts 保留在 build/bids-audit。
正在實作並逐組 green；原生測試串行輪用 shared Windows Python。
取消測試另重現 Preview 取消後可能直接 apply 舊候選，已納入同一取消邊界修復。
共用 inherited events 需逐 recording 保留 review／placement evidence，不能讓後者覆蓋前者，
也不能重複過濾同一份來源 rows；沿用 plan DTO 與既有 atomic apply。

本輪已觸及 >8 個 production files，觸發 complexity review；目前不增加 authoritative owner、
production module／class 或 receipt。獨立 reviewer 正覆核 index／跨層接線及必要性。
下一步：完成 green 與獨立審查，整合後才跑同 source D261／CI。E 槽再查仍未掛載，
不阻止其他已授權施工，不宣稱已通過 canonical134。
