# XBrainLab Now

最後更新：`2026-10-11`

## Active — Select Model 檢查提示不閃爍／不推動版面

PR #160 已合併；本輪從 main `35ccddb3` 建立獨立 task worktree，研究 checkout 不動。
使用者指出 Select Model 檢查套件可用性時提示一閃而過，已同意穩定布局、快速完成不閃出
提示、等待時才顯示狀態。UI 確認：已批准此方向，實際 Windows 預覽尚待接受。

證據：ModelSelectionDialog 建構即顯示 Checking Braindecode，背景檢查完成後隱藏提示並
重新 fit_to_content；不是 MOABB 下載或模型推論。先量 Windows 首次／再次開窗的
provider 耗時、提示可見轉換與 geometry，再決定是否有必要提早檢查；不得憑感覺加 cache。

Outcome：正常快路徑不閃提示，慢路徑有可理解狀態且不推動布局；確認前仍驗模型可用性，
搜尋／取消及失敗 recovery 語意不變。Scope：model dialog、直接測試、必要現況文件。
Non-goals：不改模型清單／設定／資料語意、不提前重構 Training 或 Split、不新增全域
readiness owner／cache，不載入或評測 Assistant 模型，不建新環境。

步驟：原生 baseline → 直接呈現 regression red → 最小 UI 修正 → focused tests／lint →
同 workload 原生量測與截圖 → 開啟真元件預覽給使用者。慢路徑用受控 external seam 補測，
另保留真 provider 成功的證據；保護失敗、取消、重開與搜尋選取。
Stop condition：原生預覽已開啟且有回應，交使用者確認設計；不是正式 handoff-ready 或 merge。
設計接受後才更新必要 visual references、跑重型 CI／DPI 與正式整合驗證。

原生 baseline：首次 provider 2386 ms、再次約 2 ms；搜尋／清單完成時上移 43 px。
修正為標題列延遲 300 ms 的 inline hint，provider 立即工作、不延後 ready；真正失敗才用
原 banner。沒有新增 cache 或預載 owner。新版真 provider／幾何量測確認位移 0 px、
warm 開窗不顯示 hint；首次耗時會受 OS/import cache 影響，不宣稱 backend 加速。
原始 red 為兩項呈現錯誤；focused 模型選取、取消、失敗及 geometry tests 通過，Ruff 通過。
獨立 actual-diff／原生 artifact 覆核無阻擋。未跑重型 CI／DPI，未更新 approved references。
Windows 隔離預覽已開啟至真實 Model Selection，確認可見且有回應；22 項 focused tests 通過。
Next：等待使用者確認此呈現，再進正式候選驗證；不持續監控使用者操作。
