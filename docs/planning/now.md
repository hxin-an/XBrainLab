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

## Active — Training／Preprocess 行為鏈重審與收尾

2026-10-11 使用者核准擴充為 Training＋Preprocess 全面重審、修正與必要清理，做到
同版本整合驗證、獨立覆核後一次集中 Windows 手測；沿目前 PR #162 整合，不自行 merge。
本輪起點 `98bc99ac`；下列舊審查完成記錄只代表當時檢查，不代表本輪已閉合。

### Reopened evidence and acceptance

- 已重現：disabled early stopping 保留非預設 patience/min_delta 時，export 合法但 loader
  拒絕自己的紀錄；補真 JSON/NPZ roundtrip 和 early-stop→best weights→evaluation→reload。
- 已重現：MOABB product journey 持續 timeout 在 finally 跳過 service.close 且中斷結構化
  回報；沿既有 shutdown owner 補持續失敗清理，不只測下次 wait 自行成功。
- 已重現：coverage concurrency 只有 multiprocessing，漏記 Python worker threads；補
  真 worker instrumentation regression，修正量測後才判讀各責任區缺覆蓋分支。
- UI 已接受；唯一新可見改動為 Preprocessing history 數字去容器括弧，例如 Notch [50.0]
  Hz→Notch 50 Hz，多值逗號分隔。保留單位、順序、有效資訊與資料語意，不全域刪括弧。
  先原生 focused preview／截圖，不重畫 layout、配色或流程。
- 完整新增範圍：preprocessor 全部運算、channel/montage接點、resample/rereference/
  normalize/filter/notch、event/window epoch、history/preview/summary、command preparation /
  publication / cancellation / rollback，連同 tests、fixtures、scripts、CI/Poe、設定與文件。
- 三條分工：Training 核心与結果；Preprocess 資料變換与交易；scripts/coverage證據。
  主 agent 擁有 history 顯示、整合、coverage判讀及跨模組覆核；各改動先 red 或 passing
  characterization 再修，獨立覆核必須看實際 diff、未改責任與缺口，不只接受作者摘要。
- 行為矩陣至少包含非預設值/開關/重開、multi-subject/fold/repeat、停止重跑、持續失敗、
  資料/event/label/time 語意、部分失敗不發布、preprocess替換使舊training/results失效、
  stale callback不覆蓋新狀態。真資料/模型/檔案證據與 mock 接線證據分開。
- 結構審查要有每個責任區的真入口、owners、去留理由；查死碼/重複policy/過度轉接/
  大檔混責任/脚本入口。無必要不新增owner、cache或control plane；性能變更先量測。
- Non-goals：不重做 Import／Agent／Evaluation／Saliency 全模組、不改 public Command／
  Assistant contract，不作所有模型科學認證；研究資料/封存/共用環境/settings.json不動。
- Stop：範圍清單無未查清責任、已知defect與必要測試缺口閉合、獨立整合覆核無blocker、
  exact-head CI/source-diverse/platform/Windows gates通過，開完整Windows程式與即時log
  再交集中手測。不是修三個bug或讀完檔案即完成。新UI/公共契約決策另請核准。

Preprocess re-audit findings：以真 MNE nonzero first_samp recording 重現 filter 在無
meas_date時重設 annotations 重複加時間偏移、resample尾端事件落到新n_times之外。
修正沿MNE既有event/time契約，測原始carrier不變、annotation位置及新sample範圍。
主agent另查預覽event與signal時間原點一致性，先真MNE red再修，不改UI設計。

Current：重審施工中，先前 handoff-ready 判斷因上述已確認缺陷撤回。
Next：各責任區讀碼/測試矩陣與red重現→修正/清理→交叉覆核→同版本gates→手測。

### Earlier Training scope and reviewed decisions

2026-10-11 使用者接受上述 UI 並核准完整 Training 功能鏈清理到獨立覆核、整合驗證後
一次集中手測。前述預覽階段的等待回饋／不做後端工作限制已由本階段取代；後續收斂
歷史預覽記錄，只保留已接受的 UI 基線。設計接受不是最終產品手測或 merge 批准。
基線 main `9d542f3e`（PR #161），既有 UI diff 納入本輪；研究 checkout、settings.json、
原始資料、研究封存與共用環境不動。Git 擁有 branch/head 真相。

### Outcome / scope / principles

完整範圍：Data Splitting → Model Selection / Training Settings → Start / Stop / rerun →
history / checkpoint / Evaluation–Saliency 交界；連同 tests、fixtures、scripts、CI / Poe、
依賴與文件入口。每個項目列責任、真入口、owner／讀寫／消費者、測試與去留理由。
不能以幾條 happy path 或只審 diff 宣稱模組乾淨。必要功能也須比較現有組織是否合理：
直接刪除、局部合併、重用既有 owner、責任抽離與保留，不為行數目標搬程式。

Non-goals：不重畫 UI、不改 Command / Assistant 契約、EEG / split / artifact 語意或
支援模型取捨，不重做 Evaluation / Saliency 全部，不跑論文實驗／prompt 調參。
公共契約／可見行為變更另提決策。dead-code 檢查含動態註冊、設定、腳本與文件；
確認無用後連同專屬測試與引用物理刪除，不搬 legacy／留空殼。有用 recovery models
不因目錄名而刪除。取消、一致性、過期拒絕與舊結果讀取保留；性能先量測，不投機加 cache。

### Coverage / execution

| 群組 | 責任與入口 | 狀態 |
| --- | --- | --- |
| Split | dialogs → preview / saved spec → generation / audit → materialization | 讀碼、修正與跨 transaction 獨立覆核完成；待整合 gate |
| Model / settings | GUI / Assistant handoff → ConfigureTraining → catalog / option / recommendation / resource preview | 讀碼、roundtrip／receipt／optimizer 修正與覆核完成 |
| Execution | Train / Stop → service / runtime / manager / monitor / publication → folds / repeats / terminal | lifecycle／rollback 深審完成；停止後 repeat admission 已修 |
| Results | records / checkpoints / history → Evaluation / Saliency | 身分／消費者邊界與檔案回復覆核完成；不宣稱 crash-atomic |
| Tests / fixtures | 各群 unit / integration / native journey | 核心本文缺口已補讀；兩個空洞斷言已修，注入錯誤確認會失敗 |
| Scripts / config / docs | training / resource / captures / fixtures / gates / CI callers | 用途已核對、重複已收斂；MOABB 明確 saliency 計算已實跑與覆核 |

先全面清單，再按上表施工；可獨立盤點並行，寫入 ownership 分離。每個 coherent slice
先 passing characterization，bug 先 red reproduction，再 focused checks／lint及必要相鄰整合。
不建立通用盤點平台或每helper表單。高風險資料／跨owner／async／publication獨立覆核；
最終 reviewer 另看整合邊界、未改責任群、保留大檔理由與測試品質。主 agent 必須驗實際證據。

### Validation / endpoint

重要行為：多subject / fold / repeat 全部執行、preview=materialization、train/val/test
隔離、Validation Disable、設定保存／取消、stale拒絕、停止後重跑、失敗不污染舊結果、
best checkpoint／early stopping／artifact重開、狀態列與 GUI/Assistant 同源。
以可回退小 commit 累積、分組 review，最後一版集中手測，不逐切片要求手測／merge。
complexity gates 仍適用；單切片超限需拆分或另取例外。交付走同 head applicable CI、
source-diverse、platform／Windows UI gates；不跑等價本機全套，不降 gate 或藏失敗。

Stop：全部盤點有結論、確認問題處理、無範圍內 blocker、獨立覆核及整合驗證通過後，
開 Windows 程式與 log 並給集中手測。未查清不算完成；不因切片完成、compaction 或 CI
pending 停工。只在此 endpoint、使用者暫停或必要新決策／資源 blocker 停止。不自行 merge。
Adjacent findings 最多三项 follow-up，非必要依賴不擴大施工。

Earlier checkpoint：UI／後端／artifact／evidence 修正已分成可回退 commits；Git 擁有精確 SHA。
前次獨立覆核未發現上述後續重現的缺陷；其通過不作本輪完成依據。
首輪整合 CI 抓到六個 typing diagnostics：optimizer helper 的 int 預設被推論成
只接受 int，以及 Qt view/window/statusBar 的 nullable stub 未收窄。補明確 float 契約
與 Qt nullable 回傳的顯式收窄，不放寬 analyzer baseline；focused typing／元件測試後
重新驗證新 head。首輪 Windows 原生四案例與 2D／3D capture 已通過，保留原 SHA 證據。
Next：整合 clean head／PR／CI → 補 CI 未涵蓋的原生 Windows
真實 Training→Evaluation／Saliency walkthrough → 開啟手測版本。不改研究封存。
細節工作證據在 ignored `build/training-cleanup/`，本文為唯一 active plan。

### Reviewed implementation decisions

- 補讀測試：兩個 warning absence 測試在未顯示的 parent 下檢查 isVisible，可能空集合
  假綠；顯示真 widget 後驗證可見文案／隱藏警告，並刪除 availability matrix 未使用的
  兩個期待欄。保留按鈕／tooltip 行為保障，不改產品 UI。
- MOABB product walkthrough：舊路徑只在訓練前設定 saliency，訓練後 parameterless query
  不會計算；目前 metric-only training 下永遠缺 saliency 產物。先用現行 service 契約
  重現，再在完成訓練後明確要求既定方法並等待 terminal，query／export 仍沿既有入口。
  修正現用工程腳本及其過強 fake，不增加 owner、不跑研究模型評測或擴張資料下載。

- 結構收斂：刪除無caller的 TrainRecord matplotlib convenience methods／專屬測試，
  繪圖仍由 MetricTab/history projection 負責；Split UI 的純 setter Holder 與重複列建構
  收斂到既有 dialog／domain value，不加owner。Root收斂兩份capture split fixture至既有
  training_evidence_fixture，修正示例 Validation Disable／holdout 顯示及過時強制尺寸。
  補查 Dataset.has_set_empty／DatasetGenerator.reset 的非文字 caller／文件入口；
  確認 tests-only 才刪除與專屬測試，constructor 初始化保留。進一步 producer／consumer
  追查確認 trial_selection_evidence 無任何現行 producer、結果／recipe consumer 或
  Epochs deserialization：只有 []/0 初始化、reset、snapshot/restore與專屬 tests。
  因而物理刪除整段失效欄位／helper／preview與transaction傳遞鏈及專屬假資料測試；
  保留真實 EEG／atomic groups／membership／RNG／Dataset.SEQ 的取消与rollback證據。
  這不改 EEG／recipe／artifact 格式；跨transaction diff 已完成獨立覆核。
- Artifact evidence：獨立 scripts review 發現 real-training helper／source-diverse runner
  只確認 record 檔名存在，實際僅重開 checkpoint／EvalRecord，不能支撐完整重開宣稱。
  用既有安全 reader／record loader 補實讀與必要語意檢查，真檔案 corruption regression
  須能抓到壞 manifest／NPZ；同時收斂重複驗證，不增加產品 owner 或 artifact 格式。
- 移除 dead internal API：TrainingStateService 舊 startup snapshot／restore、
  TrainingPlanHolder 舊 evaluation convenience 與 DatasetGenerator.apply 直接套用路徑；
  須完成動態／文件／腳本 caller核對，刪專屬 tests／mock，保留 canonical rollback、
  history／結果及 preview→transaction 測試。Runtime / Split reviewer 分檔 ownership。
- Resource receipt：普通 Training Settings 保存漏傳已接受的 resource preview receipt，
  coordinator 又誤要求 command 重送 model；先真入口測 provenance，再保留 current-model
  freshness 修正，不重寫模型、不放寬 stale receipt。Settings reviewer 負責。
- Artifact pair：調查 NPZ 先替換、JSON後替換失敗時是否損及既有artifact；先真檔案故障
  注入已重現 SHA mismatch。獨立安全設計覆核通過 bounded backup／ordinary OSError
  rollback；只在 NPZ 成功後的 manifest replace 失敗回復，identity error 不追路徑。
  回復失敗保留唯一 backup 與原始錯誤；增加相關故障／path safety tests，再覆核實際 diff。
  不改artifact格式，不宣稱 crash-atomic／concurrent-reader atomic。
- Panel：完整檢查 publication／history／plot／log／shutdown 後，核對未使用的
  plan_items／run_items 與永遠 False 的 log-suppression 分支；passing baseline 後刪除，
  保留選取、重繪、停止與 busy-query fallback 語意，不移動 UI 或新增 owner。
- Capture gate：Windows offscreen 字型的 Test Acc「—」只有 7 個 edge pixels，
  reference comparison 接受但 tile cutoff 8 導致 detail_tile_count=0，validator 拒絕。
  保持全域 edge／差異／missing-detail 門檻；沒有 qualifying tile 的稀疏 glyph 以
  整個 bounded region 檢查細節，補真像素保留／擦除 regression，不改產品 UI。
- 設定 roundtrip：核對已有 seed 在重開 Training Settings 後保存會回到預設值；以
  真 service → dialog → command → service 固定非預設 seed，保持隱含值及新設定預設。
  不新增 UI 控制項，settings reviewer 擁有此對應鏈；不改其他參數語意。
- Split close：preview publisher 註冊前關閉／reject 的第一次取消可能找不到 request，
  close retry 只等退出不重試取消；以 Event-barrier 真 publisher 重現後，在既有等待迴圈
  重試取消，不新增 timer／owner，不改 UI。Split reviewer 負責此檔与 lifecycle tests。
- Optimizer：核對 UI 與 backend optimizer map 重複；合法 baseline 後補真 service invalid
  kwargs rejection／舊設定不變，再由既有 TrainingOption admission 收斂。Owner不增加，
  不改支援 optimizer 集合；settings reviewer 負責 production / focused tests。
- Stop / repeat：核對 active repeat 停止後是否仍建立下一 repeat 的 model／loader／artifact；
  real-record red test 後在既有 loop admission 修正，保留當次停止語意。Runtime reviewer
  負責 training_plan 與 focused tests，生命週期修正後另獨立覆核。
- Script fixture：共用固定 temp 路徑的 writer 每次會 rmtree 同一來源目錄，平行 evidence
  可能互刪。核對唯一 capture caller 後改用 caller-owned TemporaryDirectory 與現有 raw
  writer，刪無必要 convenience API；驗證獨立來源、清理及 capture 真實執行。
