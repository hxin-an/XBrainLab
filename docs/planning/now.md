# XBrainLab Now

最後更新：`2026-06-20`

這頁只放下一輪施工焦點。

## 目前焦點

**Weekly stabilization：BIDS Epoch + finalized saliency baseline flow.**

`ux/saliency-compute-flow` at `6b29fc4f` 是已驗證 checkpoint，不是本週最終 hand-test
candidate。`stabilize/bids-epoch-saliency-baseline` 目前正在收斂 2026-06-17 progress report
定稿方案：training 完成後背景先算最快 baseline，Visualization 只顯示狀態或已算好的結果，
進階方法由 Saliency Settings 觸發重算。

本週進度以「把報告裡定稿的新方案落成可手測版本」為主；implementation slice 已完成。
交給人工手測前，以 clean commit 上的 `artifacts/quality/latest.md`、多資料集 gate 和
branch push 狀態作為 handoff 判斷。

## 本週 To-do

| 狀態 | 工作 | 完成判準 |
| --- | --- | --- |
| Implemented / validated | BIDS Epoch design | Data Import recipe 保存 BIDS / BIDS-like `onset`、`duration`、`trial_type` / label field、placement choice 和 epoch handoff；Epoch step 可讀 recipe 建議，不再只依賴 label time。 |
| Implemented / validated | Saliency finalized flow | Training 完成後背景先算 `Gradient` + `Gradient * Input`；不阻塞 training completion，不跳打斷式 dialog；Visualization 若 baseline ready 就顯示，若仍在算就顯示 non-blocking status。 |
| Implemented / validated | Advanced saliency recompute | SmoothGrad / VarGrad / SmoothGrad_Squared 由 Saliency Settings 觸發；選進階 method 或改參數才重新計算；切換 map / topomap / spectrogram / 3D plot 只重新 render，不重算 saliency。 |
| Implemented / validated | Saliency status and tests | UI visualization surface 顯示 computing / ready / failed；測試覆蓋 background baseline、advanced recompute boundary、錯誤不 crash。 |
| Verified | Multi-dataset confidence | 保留 Graz / BBCI / PhysioNet / SCCN EEGLAB / MNE testing-data / MNE-BIDS tiny EEG 的 gate；strict matrix 和 cross-source smoke 已重跑。 |
| Implemented / validated | Large dataset resource guard | `LoadData` / Data Import apply 前做 file-size RAM preflight；`TrainCommand` 前做 dataset RAM / GPU batch VRAM preflight，太大時回 recoverable blocked reason。 |
| Pending human review | Data Import wizard regression | GDF + MAT labels、remove/re-add label、BIDS folder、loaded label placement 四種模式至少各跑一次；任何 duplicate label、無法移除、回跳 step 或 review summary 錯誤都要記為 blocker。 |
| Pending human review | Evaluation / Visualization visual QA | 確認 evaluation table、model summary、fold switch、2D saliency、3D blocked / available state 在實機上沒有白列、卡住或錯誤 label mapping。 |
| Handoff gate | Merge readiness | clean dashboard / docs gate、commit、push、claim boundary 完成後，才交給人工手測；手測問題清完再合入 integration/main line。 |
| Deferred | Agent / tool-call benchmark research | 先把桌面本體穩住。benchmark case generation / auto-research scoring 文件已作為後續研究方向，不併入本週 product stabilization。 |

## 本週已通過的 automated gate

| Gate | 最近結果 | 邊界 |
| --- | --- | --- |
| fast quality dashboard | Use generated `artifacts/quality/latest.md` from the clean branch/commit | 工程健康，不等於人工驗收。 |
| Data Interpretation format matrix | expected capabilities observed / match | 支撐代表性格式邊界；不支援 XDF / LSL parser。 |
| Dataset validation matrix strict | OK | 覆蓋 checked-in GDF/MAT、compact multiformat、public event-rich fixtures、public BIDS EEG fixture。 |
| IO + public BIDS + cross-source integration | `36 passed` | 多資料集 smoke，不是所有公開資料集認證。 |
| Public cross-source strict smoke | `4 passed, 0 missing, 0 failed` | PhysioNet EDF、BBCI GDF、SCCN EEGLAB、MNE CNT。 |
| Saliency / visualization focused tests | ApplicationService / training / visualization focused regression PASS | 覆蓋 background baseline flow、advanced recompute boundary 和 settings method selection。 |
| Resource preflight tests | data compatibility + Data Import apply + training service focused regression PASS | 覆蓋 import RAM preflight、training RAM/VRAM preflight 和正常 workflow 不被阻擋。 |
| Docs build | `mkdocs build --strict` PASS | 文件可建，不代表文件內容已完成審稿。 |

## 本週不做

- 不重開 Match Labels / Review and Import 大型 UX 設計，除非 BIDS Epoch 或手測發現 blocker。
- 不擴張成 full BIDS validator、XDF / LSL parser 或 proprietary converter。
- 不開始 thesis-grade agent benchmark 實驗；先穩住 desktop workflow。
- 不把 automated dashboard PASS 當作 human Windows acceptance。
- 不把 explicit `Compute Saliency` checkpoint 當作 report 定稿的 saliency 最終方案。

## 收尾條件

本週可以收尾的條件是：

1. BIDS Epoch handoff 和 finalized saliency background-baseline flow 已實作並有 focused tests。
2. 使用者完成上述手測主流程，或明確標出 blocker。
3. 若有 blocker，修完後重新跑 focused regression、same-class sweep、handoff gates。
4. `docs/current.md`、`docs/planning/now.md`、`docs/validation/README.md` 沒有互相矛盾。
5. 分支保持 clean 並 push；合併前保留一條清楚的 manual-test candidate branch。

**Release-candidate gate：Backend Command Spine / Legacy / UI Refresh / Test Cleanup / Runtime UX。**

要先做這件事，因為 MVP 前最大的風險不是功能不夠多，而是 UI、backend、assistant、MCP
各自保存一套 workflow truth。

Data Import 這條線已先補一輪 UX target alignment 並交付第一版 task-oriented step-panel
wizard baseline：primary import actions、external label sources、selected scope vs scan location、
structured action items、recipe preservation 和 UI / agent / MCP command surface 對齊。
最新 UI polish 已把每個 wizard step 改成不同任務 panel，不再只是把表格搬到各 step；footer
也已把 `Cancel` 放左下、流程導航 / apply 放右下。主 Dataset sidebar 已移除第一層
`Add Labels to Loaded Data` / `Smart Parse Metadata` 舊入口。這仍需要 human Windows desktop
acceptance。

2026-05-13 Data Import Tier 1/Tier 2 checkpoint 已補強 GDF/BNCI-style external labels、
BIDS-like events、generic internal events / annotations、external MAT/CSV/TSV/TXT label carriers
四類主流路徑的 scan / preview / placement / recipe / review tests 和 screenshots。仍不支援
P300/SSVEP/clinical/XDF/LSL/MOABB/proprietary converter 等非本輪範圍。

## 本輪要達到

| 工作 | 完成判準 |
| --- | --- |
| Legacy product path cleanup | real `Study` runtime 的主要 mutating path 不再 silent fallback 到 legacy controller mutation；service wrappers 不用 generic forwarding 掩蓋 command contract。 |
| UI refresh cleanup | command 成功後的頁面更新由 shared refresh route / changed state 驅動，不由各頁自己猜；manual-test regression 要補 UI / walkthrough coverage。 |
| Test cleanup | 測試不再把 legacy fallback 當作預期成功路徑；mock 只隔離外部依賴；non-blocking gate findings 也要清掉才可收尾。 |
| Validation reality-gap audit | 盤點現有 tests / artifacts / smoke 的 claim boundary，補上 human-observable product smoke，避免 dashboard PASS 但實機 workflow 仍不可用。 |
| Data Import UX alignment | task-oriented step-panel wizard baseline、Tier 1/Tier 2 label-placement support、BIDS-like review card、fallback format guidance 和 canonical screenshots 已有 focused coverage；後續不再以 debug-style preview 為目標。 |
| BackendFacade boundary | Product runtime packages use `get_application_service(study)` / `ApplicationService`; `BackendFacade` module is removed and must not be reintroduced. |
| Architecture guard | 新增或維持 guard，防止 product path 繞過 command spine。 |
| Docs alignment | `current`、`roadmap`、`architecture` 不互相矛盾。 |

## 接下來才做

| Phase | 開始條件 |
| --- | --- |
| 1B Data Interpretation MVP Slice | downstream supervised-limited state、event extraction summary、metadata recipe provenance 和 screenshot artifact 補齊。 |
| 1C Tool-Call Product Baseline | command surface 和 state snapshot 足夠穩定。 |
| 1D Windows Desktop Acceptance | backend / UI / Data Interpretation / assistant baseline 可跑代表性 workflow。 |
| 2 Release Candidate | human desktop MVP acceptance 有證據。 |

## 本輪驗證

| 改動類型 | 至少要跑 |
| --- | --- |
| docs only | `poetry run mkdocs build --strict`、`git diff --check` |
| backend command / legacy cleanup | `tests/architecture_compliance.py`、focused backend command tests |
| UI refresh cleanup | focused UI refresh tests 或 walkthrough artifact |
| validation reality-gap audit | test matrix、human-observable walkthrough smoke、至少一條 launcher -> import preview -> apply 的 product smoke。 |
| agent / MCP surface | agent tool tests、MCP adapter tests |

## 不能先講

- product complete。
- backend target architecture fully aligned。
- Data Interpretation final。
- automated walkthrough 等於 human Windows desktop acceptance。
- tool-call eval 等於產品完成。
