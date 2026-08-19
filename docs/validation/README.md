# XBrainLab Validation Contract

最後更新：`2026-08-18`

驗證回答「哪個exact source，在什麼環境，觀察到什麼」，不能把單一PASS放大成產品、科學或真人
驗收結論。Executable handoff gate的ID、順序、argv、timeout與artifact contract只以
`scripts/dev/handoff_gate_spec.py`為準，並由canonical runner執行。

## Evidence levels

| Level | 支撐 | 不支撐 |
| --- | --- | --- |
| Unit/source guard | Bounded behavior或穩定靜態規則。 | 完整workflow、native UI、real dataset diversity。 |
| Integration | ApplicationService/domain/UI元件間的state transition。 | Windows真人操作或科學品質。 |
| Source-diverse data gate | 代表性來源的import/label/epoch/training contract。 | 所有格式、所有dataset或full BIDS compliance。 |
| Automated UI artifact | Exact-source layout、visible state與interaction。 | Native Windows DPI、多螢幕與真人usability。 |
| Handoff dossier | 同一clean/explained pushed SHA的完整工程證據。 | 使用者manual acceptance、signed installer或scientific certification。 |
| Manual acceptance | 使用者在指定產品source上完成實際操作並同意merge。 | 未測平台、未測資料集或後續改動的source。 |

## Exact-source requirements

Final evidence至少記錄branch、full commit SHA、HEAD tree、dirty state、protected local paths、source
fingerprint、command、return status、duration、timeout、skips與artifact hashes。只有repo-root
`settings.json`可作為未stage的protected local例外。

不同SHA、dirty source、舊branch、reduced denominator、stale cache或手動加總的結果只能稱
checkpoint。Dashboard是summary，不是dossier。

## Artifact locations

- Development output：ignored `build/dev-artifacts/<family>/`。
- Final handoff：ignored `build/handoff-evidence/<full-SHA>/`。
- Approved visual regression references：`tests/baselines/ui/`。
- `artifacts/`：只保留policy/ignore，不保存current evidence。

UI evidence必須檢查hierarchy、contrast、text fit、primary action、overlap、nested scroll、dialog
geometry、empty/loading/error/blocked state，以及相關width/DPI。主agent必須實際查看畫面。

Visible UI變更的default-scale candidate必須由`capture_ui_baseline.py`產生exact-source manifest並和
approved references比較；CI不得自行更新reference。Layout、theme、font或dialog路徑另跑Windows Qt
platform的100/125/150% app-polish matrix。Linux/WSL offscreen scale不能冒充Windows結果；automated
Windows capture也不取代真人native DPI、多螢幕或remote-desktop acceptance。

## Handoff gates

完整 dossier 由 `scripts/dev/run_handoff_validation_manifest.py` 執行；命令、timeout 與 artifact
policy 只讀 `scripts/dev/handoff_gate_spec.py`。Runner 的 `--model-cache-dir` 與
`--rag-cache-dir` 必須指向 D-mounted local caches，寫入 evidence 的 cache paths 必須 redacted。
Evidence root 預設必須是 repo-contained 且 ignored；只有明確傳入
`--allow-external-evidence-root` 才能使用 external root。

完整 runner 會執行所有註冊 sections；只重跑 sections 3-6 或其他子集 does not run or certify
完整 handoff dossier。Windows automated checks 也不取代 Windows native acceptance。

- Identity/scope：Git branch、HEAD/upstream、worktree inventory、dirty ownership與non-goals。
- Focused protection：bug red/green或refactor characterization。
- Same-class sweep：直接相關call sites與必要source guard。
- User-like happy path與相鄰failure/cancel/retry/stale lifecycle。
- Data/import/epoch/training/evaluation/visualization：canonical source-diverse dataset gate。
- Static quality：Ruff、configured Basedpyright、architecture guards、diff check。
- Docs：canonical truth、link/source audit、developer與user-site strict build。
- Branch/CI：focused commits、pushed exact PR head、所有non-skipped checks completed/success。

任何required gate缺失時只能稱`checkpoint`或`blocked`；所有applicable gates對同一clean/explained
exact commit完成後才可稱`handoff-ready`。

## Manual merge approval

產品runtime、GUI、資料流程或使用者可見行為有變更時，PR必須記錄`Manual acceptance`：日期、
測試範圍、product source identity與使用者明確的手測通過/merge同意。若product source之後改動，
批准失效並回到checkpoint。CI、自動journey與offscreen screenshot不能取代此批准。

純docs、tests、CI或agent-guidance變更若不可能改變產品行為，可不要求manual acceptance。

### Stable Assistant candidate

Assistant candidate必須在同一clean/explained exact source依序閉合下列證據：

1. Unit/integration證明18-tool registry、strict envelope、backend-owned stage、confirmation、GUI
   correlation與no-model diagnostic terminal；mock或manifest-only測試不等於真人workflow。
2. Frozen Granite report固定50 cases：36 positive（18 tools各2）與14 challenge diagnostics。Candidate
   gate要求36/36 positive exact tool＋parameters、其中10/10 direct preprocess通過production
   parameter-origin guard，以及5/5 missing-parameter經同一guard得到零execution與英文追問。其餘9個
   raw challenge必須完整保留為known
   limitations，不計入promotion pass，也不得宣稱raw model已解決。這只支撐bounded selection與該
   deterministic guard，不支撐完整tool execution或產品ready。
3. 真model safe E2E依normal ChatPanel路徑完成Switch Dataset → Import GUI → Select Channels →
   direct Resample；不得用debug transport或fake generator替代。
4. 使用者在同一candidate source完成Complete Workflow、Lifecycle／Navigation、Contract Failures三份
   frontend walkthrough。Import、Channel、Montage、Epoch、Split、Model與Training Settings都必須
   透過真GUI；confirmation/cancel/navigation terminal不可由script預先批准。
5. PR所有applicable non-skipped checks completed/success後，才記錄manual acceptance與merge同意。

#### Assistant manual walkthrough commands

從repo root啟動，每份profile使用fresh process與fresh session；不加`--model`，diagnostic
transport不建立或載入Granite。JSON profile是executable step sequence authority；本節只保存啟動
方式與人工選擇，不複製call list。

Response Presentation：

```bash
poetry run python run.py --tool-debug scripts/dev/agent_tool_walkthrough/response-presentation.json
```

Contract Failures：

```bash
poetry run python run.py --tool-debug scripts/dev/agent_tool_walkthrough/contract-failures.json
```

GUI Cancellation Recovery：

```bash
poetry run python run.py --tool-debug scripts/dev/agent_tool_walkthrough/gui-cancellation.json
```

Complete Workflow：

```bash
poetry run python run.py --tool-debug scripts/dev/agent_tool_walkthrough/complete-workflow.json
```

Lifecycle / Routing：

```bash
poetry run python run.py --tool-debug scripts/dev/agent_tool_walkthrough/lifecycle-routing.json
```

開啟XBrainLab Assistant後，每次只送出目前step一次。Dialog、confirmation、navigation或
training尚未terminal時不送出下一步。Unexpected outcome必須留在同一step；記錄step ID、
可見terminal與screenshot後停止，不繼續污染session。

Complete Workflow使用已provision的
`$XBRAINLAB_DATA_DIR/datasets/public-fixtures/physionet-eegmmidb-S008R04.edf`：

- Import以embedded events將T1對應`left fist`、T2對應`right fist`，排除T0。
- Channel Selection套用一組有效EEG subset，至少保留畫面上的C3、Cz與C4。
- EEG Epoch選T1／T2、`0–2` seconds；Montage選當前可用的standard montage。
- Data Split選Individual／Trial，validation與test皆為`0.2`。
- Model選EEGNet；Training Settings選CPU、1 epoch、batch 8、Adam、learning rate `0.001`。
- 先核准Start Training；若resource preflight另顯示確認，再核准該次receipt，等到training completed。
- 確認Evaluation與Visualization／Saliency Map可開啟；最後核准Compute Saliency，若另有resource
  confirmation則再核准，並等到同一operation顯示`Saliency ready`與腳本`Complete (19/19)`。

任一product source改動都使對應的manual acceptance失效；純docs／tests且不可能改變產品
行為的收尾依本文前述豁免規則處理。

Stage驗收另有一個硬邊界：匯入建立的working raw copy不算preprocessing。只有
`preprocessed.operations`非空（Channel或任一direct preprocess已成功）才可發布`preprocessed`；否則
必須是`data_loaded`並向模型發布Channel與五個direct preprocess工具。

### Staged product rebuild

跨多個bounded slices的產品重建可以先在temporary integration branch組裝，但該branch不是產品
baseline、release source或manual-acceptance對象：

- 每個slice仍需focused evidence、clean/explained source、PR與所有applicable non-skipped checks
  completed/success；integration不能成為較弱CI的避風港。
- Intermediate slice可保留尚未物理刪除但unpublished的migration source；不得同時發布兩套產品
  contract、加入runtime fallback或宣稱handoff-ready。
- Final rollup PR只能聚合已分片審查的commits，不得在rollup新增未審product behavior。其累積diff
  可超過單一slice門檻，但每個原始slice仍受complexity rules約束。
- 使用者只對同步最新main、完整automated evidence已閉合的frozen exact head進行manual
  acceptance。Head或合併基線改變時，必須重新建立candidate並重新取得適用的手測批准。
- Final main merge仍須精確核對base／head、CI及manual acceptance；integration內部成功不能替代。
- 合併後刪除temporary branch與其CI routing；rollback使用PR revert final merge，不保留隱藏雙路徑。

## Claim boundaries

- Format coverage不等於dataset diversity。
- Import成功不等於label semantics、split independence、model quality或saliency validity。
- Cross-fold Summary只對backend證明可pool的disjoint test masks成立。
- Launcher smoke不等於signed installer。
- Local Granite walkthrough不等於Assistant-ready或thesis benchmark。
- Windows真人驗收不能外推macOS、Linux、其他DPI/driver或其他dataset。

歷史執行細節由Git history保存；active狀態只讀[Current](../current.md)與[Now](../planning/now.md)。
