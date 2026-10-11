# XBrainLab Now

最後更新：`2026-10-11`

## Accepted UI baseline

使用者已接受本輪 Training Settings、Data Splitting 與 Training 狀態列設計，要求接續
完整後端／測試／腳本清理，最後一次整合手測。保留的設計：

- Training Settings：中性灰、清楚標題與緊湊右側間距；Optimizer／Output 的內嵌入口，
  Device 下拉（展開才列舉硬體），獨立 Early stopping 開關。Save／Cancel 與不可用原因保留。
- Data Splitting：860×460 預設與窄版重排、三列等距；Validation Disable 不呈現第二步
  Validation 卡片，overview 不顯示 Atomic trial groups，但分組與切分語意不變。
- Training 狀態列：閒置顯示 Split／Model／Training settings 的後端保存狀態；
  進行中工作、錯誤與暫時訊息优先，不新增工作狀態或輪詢 owner。

設計接受不等於最終手測／merge 批准。前期原生預覽與 focused evidence 保留於 ignored
build；不在此重複每版施工日誌。PR #161 已合併的 Select Model 改善屬 main 基線。

## Active — Training／Preprocess 全範圍深度清理，補齊未審分母

2026-10-11 使用者明確要求「全面深度清理已無遺漏」。`2dc8b567` 的同版工程 gates
通過僅是可執行候選，不能代替完整審查；前次手測交付結論撤回，不 merge。
本段是目前唯一 active acceptance；下方施工紀錄只提供已知 evidence，不當作完成證明。

問題：上輪部分大型共用 production/tests 只讀相關方法或名稱清單，重要失敗路徑仍有
未解釋的 coverage 缺口，不能稱「全部仔細重審」。本輪 outcome 是已定義分母內
沒有未讀／未判斷項目、已確認冗餘物理刪除、已知缺陷與必要證據缺口閉合。
不承諾未來零 bug，不用任意行數／coverage 百分比代替 senior engineering judgment。

### 固定範圍與責任

- Training：split/generation、model selection/config/resource admission、全部 training
  package/manager/contracts、application lifecycle/publication/history、records/artifacts，
  相關 panel/dialog 與直接支援的 tests/fixtures/scripts/config/docs。
- Preprocess：全部 processors、state/application/preparation/render/epoch context、
  channel/montage、Raw/Epochs/data manager/Study、全部 panel/dialog、直接支援的
  tests/fixtures/scripts/config/docs。對 shared ApplicationService 與其測試完整讀取，
  但不因 unrelated Import／Agent finding 擴大整個模組重構。
- 以 Git tracked paths、imports/callers/dynamic registry、Poe/CI/gate/docs 入口交叉建
  明確檔案分母；每檔記責任／入口／依賴／測試品質／去留／閱讀完成狀態。使用既有
  ignored review notes 保存一輪性細目，不新增通用盤點平台或第二份 active plan。
- 先前確實 full-body review 且 hash 未變的可重用，但重讀先前局部／inventory-only
  的全部 body；修改後重審 diff 與影響邊界。不得把 coverage 檔案數當閱讀檔案數。
- Main 擁有 UI、shared service/其共同測試、分母整合與 docs；Training worker 擁有
  核心/application 與專屬 tests；Preprocess worker 擁有資料/transaction 與專屬 tests；
  validation worker 擁有 scripts/CI/config 與專屬 tests。重疊處先報主 agent 分配。

### 施工與退出条件

1. 完整對帳分母及尚未 full-read 的檔案，不先宣稱可手測。逐檔比較保留、刪除、收斂、
   拆分方案；大檔不只用「cohesive」結案，要具體責任與資料流理由。
2. 查 reachable defects、重複 policy／state／adapter、無用途 API／腳本、historical
   compatibility、弱／高 mock／重複 tests。刪除前查真 caller 和契約；public/UI
   contract 決策仍不得偷改。真正缺授權另提，先完成不受阻工作。
3. 優先補先前 coverage 識別的實質失敗組合：rollback failure、worker startup／stale
   cleanup、未完成 futures 取消、preview 邊界與 artifact corruption；逐項給測試或
   合理不可達／範圍外理由，不因「特殊分支」直接略過，不為數字補無意義 assertion。
4. Bug 先 observable red，refactor 先 passing characterization；高風險修改獨立覆核。
   focused 驗證沿既有 runner，不重建環境，不大規模重跑等價已通過 suite。
5. 獨立 completeness reviewer 對帳 Git 分母、read evidence、保留理由、unresolved
   list 和原始 diff/test evidence；作者摘要與綠 CI 不能自己證明無漏審。
6. 只有分母無未查項、scope 內無未解 defect／必要測試缺口、覆核無 blocker，才凍結
   同版本 CI/source-diverse/platform/native，開 Windows 完整程式與 PowerShell log。
   不因 compaction／完成一個子任務／CI pending 停工；不自行 merge。

UI：保留全部已接受 layout／互動，只有此前核准 history 數字括弧移除；本輪不重畫。
Non-goals：論文資料/實驗、模型科學認證、第三方 library 全審、Import／Agent／
Evaluation／Saliency 全模組重做、環境或磁碟清理。這不免除它們與本模組的直接交界。
Current：逐檔閱讀、去留判斷與修正已完成；獨立覆核已對帳 production／tests／scripts
與直接支援邊界，沒有未查 source 或未解 blocker。第三方 vendor 數學與 mixed docs
的範圍外章節另列，不冒充全文認證；`2dc8b567` evidence 僅保留為 baseline。
Next：凍結修正、取得 exact-head CI／source-diverse／原生 Windows evidence，確認後
開啟 Windows 完整程式與 PowerShell log，交付單次整合手測；不自行 merge。

本輪已確認 slice：
- StopTrainingCommand 在 execute 入口走 lock-independent control，serialized handler
  中仍有不可達的第二條 stop handler／專屬 tests。核對 repo 動態／文件 caller 後，
  先 existing public stop characterization，再刪除死註冊／內部方法與專屬測試段；
  保留 public Command、停止確認與真正控制路徑。Main 同時刪 service 遺留未用型別 alias。
- Public cross-source training runner 在 import service 後、try/finally 之前建立 output
  directory；setup OSError 可能漏 close。先真 service／output 故障重現，沿既有 lifetime
  包住 setup，對應 integration fixtures 明確 teardown，不新增 lifecycle owner。
- Preprocess batch 使用 ALL_COMPLETED 後才讀 future.result；exception 中對同批
  finished futures 的 cancel 是無效分支。真 thread characterization 確認 admitted
  batch 會 drain、失敗後不提交下一批且原資料不變後刪除，不改取消契約。
- ResetPreprocess 的 rollback 若也失敗，可能蓋掉最初的 reset／retirement error。
  先 public command＋真 data manager 重現雙故障，再沿既有 error mapping 保留原錯誤、
  明確標示 rollback_failed／state_preserved=False；不新增 recovery owner。
- MOABB UI capture 使用 no-op close 的 retained-service adapter，與真正 close 確認
  相衝突；實際 runner caller 測試先重現，明確區分 caller-owned lifetime，刪除 adapter，
  將 journey setup 納入 caller 的既有 finally。保留獨立 runner 預設自行 close 的契約。
- 完整讀 shared application tests 後，確認 saved-split preservation 與 explicit-empty
  montage payload 各有一個重複案例；先同檔 baseline，再合併較強的 identity／geometry
  assertions、刪重複案例，不減少實際保護的行為。
- Split Preview worker constructor／start 未包住例外，可能留 Running／Calculating
  無結果；先真 Qt dialog＋thread 故障 seam 重現，再沿既有 failed presentation 收斂，
  驗證可重跑及 close，不新增 UI／state。完整 UI 審查另刪無 consumer 的 btn_info 空欄位、
  不可達 train_type=None fallback、失去對象的 DataSplitTitle style 及 montage 重複設定。
- Training 的 saliency resource admission 選 evaluation count 與實際 holder 的完整
  class coverage split 選擇可能不一致：真小型 holder／loader 重現後重用既有 selection
  owner，避免 test 不完整而採較大 validation 時低估 RAM，不改實際 split policy。
  同一實際工作對帳包含 retained holder 的 batch/device/model；後續設定只影響未來 training，
  不能拿目前較小 batch 或 CPU 設定估計仍使用歷史 GPU／較大 batch 的重算。
- Preprocess preview 最後 sample 的浮點時間乘回 sfreq 可能 floor 到前一點；以 100／
  250 Hz 真 MNE endpoint 重現後只修 clamp endpoint，保留一般 window floor 語意。
- DatasetStateService 三個內部便利 adapter（get_filenames、get_data_at_assignments、
  get_epoch_count）在 caller／protocol／動態註冊全查無使用後刪除；保留同名 retired
  controller 的 architecture guard，不刪必要正式 command/query。
- ResourceChecker 無 caller 的 warning-message／available-vram 便利方法與無效 monkeypatch
  在 resource baseline 後刪除；保留有 Assistant／calibration caller 的 OOM helpers。
- Human-like walkthrough 的 Linux after-close gate 可能把仍活著的 Python Thread 當成
  dormant Qt dummy wrapper；先真 waiting thread 重現，再區分既有 Thread 身分，不放寬
  thread caps。另刪已由 source identity 取代、查無 caller 的 _git_worktree_dirty helper。
- TrainingSidebar tests 的 missing-publication 重複案例及只搜尋 binding helper 名稱的
  弱 source assertion，已有同檔真 callback/request/generation 行為測試；baseline 後刪除。
  真 preview worker 測試補 finally release／close，避免 assertion failure 留住執行緒。
- UI 專屬 tests：51-fold 完整顯示案例由同範圍更強的 visible async regression 保護後
  刪重複；刪未接入產品路徑的 controller fixture。Training Settings checkpoint label
  可見性 assertion 改為一致座標空間，不能以錯誤 parent geometry 宣稱沒有裁切。
- 專屬 deferred-split／split-boundary tests 補 local fixture finalizer，確保每個建立的
  ApplicationService 都結束；不新增全域隱藏 tracker。TrainingPlan 重複 get_eval_loader
  子集由完整 get_eval_pair matrix 保護後刪除，刪無用 fixture 值。Reviewer capture 的
  兩個相同完整預處理截圖 setup 合併，保留原有所有 assertion。
- 獨立 maintainability review 確認 shared 12K application tests 的 Preprocess command
  admission／prepare／channel／epoch transaction 分散在相隔約 3,500 行的段落；抽出為
  有明確名稱的專屬測試，保留原 test bodies／參數／案例數並核對 AST 等價。只搬必要
  fixture，不 import 另一個 test module。Training close/sync 與共用 admission 高耦合，
  本輪不為縮短數字拆散。Product owners 不變。
- TrainingPlan constructor 只建立全新 TrainRecord（eval_record=None，exclusive 新目录），
  不載入舊結果；_validate_loaded_saliency_artifacts 的唯一 constructor call 因而無作用。
  主 agent 獨立核對實際初始化與 caller 後刪 call＋method，保留真正 load/consumer 的
  saliency context／producer integrity checks；不把無效 guard 當安全保護保留。
- 完整 UI sidebar body 查到 admission 已 return 後的重複 None 分支、無額外語意的
  risk-level adapter 及失去 caller 的重新查 capability 路徑；沿既有 publication owner
  刪冗餘，保留相同 warning、generation 與 async 行為，以 sidebar 真行為測試驗證。
- State service 的 preprocess-history 失敗案例雖建立 capability policy，未驗證 fail-closed；
  補 TRAIN／PREPROCESS 禁用的實際 assertion，不只驗 fixture 建立成功。
- Teacher preflight 的共用 teardown 吞掉 close failure，可能讓 epoch handoff 宣稱成功；
  先真 service 故障重現，再保留原 stage evidence 並使 cleanup failure 明確不通過。
  只修直接驗證可靠性，不扩成 Import 模組審查。
- UI baseline capture 的 timer callback 若寫圖／讀回失敗可能跳過正常 shutdown；
  先真 Qt fault regression，沿既有 callback/close 路徑收尾並回報失敗。Visualization
  CLI setup 的重複 exception hook 則刪除，由既有 run 函式唯一安裝／還原。
- Windows DPI evidence 的 observed ratio 為 JSON NaN 字串時可繞過差值比較，
  獨立 reviewer 已重現 validator 與 CI adapter 都放行；沿既有 validator 拒絕非有限值，
  保留正常 100／125／150% 門檻，補 JSON roundtrip 與 CI 消費端回歸。
- 同一 evidence 覆核重現 native smoke JSON 為 null 時被當作讀取失敗 sentinel 而跳過
  malformed 檢查；有效 source provenance 仍會誤放行。沿既有 reader／validator 分清
  讀取錯誤與合法解析的非 object 值，以真檔案＋provenance 回歸，不新增 evidence owner。
- Native platform smoke 在 service/window 建立後的 query／panel setup failure 未經 finally；
  真 panel-routing 故障重現後由既有 service/window close 收尾，保留原失敗與 evidence。
  Handoff recorder 的唯一 caller pass-through parser 在 characterization 後直接呼叫既有
  terminal parser，刪無用途 wrapper；manifest/recorder ownership 與判定不變。

已完成的前期施工細節留在 Git 歷史與 ignored review evidence，不再維持多份 Current／Next。
目前尚未宣稱 scope-complete 或 handoff-ready；唯一退出條件仍是上方完整分母與同版 gates。
