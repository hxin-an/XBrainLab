# XBrainLab Validation Contract

最後更新：`2026-08-15`

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

## Handoff gates

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

## Claim boundaries

- Format coverage不等於dataset diversity。
- Import成功不等於label semantics、split independence、model quality或saliency validity。
- Cross-fold Summary只對backend證明可pool的disjoint test masks成立。
- Launcher smoke不等於signed installer。
- Local Granite walkthrough不等於Assistant-ready或thesis benchmark。
- Windows真人驗收不能外推macOS、Linux、其他DPI/driver或其他dataset。

歷史執行細節由Git history保存；active狀態只讀[Current](../current.md)與[Now](../planning/now.md)。
