# XBrainLab Now

最後更新：`2026-08-21`

## 目前焦點

CI reliability branch 已在 PR #44 的 exact head
`a679f1417649f4266a2af84809684e40b2109293` 完成所有 applicable non-skipped checks，使用者於
`2026-08-21` 回報 Windows 與 Linux 真人手測正常，並以 merge commit
`8d8dcf6030d0b4bd79783b3a086e1efa101d0cd2` 合併至 `main`。

目前唯一 active slice 是 branch `feature/braindecode-full-catalog-v1`：固定 Braindecode `1.6.1`
的完整模型目錄，以 upstream Braindecode 作正常 provider，將逐檔確認可重散布的模型碼移入
XBrainLab 作 provider unavailable 時才顯示的本地 recovery／legacy catalog，並把現行 13 項的
Model Selection combo 改為可搜尋、可理解 unavailable reason 的完整目錄。

使用者已明確確認：

- upstream 與 legacy 使用不同 stable ID，禁止 silent fallback；
- 所有 upstream model contracts 都可搜尋，不符合目前產品能力者 disabled 並顯示原因；
- legacy 正常時隱藏，只有 upstream provider unavailable 時才顯示；
- legacy source包含逐檔確認的 BSD-3-Clause、MIT、Apache-2.0 code，保留 notices；
- 授權本 slice 使用單一 branch／單一超大型 PR、多個可回退 commit，並對約 `35,000+`
  production LOC 明確例外；所有 commit 完成及 final evidence閉合後才交付一次手測。

Data Import 與 4B Assistant 模型不在本 slice。

施工 checkpoint：catalog／provider chain至`627c5492`已由獨立gate確認無blocker／major；metadata
discovery保持barrel-free，只有checked provider status能啟用projection。`f27eabfa`已鎖定61-symbol逐檔
provenance、hash、license與excluded set。第一個baseline convolution family已完成private namespace、minimal
no-Hub base、逐symbol support provenance與六個model的strict state-dict／deterministic output parity；獨立
gate要求移除未使用的support symbols後已收斂到18個實際primitive，並新增restricted／unrelated source guard。
`861ce481`的複核已PASS。Sleep／temporal family再加入7個models與3個實際support primitives；每個model
已完成upstream strict state-dict／deterministic output parity，兩個代表完成finite backward，且`2fa43d1c`
獨立gate已PASS。Filter-bank family目前加入FBCNet、FBMSNet、FBLightConvNet與IFNet；mixed-license
`filter.py`只摘取BSD的`FilterBankLayer`，未帶入`GeneralizedGaussianFilter`，IFNet另保留MIT notice。
四個model皆完成strict state-dict／deterministic output parity，FBCNet／IFNet完成finite backward；catalog、
provenance與三個family的focused驗證為55 passed，且`09f5482b`獨立gate已PASS。Convolutional／TCN
family目前再加入EEGInceptionMI、EEGITNet、EEGTCNet、EEGSimpleConv、SPARCNet、ContraWR、TSception、
SyncNet、SincShallowNet與SSTDPN；十個model皆完成strict state-dict／deterministic output parity，三個代表
完成finite backward，新增support只限MaxNorm與MaxNormLinear，且`f183d0de`獨立gate已PASS。下一個
bounded family為attention／transformer；STEEGFormer的upstream Hub channel-index下載不會移入legacy，
legacy contract改為使用者顯式提供index或在無channel metadata時沿用identity mapping，禁止網路fallback。
本family現已加入ATCNet、AttentionBaseNet、CTNet、EEGConformer、MEDFormer、MSVTNet、MVPFormer、
PBT、STEEGFormer與TCFormer；10個model皆完成strict state-dict／deterministic output parity，三個代表完成
finite backward。Support closure只新增12個實際attention primitives、PatchTokenizer、FeedForwardBlock、
DropPath、Conv1dWithConstraint與6個直接所需functional symbols；STEEGFormer的Hub lookup已刪除並有
fail-closed regression。六個family加provenance focused suite為58 passed，Ruff／format／basedpyright皆通過，
`c71e5266`的獨立gate指出STEEGFormer仍保留Hub loader surface；`0f1cf3c9`已刪除相關文件、
`_hub_mixin_config`與`from_pretrained`語意，擴充source guard後re-gate PASS。Attention／transformer family
正式關閉。Foundation core／interpolated family目前加入EEGPT、BIOT、BENDR及其三個Interpolated variants；
support closure只新增`InterpolatedModel`與`ChannelInterpolationLayer`所需的6個實際symbols，三個model的
remote loader文件與surface均未移入。六個contracts完成upstream strict state-dict／deterministic output
parity，三個base model完成finite backward；全部既有legacy family加provenance focused suite為68 passed，
Ruff／format／basedpyright皆通過，`61735254`獨立gate已PASS。Foundation leaf family目前再加入
CBraMod、CodeBrain、DGCNN與EEGDINO；support只擴充直接需要的
`CrissCrossTransformerEncoderLayer`與`extract_channel_locations_from_chs_info`，四個model的remote
loader文件與surface均未移入。四個contracts完成upstream strict state-dict／deterministic output parity及
finite backward；全部既有legacy family加provenance focused suite為77 passed，Ruff／format／
basedpyright皆通過，`84d64ff9`獨立gate已PASS。LaBraM／EEGSym family目前再加入Labram、
InterpolatedLaBraM與EEGSym；support只擴充直接需要的MLP、parameter rescale與兩個hemisphere channel
helpers，remote loader文件與surface均未移入。三個contracts完成upstream strict state-dict／deterministic
output parity，Labram／EEGSym完成finite backward；全部既有legacy family加provenance focused suite為
83 passed，Ruff／format／basedpyright皆通過，`8190155d`獨立gate已PASS。SignalJEPA／LUNA family
目前加入SignalJEPA、InterpolatedSignalJEPA、三個classification variants與LUNA；兩個source只依賴
local legacy base／modules，Hub／download文件與可執行loader surface均未移入。六個contracts完成upstream
strict state-dict／deterministic output parity，SignalJEPA／LUNA完成finite backward；全部既有legacy family
加provenance focused suite為92 passed，Ruff／format／basedpyright皆通過，`c0d045b3`獨立gate已PASS。
最後一個REVE family目前已移入其BSD model source，但刪除position-bank HTTP／cache／JSON loader與
remote pretrained surface；legacy forward只接受caller明確提供的`pos`，channel-name lookup在沒有local
position data時fail closed。REVE完成upstream strict state-dict／deterministic output parity與finite backward；
全部既有legacy family加provenance focused suite為96 passed，Ruff／format／basedpyright皆通過，
`fe4b3959`獨立gate已PASS；57個permissive contracts的legacy vendoring正式關閉，四個restricted contracts
只保留metadata。Admission第一個checkpoint目前已建立provider-aware projection：healthy時顯示完整61個
upstream contracts，provider unavailable時改列57個distinct `legacy.braindecode.*` recovery IDs，且explicit
legacy ID在healthy環境仍可解析但不會顯示整份legacy catalog。Catalog factory只傳model宣告的signal context，
Epochs補上detached `chs_info`，TrainingService拒絕disabled contract並把provider／revision寫入ModelHolder；
相關catalog、training service、epochs focused suite為422 passed。下一步是提交本checkpoint並取得同一獨立gate
複核；`0f2d04ac`已關閉legacy alias與舊dialog projection findings，re-gate PASS。Artifact identity checkpoint
目前把exact model ID／provider／source revision寫入ModelHolder、每個新TrainingRecord與saliency producer
fingerprint；同目錄checkpoint／evaluation records因此由training record identity約束，upstream artifact用
legacy identity重開會fail closed，舊artifact缺identity時不會被補寫或冒充某個provider。相關focused suite為
108 passed；malformed identity也會在任何record mutation／evaluation load前以typed error fail closed，
`168dd127`獨立gate已PASS。Model Selection search cutover目前已完成可搜尋result list、name／ID／alias／
family／task filter、disabled reason、no-match、keyboard、selection preservation與provider recovery presentation；
provider true import preflight在Python-owned background thread執行，Matplotlib style side effect由既有lock＋
`rc_context`隔離。Healthy projection顯示61 upstream＋3 local，missing／broken provider顯示57 distinct recovery＋
3 local；找不到原ID時Confirm保持disabled，不替使用者選另一個identity。Catalog＋UI focused suite為52 passed，
focused offscreen screenshot亦已人工檢視。`5cd736a3`的獨立gate發現Enter可繞過hidden／no-match selection；
目前已讓keyboard與`accept()`共用visible＋enabled＋Confirm guard，並以no-match及hidden-selection兩條red→green
regression關閉，UI focused suite為23 passed；`5b6b4016` re-gate已PASS。UI checkpoint正式關閉。下一步進入
全部selectable models的catalog construction／forward與family workflow matrix，不提前執行full handoff。

Model matrix第一輪bounded diagnostic已完成且不重跑：目前static catalog的54個selectable upstream contracts，
在22-channel／512-sample且無montage context有43個產生finite logits；在22-channel／256-sample且有標準10–20
montage context有47個產生finite logits。失敗不是單一factory defect，而是可靜態描述的signal contract：
interpolated／DGCNN／SignalJEPA contextual需要finite electrode positions；SleepStagerBlanco2020與AttnSleep
需要較長sleep windows，AttnSleep另有原始100／125 Hz window contract；Labram需要原始128-channel order及
200-sample patch divisibility，InterpolatedLaBraM需要montage及相同divisibility；LUNA／CBraMod分別需要40／
200-sample patch divisibility；EEGDINO目前最多19 channels。下一個coherent change會在既有ModelCatalog加入
pure dataset-context availability projection，Model Selection只從`controller.get_epoch_data().get_model_args()`
取得detached snapshot，TrainingCommandService在configure時用同一projection重新admit。禁止UI自行推導、
禁止trial construction決定availability、禁止遇到constructor error後fallback。Focused tests要證明各條件的
allow／block、UI reason、UI與command一致及每個enabled contract的bounded construction／finite forward。
目前pure projection與兩個consumer已完成：interpolated／DGCNN／SignalJEPA contextual會要求reviewed finite
positions；SleepStagerBlanco2020要求至少450 samples且預設group-compatible channel count；AttnSleep只接受
single-channel 30-second 100／125 Hz contract，125 Hz由同一adapter固定其documented `d_model=100`；Labram
要求canonical 128-channel order與200-sample divisibility，InterpolatedLaBraM／LUNA／CBraMod分別檢查其
200／40／200 patch contract，EEGDINO限制最多19 channels。Upstream與legacy recovery共用判定；UI只顯示
reason，TrainingCommandService在任何configuration mutation前重新讀Epochs model args並fail closed。三個
focused files目前127 passed，Ruff／format／basedpyright通過。下一步為提交本checkpoint、獨立gate複核，
之後才建立compatible-context construction／finite-forward matrix；不再執行前述兩個diagnostic矩陣。
`a44918a7`獨立gate已PASS。Model matrix下一個slice不新增runner或availability owner：47個一般contract沿用
22-channel／256-sample／standard montage context；七個特殊contract分別使用Blanco 512 samples、AttnSleep
single-channel 3000 samples at 100 Hz、Labram canonical 128-channel／400 samples、InterpolatedLaBraM
22-channel／400 samples、LUNA 22-channel／280 samples、CBraMod 22-channel／400 samples及EEGDINO
19-channel／256 samples。每個static-eligible upstream ID必須由同一catalog projection判為available，以產品
factory與default params產生`(1, 4)`finite logits及至少一個finite gradient；不量scientific accuracy、不以
construction結果回寫availability。Focused evidence是一個獨立integration matrix，任一model失敗即停在該
contract修復，不重跑整個舊diagnostic矩陣。
第一輪完整matrix已一次通過：54個static-eligible upstream IDs全數由產品factory產生`(1, 4)`finite logits
與finite gradient，inventory case合計55 passed／15.25 seconds。Run同時暴露STEEGFormer沒有收到既有
`chs_info`後仍嘗試從Hub下載channel vocabulary並在離線時退回identity mapping；產品從零訓練而不載入
預訓練embedding，因此同一既有adapter明確傳入deterministic local `chan_pos_idx=range(n_chans)`，不新增
optional-input abstraction、不觸發網路、也不假裝具有預訓練montage alignment。以單一factory regression
及該model matrix selector驗證，不重跑54-model matrix。Focused STEEGFormer regression為2 passed／
4.52 seconds，原Hub vocabulary／identity-fallback warning已消失；Ruff／format／basedpyright通過。
`48a031a9`獨立gate已PASS。下一個workflow checkpoint不重跑54-model construction matrix，也不新增
training／artifact／saliency owner：以六個catalog family的代表`EEGNet`（Convolutional）、`EEGConformer`
（Attention）、`FBCNet`（Filter bank）、`BIOT`（Foundation）、`DGCNN`（Graph）及`DeepSleepNet`
（Sleep），在同一真實MNE-backed 22-channel／256-sample兩類Dataset上，各走CPU one epoch。每一case必須
由checked catalog取得factory與exact provider identity、產生selected validation checkpoint、完成test
evaluation、寫出safe record／EvalRecord／model-state artifacts，並用artifact reader strict-load至fresh同ID model。
每一family另只算`Gradient` saliency並驗證finite attribution及producer identity；不跑SmoothGrad family、
不比較scientific metrics。先以EEGNet單一selector打通harness；任何產品contract不相容即停在該family修正，
不把測試改成mock trainer／mock persistence。
Workflow matrix已完成：EEGNet先以單一case通過；其餘family第一次執行時DGCNN正確拒絕只有MNE Info、
但尚未commit到`Epochs.channel_position`的montage，確認是test harness沒有走產品reviewed-montage state而非
model defect。Harness改用`Epochs.set_channels()`正式套用同一standard montage後，六個family整檔一次通過
（6 passed／9.88 seconds）。每例均使用真Trainer、真safe artifact IO、fresh strict-load、test evaluation及
Gradient saliency；未patch persistence或model owner。下一步提交checkpoint並由同一獨立gate複核；不再重跑
此workflow matrix，除非相關training／artifact／saliency source再變。
`e34d2c81`獨立gate已PASS。Platform checkpoint只重用既有`platform-product-lifecycle` registry：Windows
執行54個selectable upstream models的bounded construction／forward／gradient matrix；macOS在同一test module
只執行六個family representatives，Linux authoritative integration仍執行完整54個。這不新增CI job、runner或
timeout，不把macOS best-effort升格為真人desktop claim；focused validation只跑runner contract與本機Linux
collection/cardinality，不在本機重跑model matrix。Registry／Windows-full／macOS-family policy focused
tests為5 passed；Linux collection保留54個model execution cases（另含3個inventory／platform policy cases），
Ruff／format通過，basedpyright只有既有PyYAML source-resolution warning。

## 問題與證據

- Current catalog只手工發布10個`braindecode.*`模型與3個`xbrainlab.*`本地模型；Braindecode 1.6.1
  自己維護61個model construction contracts。原本QComboBox無法清楚呈現數十個model、task、provider
  與unavailable reason。
- Current factory以`import braindecode.models`載入整個barrel。目錄取得、UI startup與model execution
  沒有分離，barrel也會接觸未選用的model/module和額外import side effects。
- Braindecode 1.6.1 `models/`約33,020 LOC。直接可辨識的source licenses包括BSD-3-Clause、MIT、
  Apache-2.0及至少四個CC BY-NC model；package NOTICE沒有完整列出所有檔案級例外，不能把整個package
  或NOTICE視為單一授權。
- 明確不得移入可發布legacy namespace的model為`EEGMiner`、`MetaNeuromotorHand`、
  `EMG2QwertyNet`、`BrainModule`；`GeneralizedGaussianFilter`另有CC BY-NC與專利
  `GB2609265`聲明。Mixed module只能摘取已確認permissive symbol。
- Braindecode包含一般classification、sleep、foundation／pretrained、interpolated及非classification
  output contracts。Current Trainer預期class logits；「在上游存在」不等於「可由目前supervised
  classification workflow執行」。
- Current`ModelSpec`只表達ID、顯示名、source、factory及少量手工參數；`model_requirements.py`只精確
  描述三個XBrainLab local model。UI、capability、training、checkpoint和saliency尚未共享完整provider／
  task／input／revision contract。

## Observable outcome

1. Catalog以checked-in Braindecode 1.6.1 metadata列出61個model contracts；目錄與搜尋不import
   `braindecode.models` barrel。所有ID唯一，default仍為`braindecode.eegnet`，既有10個upstream ID和
   三個`xbrainlab.*`語意不變。
2. Upstream IDs使用`braindecode.<model>`；本地副本使用`legacy.braindecode.<model>`；既有
   `xbrainlab.*`仍代表原本XBrainLab implementations。Training artifact、checkpoint、evaluation與
   saliency provenance記錄exact model ID、provider及source revision。
3. `ModelSpec`／catalog projection能表達provider、revision、family、task、aliases、license class、
   input requirements、parameter schema、static／dataset-scoped availability及user-safe disabled reason。
4. 每個與current supervised classification workflow相容的upstream model在本slice完成adapter後才可選；
   non-classification、license-restricted、需要未支援modality或external pretrained resource者disabled。
   `adapter not implemented`不是final candidate可接受的disabled reason。
5. Upstream provider正常時Model Selection只顯示upstream catalog。Package不存在、版本不是1.6.1或
   provider preflight失敗時，dialog顯示明確banner並改列可用legacy models；不自動改變已選ID、不執行
   自動fallback。單一model的shape、parameter、checkpoint或training failure必須保留真正typed error。
6. Model Selection使用搜尋欄與可捲動結果列表，支援name、stable ID、alias、family與task；disabled row
   顯示reason且不能Confirm。Keyboard、clear、no-match、cancel、selection preservation、narrow width及
   Windows 100／125／150% DPI均有明確行為。
7. Legacy namespace只含逐檔／逐symbol確認的BSD-3-Clause、MIT、Apache-2.0 closure，保留copyright、
   license notice、Braindecode version、upstream path與hash；不得import installed Braindecode作隱藏依賴，
   不含CC BY-NC／patent code，也不silent下載weights。
8. Final exact head在Windows與Linux完成automated evidence後才交使用者手測；source再變即撤銷批准。

## Scope／non-goals與complexity review

- In scope：model catalog／factory／requirements、training model identity、permissive vendored model closure、
  Model Selection UI、直接必要的checkpoint／evaluation／saliency provenance、tests、CI selectors與canonical
  truth。
- Non-goals：Data Import、4B Assistant model、Trainer task-generalization、非classification trainer、遠端
  pretrained model下載、installer／signing、Braindecode版本升級、scientific accuracy claim。
- User-visible UI modification authorization：已確認。核准範圍只限Model Selection搜尋、result list、
  unavailable state與provider recovery presentation；不重新設計Training其他頁面。
- Owners before／after：`ModelCatalog`仍是唯一model discovery／identity／factory／availability owner；
  `ApplicationService／TrainingCommandService`仍是configure／admission owner；UI只render catalog projection；
  checkpoint／evaluation／saliency各自既有owner不變。Owner count不增加。
- Explicit exception：預估legacy model sources約29k permissive model LOC，加精準support closure、adapters、
  catalog與UI後約`35k–40k`production LOC，遠超normal 1,500 LOC ceiling。使用者核准單一超大型PR；施工仍
  必須以family commits、focused evidence和per-commit rollback控制風險。
- Deletion candidates：現行10-model `_BRAINCDECODE_MODELS`手工tuple、broad barrel factory、QComboBox-only
  selector、依model name token判斷的零散requirements、只為barrel side effect存在的workaround。Braindecode
  dependency保留，因它是primary provider。

## 施工順序

### A. Catalog／license／provider contract

1. 建立exact 1.6.1 model inventory和per-file／per-symbol provenance manifest；61個contracts逐一標記task、
   family、constructor context、license、primary module與產品eligibility。Ambiguous source先blocked，不猜。
2. 先加passing characterization：既有10個ID/default、三個local names、lazy startup、ModelHolder／artifact
   identity及current dialog selection。新增target contract tests需先red於完整membership／search／recovery。
3. 擴充immutable`ModelSpec`和catalog projection；用explicit module/class metadata建upstream factories，
   移除目錄enumeration對barrel import的依賴。Provider preflight只判斷package／exact version／bounded
   provider load，不把model-specific execution error誤判成provider outage。

### B. Legacy permissive closure

1. 建立private legacy namespace與third-party notices。Common base／functional／modules只保留實際model
   callers；mixed-license files按symbol拆分，不copy barrels、Hub publishing、datasets或skorch trainer。
2. 依dependency family分commit移入：baseline convolution、sleep／temporal、filter-bank、inception／TCN、
   attention／transformer、foundation／interpolated。每個commit列新增source、license、direct dependencies、
   parity models與rollback path。
3. Legacy imports只能指向XBrainLab legacy namespace或XBrainLab明確direct dependencies。若Braindecode
   package移除後legacy import失敗，該family不得完成。
4. Restricted models只保留upstream disabled metadata；不得為達membership而移入source。

### C. Admission／artifact與UI

1. 將signal context映射、minimum samples、chs_info／montage、sfreq／n_times、task output與pretrained
   resource requirement集中成catalog-owned pure adapters；UI與TrainingService使用相同結果。
2. Provider與source revision寫入ModelHolder、training plan／record及saliency producer identity。舊
   `braindecode.*` state dict只由同ID upstream factory strict-load；legacy ID沒有silent migration。
3. 以搜尋欄＋result model／list取代combo。Upstream healthy只顯示upstream；provider unavailable時顯示
   recovery banner和legacy results。若current persisted selection本來就是legacy ID，resolver仍可執行，
   但healthy catalog不因此顯示整份legacy list。
4. Selection、search query與provider status不得建立第二份catalog；UI只持有detached projection和目前
   selection。Cancel不mutation；no-match／disabled不能Confirm。

### D. Candidate與merge

1. 每個meaningful commit後只跑family-focused tests，由最多一個獨立subagent gate審architecture／license／
   test evidence；blocker／major以後續commit關閉後才進下一family。
2. 中途不反覆跑complete regression或canonical handoff。所有family、UI、artifact與source guards完成後
   freeze branch，執行一次full handoff、push exact head並等待remote current-head CI。
3. 產生exact-source UI screenshots／walkthrough與Windows操作清單；使用者手測通過並明確同意merge後才
   merge。任何product source改動都使manual acceptance失效。

## Focused validation

- Catalog／provider：既有`test_model_catalog`characterization，加exact 61 membership、unique IDs、default、
  provider version、no barrel enumeration、no silent fallback及provider unavailable projection。
- License／source：provenance manifest completeness、allowed license set、hash/path、legacy self-contained imports，
  banned model／symbol／patent-source absence。
- Model parity：每個selectable upstream model以適當synthetic context執行constructor、forward與finite
  backward；每個legacy model比對upstream 1.6.1 state-dict keys／shapes及deterministic loaded-state output。
  Disabled model只驗證typed reason，不進Trainer。
- Workflow：每個model family至少一條real CPU one-epoch → selected checkpoint → save/reload → evaluation；
  支援gradient的family另驗證saliency。Data semantics仍由既有source-diverse gate擁有。
- UI：search／alias／family、keyboard、clear、no-match、disabled、selection preservation、cancel、healthy／
  unavailable provider、narrow window與default-scale screenshot；Windows跑100／125／150% native DPI。
- Platforms：Linux完整model matrix；Windows執行所有selectable model的bounded construction／forward及native
  selector smoke；macOS執行catalog／import contract和resource-bounded代表family，不宣稱真人desktop。
- Final handtest：正常Braindecode目錄搜尋，EEGNet與至少一個transformer完成CPU training／evaluation／
  Compute Saliency；provider unavailable walkthrough只顯示legacy且不自動換ID；artifact reopen及close／reopen。

## Stop conditions

- 任一copied file／symbol的license或來源不能逐項確認，或完成某model必須帶入CC BY-NC／patent code。
- 需要silent provider fallback、同一stable ID代表不同implementation、第二套model／training／checkpoint owner，
  或UI自行推導availability。
- 任一selectable model不能在其declared input contract下construct／forward，或只能靠未核准remote download。
- Provider preflight會阻塞UI、造成native abort，或legacy仍暗中依賴installed Braindecode。
- Windows model matrix出現unbounded memory／time、native abort或不可重現結果；停止該family並回報，不以
  skip、timeout放寬或降級claim取得green。
- Scope需要擴到non-classification Trainer、Data Import、4B Assistant或installer時停止並取得新決策。
