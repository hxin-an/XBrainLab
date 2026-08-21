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
`08b39997`獨立gate已PASS。Canonical truth sync更新`current.md`的model-catalog邊界、backend的唯一owner／
artifact identity／legacy license closure、UI的search／provider recovery投影，以及validation的exact-source
Braindecode candidate與Windows手測契約；不新增第二份plan或歷史worklog。MkDocs strict build通過。下一步
提交docs checkpoint，之後freeze product source、產生exact-source Model Selection UI artifact並執行一次
canonical handoff；若任何gate失敗，只修其recorded owner後建立新的candidate，不為計時重跑。
Docs gate指出architecture將identityless legacy stats-only compatibility寫成全面fail closed；實作的正確邊界是
identified／model-backed reopen拒絕缺漏／malformed／mismatch，而current identity同樣unknown時可讀舊statistics
且不可rebind／re-export。只修正該canonical wording後re-gate，不改產品或重跑model tests。
`7d059bff`的第一次canonical handoff在啟動complete regression前由architecture-compliance fail closed：
`ModelSelectionDialog`讀dataset signal context時直接呼叫`controller.get_epoch_data()`，繞過已存在的
ApplicationService command spine。修復只新增一個ApplicationService-owned detached model-signal query，
由既有ApplicationUiRuntime adapter轉交給dialog；不改catalog判定、畫面、搜尋、training mutation或owner數。
Focused validation必須證明product dialog只使用typed runtime query、無runtime時回到metadata-only projection，
並重跑architecture-compliance。建立新frozen SHA後才執行一次replacement canonical handoff；舊SHA的失敗
evidence保留為歷史，不重跑其完整suite。
第一版修復收斂為5個production files、production `+60/-10/net +50`、owner數不變；3個focused behavior
cases、Ruff、basedpyright、MkDocs strict與architecture-compliance均通過。下一步提交並由既有獨立gate
複核；只有新SHA通過後才重建exact-source UI artifact與replacement canonical handoff。
獨立gate指出第一版仍漏接typed product wiring：`TrainingPanel`在typed mode刻意不保留controller，真實
query owner位於既有`_query_port`；只將controller傳入dialog會錯誤退化為metadata-only projection。
修正必須由`TrainingSidebar`把既有TrainingQueryPort顯式注入dialog，helper直接使用該narrow port，並以
真widget＋typed fake port證明context read發生且不相容model被disabled；standalone context才允許fallback。
Typed port wiring已補齊；5個focused cases、Ruff、basedpyright與architecture-compliance通過。第一版
`31f31d1c`尚未push，會以同一focused commit amend後重新取得獨立gate，不保留兩個假候選SHA。
最終修復為6個production files、production `+75/-11/net +64`、owner數不變；`f0a77b80`獨立
re-gate已PASS。
`555ff17f`的replacement canonical handoff在complete regression fail closed。這不是selector evidence
遺失：`linux-unit-backend`有9個由新model identity／channel metadata contract暴露的失真測試fixture，另有
一個cold-import timeout；`linux-unit-rest`的兩個真spawn lifecycle cases在重型54-model backend matrix並行
時未能於既有watchdog內啟動。修復scope只包含：(1)讓saliency、Epochs與ModelHolder fixtures帶有真實
constructor會建立的identity／channel欄位；(2)讓local handoff runner禁止resource-heavy backend group與
spawn-sensitive rest group重疊，但保留八個authoritative Linux groups、unit→integration barrier、coverage與
fail-closed outcome policy。Non-goals是不增加watchdog掩蓋競爭、不刪模型／測試、不改產品行為、CI matrix
或handtest contract。Focused validation為受影響fixture tests、spawn/cold-import cases、runner scheduling
contract、Ruff與architecture guard；通過後建立新frozen SHA，才執行一次新的replacement handoff。若
focused cases仍在隔離狀態失敗、任何test count／coverage policy改變，或排程仍允許兩group重疊即停止。
修復沒有production source變更（production `+0/-0/net 0`，owner數不變）；原9個fixture failures與3個
spawn／cold-import cases均在原watchdog下通過，runner scheduling tests 6 passed，Ruff、format、
basedpyright與architecture-compliance通過。下一步建立單一checkpoint commit並交既有獨立gate複核；
只有PASS後才push並執行新的exact-source replacement handoff。
`0b7d7168`的replacement handoff確認fixture與backend/rest排程問題已關閉，但`linux-unit-rest`仍有5個
runtime-process startup timeout。完整runtime-process test file在獨立process且保留`--cov`時可重現，移除
coverage時原watchdog通過；根因是pytest-cov的`COV_CORE_*`被spawn child繼承，child啟動coverage造成
process-lifecycle probe本身失真。完整core selector進一步證明Downloader的真spawn seam同樣受影響，因此
下一修復只在`tests/unit/llm/core` scoped fixture啟動真child前移除child-only coverage env，
父pytest／其餘group coverage、八group topology與產品timeout不變；先跑完整runtime-process file，再跑
完整`tests/unit/llm/core`的canonical coverage argv。兩者未全通過即停止，不重跑handoff。
Scoped child-coverage isolation完成後，完整runtime-process file在原coverage argv為10 passed，完整
`tests/unit/llm/core`為242 passed；父pytest仍產出coverage且所有原watchdog未變。Ruff、format與diff
check通過，production `+0/-0/net 0`、owner數不變。下一步建立checkpoint並由獨立gate確認沒有coverage／
topology降級；PASS後push並建立新的exact-source candidate。
`0d0eeaaa`的新candidate已使全部unit groups通過，但integration-rest的
`test_saliency_view_publication_lifecycle.py`有16個case在共同fixture建立producer identity時失敗；該fixture
以`object.__new__(TrainRecord)`繞過constructor且漏設`model_identity`，所以尚未進入各自race／cancel／render
assertion。修復只補上同一fixture的`model_holder.catalog_identity`，完整執行該integration file；不改product
saliency或artifact fail-closed規則。若仍有其他failure即停止並按新record分類。
Shared integration fixture補齊後，該file 35 passed，原16個lifecycle cases已跨過producer identity並完成
各自assertions；production `+0/-0/net 0`、owner數不變。下一步做Ruff／diff check、checkpoint與獨立gate，
PASS後才push並重建exact-source evidence。
`cdb222fb`在具備原生CUDA權限的replacement handoff先通過source preflight、Ruff與format，之後由
basedpyright fail closed，尚未進入complete regression。相同gate在sandbox錯誤觀察為0 diagnostics；在
handoff相同原生權限下可穩定重現624個observed diagnostics，其中537個new diagnostics只位於逐檔保留的
`legacy_braindecode`第三方原碼，另7個位於XBrainLab-owned Model Selection Qt Optional access。修復scope
只包含：(1)將exact legacy third-party namespace加入basedpyright exclude，同時保留provenance、model parity、
54-model execution與六family workflow作其authoritative evidence；(2)實際收斂Model Selection的optional
style／list-item access；(3)加入typecheck config contract，防止排除範圍擴張至catalog／adapter／UI。
不更新baseline、不逐行改寫上游vendored演算法、不忽略XBrainLab-owned diagnostics，也不改可見UI行為。
Focused validation須在原生權限下使basedpyright regression為0 new diagnostics，並通過selector、typecheck
contract、Ruff與format；若exclude涵蓋legacy namespace以外、仍有owned-code diagnostics或任何selector
行為改變即停止。通過後建立新SHA並交既有獨立gate，只有PASS才執行replacement canonical handoff。
修復完成後selector＋typecheck contract為29 passed，Ruff／format／diff check通過；原生權限下的
basedpyright regression為80 observed、0 new、1 resolved，沒有更新81筆既有baseline。排除範圍只包含
reviewed legacy third-party namespace與原有LLM model source，catalog／adapter／artifact／UI仍受檢；
production變更為UI null-safe access `+14/-7/net +7`，owner數不變且沒有可見行為改動。下一步建立
checkpoint並由既有獨立gate複核，PASS後push新exact head並執行replacement canonical handoff。
`18d43be4`的replacement handoff已通過source/static、complete regression、Assistant／GPU、UI／native
lifecycle及source-diverse data gates，但在deferred record聚合時由`startup-smoke` fail closed。Artifact顯示
entrypoint在MainWindow前拒絕缺少`XBRAINLAB_CONFIG_DIR`；這是CI reliability已新增的正確產品安全要求，
而local canonical handoff的startup runner仍未提供隔離root。修復只在既有`run_startup_smoke.py` owner內：
未顯式提供root的local probe自建一個含空格與非ASCII的owned temporary root，重用
`build_isolated_environment()`產生全部mutable paths並只注入child；CI顯式root路徑與`run.py` fail-closed
要求保持不變。先讓現有clean-close test對缺少isolated root／environment轉紅，再實作並跑startup unit、
prepare-native contract及一次focused xvfb startup command。若root逃出owned temp、child未收到全部required env、
product設定被寫入真實user path、cleanup掩蓋surviving child或CI explicit-root contract改變即停止。
紅測先以`isolated_root=None`精確失敗；修復後startup＋prepare-native unit contracts為8 passed，包含local
owned-root cleanup與CI explicit-root preservation。原生Xvfb focused smoke實際觀察MainWindow initialized、
Qt `xcb`、close requested、return 0及process-tree quiescent，九個mutable paths全位於含空格與非ASCII的
temporary root；sandbox內同命令因不能連X display而native abort，未被計為產品失敗或pass。修復只觸及
既有dev runner與test，production `+0/-0/net 0`、owner數不變；Ruff／format／diff check通過。下一步建立
checkpoint並由既有獨立gate複核，PASS後push新exact head，再執行replacement canonical handoff。
`735d8a91`的replacement handoff已關閉startup isolation，但complete regression在unit phase fail closed：
`linux-unit-backend`的5,342個cases中只有
`test_policy_import_does_not_cold_start_visualization_stack`失敗，原因是其10秒subprocess probe timeout；
其餘5,341 passed，integration依unit barrier正確未啟動。修復scope只處理這個cold-import test seam：先以
無coverage與handoff相同coverage argv各執行一次，確認產品import contract與`COV_CORE_*` child
instrumentation的差異；若確認，僅讓該probe child不繼承coverage activation，父pytest coverage、10秒
watchdog、`visualization`／`matplotlib.pyplot` absence assertions與產品碼全部保持不變。Non-goals是不提高
timeout、不把import assertion改弱、不改saliency產品行為、runner topology或coverage policy。Focused
validation為同一selector在canonical coverage argv下由red轉green、完整saliency policy file、Ruff／format／
diff check；若無coverage仍timeout、child隔離後assertion失敗，或父coverage artifact消失即停止並按產品import
defect重新分類。通過後建立一個tests/docs-only checkpoint，交既有獨立gate複核並push；之後只執行一次新的
exact-source canonical handoff，不為計時重跑。
Focused red evidence來自`735d8a91` canonical backend shard的10秒timeout；同selector在無coverage時
為1 passed／4.54 seconds，加入父coverage但未隔離child時雖在空載環境通過，整體增至21.61 seconds。
Probe現只移除其child environment的`COV_CORE_*`並反向斷言未繼承；同selector＋coverage為
1 passed／11.97 seconds，完整saliency policy file＋coverage為18 passed／12.19 seconds，父pytest仍產生
coverage artifact。產品source、assertions、watchdog與runner皆未改（production `+0/-0/net 0`，owner數
不變）；Python Ruff／format、MkDocs strict與diff check均通過。下一步建立checkpoint並交既有獨立gate；
PASS後push並只跑一次replacement canonical handoff。

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
