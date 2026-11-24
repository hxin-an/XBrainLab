# XBrainLab Now

最後更新：`2026-11-23`

## 目前待手測：BIDS 座標更新與 Windows 訓練輸出

從已手測的 `fd8c719d` 修復兩個重現案例。BIDS 掃描後快速增加 recording 專屬座標時，索引曾沿用舊座標；Windows 的 214 字元輸出目錄曾在建立訓練子目錄時失敗。

本輪已完成回歸測試、修復及獨立覆核。BIDS 會重建失效的自動索引，掃描中變動或不完整時拒絕套用座標。Windows 訓練及結果回讀保留使用者選取的路徑與原有檔案身分檢查。下一步是使用同一候選版本實測匯入、montage、長目錄訓練與 Evaluation；正式 PR 與合併待確認。

## 本候選既有修復：訓練中 Assistant Stop 與可行切分誤拒絕

### 基線、證據與授權

PR #165 已由使用者手測通過並同意合併，產品 main 為
`25f15e69dd5ff13bab89fbd18f26abcd63fec1bb`。其 push CI 42264854093、docs
42264854007 已完成成功；先前 Import／Subject／逐人切分的 pending acceptance 已結束。

使用者要求完整功能／平台審查後，於本次明確授權「那你進行修正」。只修審查已確認的
兩項行為；沿用 XBrainLab-main 工作區建立 `fix/training-stop-split-feasibility`，不另建
環境，不碰研究 checkout、使用者 settings.json、文件網站工作區、既有 EEG／實驗資料。
完整審查 evidence 在本機 ignored `build/dev-artifacts/main-verification-20261107/`。

- 真 CPU 訓練、真 Assistant controller/UI：同一 run 正常進度更新 generation，模型
  回傳合法 stop_training 仍被 stale_publication 阻擋，確認卡沒有出現。
- 獨立窮舉 264 組小型資料找到兩個合法分配被拒反例；正式 parser 與 split audit 都接受
  oracle 分配。六／七個不可拆 groups 只留一個 train group；貪婪 Test 選走唯一含全部
  類別的 group，剩餘資料合在一起仍含全部類別，但再分 Validation 就不可行。

### Outcome、scope 與 non-goals

1. Stop 在 prompt 時指向的原 training run 仍活躍、當前 capability 有效時，僅正常進度
   更新不能擋住確認與停止。完成／替換 run、沒有可信 prompt run identity、其他動作的
   stale publication 仍 fail closed。模型不提供／修改 run identity，不新增 UI 或 confirmation。
2. 已確認可行的 high-holdout 分配能完成，維持 exact Number／既定 Ratio rounding、
   每人 scope、全部 train classes、原子重疊 groups、seed、取消與失敗 rollback。不靠
   偷改比例、不重採樣、不把相異 subject 類別集合政策混入本修復。
3. UI layout／copy／選項不變。使用者授權修正上述實際行為；錯誤文案與公共工具契約
   不擴張，macOS／安裝環境缺口另列，不把本輪變成平台重寫或實驗重新跑分。

### Ownership 與複雜度預審

Stop 沿用 ContextAssembler 的 prompt publication、ToolAttemptCoordinator 的 admission、
既有 confirmation 與 backend expected_run；新增資料若必要，只在既有 DTO 保存已有的
TrainingRunIdentity，不新增 owner／receipt 類型／state machine／意圖推測。
切分沿用 DatasetGenerator 與 SplitAudit。優先改既有 class-feasibility 選擇，刪除失效
重試若有可靠替代；不加入 solver 依賴、通用搜尋框架或新的 authoritative policy。
若方案需新 module/class、production 淨增 >300 或超過8個 product files，先更新實際
complexity review，不能以大量補丁掩蓋責任問題。

### 步驟與驗證

1. 將真實 Stop probe 與兩個 oracle witnesses 納入正式測試；在未改產品時觀察目標失敗。
2. 分別修復已有 owner；Stop 覆蓋同 run 進度、生成期間完成／替換、缺 identity、其他
   action stale；切分覆蓋 Number／Ratio、類別不平均、seed、取消、不可行 rollback。
3. focused regression、lint／format／typing；獨立 reviewer 查 stale安全、資料語意與
   複雜度，主 agent 檢視實際 diff／red-green 證據。
4. Windows 原生重跑受影響的 Assistant／切分→真訓練流程，補必要相鄰測試。
   同新 head 的 CI／source-diverse／平台 gates 才能支撐正式交付，不沿用25f15e69綠燈。
   正式 PR 如尚缺授權，先完成可審查的修復與本機驗證，再依 repo 規則取得確認。

### Current / next / stop

正式回歸已先 RED：Stop 同 run 進度案例失敗，切分十二個已驗證可行 witnesses 均被舊版拒絕。
修復於既有 owners 完成，無新 owner／module／class；Stop prompt 綁定原 run，paired
allocation 最多256次單群組交換，並以必要 class-capacity 界線避免已證明不可行的重複搜尋。
獨立覆核（含追加容量 guard）無 blocking finding。Windows：Assistant406、split相關368、
原生完整操作鏈及相鄰安全邊界40項全通過；獨立264例窮舉對照由兩個誤拒絕降至零，
216成功／48正確拒絕。Ruff／format及整體typing通過，不放寬baseline。
100個single-class groups的不可行設定，未加容量判斷時15.57秒，修後1.75秒；同次對照
原路徑1.76秒。此為單次Windows工程量測，不外推所有不可能配置；其餘bounded-search限制仍在。
保留測試fixture／Windows啟動器修正前的失敗紀錄；產品未以workaround繞過檢查。
下一步：提交可審查修復，取得本次PR授權並跑同head適用CI／data／平台gates；尚不稱正式
handoff-ready。不自動合併，也不把舊main的綠燈冒稱本修復驗證。
Stop 為兩項授權修復完成、直接驗證與獨立覆核通過；正式 handoff 仍需同 head 適用 gates。
CI pending／單一小切片完成／context compaction 不是停工條件。使用者尚未批准本修復 merge，
不得自動合併。必要外部資源／新的公共行為決策缺少時明示，不把缺測說成通過。
