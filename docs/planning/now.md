# XBrainLab Now

最後更新：`2026-08-28`

## 目前焦點

本 campaign 從同一個 post-plan `main` 建立隔離 worktree，同步推進四個工作包：Windows產品／WSL開發
Data Import 多 worker、Assistant 多輪補參數與誤呼叫改善、Dataset controller compatibility
cutover，以及全 repo non-UI test quality cleanup。三條產品 lane 與 test cleanup 都必須通過獨立
completion reviewer，全部告一段落後才開始使用者手測。

主 agent 只負責 canonical plan、scope／complexity gate、exact SHA、branch／worktree ownership、
reviewer dispatch、CI／PR、main 同步與手測交付；lane discovery 與施工由 subagent worker 執行。
Worker 不得自行宣稱完成，reviewer finding 也不會自動擴大使用者授權。

## 問題與證據

### Assistant

- 固定 v10 evaluator 的 81-case baseline 已完整執行：core、parameter-origin、missing guard與目前
  precision gate通過，但 production-controller clarification final 為 `0/7`，unexpected unsafe為
  `2`。
- Typed receipt、parameter reply verification與bounded two-reply state已存在；主要斷點是receipt入口
  依賴模型首輪精確輸出typed clarification。模型直接選direct tool但缺少可信參數時，verification
  會拒絕執行，卻不建立可延續的receipt。
- 使用者已批准Host只對模型已選的exact direct tool做deterministic yes/no action-origin proof；Host
  不得從generic文字另選工具。補參數追問保留clarification語意，但視覺使用一般Assistant泡泡，
  不顯示藍色`Needs input`樣式。

### Windows產品／WSL開發 Data Import

- WSL `/mnt/d`量測只能解釋開發環境I/O，不能外推native Windows產品效能；使用者已批准在Windows
  baseline暫時不可得時，將WSL作為candidate-selection development baseline，但改善目標不得是WSL
  特化，相關數字仍不作產品gate。
- 現有Windows Poetry與project venv都指向已移除的Miniconda interpreter；使用者已批准依lockfile建立
  乾淨Windows Python 3.12 project environment並下載／安裝必要dependency。先嘗試恢復native baseline，
  只有安裝或native runner仍不可用時才使用WSL fallback。
- 現有headless runner可在fresh `ApplicationService`上分別量Catalog、Review、Apply、background與
  stable，並保存CPU、RSS、I/O與correctness；native Windows source runtime使用Windows Poetry／
  Python，不使用WSLg launcher作效能證據。
- Review的獨立header/resource inspection與Apply的逐檔raw preparation目前為serial；多檔、私有、
  不碰Study／Qt／publication的工作有bounded thread parallelism潛力。先以Windows、必要時以WSL
  1/2/3-worker與thread-safety evidence選擇平台中立candidate；format enablement與產品claim仍需Windows
  驗證。

### Cleanup

- Dataset product truth已是ApplicationService command與revisioned publication，但Dataset panel、
  sidebar、actions、external label與Data Interpretation coordinators仍保留controller compatibility
  mesh。正常產品多半不走fallback，卻持續造成雙路徑、fixture負擔與接線失敗時的stale-state風險。
- Non-UI tests／test-only helpers／architecture guards與dev test scripts需在施工時做repo-wide inventory；
  目標是處理高價值obsolete、duplicated、mock-only、implementation-detail或高成本重複掃描family，
  不是預先憑行數刪測試。
- Publication renderer的post-budget retry只有在真實callback／close成本達到明定門檻時才改；沒有證據
  不建立微小PR，也不把「量過但沒改」算成cleanup完成。

## 預期 outcome

1. Assistant：模型選定exact direct tool後，Host能安全建立並延續typed receipt；中英文第二／三輪
   補值可執行既有tool，clarification至少`6/7`，unexpected unsafe最多`1`，其餘v10 gate不退步。
2. Import：先重建native Windows環境，仍不可得時以WSL 1/2/3-worker development evidence選出平台
   中立的bounded parallel preparation；candidate需同時改善blocking median至少`15%`與`0.5s`，
   且資料、安全、順序與rollback contract不退步。Windows重跑通過前不宣稱產品效能達標。
3. Dataset cleanup：Dataset production package不再呼叫controller compatibility gateway；正常layout、
   文案與操作不變，缺少／stale publication時fail closed，production LOC淨減少且owner不增加。
4. Non-UI tests：完成repo-wide inventory並處理所有in-scope高價值family；重要side effect保留至少一條
   lower-mock path，可信度、維護量或執行成本有可量改善。

## Scope、non-goals與UI確認

### Assistant lane — `fix/assistant-effect-iteration-v2`

- 可改現有verifier、tool-attempt admission、controller receipt continuity、prompt/examples與chat
  clarification presentation；不新增public tool、semantic router、owner或state machine。
- Action-origin verifier只接收模型已選tool與latest user text，只能回傳proof／reject；generic、否定、
  解釋、多action與歷史模糊指涉deny by default。
- Receipt只保存同一tool、backend generation、schema required fields與使用者文字可證明的值；stale、
  cancel、different tool或budget exhaustion全部清除。
- UI確認已取得：clarification使用一般Assistant泡泡，不顯示特殊藍色標籤／卡片；其他Chat UI不改。

### Import lane — `perf/windows-import-parallel-v1`

- 產品效能claim只接受Windows-native Poetry／Python、本機NTFS、同source／selection／protocol evidence。
- Candidate selection優先使用重建後的Windows environment；若native measurement仍不可用，可使用既有
  WSL environment作development baseline與1/2/3-worker比較，但不得加入mount／filesystem／WSL特判，
  也不得用其結果批准產品merge。
- 比較1/2/3 threads；Review worker只回傳immutable header/resource result，Apply worker只建立私有
  loader／Raw result，主thread保序組裝、套用metadata／labels與commit。
- 最終採用通過安全gate且在最快valid candidate `5%`內的最小worker數，不新增使用者setting。
- 只對有native fixture與thread-safety證據的format啟用；其餘維持serial。Concurrency resource
  preflight必須納入峰值記憶體。
- 已授權依lockfile下載／安裝native Windows project dependency；不得下載新dataset、任意升級dependency
  或修改產品dependency contract。不新增WSL／mount特判、ext4 staging、durable cache。Final full
  original-source rehash、SourceFileBoundary、selected scope、reparse／symlink／containment與atomic rollback
  必須保留。

### Dataset cleanup lane — `refactor/dataset-compatibility-cutover-v1`

- 移除external-label controller target fallback、UI direct loader mutation、Dataset render/sidebar/channel
  controller reads與Data Interpretation synchronous compatibility admission。
- Shared compatibility gateway保留給其他subsystem；這次只要求Dataset package caller清零。
- UI確認已取得：可改Dataset內部接線；正常layout、copy、互動與流程不得改變。Missing runtime改走既有
  unavailable／blocked語意，不建立新visible state。

### Non-UI test lane — `test/non-ui-quality-cleanup-v1`

- Inventory涵蓋全repo non-UI tests、test-only helpers、architecture guards與dev test scripts；UI tests
  排除。Active product-lane tests由原worker擁有，test reviewer finding退回原worker，避免branch重疊。
- 只處理有真實contract對照的obsolete／duplicate／mock-only／implementation-detail／high-cost family；
  弱測試先以最小behavior／state-transition／real-side-effect coverage替換再刪除。
- 不移除data safety、receipt、source replacement、Windows boundary、privacy或真實side-effect evidence；
  不建立新test control plane、manifest或逐helper source guard。

### Campaign non-goals

- 不新增模型、下載dataset、任意升級dependency、修改public tool contract、處理其他UI redesign或恢復
  retired compatibility／MCP surfaces；唯一dependency下載授權是依lockfile建立native Windows project
  environment。
- 不stage、revert、覆寫或隱藏root `settings.json`；不清除model cache、dataset或非明確XBrainLab-owned
  artifacts。

## Agent拓樸與持續推進

1. Plan PR合併後，三名worker從同一post-plan `main`平行啟動Assistant、Import、Dataset worktree。
2. 任一worker完成candidate即釋放slot；reviewer優先於新工作。Reviewer完成或退回rework後，有空slot
   立即啟動Non-UI Test worker。
3. 固定流程為`baseline -> candidate -> worker evidence -> independent review`：
   - `rework`：列出對應acceptance的缺口，退回原worker，新SHA由同一reviewer重審。
   - `scope blocked`：主agent保留該lane，其他lane繼續；只有需要新授權才詢問使用者。
   - `complete`：reviewer綁定exact SHA，主agent再做cross-lane gate。
4. Assistant依序由tool-call reviewer與test-quality／UI reviewer審查；Import由performance/resource與
   data-boundary reviewer審查；Dataset由architecture/code與UI product reviewer審查；Non-UI tests由
   test-quality reviewer審查。不同reviewer不重複同一維度。
5. Worker不能自行宣稱完成；非直接blocker最多三項follow-up，不擴大本campaign。

## Focused validation與stop condition

### Assistant

- 先跑model-free verifier/coordinator/controller與中英文trajectory tests，再跑固定v10完整81-case。
- Gate：既有core／origin／missing／precision gates不退、clarification `>=6/7`、unexpected unsafe
  `<=1`；raw model、Host recovery與final outcome仍分開報告。
- 若所有已授權admission、receipt與bounded prompt interventions均完成仍未達gate，reviewer必須證明
  下一步需要semantic router、新模型或public contract，才能標記evidence-complete checkpoint。

### Import

- 先依lockfile建立Windows Python 3.12 project environment；Windows baseline與candidate各使用fresh
  native process、相同fixture／mount／selection，至少三組交錯可比pass。若native measurement仍不可得，
  WSL baseline／candidate使用同一既有environment、fixture／mount／selection與相同pass規則；兩者都保存
  raw phase timings、CPU、RSS、I/O與correctness。
- Development candidate gate：end-to-end median同時改善`>=15%`與`>=0.5s`；未改phase不得有可重現
  退化，event digest、labels、recipe、input order與no-partial-state全部一致。WSL通過只允許進入candidate
  review，不構成Windows產品claim或merge acceptance。
- Windows product gate在Import手測／merge前以同protocol重跑，並同樣滿足`>=15%`與`>=0.5s`；format
  thread-safety與resource preflight也必須在Windows成立。
- 若1/2/3 workers與Review／Apply兩個安全平行區域都未通過，performance reviewer確認in-scope候選
  已耗盡後才可checkpoint；不得轉做WSL特化或cache。若只有Windows環境仍不可得，保留平台中立candidate
  與WSL development evidence，明確標記Windows acceptance pending。

### Dataset cleanup

- Publication retry只在正常旅程出現至少10次／5秒post-budget callback，或forced defer造成至少
  `250ms` median close延遲時修改；候選需移除至少90% post-budget callbacks並保留newest revision與
  teardown contract。
- Focused Dataset command/publication/label/channel/import tests、architecture guard、UI screenshot／
  walkthrough與Windows native流程必須通過；Dataset compatibility caller inventory為零。

### Non-UI tests

- Reviewer必須確認repo-wide inventory完成、所有已知in-scope高價值family已處理、重要side effect
  仍有lower-mock evidence，且可信度／維護量／執行成本至少一項有可量改善。
- Pure tests／test-only PR可依repo豁免human manual；必要時依coherent contract拆PR，不為每個小刪除
  建短PR。

## 手測、合併與收尾

1. Non-UI test PR在independent review與所有applicable CI成功後先合併；三條產品branch同步最新main
   並重跑受影響gate。
2. 只有四個工作包都達到review-complete candidate或reviewer證明的evidence-complete checkpoint後，
   才開始使用者handoff；施工中不要求半成品手測。
3. Product手測／merge順序：Dataset Windows walkthrough → merge；Import同步main、重跑Windows benchmark
   與data gates、手測 → merge；Assistant同步main、重跑v10與CI、Windows聊天／tool-call手測 → merge。
4. 每個PR base／head、CI與non-skipped checks必須精確成功；product behavior只有使用者對同一SHA明確
   表示手測通過並同意merge後才能合併，source變更即失效。
5. Campaign完成後移除active slice，只校準真正改變的current truth／decision／evidence contract；清除
   task worktrees、local／remote branches與明確owned temp artifacts，確認`main`是唯一產品基線並保留
   使用者root `settings.json`。
