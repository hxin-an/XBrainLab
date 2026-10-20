# XBrainLab Now

最後更新：`2026-10-20`

## Active — BIDS 審查缺陷整合修復

### 授權、基線與 outcome

使用者已於 2026-10-20 批准六類缺陷修復計畫，做到整合驗證、獨立覆核後集中手測。
同日再次複查後，使用者追加批准修復 events JSON entity-subset 繼承漏讀／freshness 漏檢，
以及同層多個適用 events JSON 的歧義拒絕，併入同一 PR，維持 UI 與既有 owners。
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

修復前審查與所有 red／中斷 artifacts 保留在原位置，不把歷史發現改寫為修復後證據。
PR #164 的前一候選為 `a9357fea`：24 個適用 CI checks 成功，Windows native 13 passed，
junction IO 43 passed；E 接回後，以 pinned bytes 組成隔離 fixture，原先缺檔八項也全部通過。
D261、E canonical134 均全數通過，receipt／recipe／輸入雜湊及 source 已核對。
這些是前一候選的證據，不能直接證明接下來的修正版。

E 槽已恢復；實際 134 根目錄／1,205 recordings 與歷史清單完全一致。完整逐筆重播尚未跑。
封存 case expectations 位於
`E:/XBrainLabData/evidence/retained-import-20260916/source-3a2c65aa/`；
已審查的 ignored adapter `build/bids-audit/run_frozen_retained.py` 只重用 frozen cases，
驗證 archive／inventory／case hashes，串行呼叫現有 `run_import_case`，不重新產生答案。
歷史逐筆時間加總約 2h05m；需固定 final source 後再跑，不能邊施工邊跑。

### 追加切片：events JSON 繼承與 freshness

問題／證據：`json-inheritance-command-probe.json` 已用實際 Commands 重現：
subject+task JSON 被 run-specific carrier 漏讀；task-only JSON 被 acq/run carrier 漏讀。
建議名稱錯誤，漏讀檔案修改後 Apply 仍可 publication；已辨識檔案的 mutation control 正確拒絕。
同層 `events.json` 與 `task-*_events.json` 同時適用時，Validate 未拒絕歧義。
皆屬既有 discovery 缺口，不是前一修復造成；明確 class choices 未被覆寫，未觀察到波形損毀。
追加覆核的 timing regression 也重現：真實 detached prepare 完成後新增適用 JSON，
最終 publication 只檢查已知檔案，未重查 retained index，仍發布資料。
`json-prepare-freshness-red.xml` 保留失敗；修復直接重用既有 index freshness owner，
在最終 commit 邊界再次確認目錄身分，不新增掃描／receipt。

Outcome：依 BIDS 1.11.1 entity-subset／祖先目錄規則，所有適用 events JSON 都納入既有
admission、欄位覆寫、recipe/content identity 與 apply freshness；同層歧義拒絕。
不跨 root、不讀未選 subject／不相符 task/acquisition 的 JSON；取消／atomic publication 保持。
不新增 layout、步驟、owner、receipt、cache 或資料集特例；不擴張為完整 BIDS validator。

步驟：
1. 先將四個實際 probe 收成直接回歸：subject/task/acq/run 繼承、mutation 拒絕、
   同層歧義，以及 unrelated／unselected scope 不受影響。原 red 保留。
2. 重用既有 filename entities、bounded index 與 resource guard；移除少數檔名拼接清單，
   統一適用檔案配對／局部優先順序，不新增第二套 admission 或 freshness。
3. 檢查所有呼叫者與 resource 限額／symlink／root 替換保護；實作者以外 reviewer 覆核
   實際 diff、資料邊界及測試 oracle，主 agent 驗收。
4. focused tests、typing／architecture／lint 後固定 clean head。跑適用 CI、Windows native、
   D261、canonical134 及 frozen expanded1205；保留歷次失敗，不改 baseline／門檻。
5. 同版本 gates 齊備後開 Windows app 與 PowerShell log 交集中手測，不擅自 merge。

假設／UI：使用者已批准同層歧義透過既有錯誤／validation surface 拒絕；UI layout 不改。
Complexity：前一整合 production 16 files、+551/-216（net +335），已獨立覆核；
追加切片仍依實際差異檢查門檻，優先刪除 `_bids_event_sidecar_names` 的不完整政策。
停止條件：新增 regression 全通過、資料／資源安全獨立覆核通過，必要同版本 gates 完成；
若發現需新契約決策的問題，列具體證據，不暗中放寬規則。

追加切片施工驗證：84 項 JSON／index／Command tests 與 55 項相鄰 two-phase apply
保護通過；獨立 reviewer 已檢查實際 diff、red/green artifacts、scope／root containment、
兩個 publication timing seams 與單獨 reader 的已核准 JSON 消失情況，無剩餘阻擋項。
這是施工 evidence，不是 final-head conformance。下一步固定 clean commit，依序補
native／完整 fixture、D261、canonical134 與 frozen expanded1205，並核對同 head CI；
執行狀態保存在該候選的 ignored output，不以先前候選結果替代。

`b931e514` 的 CI backend shard（run 39438413109）有一個舊 row-truncation fixture
失敗，其兩種排列放在同層、檔名無可區分 entity，形成真正 JSON 歧義；另 3,842 項通過。
本切片只隔離該測試的兩種資料排列，保留 row budget／推薦拒絕斷言，不放寬產品規則。
D replay 已於 53/261 通過時停止自有程序，原輸出保留；新候選重新跑完整 gates。
Focused validation：該 label-carriers test file 全部案例及既有 JSON regression；
獨立 reviewer 確認 fixture 修正未遮蔽產品 defect，通過後重新凍結。
