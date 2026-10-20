# BIDS 匯入深度審查 — 2026-10-20

## 結論與範圍

目前不能宣稱 LOAD BIDS 全面沒有問題。一般明確選取 recording、同層 sidecar 的路徑有實測
保障，但取消後重試、recipe 選項保留、驗證一致性、繼承 sidecar 與 Command 路徑別名仍有缺口。
本輪只審查與重現，沒有修產品、改 UI、刪測試、下載資料或改來源 EEG。

- 被審產品：`origin/main` 的 `52d3a61583a5395d5cb7d51fc20e5e2c5174d891`。
- 隔離分支：`audit/bids-import`；worktree：`D:\workspace_v2\projects\lab\XBrainLab-bids-audit`。
- 使用既有 shared Windows Python：`D:\workspace_v2\projects\lab\XBrainLab\.venv\Scripts\python.exe`；
  Python 3.12.10、Windows 11 build 26200、MNE 1.11.0。
- 原研究 checkout、文件網站 worktree、使用者 `settings.json` 均不在修改範圍。
- 診斷材料保存在該 worktree 的 `build/bids-audit/`，屬本機 ignored artifacts，不是 CI／release
  證據。下列重現程式使用暫存副本或合成小型 BrainVision，沒有改原始資料。

## 實際覆蓋與未覆蓋

| 面向 | 已核對的行為／證據 | 限制 |
| --- | --- | --- |
| 發現與選取 | root/nested root、subject projection、companion dependency、scan completeness 與 cache freshness 的現有測試；D 槽資料清單 | 不等同 134 個歷史入口在本版本全通過 |
| metadata／伴隨檔 | EEG JSON timeline、同層 channels、geometry，以及 root-level TSV／JSON 覆寫正反例 | 非完整 BIDS validator；繼承缺口見下表 |
| events／labels | 實際 TSV 選欄與 class/sample、內嵌事件明確選類、無 label 路徑；特殊類名與 sample-index 重現 | 字面 trial_type 正確不等於獨立驗證科學任務標籤 |
| 時間／波形 | duration→epoch、mixed sampling rate→resample、末端 point、D 槽代表 recording 波形比較 | 波形對照以保留的 BIDS 檔為準，不是原始 MOABB 轉換前資料 |
| 確認／取消／失敗恢復 | 實際 Preview publication→Validate cancel→retry；現有 apply/revalidation 取消測試與原子性保護 | 特定取消窗口已重現失敗；不以其他取消案例通過代替 |
| recipe／入口一致性 | fresh-service recipe、GUI 使用共同 Commands、Assistant 開窗取消、Command alias 對照 | 沒有本輪模型推論或 Assistant 完整成功匯入的端到端證據 |

### 資料可用性

D 槽 `D:\XBrainLabCache\datasets\bids` 共 15 個 roots、261 recordings、2,197 檔案，
9,622,487,796 bytes。Recording 格式為 77 BrainVision、39 EEGLAB、30 BDF、115 EDF。
37 是逐 root subject 目錄數的加總，不是跨資料集去重的人數。

已對全部 261 份 events.tsv、398,884 列做結構檢查：在側檔聲明取樣率下，未見超過
0.501 sample 的 onset/sample 差異、非單調／重複 sample、負 sample／duration 或空 trial_type。
這項檢查不讀完全部波形，也不證明來源標籤的科學意義。

Windows 目前未掛載 E 槽；`E:\XBrainLabData` 及 canonical campaign manifests 不可用。
因此歷史 **134 個 required 入口與 1,205 recordings** 不能重認證，也不能用 D15 子集替換分母。
不將過去的授權待處理／來源阻擋案例刪除，亦不推定 E 槽資料已遺失。

## 已確認發現

優先順序按使用者影響，不按刪除行數。每項均有來源追蹤；高風險生命週期與資料發現另經獨立覆核。

### 1. 上層 channels.tsv 未套用，仍可成功匯入

- 對照：同一小型 BrainVision，C3 為 EEG、C4 在 channels.tsv 聲明 EOG。
  同層 recording-specific sidecar 匯入為 `[eeg, eog]`；只改成 root-level
  `task-cvep_channels.tsv`，匯入仍顯示 safe／成功，但為 `[eeg, eeg]`。
- 原因：`bids_dataset_index.py:745`（events）／`:749`（channels）只建立同層精確名稱的 TSV 配對；
  `data_interpretation_bids_channels.py:124` 無配對直接略過，後續標成 not_applicable。
- 影響：一種已實測繼承形式可靜默失去通道類型。沒有據此宣稱所有 inherited units、
  bad status、數值縮放都錯誤。
- 同組 events 對照：root-level `task-cvep_events.tsv` 雖被 index 發現卻未配對，Validate
  blocked、Apply 拒絕。這是已知支援邊界的實測缺口，不是已證明的資料污染。
- 證據：`inheritance_probe.py`、`inheritance-probe-resolved.json`、`inheritance-resolved.log`。
  初版 Windows 8.3 alias 造成的失敗另存 `inheritance-probe-result.json`，不拿它當產品證據。
- 後續決策：實作有明確 entity／層級規則的一般繼承，或明確阻擋尚未支援但會影響資料解釋的
  sidecar；不可忽略後宣稱完整支援。此決策不在本輪審查授權內。

BIDS 1.11.1 的 metadata 繼承原則允許適用的 metadata 位於上層；TSV 不應把不同層任意逐列
合併。Events 文件明示一份 events.tsv 可以適用多份 recording。
參考：[Inheritance principle](https://bids-specification.readthedocs.io/en/v1.11.1/common-principles.html#the-inheritance-principle)、
[Events](https://bids-specification.readthedocs.io/en/v1.11.1/modality-agnostic-files/events.html)。

目前架構文件已明示「不是 full inheritance」；使用文件描述的是較廣的 accepted target。
本審查不把 target 說成已完成，也不把 unsupported 誤寫成來源資料不合法。

### 2. Preview 已發布後取消 Validate，重開的 wizard 持有舊 generation

- 實際序列：Preview expected=2 成功發布 generation=3；Validate(expected=3) 取消；
  重開 review 卻持有 generation=2；再試 Preview 被正確的 stale guard 拒絕。
- 原因：`data_interpretation_action_coordinator.py:1526` 與 `:1644` 的取消重開 closures
  忽略傳回的新 preview_state，重新使用舊 review_state。
- 影響：特定取消窗口不能正常繼續；不是要求移除 stale 保護。未觀察到 active dataset 被改壞。
- 證據：`repro_cancel_validation.py`、`cancel-validation.log`；使用真實 Commands／publication，
  只隔離排程／視窗重開並注入 Validate 取消，不冒稱完整真人點擊。
- 測試缺口：unit async-flow 測試接受舊 generation；既有 native revalidation 取消案例在
  Preview 發布前取消 candidate build，沒有涵蓋此窗口。Apply-cancel 另有發布後重試成功的
  保護，不能混為同一窗口。修復應補「Preview 先發布，Validate 再取消，再重試成功」。

### 3. sample-index recipe 遺失必要選項，第一次能匯入，重播失敗

- 明確指定 zero_based、recording_relative，samples 100／300；初次匯入正確。
  Save→新 ApplicationService→Reload→Validate safe，Apply 卻拒絕缺少 base／origin。
- 原因：`data_interpretation_recipe.py:363` 的還原 field_map 沒有保留
  `sample_index_base`、`sample_index_origin`。
- 影響：已支援的選項不能完整重播；既有 seconds recipe 測試不涵蓋這個模式。
- 證據：`semantics_probe.py` 的 `sample_index_recipe`；`semantics-confirmed.log`。
- 修復方向：既有 recipe owner 完整 round-trip，保留必要驗證，不新增第二套 recipe 系統。

### 4. Validate 說 safe，但 Apply 才拒絕

已重現兩種條件：

1. class 名稱 `Badminton`：通用 review 原本有 MNE Bad*/Edge* 保護，BIDS 專用 review
   覆寫 `placement_review` 後遺失阻擋；Apply 仍正確拒絕。
2. 100 Hz、1,000 samples 的 point event onset=9.994 秒：BIDS review 使用 `<10 秒`，
   實際 EventLoader 使用 `<=9.99 秒`，因此先通過再失敗。

來源：`data_interpretation_candidate.py:471`、`data_interpretation_bids.py:178`／`:498`、
`data_interpretation_placement.py:326`、`XBrainLab/backend/load_data/event_loader.py:331`。
第二項不混同已測的 duration 精度或 inclusive epoch tmax。
證據：`semantics_probe.py` 的 `bad_class_prefix`／`last_sample_fraction`。

修復方向是讓 review 與 apply 使用一致的既有語意；不是擅自放寬所有類名、移除保護或改時間定義。
Recipe 缺少 sample contract 的重播同樣被這個 review 覆寫問題掩蓋。

### 5. events.json 下層欄位覆寫後，仍拿上層 Levels 當建議

- root `trial_id` 有 Levels，recording-specific `trial_id` 改為只有 Description。
  `_bids_event_level_labels` 會繼續往上找到非空 Levels，提出舊 root label 建議。
- 來源：`data_interpretation_label_carriers.py:1562`。它找第一個有 Levels 的檔，
  不是先依 JSON top-level key 覆寫，再讀有效欄位。
- 影響目前限定為錯誤的名稱建議；明確選的 Target 0／1 仍正確匯入，
  沒有證據說已確認 class 被偷偷覆寫。
- 證據：`semantics_probe.py` 的 `json_field_override`；修復需要 top-level 欄位覆寫回歸測試。
  規則依上列 BIDS 1.11.1 inheritance principle，不憑資料集名稱設特例。

### 6. Command 用完整路徑別名提供 label choices，可能無法命中

- 測試重用資料時以 Windows junction 指向同一份 public fixture。Scan 會解析成實體路徑，
  但以 junction 完整路徑當 key 的 `label_carrier_choices` 未被套用，preview class_map 為空。
- 原因：candidate 的 selected files 與 required-carrier 檢查接受唯一 basename 對應；
  `data_interpretation_label_carriers.py:351` 的 choices 查找只查字串形式，不採同一正規化。
- 這是直接 Command／外部 choices 的別名邊界問題。一般 wizard 使用 backend 提供的 canonical
  path 作 key，目前不能說一般 GUI 選檔必定受影響，也未證實錯誤標籤被成功 Apply。
- 原始證據：`integration-io.xml` 的 `test_public_mne_bids_import_apply_recipe_and_epoch`。
  同次 OpenNeuro responsiveness 失敗只是 expected path 字串未 resolve，不算第二個產品缺陷。
- 後續應明確正規化或拒絕無法綁定的 choices，避免靜默忽略；不能只把該測試改綠。

## 測試品質與腳本審查

現有測試不是全都高 mock：真實 BrainVision／EEGLAB、class/sample tuples、fresh recipe、
duration→epoch、來源變動拒絕、可見 wizard 與原子發布已有實際保護。本次發現的重點是
**交接窗口與選項組合缺少 oracle**，不是僅缺測試數量。

- 取消測試需驗證真實 publication 之後的 retry，不能用 mocked 新舊 state 接線當成功。
- recipe 測試需覆蓋 supported time models／必要選項，不只 seconds。
- channels 型別測試的零波形不能證明非零訊號幅度／單位保真；本輪沒有證實縮放缺陷。
- `moabb_user_journeys/import_conformance.py:490` 的 required-resource helper 沒列
  participants.tsv，但產品 metadata reader 會讀它。若 manifest 也沒包含該檔，身份綁定不完整；
  尚未證明歷史某份 manifest 已因此錯誤通過。
- conformance helper 比較完整「選取 recording」的波形、通道、取樣率、sample 數及 class/sample，
  並 fresh-service 重播。它不自動代表每個 retained recording、原始轉換正確、participants、
  bad status 或所有 epoch 科學語意都已驗過。
- D15 選每 root 排序第一個 recording，明確使用字面 trial_type 當 audit class；
  例如 flash label 的通過不能宣稱目標辨識任務正確。沒有強制 fallback 或無 label 來刷通過。
- Assistant 既有案例驗真實 tool→視窗→取消回傳與不改資料；沒有本輪完整成功匯入／模型決策證據。

## 執行結果與重現入口

診斷 script 與 JUnit 均在 `build/bids-audit/`，不是產品執行入口。
Native 驗證由 `prlimit --core=0`／timeout wrapper 啟動；這不表示已驗證 Windows 系統
crash-dump 策略。未平行啟動多個重型 native suite。

| 檢查 | 結果 | 證據與限制 |
| --- | --- | --- |
| BIDS focused unit | 168 passed | `unit-bids.xml`；含 index、catalog、channels、timeline、montage、import boundaries |
| 實際資料 IO，junction fixture path | 28 passed、2 failed、8 skipped | `integration-io.xml`；兩個失敗已分別歸因，不能抹除 |
| canonical fixture 路徑 IO 重跑 | 30 passed、8 skipped | `integration-io-canonical.xml`；只指定共用 fixture 的實體目錄，不改產品／測試斷言 |
| Windows native BIDS wizard／Assistant cancel | 11 passed、13 deselected | `native-bids.xml`；只選本輪 BIDS／Assistant cancel，原生自動化不等於真人驗收 |
| D15 每 root 一個 recording＋fresh recipe | 15 passed，0 timeout | `d15-retained-20261020/case-*-result.json`；不是 134-case conformance |
| 特殊條件重現 | 已重現以上發現 | 主 agent 重跑語意／取消／繼承探針，並交叉核對 reviewer 的來源證據 |

8 個 IO skips 原因：缺少 OpenNeuro sub-002／003 optional multisubject fixtures（7），
以及其 CTF montage 路徑（1）。未下載補齊，不計通過。

`run_fixture_checks.py io`／`run_fixture_checks.py native` 只在本機 diagnostic runner 指向
既有 public fixture 的 canonical 目錄，保持產品 import 指向 audit worktree。
原 junction 失敗與初版探針錯誤均保留；不能以重跑通過否認前述 alias 問題。

D15 合計檢查 40,235 個 event/class tuples、5,083,100 個時間 samples（不乘通道數）。
15 個 selected recordings 初次及重播的完整 waveform 最大絕對誤差皆為 0，已綁定輸入
hash 前後一致。波形對照共用 MNE reader；header 形狀與 event/channel oracle 則獨立讀取來源。
這不排除兩側共用 reader 的缺陷。Chen 出現估計頭半徑 11.5 cm 警告，未認證 montage
幾何正確性。15 cases 合計 117.110 秒，最慢 Thielen 44.672 秒，不是效能 benchmark。

D15 初次啟動因 Windows Git 無法讀取 WSL worktree pointer，尚未執行 case 即失敗；
保留 `run.log`。重跑明確傳入 WSL Git 讀出的上述 SHA，並核對產品 module path，
結果在 `run-attempt2.log`。沒有把 preflight 失敗當產品 case，也沒有新增資料 fallback。

主 agent 已核對實際 JSON／JUnit／diff，不只採用 reviewer 摘要。兩位獨立 reviewer 分別
覆核資料語意及 lifecycle／test 邊界，要求的來源定位、取消窗口及 alias 描述已修正。
這是報告結論的覆核通過，不是產品缺陷已修復。

## 後續修復邊界

建議一個有明確終點的 BIDS 修復階段：先處理靜默 metadata 遺漏，其次取消／recipe／validation
一致性，再補 JSON suggestion／Command alias 的明確邊界。沿用現有 index、review、
recipe 與 ApplicationService owners，不另建控制層，不按特定 MOABB 名稱加分支。

每項修正先加入會抓到上述真實失敗的測試；最後在同一版本重跑 focused、source-diverse 與
Windows native journey，再交使用者一次集中手測。繼承支援策略與可見訊息改動先確認。

E 槽恢復後才可完成 canonical 134／expanded retained 檢查。本報告不等於全資料庫重認證、
產品 handoff-ready、手測通過或合併批准。
