# XBrainLab Now

最後更新：`2026-10-03`

## 目前 — TEST封存、三次完整量測與本機結果交付

2026-10-02使用者批准完整TEST施工計畫及結果回存，要求節省額度、避免頻繁監控。
基準head為7c4ac807；settings.json為使用者設定，不更動。VALID已完成並依既定規則
選定Phi-4 Mini R5；現有runner/config尚未接通TEST及指定三項消融，不能直接開跑。
Outcome：Full、RAG off、tool-catalog filter off、format retry off各132題×3 repeats，
共1584筆有效案例（修復生成另計），完成報告、離線核對、題庫稽核及本機完整結果副本。
Scope：沿用封存／runner／scorer／report owners，補TEST配置與單因素消融、必要fixture、
無LLM預檢、獨立風險覆核、同head CI、137正式執行及NAS→本機完整VALID/TEST回存。
Non-goals：除2026-10-03另批准的Host數字來源限制移除，不改UI或其他產品工具／Host契約；
不改入選提示／RAG／生成／判分，不追加DEV、模型、
B0或新環境，不merge，不依TEST錯答調整或重跑。失敗source與原始證據保留。
研究因素先凍結再讀TEST；catalog off只擴大呈現目錄，原RAG eligibility、固定示意、
state、backend admission與confirmation保持不變。RAG off與retry off各只關自身因素。
固定greedy seed0、既有137環境／Phi snapshot；三repeat按四條件循環輪換排程，
各condition獨立session、逐題reset及既有warmup。不以Host阻擋把錯誤提案計正確。
分析保持三類macro及每repeat P50/P95再平均；呈現各類、always-respond 66.67%參照、
配對變化、retry救回／成本與模型／Host／執行分層。補三類分層family配對bootstrap，
10000 draws、analysis seed0，所有變體／repeat／condition一同取樣；區間僅對題庫涵蓋
的任務作條件式推論，不當成三個repeat的新樣本或多重檢定整體顯著性。
步驟：固化協定→DEV/VALID paired-input與配置red-green→精確source／CI與獨立覆核
→解封TEST及無LLM完整fixture/input/token預檢→新封存→137單次正式啟動→完成核對。
TEST正式啟動後做下列題庫／示例稽核，不拿TEST回饋調提示。若真fixture缺口需修，
只修工程接線並重新封存／驗證；實質oracle或研究決策缺口另交使用者，不暗改。
Focused validation：單因素完整輸入差異、blocked工具仍受Host拒絕、off條件證據正確、
12 conditions×132唯一jobs、三repeat、封存防覆寫與新run、cleanup／退出／原scorer重播。
交付：NAS stages/test完整source/config/run；本機碩論準備/實驗/result/VALID及TEST
完整成功run（index/reports/raw/inputs/launches/audits/manifest），核對逐檔hash與離線links；
不複製權重、環境或暫存EEG，不覆寫舊批次。UI無改動，不新增產品手測門檻。
監控：啟動確認一次，之後按預估時程低頻讀取摘要或終態；不連續讀log／逐題輪詢。
等待期間做已授權離線分析／回存，無工作則使用等待機制；異常才深入診斷。
Stop：1584筆／12完整conditions、正常退出與cleanup、報告／稽核／回存驗證完成，
或需要使用者提供的TEST來源／新決策等真實blocker。不因compact、CI pending或啟動就停。
Checkpoint：TEST排程／reader／runtime已接通，產品0修改；173runtime、61reader/preflight、
79配置相鄰、30parent、51封存及23統計focused checks通過，非真模型分數。
獨立覆核發現報告漏驗actual runtime factors，先red後補嚴格核對；完整1584報告及2負例
共3项green。離線重評9項通過；比較工具22項在UTF-8通過（初次cp950有5讀檔失敗，
未改分數或產品）。完整報告其餘回歸已通過，新的exact head CI仍待執行。
VALID已回存result/VALID/20261002-124746-8263faf9：10143原檔402369543bytes、10523
離線links有效、逐檔hash讀回一致；排除1485個synthetic fixture及1共享模型link。
TEST沿用既有NAS樹的stages/test入口、snapshot/sources及results/runs；不為外觀重複
封存一份程式。local TEST仍按run-id集中。此為沿用現有封存owner的具體位置。
完整題庫為附錄/題型_已審完整版.xlsx；研究因素凍結後已解封做無LLM工程預檢。
封存f8af513f已完成99VALID×4真fixture／RAG／token預檢，Full對7c逐字一致且無截斷。
解封TEST後64/66 fixtures通過；FX-TEST-A09-01的已審1–100Hz bandpass，以及
FX-TEST-A11-02的已審channel selection起始狀態未被fixture支援，cleanup均正常。
批准計畫內的必要工程修理：真Command建立上述已審狀態，保護波形／channel／publication；
不改題庫、oracle、prompt、產品或研究因素，不用只修改狀態欄位冒充處理成功。
保留f8失敗預檢，另封新source與CI，重驗66fixture及396VALID輸入；尚未TEST推論。
兩fixture先2red，真Command數值／events／來源備份保護15green，完整fixture50green；
獨立data/implementation覆核無阻擋。只scripts23增3刪、tests76增1刪，產品0。
新封存fa9d4d54已通過396VALID及528TEST輸入預檢；66/66 TEST fixtures完成。
Full與原7c輸入一致，三消融維持單因素，最大含retry3294tokens，無截斷。
fa9 CI24成功／3scope skip及實物獨立覆核通過；publication完成，但run.sh於schema
檢查拒絕，仍無TEST推論。真NAS舊入口hardcode353b53df bootstrap，在選新coordinator前
先用舊config parser拒絕TEST；publisher測試漏掉真舊shell入口。原log／source保留。
Next：同publisher/launcher owner修理歷史入口遷移，真shell red-green涵蓋TEST及舊scope；
不得僅用直接python繞過不可用的./run.sh，不改題庫／prompt／scorer。
複雜度／封存決策：沿用batch owner，production0、owner不增；migration只改shell及
manifest對應hash，舊entry與manifest先exclusive封存。Coordinator/candidate/config仍fa9，
不引入old runtime compatibility branch。修理tool另封SHA與CI，既有受測source預檢仍有效。
真舊入口(TEST、DEV、root/compare dispatch)及失敗rollback通過後才恢復正式量測。
入口修理已真shell重現TEST/DEV舊schema拒絕；獨立覆核補抓發布後中斷還原不一致，
真os.replace後KeyboardInterrupt的entry及manifest兩負例先red後green，34項Linux batch通過。
涵蓋修理後可啟動、未推論check、受測bytes不變、發布前/後中斷一致性、重試及非法head。
獨立diff及部署helper覆核無剩餘阻擋；scripts113增8刪、tests208增，產品0。
入口修理tool 12aebf9d exact CI24成功／3scope skip；NAS已保留舊entry/manifest並完成migration，
真stages/test及stages/dev的./run.sh --check-environment均exit0，受測source/config仍fa9。
正式run 20261002-171315-44094303已在第30題TEST-A08-01-V1因
product_execution_observation_missing停止：29 recorded，cleanup true、runner exit1，原始資料保留。
題目four/eighteen Hz，模型raw正確提出bandpass 4/18；Host參數來源驗證僅Arabic decimal，
admission respond要求補值且terminal completed。觀察層只識別blocked/confirmation等nonexecution，
未識別這個明確respond，誤歸缺少執行證據。非fixture缺口，不可依TEST修改Host或oracle。
2026-10-03使用者另明確授權移除Host「原句偵測不到數字就不放行」條件，取代上述
僅修觀測層方向。使用者重申實驗只關心模型原始答案分數，Host/執行紀錄僅診斷。
本次outcome/scorer尚無修改；停止該方向，不藉新產品修理調整研究評分。
Outcome：bandpass/notch/resample由模型解析數值，Host不再做原句數字membership；
保留required/type/enum/range、capability、publication、confirmation及method來源檢查。
RAG example_policy重用的來源helper保持原樣，不因Host修理改檢索/模型輸入。
先真路由固定模型輸出red-green與schema/range相鄰測試，獨立覆核、新source／CI後
另存完整TEST批次；保留舊run，不拼接。UI無layout變動，放行行為已明確批准。
DEV五輪6600及VALID1485原紀錄已全量核對：270次numeric admission respond，全部
raw final_decision_correct=false，無正確答案被此Host擋下的既有案例；不用為此重跑DEV/VALID。
模型原始分數由raw scorer擁有，不因Host阻擋變正確；本次失敗TEST raw score本來即true。
Host已只在三numeric tools跳過原句membership；4項coordinator red→123相鄰green，
真condition English red→English/digit/既有ablation共5green，另24項schema/range保護通過。
獨立產品／raw-score邊界覆核通過，待舊數字gate專屬測試同步及其覆核；尚未重啟正式推論。
2026-10-03使用者再次確認只關心模型原始答案分數，要求持續完成原計畫。
後續修理也解除research量測完成條件與product_outcome有效性的耦合：完整原始capture、
原scorer、decision計時、case identity／fixture與cleanup仍必須通過；Host拒絕／執行
觀測缺口只留獨立診斷，不改模型分數或分母。產品／UI診斷不能偽稱成功；state/reset或
模型量測本身不完整仍阻止繼續。先以Host非執行、執行異常及cleanup負例red-green，
覆核caller/report/audit一致性，不刪診斷、不調prompt/RAG/oracle，舊Pilot契約不默改。
舊數字gate測試已同步：268項focused通過，tests22增202刪；待最後獨立覆核。
Next：完成research分層修理與覆核→新exact SHA/CI→新TEST封存及完整輸入預檢
→1584正式量測→報告／題庫稽核／本機回存。中途checkpoint不結束授權工作。
研究分層修理已完成：current／legacy條件先3red/3green，報告先1red/5必要負例green；
最終真route19passed、報告9passed，含Host respond、執行失敗、diagnostic後下一題、
完整raw後product deadline、capture損坏／missing terminal／pending cleanup失敗仍拒絕。
原product outcome先保存真timeout，僅current完整raw+真clock+非decision timeout才將
product deadline移為診斷；不延長等待或假造terminal。Scripts56增8刪，獨立最終覆核通過；
模型input/scorer/RAG/fixture/parser未改。Next為commit／CI與新source無LLM預檢。
題庫數值稽核已完成於results/engineering/dataset-overlap-fa9d4d54：495題、161RAG、
2固定示例，9組154737 case-pairs，75個family候選待AI語意覆核。結構全量無issue；
跨split完全相同0，DEV–RAG完全相同2（不能直接推論洩漏）。使用既有CPU/offline
MiniLM；原helper遇到installed SentenceTransformer不支援local_files_only constructor，
v2只去除此參數，仍以固定本機snapshot與offline環境執行，未下載／推論受測LLM。
稽核沿用fa9凍結bank/RAG/context；新source只改Host與量測分類，另核對相關hash不變。
75組候選雙agent語意覆核已完成並回存碩論準備/資料集驗證/2026-10-03，核對原13檔、
helper及兩review的hash和75組evidence IDs。主分類8任務等價（跨split7）、39文字相近
但任務不同、16模板近似、12完整state等價未決；不稱無洩漏，不改題庫／分母。
NAS原數值audit保留semantic_review_complete=false歷史欄，另存semantic-adjudication.json
作本輪覆核結論；此為有界AI輔助稽核，不是第二人類標註。資料分析不需再呼叫受測模型。
零推論的舊入口失敗log與本次模型原始輸出皆保留；完整TEST／題庫稽核／回存未完成。

## 已完成 — VALID量測與TEST前討論

VALID run `20261002-124746-8263faf9`已核對1485/1485、15 conditions各99筆、
cleanup通過、runner/launch exit0及非partial報告；啟動時的交回記錄保留於下方。
上述TEST施工已另獲批准；本節保留VALID完成證據。

### 待辦 — TEST正式啟動後執行題庫與示例重合稽核

另經授權完成TEST配置凍結並正式啟動後執行，不另設為開跑前阻擋。
詳細待辦及後續產出集中於使用者指定的 `D:\workspace_v2\projects\lab\碩論準備\資料集驗證`，
以該資料夾 `README.md` 為本項稽核範圍／判準的唯一明細，不在此重複維護。
不重跑受測模型、不改凍結配置或主分母；TEST內容不得回流調整。實質問題另議，不自行重跑。

## 歷史交回 — VALID修理完成，三次完整重跑已啟動

封存source `7c4ac807288aac80d7f0826dedd75fc42fa08149`／PR157未合併。
同head CI全部completed：24成功／3 scope skip；獨立source、相鄰UI風險及封存證據覆核通過。
137修理runtime真Qt66項通過；最終test-only head另5項原生保護通過，runtime未再更動。
33/33真fixtures及495組完整模型messages與原5ceb逐字相同，1485排程／研究因素不變。
原失敗run與原封存保持原樣；repair-01封存未跑，正式使用獨立repair-02。
NAS根`/mnt/home/2025/hxin/XBrainLab-experiments`；入口`stages/val/repair-02/run.sh`。
run `20261002-124746-8263faf9`，結果在`stages/val/repair-02/runs/`；
tmux `xbl-valid-repair02-7c4ac807`，log `.runtime/logs/valid-repair02-7c4ac807.log`。
初始10筆actual system／RAG／prompt與raw hash／capture／cleanup全部通過；
進度320→347/1485，session仍運行。證據`results/engineering/valid-repair-7c4ac807/initial-live-check.json`。
這是正常啟動，不是實驗完成或正確率保證；依終點交回，不持續監控、不再追加推論。
未知modal／證據缺失／清理失敗仍fail closed；不調VALID提示、不讀TEST、不merge。
使用者本機研究文件六份已更新正確修理入口；result/VALID明示尚無完整結果。
Next：使用者查結果時核對三次完整性，再整理正式指標；不要把舊部分結果混入。
本頁為封存後交回記錄dirty，settings.json是使用者設定；遠端sealed source仍clean。

本修理封存對5ceb（新增/刪除/淨）：產品0；測試327/12/+315；腳本1/1/0；
文件74/1/+73；設定/其他0；合計402/14/+388，二進位0，含新增測試檔。
分支對main72548c：產品220/23/+197；測試3028/24/+3004；腳本1763/91/+1672；
文件721/10/+711；設定/其他0；合計5732/148/+5584，二進位0。
以上不含封存後本頁及六份外部研究文件；外部文件是路徑／狀態同步，未改題庫或結果。
本修理產品未改、設定未動；測試／scripts有真路由red-green與同head CI／獨立覆核；
文件隨真實證據更新，不將工程預檢視為模型準確率。

## 歷史 — VALID錯誤工具路徑的量測可靠性修理

使用者授權修好並預先檢查同類問題，再恢復跑分。失敗run
`20261002-105305-344823d1`正常recorded394/1485，G4三遍完成，G33第一遍
`VALID-N03-03-V1`誤選3D導航，真實GPU Memory Usage提醒被driver判為unexpected_dialog；
原始決策已正確判錯，但產品量測失效導致整批exit1。既有測試手工造舊VRAM Warning文案，
未走實際產品提示，因而漏檢。
Outcome：錯誤工具選擇可被如實量測、隔離清理並繼續下一題；真正缺證據／未知對話框／
observer故障／清理失敗仍fail closed。不能保證未知缺陷永不發生。
Scope：研究UI driver及直接相鄰路由、真Qt回歸／固定回應重播、獨立審查、封存及VALID修理重跑。
Non-goals：不改產品UI／工具契約、模型、提示、RAG、題庫、raw scorer、一次格式重試；不讀TEST、
不依VALID分數改候選、不merge。舊source／run／分數／失敗證據及settings.json保留。
假設：既有137環境可用。先無LLM驗實際警告、各導航／開窗、確認與取消、逾時、下一題隔離；
不以更多正式推論代替工程預檢，不把未知視窗一概當成功。
步驟：最小真產品路徑red→重用driver窄修理→同類路徑matrix與舊raw重播→獨立source／
證據覆核及適用同head CI→新修理source封存，保持入選五套研究因素→三次VALID重跑。
驗證：原錯題決策仍false；警告被記錄／關閉，無殘留pending／modal；下一題正常，
未知或不相關視窗仍失效；真產品路由不用手工複製文案充當測試。UI無變更，無需新手測。
Stop：修理與預檢／獨立覆核通過、新封存1485排程正常啟動並驗初始capture；不無限監控。
已完成最小修理：driver辨识當前GPU Memory Usage，未知／確認型／不相關／foreign modal仍拒絕。
真checker與真3D有／無saliency均先red；修理後34真Qt路由通過。No-call／Clarification
兩種固定錯誤回應經真session→Host→UI→scorer均仍計錯、recorded、cleanup通過，下一題
reset後正常；另warmup保護通過。測試double原先逐生成重建capture backend導致排序失真，
改同condition重用，tokenizer double的字元計數限制也明確隔離；不是產品或模型問題。
獨立風險審查無剩餘blocking；不忽略unknown modal，不改scorer，不把renderer失敗稱成功。
Next：直接相鄰condition／outcome／report／runner保護完成後封新head，CI與137相同真路由
及33fixtures無推論預檢通過才發布repair-01。原父val入口保留歷史source，新入口另明示。
Checkpoint：b32c27f9的137真Qt66項／33fixtures通過；495模型messages與5ceb逐字相同，
1485排程相同。獨立source／artifact／package覆核通過，repair-01已封未跑。
CI23成功／3skip，但Windows lifecycle既有test_training_refreshes_metrics_before_explicit_saliency_click
在terminal_publications數量0失敗；UI與saliency均已完成，與本輪driver無呼叫關係。
直接驗證阻擋：有界延後training terminal notification可重現同一行，將確認放行後exact1，
若成立僅補測試等待真正通知終態、不改產品或放寬一次publication斷言。失敗CI與未跑封存保留。
新的test-only head仍需CI；不提前啟動、不回寫b32c封存，不更改研究因素。
有界真background-owner probe已證明UI全部完成時通知仍0，放行後自行exact1，未手動補發。
僅於測試末尾加6行有界等terminal/analysis通知，保留所有UI及exact1斷言；相同受控probe
green與3項正常／OOM／相鄰saliency通過。產品／scripts與b32c完全相同。
Next：test-only head CI、新repair-02封存（repair-01保留未跑）；通過後再正式啟動。

## 歷史 — VALID三次正式量測已啟動（後續中止，見Active）

使用者已明確授權開始VALID，做到整批三次排程有效啟動後交回；不持續監控到跑完。
證據：R5 run `20261002-083918-9b247d6a`完整1320筆、exit0、非partial、cleanup通過；
五輪候選額度已用完，不追加第六輪。VALID非TEST題庫已封存，尚未固定入選配置。
Outcome：按既定最終三類平衡正確率／P50選每模型一套，五模型各99題×3 repeats＝1485筆。
Scope：核對五份正式DEV報告／分母及來源（R4採repair-03）、選版、VALID封存／入口、
必要工程接線補齊、研究文件及直接測試／獨立覆核、137正式單次啟動。
Non-goals：不改候選提示、RAG、模型、生成、scorer、題庫、一次格式重試、UI；不讀TEST、
不merge、不依VALID分數調整／重跑。舊source、報告、失敗證據與settings.json不改。
假設：137既有資源可用；若早期入選source缺後續退出／停止修理，先審查工程遷移與輸入
等價性，不能直接以最新提示替換，也不能帶已知native退出缺陷開跑。
步驟：獨立選版核對→固定選版來源／排程／完全同分規則→重用封存入口補齊VALID
→focused／適用CI與無推論fixture／完整輸入檢查→獨立artifact覆核→確認GPU可用後啟動。
驗證：15個condition、每個99題、repeat0/1/2、各模型297筆；獨立實際生成而非複製；
各repeat分開計算再平均。程式與封存有改動時按tdd補直接保護；產品UI沒有可見變更。
Stop：同版本相關驗證完成、封存可重跑，三次均在排程中且初始capture／cleanup／進度正常。
Next：讀取五輪保存分數，確認各模型來源及是否需直接必要的工程相容修理。
選版獨立覆核：G4 R2、Llama R3、Gemma R4 repair-03、Phi/G33 R5；五份報告及
manifest/journal hash、完整分母、正常退出、固定研究因素一致。早期候選確有已修理的
Qt退出／停止確認舊碼；以R5共用engine加原入選提示封新source，舊DEV身份另記不回寫。
實作：只恢復入選research renderer，VALID blocked stage原子啟用沿用append owner；
preflight接既有config選VALID99題，不複製三份fixture。新增owner／產品修改均為0。
Complexity：刪除未入選G4欄位註記／Llama對照分支，重用封存發佈與population契約；
script預計淨增約21行，無新production module。共享engine/產品/RAG/scorer固定不動。
直接保護：selected prompt先6項red後79green，370catalog及10完整normal/retry歷史比對相同；
VALID preflight先missing API red後2green；封存batch/package49green；報告/runner/preflight112green。
獨立source覆核通過；兩項helper強化（沿用retrieval query界線、綁定audit三份hash）已加入。
使用者另要求本機`碩論準備/實驗/result`：依R1–R5成功批次匯出離線報告、逐題輸入輸出
及CSV/JSON，相對links保持有效，不複製環境、模型、暫存EEG或失敗批次；NAS原證據不動。
Next：最終source CI／137真VALID33fixtures與990normal/retry輸入核對，封存後啟動1485排程。
Checkpoint：f86441fd已封存／PR157 CI中；尚未推論、未發布VALIDstage。預檢helper首次
錯以為snapshot有完整Git歷史，改讀原封存source（舊helper/log保留）。第二次真33fixtures
找出FX-VALID-C04-01的reviewed prior_preprocessing={reference:average}尚未被fixture
實作；其他32情境通過。直接必要修理：以真PreprocessCommand平均參照建立起始狀態，
先red／波形和publication保護再實作；不改銀行內容、oracle、prompt或產品契約。
新source需新CI及33fixture完整預檢；失敗f864證據保留、不覆寫、不計模型改善輪次。
平均參照修理先2red／5green，再直接7green與完整fixture42green；独立數值與
publication／原始資料／EOG保護通過，獨立diff覆核無阻擋。只改研究fixture，產品0。
最終head `5ceb00cdb513539868793eaead9e80361320cad3`／PR157；stage
`.runtime/valid-stage-5ceb00cd/source`，證據`results/engineering/valid-5ceb00cd`。
137無生成預檢exit0：33/33真fixtures，495正常＋495retry完整輸入等同歷史入選renderer；
fresh RAG每模型74/99題有例，max retry1903/3081/2700/2096/2910 <7680，無裁切。
獨立實際artifact覆核PASS（含65完整輸入samples、15conditions各99、三repeat身分及綁定hash）。
本機result已完成R1–R5離線副本：34325原檔逐檔SHA讀回一致、47470HTML links有效；
含provenance/README共34331檔1552657945bytes，無暫存／archive殘留，未複製權重／環境／EEG。
五輪report SHA主agent另核對；外部研究文件5份的links/fences檢查通過。
Next：等待同head CI全完成成功後，以工程helper publish啟用stages/val，確認GPU仍空閒，
單次tmux啟動15conditions/1485jobs，驗最初10筆actualcapture與進度即交回；尚未推論。
最終同head CI已全completed：24成功／3scope skip。已原子啟用stages/val，
root manifest `544ac80680537a9f2d10710eebde400e39a645b78aa16a5fcc209d454a67849c`。
181舊sealed檔／14run身分／3repair seals保持不變，shared environment check通過。
GPU空閒後單次啟動run `20261002-105305-344823d1`，根目錄`results/runs/`；
tmux `xbl-valid-5ceb00cd`、log `.runtime/logs/valid-5ceb00cd.log`。
最初10筆actualcapture／system／RAG／prompt/raw hash／cleanup通過，15conditions各99題，
repeat0/1/2及1485唯一jobs核對通過；進度觀察13→47/1485。證據initial-live-check.json。
此為有效啟動，不代表三次完成或答題正確。依授權終點停止監控，不追加推論／TEST／merge。
外部文件與本機result/VALID入口已寫實際run；DEV五輪副本已全部驗證並交付。
Next：待使用者查結果，再核對三次完整性與保存指標；不要自行重跑或依VALID調提示。
本頁是封存後交回記錄dirty，settings.json仍屬使用者；remote sealed source保持clean。

本輪封存對51dd709b（新增/刪除/淨）：產品0；測試321/39/+282；腳本105/73/+32；
文件66/1/+65；設定/其他0；合計492/113/+379，二進位0。
分支對main72548c：產品220/23/+197；測試2701/12/+2689；腳本1762/90/+1672；
文件648/10/+638；設定/其他0；合計5331/135/+5196，二進位0。不混為本次新增產品。
不含封存後本頁／外部論文文件及報告副本（資料搬移非新增source）；測試/scripts直接與
同headCI及独立覆核通過、文件build/link檢查通過，產品本切片未改，設定未動。

## 歷史 — DEV第5輪已完成

使用者批准外部`DEV第4輪總結與第5輪改善計畫.md`第四節，要求改好跑下一輪。
證據與假設：R4完整1320筆仍有必要值／操作與回覆判斷錯誤；只測一套逐模型候選，
不預先宣稱提升。Granite4取R2提示、Phi／Llama取R3、Gemma／Granite3.3取R4；
共用source保留78110571的停止確認與退出修理，不回退產品。
Scope：G4必填欄位局部來源提示；Phi完整／缺值對照；Gemma只核對所請求工具；
Llama開窗／資訊對照；G33操作／禁止／資訊／缺值對照，替換既有示例或提示。
Non-goals：不改UI、模型、生成、RAG、schema、Host、scorer、一次格式重試或題庫；
不碰VALID／TEST、不merge、不追加smoke或第六輪。示例只依公開契約，不抄DEV題目。
步驟：實際assembler保護與實作→focused／lint→獨立source與完整輸入覆核
→同head適用CI→66真fixture及1320上下文／精確tokenizer檢查→封存完整source/config
→137確認GPU空閒後單次啟動五模型各264題，驗最初真capture與正常進度。
Complexity：沿用研究assembler及append_round；產品與owner不增加，不新增控制層。
Stop：精確封存版本有效開跑且初始紀錄／cleanup／進度正常即交回，不監控整輪。
UI無改動；settings.json保留。五模型呈現已實作，4項新保護先red，72項直接測試green；
獨立source覆核通過。相鄰session檢查找出3項沿用R4強調位置的舊斷言，改為核對本輪
明定的R2／R3／R4位置；其餘28項通過，不改產品接線。
Next：精確source封存／CI與137無推論完整輸入檢查，覆核通過後才正式啟動。
Checkpoint：d1d2ff3d的66-state／1320-context與精確tokenizer及獨立完整輸入覆核通過。
CI阻擋：既有saliency queue handoff測試忽略release_shutdown_fence的bool，背景retry仍握有
同generation reservation時可合法返回False，隨後query仍可成功，測試卻立即要求pending清空。
先用有界交錯probe確認；只修直接阻擋驗證的測試同步、保留終態／一次通知断言，不改產品／
提示或研究條件。若證據成立，新test-only source重新CI與封存檢查後才開跑；保留原CI失敗。
受控原生probe已重現原失敗：真retry握有reservation時release=False／fenced=True／pending=True；
放行後真交接完成、release=True／fenced=False／pending=False。測試改沿用既有有界release重試，
不增加watchdog，不刪終態／一次通知断言；正常focused green，產品及提示不變。
最終source `51dd709bc8f4aefb17f0c625e8135e69bcfe901b`／PR #156，CI24成功／3 scope skip。
受控交錯green亦通過；失敗CI與red/green probe保存於NAS `results/engineering/round5-d1d2ff3d`。
新stage `.runtime/round5-stage-51dd709b/source`，證據 `results/engineering/round5-51dd709b`。
新head66真fixture／1320context及精確tokenizer通過（含retry最高3078/7680），獨立完整輸入
與封存覆核通過；175舊封存檔、13run身分及3份repair seals不變。未重做舊run全文hashaudit。
已追加`stages/dev/round-05`，137 GPU空閒後單次啟動run `20261002-083918-9b247d6a`，
結果在NAS `results/runs/`；tmux `xbl-dev-round05-51dd709b`，log `.runtime/logs/dev-round05-51dd709b.log`。
最初10筆actual system／prompt及raw hash／RAG／cleanup通過，進度已觀察31→80→176/1320。
臨時初始核對helper先因key/value-list與dict表示不同誤報，解碼後內容完全相同；v2檢查通過，
未改sealed source或run。證據`results/engineering/round5-51dd709b/initial-live-check-v2.json`。
外部研究文件與一行重跑指令已同步；不merge、不追加推論。這只證明啟動正常，不代表整輪
完成或分數提升。Next：依約停止監控，待使用者要求查結果，再討論五輪選版；不自動VALID／TEST。
本頁封存後收尾記錄dirty，settings.json仍屬使用者；remote sealed source保持clean。

## 已完成 — 第4輪分析與DEV研究文件精簡

`碩論準備/實驗/DEV階段紀錄`全數整理，移除工程除錯／CI／行數／重複進度，保留研究結果、
代表錯題與各輪已採用決策；新增`DEV第4輪總結與第5輪改善計畫.md`，第五輪仍待批准。
核對四輪保存分數與代表完整輸入輸出，獨立覆核數字、歷史決策與候選邊界，無阻擋。
同目錄由三份939行變為四份402行；README與操作指令同步精簡、連結核對通過。
未改產品／測試／腳本／設定，未重評分、推論或使用VALID／TEST；封存與失敗原始證據不動。
Next：第五輪已獲批准，以上方Active為準；未授權merge。

## 已完成 — DEV第4輪修理／完整重跑與證據覆核

使用者要求修正停止確認後全量重跑，追到1320筆、正常退出、audit及共同案例比對；
不沿用初始10筆即交回。UI layout不改；同run停止確認契約已獲批准並記入target/agent。
不改模型／提示／RAG／題庫／raw oracle／一次格式重試，不啟動第5輪、VALID／TEST或merge。

已完成修理：同一running trainer/run的進度publication不再使停止確認失效；
換run／terminal／stopping仍拒絕，原run由Host一路傳至Trainer鎖內原子核對，不信模型參數。
成功stop後新run立即啟動的ack競態亦保留原target，不拿新run終態回報。
量測以完整相關trace辨識blocked／cancelled，不再把合法拒絕誤當缺失；缺事件仍fail closed。
6177份歷史case離線重播只改一筆分類，舊raw scores與檔案保持不變。
重用原pending context、TrainingRunIdentity與既有locks；10個既有產品檔、owner數不變。

精確封存source：`7811057170307b4f93e33e6248750cb1b6e51beb`，PR #155未merge。
此前c29a3c09的macOS測試失败已定位為第一次reset的montage publication延後7→8，
非duplicate執行；只補7行等待真終態，全部安全斷言保留。已封未跑repair-02及失敗證據保留。
最終head CI全completed：24成功／3 scope skip，含Windows／macOS lifecycle。
直接／相鄰443項及真Qt3路、ack競態、確認提示、舊stop control均有通過證據；
137精確source 30項native、66-state／1320-context preflight與獨立source/artifact覆核通過。
Ruff與changed-file Basedpyright通過；Mypy有3項既存錯誤，不宣稱全案零缺陷。

NAS根：`/mnt/home/2025/hxin/XBrainLab-experiments`。
封存入口：`stages/dev/round-04/repair-03`；run `20261002-060225-32f033ab`。
單次全量1320/1320完成、五模型各264；runner及五child均exit0、cleanup全部通過，
complete_selected_schedule=true、partial=false。所有實驗程序已結束，GPU已釋放。
Gemma DEV-A14-01-V0實際走批准→停止原run→completed，不只是模型選對工具。
報告：上述入口下`runs/20261002-060225-32f033ab/index.html`。
同run audit `audits/20261002-063642-db52d3dc.json`：1320重播、零issues，12812項原證據不變。
最終正確1016/1320，仍有模型錯答與既定harness取消；不是所有產品操作成功。

兩份compare均完成、原始證據不變（均位於repair-03/comparisons）：

- 原版dd2：`20261002-063734-f1b61ec5`，首次1010/1010、最終1052/1052工具與參數相同。
- repair-01：`20261002-063635-6ebeddef`，首次1115/1115、最終1157/1157相同。
- 分母只含雙方都有有效可讀決策，排除不算一致；後者1161份有效raw決策含舊105題，
  不等於1160筆recorded產品量測。兩份均因舊批次不完整／scorer依賴樹改變保留
  incompatible_or_unknown，不宣稱同source五模型全量重現，也不修改guard或舊scores。

独立最終覆核已直接核對五child／runner退出、完整分母、Gemma真停止、audit及比較語意，
無阻擋。此授權scope-complete；交回完整結果，下一轮需另討論，不追加推論或merge。
本機settings.json仍為使用者修改；封存後本頁及外部三份論文文件補記不改sealed source。
外部結果、修理原因、完整指令與限制已寫入`碩論準備/實驗/DEV階段紀錄/DEV第3輪總結與第4輪改善計畫.md`。

封存修理ac6→781新增/刪除/淨：產品215/22/+193、測試783/1/+782、腳本57/0/+57、
文件107/10/+97、設定/其他0，合計1162/33/+1129，二進位0。
分支對main72548c累積：產品220/23/+197、測試2265/4/+2261、腳本1624/83/+1541、
文件552/10/+542、設定/其他0，合計4661/120/+4541；含先前多輪，不混為本次。
測試／腳本經focused、native、CI與獨立覆核；文件CI及外部入口核對，設定未改。
以上不含封存後文件與臨時診斷；完整結果不代表永久無缺陷、跨環境重現或整個DEV完成。

## 已交回 — DEV第4輪退出修理與全量重跑已啟動

使用者已授權修好後續跑，並明確改為全部重跑以檢查可重現性；不僅續跑Gemma。
證據：run `20261002-024229-8b91f51c`完成1056/1320，Llama264題與condition結果寫完後
子程序returncode=-11(SIGSEGV)，hard_timeout=false、cleanup_ok=true；runner按fail-closed
停止，Gemma未啟動。原失敗log無Python traceback/native stack；後續有界probe已取得定位證據，見下。
Outcome：有證據的退出修理及直接／原生驗證；完整1320新run啟動、初始紀錄正常後交回。
Scope：退出生命週期、直接回歸與必要crash診斷／研究封存；保留失敗run及既有1056筆。
Non-goals：不改提示、模型／revision、生成、RAG、題庫、scorer、Host決策或重試；不啟動第5輪、
VALID／TEST，不改可見UI或merge。不忽略SIGSEGV或用強制exit假裝成功。
先以最小有界原生probe定位，診斷推論若不可避免另標工程證據，不混正式分母、不依分數調候選。
步驟：追退出／捕捉stack→可重現保護與修理→focused與原生exit驗證→獨立覆核／適用CI
→以可追溯修理source封存同一提示候選（不覆寫旧快照）→全量新run→驗初始capture與進度。
假設：137資源仍可用；禁止修改凍結source／舊manifest來蒙混身分；先核對封存對應方式。
可重現性：新run完成後與失敗run共同1056筆比對；Gemma缺舊結果，不能稱五模型全量已重現。
Stop：修理證據與同版本驗證閉合、全量重跑有效啟動後交回，不持續監控整輪；不自行加跑第二整批。
已定位：137原版load/READY/close最小probe三次中第三次SIGSEGV；gdb另一次重現
`sip_api_get_address → cleanup_qobject → cleanup_on_exit → Py_FinalizeEx`，位於PyQt退出清理。
首次診斷probe缺spawn main guard而逾時，屬probe錯誤，保留但不算產品重現；修正後才取得上述證據。
兩項Windows回歸先red：close只隱藏視窗、第一次失敗後錯誤鎖定closed。修理重用Qt drain，
以accepted close的WA_DeleteOnClose完成原生銷毀，成功才標closed；不跳過MainWindow關閉政策。
首次修理原生三次正常exit0且window_destroyed=true；非永久穩定保證。獨立覆核另找到延後銷毀
後再次close存取已刪Qt timer，已補red與刪除感知的重試；最終59項Windows直接測試、
changed-file Ruff/format通過，獨立source覆核解除阻擋。精確版本原生退出與CI結果見下。
封存使用既有create_package建立`stages/dev/round-04/repair-01`，保留candidate4與舊父入口；
新完整source/manifest/run獨立，不偷偷重指舊版，不計第5輪，不自動納入父DEV aggregate。
最終source `ac6f02553de5b11008694003bbdb513036c2a473`，PR #155，未merge。
同head CI全completed：22success／5 scope skips；137精確source三次Llama原生退出均0，
window_destroyed=true。獨立reviewer直接核對stack／logs／乾淨source與腳本hash，無阻擋。
封存與環境check通過，175舊封存檔／11舊run身分／失敗run10625證據項目保持不變；
獨立覆核新package hash、五模型candidate4共1320唯一DEV jobs及固定因素等價。
新run `20261002-035756-8b73ad40`，位於`stages/dev/round-04/repair-01/runs/`；
tmux `xbl-dev-round04-repair01-ac6f0255`，log `.runtime/logs/dev-round04-repair01-ac6f0255.log`。
GPU空閒後單次啟動，觀察61→120/1320；最初10筆真capture／system／RAG／hash／cleanup通過。
只支撐有效啟動，不代表整輪完成或五模型結果已重現；完成後共同1056筆方可做一致性比對。
獨立package沿用原leaf adapter，沒有父batch每5秒的進度列；不以空log判停滯，可用既有
`assistant_experiment_progress.describe`讀同一run的condition summaries。沒有改動正在跑的版本。
工程證據另在`results/engineering/round4-repair01-ac6f0255/`；外部論文文件與一行指令已同步。
Next：依約停止啟動監控，待使用者要求查結果／比對；不自動重跑第二批或調整候選。UI無改動。
本頁是凍結後交回記錄，remote sealed source仍乾淨；本機settings.json仍為使用者修改。

修理commit相對dd2a5e75（新增／刪除／淨）：產品0/0/0、測試92/0/+92、腳本26/10/+16、
文件51/2/+49、設定/其他0，合計169/12/+157，二進位0；文件含開工前未提交交回記錄。
分支相對main72548c累積：產品5/1/+4、測試1482/3/+1479、腳本1567/83/+1484、
文件451/6/+445、設定/其他0，合計3505/93/+3412，二進位0；不混為本次修理。
以上限封存repo差異，不含本頁凍結後補記、外部三份論文文件與臨時工程probe。
測試／腳本經focused、native與CI及獨立覆核；文件CI通過，外部入口另核對；產品／設定本次未改。

## 歷史 — DEV第4輪首次量測（後續1056/1320退出失敗）

使用者已讀完並批准`碩論準備/實驗/DEV階段紀錄/DEV第3輪總結與第4輪改善計畫.md`
第五節，要求修改後正式開跑。R3完整1320筆：Granite4多物件、Gemma操作變文字承諾、
Phi／Llama當前參數與參考值混淆、Granite3.3依賴格式重試；既存錯答及原始證據全部保留。
Outcome：五模型各固定candidate4，完整source/config封存；正式1320筆初始紀錄與進度正常。
Scope：研究提示及直接相關測試／文件／封存接線；Granite4以R2、Gemma以R1提示起步，
Phi／Llama／Granite3.3以R3起步。共用runner與產品不回退，不改模型／生成／RAG／題庫／
scorer／Host／parser／一次重試，不碰VALID／TEST；不改UI、不merge、不自動開第5輪。
假設：137共享環境與模型仍可用，推論前確認GPU空閒；settings.json保持原樣。
步驟：提示保護與實作→focused驗證→完整輸入與五模型精確tokenizer→獨立source／輸入覆核
→同head適用CI→追加round-04並驗旧封存不變→正式啟動與初始capture／進度驗收。
驗證：profile只依model_id選擇；schema／membership／blocker／state／RAG／current_user
不變；移除示意只影響Granite4／Gemma；第1–3輪檔案／配置／run身分不變。
Complexity：重用研究assembler和append_round，產品LOC與owner不增加；不新增控制層。
不額外推論smoke、不按分數反覆改候選；本次授權正式五模型各264筆、seed0／repeat0。
Stop：同版本驗證、獨立覆核與封存完成，run產出有效初始量測及正常進度後交回；不監控到結束。
進度：13項預期red後42項提示保護及27項session接線均通過；Ruff通過，產品程式未改。
獨立source覆核找到開窗參數條件句歧義，已改為即使提到窗內設定也固定{}，覆核解除阻擋。
修改後69項與Ruff重驗通過；UI無變更。
已凍結source `dd2a5e75cc2db782a33590e40399b861371398d8`，PR #155未合併，承接#154/#153。
137暫存source為`.runtime/round4-stage-dd2a5e75/source`，完整來源clean；工程證據在
NAS根`results/engineering/round4-dd2a5e75/`，prepare／append及正式啟動已完成。
66真fixture／1320輸入及五模型精確tokenizer初次/潛在retry全過，最高2953/7680，RAG未裁切。
兩位獨立reviewer完成source／實際輸入／配置artifact覆核：五模型七stage及另選六個缺值／
不操作要求，無阻擋；固定因素不變。輸入為既存capture重播，不冒稱fresh retrieval或準確率。
同head CI全completed：22成功、5 scope skip；GPU空閒後追加round-04並單次啟動。
169個舊封存檔／10份run身分不變，第1–4輪環境check通過；未覆寫歷史source或結果。
正式run `20261002-024229-8b91f51c`，log `.runtime/logs/dev-round04-dd2a5e75.log`，
tmux `xbl-dev-round04-dd2a5e75`。已觀察8→17/1320，初始10筆recorded／cleanup／live system
及capture hash／RAG核對通過。只證明初始量測正常，不稱整輪完成或準確率提高。
Next：依約停止監控，待使用者要求查結果／討論第5輪；不重複啟動，不自行調提示或開始第5輪。
重跑入口：NAS根`stages/dev/round-04/./run.sh`；外部實驗README／計畫與指令已同步。
只留本頁凍結後記錄dirty，settings.json仍為使用者修改，未merge。

封存diff相對R3 e6d10a9f（新增/刪除/淨）：產品0/0/0、測試38/4/+34、腳本44/13/+31、
文件62/3/+59、設定/其他0/0/0，合計144/20/+124；二進位0。文件含未提交R3交回／分析，
非全為本次新寫；本頁凍結後及外部文件另計，不混入候選source。
分支對main72548c累積：產品5/1/+4、測試1390/3/+1387、腳本1541/73/+1468、文件402/6/+396，
設定/其他0，合計3338/83/+3255；包含之前封裝/R2/R3。產品本輪未改，測試/腳本經focused、
同headCI與獨立覆核；文件MkDocs通過、外部連結核對，設定未動。不評回答品質，未做VALID/TEST。

## 已完成 — DEV 第3輪結果分析

第3輪run `20261002-011825-eeb4bce1`已完整1320筆，exit 0、非partial、cleanup通過。
source為`e6d10a9f11221d3dd0ba320088bb191c65b709ac`；未merge、未啟動第4輪。
依使用者「跟上次一樣」只分析既有證據並整理外部論文文件，未改候選或新增推論。
文件：`碩論準備/實驗/DEV階段紀錄/DEV第3輪總結與第4輪改善計畫.md`；實驗README已有入口。
首次正確847→684→927、最終894→808→979；分清工具／參數／封裝及重試救回，
不將Clarification／No-call分數稱為回答品質。核對saved scores與代表完整輸入／原始生成，
獨立分析另驗Gemma／Granite3.3三輪1584份request/result配對hash；未重新判分或讀VALID／TEST。
候選草稿：Granite4以R2、Gemma以R1提示起步，其餘以R3；只選各模型主要弱點，
不更動RAG、Host、parser、scorer或重試政策。後續批准與施工狀態以本頁active section為準。
本次僅文件更新；產品、測試／fixtures、腳本、設定與二進位均無修改，settings.json保留。

## 歷史交回 — DEV 第3輪逐模型提示呈現與正式啟動

使用者已批准第2輪總結所列五模型改善方案，要求移除草稿／待確認狀態、實作並正式開跑。
證據：第2輪1320筆完整結束，首次正確847→684、最終894→808；完整封裝與操作／回覆混淆
因模型而異，不能將共同文字呈現視為各模型最佳起點。外部詳細計畫位於
`碩論準備/實驗/DEV階段紀錄/DEV第2輪總結與第3輪改善計畫.md`。
Outcome：每模型固定一套candidate3；Granite4／Llama以R2提示起步，Phi／Gemma／Granite3.3
以R1提示呈現起步，明示完整JSON輸出及操作／回覆邊界。共用runner與產品修復不回退。
Scope：研究提示呈現、直接測試與封存／文件；不改模型／生成／RAG／題庫／scorer／Host／
一次格式重試，不讀VALID／TEST，不改UI、不merge、不新增推論或通用控制層。
授權正式五模型各264筆（共1320）；本輪不額外跑20題工程smoke、不暗中搜尋或重跑候選。
假設：137既有環境／模型／GPU仍可用，部署前核對；settings.json保持原狀。
步驟：提示與baseline保護→focused tests→五模型完整輸入及tokenizer預算→獨立程式／
研究契約與實際輸入覆核→同head適用CI→封存完整source/config並追加round-03→正式開跑。
驗證：工具schema／membership／blocker／RAG／當前請求不變，完整輸出例合法，模型選擇
不依case/oracle，舊round1/2及證據不變；五模型candidate3與完整source身分可追溯。
Complexity：產品owner與預計production LOC均不增加，重用assembler純呈現hook與append_round。
Stop：正式run已產生有效初始紀錄與進度，交付run/log/一行重跑入口即停止監控，不等跑完。
進度：已實作逐模型baseline與公開契約完整JSON示意；產品程式與固定研究因素未改。
提示保護先重現26項預期失敗再通過37項；獨立source／契約覆核無阻擋，仍待實際輸入覆核。
相鄰接線三項舊測試已同步已批准的逐模型目錄；159項直接測試均已有green證據，Ruff通過。
凍結source `e6d10a9f11221d3dd0ba320088bb191c65b709ac`，PR #154未合併，承接PR #153。
同head CI 22成功／5 scope skip，全completed；兩位獨立reviewer均完成實際輸入覆核、無阻擋。
66真fixture／1320輸入通過；五模型精確tokenizer重播全部初次及可能retry，最高2993/7680，
RAG未裁切。重播採原capture，不冒稱新檢索；正式初始10筆另驗live RAG／system／原始檔hash。
NAS已追加round-03；163舊封存檔及9份歷史run身分不變，round1/2/3環境check皆通過。
正式run `20261002-011825-eeb4bce1`；已觀察9→39/1320且初始10筆recorded／cleanup通過。
初始驗收probe曾誤將trace鍵值對序列當dict；修正唯讀解碼後相同內容核對通過，原probe保留，
未改候選、未追加／重跑模型。這不是完整量測或準確率改善宣稱。
NAS根`/mnt/home/2025/hxin/XBrainLab-experiments`；log `.runtime/logs/dev-round03-e6d10a9f.log`，
工程證據`results/engineering/round3-e6d10a9f`；重跑入口`stages/dev/round-03/./run.sh`。
當時依授權停止監控；後續第3輪完整結果及下一步以本頁頂端為準，不自動跑第4輪。
完整研究快照乾淨；本頁交回記錄在凍結後補記，非候選程式改動。settings.json保持原使用者修改。

封存diff相對第2輪d2e679c2（新增/刪除/淨）：產品0/0/0、測試91/15/+76、腳本91/17/+74、
文件63/8/+55、設定/其他0/0/0，合計245/40/+205，二進位0；文件包含開工前未提交的R2交回
記錄，不冒稱全部本輪新寫。本頁凍結後記錄及外部論文文件另計，不混入研究candidate。
分支相對main72548c累積：產品5/1/+4、測試1356/3/+1353、腳本1510/73/+1437、
文件343/6/+337、設定/其他0/0/0，合計3214/83/+3131；含先前封装、報告、R2，不是本輪淨增。
產品本輪未改；測試／腳本經focused、同head CI及独立覆核，文件MkDocs通過，設定未動。
當時限制：啟動驗收不是完整run驗收；後續已完成結果分析，仍不評回答品質、未做VALID／TEST或merge。


## 已交回 — DEV 第2輪正式量測已啟動

使用者認同共同調整→逐模型重點，要求覆核並提出做到137正常開跑即交回的實作計畫。
唯一施工順序由本頁追蹤；詳細候選/步驟見`碩論準備/實驗/DEV階段紀錄/DEV第1輪問題討論.md`
第五/六節。已核對研究規格及實際接線，獨立覆核指出schema資訊保留、精確model_id注入、
preflight五模型覆蓋及RAG預算需驗；計畫已納入。現有封裝入口缺新增輪次操作，列直接依賴。
Outcome：共同文字呈現＋五模型短提示，固定candidate2/source；經驗證封存部署137，
新增本輪固定20筆工程驗證後啟動完整1,320筆，確認進度/有效初始case落盤即交回。
版本方式已獲使用者確認：共用程式，依精確model_id選固定提示；五套提示各自演進，
每模型每輪綁定完整source/提示/配置，不走五條長期分岔的產品分支，也不只封存提示。
Scope：提示呈現與直接必要的研究接線/封存/測試/文件，不改模型、生成、RAG、
scorer、題庫、Host政策與一次格式修復；不讀VALID/TEST，不調UI。
假設：共用資源仍可用、137GPU可用；實際部署前重查。第五節防退步是分析項，不是重跑門檻。
驗證：schema/工具membership/blocked reasons/上下文/五模型profile/預算等價，source與
oracle/scorer可比較、舊round1完整性、focused tests及適用CI、獨立輸入/程式覆核。
Stop：正式run初始有效量測與進度正常，提供run/log/重跑入口後停止監控，不等整輪結束。
使用者已授權本計畫施工、固定20筆工程驗證及正式開跑；要求開跑前多位獨立reviewer
核對實際程式/研究契約/完整模型輸入。已按本輪授權執行，不援引R1舊review代替本輪。
Next：等待使用者下一次要求查結果／分析；不持續監控，不追加推論或啟動第3輪。
UI不變；settings.json保留不動。未授權合併，不將啟動成功誤報為整輪完成或準確率改善。
進度：139項Windows focused回歸通過；Linux封裝22＋package/shared33項通過，Ruff全庫通過。
新增round獨立review通過，另做第二次move故障注入，舊round仍可執行且可重試追加。
最終source `d2e679c2269c2edcd56698a0cdf30b5b332237b5`，PR #153未合併。
同head CI：22成功、5 scope skip，全completed。66真fixture／1320份完整輸入通過；
五個精確tokenizer重播全部初次與可能retry，RAG/state/request原文不裁切；最大retry2157
tokens < 7680。所有scorer/frozen依賴未改。三個獨立審查面向均通過；輸入review抓到
禮貌問句與資訊問題的歧義，已在推論前修正並重新產生全部capture，沒有用分數調提示。
NAS已追加round-02；157舊封存檔、8歷史run身分保持不變，round1/2 check均通過。
固定20工程案例完整，exit0；23份prompt/raw captures及五模型CUDA/cleanup由獨立review
核對。模型錯答保留為有效量測，不拿工程成功宣稱全答對。沒有額外smoke或候選搜尋。
正式run `20260930-132737-274c0afd`，只跑round-02五模型candidate2共1320題。
已確認進度30→56/1320，直接核對前10筆recorded、trace與cleanup；不是整輪完成宣稱。
NAS根`/mnt/home/2025/hxin/XBrainLab-experiments`；log為
`.runtime/logs/dev-round02-d2e679c2.log`，工程證據為`results/engineering/round2-d2e679c2`。
手動重跑入口`stages/dev/round-02/./run.sh`；目前正在跑，勿重複啟動。外部實驗文件已同步。
Complexity：產品僅原樣預設呈現hook（+5/-1），沒有新增owner；研究呈現與追加輪次重用
原assembler/packager/runner，沒有新state、scheduler或評分機制。原始證據不覆寫。

封存候選LOC（新增/刪除/淨；不含settings；二進位0）：相對da137366，產品5/1/+4、
測試353/2/+351、腳本330/14/+316、文件57/3/+54、設定/其他0，合計745/20/+725。
此基準含開工前已討論但未提交的計畫文件，不冒稱全為本次新寫；本交回記錄另計。
分支對main72548c累積：產品5/1/+4、測試1280/3/+1277、腳本1436/73/+1363、
文件288/6/+282、設定/其他0，合計3009/83/+2926；含先前封裝/進度/比較報告工作。
產品/測試/腳本由focused與同head CI覆蓋，文件MkDocs通過，設定無改動；實際模型準確率
與全輪完成仍未知，未做VALID/TEST、未評回答文字品質。外部文件不混入repo LOC。

## 已完成 — DEV 第1輪唯讀交叉分析與討論筆記

依使用者要求，問題整理於`碩論準備/實驗/DEV階段紀錄/DEV第1輪問題討論.md`，README有入口。
以run B `20260930-075129-46512761`保存證據核對1,320筆判分，按題組讀錯誤輸出及
代表上下文/修復；區分已確認現象、因果假設及未批准改法。五模型分型/平衡率、錯誤
分類、92次修復與47筆救回、案例ID及連結已直接核對。不宣稱人工逐讀所有重複prompt。
僅寫討論文件，無產品/UI、題庫、scorer、RAG或原證據變更，未讀VALID/TEST、未推論。
第五節已補共同調整→五模型個別重點/防退步項，皆為待討論候選，不代表施工批准。
沿用使用者搬移後位置並修相關連結；五模型數值、Phi修復、文件連結與固定因素已核對。
Next：共同討論第2輪的工具資訊/提示呈現；尚未批准候選、實作或開跑。不另產分析報告。

## 已完成 — 可讀的重跑比較報告

使用者確認中文報告樣式：結論→比較表→數字解釋→版本差異，明示不新增cases.md，直接開既有檔案。
Outcome：compare.sh產生可讀comparison.md，連到比較JSON與兩次既有報告；本次結果重產並下載Windows。
Scope：既有比較器的純Markdown呈現，不改比較/判分/schema；不推論，不改原run或舊source。
不因工具一致率100%宣稱答對100%，不因版本不同自動判新候選，也不替差異寫未驗證的原因。
步驟：相同/不同/不可比的真fixture測試→呈現收斂→focused回歸/review→新快照部署→真結果比對/下載。
Stop：主報告易讀且結論對資料成立、JSON指標未變、NAS新入口可用、Windows副本完整。
UI：報告文案/排列已確認；無桌面UI變動。Owner無增加，產品0；只抽純renderer以隔離呈現。
Next：先保護一致率/正確率與不可比較分母，再實作。
進度：比較JSON與數值不變，主報告約52行；相同/差異/缺證據測試通過。依最新要求移除cases.md生成。
獨立review重現未知source metadata會中止呈現，已red→green修復並獨立覆核通過。
精簡後比較/封裝40項通過，共用環境10項沿用未改動的前次通過證據；Ruff與獨立覆核通過。
NAS coordinator為353b53df65a2bd3e70644d5483c7e89959762e6a，無推論check通過、19份設定/run
manifest未變。真實報告results/comparisons/20260930-103303-62a13c5b僅含comparison.md/json，
主報告59行，既有證據連結均有效；JSON SHA256與舊比較完全一致，原始證據未变。
Windows下載/XBrainLab-comparison-readable已放主報告與原JSON並開啟；下載副本連本機JSON，
NAS原報告路徑另列，避免搬到Windows後留下失效相對連結。沒有cases.md。
本次含cases.md的未交付草稿已核對JSON一致後刪除；先前正式比較與原run保留。
Next：進入第1輪結果分析討論；未push/PR/merge，未啟動新推論。

## 已完成 — 新進度入口重跑與真實結果比對

使用者要求上一輪完成後用新脚本再跑並測比對；唯讀確認舊run
20260930-070700-24d44eac五模型各264題、runner/launch exit0，且使用者已啟動新版run
20260930-075129-46512761，coordinator a08d7f38，1320題同配置，仍執行中。
Outcome：沿用正在執行的新版run；先用compare.sh實測基準→上一輪，完成後自動比上一輪→新版。
Scope：只執行既有比較入口、寫獨立comparison結果及本次背景操作log；保留舊證據，不開重複推論。
驗證：原run退出/cleanup/排程完整、逐題可比較性、原始證據不變、差異/不可比較如實列出。
背景等待只觀察這個run與既有PID，完成/失敗後結束；不介入實驗程序。不改產品/scorer/題庫。
Stop：當前基準比較可用，背景後續比對已安排且新版仍有進度後交回；不持續監控整輪。
UI：無改動；此為第1輪重現核對，不新增candidate/DEV輪次。
2026-09-30核對：基準→上一輪compare.sh exit0，報告results/comparisons/20260930-075707-7ed27438。
1320題first/final正誤均無改善/退步、unavailable0；final工具/參數1308/1308一致，12無有效
decision如實不可比較，原始證據未變。classification為candidate_comparison，列出的差異
含coordinator版本及搬移後config/models/environment路徑，不改寫原證據或強稱配置逐位元相同。
新run已完成granite4 264題、進入granite33，無需另啟重複推論。tmux背景工作
xbl-compare-20260930-075129觀察精確runner PID606707；成功退出後執行上一輪→新run比較，
失敗/無唯一end紀錄/逾6小時則明示停止，不比較不完整量測。log：
.runtime/logs/compare-after-20260930-075129-46512761.log。已確認session存在且log記錄等待。
新版run五模型各264題、exit0；自動比較exit0，報告20260930-082651-56dff1cc。
1320題first/final正誤一致，final工具/參數1308/1308一致、12不可比；原證據未變。
Next：可進入第一輪結果分析；不主動開下一candidate。未push/PR/merge。

## 已完成 — 實驗終端進度顯示

問題：137正在執行的Round1逐題結果已寫入，但child stdout/stderr只存log，終端只有輸出路徑。
Outcome：既有./run.sh顯示準備、目前模型/題數、總題數、耗時與最後exit；不把已處理誤稱答對。
Scope：封裝入口唯讀觀察既有manifest與condition結果，5秒更新；不改runner/題庫/推論/計分，
不新增進度state owner，不中斷或重新啟動使用者實驗，不覆寫舊source或run manifest。
步驟：真檔案/子程序進度red測試→薄顯示器→入口及取消/失敗回歸→獨立review→NAS新快照部署。
驗證：啟動/跨模型/失敗/部分寫入/產報告/取消，確認讀取不改原始結果；用既有實驗唯讀核對。
顯示故障不得終止研究程序；不掃模型或逐題大型檔案，不猜ETA。UI：CLI顯示已獲使用者同意。
Complexity：重用既有批次程序與condition identity；純renderer不是owner，產品0，腳本預計約100行。
Stop：新入口進度與真程序回歸通過、NAS可用且結果不變；本次不等1320題跑完。
進度：52項直接回歸通過，含真5秒更新、讀取中間態、broken stdout、失敗與取消；Ruff通過。
獨立review無阻擋項，另驗6項進度與3項SIGINT/SIGTERM/後續阻擋整合。
NAS coordinator已更新為a08d7f382cd9f5af63abf7127a30d3a1a5dfc675；新入口無推論check通過，
18份設定/run manifest hash未變，模型source仍d9182f19。真實現行run唯讀顯示473/1320，
沒有停止/重啟原程序。既有run不熱更新；下一次./run.sh自動顯示。外部文件已同步。
Next：使用者原run繼續，無需為顯示重跑；未push/PR/merge，亦未啟動新推論。

## 已完成 — NAS 根目錄直接採用約定結構

使用者糾正上一輪層級並明確要求「直接把舊目錄改成這個結構 NAS上的」。
唯一根目錄是`/mnt/home/2025/hxin/XBrainLab-experiments`，不是其reproducibility/experiment子包。
Outcome：根目錄直接呈現README/run.sh/compare.sh、stages、snapshot、results、.runtime。
Scope：先盤點舊目錄全部頂層與實際引用，將仍需保留的source/inputs/成功結果歸位；共用
模型/Python須保留並有明確固定位置，搬移後驗環境/入口。刪除只限已確認重複或本次施工
副產物；唯一舊研究證據保留，不把整個舊目錄藏進legacy/archive。原始結果manifest不改寫。
不推論、不開新輪、不改產品/題庫/scorer、不調ACL、不merge；D槽仅同步文件與指令。
步驟：引用/內容清單→確定各舊目錄去向→安全搬移及必要資源重綁→同root直接check與
離線證據核對→清掉已確認重複/空目錄→更新操作文件。新權限/不明獨有資料另報不擅刪。
Stop：NAS根目錄實際符合約定，直接入口可用且成功結果/共用依賴完整；不以子包通過冒充。
UI：無變動。產品owner/production LOC均0；重用既有封裝器，不新增控制層。
盤點：現有9個頂層；無推論程序，兩個shell停在根目錄，既有http.server 577755指向舊
成功run，不關閉。需使用者以新路徑重啟報告服務。active venv為system Python copies，
無外部symlink或私有路徑pth依賴；獨立封装review同意只改當前binding，不重建環境身分。
精確歸位：當前子包升到根；各歷史Git快照按SHA去重；原inputs/contracts/specs歸snapshot，
五個歷史工程run歸results/reference並標明非新DEV候選，獨有診斷歸results/engineering。
模型/Python/安裝資源移至同層XBrainLab-resources，active為models及python/experiment；
其他cache/wheels/舊環境只分類保留，本次不擅刪獨有資源。舊成功run僅在完整樹hash/link
與reference一致後刪重複；保留同ID但報告不同的工程搬移證據。只清已識別純code傳輸
壓縮檔與pytest快取，不把整個engineering改名藏起來。
進度：實際根目錄已只剩README/run.sh/compare.sh、stages/snapshot/results/.runtime；
10個獨立來源版本各一份、6份reference（5工程＋1正式），舊8個資料夾已移除/分類歸位。
根目錄round-01及DEV check通過，root/VAL/TEST拒絕如預期。現行env保持原154套件身分，
只重綁路径並修正venv產生的啟動文字；無套件升級。原成功run全樹hash/link一致後去重。
安全覆核要求的忽略檔檢查真的擋下兩份.test-tmp，未刪，均另移資源cache；1300項內容
匹配的workstation傳輸包刪除，未證明相同的smoke傳輸包保留snapshot/inputs/transfer-archives。
新位置的PyTorch/MNE/transformers匯入、offscreen QApplication及runner --help均通過；
真實1320題reference自比為same_config_reproduction，原始證據未變，正誤全部可比較且
沒有改善/退步；有效final工具/參數1308筆一致，12筆無有效decision如實不可比較。
獨立SSH實物覆核通過，無阻擋項；results/runs仍空，未啟動新推論。D槽文件已同步。
Next：使用者登入137後在stages/dev/round-01執行./run.sh；舊報告服務需自行停止後依
新根目錄重啟。VAL/TEST尚未準備，不宣稱整個研究已可執行；未push/PR/merge。

## 前版部署 — 單一可搬移 experiment（路徑已由頁首取代）

2026-09-30最新確認取代下方前版封裝：搬移單位是整個experiment，不是各round；
頂層README/run.sh/compare.sh、stages/{dev/round-01,val,test}、snapshot/{sources,inputs,
environment,manifest.json}、results/{reference,runs}與隱藏.runtime。每個distinct commit只
存一份完整source；各層run.sh引用同一封存程式，不再各存batch-source或各round一套source。
Outcome：137的Round1可用一行重跑、結果分開保存、可離線比較原成功1320題結果；整包搬移
含中文空白路徑可檢查。DEV固定僅round-01；root含未準備VAL/TEST，整體先拒絕不部分偷跑。
Scope：既有封裝/批次入口收斂、直接回歸與獨立覆核、部署及本機結構/指令文件；
使用者明確授權刪除失敗run 20260929-115803-8477ba6c，先核對精確manifest與無使用中。
保留成功run 20260929-152153-64a2c9c8、仍共用的模型/Python；不開推論、不改題庫/判分/
產品UI、不調權限、不merge。前版本agent產生且無研究結果的多重batch-source樹於新包
驗證後清除；不清其他歷史資料。成功reference原始manifest不改写，不冒充新環境新實驗。
假設：同Linux/NAS且共用固定環境/模型可讀；跨帳號權限未驗證，不作本次阻擋或暗自chmod。
步驟：核對配置/比較器路徑→真Git/shell搬移/去重回歸→替換舊批次封裝→獨立review→
137無推論check及reference自比→精確清理失敗run/本次過期中間包→同步文件/重跑指令。
Stop：上述已授權成果與直接證據閉合；不等待下一次推論完成、不宣稱新DEV已重跑。
UI：無產品UI變動；目錄與CLI已批准。中央snapshot／scope／結果已實作；88項封裝、
shared/portable與比較回歸通過，Ruff與MkDocs strict通過，獨立覆核無阻擋項。測試的昂貴
推論runner以fixture替代，真Git/shell/venv/搬移/訊號/比較器都有跑，不當成1320題重跑。
部署coordinator為`9ddcfec8f4ea4bb0a39a60480a5b93ae1d8f0c0b`；五模型source仍d9182f19。
137路徑為`XBrainLab-experiments/reproducibility/experiment`，實際僅兩份source快照。
round-01及DEV check通過，root/VAL/TEST明示blocked。暫移中文空白路徑後check與真實
1320題reference自比通過：correctness unavailable=0、無改善/退步，原始證據未變；
有效final工具/參數1308/1308相同，12筆無有效decision仍如實不可比較，不說模型100%正確。
新research run為0；成功原run留原位並逐檔核對複製reference，沒有改寫其版本/路徑。
失敗run已永久刪除（約399MB，NAS開啟鎖檔先阻止rmdir，關檔後空目錄已移除）。
已核對舊shared-baseline無研究run/batch結果後刪除，部署暫存亦已移除；必要模型/環境保留。
沒有新推論/PR/push/merge；共享資源權限未改，其他帳號仍需通行權限。
Next：使用者以文件中的一行指令自行重跑第1輪，完成後比較，再討論下一輪；不自動開跑。
Complexity：runner仍唯一擁有admission/journal/cleanup/scoring；package仍封存owner，batch
只作範圍/順序委派。刪除每節點batch-source/遞迴package封存，重用Git snapshot、runtime
隔離和runner；不新增排程器/評分owner。產品0；脚本預估重寫300–500行，rollback以Git
小commit為單位，不改原成功封存。保留v1-v3因有真實歷史包；未使用的新批次格式不加相容層。

## 前版交接 — 實驗結構與工作站操作文件（已由頁首取代）

使用者確認只需結構與既有重跑指令，不新增Windows啟動器。文件位於
`D:\workspace_v2\projects\lab\碩論準備\實驗\README.md` 與 `重跑指令.md`。
環境準備與既有 `run.sh`／`compare.sh` 分開說明；本機題庫編輯稿不替換封存輸入。
未啟動新run、未修改遠端封存包／環境；未授權下一輪改善。下一步依使用者討論決定。

## 前版 — 共用唯讀資源與分層實驗入口（不再作施工目標）

2026-09-30使用者連續確認方案並同意施工：同工作站／NAS，完整程式與題庫／設定隨每輪
封存，模型與Python共用唯讀；root／DEV／round／VALID／TEST各層相同`./run.sh`，
上層只按明確固定清單呼叫下層，不掃目錄猜範圍、不自動調參／選版／解封TEST。
目前問題：v2須手貼環境變數且綁定原帳號可寫位置；v3每副本重建環境並複製模型，
不符合本次共用資源需求；尚無固定範圍的分層入口。TEST實際執行協定仍未實作。
Outcome：固定共用環境的可複製封存包、自動環境／cache隔離、明確範圍的薄批次入口、
新run不覆寫及可追查索引；文件含DEV五輪／VALID三次／TEST消融的封存與實際能力界線。
Scope：既有packager/bootstrap及直接測試、封存／本機文件；不改產品UI／Agent／scorer／
題庫／模型、不覆寫舊包或原結果、不啟動正式推論、不變更他人權限／建立帳號。
TEST與未封存輪次以阻擋理由拒絕；目前整體範圍不能冒稱完整研究已備妥。
假設：共享資源對接收者可讀／執行，輸出在接收者自己的可寫副本；實際跨帳號權限需
讀取檢查，無帳號／權限時不能冒稱跨帳號驗證通過。Python／模型不原地升級。
步驟：固定文件與complexity review → 真Git／shell／檔案的red測試 → 共用環境與薄批次
入口 → focused regression與獨立覆核 → 137唯讀資源及無推論check → 本機文件交付。
Stop：授權入口／文件與直接驗證閉合；部署需要新權限時明示，不把待決權限藏在操作文件。
UI確認：無產品UI改動；CLI分層入口已獲確認。Next：先寫可觀察的封裝／批次回歸。

進度：v4共用環境與固定批次入口已實作；75項真Git／shell／venv與既有v2/v3回歸通過，
Ruff通過。獨立覆核重現cache巢狀symlink可回寫外部，已red→green修復並獨立覆核通過；
批次後續leaf不可寫亦已先重現再修復。這些測試替代昂貴模型runner，沒有推論證據。
137權限只讀核對：`XBrainLab-experiments`及舊工程包`.runtime`的group/other均無通行，
且沒有ACL例外；不自行chmod。程式固定於`22b60ac0`，新獨立封存樹位於
`/mnt/home/2025/hxin/XBrainLab-experiments/reproducibility/shared-baseline-22b60ac0`。
137葉節點及DEV的check-environment通過；VALID／TEST／root明示blocked，舊run清單不變，
新樹沒有研究run或batch結果。MkDocs strict通過。D槽結構／指令／三階段封存文件已同步。
仍未scope-complete的跨帳號使用：需指定接收帳號／群組並核准最小通行及唯讀資源權限；
目前不能宣稱接收者可執行。Next：使用者決定ACL對象／範圍後完成真正接收者check。
沒有建立PR、push／merge或啟動研究量測；新封裝工程檢查不冒稱1320題重跑或CI通過。

Complexity review：現有run_assistant_dev／case runner繼續擁有admission、journal、cleanup、
scoring；新共用資源適配不擁有實驗狀態，批次入口只選範圍順序與傳回exit，不另建resume
或評分政策。刪除候選：重複runtime環境組裝、手貼環境文档；不保留誤加Windows捷徑。
預估新增腳本約300–500行（共用資源與批次兩個可分離責任），產品0；不增產品owner。
必要性：共享環境核對與批次委派是兩個不同外部seam，不塞入既有大型packager；不新增
通用排程／服務／中央ledger。實際LOC與owner delta完工再核對，超出界線先重新review。

## 已完成 — 合併收尾修復，重跑 DEV 第1輪五模型

PR #152 已合併；新 run `20260929-152153-64a2c9c8` 完成五模型共1320題，退出碼0。
封存source為 `d9182f1922b9e80bc4fee647ef0d3657b274f915`；完成量測不代表全部答對。
下方保留該次修復與授權紀錄，不再作為待啟動工作。

最新授權：使用者選擇修正版全部重跑並說「跑吧」，依已說明順序完成必要CI、合併、
建立新封存source/run後在137啟動。五模型各264題、共1320題，仍是candidate1／DEV
第1輪工程修復重跑；seed0／repeat0、RAG on、一次格式修復、14400秒active預算及
18000秒外層wall guard不變。不調參、不改題庫／scorer、不開第2輪／VALID／TEST。
原run `20260929-115803-8477ba6c`曾保留894題及失敗證據，不拼接、不覆寫；
2026-09-30使用者另行授權刪除此失敗run，清理以頁首範圍為準。
重用137現有權重與Python環境，建立新source封存包，不重新複製38GB資源。
Stop：精確修復head所有適用CI通過、合併後新run最初有效案例正常落盤，即交回run/log
位置，不持續監控到全部結束。此次UI未改；不宣稱使用者新增手測證據。

2026-09-29 使用者要求定位後繼續修復，不停在診斷。Round1 已記錄894題，下一題
Llama DEV-A13-02-V2 在 fixture 訓練 admission 失敗，尚未提交模型；原失敗證據保留。
原因證據：fixture／case cleanup 只等待 owned operation terminal，沒有等待 training
terminal publication 與 monitor 退出；空資料狀態不代表 restart-safe。
Outcome：案例準備、清理與 reset 使用既有後端收尾事實，Qt 保持處理事件，未完成時
bounded fail closed。Scope 為 runner/fixture 及直接測試；不改 UI、模型、prompt、RAG、
題库、scorer，不覆寫封存 source／既有結果，不因工程修復占用下一輪改善機會。
步驟：延遲 terminal delivery 的真 CPU 訓練回歸先 red → 最小等待修復 → focused
fixture/condition checks → 獨立 lifecycle 覆核 → 核對 source identity 與可重跑方式。
Stop：修正與直接驗證、獨立覆核閉合；續跑若需跨 source 沿用結果而既有協定不允許，
明列決策，不暗改 manifest。UI 行為未改，不需新增 UI 確認。
進度：真 CPU delayed publication 回歸先 red 後 green，首批54 focused tests通過。
取消整合補測另重現直接依賴缺陷：ApplicationService.cancel_all_owned_operations只呼叫
registry.cancel_all，未轉送training/saliency runtime取消；10000 epoch fixture不能停止。
修理 scope 納入既有ApplicationService的bulk cancel，重用單筆取消，不新增owner或契約。
實作：bulk cancel重用單筆取消轉送；fixture completion/error cleanup與condition cleanup/
pre-reset檢查既有restart-safe，zero-timeout輪詢並持續處理Qt，不移除admission guard。
Windows focused：fixture/condition/owned registry/training state 96 passed；相鄰saliency
single/bulk cancel、shutdown、close、restart/publication 12 passed。三個red均確認：
舊fixture在ack前回傳、舊condition缺ack仍cleanup_ok=true、舊bulk cancel無法停止真CPU。
未使用真模型推論；原run與失敗證據未更動；不把工程測試當DEV完成或新版跨平台CI。
最終獨立code/lifecycle覆核無blocking finding，審查包含實際7個Python檔diff；執行證據
由主agent核對，reviewer未重跑。新增owner 0，產品service淨增4行，沒有新UI／契約。
Next：修復commit `a4aec703`加本次授權文件送PR，追蹤同head適用CI；核對137資源、
固定五模型新run配置與新source封存，完成合併後啟動。以頁首全五模型授權取代528題提案。
CI首次head `6b27fe90`：21成功，Windows lifecycle有一項既有刷新計數失敗；原失敗保留
於Actions run36585733302。獨立追查顯示測試只等eval/visualization到STOP_REQUESTED，
未等待Training自己的queued render便開始計terminal刷新數；bulk cancel僅teardown路徑。
直接修正驗證阻擋：先確定三面板preterminal都已render，再保留terminal exactly-once
斷言；不改產品、不放寬數量或timeout。CI失敗作red證據，本機原測試單次pass不能
排除此排程競態；修後重跑直接案例與同headCI。新source封存重建，未開始推論的舊
準備包只作中間產物；不以舊head成功項冒充新head全部通過。

## 已執行 — 合併工具PR，啟動DEV第1輪後交回

最新授權（2026-09-29）：使用者同意合併PR #151並開跑第1輪，要求確認正常啟動後
停止監控，不等待整輪結束。範圍為137上五模型各264個DEV、共1320案例；candidate1、
seed0／repeat0、RAG on、既定一次格式修復、14400秒active執行預算。不追加smoke、
跨機／跨帳號測試，不開第2輪／VALID／TEST、不調整模型／prompt／RAG／題庫／scorer。
步驟：提交本次文件收尾→精確head既有CI閉合→通知並guarded merge→核对137 GPU
與既有封存包／配置→使用既有runner背景啟動→確認進程、模型載入及最初有效案例落盤。
封存source及實際路徑保留在run manifest，不改寫原包或既有證據；文件收尾與merge SHA
不冒充封存source。已驗證副本可直接用於本輪，避免重複複製38 GB或無必要重建環境。
Stop：初始案例與raw／journal正常持續落盤後交回PID／run／log位置，不自動監控到完成、
不因錯答調參或重跑；若啟動失敗則先判明工程原因、保留失敗，不報成已正常開跑。
UI未改；保留settings.json、模型／環境／題庫／原始證據及正在使用的檔案。

### 已完成的可搬移實驗包準備與驗證界線

最新決定（2026-09-29，優先於下方原施工範圍）：使用者說明各工作站共用NAS，接受
以已在137完成的證據採用現有包，不再追加跨工作站、跨帳號或新環境推論驗證，也不再
以測試帳號／另一台工作站作收尾阻擋。使用目標是環境相容的實驗室Linux工作站，
137是已實測機器，不是hostname／IP准入限制；既有Python／平台相容性核對保持不變。
未執行的測試仍記為未驗證，不改標通過；不修改封存包、不放寬私人目錄權限。
該次僅固化驗收決定；後續merge及第1輪授權由頁首最新決定取代，仍不追加工程smoke。

2026-09-29新增使用者授權：在137使用NAS的另一帳號，將整包複製到自己的目錄後，
以`./run.sh`建立必要的本地環境並執行；不要求另設共用路徑。現有v2封存包只保證
已provision環境內重跑：Python symlink與模型設定仍綁定hxin的絕對路徑，私人目錄
權限也阻止其他帳號讀取。既有source／input快照不是可搬移安裝包。

Outcome／scope：沿用既有封存器與runner，加入同機Linux/Python固定版本的可搬移包；
包含獨立source、非TEST題庫、設定、已固定模型／embedding及離線環境安裝依賴。
包內相對路徑定位；首次執行在副本內建立固定環境，重跑重用；輸出／cache只寫副本。
不得複製credential、使用者settings或私人SSH資料；不分享hxin家目錄權限。
Non-goals：不改產品UI、Agent、題目、oracle、scorer、模型revision或研究政策；不啟動
正式DEV／VALID／TEST、不刪舊包、不下載新模型、不承諾跨OS或其他GPU工作站。
先前「不新建環境」限制僅對前一工程切片；本切片明確包含副本內首次環境重建。
尚未授權對外散布模型、建立系統帳號、sudo／ACL變更或正式DEV推論；若需要另提確認。

施工：盤點已安裝Python／依賴／wheel cache與runner資源路徑→先加搬移／離線首次
啟動失敗測試→新增bounded封裝／bootstrap→真137不同路徑（含空白／非ASCII）驗證
環境重建、資源核對、重啟、壞包拒絕與唯讀原包→獨立安全／封裝覆核與同head CI。
新環境使用現有固定版本與套件來源；缺少離線依賴時先確認下載清單與容量，不silent fallback。
不為新包重跑已用完的fixed20推論；先用不生成的preflight及既有結果離線比較驗工程。
另一帳號實測需要合法可用的測試帳號，目前未知；先完成不受阻工作，不以同帳號搬移
冒充跨帳號通過。最後必要真模型驗證範圍／額度另明列後取得確認。

Complexity review：沿用package為封存owner、runner為執行／journal／budget owner，
bootstrap只負責副本內環境建立與啟動，不新增評分或實驗排程owner。刪除候選是重複
shell entry生成與個人絕對路徑綁定；保留真實歷史v1/v2讀取，不原地修改舊證據。
若需新module限封裝環境責任，預估腳本+300–600 LOC、產品XBrainLab/零變動；實際
diff超出時重新審查，不藉generic installer/platform擴張scope。
Stop：可搬移包與直接測試／獨立覆核閉合，清楚區分同帳號搬移、跨帳號及真推論證據；
缺必要帳號／資源時報告具體阻擋，不宣稱完成、不開正式DEV。UI確認不適用。
進度：source `33f4d3fa6eac16d4e08cdd5627546716039d0417`實作v3可搬移包與離線bootstrap。
19個真Git／shell／venv／pip搬移測試、原封存23與比較17通過；輸出root／retained-run
symlink漏洞先重現後修正，獨立安全覆核GO。既有runner仍核對完整模型hash並擁有推論／
判分／budget。腳本本切片+560/-11/net549，tests+427；產品XBrainLab/未改。
137已確認154個已安裝套件皆有相容cached wheel（3,166,572,697 bytes），不需下載；
Ubuntu缺ensurepip，以封入的固定pip wheel離線安裝。私人NAS新包
`distributions/dev-round-01-portable-33f4d3fa`已建置成功（991.28秒），舊包不動。
實際複製到`engineering/portable-copy-33f4d3fa 空白`成功（1718.99秒）；首次離線安裝
388.16秒、重複檢查0.62秒、66 fixture／264 oracle預檢57.22秒、完整資源hash與1320-job
prepare-only 770.23秒，五步exit 0；另直接執行`./run.sh --check-environment`成功。
新環境154套件版本完全符合wheel inventory；五模型各264個DEV、candidate1／repeat0／
seed0，所有runtime source／模型／embedding路徑皆在副本。原包manifest未變、未生成
runtime，副本未建立runs；沒有LLM推論。模型及wheel約38 GB，不需新下載。
script／log／逐step結果位於`engineering/portable-build-33f4d3fa/`；本機小報告在
`build/dev-artifacts/portable-bundle/`。封存source固定33f4d3fa，後續文件commit不是重跑
推論證據；不重複整包複製、不覆寫bundle／驗證副本。
實機artifact獨立覆核GO（僅同帳號搬移／離線安裝及prepare，不外推跨帳號或推論）。
PR #151 head `a433a5055f1e2ecd3e98ef193487982deda02e67`已有22項non-skipped CI成功，
另5項scope skip；以上僅文件後續調整不冒稱已在該head執行。依頁首最新決定停止追加
驗證，不再索取另一帳號／工作站作驗收。原待確認的PR處置及第1輪授權已由頁首更新；
接續以Git／PR狀態與實際run manifest為準。

### 前一工具切片（已開PR，未合併）

使用者已授權工具PR；[#151](https://github.com/hxin-an/XBrainLab/pull/151) head
`bdc63837b2c6c0576825ec67aab4500bb14ee9c7`的22項non-skipped CI全部completed/success，
另5項依scope skip；base為`d4e54b628bd49d71fb2df73e7bbdf8b0c36efef0`。本次擴充後
舊head CI不能替新head放行。尚未授權merge或完整DEV執行。

2026-09-29使用者確認每模型五輪都完成、基準占第一輪，並要求每輪可一鍵執行，另有
一個腳本比較兩份結果；不是只對單份結果做audit。輪次、封存與比較契約由
[研究協定](../validation/thesis_protocol.md)擁有；既定四表輸出沿用，不另設報告系統。

使用者隨後確認新批次以本次已驗收產品基線加必要實驗工具準備作第1輪，舊d0保留歷史，
不拼接為新版成績。優先順序固定為：實驗工具準備→五輪DEV→VALID選版→TEST與三項
消融→再討論全面清理、UI打磨與非必要優化。這是工作順序與設計決定，不提前解封TEST
或略過各階段的配置凍結、執行範圍／額度確認。
實驗期間只修阻礙執行、判分／計時、證據完整性、可重現性或資料安全的必要問題；
不因模型答錯重開產品清理／RAG調參。修理若影響實驗來源，另建版本與run，保留原結果。
各輪的既定DEV調整不算另開泛用優化；VALID／TEST不因結果回頭調參。

使用者最新確認採逐輪討論，不授權agent連續自主完成五輪：先完成工具與直接工程驗證，
第1輪完整DEV開跑前交代精確source、配置、題目範圍及執行條件，取得確認再跑；每輪
完成後共同看結果／錯誤類型、決定下一輪調整，再封存執行。日常工具施工及focused
tests不逐次要求使用者介入；本次授權不包含完整DEV或任何下一輪模型調參。

原問題：`assistant_experiment_package.py`已有獨立source快照、`run.sh`及resume／report／
audit，但缺兩run比較；研究文件也仍混有舊wire／RAG敘述。本輪已補齊並以新source在137
工程驗證，不拿舊Windows d0或先前smoke冒充本次結果；没有新增執行／評分owner。

Outcome：已準備環境的137上，每輪固定程式、五模型各自設定、題庫、RAG／資源及scorer；
一鍵跑完本輪並產生新run。另一個入口唯讀比較兩份run，輸出決策／參數一致率、正誤
變化、時間差異與逐題明細，明列來源差異及缺漏；不重新推論或改原分數。
Scope：文件同步、既有封存／runner接線、bounded comparison與直接測試。
Complexity review：沿用runner／scorer／report原owner，比較器只讀已存結果，不新增評分或
執行owner。新增v2只為封存compare.sh；v1讀取分支對象是仍保留的真實歷史研究包，
不新增舊版執行fallback；只有使用者明確退役所有v1證據後才可移除。刪除候選是重複
launcher文字（共用同一shell前綴）；不刪有實際重現用途的audit或歷史reader。
Non-goals：不改可見產品UI、Agent政策、模型／prompt／RAG；不讀TEST、不執行正式DEV／
VALID／TEST、不新建環境或下載資源；完整跑分仍另在開跑前批准。
使用者已批准137固定20次工程驗證：五模型各4題（既定開窗／填參數／缺值／不操作），
累計最多60分鐘、不含資源複製；不依分數調參、不計DEV輪次。先確認共享GPU負載。

預定施工：先同步研究文件與最新契約／137環境，固定已確認新批次的精確基準與候選帳目；核對既有
封存器及所有caller→補兩run比較→用固定小樣本驗封存重建、續跑、不覆寫、報告與比較。
Focused validation：同份結果自比、工具／參數改變、錯變對／對變錯、相同錯誤、缺題／
損壞／重複ID、不同source／題庫／scorer／環境、首次與格式修復後、無可比較案例；
比較前後原檔hash不變，非操作訊息措辭不當成tool-call差异，不能將兩份缺失當一致。
封存驗證須證明不依賴開發worktree、資源被改會拒絕、新run不覆寫、續跑不重複計題。
Stop：兩個入口與可重現性證據完成且限制明列，準備第1輪開跑確認；不自動消耗正式額度。
進度：封存v2的compare.sh與唯讀兩run比較已實作，原runner／scorer不變；模型選擇仍在
封存前config擁有，不另增執行時覆蓋。初始封存19 tests通過；缺compare入口的2案red後，
封存23＋比較17通過，獨立diff／證據覆核GO。Windows相鄰runner／audit／report首輪150秒
逾時，定位為1,320筆合成fixture耗時；該案單獨100.81秒通過，其餘116案37.79秒通過。
Hook／guidance及strict docs通過；Windows比較17案亦通過。Script +701/-9/net692，
tests +551/-0；`XBrainLab/`產品程式無差異，沒有為smoke錯答調參。

137工程驗證source為`7a2fc9edcb3f2af743d6e268bc1df4a48be6d810`：66個初始狀態／264個
DEV oracle預檢通過；固定20次有效量測全部完成，首次／最終15對5錯、無格式重試，
active budget用88.34/3600秒。report-only、原版audit及自比通過，raw／inputs 179項
hash不變，獨立實機artifact覆核GO。舊v5與新v6比較正確標示不可直接比較正誤。
工程包：`/mnt/home/2025/hxin/XBrainLab-experiments/engineering/dev-round-tools-20260929-7a2fc9ed`；
run：`20260929-063418-83bfd335`。本機報告與核對副本位於
`build/dev-artifacts/dev-round-tools/`。這是工程證據，不是正式DEV準確率。

第1輪包已prepare但未run：`/mnt/home/2025/hxin/XBrainLab-experiments/development/round-01`，
同source、五模型candidate=1、各264題／共1320次、DEV repeat0、seed0、RAG on、一次
格式修復；config預算14400秒只是待確認上限，不是開跑授權。`prepared-for-discussion.json`
保存真環境／資源與完整排程。本機同名副本加round-01前綴；TEST未讀、VALID未評估。
另經使用者明確授權完成Windows本機SSH key與`ssh xbrainlab-137`別名，金鑰不進repo。

前一切片Next已由頁首可搬移包施工取代。接著共同確認第1輪版本、配置及完整執行
額度，才可run；不開始第2輪。
這是約定的討論交接點，不授權跳過PR／CI或自行開始完整實驗。

## Closed — Agent Development基線已手測通過並合併

2026-09-29使用者完成Windows手測並回覆「我實際測完了沒有問題」，接著明確批准
「同意 MERGE」。[PR #149](https://github.com/hxin-an/XBrainLab/pull/149)已合併至main，
merge commit為`97a76f7a478d3865220f6b99bbe9b365355370b5`；驗收head為
`ec646126ad5a8078d609d0ee72a737bdbdac1d05`，24項non-skipped CI全部成功。
驗收範圍是保留已知限制的Development單一英文要求基線，不包含複合需求、Stable或
論文準確率宣稱。產品事實由[Current](../current.md#assistant-research-baseline)擁有；
下方保留歷史施工與失敗，不再派工、不要求重跑或追加prompt／RAG調整。
後續研究準備依頁首新計畫，不回頭追加產品調參。

## 歷史 — Agent Development候選版集中手測交付（PR #149，已結案）

### 本輪整理範圍收斂（2026-09-29）

使用者在核對RAG組成及模型輸出後同意「就整理到這段」：維持161個英文單輪示範
（117個操作、44個回答／不操作）、BM25＋dense＋RRF及最多3個參考；輸入使用當輪
要求、後端狀態／工具與參考，不帶過去對話；模型只輸出`tool_name`與`parameters`。
不再擴充語料、增加多輪補值或追加prompt／檢索調參。這是本輪整理範圍的終點，
不表示下列模型決策失敗已修復，也不改寫歷史判分或授權merge。

使用者隨後明確接受「保留已知限制的Development候選版」交付，並澄清本輪開發目標
本來就不包含複合需求。Outcome是完整、單一英文要求的Windows集中手測候選，不是
Stable或任意工具要求皆正確的可靠性宣稱。複合要求不納入本輪支援／手測成功門檻；
既有拒絕複合要求的產品指引不改，失敗不重標成功。Reset漏執行、空資料epoch誤切panel、
不可用工具提案等非複合失敗仍明列為此Development版本的已知限制，不說成全部是scope外。
Scope／non-goals：僅同步current／target／validation及交付文件；不改產品、模型、語料、
prompt、工具或UI，不新增推論。沿用既有工程證據及已說明的parser等價性，不冒稱重新實測。
步驟／next：文件focused audit與strict build→提交既有PR #149→同head適用CI閉合→
Windows原生啟動及確認有回應→交付短清單與重開指令。測試使用可丟棄的working data，
保留原始資料與settings.json；PowerShell即時log，不另開Live Log視窗。
Stop：候選已開啟並交集中手測，或必要資源／CI新缺陷確實阻擋；手測通過與merge另待批准。
UI確認：不變更layout、文案或互動。此決策取代下方歷史「待接受限制」的阻擋。

### 前次授權與已完成檢查：依tool-call範圍整合驗證與凍結

2026-09-28使用者澄清「只有tool call準確率，沒有要審回答品質」，並批准架構／程式碼
足夠清楚後進行整合驗證與凍結。這是明示縮限驗收維度，不把舊完整回答失敗改標成功。
Scope：唯讀獨立覆核Agent decision/admission與Qt/runtime/RAG ownership；同步target／
validation／current的驗收界線；保留現有產品source、模型／prompt／RAG及固定題目。
不新增架構、不再為回答文案調參，不重跑既有52首答，舊report／scorer／失敗證據不改寫。
Outcome：同一確切版本可追溯tool選擇／參數／合法格式／正確不操作及實際執行、確認取消、
UI correlation／shutdown；回答完整度／措辭／知識性品質僅保留觀察，不作本輪阻擋。
Host擋錯不救模型分數；回答不能替代本來應執行的工具。真錯誤side effect仍阻擋。
步驟：兩個互補獨立source覆核；以既有capture核對20＋6題tool-only結果；一次74題
既有單輪廣度報告；Windows真模型ChatPanel四步及必要confirmation／cancel直接驗證；
精確head推送既有PR #149並追蹤全部non-skipped CI，通過後凍結SHA／模型／corpus及證據、
開啟Windows給集中手測。不是論文正式Test，不宣稱所有未知要求正確。
Validation：重用同產品source的52首答及相關工程tests，新增必要整合證據，不跑等價本機全套。
Rollback：本輪預期只改文件；具體整合defect依原owner做必要修復並重驗受影響證據。
UI確認：無layout改動，使用者已批准回答品質不作此輪gate。settings.json保持不動。
Stop：凍結版本及所有必要gate閉合並開Windows給手測；或重現tool/執行缺陷、必要資源缺失。
兩個獨立source覆核均GO：decision/admission／Command與Qt/runtime/RAG責任清楚，無確認
阻擋；大controller與少量RAG metadata重複只是後續維護項。另以既有capture獨立tool-decision
覆核：hybrid原20題20/20、另6題6/6；off14/20與4/6，首答／格式修復後分數各自相同。
舊完整回答語意失敗未改寫。下列整合結果取代先前待跑狀態。

#### 整合檢查結果與當時的可靠基線凍結阻擋（2026-09-29）

產品仍是`77edf12e`；文件checkpoint `d586a173`的Windows真模型ChatPanel四步全部通過：
Dataset→EDF匯入→選C3/Cz/C4→真Command重取樣64Hz，capture完整、資料變更正確，
關閉後剩餘worker／subprocess皆0。另5個原生Windows確認／取消／stale確認／匯入取消／
停止後關閉測試通過；這5項使用scripted generation隔離邊界，不冒稱真模型選擇證據。

既有74題一次hybrid推論完成，74首答＋1次既有格式修復；75份capture、74份首答輸入hash
全部核對，engine正常關閉。獨立tool-decision為首答65/74、修復後66/74；其中positive
35/36、challenge 11/14、no-action precision首答19/24→20/24。歷史自動content screening
是63/74→64/74，未改寫成新分數。19題positive原文與檢索範例重合，74題只有64份不同
rendered prompt，因此只作固定工程廣度，不是holdout或論文準確率。

8個最終失敗case對應7種不同原句：要求reset卻回答不執行；複合操作只提案bandpass或
average reference；空資料的epoch要求改提案切Preprocess；以及dashboard／尚不可用的
split／training settings仍提案操作。4個no-action case（3種不同原句）錯誤提案通過產品
准入、抵達evaluator抑制的執行邊界；另3個被Host擋下，但仍算模型錯誤。沒有真Command
或資料mutation發生，不把「未執行」包裝成正確不操作。這是工具決策缺陷，不是回答品質。

因此當時source架構覆核GO，但整合candidate未通過可靠基線gate；後續Development候選
交付依上方明示接受限制的決策，不將此失敗改成通過。
不增加Host意圖判斷、重試、prompt候選，也不因74題是breadth而忽略錯誤准入。既有52首答、
本次失敗及舊判分全部保留於ignored `build/dev-artifacts/agent-toolcall-freeze/`與
`agent-answer-completeness-v1/`；新input bundle SHA為
`52293dd515647c27b40cdaccc974d95052cedf2cf88ea84fb2a7f1639eb78871`。

同head CI仍作獨立工程驗證，最新狀態由GitHub PR #149擁有；即使全綠也不能補掉上面的
模型gate失敗。當時待決策已由上方使用者接受Development候選限制閉合；不得再自行
啟動模型調整，亦不提升為Stable。settings.json未改。

已完成直接修理：CI run36449067516的`linux-unit-rest`揭露parser兩處`str(exception)`
違反既有診斷邊界。Duplicate key由模型文字提供，確可將私人路徑／email／token帶入error。
先新增真parser惡意key回歸並重現，再重用既有`public_exception_message`；不加owner、不放寬
source guard、不改accepted JSON／格式修復、模型輸入／tool admission或UI流程。
Focused：parser與result contract、strict recovery；獨立覆核，以及保存capture重播證明
所有既有proposal判定不變（不是新模型分數）。完成後提交精確head CI；舊CI失敗保留。
此修理只閉合必要工程驗證，不授權追加prompt實驗；後續交付依最新Development決策。
同輪CI另有3項過時測試：Dev context仍要求舊untrusted items包裝與空history user訊息；
runtime trace及pilot outcome fixture仍用退役`structured_action`。依既定
`application_state/current_user`與`assistant_tool_response.v1`同步測試，保留真resample、
correlation、格式錯誤不救分等assertions；不修改runtime/scorer或fixture中的故意錯誤輸出。
實測：3個privacy案例RED→GREEN，parser／診斷邊界／strict recovery共120 passed；
3項舊fixture先重現，遷移後相關156 passed。Production僅parser +4/-2（淨增2），
owner不增；tests保留真Command等斷言。獨立覆核將先前53＋75＋4份capture共132份
交給前後parser重播，status／message／command／error完全相同；這是修理等價性證據，
不是新版真模型準確率或重新推論。舊source／模型失敗原樣保留，只有診斷隱私修正進新head。

### 歷史候選：回答完整性修正未通過當時的完整語意gate

2026-09-28使用者批准「那就修吧」的一次有界候選已實作並測完；規則歧義確實移除，
但未達「三類回答問題收尾且既有操作不退步」outcome，不能宣稱修好或交手測。
僅prompt policy +13/-4（淨增9行），測試+25/-3（淨增22行）；沒有新增owner、欄位、
Host意圖判斷、語意重試或補答案。模型／revision、RAG語料／排名／top-k、題目／oracle、
confirmation／取消及UI layout皆未改。target只釐清已批准的回答要求。

RED是前版真模型失敗capture；另2個policy投影保護先失敗再通過，不能當模型理解證據。
工程baseline90 passed；最終直接回歸126 passed（含真Command、normal/recovery及budget），
Ruff、型別、guidance audit與strict docs通過。途中舊文案斷言失敗已同步，沒有放寬語意判準。
獨立覆核全部52份輸入後凍結；bundle SHA前綴`e302ea1c`。463份runtime檔案hash與
當前候選相符；推論時HEAD為`90b6a528`加本slice，不冒稱該HEAD本身包含修正。
新證據位於ignored `build/dev-artifacts/agent-answer-completeness-v1/`；舊候選不覆寫。
初次export缺embedding快取連結而中止，補用既有pinned models後完成；無下載、無失敗推論重跑。

| 固定案例 | 前版完整語意 | 本次完整語意 | 本次自動判分 |
| --- | --- | --- | --- |
| 原20題／RAG off | 9/20 | 8/20 | 14/20 |
| 原20題／RAG hybrid | 16/20 | 17/20 | 20/20 |
| 既有另6題／RAG off | 2/6 | 2/6 | 4/6 |
| 既有另6題／RAG hybrid | 5/6 | 5/6 | 6/6 |

獨立覆核全部52組raw／final及新舊106份capture，結論為candidate gate failed；詳見
該證據目錄的`independent-semantic-review.md`。52首答＋off Channel Selection既有格式修復1次；四份capture／首答輸入身分verified，
engine皆closed。兩组題目分母不合併，不是論文成績。hybrid的reference禁止回覆改善；
E10b仍只確認不執行而不解釋、bandpass仍漏完整重述、normalize仍複誦（另6題亦同）。
off E10b已解釋但未確認不執行，依完整契約仍不計通過；off E10a新增把8–30 Hz稱為
alpha的錯誤，屬回答準確性退步而非誤執行；[MNE頻帶範例](https://mne.tools/stable/auto_tutorials/time-freq/20_sensors_time_frequency.html)
明分Alpha與Beta。此嚴格計分與具體改善並列，不把漏確認說成漏解釋或危險操作。

Next／待決策：prompt釐清不足以解決剩餘問題。E10b在off已能解釋、hybrid卻仍跟隨
僅確認不執行的參考，支持進一步檢查RAG示範適配，但不證明其他失敗也有相同根因。
保留這一版失敗checkpoint；不再追加候選／模型推論，不改gate、merge或開手測。
須先決定下一個有界修正範圍或明確接受哪些產品限制；通過原模型gate後，仍需74題廣度、
真模型ChatPanel／確認取消及同head CI才能交Windows集中手測。下方各候選結果保留歷史身分。

### 已完成：模型輸入不帶對話歷史

依2026-09-28使用者授權，刪除舊Assistant回覆投影、專屬限長及無用helpers／測試；
畫面與診斷紀錄、當輪原文、confirmation／取消／格式recovery保持。
Production +21／-118，淨減97行；測試+91／-183，淨減92行；owner數不變。
7個新增／改寫案例先RED再GREEN；相關Windows回歸211 passed，assembler型別檢查通過，
獨立覆核無未解source／test blocker。52份既有凍結首答輸入各比對有／無舊對話，
104次完整messages比對相同；未呼叫模型或檢索，不能算新模型成績。
當前契約見current／architecture／target；下方模型結果仍屬舊checkpoint，已知語意
失敗尚未解決，仍不交手測／merge，也不自行追加prompt候選或調參。

### 最新施工：英文上下文與 RAG 單一候選收斂

使用者於 2026-09-28 批准「那就開始吧」，並要求收尾時整理整輪改善前後的具體差別
與影響。此節取代下方已完成診斷的等待決策；只做一版整體候選，不換模型、不追加
多輪能力／Host intent router／第二控制層，不以 reviewer 看得懂代替小模型實際可用。

證據／假設：旧 off/on 均13/20；人工正確選例5題只改善2題、3題仍失敗、另2題語料
缺口。規則正確不表示容易使用；本輪假設可透過回答／操作平衡呈現、合併重複規則、
清楚區別当輪與參考、以及直接英文正反對照降低小模型理解負擔，尚非已證實因果。

Scope／outcome：僅英文；維持18工具、兩欄wire、完整單輪要求及一次格式修復。
整理既有 assembler／prompt policy，保留安全、來源、publication、confirmation、取消
與真後端 owner；RAG維持BM25＋dense＋RRF，不改模型／top-k／准入門檻，不新增分流。
語料對齊常見英文操作，補同操作的禁止不執行示範；明分完整、全缺值、部分值、
否定及純說明，不複製測試原句或用錯誤tool call當範例。無UI layout／工具contract變更。
只刪／收斂重複呈現，不刪必要狀態，不藉fail closed隱藏模型錯誤。

施工步驟：
1. 先由獨立 reviewer 凍結6題新英文問法與判準，完整／缺值／否定各2題；原20題不動。
2. 主agent整理最終輸入；RAG語料獨立寫入；保持對應baseline tests，再完成focused
   regression及離線檢索。不得為通過而刪反例／改oracle／掃參數。
3. 在任何新模型結果出現前，完整候選與案例凍結並獨立覆核所有實際輸入；新候選26題
   各跑off/on一次，52首答，最多每題原產品格式修復一次，無semantic retry。
4. 逐題比對首答、格式修復、Host admission與獨立語意；原20題須全符合契約，新6題
   不得猜缺值／違反否定或新增錯誤副作用。RAG需具體受益且不新增錯誤，不要求任意漲幅。
5. 通過才同head CI／適用真模型GUI journey及Windows交付；仍失敗先保留source/失敗
   並提出模型／產品取捨，不再開始第二版prompt、偷偷放寬gate或交使用者替失敗驗收。

Complexity：owner不增；刪除候選是重複policy／schema重述與只供Host追蹤的多餘呈現，
不是驗證本身。production delta逐slice記錄；單一PR#149既有大小例外仍有效。
UI確認：只改已授權Assistant英文理解／回答契約的內部呈現，無layout改動。
驗證／stop：focused assembly、安全隔離、budget、parser及真Command保護；offline corpus/
retrieval；固定52首答；獨立完整context與語意review；通過適用同版本gate才handoff-ready。
本輪結束另列已接受main、單輪簡化前、13/20中間版與最終候選的差異，分清code/tests/
scripts/docs/corpus、實測與未驗證影響；不將不同題目分母直接加總。
Next／狀態：唯一候選已實作、凍結、完成52首答及獨立內容覆核；仍未通過基本模型
gate，屬需要後續決策的checkpoint，不是handoff-ready。不得重跑抽成功或追加候選；
也不啟動手測／merge。settings.json不動。結果與整輪差異如下，下方舊Next皆為歷史。

#### 英文候選實測與整輪比較（2026-09-28）

產品候選checkpoint `2bc64c44b442421927c57316488e1c0b79ae9a97`。推論時Git HEAD仍為
`00a8c829`、本輪source尚未commit；不是clean-head gate。462份runtime檔案的凍結hash
與後續checkpoint內容逐一相同，runtime fingerprint為
`99fa8c7ffae169012b813a324d1419ad918d594e91631392ddc7786f4f950ce5`。
完整證據在ignored `build/dev-artifacts/agent-english-candidate-v1/`；原失敗與舊結果未覆寫。
52份完整輸入在生成前獨立覆核，bundle SHA為
`1d1595b39b07202af7b09f5f4ee12451d255526e46756155e0c31eca96fb0c2b`。
模型／revision／greedy設定不變；52首答＋1次既有格式修復，無semantic retry。
四份report全部capture verified、engine closed，首答prompt逐份符合凍結內容。

| 同一英文候選 | 原20題自動判分 | 原20題獨立完整語意 | 新6題自動判分 | 新6題獨立完整語意 |
| --- | --- | --- | --- | --- |
| RAG off | 14/20 | 9/20 | 4/6 | 2/6 |
| RAG hybrid | 20/20 | 16/20 | 6/6 | 5/6 |

首答與一次格式修復後分數相同。自動分數只代表工具／參數／格式及既有content screening，
不能冒稱完整語意通過；兩组分母不合併，也不是論文準確率。新6題凍結在候選前且
未複製語料／原20題；仍只是小型工程檢查，不是統計泛化保證。

hybrid剩餘4個原題：E10b「不要執行，請解釋」只確認不執行，漏掉解釋；bandpass全缺值
已正確問上下限，但未明確要求完整操作重述；reference與normalize禁止題只複誦原句，
未確認會遵守。新6題只剩normalize禁止題同樣複誦。後三類是回答品質／契約完整性，
不是此次誤執行；即使較寬鬆接受複誦或重述措辭，E10b仍足以阻擋原有gate。
E10b前一版off/on有解釋，因此這是確定退步，不用其他題改善抵銷。

前一版相同20題off/on自動皆13/20；本次hybrid五種缺值都能指出正確缺項、不再猜參數，
其中bandpass仍有上述重述缺口。當前候選off→hybrid，原20題完整語意改善7題、新6題
改善3題，各自無語意退步；這支持這個固定組合下RAG確有幫助，不隔離prompt／corpus
各自因果，也不證明換組件仍有同樣效果。off仍猜缺值，且Channel Selection格式修復
後仍失敗；不是修復機制能修好所有理解錯誤。
此次所有no-action題未到錯誤執行邊界；正向操作由evaluator刻意抑制，不能當真GUI執行。

離線v5准入20題通過；36個positive retrieval probes top1由34降至32、top3維持35。
bandpass全缺值未取到對應示範、normalize／reference否定仍取到操作示範等限制保留，不能說檢索
全面修好。實際輸入1400–2284tokens、預算7680，無截斷；原20題off中位數1875→1947、
on2122.5→2212，清楚呈現不等於更短或已證明更快。

直接回歸在checkpoint通過1251項（66.93秒）；涵蓋Agent／parser／真Command integration／
context template／RAG／verifier與新案例fixture，非全專案coverage宣稱。獨立覆核包含全部
52份新輸入／輸出；原20題另核對40份舊capture。Ruff、changed-source型別檢查、hooks、
guidance audit與strict MkDocs通過。三筆新增secret baseline只標註公開source／fixture hash，
未排除整份檔案或減少gate。模型未合格，因此未推送新手測head、未以舊CI補位，未跑
真模型GUI交付流程；不能宣稱整輪基線已完成。

整輪相對已接受main `a5f57a15`，而非只相對上一小步：

| 部分 | 之前 → 本輪候選 | 具體影響／代價 |
| --- | --- | --- |
| 模型契約 | stage＋tool＋parameters、typed補值 → 恰好tool＋parameters、完整獨立要求 | 刪跨輪累積／猜意圖分支；缺值後須重述整個操作，不能只回數字。中途五欄草稿方案已刪除。 |
| RAG | 手寫分流、dense池內BM25重排 → 已發布工具／回答集合，獨立dense＋BM25及RRF | BM25可補召回；不取得授權、不能填當輪缺值，仍可能選到不合適示範。 |
| 語料 | main72筆 → 現161筆；本小步157→161 | 包含完整、缺值、部分值、禁止、純說明；數量不是效果保證。 |
| Context | state與參考共用可裁減區塊 → state與當輪原文是必要輸入，參考獨立 | 沿用同publication；整例packing、回答與執行並列，不是更短prompt宣稱。 |
| 驗證 | 歷史81題契約 → 保留歷史，固定新20題＋6題，raw／修復／Host／語意分開 | 不將舊成績、Host擋錯或合法JSON當作本輪模型答對。 |

以2bc64c44為統計截止：production Python +730/-1891（淨減1161行）、scripts Python
+892/-2114（淨減1222）、tests Python +3568/-4256（淨減688）。含JSON fixture後scripts
共淨減677、tests共淨增35；語料JSON淨增943，文件當時淨增829，另有30行公開hash
allowlist。後續只補本節及current事實，不把文件／fixture膨脹包裝成產品程式縮減。
18工具、backend owner、confirmation／取消／publication及一次格式修復保留；沒有新增
第二模型／控制層。這是已完成候選工程與實測的結論，非可靠基線已驗收。

### 已完成診斷：英文小模型上下文與人工選例

2026-09-28 使用者批准「好施工」：本輪僅支援英文輸入／回答，先對既有失敗的
7 個單輪案例做人工選取既有 RAG 示範的診斷。舊 off／hybrid-native 配對保留且不重跑。
問題與證據：規則正確、無截斷不等於小模型容易使用；bandpass 全缺值要求收到兩個
完整操作與一個 partial-high 示範，實際只問 lower，五個完整缺值示範未進融合候選。

Outcome：區分「找錯參考」和「即使提供適合參考仍無法遵守」；不是正式準確率、
RAG 改善宣稱或最終交付。現有基本模型 gate 仍有效，不以人工選例替代。
Scope：先盤點既有語料、凍結選例／判準／模型與來源身分，再每題一次首答診斷（最多
7 次生成，不做格式或語意重試），保存完整輸入／原始輸出與逐題獨立語意覆核。
原產品最多一次格式修復仍保留；此診斷只比較舊首答，不能把零重試診斷冒稱產品改版。
不改 system／工具／state／使用者原文、產品提示、語料、檢索參數、模型、settings 或
UI。人工選例只走既有 RAG 編碼與 context 組裝，不另建 production owner 或逐題路由。
若既有語料無合適示範，明記缺口並不生成該題，不為題目現寫答案；分母仍列全 7 題。

步驟／focused validation：
1. 記錄 7 題、既有示範 ID 與選擇理由，覆核沒有變造語料／補答案；先凍結再推論。
2. 重用現有 assembler／模型 runtime 與既有快取；逐 byte 核對 system/current_user
   對舊 capture 一致，確認只替換參考；無執行副作用，輸入輸出有 hash 與確切來源身分。
3. 每題一次生成；不以格式合法或 Host 擋錯評為答對。判斷缺值項目／完整重述與否定
   不操作的語意；獨立覆核全部 7 題，說明人工選例、範例數量改變等因果限制。
4. 有證據才決定最多一版整體修正；沒有則提出模型／產品取捨，不自動 sweep。
   修正版仍需固定 20 題、事先凍結少量新問法、RAG 受益及同版本整合 gate 才手測。

UI 確認：本次診斷無可見產品改動。Complexity：production +0／-0、owner 不變；
只用有界診斷附件，不新增通用測量平台。Stop：診斷完成後依結果判定可修範圍；
不能將 reviewer 看得懂當小模型可用，也不將 checkpoint 冒稱 handoff-ready。
診斷已執行，結果與接續如下；不重跑抽到成功。

#### 人工選例首答診斷（已跑、非產品成績）

Source `14ddc4ca644cdbd70c591b4f24a0514a762df5d9`；只有本節與 target 文件改動，
產品程式及使用者 settings 未改。附件在
`build/dev-artifacts/agent-single-turn-v1/oracle-reference-v1/`；凍結 manifest SHA
`2a779a57f790a0b1aae2afabe3a4de8479a2c18ce6722fdd86833486a9af257e`。
診斷腳本 `build/dev-artifacts/diagnose-single-turn-oracle.py` 只用既有 assembler／encoder／
LLMEngine，無 executor、Host admission 或重試。只讀既有 D 槽 pinned Granite 快取，
與舊 control 相同 CUDA／非4bit／greedy／512；Windows native 一次載入、5 次首答生成，
engine_closed=true。生成前已獨立覆核選例，核對舊 off 的整份 rendered prompt、
舊 on 的 system/current_user 與當前一致；新 5 captures 與凍結 prompt/output hash 一致。

| 固定案例 | 人工選例首答 | 判斷 |
| --- | --- | --- |
| missing_bandpass_en | apply_bandpass_filter，parameters={} | 仍錯；沒有詢問上下限。原 hybrid 只問下限，兩者都失敗但形態不同。 |
| missing_notch_en | apply_notch_filter，parameters={} | 仍錯；沒有詢問頻率。 |
| missing_resample_en | resample_data，parameters={}，尾端多一個 code fence | 仍錯；另有格式錯，不以修復重跑掩蓋。 |
| missing_reference_en | 詢問 reference method/channel 並要求完整重述 | 改善；原 off/on 均猜 average。 |
| missing_normalize_en | 詢問 z-score/min-max 並要求完整重述 | 改善；原 off/on 均猜 z-score。 |
| single_turn_negated_resample_en | 未生成：語料缺口 | 沒有同操作、單純禁止、respond_to_user 的既有示範；不是通過。 |
| single_turn_negated_normalize_en | 未生成：語料缺口 | 同上；不能把其他操作的否定當等效參考。 |

準確的語料缺口不是「完全沒有否定」：apply_notch_filter_07 與 resample_data_07 的
混合要求分別包含禁止 resample／normalize，但示範是執行另一個操作，不適用此條件。
7 題完整列出，5 題已生成中 2 題行為改善、3 題仍失敗，2 題未生成不計 pass／fail。
此診斷未執行工具，也未測 Host 擋錯；不能說三個空參數操作已在本次被後端擋下。

支持的結論：現有單一合適示範能幫助 reference／normalize；相同介入不足以讓另三題
遵守缺值契約。不是「只修檢索即可完成」，也不證明模型天生不會、RAG 永遠無效。
人工選例同時改了 relevance、範例數量與競爭內容；未隔離其因果，未跑新問法或正向
回歸，不能把 2 題改善併入原 20 題宣稱 15/20，亦不能宣稱產品 RAG 已受益。
獨立覆核已完成：manifest、腳本、corpus／case hash、14 份舊 capture 與5份新 capture
核對一致，語意判斷同表；未找到規則矛盾、參考遺失／截斷或組裝錯誤，不能由失敗
直接推導應改哪段 prompt。Guidance audit／strict MkDocs／diff 檢查通過。
Next：帶著此結果討論下一個有明確假設的模型／上下文適配取捨；目前沒有足夠根因
支持直接動用唯一有界修正，不追加候選或重跑。原20題 gate 與否定風險仍阻擋手測。
本次只完成已批准的先跑診斷，產品可靠基線仍未完成；不能把文件與診斷收尾當整輪完成。

### 最新決策：完整單輪操作基線（取代下方跨輪施工方向）

使用者於2026-09-28同意「好這輪做到這樣」：本輪以責任清楚、各部件直接測試、完整
模型輸入覆核、同版本整合及可重現封存達到集中手測；不是零缺陷承諾，不增加功能。
產品改為每次一個完整獨立要求；缺值回答需要重新提供完整要求，不保存或合併跨輪值。
正常說明、GUI開窗、一次格式修復、backend publication／confirmation／取消／資料驗證
保留；training背景工作與停止不是草稿能力。不做Host意圖猜測，不增加第二模型／owner。

證據：目前五欄及累積來源契約使E01基本操作退步；同模型舊prompt重播正確，兩次有界
刪減診斷未解決。不可用更多prompt範例掩蓋。已增五筆單純說明示範，但尚未證實模型
受益；這批及RAG參數先固定，不繼續調詞／門檻。settings.json仍完全保留。

施工與分工：
1. 先更新target，以單一兩欄tool_name／parameters模型回覆投影現有18工具；純回答用
   respond_to_user/message表示，非新增可執行工具。移除mode／changes／source_turn／quote
   與pending草稿傳遞，不保留舊wire相容分支；本輪direct參數來源檢查仍由既有validator做。
2. parser／prompt／assembler、runtime／confirmation邊界、RAG／研究consumers各自獨立
   寫入；先小模型基本互通再擴展驗證，不能完成大遷移後才第一次看模型是否能用。
3. 移除跨輪專屬程式與測試；以缺值後只回數字不執行、完整重述才可執行取代產品需求。
   歷史81題／累積實驗artifact保留原身分，不覆寫成新gate；研究runner明示新版本契約。
4. 固定基本模型驗證：5種direct操作各一完整／缺值／否定（15），2種GUI開窗，2個
   純說明，E01完整7–30（共20個單回合）；加獨立工程軌跡保護不沿用舊值／RAG值。
   工程不變量全通過；這20個基本契約案例需全過且不能由Host擋錯冒充模型答對；不是
   所有自然語言100%準確宣稱。其餘固定廣度題保持分母、逐項回報，不要求無限刷分。
5. 初版只做一次固定互通比較；僅有具體根因才容許一次有界模型呈現修理再驗相同案例，
   不掃候選。若仍無法保住基本能力，候選不進基線並提出取捨，不擅自放寬gate。
6. RAG另按既有受益要求做固定開關比較，不以能檢索代替受益。完成source、test品質與
   完整context的獨立覆核後，跑同head必要CI/native gates，再開Windows供集中手測。

Complexity：刪AssistantPendingRequest/ParameterChange/RequestUpdate及跨輪merge、來源
鏈和相關research/runtime轉接；PendingInteractionCoordinator保留confirmation／GUI交接，
backend仍唯一執行owner，owner不增加。各slice記實際production/tests/scripts/docs增刪。
UI確認：本次已授權缺值時重述完整要求的互動變更，不改layout／工具membership／確認。
Stop condition：符合上述固定scope、獨立覆核與同版本gate才handoff-ready；沒有merge授權。
Next：續作以緊接下方的「當前施工與接續」及固定模型驗證結果為準。

### 當前施工與接續 { #agent-baseline-construction-plan }

本輪仍為單一整合 PR #149（使用者明確批准大小例外），不將切片當多次手測。
前一個 source checkpoint `223c624b2a194221c69cfc22e3431ce4092eb0a5` 不是新單輪候選；
本輪遷移保存為本機工程 checkpoint，不推送為手測候選。`settings.json` 是使用者原有
修改，必須保留。Git 擁有即時版本事實。
本輪 outcome、scope、非目標與 stop condition 由頁首定義；不再按下方歷史跨輪任務施工。

| 範圍 | 已做／下一步 |
| --- | --- |
| Wire／context | parser、schema、policy、assembler 已改兩欄；刪除草稿來源 ID／quote／mode。必要 state 與當前原文完整保留。直接 200 tests 及下列整合檢查完成；模型 gate 未過。 |
| Runtime | 刪跨輪保存、合併、失效與 draft origin bypass；保留 confirmation／GUI owner、publication、取消及 training async。獨立 reviewer 未見 runtime blocker；真 Command 測試保護完整重述與不沿用舊值。 |
| RAG | 157 筆，schema 6，刪兩個跨輪示範並保留五種單純說明。v4 檢索 fixture 實際是 20 題（原 24 只刪四個跨輪），不是原先錯估的 16；unrelated 反例不刪。offline 已通過，尚非模型受益。 |
| Consumers | runner v17 預設固定 20；舊 81 原始案例及報告保持歷史身分，74 個仍適用單輪另列廣度。研究 scorer／capture／report／gate readers 已同步並直接驗證，不新增相容草稿層。 |
| 文件 | 刪除 active target 的被取代跨輪說法；current／architecture／validation 同步。此處保留失敗位置，不複製另一份產品契約。 |
| 整合出口 | 完整真 input 獨立覆核、所有 directly affected tests/static checks、同 head CI 與適用 native journey 後，開 Windows 完整程式及 PowerShell log 集中手測。不 merge。 |

### 固定模型驗證與目前證據 { #agent-m0-acceptance }

固定 20 題 manifest：
`scripts/dev/stable_assistant_single_turn_cases_v1.json`，
SHA `5ef6bca6053b835ce1e21a68b51735e69630d0c881e28cf072fa61135abbd1a4`。
完整契約在 [validation](../validation/README.md#single-turn-assistant-candidate)：
raw 與一次格式修復後分開，20/20 要求含獨立回答語意覆核，Host 擋錯不救分。
模型是 pinned Granite 4.0 Micro，CUDA／非4bit／structured greedy 512；只用既有快取。
不改 settings，不下載或 silent fallback。

證據位於 ignored `build/dev-artifacts/agent-single-turn-v1/`，每次失敗不覆寫：

- `off/report.json`：預設設定找不到 cache，零推論；不是模型失敗。
- `off-cached/`：明確既有 D 槽模型快取，20 真生成與 capture hash 核對完成，
  raw/post 均 13/20。E01 7–30 及 E10a 說明恢復；五個缺值猜參數、两個否定誤操作。
  來源 validator 擋住五個缺值，但否定 resample 到 suppressed execution boundary，
  不能宣稱後端已理解否定。兩個其他否定回覆只重複原句，尚非完整語意品質通過。
- `offline-report.json`：157 筆真離線索引、v4 20 題准入及既有 retrieval 保護通過。
  36 retrieval probes top1 34、top3 35；這不是生成模型正確率。
- `hybrid/`：本機測量包裝缺 Windows multiprocessing main guard，檢索退化；
  不是有效 RAG-on 對照。包裝已修，產品 prompt／模型／語料未變。
- `hybrid-native/`：有效配對完成，20 captures核對成功，18 retrieved／2正常empty，
  raw/post仍13/20，沒有case-level fail→pass或pass→fail。RAG使notch否定回覆改善，
  bandpass缺值不再猜操作但抄partial例只問lower、漏upper；notch／resample缺值改抄
  示範數值。獨立review確認與off相同system/current_user、僅RAG不同，無packing遺失。
  這支持局部行為影響，未達可靠基線或RAG完整受益要求；不啟動prompt sweep。
- `retrieval-diagnosis.json`：CPU／offline只讀既有索引，五題最終ID逐項重現。
  五個完整缺值例都沒有進融合候選：bandpass／notch dense rank6／3、cosine
  .6830／.6371被.7准入擋；resample／reference／normalize rank34／28／19在top10外
  且也低於.7。五例BM25只命中一詞，未達min2與coverage；filtering/filter、
  sampling rate/resample、normalization/normalize及recording/EEG data表述不匹配。
  不是最後top3排序壓掉已召回正例，也不證明降低門檻或加stemming即可解決。

Consumer／docs遷移、直接驗證與獨立覆核已收斂，保存為可回退本機checkpoint。
以下是人工選例診斷前的阻擋狀態；新授權的最多 7 次診斷依頁首施工，不宣稱已可手測。
模型gate目前阻擋交付；完整輸入覆核未發現足以支持有界呈現修理的source缺陷。
若沒有可證的實作錯誤，不擅改retrieval設計、加Host語意路由／第二模型或放寬gate；
完成coherent工程checkpoint後提出具體設計決策，不把此候選交手測或merge。
需決策的是是否另授權一次檢索／語料適配修理；這不保證能解決off已存在的否定理解問題，
不能將兩個問題合併聲稱只修RAG就會可靠。

工程收尾證據（不合併重疊測試數，也不替代模型gate）：
- Assistant unit＋integration 1,064 passed／1舊current_user.id斷言失敗；改斷言後該檔及
  registry focused共25通過。真Command、confirmation、取消、stale／async保護與長session在內。
- Consumer／RAG／research直接集合561通過；後續兩個純死碼刪除的186子集合另通過。
- 新研究report v4原被呈現為Pilot，先RED再修兩處schema membership；5個新舊版本／
  不混算focused及2個render-time capture drift通過。較廣兩檔I/O測試100秒timeout，
  Windows process確認已退出；未延長timeout或宣稱全report suite完成。
- Runtime focused Basedpyright為0 errors；額外scripts掃描有14個diagnostics，涉及既有
  optional narrowing／evaluator duck-typed harness，這些scripts不在既有XBrainLab typing
  gate內。未宣稱所有腳本typing通過，未為此擴大改寫或修改baseline。
- Scope lint／diff檢查、guidance audit、strict MkDocs通過；獨立review修正報告reader只信
  PASS flags的假綠及malformed nested JSON crash。讀取器檢查實際20題、trace、capture、
  模型版本、cleanup與RAG狀態；CLI機械結果與獨立語意覆核分開，13/20報告仍拒絕。

尚未跑final-head CI／真模型GUI journey／Windows真人驗收，因候選基本模型gate已失敗，
不把無法交付的版本推成驗收候選。工程checkpoint不是scope-complete或handoff-ready。
只有具體根因才動用一次有界呈現修理；不能因 20 題未過而另掃語料、門檻或 prompt。
尚未 scope-complete／handoff-ready。Compaction 與 CI pending 不是停止條件。

### 先前跨輪設計的診斷證據（已被單輪契約取代）

歷史細節可從 checkpoint `223c624b` 的本文件及 ignored artifacts 還原；保留 source、
失敗與分母，不把舊累積功能當新待辦：

- `agent-baseline-rag-v3/`：154 筆舊 corpus 的固定 9 題 hybrid 4/9、off 5/9；
  ordered-hybrid／ordered-off 均 5/9。不是 RAG 淨受益或基線通過。
- `e01-accepted-prompt-diagnostic/`：accepted main capture control 逐 byte 重現；
  舊 prompt off 的相同 E01／E10a 正確。只支持上下文／契約組合退步，非單欄因果。
- `agent-e01-catalog-scope/` 與 `agent-e01-added-examples/`：兩個 bounded 刪減診斷
  均未解決 E01；沒有採用或繼續掃描變體。
- `agent-rag-m3/` 及先前 v1／v2 admission 失敗保留；固定准入的政策決策見 target。
- 舊跨輪專屬測試／DTO／提案 wire 已批准刪除，不以搬 legacy 或兼容空殼保留能力。

## 歷史 — RAG／決策與追問聯合修理與撤回（不再派工）

以下保留前次修理範圍、撤回與證據，已由頁首的整體設計討論取代；其中Next與舊授權
不是本次施工指令。Public contract仍須先核准，撤回不代表RAG品質已完成。

### Outcome、scope與現況

Outcome：補檢索缺口且不增加既有逐題pass→fail，不把工具命中、安全擋錯與正確回答混為一談。
Scope為RAG表示／召回／排序、既有決策提示與直接追問交界；不換模型、不動正式研究題庫、
不新增intent router／owner、不放寬Host保護。UI layout、工具名稱／副作用與兩欄root維持。
受保護的root settings.json不動。跨既有參數來源／追問output contract須另核准target。

PR #149未merge；c753撤回fe533改動之後，獨立語意覆核又發現保留的catalogue修正仍有新增錯誤，
因此連Split／Training描述也撤回。當前產品／測試／scripts與2e3b逐byte相同，本次聯合修理
**沒有被採用的runtime改動**；不能以淨增行數、診斷數量或green測試聲稱能力提升。
目前仍145筆、schema2、cosine准入後BM25重排；已知兩筆正確例被dense門檻排除，並未修好。
**本輪不是scope-complete，也不是handoff-ready；不開手測、不merge、不開始下一部件。**

### 已完成的有界診斷與否決

固定MiniLM／Granite revision、工程題目與生成設定；以下是development，不是sealed thesis evidence。
不得重跑抽到通過、改題降gate、把粗工具命中冒稱完整語意正確。

| 候選／診斷 | 證據與判斷 |
| --- | --- |
| b4c7：dense／BM25獨立聯集 | positive檢索Top3 34→36/36，但模型positive36→35、追問6→4/7；已撤回。 |
| 序列化input先於answer | 98 fresh control逐byte重現，196 captures；6 raw退步0改善，否決。 |
| catalogue／最後reminder分開比較 | 98題、122 fresh；catalogue先通過機器非退步，但c753後續語意覆核失敗亦撤回；reminder3退步，否決。 |
| 僅decision name，移除現成答案 | 98題，新增錯誤操作／虛報完成；input仍帶數字，否決。 |
| fe533：聯集＋五種typed缺值例＋pending資格 | 150筆、426 focused通過；完整105題positive36/36但追問4/7，否決並撤回。 |
| 固定同候選、每decision選代表 | 100 contexts重建一致；typed缺值命中仍1/5、22/36正向增加其他action；離線否決，未跑模型。 |

fe533的103 captures經獨立hash／trace覆核。五typed例都在union，但排名6/5/3/8/12，
Recall@3/5/10為1/5、2/5、4/5；resample例進prompt後仍猜128。17題rank audit完整context
重建一致。缺值與完整參數題可得到相同context，故增加k或宣稱corpus覆蓋齊全不是修復。
Selection文獻支持檢查集合冗餘，不證明這個decision-label heuristic有效：
[Coverage-based Example Selection](https://aclanthology.org/2023.findings-emnlp.930/)。

失敗commits、完整inputs/raw/逐題結果保留在build/dev-artifacts：
rag-b4c7-*、rag-example-order-replay-*、rag-contract-clarity-replay-*、
rag-decision-reference-replay-*、rag-fe533-*；不覆寫、不刪失敗證據。
fe533 CI failure來自multi-GDF外部labels UI walkthrough等待publication逾時，aggregate連帶失敗；
不是已定位的RAG型別錯誤，不以偶發失敗名義忽略。c753的後續CI屬於已撤回候選的證據。

### 撤回驗證與仍缺的證據

c753：217個RAG/context/tools focused通過；explicit-file hooks、guidance audit與MkDocs strict通過。
完整105題真Windows模型／Host診斷已完成；source changes排除settings後為空，positive36/36、
product no-action23/24、追問6/7，逐題pass/fail與f89f完全一致。raw precision仍15/24，
raw clarification2/7；Host協助後6/7不能當成模型本身全會追問。paired為21 machine pass、
1待語意覆核、2失敗，沒有把安全未操作算語意答對。
產物rag-c753-hybrid-model.json與rag-c753-prompts；獨立覆核103 captures／provenance通過，
99個raw與f89f逐byte相同；但capture90新增「產品提供Dense/CNN/RNN」錯誤選項宣稱，
既有no-action機器分數未察覺，main依不新增語意錯誤準則否決保留catalogue。
c753 CI run36377377474、docs36377377389是已撤回候選證據；未做新的native GUI handoff。
完整撤回後不重跑與已驗證source逐byte一致的模型全套；核對差異、直接工具測試與新head CI。
完整撤回已驗：git diff對2e3b的XBrainLab/tests/scripts為空；124個工具／context測試、
兩個變更檔hooks、guidance audit、MkDocs strict通過。受保護settings保持原差異。

### 待核准的追問契約與下一步

另一個RED重現的defect：模型typed追問時，原要求已有的單側cutoff未保留。
Host label parser候選雖測試通過，但違反target的「模型負責low/high mapping」；已撤回，
未核准patch保留在build/dev-artifacts/partial-cutoff-host-parser-unapproved.patch。
已詢問使用者選擇：建議typed追問攜帶model-proposed已知欄位，由Host沿用來源驗證；
或明確授權Host label解析；或另輪處理。**這項契約修理不保證解決RAG排序／模型抄例。**

Next：完成安全撤回的diff／focused檢查與CI追蹤，取得上述public contract選擇後先更新target，
再RED→修理→直接validation。RAG選例目前沒有可採用的非退步候選；不得自動再排列
權重／prompt／模型。需以已觀察的錯誤定位界定下一個有根據的修理，而非補題求綠。
Stop condition是有證據的部件收尾，或真正的新契約／必要資源決策；不因一個切片或CI pending結束。

## 歷史 — 前次 RAG 工程收尾（檢索品質判斷由上節取代）

2026-09-28 使用者要求先做到 RAG 收尾，再討論下一組件。本輪 source 為 `f89f3f89`，
已推送既有 PR #149，未 merge；本機只有受保護的 `settings.json` 差異。獨立 reviewer
完成 source、145筆語料、測試品質與實際模型產物覆核，RAG 工程範圍無 blocker。
這是部件 scope-complete，不是整合 handoff-ready，不開手測程式或自動開始下一組件。

- 四筆解釋＋操作示範保留問題／ID，改為先選一件；145筆現為117操作／28回答。
  既有 prompt rule 同步，owner 不增；production Python 本 slice +6/-3/net+3，corpus另計。
- Scorer v14 保留全部81＋24題，兩個 mixed probes 的預期按新契約改正；安全不操作與
  `semantic_review_required` 分開。歷史報告不改，不把評分規則更正算準確率提升。
- RED5→RAG/context/process190通過，controller RAG7通過；評分先RED後相關131通過。
  hooks、guidance audit、MkDocs strict通過，獨立實際diff覆核無blocker。
- f89f 真 offline hybrid/dense皆Top-3 34/36、145points，資格／bounds／manifest／repeat
  initialization通過；hybrid對舊36題基準non-regression通過。新隔離vectors只連結既有D槽
  embedding，不下載／改共享模型。報告如實標示worktree dirty（僅使用者settings）。
- f89f 完整105題真模型診斷完成；103個prompt/raw capture逐byte/hash經獨立覆核，
  75次retrieved、28次正常empty、0degraded；model source_changes排除settings後為空。
  positive36/36、raw precision15/24、product no-action23/24、clarification6/7。
  相同81題相對15e無pass→fail或新增執行邊界；training-settings的raw加分仍非正確blocker說明。
- 混合bandpass已收到正確範例／規則，仍只解釋，語意覆核不通過；normalize輸出雙JSON，
  Host回choose-one但模型格式失敗；paired21機器成功＋1待覆核＋2失敗，不與舊契約總分比進步。
  待覆核bandpass現已獨立判為不完成，保留原機器報告，不回填或重算它。
- 初次model preflight因預設C槽無模型在零生成時停止，失敗報告保留；重跑明確使用啟動器
  同樣的D槽model cache，完整結果另檔，沒有silent fallback或重抽失敗題。

Evidence：`build/dev-artifacts/rag-f89f-{hybrid,dense}-retrieval.json`、
`rag-f89f-hybrid-model-offline.json`、`rag-f89f-hybrid-prompts/`；前置失敗為
`rag-f89f-hybrid-model.json`。f89f同source CI run `36369844021` 已 completed/success，
全部適用non-skipped jobs成功；後續本文件收尾不改產品，不將該結果冒稱新head的CI。

**下一次討論而非自動施工**：決策提示／輸出契約是否先做受控回退比較，再處理模糊要求
`ambiguous_en`擅選channels與`generic_filter_selection`追問缺口。現行兩欄不變，未達
product gate，不宣稱Stable、可集中手測或最佳RAG。回退的必要授權已有，但最新要求是先
討論下一組件；不再自動調RAG權重、門檻、加例或跑組合搜尋。

## 歷史 — 已執行的 RAG 收尾計畫與後續共同基線方向

2026-09-27 使用者批准實作：先把 RAG 作為完整部件整理，再往下一部件推進。
起點 main `a5f57a15`；單一 task branch `fix/rag-component-baseline`，不更動使用者
`settings.json`、共用環境／模型、正式研究題庫或既有結果。這一輪包含 product、tests、scripts、
corpus、必要 prompt 及 canonical docs，不以補到指定筆數或單組測試通過當成完成。

### 歷史決策與施工順序（2026-09-28；續作以頁首為準）

使用者確認：這輪先建立可靠共同基線，不追求讓 RAG 適配當前所有組件的最高分；
基線通過後再逐個打磨工具說明／決策提示、追問／上下文，於 Development 驗證組合效果。
產品行為以 [Agent target](../target/agent.md) 的單次決策規則為準。解釋＋操作不再以
「只執行操作」當完整成功；模糊要求先確認種類、缺參數不猜、不可用操作不代做前置步驟。
使用者同意必要時受控回退已實測退步的兩欄輸出／提示遷移；不是自動認定三欄有效，
也不授權雙格式相容、改模型、放寬後端保護或合併 PR。這次先固化文件，尚未修改產品。

**問題與證據**：f329f3c9 的適用 CI／Windows 四步 journey 通過，但不等於整合基線過關。
15e 模型報告的新增不可用 split／training-settings 誤選尚未解決；既有產品 gate 仍是
no-action 23/24、clarification 6/7。前者的 `ambiguous_en` 將「process this EEG data」
自行解讀為 select_channels，已抵達被 harness 抑制的執行邊界；後者
`generic_filter_selection` 曾提出無來源的 1–40 Hz，Host 擋住卻未完成必要追問軌跡。
這兩項與 paired probes 的模糊 import／解釋＋操作案例不同，不混成同一失敗。

**Outcome／scope**：保留有效 RAG 結構整理與 import busy 修理，收尾語料契約、檢索資格、
生命週期及可追溯性；依責任修理上述整合阻擋，再一次交 Windows 手測。
假設是整體準確率受多組件交互影響；不宣稱輸出 stage 是必要推理機制，或回退能修好全部問題。
不增加 router、planner、模型、permission owner、第二套 evaluator 或通用實驗平台。
暫停擴充同義句、調權重／門檻／top-k；145 筆現有語料可作契約一致性修正，不是固定最佳值。
UI 確認：沿用已確認的 layout／工具／confirmation；此次批准混合要求先選一件的回應語意，
不新增視窗或多步執行。使用者 settings、共享環境、sealed 題庫與歷史 raw/report 不動。

**施工順序與 focused validation**：

1. 先對齊已批准的單次決策：target → 語料／prompt → oracle／tests；獨立覆核預期是否符合
   產品承諾，包含四筆解釋＋操作示範及 paired cases。保留題目及歷史結果，新版契約／scorer
   另記身分；不能刪難題、重標舊分數或把規則更正宣稱準確率提高。
2. 固定其他變因，受控比較輸出／提示遷移的回退。先驗真 parser、publication／stale、
   confirmation、參數來源及一次執行；再以同契約、同題意的完整模型比較逐筆確認。
   歷史 785c 只作參考，不冒充新規則下的 contemporaneous control；採用與否依新證據。
3. 在選定契約上處理模糊要求與 generic-filter 追問缺口，先重現再修理其真正 owner；
   不把後端安全拒絕當模型答對，也不以新增 RAG 範例替代決策／追問責任。
4. 凍結整合 source，跑適用 focused／完整模型 gate、RAG 開關與必要 ranking 對照、
   同版本 CI、Windows 真操作與獨立覆核；通過後開程式及一個 PowerShell log，集中手測。
   不每個切片要求手測，不自動 merge。對照重用現有 runner，不做全因子暴力搜尋。

**完成層級／stop condition**：RAG 部件完成指契約、檢索、生命週期及直接證據可靠；
整合 handoff 仍須必要產品 gate 通過且沒有未處理的新增退步，不以「部件完成」豁免。
最佳組合留給後續 Development／Validation；重要組件變更時才做原／新組件 × 原／候選
RAG 的有界交叉比較，正式 Test 不參與選擇。若有界修理仍無法達標，保留失敗並提出具體
取捨，不無限加例／改 prompt 或默認放寬 gate。

**本次施工界線（使用者追加確認）**：先做到 RAG 部件收尾，再討論下一個組件。此次實作
步驟 1 的契約／語料／評分對齊及 RAG 檢索／索引／生命週期直接驗證、獨立覆核；
不自動開始步驟 2–3 的輸出回退或追問修理，不把部件結案冒稱整合 handoff-ready。
寫入分工：主 agent 負責 corpus、prompt 的既有單次決策規則、直接產品測試及 canonical docs；
評分 slice 負責 paired probes／runner 身分及正反例測試；独立 reviewer 檢查未改 RAG owner、
取消／publication／cache 與 evidence 充分性。維持 owner 數，不新增 parser／compatibility／控制層。
刪除候選是四筆 mixed-request 示範中錯誤的操作答案及 paired 舊期望，不刪題目或歷史 evidence。
Rollback 以本 slice source／corpus／scorer 一起回退；既有 settings 與失敗產物不動。
先建立新規則的 RED，再修 corpus／prompt／scorer；跑同測試及必要鄰接、真 offline retrieval、
版本／來源核對。若改動 prompt，真模型工程診斷仍需記錄，不用其結果追分或宣称整合過關。
RAG 部件完成後回報實際驗證、未解整合缺口及下一個建議議題，依最新要求先討論再施工。

**進度／Next**：四筆 corpus 錯誤操作答案及缺少 prompt 規則先 RED（5 failures），修正後
RAG／context／process lifecycle 190、controller RAG 7 通過；scorer 另先 RED，相關 131 通過。
維持145問題／ID，現為117操作＋28回答；paired 24題只改兩個 mixed-request 期望，問題不動。
Evaluator v14 將安全不操作與待語意覆核分開，舊 raw／report 不改。獨立 source／語料／測試
覆核無 blocker。真 offline hybrid 新隔離索引145 points、12 checks 通過、Top-3 34/36；
source 當時為 dirty，report如實記錄，不冒充 clean commit。使用既有 D 槽 pinned embedding，
沒有下載或修改共享模型，重用既有 cache helper 隔離 vectors。下一步凍結 source，跑一次
完整105題真模型工程診斷並覆核實際回覆；這不是整合 promotion，也不按結果無限追分。
回退授權已解除，但是否啟動回退比較留待下一組件。產品仍為兩欄，尚無本次新模型成績。

### 歷史施工與失敗證據（保留溯源，不作續作指令）

以下為最新決策前的實作／診斷紀錄；其中舊 Next、等待批准及 mixed-request 評分假設
均由上節取代，不重寫原實驗成績。

曾選定並已否決的候選：以既有publication-filtered contracts生成單一兩欄JSON Schema，
互斥alternatives重用各工具參數與response schema；blocked reason另置於schema外。
取代混合catalog與重複輸出形狀，不新增permission owner／constrained decoder。
RAG corpus／ranking／example內容不改；先以schema membership／真parser測試RED，
再驗fixed105逐題語意。依據為[Granite官方JSON schema範例](https://github.com/ibm-granite/granite-4.0-language-models/blob/main/Granite%204.0%20Prompt%20engineering%20guide%20v2.md)，
不把該文件當成Micro一定改善的證據。
仍保留固定105完整對照、原門檻及所有失敗，避免逐題搜索；若產品設計必須變更則另需授權。
Import先RED確定busy→新publication→release順序，再讓既有render owner提供當前可用性，
不增加狀態owner。兩項寫入分離、共享邊界獨立覆核；凍結整合source驗CI、offline retrieval、
真model與Windows journey後開程式＋PowerShell log交付一次手測，不合併。
施工進度：import兩種真Qt／FIF publication交錯先RED後GREEN；直接176案例（含原失敗的
GUI import→subject training→重開結果流程）及重疊的sidebar/presentation124案例通過。
Production兩檔+27/-19/net+8，只有既有owner的busy狀態投影，Cancel及generic async不改。
Schema呈現一檔+40/-51/net-11，97個直接測試通過；獨立覆核兩項diff無blocker，
另驗103個已保存輸入的schema結構，但不把它當模型語意通過。
**bfad6446否決**：完整105真跑positive36/36，但raw precision8/24（15e14/24、785c16/24），
paired first21/24、final22/24；新增多個不可用操作誤選及negated navigation，不能交手測。
回退該schema呈現及專屬測試／文件到23693406，保留已批准兩欄契約及632b94e0的import修理。
所有bfad報告／capture保留，不再修補oneOf提示。獨立檢查發現103個15e prompt中，
不可用tool ID只出現在status reference；Host才需要stable ID作admission。
**已完成的status-label隔離診斷**：固定15e全部98個首輪case（不冒稱包含7個
clarification trajectories），只把reference字典key換成既有trusted tool description，
保留數量／順序／reason／其他所有prompt內容，98個control rendered hash全吻合才允許生成。
不改RAG／callable IDs／Host map，不重抽control、不將raw-only證據冒稱產品成功；此診斷
不直接解釋normalize雙JSON，也不授權回退使用者批准的兩欄契約。依結果決定是否採用此
呈現修理，不降低原門檻、未知模型誤選不稱RAG已完成。
f329診斷98個control輸入逐byte相同，98個treatment capture全部驗證、source／設定不變，
零重試、零Host執行，正常cleanup。positive36/36、precision14→15/24、paired22/24，
但`split_before_epochs_en`從不可用split改成可用`set_montage {}`，在同state會通過既有
admission而開錯GUI；這是source-supported reachable risk，診斷並未真的開窗或改資料。
新增training-settings no-action分數只是收集不應收集的參數，不是正確解釋阻擋。
獨立覆核否決採用；script／report保留在`build/dev-artifacts/rag-status-label-*`，產品未改。

f329產品版最終證據：回退後context／真command111及evaluator109通過；PR run36335898154
所有適用non-skipped checks completed/success（含macOS原失敗流程、Windows lifecycle及source-diverse）。
`rag-f329-native/journey.json`四步通過，source／隔離設定／EDF不變，0 owned workers/subprocesses，
未修改root settings或使用者per-user設定。這不覆蓋模型誤選、不等於Stable或手測候選。
後續Agent討論已核對三個真正產品決策：解釋＋單一操作的完成語意、clarification支援邊界、
對話指涉／歷史範圍；不先加planner或第二套控制層。當時等待契約回退授權，未merge；
現行授權與續作順序見本節開頭。

**前一checkpoint**：兩欄契約已實作，但15e06744真模型驗證仍有新增
語意退步，獨立覆核不批准non-regression／交付。需要決定暫緩此遷移，或明確接受新增限制；
不再自動調prompt追分，也未合併。2026-09-28 使用者批准獨立遷移模型輸出契約：
移除模型回填的 `workflow_stage`，只接受 `tool_name` 與 `parameters`；階段仍由後端提供給
模型，publication generation、工具資格、參數來源與confirmation保護不變。先更新target，
再以parser RED／既有execution baseline施工，接續focused與真模型／native驗證及獨立覆核。

本切片證據：RAG提供兩欄decision片段，正式輸出要求三欄；controller只比對模型抄回的stage，
真正stale admission由host保存的publication generation驗證。差異不是已證明的漏執行成因。
Outcome是責任清楚且安全邊界不退步，不承諾模型語意準確率提高。UI無可見改動，使用者已確認。
Scope包含product parser/prompt/controller/RAG consumer、直接測試、實驗runner/scorer與canonical
文件；後端stage/state card、既有題意與oracle、BM25/門檻/排序、語料內容、模型與UI不改。
刪除候選是model stage echo／mismatch分支；既有owner不增不減，不新增兼容三欄輸出或新控制層。
歷史raw evidence不重寫，不把host stage冒充model輸出；新版scorer身分與舊結果分開記錄。
先驗兩欄接受／舊三欄拒絕，再驗真tool admission、同stage換資料的stale拒絕、confirmation、
format recovery、no-action與評分一致性。模型比較固定原81＋24題，分開格式與語意結果；
不使用sealed研究題庫、不改失敗題追分。獨立覆核後檢查同head適用CI及Windows native journey。
Stop condition為此切片安全／契約／evidence一致且必要驗證完成；不等同整輪RAG已解決。
可獨立回退本契約切片；既有24題診斷與失敗證據保留，PR #149尚不交付手測／merge。

2026-09-28切片進度：parser兩個新契約測試已RED→GREEN，全parser87、RAG邊界44、
unit／真command／Qt整合556通過。五個production檔+22/-81/net-59，owner不變；獨立覆核
確認host generation、confirmation及execution保護仍在。Script評分移除model echo並分別升版
stable v13／pilot scores v3／synthetic calibration v2；保留backend案例情境與原81＋24題。
另以RED補上raw scorer拒絕多JSON物件，避免移除stage比對後錯入內容評分。
Script evaluator109、runtime evidence14、report／observer直接案例37通過；與前述測試有重疊，
不相加為coverage。額外直接typing檢查的product無診斷，
scripts出現15項既有duck-typing／Optional診斷（canonical typing範圍原為XBrainLab），不宣稱全scripts
typing乾淨；本切片沒有修改那些型別責任。

c49f3625已實測hybrid105且capture完整：positive36/36、raw precision14/24（785c為16/24）、
paired22/24；product precision23/24、clarification6/7。新增split-before-epochs及start-before-setup
語意錯選，均被Host擋住；mixed normalize改成雙JSON仍失敗，不能用安全拒絕冒稱模型正確。
Windows四步真模型journey通過，資料／隔離設定／source未變、關閉後worker/process皆0。
初次native preflight因受保護settings選Phi而拒絕，未生成；改用明示的隔離Granite設定，未覆寫settings。
獨立覆核發現移除output echo時亦移除了trusted system中的stage值，state card仍有stage並非全失。
批准scope原本保留stage輸入；15e06744只從已讀publication補回一行trusted stage事實，
不新增policy/router/output欄位或再次讀state。該輸入位置先RED，相關102測試GREEN。
兩欄切片合計五個production檔+27/-85/net-58；parser／prompt／consumer刪除stage echo，owner不變。

15e06744完成同105題與Windows四步真模型journey；獨立覆核逐筆驗103個capture hash，
確認模型／cases／corpus／retrieval一致、無degraded。positive36/36、raw precision14/24，
paired22/24，product precision23/24、clarification6/7。相對785c新增失敗為
`split_before_epochs_en`與`training_settings_before_epochs_en`：提出不可用工具，被Host擋住。
`start_before_setup_en`相對c49f恢復不操作；challenge3→4/14只通過措辭oracle，
新回答誤列必要前置操作，不能宣稱語意品質提高。mixed normalize仍輸出兩個JSON；
模糊import仍誤提開窗。Native完成真匯入／三channel／160→64Hz，source、隔離設定及EDF不變，
關閉時0 worker／subprocess；不代表全產品或模型語意驗收。

獨立code／evidence覆核通過可追溯性及Host保護，但不批准模型非退步；所有失败產物留在
`build/dev-artifacts/rag-{c49f,15e0}-*`，舊785c不重評、不覆寫。PR #149目前不是手測候選。
另c49f的macOS lifecycle CI實際失敗：匯入完成且最新preprocess capability可用，Channels卻disabled。
source-based獨立診斷指向import busy release恢復舊enabled值、蓋掉最新publication render；
尚未建立確定性重現，未修改UI或擴大本切片。保留run36333439996/job108659706271證據，
不加timeout或盲目重跑。15e同head CI仍在追蹤，不用較新綠燈抹除這個既有race finding。
**Next／需決策**：建議暫緩兩欄遷移、保留此失敗比較，再另定修理邊界；不默認接受語意退步，
不擅自回退已批准public contract。上述import競態需另准最小RED→GREEN修理，不混入廣泛UI清理。

### 問題、outcome 與邊界

- 現行文字分流使同義詢問／混合要求走不同路；全庫 dense top-10 後才篩 callable tools
  可能漏掉合格範例。改為不做手寫語意分流、在已發布工具及合法 response 範例內搜尋。
- 保留 BM25；目前沒有足夠移除證據。共同修正後，以同source/corpus/model的 hybrid 與
  dense-only 做有界消融，不將old/new總體差異誤稱BM25效果，不因小樣本打平刪除。
- 約108操作＋24正確不操作範例是初始整理預算，不強迫湊數；最多約180，新增須對應
  真語意／參數缺口。示範、公開工程probes及sealed研究題庫隔離，不複製驗收題進corpus。
- UI、18個action contracts、confirmation、模型及正式研究政策不變；response範例重用
  `respond_to_user`既有契約，不新增tool、owner、classifier、reranker或第二套評測平台。
- 保持門檻0.7、top-3及bounded context，量測初始化／暖機／檢索／決策，不靠放寬timeout
  或依速度silent skip取得綠燈。缺資源須degraded，不能冒稱正常empty。

### 施工與驗證

1. 保存目前source/config身分及focused基準；先RED重現post-filter候選飢餓，再最小修理。
2. 更新範例驗證、搜尋前篩選、索引版本；刪除僅供RAG的intent規則及無用途測試／引用。
   必要輸出schema、資格、取消、close、late callback與index integrity保護留下。
3. 逐筆審corpus，補獨立英文案例；原48個retrieval probes不改題，新增24個成對工程案例。
   查驗GUI／Assistant／實驗runner送入同一產品RAG路徑，actual context及身分可追查。
4. 用既有產品模型／evaluator比較原main、新hybrid、新dense-only、新RAG-off；既有81題
   與新增24題保留首發輸出、side effects、失敗與時段。只屬工程準備，非正式DEV／VALID／TEST。
5. focused lint/tests與真offline retrieval後做獨立覆核，再同head applicable CI、Windows
   native Assistant操作／相鄰流程。覆核含未改生命週期、測試oracle及剩餘複雜度，非只看diff。

### 複雜度、交付與停止條件

- Owner維持retriever持有embedding/client、indexer借用、process lifecycle持有程序；assembler
  讀後端publication。篩選metadata由已驗證decision推導，不成為第二權限來源。
- 刪除候選：RAG專用intent grammar及exclusive characterization；保留BM25、完整性與
  lifecycle保護。各slice記錄實際production +/-/net，不以LOC證明品質；小commit可回退。
- 原gate不降低，不新增錯誤開窗／confirmation／execution，不注入不可用action。若合適示範
  已提供但model仍錯，定位責任，不無限增例；若無可辨識RAG收益，不宣稱效果已證實。
- 正向選擇已有36/36的工程基準，不以顯著增分作為整理有價值或結案的必要條件。
  分別評估既有能力不退步、混合／不操作要求、檢索資格與生命週期正確性，以及移除分流
  規則後的可讀性和維護成本；架構整理價值不等於已證明準確率提升，新回歸仍須處置。
- 完成獨立覆核及同版本適用驗證後，開Windows程式＋一個PowerShell log，附重啟指令，
  一次集中手測。Pending CI、commit或compaction不是停止理由；merge另待明確批准。
- **進度／Next**：原main retrieval34/36，81題真模型原始輸出已保留（非全對）；
  候選132範例與搜尋前篩選已完成。BM25候選遺漏、prompt最終publication漂移、
  malformed context／metadata及comparison失敗exit0均先RED再修理；整合focused306通過，
  獨立source／test覆核無blocker。Production Python +119/-572/net-453，corpus JSON
  +372/-12/net+360；owner不增加，刪除534行intent grammar，未增第二router。
  Next固定source後真模型四條件比較、同head CI及Windows手測交付；目前不是scope-complete。
  原產品的新增24題比較採共同harness回植到臨時snapshot、完整跑105題；記錄原產品SHA與
  三份harness hash，明示modified harness，不將其冒稱clean原main或拼接原81題結果。
- **18b8de9a真跑發現**：retrieval33/36，相對原34/36退步一題，原non-regression gate
  保留失敗；獨立語料審查發現12個有效舊表達被改寫取代。恢復原72筆，僅追加9個有新
  區辨意義的改寫（另3個與新增例重複），總141筆；不抄probe、不降低0.7／33/36門檻。
  同版模型105題已生成，但最終stdout因Windows CP950無法編碼U+202F中斷，僅checkpoint／
  raw保留，不冒稱完成。修理CLI以ASCII-safe JSON輸出、先保存UTF-8 report再寫stdout，
  補CP950及pipe failure測試；舊版105比較使用UTF-8環境獨立執行。候選修理後重凍结真驗。
- **325fdbbd驗證**：141例hybrid／dense offline均34/36、non-regression通過；真hybrid
  105題完整，既有positive36/36、no-action product23/24、clarification6/7，原有限制仍在。
  成對題first22/24（原版21/24）、final22/24（原版22/24），不是明顯收益證據。
  PR #149 CI發現partial(custom兩參數target, hybrid_alpha)型別不符，及三個security fixture
  仍用retired get_dataset_info或缺少decision。修為explicit product-target binding、提前拒絕
  不支援的custom+alpha組合；fixture改合法response並保留原攻擊／隱私斷言。隨後同head重驗。
- **bce55990內容覆核**：hybrid／dense／off各105題完成；原81題皆維持同樣結果，
  paired hybrid／dense first22、final22，off first21、final22。逐題揭露交換：RAG修正
  禁止開training settings，卻新增「說明再normalize」只說明未操作；兩邊都仍誤解模糊import
  指涉。Evaluator的舊output_format標籤在這個normalize案例實為合法response選錯語意，
  不可宣稱JSON壞掉或Host擋住了模糊import（harness只抑制實際副作用）。
  獨立審查確認117個action示範完全沒有說明＋明確執行的類型；最後有界補齊4筆獨立
  bandpass／notch／resample／min-max例，145筆上限（121操作／24回應）。Author未讀probes／
  輸出，參數直述，不新增router／回合／tool。只承諾選對既有單一action，不宣稱同時完整解說。
  Next重凍結、整批三條件與原gate比較；若合適例已取回仍錯，定位prompt／model，不再加同義句。
- **785cf2d1責任定位**：145例offline兩模式仍34/36；hybrid／dense／off各105題完整，
  mixed normalize的合法response仍漏操作，四例不能修正它。既有action示範已取回；不再加例。
  獨立覆核指出canonical decision rule 4將information及multi-action都列response，未區分
  「解說＋單一明確操作」。直接修理只在既有prompt policy釐清information-only及單一未否定
  操作；rules 1–3的可用性、必填值及禁止操作保護不變，不加assembler第二套政策。
  785c真模型結果作RED，既有prompt composition／contract測試及最後同版本三條件真模型
  作回歸；不以文字斷言冒稱模型會遵循。維持145例、原門檻與所有失敗產物，再做Windows真旅程。
- **10a5b4ee否決與回退**：三條件完整105題，generic prompt釐清未修正normalize混合要求，
  並使原positive split第二題選成training settings（35/36）。撤回該prompt與專屬文字斷言，
  回到785c相同產品code／corpus，不把unit／CI通過當模型行為通過；所有失敗保留。
  2026-09-27使用者同意一次受控定位：固定全部24個paired probes、785c control輸入／原始
  輸出與生成條件，只在檢索後排除response示範、不補位，觀察操作與不操作兩面。
  此為ignored一次性diagnostic，不改production、不作promotion或新held-out成績；control
  rendered prompt必須逐筆hash相同，記錄移除ID／完整模型輸入輸出。結論決定下一個最小
  修理，禁止無限prompt／語料搜尋；手測仍待新退步處置、同版本CI／native及獨立覆核。
- **55632eb2受控診斷**：產品／tests／scripts與785c完全相同；Windows真Assistant四步
  開Dataset→匯入→選三channel→160轉64Hz通過，source／原始EDF／設定不變、cleanup零
  owned worker／subprocess。此不代表mixed-request或全產品驗收。
  ignored診斷先核對24個785c control rendered prompt hash，再只移除response示範、不補位。
  六題context有變，其餘18題prompt及原始輸出逐byte一致；24筆capture完整，source／設定
  不變。操作首發11/12→12/12，不操作首發11/12→9/12，總22/24→21/24；normalize混合
  操作改善，但純說明變非JSON，training settings禁止開窗卻選switch_panel。這是raw-only
  一次性因果定位，不是Host執行、重試後成績或獨立泛化證據；歷史control非同時隨機重跑，
  舊settings位元與全部載入參數未保存，限制明列於診斷report。
  獨立覆核確認回答示範兼有格式／不操作保護與概念回答干擾，沒有建立通用更佳政策。
  使用者關切局部最佳解；本輪不再逐題調優，不能把可靠基線誤作這24題全對，也不能以
  未來Development為由默認接受本輪新回歸。需要上述職責決策才繼續新的有界設計施工。

## Context — 單一 main 基線先穩定，再分產品與實驗兩線

PR #147 已於 2026-09-27 合併；使用者完成最終 Windows 手測並明確同意合併。
產品與研究量測程式現在共用 `main`，原三條施工 worktree 與手測 worktree 已清理。
目前**不立即建立兩條新基線或 worktree**：先在同一基線上逐塊打磨到雙方確認的穩定門檻，
再從同一個 `main` 精確版本分出產品與實驗兩條施工線。下一步是討論並固定穩定門檻與
第一個有界部件；這段狀態不自行授權新功能、正式 DEV／VALID／TEST、模型或研究政策變更。

本輪 137 的 fixed20 是可重跑的工程 smoke，不是正式論文結果；使用者已同意清理其本機
pilot／工程輸出，不必為移除 worktree 另行封存。程式、實驗規格、題庫定義、共用模型／環境、
原始資料與既有正式結果不因此刪除。任何新實驗須以其當時的 source／模型／設定重新記錄身分，
不得把後跑結果接成這輪 smoke。Git／PR 擁有實際版本與 dirty state；主 worktree 的使用者
`settings.json` 保持本機修改，未當作程式碼污染或清理目標。

## Completed — 共同版本功能與實驗量測驗收（PR #147 歷史施工計畫）

以下保留施工時的範圍、失敗與修理依據；其中「未 merge」「待手測」及當時的 next step
是歷史狀態，不再派工。最終合併與清理狀態以上方 Active 節及 Git／PR 為準。

2026-09-24 使用者希望在第一版實驗前，逐一討論與打磨整個 Agent 部件，而非再次只按
程式檔案清理。範圍包含用途、內容、方法、操作體驗、實作、測試、腳本及研究可觀測性；
RAG 作法與庫內數量等基本合理性也須查證，不能把目前做法或工程測試通過當成設計合理。
最初僅制定計畫與唯讀審查；2026-09-24 使用者追加授權由本代理統一整合產品／實驗兩線，
先建立可靠共同基線，再分回產品部件與研究推進。允許本機checkpoint、整合候選及直接必要
的相容修理／補測；當時未授權發布PR，2026-09-25啟動本計畫後依下節建立驗證PR；仍不merge main、下載模型或啟動正式實驗，不更改公開工具、
可見UI、研究題庫／判分政策。下面各部件先討論，再依已確認的方案授權施工；計畫不是
把所有候選技術都批准實作。前輪內部清理的結果與限制保留在下節，不重做或改標研究證據。

使用者隨後澄清：本輪目標是先建立可靠基礎，完成後才開始跑 Development 改善。
不能把必要的 RAG／tool call／prompt 內容與方法打磨提前算成 Development，也不能
以「這應留給實驗」為由，讓已知基礎缺口進入 Development。部件小驗證是準備的證據，
不是正式 Development 成績；正式研究仍須有明確的起始版本與資料使用界線。

### 優先施工計畫 — 功能與量測驗收 { #integrated-functional-acceptance }

2026-09-25 使用者要求：分線继续改善前，先由代理實機跑過整合產品與另一線實驗腳本，
涵蓋已迭代的 Evaluation／Saliency，準備到一次集中 Windows 手測；實驗部署在工作站137
（使用者於2026-09-26更正原先誤認的134）。
計畫已固化並經獨立覆核，使用者現已明確要求開始執行，做到集中手測。
下方六部件打磨是後續工作，
不能跳過本節驗收直接接續。這不是重開無限全盤清理或重新定義研究方法。

#### 起點、已知事實與授權

- 起點為 clean `d4963adc3101741f3ba1f07779ee7c1e90a6157d`，worktree
  `D:\workspace_v2\projects\lab\XBrainLab-agent-baseline`；本次計畫文件修改須另記，
  不把 dirty source 當成已凍結版本。既有整合證據及限制見
  [Current](../current.md#assistant-integration-baseline)。本輪產品與研究須驗同一最終source，
  Windows／Linux runtime及模型配置各自記錄，不混用速度或判分成績。
- 2026-09-26已以 `hxin` 成功登入正確目標 `140.113.193.137`，嚴格核對既有host key；
  主機為 `ws-4090-03`、RTX4090 24GB。共用NAS上既有Python3.12.3環境、模型與
  clean `fac3c714`工程包可讀，不需重複搬模型或重建環境；這不等於137已跑過CUDA／模型。
  2026-09-27重查GPU空閒，137真CUDA matmul／Qt offscreen預檢通過；封裝真跑已啟動。
  134的歷史smoke、prepare及程序邊界證據保留134身分，不換標。
- 保持已接受的UI／功能／資料語意、公開tools及研究判分政策。必要的相容修理和直接補測
  在已授權準備範圍內；新可見行為、contract或研究方法取捨集中提出，不偷偷改成容易通過。
- 原兩線、main的使用者 `settings.json`、原始資料、共用環境／模型與B0／d0結果不動。
  不讀sealed VALID／TEST，不跑新正式DEV／VALID／TEST，不下載／重複備份模型。
- **本輪授權**：使用者在確認計畫及PR用途後要求開始，允許push整合分支／建立一個驗證PR
  取得同head CI，不包含merge。這是一個階段整合PR，帶入既有已審查模組與研究改動，
  不因累積diff強迫逐slice手測；新增修理仍逐片複雜度審查與驗證。
  登入授權不等於可覆寫工作站既有source／env／結果；實作本計畫時僅使用
  預檢確認的既有資源及新隔離工程輸出，若需安裝、替換資源或新增下載，先列明再確認。

#### 執行順序與各段出口

| 階段 | 工作 | 出口／不可以冒稱的事 |
| --- | --- | --- |
| A. 版本與環境預檢 | 核对原兩線有無新修改、最終候選及適用gate；核對Windows共享環境與本機cache。137先查實際GPU負載、自有／他人程序、Python／lock／CUDA、既有五模型與embedding身分和容量。核對研究交接，不能假裝已聯絡不可見的獨立fork agent。 | 明確可用的執行環境與輸出位置；GPU空閒不等於已預約。不關閉別人的程序，不用silent fallback。缺資源先報具體缺項，不把登入成功當環境通過。 |
| B. 完整工程回歸 | 依現有CI／runner執行產品、tests、scripts整體回歸、全專案typing、架構、docs與適用跨平台／視覺gates；完整Linux aggregate沿用既有coverage verifier。補同版本canonical source-diverse與本次階段驗收要求的完整代表性import catalog，使用現存資料、不重下載。 | 同head全部適用non-skipped checks成功，原失敗與skip理由保留。不同SHA不換標，同版本等價CI證據不在本機重跑。完整catalog以registry required membership為準，不把少數資料流程當全catalog。 |
| C. Windows實際產品流程 | 原生Windows走Import／class／channel／montage → preprocess → epoch → split → training → Evaluation → Saliency；資料輸入與測試產物隔離，核對真資料副作用和結果，不只開視窗。涵蓋正常、取消、停止／重跑、重開結果及前輪已修路徑。 | 當前source的真操作／截圖及相鄰failure證據；Windows gate與必要100／125／150% DPI通過。Linux offscreen不代替Windows，代理操作不代替使用者最終手測。 |
| D. 真模型Assistant | 使用現有精確產品模型及RAG，跑適用既有bounded model gate與正常ChatPanel真操作；涵蓋開窗、填參數、實際操作、缺資訊、不可執行、確認／取消、停止與錯誤回報。 | 完整模型輸入／原始輸出與實際結果可追查；既有模型限制如實保留，不調prompt／題目或反覆重抽來取得綠燈。GUI成功與raw model正確分開，既有bounded限制不冒稱Stable。 |
| E. 實驗量測驗收 | 先完成下面的量測正反例，再於137從新封存的同source工程包實跑；沿用 `package → dev → pilot → condition` 及包內 `run.sh`，不是另寫簡化runner。 | 五模型固定20筆工程smoke、capture／判分／報告／cleanup可核對；可從包內啟動及離線重建／audit。不把「有報表」或「20題全對」當量測正確的替代證據。 |
| F. 修復與獨立覆核 | 真defect先重現、補測、最小修理，再驗受影響及必要相鄰流程；高風險owner／publication／async與量測邊界由非作者覆核。主代理核實實際diff及產物，不只收摘要。 | 無未處置的功能／量測blocking finding；已知模型錯答與產品bug分開。source變動後更新相依證據及最終CI，不因單組通過就提前交付。 |
| G. 固定版本、集中手測 | 將Windows與137產物綁到最終clean／明確解釋的source；提供範圍清單、修正／限制、實驗報告入口及重跑命令。直接開Windows完整程式與一個PowerShell即時log，確認有回應後交回使用者。 | 使用者測的是代理已實機驗過的候選；附一行重啟命令。沒有額外Windows Live Log視窗，不自動merge、不持續監控手測，也不開始另一輪部件改善。 |

**C的必驗重點**：Split含subject模式與實際預期工作數，不只看第一個run啟動；training含停止
與重跑。Evaluation核對fold／run／Summary、長標籤／圖表與scroll、實際結果及結果重開。
Saliency核對真Compute／Recompute、SmoothGrad有界完成、背景時其他panel仍可用、游標恢復、
fold／run／class／method切換、2D／3D及warning偏好、視窗縮放與結果重開；不把只顯示
「背景計算」當成功。若契約明示某模型／方法不支援，驗正確blocked行為，不要求偷偷fallback。
此處「結果重開」指同一工作階段離開／返回panel；磁碟EvalRecord讀回另由backend自動
驗證涵蓋。目前沒有重啟程式後載入整個舊分析結果的GUI入口，不能把後端讀回當成此功能。
程式關閉／再開只驗啟動、適用設定與cleanup，不新增session恢復功能。

#### E的量測正確性：不只是腳本單元測試

- **身分與選擇**：核對單模型／核准子集／全部選擇、實際case／condition集合、source與
  模型revision／量化／template／prompt／RAG／生成設定；錯source、缺資源與設定漂移須拒絕，
  選擇不能只驗prepare清單而不驗實際啟動。沿用既有協定，不新增第二套manifest owner。
- **Capture與實際操作**：核對最終送模輸入、每次原始輸出、格式修復、Host admission、
  GUI／Command結果與terminal；對已知實際副作用核對，而非只信status字串。
- **Scorer正反例**：使用公開／合成且有獨立預期的正確與錯誤tool／參數、缺資訊、blocked、
  GUI取消、工具失敗及量測缺失案例；核對raw first、post-recovery、Host安全及最終結果不混算。
  對false positive／false negative及case分類作人工核對；必要補測不讀sealed題庫除錯。
- **計時與彙總**：以可控制時間的工程case與真run事件序列核對時段界線；載入／暖機另計，
  決策、格式重試、工具／人工等待按[研究規格](../validation/thesis_protocol.md)計算。
  分母、成功／失敗／逾時／無效量測、分位數與逐題輸出一致；不能遺漏失敗或用重試灌分。
- **中斷與重播**：使用獨立工程case驗背景啟動／SSH端退出、自有child逾時或可控中斷、
  同source/runtime續跑、跨source拒絕、不重覆計分／覆寫；不強殺共享GPU工作。
  從封存包另開新run，執行report-only及原scorer audit，核對原inputs/raw不變；
  既有協定不支援搬移未完成run後無縫resume，不將其列作本輪新功能。
- **137真跑邊界**：沿用protocol固定五模型各四題、共20筆 `engineering-smoke`，執行累積
  60分鐘预算（不含資源複製），不是完成時間保證。真RAG／終態／capture／cleanup缺項不能算通過；
  有效模型錯答保留，不因分數重跑，不當正式DEV成績或模型排名。額外故障注入用隔離工程
  case／fixture，不污染這20筆，也不重跑整套正式題庫。需要超出預算先報原因，不暗中加碼。

#### 分工、驗收與接續

- 主代理擁有候選、計畫、版本凍結及最終證據驗收；可獨立的產品／量測審查並行、寫入責任
  不重疊。CPU／文件工作可在模型執行時進行；同一GPU重型工作循序、一次一模型，
  不因平行化產生資源爭用。使用既有runner與ignored證據位置，不建新驗證平台或重複環境。
- 驗證命令、timeout與artifact政策由現有[驗證契約](../validation/README.md)、
  `scripts/dev/handoff_gate_spec.py`、CI及研究protocol擁有。本輪是完整功能驗收範圍，
  不是任意宣稱完整release dossier或Stable promotion；若宣稱full dossier須跑原完整manifest。
- **交付門檻**：適用同版本CI成功、Windows產品／Assistant實機證據齊全、137量測正反例及
  真smoke／封存audit完成、獨立覆核無blocker、來源一致。Pending／stale／missing gate
  不算通過。使用者不需逐slice手測；修理後只重验受影響及必要相鄰範圍，最後一次集中交付。
- **停止條件**：達到上述門檻且Windows程式已開啟有回應，交給使用者手測即停止主動操作。
  Compaction、單slice／commit完成或CI pending不是停止理由；缺新授權／必要資源才回報
  具體blocker。手測／merge另依明確批准，不自動把本計畫當merge授權。
- **可達效果**：證明指定版本在Windows代表流程與137指定工程量測範圍可運作，量測輸入、
  判分及計時可追查；留下雙線後續的共同起點。不能證明所有資料／硬體組合無bug、
  Saliency科學有效性、模型高準確率、研究統計效力或六部件設計／內容已全部打磨完成。
- **目前next（2026-09-27，恢復修理完成，待新候選整合驗證）**：整合PR #147未merge；
  下面已完成的大型驗證屬於舊候選 `fac3c714`。本次另修量測腳本，不改產品、模型或題目，
  不把既有證據改標為新SHA；修理commit是後續候選，精確身分由Git／PR擁有。
  該候選同head CI全綠，Linux彙整10,842 passed／82既定skip、line coverage88.048%；
  canonical source-diverse四案、完整134個required代表匯入、Windows真產品流程及native
  Saliency／3D stress均通過。真Assistant四步操作與五個確認／取消／Stop／錯誤情境
  完成並獨立覆核；81題bounded通過，但不是81題全對或Stable，既知模型限制保持。
  137 CUDA／runtime核對通過，原封裝的run `20260927-040225-001e867c` 在SSH退出後
  繼續執行，前四模型16筆已保存。最後Gemma3在四題開始前觸發既有180秒啟動逾時；
  第一權重分片約111秒，尚不能僅憑此判定NAS或量化為唯一成因。原失敗保留，不提高
  timeout／重抽或把16筆當完整20筆。Next先完成report-only／audit、inputs/raw不變及
  cleanup核對，獨立審查成因與必要處置；E未通過，不交付完整手測、不在134替代執行。
  原執行沒有Gemma載入期CPU／I/O採樣；依獨立覆核，在剩餘60分鐘工程預算內僅做一次
  同source／模型／量化／cache、原180秒上限的純載入診斷，新增自有PID資源觀測。
  不生成題目、不另暖機、不改逾時或下載／複製模型；記錄可能的warm-cache影響，
  診斷成功也不能代替缺少的四筆或自動授權重跑20筆。
  診斷於原180秒內36.019秒載入成功；warm-state採樣有I/O等待，不能倒推原逾時唯一成因。
  另經source與獨立覆核確認恢復缺口：condition初始化先建立第一case目錄，load失敗尚無
  case結果，卻使同source、已certified cleanup的missing-case resume被既有目錄保護拒絕。
  **直接修理slice**：依既有失敗恢復契約先RED，讓condition啟動／暖機證據留在condition
  範圍，真正開始case才建立case輸出；保留未知目錄、未認證cleanup與有效錯答不得重跑的
  guards。不刪／搬原失敗目錄、不新增owner或相容路徑，不改UI、prompt、scorer、模型或
  180秒上限。Focused驗真啟動失敗→cleanup→同source missing-case續跑，及正常首題、
  多題重用／報告capture路徑；最小diff另做獨立覆核。
  修理已完成，script一檔+6/-10、product零改動；test一檔+145/-9。
  原baseline42通過；RED重現三個提前建立目錄的失敗，未知目錄guard仍通過；
  直接GREEN45、最終五組相鄰Windows測試156通過／0skip、exit0，Ruff及diff check通過，
  獨立覆核無blocker。證據是real Qt／runtime／filesystem加受控external inference的
  分段啟動失敗／cleanup／pending選取／新session首題，並非宣稱真模型完整resume已跑通。
  修碼後需新clean source／同head CI及新工程run，不將原16筆接到新版本，也不把舊證據
  改標。原905.615秒＋純載入診斷保守預留300秒，共1205.615秒；本輪後續真模型仍受
  原3600秒累計工程預算約束（另有2394秒），不因新run重設額度，資源校驗另計。
  若必要驗證超出此預算或需改runtime/cache政策，明示新決策；不以無限重跑取得綠燈。
  共用NAS既有封裝可保留，但啟動前仍須canonical來源／資源校驗，且輸出記錄137真實身分。
  未到集中手測門檻；完成E及獨立覆核後才開Windows交付。舊134證據不刪、不換標。
  Windows手測checkout為 `D:\workspace_v2\projects\lab\xbrainlab-manual`，目前clean detached
  `fac3c714`，尚未開啟交付；修理後須更新為最終候選並核對相依證據，不能仍交舊版。
  共用既有Python與cache，不建立新環境。
  Next：提交／push此最小修理與文件，取得新head CI；同head重建137工程包（新包預算2394秒），
  新run固定20筆，保留fac3原失敗；補新候選尚未由CI提供的Windows、真Assistant／bounded及
  required catalog證據，再独立核對交付。不能只用product tree相同豁免已約定exact-source
  門檻，不另跑CI已提供的等價本機全套。Source凍結後進度存於既有ignored驗證報告，
  不為每次進度再移動候選；手測及merge仍分別等待使用者明確確認。

#### 驗證收尾發現（2026-09-27，89913442）

137新包固定20筆工程量測、report-only／audit及cleanup已完成並獨立核對；
134個required代表匯入與source-diverse也通過。原失敗與所有模型錯答保留。
Windows正常產品、SmoothGrad與互動3D操作通過，但native stress在active probe刪除後
以固定12ms檢查1ms QTimer心跳，得到false；view／owner實際刪除與零late callback均通過。
此固定等待未保證最後一次Qt事件派送，須先用延遲／停止timer正反例驗證oracle，不能重跑取綠。
另外macOS CI的真匯入流程在等待Channels啟用時逾時，仍須讀取owner與publication證據定位，
不能先假定只是CI慢或放寬timeout。

- 本次最小修理：只在證明測量缺口後，改既有stress heartbeat判定為有界等待真tick，
  保留active worker、已刪view、零late callback、owner drain及timeout fail closed；
  正反例使用真Qt／thread，外部引擎仍沿用既有controlled seam。
- 不改可見UI、模型、prompt、scorer或研究題目；不增加owner、不放寬產品cleanup條件。
  macOS先在原Channels等待失敗處補只讀診斷（capability reason、publication、render pending、
  parent enabled及modal）；原10秒上限及assertions不變。若證明產品缺陷，另在本段補精確
  最小repair後實作；不以推測改產品或忽略原CI失敗。
- Focused：延遲heartbeat在舊oracle失敗、新oracle成功；完全停止heartbeat仍失敗且worker
  被釋放；相關script unit、native lifecycle及Windows12+2壓力測試，獨立覆核actual diff。
- UI確認狀態：沒有新layout／文案／互動變化。Stop仍為同版本必要gates完成後Windows手測；
  89913442證據不換標。先暫停未執行的真模型情境，避免修理期間污染來源或重複生成。
- 已驗：既有62測試通過；真Qt engine／probe兩個延遲heartbeat正例在舊碼RED，兩個停止
  heartbeat負例仍fail closed且清理完整。修理後四例與相鄰測試共66通過／0skip，
  新等待限1秒且短於controlled worker的5秒；timeout仍釋放worker、drain owner再判失敗。
  Script +15/-3、tests +63，product零改動；macOS僅test failure diagnostics +54/-3。
  下一步：獨立覆核、凍結新候選及同head CI／尚缺native與量測證據；若macOS再失敗，
  以新增狀態證據修理，不把上次逾時宣稱已修復。137原budget已用1324.652615秒，
  後續仍共用剩餘2275秒（不是新3600秒）；不以新run重設預算或混接舊模型結果。

### 目標、基線與文件分工

- **目標**：形成一套能說清楚各部件的目的、輸入輸出、責任與取捨，且能被可靠測量的
  第一版工程候選；不是先追求最高分、最少行數或全產品零缺陷。
- **版本**：整合 worktree 為 `XBrainLab-agent-baseline`／`integration/agent-baseline`，
  以研究線 clean `293f1890` 為起點，帶入產品 checkpoint `8c50bee9`；原兩線保留。
  這不是 main 已發布基線，也不因任一線先前通過就稱共同基線已驗收。
  本輪先固定產品source、runtime與研究observer／runner相容的**共同工程基線**，再由
  兩線從同一精確版本接續。這不表示下方六塊設計／內容已打磨完成，也不自動成為
  正式研究起始配置；後續部件準備與研究條件仍依各自已確認的範圍、版本及授權驗收。
  該版本與既有研究 B0 的命名／比較關係，在啟動研究前核對；舊 B0 與其證據不覆寫，
  不只記 HEAD 而漏掉 dirty diff。新授權允許必要本機checkpoint／整合worktree，
  不備份權重、不覆寫原實驗產物；兩線原始來源保持可恢復。
- **接續順序**：**共同工程基線整合／固定版本 → 本節功能與量測驗收／集中手測 → 兩線接續部件準備與研究流程核對 →
  確認研究起始條件 → 依授權執行研究**。後續Development／Validation／凍結／Test
  的題庫與測量門檻以
  [研究規格](../validation/thesis_protocol.md)為準；下方M0–M6只保留歷史，不重新派工。
  必要pilot驗實驗流程與成本，不代替部件準備，也不默認重跑已完成的歷史pilot／d0。
  前置工作可查證方法、補足或清理 RAG 內容、釐清工具／prompt、做有界小驗證與修缺陷；
  不能因觸及這些部件就稱已開始 Development。Development 是在固定可靠起點後，
  按明定研究問題與搜尋預算做系統性改善比較，另保存候選與成績。
- **文件**：本節是本線順序／狀態／next step 的唯一入口；實作事實歸 architecture/current，
  公開行為決策歸 target，題數／split／判分／模型矩陣歸 thesis_protocol。
  研究線最新入口與完成狀態已向 clean `293f1890` 核對，不以舊里程碑推斷題目尚未完成，
  不讀取sealed Validation／Test；跨線整合統一由本代理協調，原研究worktree先唯讀保留。

### 共同工程整合已完成／下一步

產品 `8c50bee9` 與研究 `293f1890` 的必要改動已在 `integration/agent-baseline` 合成，
直接接合驗證與獨立覆核通過；結果、初次失敗及證據限制由
[Current](../current.md#assistant-integration-baseline)擁有。原兩線與歷史B0／DEV封存保留，
不更改scorer／題庫、不恢復失效產品欄位或另建owner。這是本機工程scope完成，不是main發布、
release handoff-ready或六部件全部通過。

先完成上方功能與量測驗收及集中手測，再以最終整合分支的精確clean commit為共同起點，
而不是繼續各自舊HEAD：產品線按下方順序
先討論Tool call／操作能力，再逐塊打磨；研究線先核對封存入口與起始配置，不自動重跑歷史
pilot／d0或開始新DEV／VALID／TEST。任何改變研究條件的後續部件改動另立candidate，
舊結果不換標。公開工具、可見UI、模型／RAG／prompt政策改變仍須先確認；原worktree、
使用者settings及資料不刪除；本輪push／驗證PR依上方新授權執行，仍不merge。

### 後續部件打磨第一步：先確認目前架構與品質

使用者再次明定：更進一步前須先確認現況。這是逐部件討論的共同起點，不直接啟動新一轮
大改或假定每塊都有問題。前輪已核實的責任分析與仍適用證據沿用；只補本次產品部件視角
尚未回答的問題與來源已變更的證據，不為新計畫重跑等價全套。

- **架構現況**：用一條真實要求串起工具公開、context／RAG、模型輸出、驗證、確認、
  Command／GUI交接與結果回報，查責任是否清楚、是否重複決策、是否存在不必要等待或轉接。
- **設計與內容品質**：核對工具契約、prompt的資訊／規則、RAG內容與方法是否足以承擔
  各自目的；查缺項、矛盾、過期、重複及資料來源，不能只以可執行或沒有exception判合格。
- **實作與證據品質**：檢查直接相關產品碼、tests／fixtures、scripts／設定／文件的一致性；
  大檔與過度設計、真正行為oracle、mock邊界、失敗／取消／重跑與可重現性一起判斷。
  區分已驗、未驗與失效證據，不把passing數當coverage，也不以審查取代必要動態驗證。
- **交付與判斷**：先給目前系統的簡明評價，每塊列「已有證據支持保留」「進入打磨前需修」
  或「尚待查證」及其依據；獨立reviewer核對重要結論、重大缺口與保留理由，主代理負責
  最後核實。未查清項不算通過，不承諾永不出錯，也不因行數大就預設要拆。
- **出口**：架構／品質現況與已知缺口明確後，逐塊討論處置；共同工程基線先保護接合
  可靠性，後續仍須在核准的研究起點前處置必要內容／方法缺口，不把基礎修理當調優成績。

### 每塊固定的討論與施工節奏

1. **我先準備現況**：從正式入口追到實際模型輸入、輸出、操作與錯誤；提供具體例子，
   清楚分開已實作、設計目標及未知項，不只給 class／檔案圖。
2. **補查依據與內容盤點**：查相關原始論文／官方技術文件，記適用情境與限制；核對
   實際內容、分布、重複與維護來源。分開標示基本工程要求、可選方法與待驗假設；
   不因某技術流行就導入，也不把外部參數／效果直接套成本專案標準。
3. **一起做一組有界決策**：每次一個部件，提出保留／調整／刪除選项、理由、成本與
   可觀察的驗收方式；集中討論會影響使用行為或研究的選擇，不逐個 helper 詢問。
   保留現有 UI 為預設；可見行為、public tool contract 或研究條件改變先明確確認。
4. **確認後施工與小驗證**：維持既有 owner／Command 路徑；同步處理直接 tests、fixtures、
   scripts、文件與無用能力。先 characterization，真 defect 先 RED，再做 focused integration。
   Engineering checks 與有界模型小驗證使用明確標記的公開工程樣例／準備用案例並保存軌跡，
   不冒稱 Development 實驗、不讀 Validation／Test 除錯。模型下載／執行仍依實際授權與
   資源限制；安全／功能與內容缺口須在可靠基礎驗收前修好，不推給後續研究。
5. **獨立覆核後銜接下一塊**：review 實際 diff、內容與證據，同時檢查未改部分的保留理由；
   無 blocker 才記本塊完成。若需跨塊修理，記清直接依賴，不把一塊完成當整體完成。
   保留無新證據不重開決策的原則；每塊不另要求完整手測或 merge。

### 建議順序與每塊出口

順序是討論提案，不把表內候選改法當核准契約。各塊均沿用上述五步。

| 部件 | 要一起釐清的內容 | 本塊出口與驗證 |
| --- | --- | --- |
| 1. Tool call／操作能力 | 現行工具如何區分開窗、填參數、直接操作、導覽與回覆；名稱／描述／schema是否清楚；缺資訊、狀態不可用、確認與成功各代表什麼；是否有重疊或缺口。 | 用代表性原話→實際公開工具→模型決策→backend／UI結果說清楚；逐工具契約與正常、缺資訊、不應操作、失敗邊界可核對，不能把開窗／排程當任務完成。 |
| 2. Context／prompt／歷史 | 模型實際看到哪些狀態、工具、規則、上一輪內容；哪些是權威、哪些只是參考；是否重複、矛盾、過期或超出 token budget。 | 保存可讀的最終模型輸入樣本；檢查資訊來源、順序、截斷、無資料／長輸入與狀態改變；不讓評分答案進入 prompt。 |
| 3. RAG 與知識／範例庫 | 它究竟補什麼；schema已足夠的情況是否需要檢索；資料來源、條目粒度、分布與更新；embedding、關鍵字混合、top-k、排序、token成本與失敗行為各有何依據。 | 盤點實際內容與獨立情境，不用總筆數冒充涵蓋；以獨立於庫內原文的準備用查詢核對相關條目命中、錯誤／無關取回、缺適用資料與延遲，修好已知內容與檢索缺口。基礎可用性小驗證不冒稱正式效益；改善幅度與一般化效果留待可靠基礎完成後的實驗回答。 |
| 4. 回合控制、確認與使用者回饋 | 一回合何時完成；缺資訊接續、格式修復、backend失敗、人工取消與Stop有何差別；忙碌、等待人工、錯誤與再次操作如何呈現。 | 正常與故障路徑含遲到／重複回覆、拒絕確認、關閉／重啟；驗副作用恰一次、舊回覆不覆蓋新狀態，重試不重送已執行操作。UI有變才做局部預覽確認，不重開已接受排版。 |
| 5. 模型與 runtime | 精確模型／模板與設定、載入／切換、離線資源、取消／釋放、冷啟動與逐題等待如何區分；現行產品與研究模型支援是否一致。 | 核对 pinned identity與可行性，無silent fallback；依授權做有界真模型 smoke及失敗／清理檢查。時間按載入、RAG準備、決策、操作分開；未量測不承諾加速，不為比較一次載入全部權重。 |
| 6. Evaluator／評估題庫／實驗腳本 | 和研究線核對已備妥題目、family分組與適用工具；scorer是否誤判、觀測是否貼近真產品；單一入口如何選實驗、保存輸入／輸出／失敗並重現。 | 評估oracle／scorer與產品路徑對齐；正常、錯誤、不操作與未完成不混算，先做判分正反例與人工抽核。沿用既有研究規格，不另定題數或擴張矩陣；正式Test只由保管者核實封存。 |

### RAG 庫數量與評估題數不混為一談

- **RAG corpus**：數原始來源、有效條目、重複／近重複及各工具／stage／情境覆蓋，
  不把改寫筆數當獨立知識。補內容由缺口驅動；top-k、混合搜尋或reranker均待具體證據，
  不是預先承諾導入。避免把失效工具、其他狀態的例子或錯誤參數當可執行指示。
- **評估題庫**：依 protocol 核對 family、類別與split的數量和獨立性；是否足以回答研究問題，
  要看每類／每工具的樣本與不確定性，不能只看總題數或把repeats算成新題。
  已公開工程例子不得改標封存Test，正式測試題／oracle不得回填RAG；Validation不參與內容調整。
- **外部依據起點**：[Contextual Retrieval](https://www.anthropic.com/engineering/contextual-retrieval)
  用於理解chunk／混合搜尋／rerank的取捨；[RAG evaluation](https://learn.microsoft.com/en-us/azure/foundry/concepts/evaluation-evaluators/rag-evaluators)
  用於區分檢索與最終輸出評估。它們不是本產品效果證據，也沒有在此核准任何最低條目數。

### 全部件整合、停止條件與接續

- 每塊都回答前輪固定的四項：實作是否過度複雜、測試是否真保護行為、不拆是否有具體
  工程理由、是否涵蓋原始完整範圍；這次另確認部件目的／內容／方法合理性，不只審程式碼。
- 全部六塊的已確認改善完成、已知重要缺陷與阻擋證據缺口處置後，做一次跨部件獨立覆核，
  核對相同候選的適用CI／真模型／Windows gates，再集中一次端到端手測。
  各塊的可見設計確認只用局部預覽，不要求每次全套重測；需要修理只驗受影響及必要相鄰流程。
- 凍結第一版時保存精確source（含所需程式碼備份身分）、模型／模板／prompt、工具契約、
  RAG內容／索引、設定／環境、題庫／scorer身分及可重跑入口；工程版本與研究B0不混稱。
  不默認複製全部資料或權重，也不把目前尚未實作的runner命令寫成已可執行。
- 可靠基礎驗收完成後，核對既有題庫與測量就緒門檻，再依授權跑pilot → 有界Development →
  Validation選版 → 凍結正式配置 → Test。Development不得先於可靠基礎驗收啟動；
  保存負結果，不以分數漂亮才結束，也不把基礎功能修好宣稱為研究改善效果。
- 只對新證據、具體缺陷、契約衝突或必要依賴重開已定部件；非阻擋改善最多列三項後續，
  不無限追加方法。壓縮不丟失決策；每次對話更新本節當前塊與next step，不另寫平行worklog。
- **目前狀態／Next**：第一輪架構／品質核對與最新user來源修理已完成；目前先完成上方
  共同工程基線整合，再從 **Tool call** 的代表情境討論六塊打磨。未下載／載入模型、
  未讀sealed Validation／Test；研究線最新工程能力已核對，但不等於共同基線已驗收。
- **本次文件驗收**：與既有研究規格的分工／基線／順序／授權不衝突，連結、guidance audit、
  strict docs build通過即交付討論計畫；不執行模型評測或以文件通過宣稱產品就緒。

### 初步審查結論與仍待討論的部件

- **可保留**：18個正式工具沿用同一backend publication、Host驗證、Command／GUI
  outcome及correlation邊界；RAG是英文操作範例檢索，不是EEG文件知識庫。沒有證據支持
  新增執行owner或重寫整套架構。
- **已修復的來源缺陷**：最新user以 `System:`／`Tool Output:` 開頭曾被誤排除，
  模型輸入與參數來源驗證回退上一要求；6案RED包含真Command錯用舊128Hz而非當前64Hz。
  `8c50bee9` 以既有history的明確 `internal` role隔離host trace，保留真人原文；
  outbound仍只有既有模型roles。331案直接回歸與22案runner回歸、獨立review通過。
  這是model-free工程修理，沒有重跑模型或把舊研究結果換標。
- **本線契約／RAG待釐清**：target對select_channels stage有矛盾、resample的number
  與實作integer不一致、repair範圍與目前terminal分界不同；不自動放寬或增加重試。
  corpus為72筆／18工具各4筆／29種tool+parameters組合，均是單步肯定正例。
  公開36正例probe至少1筆與corpus原文完全重合，不能沿用文字獨立性主張；六題
  diagnostic缺實質相關性oracle。既有34/36僅是舊檢索工程結果，不是本輪Agent成績。
  target canonical/top-2與目前semantic/top-3仍待決，未批准擴库或新方法。
- **評估腳本結論限於本線副本**：本線舊runner的dirty內容身分、完整capture、真操作
  outcome與關鍵字scorer有證據限制；不能據此判定研究線最新版也有相同缺口。
  2026-09-24 核對研究 clean `293f1890` 與產品 checkpoint `8c50bee9`，共同基點為main
  `94328196`；研究線領先main38個commits，不是舊dirty runner副本。
  研究線不只改scripts，也改controller／parser／prompt_policy／worker／local backend／
  engine／model_catalog／main_window，必須按共有契約整合，不能只複製scripts目錄。
  已核對最新入口、封存／capture與真操作觀測，整合已獲授權；在獨立候選逐一處理共有
  邊界並用公開工程案例驗證。新版本的成績另記，不把舊分數當新系統證據，
  不維護兩套互相追補的runner，不改sealed題庫或scorer政策。

## Completed record — 產品 Assistant 深度清理（整合前 checkpoint）

以下保留產品線施工與當時覆核紀錄，已固定於 `8c50bee9`；原先漏失的最新要求來源錯置
亦已修復並獨立覆核。下方數字與dirty來源描述屬當時證據，不是新整合版本的證據；
不能據此宣稱共同Agent基線已驗收。

先前把已完成切片誤報為完整模組結案的判斷已撤回。2026-09-24 重新按原始範圍比較
重要責任群的保留／收斂／拆分方案，完成 source 改善、同候選直接整合與非實作者覆核。
最後的 long-session fixture 與 capture 樣式污染亦已處置；四項原始結案標準均完成，
無剩餘已確認的 in-scope blocker。主代理已核對實際 diff、XML 與保留理由。
目前為 `64bd5fdca29ae10ea0ad089b24f3d5b41e2137d1` 加本輪 dirty diff 的本機
scope-complete，不是 handoff-ready；沒有 commit／push／PR／merge 授權或同 head CI。

### 四項結案標準與本次處置

| 必須回答的問題 | 已完成處置與判斷依據 |
| --- | --- |
| 功能必要，實作是否仍過度複雜？ | 刪 accepted 同步回呼 FIFO、重複 shutdown observer、必備依賴的 optional fallback、舊模板／metadata 尾鏈、下載清理 subclass 與 RAG 重複 filter。取消、失敗資源持有、exact correlation、confirmation 與 cache integrity 保留。 |
| 測試通過，是否真正保護重要行為？ | 真 Qt dispatcher 強制先 emit，驗 GUI 返回後處理及 transcript 順序；真 delayed shutdown 驗失敗通知與最終釋放；真 HF 停止條件取消生成 thread，空 criteria mutation 確實失敗。真 transcript／timer 保護通知重試、clear／close；兩個 CLI 真入口拒 missing／failed／duplicate／stale terminal，不以有文字判成功。 |
| 決定不拆，是否有工程依據？ | 下方逐責任群比較狀態、affinity、回呼與替代方案；已拆完整 viewport，publication 歸回既有 coordinator，不替仍大的檔案給 blanket approval。 |
| 切片完成，是否滿足原始整體目標？ | 下方原始範圍保留 Agent／tools／core／RAG、Chat、runtime、接線與相關 tests／scripts／config／docs，並揭露共享檔閱讀界線；最後整合與非實作者模組覆核已通過，不以單片 approval 代替。 |

### 邊界決策與保留理由

- **ChatPanel → ChatTranscriptView**：完整移交 widgets／layout、分批重建、六個 timers、
  reader anchor／follow-tail；Panel 保留 runtime／turn／composer／confirmation 呈現。
  四個既有 transient surfaces 借用同一 viewport，三個窄 signals 協調幾何與 replacement。
  只抽 rebuild helper 會留下十多個跨類欄位／回呼；搬到 ChatController 會混入 widgets，
  皆否決。新增 presentation class／責任 owner 一個，但沒有新增可變 history／runtime policy。
  刪 Panel 舊 append／layout 相容入口，產品 capture 與 tests 全部遷到真正 owner。
- **Publication → 既有 coordinator**：bridge、rendered revision、兩個 retry timers、
  render commit 與 training notice 歸同一 owner；Manager 只提供 status／terminal rendering、
  idle 查詢三個窄 ports。只搬 projection 仍需跨類拼裝同一 retry transaction，另建 owner
  無必要；因此由既有 coordinator 直接擁有 Qt lifecycle，刪 schedule DTO／test-only snapshot。
  Assistant 不 acknowledge Desktop，失敗 obligation、latest revision、clear／close 保留。
- **Controller 保留的組合責任**：generation／worker／RAG shutdown 共同處理 affinity、
  回呼斷線、late callback fence、failed close retry 與 release。搬往 GUI Lifecycle 是反向
  依賴與錯 thread；另建 shutdown owner 需大量 resource ports 或整個 Controller proxy，
  沒有移除政策。proposal／confirmation／execution 已交既有 policy、pending、tool owners；
  debug 只保留 model-free origin，執行鏈共用，另拆只會新增 history／metrics／terminal 接線。
- **Runtime 保留不同生命週期**：admission reservation 在 Controller 綁定前；delivery ACK、
  terminal-before-ACK、startup rollback、dispatcher cleanup 不是同一狀態。
  deactivation 可重新啟用，永久 close 不可，不能盲目合併。physical cleanup 由 dispatcher
  單一回報，刪重複 observer；未 bind startup rollback 與 failed cleanup ownership 仍必要。
- **Manager 保留兩個呈現入口**：normal/debug 的 composer、rejection 與 copy 不同，但
  reservation／reject／matching commit 只有 turn_state 一個 owner。抽共用 helper 需新增
  錯誤 taxonomy、文案 flags 或 callback 協定，沒有刪除 state policy。command-in-flight
  與含 GUI handoff 的 turn RUNNING 語意不同，不能以後者替代 Stop 門禁。
- **Core／RAG／tools 保留信任界線**：process owner 與 model-thread lease、persisted
  integrity 與 operation lease、tool schema 與 backend capability 各保護不同邊界。
  Dispatcher 的 optional shutdown signal 有真 scripted walkthrough controller consumer，
  同步 close 是其正式生命週期；不是為測試保留。兩現行模型原生 system role，已刪無用
  capability 欄位與不可達 template fallback，現行 prompt／token budget 不改。

### 授權、複雜度與整合規則

- **Outcome／非目標**：維持既有可見 UI、功能、18 tools、模型／prompt／RAG policy、
  Command 與 EEG 語意。不改研究 scorer／題庫／artifact、使用者 settings、其他 worktree，
  不下載或執行 commit／push／PR／merge。既有 Evaluation／Saliency 修改保留、不計本次增量。
- **複雜度**：唯一新增 class 是完整 viewport presentation owner；其餘責任歸回既有 owner。
  首次 viewport 候選 +804/-734，觸及略超1,500行的 architecture exception 明確限於完整
  layout／六 timers／anchor／rebuild 移交，無有效的半遷移中間態，不用 facade 或壓縮碼避門檻。
  四大檔並非字數達標就結案；按上列實際耦合選擇拆分或保留。
- **驗證方法**：Windows native、timeout／core=0、先 passing characterization；
  發現真缺陷再 RED→GREEN。保留失敗報告，不以放寬 assertion 消除紅燈。
  模型、時鐘、外部 IO 可隔離；queued delivery、transcript、timers、QObject 銷毀採真實機制。
  Source-bound capture fingerprint 包含新 viewport 與 coordinator；bytes mutation 會改 fingerprint。
- **整合中發現**：截圖量測把 QRect inclusive bottom 算多一像素，已補12px接受／13px拒絕
  邊界測試並修量測式，門檻未改。整組失敗已定位為 UIUX capture tests 未還原 QApplication
  style（native空白12px、裸Fusion14px、正式完整theme10px）。還原後又揭露四個截圖測試
  隱性依賴前例的Fusion；已明確套用正式capture樣式並在各測試後還原，不改圖像門檻。
  整組371通過，session結束樣式仍是原windows11，不留跨測試污染。
  Long-session 舊 runtime fixture 缺必要 signal 且使用同步 submit，已遷 Qt queued delivery，
  原資料／流程／延遲斷言不改，含202回合 soak 的24案通過。
- **回退／基準**：本次 before 為
  `/tmp/xbrainlab-agent-boundaries-before-20260924.iEtqAF.tar.gz`，只撤 owned patch。
  下方以前階段數字不重計為本次成果；測試組有重疊，不能相加宣稱 coverage。
- **結案／發布界線**：同候選直接整合、文件同步與非實作者四項結案核對完成。
  正式發布另需授權與同 clean head applicable CI／人工 gates；本機深度清理不等於
  handoff-ready，不因本輪結案自行建立PR或要求合併。

### 原始範圍與保留理由

以下是模組／直接共享路徑覆蓋，不宣稱整個 repository 或所有測試逐行閱讀。
非實作者覆核包含未修改的 source，不能以單片 approval 取代模組結案。

| 範圍與入口 | 責任／去留 | 閱讀與直接證據 |
| --- | --- | --- |
| `llm/agent` 27 檔（含 package） | Controller 組合 turn；orchestrator 擁有 correlation，pending owner 擁有待決互動；保留 parser/schema/origin/confirmation/publication 邊界。刪舊入口、未用參數／DTO／欄位及不可達 handoff 路由。 | 全 source；大型 controller 測試讀相關 fixtures／案例及全部增量，非全測試逐行。正式 parser、18-tool producer、取消與原生 import dialog 路徑。 |
| `llm/tools` 10 檔＋action contracts／pipeline | registry/schema→capability→Command 或 typed UI request，不新增 policy owner。分類與 model-facing projection 保留真 consumer；結果歸既有 ToolCommandResult。 | 全 source、直接 caller；工具／verifier 與真 public projection 的 hostile、cyclic、redaction 測試。 |
| `llm/core`／backends 11 檔 | config→resolver→process owner→child engine→local backend。保留 exact model、quota、consent、設定 migration、失敗時持有資源。刪假 owner/thread fallback、無用 config API 與無 producer fallback 標記。 | 全 source；config 全測試，其他直接 fixture／案例和全部 diff；實際 process ownership tests，未下載或重跑真模型。 |
| RAG 6 Python 檔＋bundled corpus | retriever 擁有 client／embedding，indexer 借用；manifest/digest 為持久化信任檢查。BM25／ranking／corpus 保留不變。 | 全 source、indexer/security 全測試及直接 retriever 案例；未將單元回歸冒稱新模型準確率。 |
| Chat 13 檔＋ChatController | 保留呈現、scroll、bounded history、restore 與確認。typed history 唯一可變紀錄；viewport 責任已完整移交，刪隱藏 renderer、無用樣式／icon、雙 list 和不可達 update transport。 | 全 source；native chat／controller、真 subscriber reentry、anchor／rebind／delete-during-rebuild 與202回合兩次 prune，非只有 panel queue。 |
| Manager／runtime／dispatcher／publication／presentation／status | 既有 owner 分掌 Qt affinity、turn admission、resource lifecycle 與 publication acknowledgement；identity 各守不同 async 邊界。刪測試専用入口與無效傳遞，Stop 晚到 navigation callback 用既有 lease fence。 | 各 owner 全 source 由分工覆蓋、主 agent 查實際 diff；真 Qt activation、取消、關閉／重試及 revision tests，無新控制層。 |
| workflow host／router；settings/download／MainWindow 接線 | 真 GUI completion 留在既有 dialog／panel owner；只保留 registry 產生的 Agent routes，lazy navigation／command pending 不是成功 terminal。Settings standalone、app-parent download 與 optional manager 有實際使用情境。 | host/router/settings 全檔；MainWindow 等共享檔只查 Assistant 直接路徑。真 import dialog 取消、Stop 後 callback 及訓練設定路由回歸。 |
| 產品 capture／DPI／RAG／setup scripts、profiles | local 單回合、雙回合、UI geometry、DPI 與人工 profiles 各有不同 consumer，不刪有用途腳本。capture 成功需 matching request＋typed result＋successful terminal，不以有文字判成功。 | 兩個 local CLI、UIUX／DPI／driver／contract／capture config／fixture／5 profiles 全讀；巨大共享 capture、setup、verify 等只讀相關路徑。研究 evaluator 僅同步內部參數，scorer／題庫不改。 |
| 相關 tests／fixtures／arch guards | 保留真外部資源隔離；刪無效入口専屬 AST 模擬器／白名單，保留 hostile payload、failed-close、stale／duplicate 保護。 | 各區清楚區分全檔與直接案例；passing counts 不代表 coverage 提升。尚無本輪 coverage 百分比或全產品 CI。 |
| 文件／設定／開發規則 | current architecture 擁有實際責任；now 記錄結案與發布界線。refactor workflow 要求原始模組範圍獨立結案。 | guidance audit／strict docs build；不碰使用者 settings、模型政策、研究 worktree。target 的 select_channels stage 文案矛盾只列非阻擋 follow-up，不偷改契約。 |

具名保留：`compact_tool_state.interpretation` 有真 backend snapshot producer；parser
`_BARE_COMMANDS` 仍用於 malformed-output 診斷，不是執行兼容入口。未用 result／metadata
專屬測試已移除或遷到真 producer，hostile payload、取消／stale／duplicate 安全斷言保留。
Controller／Manager 仍大，但已評估並否決只搬行數、增加 adapter 的微型抽取。

### 本次追加清理的改動與證據

相對本次 boundaries before，不含前階段、Evaluation／Saliency 或 main：production 14檔
+1050/-1381（淨減331），tests 22檔 +1582/-709（淨增873），scripts 7檔 +112/-71
（淨增41）；文件與流程規則另計。測試增加包含真行為 oracle、失敗時序與正式入口基線，
不是為 deleted helper 留相容測試。尚未量測 coverage 百分比。

目前大型檔案：Controller 2420行、Manager 1447行、RuntimeLifecycle 1477行、Panel 1426行；
新 viewport 752行。這些是維護風險訊號，不是零風險保證，保留理由以上方責任分析為準。

以下為同一未提交 candidate 的 Windows native focused evidence，各組重疊，不相加：

- UI／admission／publication／ChatController／RAG：568通過；最後 canonical import 調整後的
  publication＋architecture另269通過。
- Runtime units330、runtime／offline context integration24、core template／取消64、
  downloader／lifecycle75、catalog38均通過。Downloader最初Windows長路徑fixture失敗，
  改短pytest專用temp後通過，沒有改模型／cache政策。
- Product UI walkthrough10通過；long-session24通過，含202回合／兩次prune，
  每回合 terminal 與 admission exact correlation 一致。
- 六個source-bound capture／DPI script test files整組371通過，零失敗／錯誤／跳過；
  樣式隔離7個focused正反例亦通過，原12px與影像門檻不變。
- 所需 Ruff／format、修改production typing與兩個local CLI typing通過；guidance audit、
  strict docs build通過。共享 evidence script 的既有 QLabel optional typing 診斷仍存在，
  未把該整檔宣稱零診斷。

XML 位於 `build/assistant-cleanup/`；紅燈、mutation與前候選報告保留原意，未改標成綠燈。
沒有本次真模型新實驗、新機網路安裝、clean-head CI或新版人工驗收；不宣稱全repo逐檔
或所有測試逐行讀完。目標文件 `select_channels` stage 文案矛盾是另需契約決策的非阻擋
follow-up，不在本輪偷改公開契約。

### 前一階段驗證與限制（不是本次深度結案）

以下均為 dirty working tree 的 Windows native、model-free 證據；不是 clean-head CI、真人
workflow、模型準確率或論文結果。各組有重疊，不相加宣稱 coverage：

- 最後批准尾項完成後：Agent＋architecture **1179 passed**；tools/root **185 passed**；
  UI **388 passed**；Agent／runtime／LLM integration **80 passed**；native host／Import／Stop
  與相關 host units **57 passed**；source-bound scripts **316 passed**。原始報告保留在
  `build/assistant-cleanup/`，均正常 exit0。
- Response/parser 同選集在施工前為497通過、兩個新增 fixture 缺少 json import；補 import 後
  該兩案在 production 修改前通過。施工後 **498 passed**，僅刪一個未用 natural-language
  capability 專屬案；evaluator recovery／trajectory **9 passed**。108個現有公開 parser 測試
  literal、432次 recovery 對照，其保留欄位／action／七個 taxonomy 字串逐項一致。
- 尾項 direct Ruff／typing 與分片覆核已通過。此尾项對 before archive：production 15檔
  +51/-379（淨減328），tests 20檔 +201/-325（淨減124），scripts 無新增變更；文件另計。
- 整輪重開清理對 reclosure before（ChatController 使用獨立 before）：production 43檔
  +259/-1750（淨減1491），tests 52檔 +1279/-2212（淨減933），scripts 8檔 +96/-30
  （淨增66）；workflow 1檔 +10/-10。這不含此前 Saliency／Evaluation／第一輪 Agent 修改。
- 較早候選證據保留：core281、RAG107、UI／ChatController652、git-bound scripts316 曾通過，
  不重標為尾項後執行；Stop 有真 Manager callback RED→GREEN。早先 Flow72中一個舊 fixture 參數已遷移，
  原失敗未改標成功。腳本最初16個失敗來自兩個長路徑、兩個抓圖 seam、12個空 Git identity；
  以短 pytest-owned 路徑、明確外部 seam 及正確 Windows Git metadata 修正後重跑，不關閉檢查。
- 既有 cache 真離線 RAG gate 曾通過（72 points、Top-3 34/36），未做新機完整安裝／網路下載。
  另一次舊跨域單 process Qt teardown timeout 未證明原因，沒有宣稱已修；採既有隔離 runner。
  歷史數字不當作本次真模型或人工驗收，也不修改研究 sealed cases／scorer／舊 artifact。

先前 reviewer 的廣泛結論已撤回；上述測試與有效清理保留，不回寫成新候選證據。
本次責任群替代方案與最終整合結果已在上方補齊。尚未量測完整 coverage 百分比。Current 責任見
[Agent 架構](../architecture/agent.md)，安裝限制見[本機環境](../developer/local-setup.md)；
本頁不保留逐片施工流水帳。

## Current — Evaluation 內部清理與補測完成，尚未發布

使用者已要求依逐模組六項準則，加上完整範圍清單、數值／不必要工作檢查、獨立 reviewer
退件權審查 Evaluation；隨後授權不改 UI／功能／資料語意的清理與補測，並明確授權五個
無產品 caller 的舊數值 API 退役。已完成修理、補測及非實作者交叉覆核，無剩餘已確認
的 in-scope blocker。下方 UI 迭代是歷史證據，不是新的待辦。
這是本機 scope-complete，不是 handoff-ready：仍為 `64bd5fdc` 加本輪 dirty diff，
沒有 clean head CI，也尚無 commit／push／PR／merge 授權。main 與使用者 settings 未改。

- 範圍：產品 Evaluation（非 Assistant 評測研究線）：render publisher／work、panel 與
  四個呈現檔、EvalRecord／TrainRecord／Evaluator 的結果與分類計算路徑、analysis/service／
  state／UI ports 直接邊界、相關測試與 product evidence scripts。共享檔只審／改相關段落。
- 證據：三路独立唯讀審查確認：相同 Evaluation signature publication 清掉已顯示 DTO，
  百分比 checkbox 後續不更新；舊 backend get_confusion_figure 只有測試 caller；部分
  回呼便利分支／DTO 欄位／work API 無正式 caller；數值 oracle 對稱或只驗 support；
  screenshot readability 只驗整張 canvas，20 類 canvas2028×1809／viewport968×526
  仍回 fully_visible=True。數值真 probe 正確，100k×4 pooled read 約5.15–5.56ms，
  尚無可支持的效能 blocker，不新增 cache／worker 或架構層。
- Outcome：上述已確認缺口關閉；入口、責任、去留、保留理由及測試對應逐塊覆核。
  保留現有排版、完整名稱可捲動、統計 pooling 定義、public Command/query、split／
  producer identity、immutable DTO、取消／stale／close／publication 保護。
- A 完成：populated panel no-op publication 先 RED 再修；刪 test-only callback／work／
  UI adapter leaves，producer serialized contract 不改。此切片 production +9/-60，淨減51行。
- B 完成：不對稱、unequal-fold、未完成 sentinel 手算 oracle；刪 backend confusion
  plotting、`TrainRecord.get_acc/get_auc/get_kappa`、`EvalRecord.get_auc/get_kappa`，
  保留有正式 caller 的 `EvalRecord.get_acc`。AUC 收回既有 Evaluator，不留多餘 helper；
  數值／持久化 oracle 移到正式 scorer 與獨立 sklearn 對照。production +3/-174，淨減171行。
- C 完成：canvas 完整／viewport 可見／捲動可達分開判定，必要 gate 不放寬；真 widget
  回歸與真 service→panel workflow 已完成。evidence script +24/-3；沒有刪整支正式腳本。
- 以上內部 A/B 共 production +12/-234、淨減222行，與前輪 Saliency／Evaluation UI
  diff 分開計算；不以整個 dirty worktree 當本次新增量。新 owner／module／class 均為零。

### 最終 focused evidence 與獨立覆核

- Windows Evaluation UI／ports／read-side architecture：183 passed；
  `build/evaluation-ui-preview/integrated-native.xml`。
- 數值／record persistence／render／deterministic pipeline／training history：144 passed；
  五 API 退役獨立覆核另選18項通過（不與前述數量相加）。
- 最終真 training→persisted results→Evaluation Windows workflow：1 passed；
  `build/evaluation-ui-preview/service-workflow-native.xml`。
- source-bound evidence focused：34 passed、197 deselected；
  `build/evaluation-ui-preview/evidence-viewport-native.xml`。
  前兩次33/34的原因已查清：WSL建立的worktree `.git`含Linux絕對路徑，Windows Git
  無法查來源而回空 digest，不是已證實的source drift；僅在驗證程序指定正確Windows
  `GIT_DIR`／`GIT_WORK_TREE`後通過，未改Git metadata／產品／斷言。
- 最終來源的既有 `run_public_cross_source_training_smoke.py --format json --strict`：
  4 passed、0 missing／failed；EDF／GDF完成訓練與artifact reload，EEGLAB／CNT保留
  import／preprocess及缺少足夠class語意時阻擋監督epoch，不能宣稱四者都做了訓練。
- 修改檔 Ruff／format、production typing、diff check 通過。共享 evidence script 的
  Assistant label 可空型別診斷在 HEAD baseline 已存在，本輪未改其行為，不冒稱該整檔零診斷。
- 非實作者覆核實際diff與證據：生命週期／數值與API／evidence producer／真service
  integration／測試替代／範圍完整性均無blocking finding；不是實作者自己的PASS宣告。
  合成fixture不代表科學品質；新integration未涵蓋Validation split或model-summary真worker
  失敗，不替代既有窄層保護，也不替代未來同headCI／真人Windows驗收。

### Evaluation 範圍盤點與保留理由

以下是本模組範圍，不是全專案逐檔審查。完整閱讀的專属核心為
`ui/panels/evaluation/` 五檔（含匯出入口）與 `application/evaluation_render.py`、
`evaluation_work.py`；共享檔只涵蓋列明路徑，沒有把搜尋命中當作讀完整檔。

| 區塊／入口 | 清理或保留判斷 | 直接保護 |
| --- | --- | --- |
| Service → render publisher → immutable DTO | 保留來源／split／producer／選取前後驗證、不可變複本；跨 Fold 限同 cohort／round／Run、互斥 Test masks；先 pooling predictions 再算 metrics | render tests：不對稱手算、unequal-fold、未完成排除、來源與 stale 拒絕 |
| Service → evaluation work → shared registry | 保留 admission／single claim／checkpoint／commit fence；刪無正式 caller 的 cancel／snapshot 轉接，不另建取消 owner | work tests：取消、重試、single claim、request identity |
| Panel → typed UI ports → worker → charts | 刪 test-only callback overload、wait helper、未使用 DTO storage、舊 scalar split fallback、無 caller 的 UI 同步 adapter；真正 service 同步入口仍供 scripts 使用 | publication／panel／read-side tests；真 service workflow |
| Model summary 與 Qt lifecycle | 保留 bounded cache、request/worker identity、pending latest、terminal callback 後釋放及 shutdown／cleanup 差異；這些分別保護可重現 stale／關閉邊界，不是第二套業務真相 | summary failure、A→B→A、取消／close／late callback tests |
| Confusion matrix／bar chart／table | 只呈現 detached 數值；保留既有 label 量測、局部捲動、figure cleanup；百分比只影響矩陣，不改 metrics | 真 artist／table 數值、geometry、wheel／pixel、空／錯誤狀態 |
| EvalRecord／TrainRecord／Evaluator 分類與結果路徑 | 刪舊 backend confusion plotting 與專屬 tests；五個已授權便利 API 已退役；保留有正式 caller 的 accuracy、history figures、持久化與 split 讀取 | evaluator／record／deterministic oracle；真保存結果重新讀取 |
| analysis／service／state／ports 相鄰邊界 | 保留既有 Command/query、正式 serialized catalog 與 revision；不另增 owner／receipt／compatibility path | analysis 相關測試、UI ports、read-side architecture |
| Product evidence scripts | baseline、polish、human-like、visualization walkthrough、native smoke、source-diverse、MOABB journey／UI capture 均有不同正式用途，沒有已證實可刪的整支腳本；只修 canvas 完整被誤當 screenshot 完整的證據 | 真 4／20 類 widget、既有 evidence consumers／manifest gate |

測試清理保留行為對照：舊 backend plotting 三個專屬案例隨能力刪除；重複的 Evaluation
model-summary callback「integration」案例刪除，獨有 visible／capture 斷言併入原三種錯誤
component test（該兩檔 7→6 cases，實際通過）。真 service integration 另走
FIF→epoch→兩 Fold×兩 Run CPU 訓練→保存／載回→Run／Train／Test／Summary／跨 Fold→
真 publisher 失敗與恢復→reset／close，直接檢查 matrix／table／三組 bars，不偽稱
model-summary 真 worker 覆蓋，也不以合成資料聲稱科學有效性或來源多樣性。

目前沒有量測到需要新 cache／thread 的 Evaluation bottleneck。Panel 與 publisher 仍大，
但不為縮行把有共同生命週期的狀態搬成新控制層；此次新增 owner 數為零。

### 已完成 UI 迭代與當時證據（歷史記錄，不取代上方結案狀態）

- 觸控板追加修理（使用者已授權，不改排版）：原生診斷證實 angleDelta 水平事件能捲動，
  pixelDelta-only 事件在 canvas → viewport 後被忽略（bar 100→100）。尚未擷取使用者
  實體觸控板事件，不將此重現等同完整裝置驗收。
- Outcome／steps：先加入真 chart 的像素位移 RED，涵蓋水平／垂直、雙方向、細小位移、
  混合 pixel／angle 不重複捲動與邊界；在既有 canvas 處理像素位移，保留 angle 路徑。
  focused native tests／typing／review 後重開獨立 Windows 預覽並帶到前景。
  不新增手勢 owner／全域攔截／設定，不改其他 panel；Stop 為修理證據完成且預覽可操作，
  實體雙指操作仍交由使用者確認，不提前開始後端清理或重型 gates。
- 觸控板修理結果：新回歸先重現 pixel-only 不動與 mixed delta 錯誤距離；existing canvas
  現直接依 pixelDelta 更新兩軸既有 scrollbar，Qt 自行限制範圍；像素優先且不再套一次
  angleDelta，不重複反轉平台已處理的自然捲動方向。沒有 pixelDelta 時保留原 Qt 路徑。
  垂直短圖最大位移不足 120 的 fixture 改用 30px 精確距離驗證，另保留兩端 clamp 檢查。
  Windows focused 44 passed（`build/evaluation-ui-preview/touchpad-native.xml`），Ruff／
  Basedpyright 通過。獨立 reviewer 讀實作與 artifact，無 blocking finding；實體裝置事件
  送達仍未驗證。已替換舊版，重新以獨立 Windows 程序開預覽，不依附工具終端。

- 最新確認：上一版矩陣偏右上、比例不佳，UI 尚未接受。使用者同意跨 Fold 的
  `Run 1 (Summary)` 改為 `Run 1`（各次序號保留）；單一 Fold 內的多 Run 彙總仍為
  `Summary`。矩陣改回较大、置中的正方形；放不下兩張圖時提前使用既有 chart tabs。
- 已重現滾輪缺陷：真 Windows canvas 收到 wheel 後 accepted，但垂直 scrollbar 留在
  0；同事件送 scroll viewport 則前進到 200。Matplotlib 消耗事件，未交給外層捲動區。
  修理只讓 Evaluation chart canvas 將捲動交回 Qt，不改全產品／資料或新增捲動 owner。
- 本次步驟：wheel 真事件 RED（上下／水平／邊界）與矩陣 square／center／大小回歸 →
  既有 canvas、panel layout 與顯示字串最小修理 → 相鄰 UI tests／截圖 → 開新 Windows
  隔離預覽。原生可操作預覽是本次終點，UI 確認前不宣稱 Evaluation 模組結案。

- 使用者已確認修理長 class label 擠壓、下方資料列推擠圖表；Run 彙總名稱指定為
  `Summary`，單一 completed Run 不顯示、至少兩個 completed Run 才提供。追加檢查
  Fold／Run／Split 下拉選單是否有 Saliency 同類白邊，確認缺陷才修。
- 證據：metrics table 以最多 12 列同時設定 min/max height；圖中文字主要依畫布寬度
  而非 label 長度排版；on_model_changed 只要有任一完成 Run 即加入舊 Summary 文案。
  白邊尚需 Windows pixel／原生檢查，不以相同元件推定已重現。
- Outcome：長名稱仍可讀、多列在表格內捲動而不擠壓主圖、單次無冗餘彙總、選單深色
  背景連續；保留 run identity、跨 fold 彙總、split、計算與 publication 語意。
- Scope：Evaluation 既有 UI 元件與直接測試；優先重用現有 popup 呈現方式，不新增
  backend owner，不改其他模組樣式、不展開 Evaluation 後端清理、不動 main 或設定。
- Steps：真 widget／繪圖與 native popup 建立 RED → 最小 coherent UI 修理 → focused
  regression／geometry／pixels／lint → 開 Windows 隔離示例預覽並確認有回應。
- Validation：短／長 class 名、多列／少列、縮窄再放寬；單次／多次／未完成 Run、選取
  與 split 保留、popup 頂底背景及清單末列／鍵盤可達。模型與昂貴計算可在預覽隔離。
- Stop：使用者可直接操作本次 changed-surface 原生預覽；等待 UI 設計確認後才進行
  內部清理與重型／正式 gates。Saliency 已結案 dirty slices 保留，不重做或發布。
- 已重現：Windows 三個 popup 的頂／底白邊（2／50 項），以及 metrics 3→40 列時
  plot group 高度 467→248；先 RED 再修。popup 只改獨立 frame 背景，無全域樣式改動。
  長清單初次末列失敗是 fixture 在 native window exposure 前開 popup，修為等待真實
  exposure，保留像素與末列／鍵盤斷言，不增加 production 捲動 workaround。
- Summary 已使用至少兩個完成 Run 的条件，保留原 identity／split／跨 fold 路徑；舊
  summary freshness／失敗案例改用兩個完成 Run 作 fixture，沒有刪除這些保護。
- 長標籤第一版雖通過 non-overlap，但 native screenshot 四類別仍需過量捲動，因此
  不作交付；正調整現有 canvas 的文字量測／換行／軸間距並保留很多類別的局部捲動。
  表格取消依列數強制增高，保留短表上限與長 class tooltip；不碰 backend 數值。
- 上一版 UI 候選（未接受）：普通四類長名稱在 460×350 圖區完整可見且無捲動；matrix 完整換行／
  X 軸直排、寬高獨立分配，很多類別才局部捲動，不縮為 7／8pt。長→短→空資料會
  釋放多餘捲動範圍；現有 canvas 共用，無新 owner／模組／類別。
- 上一版直接證據：Windows 五個相關 UI test files 共 101 passed，四個 production files
  Basedpyright 零診斷、Ruff 通過。`build/evaluation-ui-preview/focused-native.xml`；
  獨立 reviewer 檢查 Summary identity、table sizing、canvas lifecycle／resize 及原生
  圖，無 blocking finding；這不是 Evaluation 後端結案審查。
- 已開 Windows 原生預覽：`build/evaluation-ui-preview/preview.py`，標示合成資料，
  使用真 panel／chart／controls 與隔離 runtime；可切短名／長名／20 類及一／兩次完成
  Run，不使用研究模型或使用者資料，不改 main。Qt timer 已確認 window visible、
  platform windows、五列表格、Run 1／Run 2／Summary，截圖已人工視覺檢查。
- 本次修正結果：跨 Fold 顯示 `Run 1`／`Run 2`，同 Fold 多完成 Run 的 `Summary`
  不變。矩陣恢復置中正方形，保留完整水平換行名稱；plots／details 分配調為 3:1，
  兩圖不能等寬容納時使用既有頁籤。滾輪事件只從 Evaluation canvas 轉送至既有
  QScrollArea viewport，保留方向、delta、phase、device 與事件接受狀態。
- 獨立覆核另重現 1500／1600 中間寬度仍溢出：原門檻將兩張圖所需寬度相加，
  實際並排卻等寬分配。補原生 RED 後改為兩倍最大需求，加間距；回歸涵蓋窄／中／寬
  來回切換、selection 保留、真正上下／水平 wheel 與捲動終點，不只直接操作 scrollbar。
- 本次直接證據：Windows 五個 UI test files 107 passed，artifact
  `build/evaluation-ui-preview/revision-native.xml`；三個本次 production files Basedpyright
  零診斷，Ruff／diff check 通過。跨 Fold 名稱另有 backend／UI／capture script focused
  33 passed（與 UI 群組重疊，不加總）。已檢視原生四長名稱截圖，無多餘捲動、圖方正置中。
- 獨立 reviewer 以小型 Windows 診斷覆驗 1280／1400／1500／1600 頁籤與 1800 並排皆無
  水平溢出，原 finding 已關閉；本次 wheel／geometry／layout 無新 blocker，不代表後端結案。
- 新版原生預覽已開啟，Qt timer 確認 visible／windows／五列表格及三個 Run 選項。
- Next／Stop：等待使用者確認本次修正版 Windows 預覽；尚未展開 Evaluation 後端清理、正式重型 gates
  或 PR。已接受的 Saliency 不重測，不把預覽視為完整 workflow 手測。

## Current — Saliency 清理已結案，尚未發布

2026-09-23 使用者確認改由 Saliency 往前討論，Import 最後；先建立隔離工作區與保存
計畫，不修改正在手測的 main。工作區 `XBrainLab-product-workflow`，分支
`refactor/product-workflow`，起點為已接受的 main `94328196`（PR #146）。
本節保留先前取代「Import Wizard 優先」的決策；最新 active scope 以本文件頂部為準。

目前沒有尚未完成的 Saliency 施工切片。使用者已接受 UI；內部清理與最後三項缺口
已完成，非實作者已按下列六項準則獨立覆核，未發現新的 blocking finding。
這是本機 `scope-complete`，不是 `handoff-ready`：來源仍為 `64bd5fdc` 加本輪 dirty diff，
尚未獲得 commit／push／PR／merge 授權，也沒有對應 clean head 的 CI。
Saliency 先保留未發布成果；Evaluation 最新授權以本文件頂部 active slice 為準。
以下保留的施工證據不是新的派工，不因 context recovery 重做已完成切片。

### 已完成並接受的 UI 修理 — Saliency 縮窄時功能列文字擠壓

- 使用者追加回報：調整視窗寬度時 Saliency 功能列文字疊在一起，明確要求先修這項 UI，
  再繼續內部清理與獨立審核。既有其他 UI 接受保留，不重新整套手測。
- 初步線索：panel 的 responsive grid 以固定 700／760 門檻及 ctrl_bar／panel 寬度估算
  選擇 layout；需用真 Qt geometry 確認縮窄／再放寬是否採到 stale width、是否低估文字與
  controls 實際需要的寬度。這是待驗原因，不能只改門檻猜測修好。
- Outcome：支援視窗寬度與 Windows DPI 下標籤／選擇框／checkbox 不重疊或被擠掉，
  窄寬來回調整能正確換行；保留功能、選取、busy／cancel 行為與既有文案。
- Scope：只修 Visualization 功能列及直接受影響的 layout／geometry tests／原生預覽；
  不新增 backend owner、不改 EEG／計算語意、不同步做後端清理。若發現不同 UI 設計取捨另確認。
- Steps：真實 widget 縮放重現並補 RED → 既有 layout 內最小修理 → 同測試與相鄰控制列回歸
  → Windows native 縮放預覽，明示示例資料、確認有回應後讓使用者看。
- Validation：連續縮窄／放寬、長 method／class、Absolute 顯示／隱藏、選取不丟失、
  控制列 containment／文字尺寸／不重疊；檢查 100／125／150% 的直接 changed surface。
  此設計確認前不重跑全套 compute／跨平台重型 gates。
- Stop：本 UI defect 的直接證據收齊並展示原生畫面；確認修理後再恢復下方內部三項未結工作。
- 已重現與修理：嵌入 panel 在 1180 寬（bar 880）仍採 wide，Run label 與 Fold combo
  的 QRect 實際相交；側欄隱藏時亦重現。先建立 RED，再改為聽取 bar 自己的 Resize／Show，
  由既有 QGridLayout 的實際 minimumSize 選擇可容納的一／二／三行。避免寬版 minimum
  size 反過來鎖死 window 縮窄；保留窄版最小寬度，修正 wide 未還原 class combo 寬度。
  不縮字、不隱藏功能、不新增佈局 owner，不改計算或資料流程。
- 直接驗證：Windows panel suite 123 passed，125／150% 各 4 個連續 resize regression
  passed；包含 embedded／top-level、側欄顯示／隱藏、長 method／class、真選取保留、
  Spectrogram 的 Absolute 隱藏／還原、文字尺寸／containment／無重疊。Ruff 通過。
  150% 初次 top-level 測試因要求超出螢幕的寬度失敗，改以螢幕可用寬度測 top-level，
  embedded 仍保留完整寬度範圍；未放寬文字／重疊斷言。另修測試 parent/child teardown。
- 原生預覽：build/saliency-ui-preview/resize_preview.py 使用真 panel controls 與隔離示例
  選項，renderer／計算不執行；Windows 三倍率截圖位於同目錄 resize-*。已檢視窄／中寬
  圖，預覽不是正式 workflow handoff。使用者已明確回覆「沒問題了開始修後端吧」，
  本 UI 修理已接受；不重測其餘已接受 UI。單檔 Basedpyright 零診斷。

### 已完成 — 內部責任收斂與取消證據

- 問題與 outcome：處理獨立 reviewer 提出的三項缺口；在已接受 UI baseline 上消除
  3D 重複 lifecycle presentation，補真 3D 取消／重試，量測昂貴 evaluator 的取消耗時。
- 切片 A：先用正式 panel 的 unavailable status 與 pending runtime probe 回歸保護可見
  行為，再刪 3D 的 status field／setter／重複提示與 test-only 入口。Panel 仍是呈現 owner，
  backend publication／native commit／generation fences 全部保留，不新增 owner。
- 切片 B：沿用既有真 GUI／Assistant fixture 與 EEGNet／Captum，在 Windows interactive
  3D 驗 compute → 重算 → prepare 中取消 → late callback → 再算成功及關閉。CPU attribution
  與互動 VTK 真實執行，僅用可釋放同步 barrier 定位取消時點；不以 stub scene 取代證據。
- 切片 C：先量測代表性 Gradient／SmoothGrad workload 的取消請求到 worker 結束，區分
  UI 接受、拒絕 publication 與實體釋放；不以預設性能目標新增 cache／worker。若需修改
  合作式取消粒度，先記錄量測、直接 baseline／失敗回歸、caller、同值與原子性保護再施工；
  可見語意或新架構取捨另提決策。
- 驗證：各切片 focused baseline／回歸，資料／非同步獨立覆核，再整合六項結案準則。
  保留既有 dirty slices；限定檔案可分別回退，不以全 worktree reset 回復。PR／merge 尚未授權。
- Stop：三項逐一有實際結論與直接證據，再請未參與實作的 reviewer 判斷模組結案；
  不因一批測試綠燈就宣稱全模組乾淨，也不以未知項自行轉 follow-up 結案。
- 取消 baseline：Windows CPU／Torch 4 threads，固定 seed 未訓練 EEGNet，128×32×256
  合成輸入、batch 16、SmoothGrad 預設 5 noise samples。首個 forward 後發取消標記，
  evaluator 仍跑完全部 8 batches；Gradient 8 forwards／83–89 ms，SmoothGrad 16 forwards／
  455–468 ms（各 3 次）。這是 evaluator tail，不是 GUI end-to-end 或所有硬體延遲。
  evidence：build/dev-artifacts/saliency-validation/cancellation-before.json。
- 最小修理決定：唯一 production caller TrainingPlanHolder 已持有 should_cancel，直接
  傳入 evaluator，在進入工作、每個 batch 與各 attribution 方法間檢查；沿用既有
  StaleSaliencyUpdateError 及 manager 的取消／拒絕發布／cleanup，不新增 owner 或 thread。
  要求是取消後不再啟動下一個計算單位；已進行中的單次 Torch/Captum 呼叫仍合作式完成，
  不承諾硬體搶占或固定毫秒上限。先 RED 驗 pre-cancel／forward 中取消／noise 中取消、
  false callback 下同 seed 同結果，再修改 evaluator + holder 兩檔及直接測試。
- 最後結果：A 刪除 3D 重複 status／setter／提示與 class coverage map，八個真 panel／
  late probe baseline 在刪除前後通過；Panel 是唯一 lifecycle 呈現 owner。B 真 Windows
  GUI／Assistant → EEGNet／Captum → 3D 取消／晚到結果拒絕／重試／native cleanup 六案
  全通過，檢查互動 QtInteractor、actors、finite scalars 及有空間差異的 framebuffer。
  C 取消訊號已傳入 evaluator；真 manager 中途取消驗證後續計算不啟動、舊 record 保留、
  retry 成功，同 seed 五種方法的值不變。未新增 owner、thread、state 或 exception。
- 同一測量條件修理後首個 forward 後即退出，Gradient／SmoothGrad 各為 1 forward；
  evaluator tail 0.038–0.101 ms。這只說明未再執行剩餘批次，不是 GUI／CUDA 延遲保證。
  單次已在執行的 Torch／Captum 仍完成後才觀察取消。前後 probe JSON 保留在同一 evidence 目錄。
- 最後覆核：原獨立 reviewer 直接讀 diff／測試並解析 artifacts，確認原三項 findings
  可關閉、六項準則於 Saliency 範圍達成；responsive 修理另由未參與該修理的 reviewer
  檢查 layout／reentry／selection，未找到 blocker。不宣称整個 repo 或永久零缺陷。
- 最後本機證據：`final-panel-native.xml` 256 passed；`cancellation-regression.xml`
  34 passed；`final-source-diverse.json` 4 passed。均位於
  `build/dev-artifacts/saliency-validation/`。`build/dev-artifacts/` 的
  `saliency-final-native-entrypoints.xml` 6 passed、`saliency-final-offscreen-entrypoints.xml`
  4 passed／2 explicit native-only skips；不把重疊群組加總。63 個修改 Python 檔 Ruff
  check／format 通過，全專案 Basedpyright 零診斷；未調整 diagnostic baseline。
  真 3D native 案例不在一般 offscreen CI 執行，後續影響該路徑仍須補 native evidence。

### 已同意的逐模組結案準則與順序

2026-09-23 使用者同意依下列六項準則逐模組討論、清理；並明確確認**以下順序適用
每一個模組，不只是 Saliency：討論並確認 UI 行為 → 清理後端、測試與相關 scripts →
獨立 reviewer 結案 → 下一個模組**。本輪從 Saliency 開始，後續 Evaluation、Training／
Data Split、Preprocess／Epoch、Import 同樣遵循，不在 UI 未確認時提前展開其後端清理。
這取代「限定切片回歸通過即可
視為模組清理完成」的判斷；不以「重大歷史包袱」等無可核對的形容詞作為退出條件。

1. 無已確認無用途的程式：追查正式 caller、動態註冊、設定、scripts 與文件後，刪除
   無用途 API、分支、狀態、包裝及專屬測試；只有測試呼叫不是保留理由。
2. 同一政策不多處獨立實作：同一 workflow 狀態／決策有明確權威；多層防護須指出
   各自保護的不同邊界，不能把必要的 freshness／integrity 檢查當成重複刪除。
3. 每份狀態、cache、轉接都有用途：能指出產生者、消費者、失效時機，以及不能直接
   使用既有資料的原因；未查清的項目不可標為完成。
4. 處理責任混雜：若修改同一規則需要同步修改多份判斷／狀態，就收斂責任；不按
   檔案行數強迫拆分，也不以搬檔／新增代理層冒充改善。
5. 測試保護正式行為：重要成功、失敗、取消、重試、stale result、關閉路徑有適用
   observable evidence；只塞內部狀態或 mock 成功不代表完整流程已驗。先有替代證據
   再刪維持舊入口的測試，保留必要外部依賴隔離。
6. 相關 scripts 逐支去留：指出現行用途、入口、與其他腳本的差異；一次性任務已結束、
   用途退役或功能重複時，連同專屬設定／測試／文件清理，不移到 legacy。

節奏：先逐項討論 UI 操作與預期狀態，用正式 Windows 流程確認正常及異常行為；
必要的可見修改先取得確認，不能把已接受的 warning 外觀當作整個 Saliency 行為驗收。
UI 行為確認後才追加後端內部清理，保持已確認行為並補 focused regression；若 UI
驗證重現 backend defect，先定位、明示直接修理範圍，不以此提前展開整輪後端重構。
既有 dirty 修改保留，不撤回。使用者已再次明確確認 Saliency UI 行為已確認過，
該模組直接接續後端／內部清理，不重開 UI 討論或要求重測；其餘模組仍先確認 UI。
後續若影響已接受行為，補受影響部分的驗證，不預設整套重測。模組結案由獨立 reviewer 核對
六項準則；範圍內已確認要修的項目須關閉，未查清不得自行轉為下一輪 follow-up。
保留項要有可核對理由，需要行為／效能取捨時由使用者確認。不承諾永遠沒有新 bug。
模組討論／UI 行為確認不等於每塊都要求正式手測或 merge；整合版本才集中驗收，
仍依既有 exact-source／CI gate 與授權辦理，不新增第二套清理平台或任意數字門檻。

Saliency 已按這些準則完成本輪結案；上述三項已修理並獨立覆核，不再列為未結項。
模組範圍是下方核心 production、直接測試與四支 scripts，不外推為全專案清理完成。

## Completed record — 研究線最新工程與歷史量測

2026-09-23 核准的封存包／Linux evaluator 工程範圍已 scope-complete；
固定20題、搬移後離線報告／原候選判分核對、歷史d0不變及三方獨立覆核完成。
實際來源、產物與限制由 [Current](../current.md#linux-evaluator-2026-09-23)
擁有；執行及研究契約由[研究規格](../validation/thesis_protocol.md)擁有。
本輪未PR／push／merge；不自動開始新候選、完整DEV、正式VALID或TEST。

### 產品 Saliency 施工界線補記（歷史，非當前整合授權）
- 問題與證據：上一輪 Import 修理已合併，但本文件仍指向已刪除的 worktree 及待 PR
  狀態；使用者現在要求逐站討論 UI／操作，並審查是否存在無用途或重複腳本。
  這是新的審查方向，不代表已確認 Saliency 有新 defect 或腳本可直接刪除。
- Outcome：Saliency 每塊 production／tests／scripts 都追清實際入口、責任與用途，
  刪除已確認死碼、無用腳本與專屬測試，收斂重複政策／轉接／狀態；必要保留項有理由。
  三項 UI 修整與測試綠燈只是基線，不代表深度清理完成；逐塊施工後再整合驗收。
- 順序：Saliency／Visualization → 產品 Evaluation 結果頁 → Training／Data Split →
  Preprocess／Epoch → Import Wizard。後續各站目前是候選，不同時展開全部重構。
- 目前授權：使用者提供 Windows 截圖並確認三項修整：Assistant 與 3D 同時使用時的
  VRAM 提醒可勾選 Do not ask again；Fold 不再包含可選的 Select a fold；下拉選單
  上下白邊修正。保留整體 UI 操作。另審查 Saliency 後端、測試、架構及相關腳本。
  未確認的計算語意／流程取捨只回報，不直接實作；其他 panel 仍未授權施工。
- 最新澄清：使用者要求深入查冗餘設計、死碼、無用 scripts，從 Saliency 一塊塊修好。
  授權行為保持的內部刪除／收斂與直接測試修理；保留已接受外觀、方法／資料語意、
  Assistant 工具契約、取消／一致性保護。不以額外 UI／政策改動替代清理。
- Non-goals：不更換 main 手測版本、不改另一條 Assistant Evaluation 研究線的
  題庫／runner／scorer／模型／prompt／RAG／封存，不升級或複製 virtual environment、
  不下載或搬資料、不動任何既有 settings.json，不自動發布 PR／merge。
- 假設：後續可重用現有 Windows Python 與資料；本次不建立新環境；設計接受後執行必要計算驗證。
  新 worktree 不帶入 main 的本機設定；需要原生預覽時另確認啟動路徑與測試資料。

### 研究線最近完成（原來源證據）

報告閱讀介面與產生器可讀性整理已完成；實際能力及證據邊界見
[Current](../current.md#assistant-research-baseline)。這不是其餘 evaluator 政策修理、
資料夾遷移或人類設計驗收完成；外部產出格式計畫的未實作項保持待辦。

`review_status` 已改在正式非 TEST 題庫來源移除，runner 恢復原樣複製；
正式來源與驗證見 [Current](../current.md#assistant-research-baseline)。

2026-09-22 核准的完整 DEV initial 已 scope-complete：1,320 有效量測、獨立判分／capture
核對、報告重建及實際 queue 接續已通過。結果與限制集中於
[Current](../current.md#assistant-research-baseline)，執行契約由
[研究規格](../validation/thesis_protocol.md) 擁有，不在本 plan 重複保存數值。
本輪沒有 PR／push／merge，也不等於產品 native GUI 或正式 TEST 驗收。

上述已完成工程範圍之外，下方 DEV 調優候選仍未授權；不自動執行第二套、VALID／TEST，
不重跑已完成的起始基準或歷史 Pilot。以下保留歷史及候選，不作新的施工授權。

## Completed record — 產品 Saliency 清理證據補記

以下保留整合前產品線的施工狀態與證據，當時的dirty／待發布描述不代表共同基線目前狀態。
- 文件準備已完成；下方清理與本機整合證據屬本輪 dirty candidate，不使用 PR #146
  或清理前的 UI 綠燈代替本輪驗證。
- 後續施工：focused tests、相鄰流程與適用 source-diverse gates；可見改動需同來源
  畫面／walkthrough 與 Windows native 確認。沿用 validation contract，不另建 gate 系統。
- Next：Saliency 內部工作已完成，待發布授權；沒有 pending 施工或 reviewer。
  不要求使用者重測全部已接受 UI。發布後仍依 exact-head CI／適用 gate 決定正式交付；
  其他模組尚未因此取得 UI 接受或施工結案。
- Stop：Saliency 清單逐塊有實際讀取與去留結論，確認的冗餘完成刪除／收斂並有直接
  行為驗證與獨立覆核，最後整合 review 才交付。未知項不得算完成；PR／merge 另需授權。
  本輪審查結論須區分已檢查範圍、實際 findings 與未證明的科學有效性。

### 深度清理清單與施工界線

| 區塊 | 已做的限定清理 | 模組結案狀態 |
| --- | --- | --- |
| Settings／參數與方法 | 收斂 store mapping、參數重算、dialog alias；保留 command admission 與 artifact decoder 的不同責任 | 已獨立覆核結案 |
| Compute／取消／publication | 移除 test-only prepare／defer／holder setter；保留正式批次發布、ack／retry、commit fences；evaluator 採用既有取消訊號 | 已覆核；保留單次 Torch／Captum 合作式取消界線 |
| 結果與 provenance／快取 | 刪重複 copy／不可達 fallback；保留模型與資料 provenance、artifact 語意 integrity、filesystem transport 三種不同保護 | 已獨立覆核結案 |
| 四視圖與 controls | renderer 只收 detached DTO；刪隱藏 selector、同步 scene fallback、死 helper、重複 3D status；保留 native resource ownership | 已獨立覆核結案，responsive UI 已接受 |
| 專用測試與 fixture | 先遷移正式入口與真 publisher 再刪退休入口測試；補 artifact／alias／shared selector／真 3D 取消重試／數值與中途取消 | 已覆核；native-only 案例需原生環境執行 |
| 相關 scripts／gate／docs | 四支直接腳本均有 gate／人工入口；保留整支，刪內部重複並修兩個驗證缺口；不是全 repo scripts 審查 | 已核對去留並獨立覆核結案 |

- 每塊先列具體檔案、caller、deletion candidates、owners before/after 與 focused baseline；
  不新增通用盤點系統、legacy 目錄、第二套 owner 或純搬檔重構。小切片可逐一回退。
- 既有 source-diverse／Windows 真 compute 與 render 證據是施工前基線；變更後先驗直接
  影響，整合完成再取得新 source 的必要 gates。未改模組不反覆跑同等重型驗證。

#### 已核對的第一批施工切片

- Backend：Evaluator 已算好的 effective noise parameters 重用於 batch，方法名稱／store
  mapping 收回既有輕量 saliency_methods；EvalRecord 的 decoder 已強制 dict，刪 load 端
  不可達 malformed-store 分支及 getter／setter 外重複 metadata copy。保留 decode、
  context／integrity 檢查與持久化隔離；owner 不增，先過原數值／tamper baseline 再改。
- Views／Settings：移除無 production caller 的 PlotType/get_saliency 舊便利 API 與
  專屬無效測試；Settings 移除重複 alias／重複初始化。3D 永遠隱藏的 class_combo
  退役，保留 shared panel selector 的 canonical key 與 first-available／blocked 語意；
  改成只保存選定 key，不新增選擇 owner。保留公開 SaliencyRenderData／worker 保護。
- Panel：刪無 caller 的 _has_service_saliency_summary；cache 的 presence 與 lookup
  改用一次同一查詢，重用既有 publication identity predicate；各 renderer 保持不同
  update_plot 參數，但共同 publication／terminal 綁定只保留一份。保留 queued worker
  finished、stale、operation／commit fences，不在這個切片移除 compute-attempt ledger。
- Scripts／tests：walkthrough validator 的 optional final_state 可略過終態檢查，先
  RED 重現缺失／空值後改 fail closed；runtime claim 不再硬寫 XCB。reviewer capture
  的 29+5 歷史 inventory 合成同一份 34 項，保留名稱／順序；polish 同檔 PNG 轉換
  重用既有函式。刪被目錄級 guard 覆蓋的單檔 guard／舊拼字 assertions，不削弱 gate。
- Rollback：上述切片各由限定檔案 diff 回復；不碰既有 UI acceptance 修改或其他工作區。
  先 focused baseline，修改後同組回歸，hidden selector 與 publication 變更獨立覆核。
- 第二批限定候選已查 caller：render 的單份 prepare 只有 service 空轉接、stress fixture
  與舊測試，正式 UI port 使用 prepare_variants；notification.defer 只有測試，正式流程
  使用 reserve／publish_reserved／release。刪前將既有測試移至真實入口，保留取消、
  commit、queue handoff／retry／ack 保護；不更動 Command／query DTO 或 Assistant 契約。
  Sidebar.update_info 是空方法，刪除自身與 panel 的空呼叫；實際資訊仍由 InfoPanelService 更新。
  3D checkbox callback 包裝未被使用，下一片改為既有 scene 上兩個布林值；constructor
  的同步 engine／自行建立 plotter fallback 只供舊測試，改由現有背景準備與 QtInteractor
  入口測試。prepare_engine 本身仍由 worker 使用，必須保留。以上不增加 owner。
- Renderer 邊界：所有實際繪圖 caller 已使用 SaliencyRenderData；Visualizer 與 3D engine
  的 EvalRecord／Epochs 第二入口只留在測試。遷移到同一 detached DTO，將 context drift、
  legacy missing、持久化 roundtrip 的 oracle 放回真 SaliencyRenderPublisher → renderer
  路徑，再刪 renderer 內重複 record mapping／context fallback。不改 publisher、artifact
  admission 或數值算法；先取得遷移後 passing baseline，沒有替代證據的案例不刪。
- Holder.set_saliency_params 只有七個 unit 與兩個 integration fixture 呼叫；正式 manager
  使用 prepare_saliency_update + 整批 publish。將九個 caller 改真 preparation/publication
  流程後刪此 convenience，不刪 Study／TrainingManager 的正式設定入口，不改批次原子性。
- 整合檢查：全專案 Basedpyright（不同於單檔分析）指出 Captum kwargs 失去舊 helper 的
  Any seam；為已經 canonical normalizer 驗證過的 effective_parameters 補同等型別註記，
  不新增轉換／驗證、不改任何計算值，重跑完整 gate，不調整 diagnostic baseline。
- 實際 stress 驗證發現 runner 不理會 QT_QPA_PLATFORM=windows，固定改為 offscreen，
  因此 --require-interactive-3d 在 Windows 永遠失敗。先 RED 驗 explicit Windows 選擇，
  再只開放 Windows 的既有環境變數 opt-in；預設 CI/offscreen、macOS 與原 resource gates
  保持。原生重跑明確設定 PYVISTA_OFF_SCREEN=false；不假冒 offscreen 為 desktop。

### 本輪深度清理結果與限制

- 完整讀取的核心 production 範圍為 30 檔：panel 1 檔；views／Settings／renderer 17 檔；
  application saliency services、方法定義、Evaluator、provenance／integrity、EvalRecord／
  artifact store 12 檔。另讀 warning 元件、被刪 CheckboxObj 與共享 owner 的相關段落；
  不把後者算成全檔審查。直接腳本四支；測試按修改責任追到真行為，非全 repo 逐檔審查。
- 最終 production 27 檔 +288/-1055，淨減 767 行；scripts +29/-44，淨減 15 行；
  tests +1619/-770，淨增 849 行（補 observable evidence，不用淨減測試當品質指標）。
  未增加 owner、state machine、receipt 或
  compatibility path。移除 ui/core/utils.py 及其專屬 test；其餘為原 owner 內收斂，
  沒有刪使用者資料、模型、環境或研究線檔案。腳本沒有可整支刪除項。
- 保留 compute-attempt ledger：同一 publication 的 dispatch／confirmation 期間需要擋
  重複提交，failure／cancel／reset 會釋放；不是第二套 backend operation state。
  保留 geometry／STFT 等 bounded cache 及 native async cleanup，未以縮行數移除它們。
- 覆核：backend／publication 與 UI／native lifecycle 由非實作者交叉審查；主 agent
  檢查實際 diff 與整合證據。DTO 遷移保留 context drift／legacy missing／持久化 roundtrip、
  一基底事件碼與字串 class key、VarGrad absolute、float64 cancellation-sensitive 數值 oracle。
- 清理後本機證據：backend renderer 161；Windows UI／Settings／panel／views 364；
  真 GUI／Assistant compute、SmoothGrad 重算、取消與 native lifecycle 9；source-diverse 4
  通過。這些是不同執行組、部分有重疊，不加總成唯一案例或全專案覆蓋率。
  Holder 正式路徑與六模型 family workflow 34、scripts stress 62 通過；完整 Basedpyright
  零診斷、architecture compliance 通過。POSIX-only filesystem 案例未由 Windows 取代。
- Windows 真四視圖 capture：compute completed、互動 3D framebuffer 有 actor、無未捕捉
  例外、clean shutdown。原生 stress 2 輪 warmup +12 輪量測，14 次 3D close 成功，
  零晚到回呼／active Qt worker，resource 與 memory contracts 通過；不是無 memory leak
  的普遍證明。Windows 100/125/150% app-polish matrix 通過。
- 證據位於 build/dev-artifacts/saliency-validation/ 的 deep-*、renderer-detached.xml；
  綁定 64bd5fdc 加清理 dirty source，最後文件收斂與 test formatting 另記於 diff，
  不是未來 clean PR head 的同版本 CI。初次完整 typing 與 native stress 的失敗已修正並
  重跑，不掩蓋初次結果。source-diverse 重用 E 槽，沒有下載／複製環境。
- 限制：大型 panel／base view／3D view 仍有整合責任，不因大小判定必拆；取消粒度與
  測量已完成，界線見上方結論。相關 scripts 之外的全 repo 腳本尚未
  審查，隨後續模組逐支處理，不冒充本輪已清完。Attribution 科學有效性、所有模型／
  資料與逐 bit 重現不是本輪工程測試的保證。

### 已接受 UI 與清理前基線（以下舊數字不是深度清理後證據）

- Fold 的提示項目前在 init／refresh／clear 三處作為普通選項加入；改為空清單的
  placeholder，無資料時不可選；有結果只列真實 Fold／Fold Set，保留 selection identity。
- VRAMConflictChecker 的提醒是 UI advisory，不是 backend resource admission 或 Assistant
  工具授權。沿用 ModalAlertDialog presentation 與 application_settings 保存個別提醒偏好；
  只有使用者勾選並按 OK 才保存，關閉／Escape 不默認同意。跨重啟記住選擇，不讀寫 root
  settings.json，不略過 OOM／資源 preflight／工具確認。預覽與測試使用隔離 config root。
- 2026-09-23 使用者追加確認：Do not ask again 移至 dialog 最下方左側，與右側 OK
  同一列；只調整 opt-out dialog 排版，未使用 opt-out 的既有 modal 位置保持不變。
  先以真 Qt geometry 驗證同列、不重疊與按鈕可達，再開原生警示框；仍不跑重型測試。
- 最新文案確認取代舊提醒：標題 GPU Memory Usage，正文說明 local Assistant 與 3D
  同用可能增加 GPU memory usage，若變慢可分開使用；這不是已偵測不足。
  勾選改為 Don’t show this again。使用者不接受上一版外觀，已授權再做一版：縮短正文、
  統一標題／正文／勾選框左緣、調整標題與操作列間距，保留黃色圖示；其他 modal 不變。
  最新確認：正文合為單一段落，移除句間強制換行，依視窗寬度自然折行；其他排版不變。
  本次只驗直接 modal／VRAM 小測試和 Windows 原生警示預覽，未接受設計前不跑重型 gate。
  新版對齊檢查先重現左緣 18／52 不一致，修正後直接 modal／VRAM 39 cases 在 Windows
  通過；已開真實警示框、確認有回應並檢視截圖；使用者已接受單段正文設計。
- 白邊先用 Windows popup 擷取確認來源；只修 Visualization 的受影響選單，不任意
  改全產品樣式。保留鍵盤、滑鼠選擇和長清單捲動。
- Owner before/after：backend command／operation／publication owners 不變；既有 VRAM
  checker 保有提醒政策，modal 只負責呈現，Qt settings 保存使用者偏好。不新增 owner、
  state machine、receipt 或 compatibility path；production 3 檔 +91/-23，淨增 68 LOC。
- 驗證：真 Qt dialog 勾選／未勾選／取消及 fresh checker 持久化；Fold empty／多項／刷新
  保留及跨 fold set 選取；native 展開 Fold／Run／Method／Class 的像素及鍵盤操作，
  另跑直接相關 lifecycle／render regression。測試隔離昂貴推論／GPU，不啟動研究模型。
- 審查：沿資料→completed run→saliency method／class→artifact→render 追蹤真入口與
  取消／stale／整批發布；核對測試 oracle、mock 邊界及相關腳本用途。不將通過測試數量
  或 3D 頭部圖宣稱為 attribution 科學有效性或腦內定位。
- 整合回歸發現兩個舊測試仍把空 Fold 視為 enabled：補空／有結果情境，保留 busy
  還原與 summary query 不阻塞 Qt 的原始保護；不為舊 assertion 改回可選空提示。
  完整型別 gate 另發現 combo.view()/window() 的 Qt stub 可為 None；補呈現層窄 guard，
  保持正常 popup 外觀不變，再驗型別與直接 popup 回歸；不放寬 analyzer baseline。
- 清理前 UI 整合結果：UI 396、backend 數值／artifact／publication 315、Windows 真 GUI／Assistant
  compute／SmoothGrad 重算／取消／render lifecycle 9、canonical source-diverse 4 通過；
  source-diverse 重用 E 槽資料，不下載。兩項舊空 Fold assertion 改成空／有結果案例，
  獨立覆核確認沒有削弱 busy／Qt 回應性保護；沒有刪除測試或 backend 功能。
- 原生證據：四視圖含互動 3D、clean shutdown 通過；Windows 100/125/150% 完整
  app-polish matrix 通過；變更表面 modal／popup 三倍率各 47 通過。capture 初次因
  WSL worktree Git 路徑及共用環境 namespace 來源檢查失敗，改用行程限定 Git 路徑／
  import path 後補跑成功，保留 failed artifacts；未改共用環境、Git metadata 或 gate。
  以上 capture 綁定 guard 修理前的 source fingerprint，不是最終 commit 的交付證據。
  最後 nullable guard 後 Windows popup／Fold 54、完整 Basedpyright 零診斷及 changed-file
  Ruff 通過。完整 regression／Linux visual／跨平台 CI 留給獲授權後的同一 PR head。
- 證據位置：`build/dev-artifacts/saliency-validation/`，早期 JUnit 在
  `build/saliency-validation/`。本機來源仍為 `64bd5fdc` 加本 slice dirty diff；沒有
  commit／push／開 PR／merge。main 的 protected settings.json 雜湊核對未變。
- 已驗：Windows 原生四種 popup 白邊先全部重現；僅改 list style／combo palette 不足，
  最後針對 popup 獨立 window 補背景。Fold 改動的 busy refresh／empty restore 風險由
  獨立覆核抓到並修正，保留既有 operation fence，無新增 owner。直接 Fold／popup
  22 cases 在 Windows 通過（含 50-item 清單最後列可達與鍵盤選取）；VRAM／modal
  38 cases 通過，包含勾選、OK、Escape、close、INI 及新 process 讀回。不是 full suite。
- 預覽：`build/saliency-ui-preview/preview.py` 為忽略於 Git 的一次性 native preview，
  重用真實產品 controls 與既有 detached fixture，示例 Fold／class，計算與 render 隔離；
  Qt 設定寫入該預覽的獨立 config root，不動使用者設定。截圖與預覽不是完整 GUI handoff。
- 清理前初步唯讀審查：compute／artifact／render 的整批發布、取消不覆寫及 stale 拒絕有
  實際 owner／測試；亦有真 MNE／EEGNet／Captum 與解析梯度 oracle，非全靠 mock。
  未確認新 backend blocker，未逐行審完全套大型 tests，也未重跑數值／跨平台 gates。
  三項後續候選：取消只在 run 前後檢查，延遲尚未量測；核心 panel orchestration 仍大；
  label-render 固定等待與 GUI compute 矩陣未納 3D 的 evidence 邊界可再改善。不在本輪改政策。
- 相關腳本：visualization render walkthrough、native render stress、reviewer captures、
  polish captures／DPI runner 均查到 gate／CI／其他 capture caller，暫無可整支刪除項。
  部分 Settings fixture 重複不等於整支無用途；全 repo 腳本清單仍未完成。
- 解讀限制：一個 completed run 缺完整 Test／Validation class coverage 會讓本批 Saliency
  不發布，舊結果保留。Attribution 對 true class output；3D 是 electrode 值插值，不是
  腦內 source localization。方法科學有效性、跨模型梯度與隨機方法逐 bit 重現未由本輪證明。

## Accepted history — 產品品質線：Import 適配與內部整理

以下保留另一線施工及證據；已由 main@94328196 的 PR #146 合併，不是本線 active 工作。

使用者已授權本輪施工，並要求先更新文件、深入整理完整 Import 路徑，不只修單一 helper。
工作區為 `XBrainLab-product-quality`，分支 `refactor/product-quality`，起點 `8636a754`。
本節是本線唯一施工進度；下方研究里程碑由 Evaluation 線維護，不覆寫或執行其題庫／評測。
PR #143–#145 已進入此 main 基線；舊啟動器、RAG、split receipt 與回應性修理不再 active。
使用者已批准刪除 `wip/data-split-summary`，未合併的 UI 修改未帶入本輪。

### 問題、outcome 與界線

- 正式 BIDS importer 使用 metadata／內容，不以 MOABB 名稱白名單放行；Graz GDF 名稱還原、
  T1／T2 語意防護與轉換端 loader 修補需要分清來源、假設及責任。
- 靜態閱讀發現 preview 與 apply 各自實作 run mapping 查找，對同名檔案唯一性處理不同；
  這是待重現風險，不先宣稱使用者資料已錯誤。
- Outcome：preview／validate／apply／recipe／epoch 的 recording 與 class 解讀一致，
  重複政策收斂；production、直接相關 tests／fixtures／scripts 的去留有具體理由。
- 允許修復已重現的 mapping 誤套或資料一致性缺陷；不改 Graz 自動還原或 Assistant 公開工具。
- 2026-09-21 使用者批准移除僅因內部事件名稱為 T1／T2 而要求逐 recording mapping 的
  特例；現有 Match Labels 選事件、填 class 應足以確認，不新增 UI。外部 labels、既有
  recipe 的明確逐檔 mapping 及一般資料一致性／epoch 前置條件保持。
- 不改研究題庫／runner／scorer／模型／prompt／RAG，不新增下載、不搬資料、不升級共用環境，
  不覆寫任何 worktree 的使用者 settings.json；本輪不是 B0 封存。
- 保留有證據的來源適配，不以特例、LOC 歸零為目標；獨立 UI 打磨留待下一階段討論。

### 施工順序

1. 文件先行：校準已合併歷史；逐段追蹤選取 recordings、events／labels、channels、
   review／apply 與 recipe 的實際 caller，在既有資料架構文件記錄保留／收斂／限制。
2. Baseline：沿用 focused tests，建立真 MNE／Command 路徑的 characterization；
   已重現缺陷先 RED，再修理。查清完整路徑、唯一 basename／run 與 carrier 對應。
3. 收斂：在既有模組重用純函式統一等價查找規則；歧義簡寫不得套用到另一筆 recording。
   保留無歧義輸入與 recipe，維持既有 admission、mutation/publication ownership；
   不新增 authoritative owner、state machine、receipt、通用適配平台或 compatibility 空殼。
4. 相鄰清理：同時檢查專用適配、label 建議、recipe trace、資料一致性與相關腳本；
   確認無 caller 或已有可靠替代證據才刪除 helper／重複測試，不擴張無關 panel。
5. 獨立 review、focused／source-diverse／必要 Windows native 驗證；同候選適用 CI 通過後
   集中一次 Import 局部手測。PR 發布／merge 各依授權，不自行合併。

### 驗證、複雜度與完成

- 正例：完整路徑、唯一檔名／run；不同 run 的相同 T1／T2 不同語意；apply／recipe／epoch 一致。
- 反例：跨 subject/session 同名、重複 run、部分 mapping、對調 carrier、真 stale source；
  失敗不得部分 publication；不更動原始檔案、波形、事件時間。
- 適配：Graz 已知模式保留、名稱／順序／通道數不同不得誤套；BIDS external／embedded／
  no-label 路徑維持。用真物件與 Command evidence 補強 mock-only 覆蓋後才刪重複測試。
- 每個 coherent slice 記錄實際 diff、owner 前後與 production LOC；觸及 root complexity
  門檻先 review。Rollback 為各 slice revert，不用大規模搬檔冒充架構改善。
- 不將舊 134-root campaign 當成本 head 證據；CI 已提供的等價 full checks 不本機重跑。
- Stop：已授權範圍、直接驗證與 review 完成後集中交付；若新政策／UI 決策或必要資源阻擋，
  先完成其餘安全工作並提供具體證據。小 commit、CI pending、context 壓縮不是停止條件。
- 已驗：既有 BIDS／reader baseline 72 passed；新增真 Commands 6 個案例原先 4 failed／2 passed，
  重現 run 簡寫丟失、同名檔案 metadata 誤配、歧義 basename 誤套。修理後另外追到 recipe
  將同名 recordings 的 metadata overrides 壓成單一 basename，初次 apply 正確但重播丟失語意。
- recipe 同名 metadata、完整路徑 mapping remap、部分 remap 誤合併與歧義簡寫被 remap
  誤升格均已有真 Command regression；獨立覆核的 findings 已修理，最後覆核無 blocker。
  原 scope 有歧義的簡寫不因重新命名而取得語意授權；沒有 reviewed mapping 時維持原事件，
  不為測試新增 epoch hint 政策。擴大 focused 曾 255 passed；最後 remap 修理直接相關
  82 passed，需在固定版本重新取得整合 evidence。
- BIDS recommendation 清理為 production +8/-42/net -34 LOC，characterization 先後皆 77 passed；
  Graz reader seam 改用真 MNE 物件補正反例、annotation preservation 比對改為事前 snapshot，
  對應 35 tests 通過。純解析／state owners 不增加；不改推論門檻或 UI。
- T1／T2 修理前的 production 合計 +165/-99/net +66 LOC、5 個既有模組；不新增 owner／module／class。
  Apply 內部 mappings 每批先解析一次，移除 preview/apply 的分歧查找；existing publication
  owner 與 cancellation 不動。相關 catalog／converter 腳本確認仍有用途，本輪未任意刪除。
- Static typing、changed-file lint 與 strict docs portal（42 pages／1,617 links）已通過；
  既有 MNE／NumPy deprecation warnings 保留，不在本輪升級共用環境。
- 候選 6f1cf5f9 已驗 focused 256／source-diverse 4 passed。Windows wizard 19 passed／
  2 failed：原 PR #141 已新增 no-label Back/Next driver，folder trace expectation 卻漏同步；
  基線與候選測試 blob 相同，獨立覆核確認。僅補完整序列中的返回步驟，保留所有 state
  assertions，不改 UI。舊 catalog 因候選需更新而主動中止；保存 partial evidence，不計通過。
- 9a0cc0f0 已完成 focused 256、source-diverse 4、Windows wizard 21 與代表性 catalog
  134 passed；這些是修正 T1／T2 政策前的基線，不代表新修改已驗證。
- T1／T2 repair 已完成：真 Commands 重現填 A/B 後 epoch hint 仍是 T1/T2；真 wizard
  重現完成選擇後仍要求額外確認。名稱特例、專用 helpers、確認與套用分支已移除；
  現在以明確 class maps 決定分類／逐檔差異，不新增 owner／module／UI。
- 替換兩個只保護退役政策的 mock-heavy unit tests，改由真 MNE／Command 與 native UI
  覆蓋：共用 class、明確逐檔優先、recipe replay、事件 sample／class 序列與來源 bytes。
  直接回歸保留同名／歧義／remap 的 epoch 防護；獨立覆核的五項資料流程探測通過，無 blocker。
- 6af61225 已完成 focused 279、source-diverse 4、Windows native 22 與代表性 catalog
  134 passed；詳細結果在 build/import-quality 的同版本 verified artifacts。
  使用者已確認 Windows 原生 T1／T2 → A／B 操作通過；此為局部操作確認，不是全部 Import
  驗收或 merge 授權。2026-09-21 使用者已授權推送／開 PR；仍未授權 merge。

- 2026-09-21 使用者同意的操作路徑覆蓋收尾已完成：既有 UI 測試補單／多檔共用 class、
  返回改名後重新 review、BIDS 內部事件及外部 MAT 的實際 epoch／recipe 語意；CSV／TSV
  原 placeholder 測試升級為真 widget → Commands → epoch／recipe，無 labels 實測 epoch
  拒絕且不改 working data。保留取消／重試／失敗 atomicity 的既有保護；完整對照及限制由
  [validation contract](../validation/README.md#import-support-claims) 擁有，不複製另一份矩陣。
- 收尾僅 tests/docs，production 0 LOC；獨立 review 的多檔 oracle 缺口已修正。首輪外部
  測試抓到等待 worker 而未等待獨立 render timer 的時序錯誤；移除測試內手動刷新，限時
  等待自然繪製後 4/4 通過，原失敗保留。整合 Windows native 30/30、0 skip 通過
  （build/import-quality/path-closure-native-integrated.json），lint 通過。未重跑未變產品的
  134-root catalog，不把既有結果換標成新 head；仍有來源警告與 MNE／NumPy deprecations。
- Next：推送產品品質分支、建立 PR 並追蹤同 head CI，修復 in-scope 失敗；不自行 merge。
  本輪沒有再次改變使用者剛確認的產品行為，不要求重測 T1／T2，也不把局部確認当 merge 同意。
## Completed record — B0 完整執行入口（2026-09-21）

使用者授權的可日常重跑 B0 入口已實作、獨立覆核及實跑全矩陣；
`baseline.cmd` 的固定範圍與用法由[研究規格第 5 節](../validation/thesis_protocol.md)擁有，
實際結果、資源位置與重現限制見 [Current](../current.md#assistant-research-baseline)。

- 重用 frozen runner／scorer／report，沒有新增產品 owner、環境或模型下載；原封存不改。
- 全 300 題與報告驗收、report-only、無重送的 completed resume、中文／空白搬移驗證通過。
  入口測試／相鄰契約與 Windows preflight 完成，測量與各次報告保留。
- 已辨識既有 prompt 的匿名識別／publication counter 變動；不追改 B0，也不把它說成
  完全相同輸入或正式模型排名。正式比較前的非任務資訊控制留待 M4 決策。
- 本輪 scope-complete；沒有產品 UI 變更、push／PR／merge 或 Development／Validation／Test。
  不自動啟動下列 candidate。

## Completed record — 正式 B0 共用修理與封存（2026-09-21）

使用者授權的共用格式／重試修理、相同矩陣重跑及另立正式 B0 已完成。
`assistant-b0-formal-20260921-926d90ea` 固定 `926d90ea`；前期 `ac8af81d` tag、
原始分數與封存不追改。精確版本、結果、封存位置與限制由
[Current](../current.md#assistant-research-baseline) 擁有，契約由 target／研究規格擁有。

- 共用整份 JSON fence 相容與預設一次格式修復，沒有新增 owner／控制層；直接相鄰的
  舊 evaluator observation adapter 及非法 typed-clarification scorer 假陽性亦已修正。
- Focused tests、契約／安全獨立覆核通過；完整 300 題與 320 次 capture、分母、
  逐題判分及報告連結經獨立核對，低分、失敗與先前 partial 原樣保留。
- 新鎖定 Windows 環境真跑單條件 30 題，分數／repair／核對的產品結果一致。
  E 槽封存 6,216 檔逐檔校驗通過，僅移除本輪臨時 checkout／環境；共享資源保留。
- 本輪 scope-complete，不是 native UI 驗收或產品 handoff-ready；未 merge、
  未跑 Validation／Test，也未開始 Development 調優。後續候選須另行確認。

## Future — 完整 DEV 起始基準後的調優（尚未授權）

前期 Pilot／B0 與新版完整 DEV initial 均已完成。
事實與限制見 [Current](../current.md#assistant-research-baseline)，
報告入口／契約見研究規格第 5 節。舊分數與快照不追改。
下一輪若經使用者確認，才依
[研究規格](../validation/thesis_protocol.md) 的每模型最多五套設定規則選擇改善方案；
本輪 initial 已占各模型第一套。只調已允許的提示詞／工具呈現／格式修復，RAG 固定。
不因 Pilot 分數直接調 prompt／RAG、挑模型或啟動
Validation／Test；Test 仍封存且本輪未讀取。

可據本次證據討論的改善最多三項：缺資訊時自行補參數、不得操作時仍選擇工具、
動態 publication 變動下的操作交接。共用 fence 與重複修復已處理；仍存在的模型格式錯誤
不能說成全部解決。這些是候選，不藉報告施工直接改模型或產品。

## Completed record — Assistant Evaluation 準備至 Pilot（2026-09-21）

使用者已確認本輪做到「文件校正 → 非 Test 題庫接入 → 評測系統就緒 → Pilot →
結果報告與改善前基線封存／還原驗證」。不是只做文件，也不自動進入 Development 調優、
正式 Validation／Test 或 B1／B2。研究條件與預算只由
[研究規格](../validation/thesis_protocol.md) 擁有；本節只記執行順序、責任與進度。

### 起始問題、施工範圍與出口

- **起始證據**：既有 calibration 只讀合成觀察；舊 frozen 81-case runner 攔截工具執行，
  不能當成本輪真實 Product Outcome。正常 ChatPanel／Host／Command 與 prompt capture 可重用，
  新題庫讀取與單次決策 scorer 已完成 focused 驗證；五模型配置、真實 outcome 與
  完整 runner／軌跡判分／計時／續跑在本輪開始時尚待施工及驗證。
- **起始題庫狀態**：已接收使用者指定的非 Test Excel，結構為 DEV 264 題／66 families、
  VALID 99 題／33 families，family 無交集。使用者於 2026-09-21 明確確認題目與答案
  全數人工覆核完成；當時實際 runtime fixture 仍須準備，不以人工確認代替執行證據。
  Test 仍由使用者保管，
  不為找題庫而讀取封存題文、答案或其他對話全文。
- **完成出口**：Pilot 全部預定案例有完整可追溯軌跡，測量與判分可核對，交付分條件結果、
  有效失敗／無效測量、延遲與資源成本、後續實驗可行性，以及可還原的改善前基線。
  模型低分不是未完成；缺少條件／紀錄或只跑工程 smoke 不能算 Pilot 完成。
- **假設**：使用英文單回合題庫及既有產品工具契約。必要的取消、停止、狀態過期與晚到結果
  只作工程保護，不擴張為未批准的正式多輪實驗。
- **範圍**：題庫格式／oracle 接合、真實觀測、scorer、模型研究接入、單一實驗入口、
  計時／軌跡／結果彙整、安全續跑、Pilot 與封存。直接必要缺陷先重現、最小修理。
- **非目標**：不改公開工具、產品模型清單、UI layout／文字／流程；不調 prompt／RAG 追分，
  不做全面重構、EEG 模型研究或重新下載整套 EEG 資料。Test 不讀、不跑。
- **UI 確認**：本輪不含可見 UI 變更；真實操作觀測沿用現有 UI。若修理需要改可見互動
  或 public contract，先提出具體決策，不把本輪批准當作通用授權。

### 雙線工作區與共用邊界

| 工作線 | 工作目錄／起始 branch | 責任 |
| --- | --- | --- |
| Evaluation（本線） | `D:\workspace_v2\projects\lab\XBrainLab-evaluation`；`feat/assistant-evaluation` | 本節授權範圍、研究規格、評測與基線 |
| 產品品質（另一對話） | `D:\workspace_v2\projects\lab\XBrainLab-product-quality`；`refactor/product-quality` | 另行確認的清理、重構與 UI 調整；不是本線的隱含施工範圍 |

兩個 worktree 從 `main@8636a754` 建立，Git 決定最新 branch／dirty 事實；`main` 仍為唯一
產品基線。工作目錄可持續使用，task branch 仍須保持明確目標，不演變為永久平行產品。

- 本線擁有研究規格與 Evaluation active 內容；另一線更新自己的計畫區塊，不覆寫本線進度。
  本文件仍是唯一 active plan，不另造第二套總計畫。合併時保留兩線各自有效更新。
- Command API、工具／完成語意、狀態 publication、資料解讀與 UI 觀測接點是共享邊界；
  修改前協調 owner 與受影響案例，不各自建立相同責任，也不自行合入另一線未完成修改。
- 每輪實驗固定 source／設定／模型／題庫／scorer 身分；只在輪次之間明確同步已接受的
  `main`。中途不 pull／換 source，改版另立 run 身分，不混用前後結果。
- 不複製大型模型與 EEG corpus；必要來源按不可變 revision／hash 管理。各 worktree 的
  可寫設定、run output、log、暫存與 RAG index 須分離或有明確唯讀共用邊界，先驗證再執行。
  主工作區 `settings.json` 不覆寫、不 stage。
- 優先使用既有 Windows 環境；實驗期間不得升級共用依賴。若需要不同依賴，先確認有界的
  隔離環境與空間方案，不默默改另一線。量延遲期間不並行 GPU 訓練、模型推論或重型測試。
- 正式實驗與 B0 不靠 worktree 留存保證：封存內容／還原要求由研究規格擁有。

### 實作與驗證順序

1. **文件與接收**：移除已結束 dispatch、保存本輪與雙線決策；核對非 Test 題庫路徑與
   元資料。只有當題使用者輸入可進入該回合；oracle／答案與其他題庫內容不得進入 prompt、
   few-shot 或 RAG。Validation 不用來除錯。只取得使用者提供的
   Test 封存狀態／數量／身分，不代稱已獨立審題。
2. **題庫與 scorer**：沿用既有 parser／schema，實作正式研究的三類／分層判分與完整性檢查；
   用已知正反例保護工具／參數錯誤、正常不執行、Host 擋錯不算模型答對、缺失軌跡與錯誤身分。
   不覆寫舊 calibration 或 frozen 81-case 的規則與歷史成績。
3. **真實觀測與 runner**：正常 ChatPanel／Host／Command 路徑接 case／attempt／terminal，
   開窗就緒與完整操作 outcome 分開；產品 owner 決定 readiness、confirmation、mutation。
   補選一／多個／全部條件、輸入輸出與各時間段、失敗彙整與安全續跑，不新建產品 owner。
4. **模型與資源**：唯讀核對五模型精確來源、revision、權重大小、VRAM、授權與 cache。
   缺模型／條款需取得對應授權，不 silent fallback、不自動增加 cache 上限。固定配置後，
   有界載入、暖機與非 Test smoke；RAG on 須真正可用，degraded 不能當作 on 成績。
5. **Pilot**：題庫／系統 gate 通過後，按研究規格固定 manifest、題號、配置與輸出；
   先小階段驗證測量，再補完整矩陣。有效低分照跑照留；測量故障修理後只補受影響部分，
   不以看見答案後重試挑分數。機器時間到預算上限即保存 partial，不自行延長。
6. **收尾與封存**：核對逐題軌跡／分母／失敗與量測界線，交付粗略成本與限制；
   保存 source、環境、模型／資料身分、重跑命令與原始結果，實際還原驗證 B0，
   不開始 B1／B2，不將 Pilot 當正式獨立 Test 或穩定 P95／模型排名。

每個直接必要 slice 實作前在本節補 call sites、具體 focused validation 與回退邊界；
新行為先 RED→GREEN，refactor 使用 passing baseline。每次修改 review，高風險資料／
async／評測證據採獨立覆核；同一份實際 diff 與測量證據由主 agent 驗收。
不為每個內部 slice 要求使用者重測 GUI；產品行為變更仍遵守正式 handoff／merge 規則。
Pilot 完成不等於產品手測／merge 同意；外部寫入與交付仍依 repo 授權邊界。

**完成位置**：題庫／scorer、研究 runtime 注入、五模型檔案取得、全部 selected fixture、
真 Qt observation 與完整 runner 已完成 focused 驗證；Gemma 經批准 NF4 配置通過 GPU
工程檢查。第一版 frozen Pilot `8a7935c3` 在 176/300 fail closed：Phi-4 對
`DEV-C06-01-V3` 錯誤呼叫 `switch_panel(visualization, 3d_plot)`，產品正常顯示既有
`VRAM Warning`，但 driver 把該可歸因的產品警告誤記為 `unexpected_dialog`／無效量測。
已完成的低分與失敗原樣保留，不作挑分重送；此 run 僅是量測框架缺口證據，不納入正式
Pilot 比較。完整 300 題 Pilot 與 B0 封存／還原結果見本節後續完成紀錄及
[Current](../current.md)；下列施工細節保留為歷史證據，不再是 active dispatch。
題庫 intake 證據與來源如下。
來源為使用者指定的 `C:\Users\Administrator\Downloads\題型_已審不含TEST.xlsx`，
SHA-256 `2161af9932950e2a0726daeae3d744935d8d1bc6f408d739b2240d2752a29c23`。
只讀原檔；工作表、split、ID／family／fixture 與 ground-truth 對應 fail closed，
不發現其他檔案或讀取 Test。原 workbook 的 363 筆 review_status 均仍為待人工複核，
runtime 證據 source 為 `8314b590`。使用者於 2026-09-21 已確認全部人工覆核完成；
此為原 workbook hash 所對應的補充宣告，不覆寫原檔／舊 runtime 證據。

直接施工接點：`scripts/dev/assistant_pilot_bank.py` 讀取這份明確 XLSX 契約並輸出有
source identity 的非 Test bank；`scripts/dev/assistant_pilot_scoring.py` 以既有
`CommandParser.parse_product`、`ToolSchemaValidator`／工具 registry 做離線決策判分。
保留 workbook oracle／fixture 原始欄位與舊證據標記；供模型的輸入與 oracle 分離。
Scorer 區分 Action、Clarification、No-call，正常 respond_to_user 不要求 exact message
或 typed pending receipt；錯誤 call 被 Host 擋住仍不能變成模型正確。這只是決策判分，
不宣稱 backend／GUI 成功，不改舊 calibration 或 frozen 81-case。
刪除候選：無；既有 product owner 前後不變，production LOC +0/-0，僅 scripts／tests，
不增加 state machine、receipt 或相容分支。XLSX 不新增套件／修改共用環境。
Focused：新增相應 unit tests 先 RED→GREEN；覆蓋正常讀取、split／family 洩漏、重複／
缺漏／衝突 ID、無效 JSON、受限壓縮／XML、source 身分，以及正／錯工具參數、
布林不等於數值、正常／空白／invalid 不操作回覆、初次／修復後分開與不偷用 oracle。
真 workbook 做 metadata／完整性核對，題庫內容不 commit。獨立 review 後才接實際 runtime；
rollback 僅移除本 slice 新 scripts／tests 與對應計畫，不改原 XLSX／模型／產品。
**已查**：bank／selection／models／fixture／scorer 與既有 calibration 的 Windows
focused tests 合計 226 通過；runtime 注入及相鄰 default／spawn／cancel tests 132 通過；
MainWindow factory／既有 UI shutdown tests 28 通過。scorer、runtime 與 fixture 經獨立 review，
主 agent 已查實際 diff／測試及真 workbook；Ruff、diff check 通過。第三方 deprecation
warnings 保留，未改環境。真 workbook 363 題 oracle schema 全數合法，人工覆核由使用者確認。
正常 controller 的 generation request／events、activity、Command completion 與 turn terminal
可作觀測接點；舊 runner 明確 suppress 工具執行，不沿用其結果作真實 outcome。
既有 TurnMetrics 包含整個 turn，UI request success 也不代表畫面已就緒，須分別觀測。
既有 Windows 環境為 Python 3.12.10／torch 2.11.0+cu130／transformers 4.57.6；
未安裝或升級。三個批准 snapshot 的既有 HF 帳號 access 通過；39 個必要檔案下載及
大小／官方 LFS SHA-256 核對完成，新增 22,768,349,036 bytes，盤點總 cache
41,711,365,409 bytes（含既有 repo/cache 與保守 WSL 用量），未刪既有資料。
**已完成的量測修理**：上述 UI 實例已補 RED→GREEN characterization；只將可識別、由本回合 action 引起的
產品資訊警告記為 product outcome 並安全關閉，未知 dialog 仍 fail closed。Windows runner
子程序已加 `CREATE_NO_WINDOW`，保留 stdout/stderr、精確 PID、timeout、terminate/kill 與
cleanup 語意；相鄰 117 tests 與 focused Ruff 通過，diff review 無 blocker。

第二版 frozen run `efa46489` 在 35 個完整結果後依使用者要求停止；精確執行中 child 已確認
退出，partial 只保留工程證據、不納入 Pilot。這 36 份已寫 result 的 baseline 顯示模型載入
中位數 7.424 s、整題中位數 12.854 s，載入占總 wall time 57.0%；fixture 中位數 0.289 s、
decision 中位數 2.049 s。每題 fresh process 雖隔離嚴格，但 300 次載入不是研究條件，模型
載入本來也另行統計，故改成每個 model×RAG condition 一個 owned child／一次 cold load，
同條件 30 題依序執行。

Condition worker 只重構 `scripts/dev` runner/case seam，不改產品 runtime owner、prompt、題庫、
scorer、UI 或 public contract。每題沿用既有正式 `reset_session` 與 `reset_conversation`，重新
建立 fixture、trace、UI driver、case deadline 與 result；進題前 fail closed 核對零 active
operation／turn／pending interaction、空 conversation/transcript、初始 pipeline stage 與同一
pinned runtime。prompt capture 需用序號範圍精確綁定每題，warmup 每 condition 只做一次。
Parent 對 condition child 保留精確 PID、硬 timeout、stdout/stderr、journal 與不重送 started
condition；任一 case 或 reset audit 失敗立即停止並保留所有已完成結果。先用 synthetic/real Qt
characterization 證明兩題不同 fixture／conversation 無污染、child timeout cleanup 與 resume
語意，再跑一個 2-case 真 GPU before/after probe，確認只載入一次且決策／capture 完整，最後
以新 clean commit 從 0/300 重跑。不得把舊 176／35 題與新 source 混成一批。

Owner 前後不變：產品 model process 仍由既有 LocalRuntimeProcessOwner 擁有，Study mutation
仍由 ApplicationService 擁有；研究 parent 由 per-case child scheduling 收斂成 per-condition
child scheduling，不新增產品 owner/state machine/receipt。刪除候選為每題重複 runtime
bootstrap、warmup 與 RAG warmup。回退為 condition runner/case adapter 與 tests；若無法證明
reset isolation，回到 fresh-process 設計而不宣稱效能改善。production LOC +0/-0。

**Condition batching 施工狀態**：parent manifest 已升為 v2，依 condition 分成 10 個 hidden
Windows children；每個 child 一次 cold load／warmup，30 題各有獨立 hard watchdog、fixture、
trace、UI driver evidence、prompt capture range 與 result。case 之間經正式 reset owners 並
檢查空 pipeline／conversation／transcript／pending interaction／owned jobs；parent 只為 child
實際回報的 case 建 journal terminal，不把未開始題偽造成失敗。Report 將 model load／warmup
每 condition 計一次，case timing 仍逐題。相關 128 tests 與 Ruff 已通過。
第一個真 Phi-4/RAG-off probe 在模型完成一次載入／warmup後、首題進入 boundary audit 時
fail closed：產品 `pipeline_stage` 契約為字串，runner 誤當 Enum 取 `.value`。沒有送題或產生
模型成績，condition cleanup 通過。已補最小 RED→GREEN 與 parent 相鄰 29 tests；舊 probe
只保留工程失敗證據。修正後以 frozen `c31a8559` 重跑同一真 GPU／真 Qt condition：30/30
結果均為 recorded、cleanup 與 case boundary 通過，conversation／visible transcript／active
operation／pending interaction 皆在每題前歸零，逐題 prompt capture 與 input audit 無 issue。
模型只 cold load 一次（8.002 s），30 題 condition wall time 108.011 s；相對先前 fresh-process
36 題實測的整題中位數 12.854 s，30 題推估 385.620 s，減少約 72.0% 無研究價值的等待。
Probe report 保留為 partial engineering evidence：有效 decision 30/30、無 missing／invalid／
timeout，first／final macro 皆 0.648；低分不重送也不當成 runner 失敗。此 probe 當時仍不是
Pilot 完成；後續完整 frozen 300 題結果如下。
當時已有基本報表與 B0 封存／環境還原；後續已補完整可讀報告及還原後真實測量，見 Current。
UI layout／文案／產品互動不變；只改研究 driver 對既有警告的觀測分類與 runner 的 console
presentation。回退為這兩個 script seam 與 tests，不改產品 owner/public contract。
**當時出口**：frozen `ac8af81d` 的 300/300 題完整執行、基本報告與 B0 環境還原已完成；
Test 未讀取。缺資訊題的 prompt/history/RAG 由逐題 input audit 核對，fixture setup 不取代此 gate。

模型唯讀 preflight 找到下列官方 pin，使用者於 2026-09-21 批准下載；尚未認證載入成功：

| 官方來源 | 候選 revision | Safetensors 權重大小 | 權限 |
| --- | --- | ---: | --- |
| [Phi-4-mini-instruct](https://huggingface.co/microsoft/Phi-4-mini-instruct) | `cfbefacb99257ffa30c83adab238a50856ac3083` | 7.672 GB | MIT；已下載／核對 |
| [Llama-3.2-3B-Instruct](https://huggingface.co/meta-llama/Llama-3.2-3B-Instruct) | `0cb88a4f764b7a12671c53f0838cd831a0843b95` | 6.426 GB | 既有帳號 access 通過；已下載／核對 |
| [gemma-3-4b-it](https://huggingface.co/google/gemma-3-4b-it) | `093f9f388b31de276ce2de164bdc2081324b9767` | 8.600 GB | 既有帳號 access 通過；已下載／核對 |

官方 shard metadata 加上既有兩個 Granite，五模型權重合計約 34.571 GB，尚不含其他
cache／設定／tokenizer；超過原 20 GB 總上限。使用者已批准上述精確
來源下載至 `D:\XBrainLabCache\models`、研究期間總模型 cache 上限提高至 50 GB；先
精確盤點現有用量，若仍超限便停，不刪共用模型、不繞過條款，也不代使用者接受條款。
五個 pinned tokenizer 都完成原生 system／untrusted context／request template 檢查。
兩個 Granite、Phi、Llama 依序完成 Windows GPU BF16 load→32-token engineering generate→
close，四個 owned child 均確認退出。32-token smoke 不等於正式 512-token／8K prompt
壓力測試、GUI tool outcome 或 Pilot 分數。Gemma 的 tokenizer 成功，但 load 在物化前拒絕。
全部維持 `trust_remote_code=False`、local-files-only，不代接受條款、升級或 silent fallback。
產品 allow-list 仍只含兩個 Granite；研究已重用既有 `engine_factory`／lifecycle 接點。

**Gemma 限制**：研究候選估算 12,000,000,000 bytes 尚非實測 peak；既有 model-load guard
在 required > 75% available 時 fail closed，因此需至少 16,000,000,000 bytes 可用。
所有本 agent 模型程序退出後再查為 15,738,077,184 bytes，尚差 261,922,816 bytes。
這是 admission rejection，不是 OOM、模型錯誤或準確率；不為過 gate 降低未測估算、不
關無關程序。原生權重 header 確認 BF16 tensor 共 8,600,158,944 bytes；加最保守 full-length
KV 為 9.741 GB，但尚未含 activation/workspace/allocator，不能用來假裝總 peak 已知。
使用者後續批准 Gemma NF4/BF16，量化 estimate 已依實測上調為 11 GB，沒有繞過 guard。
本機 evidence：ignored `build/dev-artifacts/model-preparation-20260921/`，含下載 receipt、
各模型 smoke（包括 Gemma 失敗）、bank-hash selection 與 initial fixture report。

### 直接必要 runtime slice（2026-09-21）

**2026-09-21 已批准 Gemma 量化修理**：只將 Gemma 研究配置改為 bitsandbytes
NF4 4-bit／BF16 compute，其他四模型不變。沿用官方 pin／已下載權重，不改日常
settings、不下載或升級共用環境。原 12 GB BF16 估算被既有 75% guard 拒絕不是 OOM。
先 RED tests，再由既有 immutable spec 攜帶量化 estimate/type/compute；research factory
固定配置並拒絕漂移；default product 4-bit 行為不變。研究量化固定指定 GPU，不 offload。
初始 estimate 依 pinned tensor headers：BF16 8.600 GB，其中 embedding 等未量化
1.355 GB、候選 Linear 7.245 GB；保留 metadata、保守 8K KV、activation/workspace
與載入暫存餘裕，先估 8 GB（未實測）。保留既有 75%/90% guard 與 OOM cleanup。
Focused：量化/非量化 admission、無 estimate/漂移拒絕、dtype/device/pin、相鄰載入與
OOM tests；Windows native load、代表性 prompt/output、peak memory、cancel/reload/close。
新 evidence 不覆寫舊拒絕；實測超出估算須上調重驗，不為過 gate 降低。
Owners 不變，無新 class/state/receipt；optional spec fields 與既有 backend branch。
UI unchanged；回退只移除此配置接合，不刪共用模型或證據。出口為安全實測及獨立 review
後接續 runner/Pilot，不將 smoke 當 Pilot 或 BF16 accuracy。

**量化驗證結果**：初始 7,025-token input 的 peak reserved 8.869 GB 超過 8 GB
analytic estimate；如實保存並上調為 11 GB。較強 7,671 input＋512 output 原生生成
35.62 秒，peak allocated 9.375 GB／reserved 9.878 GB、400 個 Linear4bit，全部 CUDA。
直接 engine 同程序 unload 後仍保留 allocator pool，故 reload 被 11 GB guard 拒絕；
保留此限制，不把它說成成功。產品實際 owned-process 邊界另驗兩輪載入／串流／
並行消費時取消／再生成／close；均成功且 child 退出，可用顯存前後同為
15,738,077,184 bytes。第一版 cancellation probe 同執行緒不消費 stream，觸發正常
hard-stop/restart-required；修正 probe 為產品同樣的並行消費，舊失敗保留。
Windows focused quantization／catalog／backend／injection 合計 99 tests 通過；
獨立 source review 無 blocker。工程 artifacts 為 model-preparation-20260921 下
gemma-nf4-*／gemma-owned-nf4-*，不計入 Pilot 分母，未宣稱 BF16 速度或品質等價。

證據：`AgentWorker` 已使用 owned process，但固定建構預設 engine，且每次生成重新讀取
日常 settings；`LocalBackend` 三處直接取 product spec；系統角色與連續 user roles 能力
混在同一 flag。五模型研究不可經 Settings 正規化而無聲換回 Granite。
Outcome：既有 runtime 注入不可變研究 spec／frozen generation config；預設產品行為與
allow-list 不變。UI 文案／layout／public tools 不變，不建立第二個 controller 或取消 owner。
步驟／接點：`LocalBackend` explicit spec 與固定 template kwargs；既有 `LLMEngine`
接受 backend factory；`AgentWorker` 透過既有 `LocalRuntimeProcessOwner.engine_factory`
傳入可 pickle 的研究 factory，選用 frozen config loader；`LLMController` 選用 worker factory。
`LocalModelSpec` 分開連續 user role 能力，Granite 現有 prompt 保持不變；Gemma 只作官方
template 必要相容，Llama 固定模板日期。不改 product catalog membership、download policy
或 runtime lease／cancel／close 實作；MainWindow 接合另先核對既有 lifecycle seam。
Complexity review：刪除／收斂候選為重複 spec lookup；owners 前後不變，不新增 public class、
state machine 或 receipt。實際 runtime production +91/-12/net +79 LOC／5 files，屬研究
接入功能而非純重構；MainWindow 接點另 +5/-2/net +3。可獨立回退，不刪下載模型／題庫。
Focused：既有 local backend／engine／worker／controller characterization 先通過；新增
default policy 拒絕、spec/config mismatch、固定模板與 settings、Windows spawn／stream／
cancel／close 測試。外部權重隔離允許 mock，但 owned process lifecycle 必須實際執行。
獨立覆核 default-policy bypass、父子程序身分漂移與 shutdown；主 agent 核對實際 diff。
此 slice 出口為上述工程證據閉合，之後接真實 GUI／Command 觀測；不冒充 Pilot 完成。
研究端接點 `scripts/dev/assistant_pilot_models.py` 僅固定五個既有／批准 spec，重用
LaunchSpec／SettingsSnapshot 與 module-level engine factory；拒絕未列模型，不替產品
新增 resolver policy。Pilot 初始工程配置沿用 structured-decision greedy／512 output，
8,192 context、seed 0；四模型 BF16，Gemma 依後續批准 NF4/BF16；
Llama template 日期固定 2026-09-21。
這是先行 smoke／Pilot 配置，不提升為正式實驗參數。Focused：完整 pins、未知模型拒絕、
frozen config 重建互不污染、spawn pickle 身分、existing two-model product catalog 不變。

Pilot selection 準備：不依模型結果選題。DEV A01–A18／C01–C06 各選字典序第一個
family，N01–N03 各選前兩個 family；family 內選最長 input，平手以 case ID 排序。
保留 30 個不同 family、18／6／6 配額、18 action tools；第一階段固定 A05、A08、
C01、C02、N02 第一個 family、N03 第一個 family（2／2／2、含 GUI 與直接操作）。
只保存 bank hash、選題規則、ID 與分階段順序，oracle 不進 prompt；拒絕錯誤 ID、
不足配額／重複 action tool／VALID 入選。接點為既有 `assistant_pilot_bank.py` 的純函式，
focused synthetic bank tests 保護順序不受輸入排列影響、更新 bank hash 不能偷用舊身分。
實際選題最長版本僅 37–81 字元：包含本題庫相對較長變體，不宣稱 long-context 壓測。

### 真實 fixture／UI 接合 slice

**正常路徑 observation slice**：重用 controller generation／dispatcher／runtime signals，
script 收集 per-case/per-generation 原始 input/output、confirmation、Command、UI handoff
與 turn terminal；不接受 oracle、不代執行或推導成功。controller 只在既有 parser／
ToolAttemptDecision 位置加 best-effort 診斷（含拒絕）；不重評 admission，不新增 owner。
觀測有界、時間戳與關聯身分明確，缺漏／截斷標為無效量測；GUI visible-ready 由後續
實際 Qt driver 另觀測。先已知完整／拒絕／錯誤／缺失 trace tests，再真 Qt controller
路徑驗證；獨立 lifecycle review。無可見 UI／工具契約變更；回退只移除此診斷接點與
research collector，不改既有執行／取消政策。此 slice 完成後仍須 runner 與真 Pilot。
RAG off 由 controller 的明確研究建構選項跳過 start/retrieve，沿用既有無檢索組裝路徑；
預設 on 不變，不用 failed/degraded retriever 假裝 off。On 須另驗 ready/檢索無錯誤，
embedding 唯讀共用、可寫 vectors 在研究 run 隔離；corpus 不加題目／答案。

**真 Qt driver／單一入口**：script 只對 isolated synthetic case 的實際 confirmation card
按批准；按真 handoff route 觀測 visible/enabled dialog 或實際 panel/view，保存畫面，
開窗題在 ready 後透過真 Cancel 收尾。不憑 oracle 挑畫面、不合成 resolution，不對未知
提示框任意 Yes。Start/Saliency 另待真 job terminal，不能以 turn terminal 代替。
每題 fresh Study/MainWindow/owned runtime，先固定 settings/prompt/log/RAG/output 隔離；
模型 load/warmup 與單次決策120秒分列，case process 有硬 timeout；只停自己的程序。
父入口固定 DEV30／5model／RAGon-off／seed0，先6題60次再24題240次，支援指定條件與
同身分續跑，不覆寫結果或重送已開始但未終結的case。總4小時含setup/load/cleanup；
到限保存partial。Source/environment/hash漂移拒絕續跑；先合成正反例與真Qt工程驗證，
再凍結commit跑Pilot。A14 CPU live fixture 明確10000epoch ceiling，仍只有12trials；
只為維持running初態，在decision完成/120秒時立即stop，另≤10秒cleanup；自然先完成
為fixture drift不是模型錯誤。其他completed fixtures仍1epoch，不增加EEG研究範圍。

問題：舊 fixture 是 128 Hz／4 channels，與本題庫的 250／256／512 Hz／5 channels 不符；
部分舊 helper 會刪共用 temp 目錄，不能直接沿用。`MainWindow.init_agent` 固定 manager
建構，研究不能在啟動後偷換 controller／engine 或以 debug transport 取代正常路徑。
Outcome：逐 case 專屬新目錄中的 deterministic EEG，經既有 Scan→Preview→Validate→Apply
與 preprocess／epoch／split／train Commands 產生真實狀態；fixture、publication、callable
tool 必須核對，不以人工 stage 字串或 oracle 偽造。fixture 配置只建初始狀態，不執行待測動作。
接點：研究 script `assistant_pilot_fixture.py` 與直接 integration tests；先覆蓋 empty、
data_loaded、preprocessed、epoch_ready、dataset_ready，完成／執行中 training 與 saliency
必須用真 job，另驗取消／close。不得呼叫會刪 global temp 的舊 helper，原資料唯讀。
UI 只為 `MainWindow` 加可選 manager factory，預設仍建相同 AgentManager；研究沿用既有
AgentManager(runtime_lifecycle=...) 與 lifecycle.start(launch_spec=...)，在 UI 綁定後啟動。
不新增研究 resolver、不走 Settings／model switch，不改可見 UI；controller／Command
owner 不變。constructor/init_agent 實際 +5/-2/net +3 LOC，無新 owner。
Focused：預設 MainWindow lifecycle／shutdown baseline、factory 真 Qt 綁定與 close；fixture
以實際 service publication／channel／sfreq／event／split 檢查。相鄰 UI 流程不全套重測。
Rollback 僅移除 factory 參數與新研究 script/tests；不清共用 cache、原始題庫或 EEG 檔案。
slice 出口後接 observer／runner，非 Pilot 完成；等待 signal／GUI handoff／模型錯誤各自記錄。
實際 30 個選定 DEV 的 initial-state fixtures 均已經真 Commands 驗證；另補五個
job-dependent case 的真 CPU training／Gradient saliency，fixture suite 32 tests 通過。
真 Qt driver 及 adjacent host 17 tests 通過，包含真 completed saliency render。
以上只是初態及量測準備，不是 30 題模型結果或完整 Pilot。
observer source review：既有 generation request/events、dispatcher input/confirmation、
command completion 與 runtime turn terminal 可重用；Host admission 及可見 surface-ready
尚無完整觀測。須在既有判定接點加 failure-isolated diagnostic notification，或研究端
Qt show/next-loop 觀察，不攔截 execute、重算 admission 或把 modal 關閉當開窗延遲。

**2026-09-21 runner 整合修理／證據**：原 helper 在 composer 空白時等 disabled Send，
真 host 工程 attempt2 因而未送出；已改填入後等待 ready，真 Qt regression 保護。
Gemma attempt3 正常走完三次格式錯誤與耗盡終態，完整 raw／capture／scorer、cleanup；
這是有效模型失敗，不是正確回答。Granite4 RAG-on engineering bandpass 已真正執行
8–30 Hz 濾波、記錄 Command／publication 並正常 close。兩者不是 workbook 或 Pilot。
Decision clock 改採實際交付／回覆事件，不以 provisional envelope 結束修復計時；
job 從永久 identity/result 追蹤，不只 poll active；UI pending drain 後才產出結果。
Windows venv launcher 有兩層 PID：已用 base interpreter＋child-local launcher hint，
原生確認實際 PID＝Popen PID 且仍用同 venv；不終止無關程序。
Training 初態改在暖機後建立；turn 終態或120秒定點停止 runner 自有初始 CPU job，
明列 runner cleanup，不算模型 stop 成功。真正 stop engineering case 被 Host stale
publication 擋住，保留原始證據並釐清，不修改模型/prompt來追分。
Prompt provenance 核對初次 fresh history、當題 input、state card 與 untrusted RAG 分離；
缺資訊英文語意仍由人工覆核，不宣稱字串檢查能證明。後續已完成 Product Outcome、
報表、callback exception／cancel工程檢查及 source freeze，再完成全部 300 題；未因 checkpoint 停止。
整合 complexity review：production 六個既有 files 共 +197/-24/net+173 LOC，
owner 數不變；沒有新增 production class/module/state machine/receipt。研究 scripts
分別擁有 bank、fixture、配置、passive trace、UI driver、case composition、sequential
journal 與離線報表，均不替代 ApplicationService／Host policy。暫無可刪的產品 owner；
需要的注入 seam 可整組回退，原模型／設定／題庫不動。逐題 fresh runtime 的載入成本
獨立報告；這輪先確保可核對，並不宣稱此 runner 已優化成最高吞吐量。
取消的 prompt capture 另保護 late-chunk 邊界：僅 host terminal 與 capture status
均 cancelled 時，可接受 host raw 是 child raw 的嚴格 prefix，保留未觀測尾段長度與
兩份原文；scorer 不使用該尾段補分。完成／錯誤或非 prefix 不一致仍無效。
真正提交後、生成前便達決策 deadline，須有同題 submission＋cancelled terminal；
可記為尚未送入模型的有效 timeout，不偽造 prompt。Qt poll exception 留存 error 後
走正常清理；不能穿出 callback 造成無證據的 native abort。
兩批整合 focused tests 為146＋137通過；之後直接新增的報表／callback／取消 tests
另依其實際結果核對。兩個 MkDocs strict build通過。實際 Windows --prepare 已核對
300 jobs／五模型／embedding hash；執行拒絕 dirty source，後續完整 Pilot 已由 clean frozen source 完成。
最後的 Product Outcome 已接合：正確 decision／Host blocked／實際 Command／GUI
handoff 分列；driver Cancel 只證明可開窗，不說匯入完成。錯誤工具真的執行仍保留
observed_actions；Saliency 精確綁定本次 compute operation ID，不以舊 fixture job代替。
有匹配 request、clock、screenshot 的 UI timeout／render failure 是有效產品失敗，
缺觀測才是無效量測。新 saliency engineering attempt2 已真模型執行／渲染完成並
通過新 binding；舊 artifact 不補造 ID 或覆寫。獨立覆核 blocker 已解除。
Runtime／passive observer 切片提交於 `aba24e5c`；最終 runner 由 clean `ac8af81d` 執行完整
manifest。300/300 均 recorded，10 個 condition cleanup、每題 boundary／capture／input audit
全數通過；正式 report 為 non-partial、完整 selected schedule，總 active time 1,876.047 秒。
模型錯誤與低分照留不重送。B0 tag 為 `assistant-b0-20260921-ac8af81d`；E 槽封存約 1.4 GB、
3,136 個檔案逐檔 SHA-256 通過。五模型 66 個 snapshot 檔（34,655,741,445 bytes）與 11 個
embedding 檔（91,578,415 bytes）重算一致；大型資源維持 D 槽單一受控 cache，不重複複製。
從 bundle 在 E 槽隔離 checkout、由外部 Poetry 2.3.4 建立全新 Windows venv，三個 PyTorch
套件均為 `+cu130`、`pip check` 通過，非 Test prepare 重建 300 jobs 且所有身份相符。
第一次把 Poetry 裝入目標 venv 的錯誤方法與 PowerShell 中文路徑失敗均保留；修正後 ASCII
wrapper 的 PrepareOnly 單一命令通過。這不是產品 merge 批准或正式模型排名。

**歷史交付更正**：上述完成宣稱未區分基本報表與完整可讀輸出，也未取得還原後真模型／工具
測量；後續補驗及限制由 Current 擁有。M4 仍是後續研究決策。Context compaction、完成一個
slice、CI pending 不是完成。

## 已結束的共同基線

PR #143 啟動器、#144 研究準備與 #145 RAG／直接手測修理已合併；
本輪起始 main 為 `8636a754`，實際 Git／PR 擁有版本事實，不重做舊候選／手測。
#145 包含 Assistant preprocess 回應性、首次 data split receipt stale 與 Visualization
publication 修理。舊 81-case 證據仍有原先 bounded 限制，不是本研究 Pilot 成績。
Split WIP 已依使用者批准刪除，不能再列為待保留分支；主工作區本機設定、資料、
必要歷史證據與共用環境保留。

## 歷史 — 前期第二主線研究里程碑（M1 核對、M2 與 M3）

2026-09-19 使用者確認先備妥完整計畫與里程碑，完成題庫及系統前置驗證，再進入 pilot。
本節保存前期 Pilot 的歷史安排，不再派工；新版初始基準的結果見 Current，
後續候選以上方 Future 為準。[Assistant 研究與實驗規格](../validation/thesis_protocol.md)
擁有目前題數、模型、計分、實驗條件、預算與證據契約。

- **起始問題與證據**：已累積方法決策，但逐項討論缺乏整體交付順序；研究規格第 7 節當時明列
  正式題庫、五模型 runner 與完整 outcome／報告接合未完成。舊 calibration 不是新實驗就緒證據。
- **Outcome**：以 M0–M6 串起計畫、題庫、系統、pilot、改善、選版與結果；每階段有可核對出口，
  不用「系統應該沒問題」或完成一個小切片代替整階段完成。
- **目前位置**：M1／M2 與 M3 Pilot 已完成；非 Test 題庫、fixture、五模型 runner、真實 outcome、
  report 與 B0 還原均有 exact-source 證據。Test 仍由使用者封存，本輪未讀取。
- **下一步**：M4 Development 仍是 candidate；先由使用者確認有限改善範圍與速度目標，再施工。
  未定的正式 Validation／Test 細節仍於原決策時點處理，不提前解封或以 Pilot 選正式冠軍。
- **已完成 scope／non-goals**：以上方已授權範圍及明確三模型下載批准為準；不包括代接受新模型條款、
  任意產品契約／可見 UI 改動、正式 Validation／Test 或 M4–M6。封存 Test 不讀。
- **本次完成條件**：Pilot 報告與改善前基線封存／還原驗證；不是只交付文件，
  也不因此宣稱 M4–M6 完成或產品 handoff-ready。

### 完整里程碑與依賴

依賴順序：**M0 → M1 與 M2 平行準備 → 兩者皆通過 → M3 → M4 → M5 → M6**。
平行指工作安排；獨立且有益的 agent 分工依 repo 規則，GPU 排程與背景長跑仍受本輪預算／隔離限制。

| 里程碑 | 交付物 | 驗收與下一階段入口 | 主要分工 |
| --- | --- | --- | --- |
| M0 研究／施工計畫定稿 | 研究問題、已確認規則、題目模板、準備工作範圍、資源方案及待定項時點 | M1／M2 不存在會阻擋施工的契約／授權缺口；後續決策有 owner 和截止階段，不要求先猜實測值 | Agent 整理整包建議；使用者核對研究意圖與授權 |
| M1 題庫準備 | 規格第 3 節的完整題庫、oracle、初始狀態、family／split 清單及封存資料 | 題數與分組符合規格、可判分、語意經審查；Test 由使用者封存，開發端沒有讀取權 | 使用者負責人工內容與 Test；agent 協助非 Test 模板、改寫、檢查 |
| M2 系統與評測工具就緒 | 可用的五模型接入、單一入口、真實觀測、scorer、結果目錄、失敗與續跑處理 | 已知正反例及代表性端到端路徑通過；紀錄／計時／分母可核對；必要安全檢查通過 | Agent 實作與 focused 驗證；使用者處理必要模型授權及適用的集中驗收 |
| M3 Pilot | 規格第 6 節的小規模真模型試跑、問題分類、成本與可行性報告 | M1／M2 均通過才開跑；可區分模型錯誤、產品故障與無效測量，能據以確認 M4–M6 預算 | Agent 執行／整理；使用者集中確認成本、速度目標與必要調整 |
| M4 Development | 保存的 B0、有限改善方案、B1／B2 候選及同題比較 | 規格第 6 節的中止與進入 Validation 清單通過；不以分數完美為出口 | Agent 推進已授權方案；使用者只處理契約、範圍或超預算決策 |
| M5 Validation 與凍結 | 固定候選的比較、選版理由、人工 scorer 核對與 Test 配置 | 選版規則先固定，評分可信；選定系統、B0、適用消融與分析方式凍結後才解封 Test | Agent 執行與整理；使用者人工核對、確認凍結並提供封存 Test |
| M6 Test 與論文結果 | 完整逐題結果、人工核對、表圖、失敗分析、限制與重現附件 | 承諾條件結果完整且無未解釋排除；每項論文主張能連到證據，不要求正向結果 | Agent 整理證據與結果草稿；使用者核對解釋與論文表述 |

### M1：先完成題目，不拿 pilot 代替出題

1. Agent 先提出工具／情境覆蓋表與一份共用題目模板：題號、family、split、使用者輸入、
   初始狀態、可用工具、允許的答案／參數、禁止副作用、預期觀測層與 fixture 身分。
   先以少量非 Test 人工題驗證模板與 oracle 可表達需求，再大量填題；不擴張工具契約。
2. 使用者協調自己／受邀者提供人工 seeds／改寫與語意核對；agent 先提供模板與格式檢查，
   Dev／Validation 的 AI 改寫須另行確認，不替代人工作者生成「全人工 Test」。
   先分 family 再改寫，不能事後隨機切分。
3. 正式題庫全數完成後核對語意、標準答案、數量與重複風險。Validation 不用來修產品或調 prompt；
   對其題目格式的必要準備不等於允許先看模型結果。Pilot 只抽已準備好的 Development 題目。
4. Test 由使用者在隔離位置完成審查與封存；agent 可提供本機檢查工具供使用者執行，
   只接收數量、版本／hash 與審查狀態，不接收題文、oracle、含題文 log 或實驗前的 Test 軌跡。
   這不能冒稱 agent 已獨立審過 Test 語意；單人出題／評分限制照實保留。

### M2：確認可測量與可運作，不要求模型先很準

#### M0 source 核對與 M2 最小準備範圍

以下為既有 source 接點盤點，不是 runtime 通過證據；施工權限以上方 active scope 為準：

| 現有接點 | 可重用部分 | M2 必須補齊／確認 |
| --- | --- | --- |
| `llm/action_contracts.py`、tools definitions、核准 target | 18 工具、schema、既有 owner 與確認／結果契約 | 逐工具情境與可觀測結果對應，不新增第二套 readiness |
| `scripts/dev/assistant_benchmark_calibration.py` | 真 parser／schema 的離線正反例模式 | 新研究 scorer 配合已確認的缺資訊不執行與 GUI 交接分層；不改寫舊 calibration 的歷史成績 |
| `scripts/dev/run_stable_assistant_model_eval.py` | 保存設定／模型輸出及既有評估接點 | 舊 runner 綁定 primary 與 frozen cases，會攔截工具執行；不能直接當五模型真實 outcome runner |
| `llm/core/backends/local.py` prompt capture | 實際 prompt、raw output、metadata | 接上 case／repeat／修復與事件因果鏈，完整報告不是單次 capture 就有 |
| 正常 ChatPanel／Host／ApplicationService 與既有 walkthrough | 真實操作、UI、狀態與確認 owner | 研究 fixture 下的觀測、隔離／重置與結果收集，不複製命令執行責任 |
| 產品 model allow-list／runtime | 既有兩個 Granite 的受控產品載入 | 五模型研究接入與其餘三模型精確 revision／相容性另設有界研究配置；不默默擴張產品 Settings 或關閉 allow-list |

直接相關差異在準備開始時須核對：`pipeline_state.py` 的 preprocessed 工具清單目前未列
`select_channels`，而核准 target 的 stage 說明允許它；先確認實際 publication，不能用文件
假定該情境可執行。此為 M2 覆蓋／修理候選，不在本次文件工作順手改產品；若只需研究先選
已一致的合法情境，不把未測的情境冒稱已通過。

研究 fixture 建議從可重現的合法資料狀態建立，分為空工作區、有資料／預處理、epochs、
設定完成、執行中及完成 run；用現有服務建構、在案例間重置，不讓前題副作用影響下題。
Agent 負責 fixture 與機器欄位；使用者不用手填 publication、generation token 或內部 ID。
Synthetic fixture 適合工程驗證，但真實產品 outcome 必須另外取得適用的真實來源與 Windows
原生 UI 證據；不新下載整套資料集，也不把模擬訓練終態或預寫 JSON 當成實際運算。

本輪不擴張 GUI、模型產品清單、公開工具或一般對話功能；研究所需的接入、紀錄、scorer 與
直接必要缺陷已納入上方有限授權，產品契約或可見 UI 改變仍另作決策。只做單回合主分數的提案，不等於允許省略取消／狀態一致性測試。
模型精確來源、大小／VRAM、既有 cache 與可寫輸出位置須在下載前唯讀盤點，交付一份資源方案；
目前沒有選定新儲存目錄、下載模型、刪 cache、安裝環境或新增正式 CLI。

#### 本輪已授權的實作順序

施工前重新讀 Git／source，沿用既有 Command、模型載入與 prompt capture 能力；
每個直接必要 slice 補上 call sites、具體驗證命令與回退邊界，不在文件中發明尚不存在的 CLI。

1. 先接題目格式、oracle 與 scorer 的正反例，涵蓋選對／選錯、參數錯、缺資訊、No-call、
   Host 擋住錯誤但模型仍判錯等情況；確認讀取錯誤能被辨識，而不是靜默漏題。
2. 接正常 Assistant／Host／Command 觀測路徑，使用研究 fixture 核對操作、GUI 交接、
   前後狀態、確認／取消與必要失敗路徑；不以攔截執行或捏造 UI 終態當作產品成功。
3. 補單一入口的選一／多個／全部條件、逐次輸出、計時、修復預算、失敗分類與彙整。
   驗證中斷不遺失已存證據、續跑不覆寫、不重送終態不明操作、設定不一致不混入同一 run。
4. 經資源與授權確認後，五模型分別做載入／固定暖機／少量非 Test smoke check；
   固定精確 revision／模板／runtime／生成設定，核對 RAG on 真有檢索、off 不檢索。
   不相容或 OOM 明列 blocker，不換模型冒充通過；不要求 smoke check 決策全部正確。
5. 以同一份保存軌跡核對輸入、raw output、事件、決策分數、產品 outcome 與時間；
   已知 parser／scorer、取消／安全、漏記／誤計時問題須修到能判斷結果，才可進入 pilot。

此處「系統就緒」只涵蓋研究所需的可運作／可測量能力與必要安全保護，不是全產品零缺陷。
UI 或公開工具契約變更仍須明確確認；需要產品 handoff 時遵守既有 workflow，不為每次純評測
改動都要求 GUI 手測。真模型 smoke check 也須有預先列明的有限案例與資源預算。

### M3–M6：用證據推進，不以分數好看才結束

- **Pilot 前保存基線**：M2 就緒時保存可追溯的準備版本。Pilot 若暴露須修的產品／配置問題，
  留下前後版本與原因；M4 第一個改善方案前固定可重跑的 B0，不事後拿新版冒充改善前基線。
- **Pilot 出口**：交付每模型／條件的可行性、測量缺陷、延遲／修復／失敗分布與成本估計。
  成本須含載入、操作、重試及實際排程開銷，不只用最快題估計整場。超預算或量測仍壞即為
  checkpoint，提出有範圍的修正／調整，不暗中把剩餘矩陣跑完。
- **Development 出口**：按既定輪數／方案預算與規格 gate 執行。五模型比較不能變成無限調參；
  未授權且無關的產品／架構問題列為後續，不阻擋已能可信測量的本輪研究。
- **Validation 入口與出口**：看結果前固定候選、共同預算、速度門檻、相近判準、統計與安全規則。
  使用保存軌跡做人工作業；若 scorer 有缺陷，一致重評受影響紀錄，不挑有利版本。
  完成選版與凍結後，不再依 Validation 追加改善方案。
- **Test 出口**：只跑規格批准的完整系統、適用消融與同模型 B0；原始軌跡可追到圖表。
  低分、負面消融或 B0 較好都照實報告，不據此重新選版／調參後混入同一獨立 Test。
  人工抽查、剩餘缺失與論文限制齊全，才宣稱本階段結果完成。

### 集中決策時點與分工

| 最晚決定時點 | 集中核對的內容 | 處理方式 |
| --- | --- | --- |
| M1／M2 開始前 | 研究問題表述、題目模板／覆蓋、fixture 與操作層範圍、實作／模型資源授權；多輪是否納入 | Agent 提供一包建議，使用者確認範圍；未批准的多輪數量不默認施工 |
| M3 開始前 | M1／M2 通過證據、精確五模型配置、pilot 題目清單／順序、smoke 與 pilot 資源範圍、輸出位置 | 不需要先決定最終模型贏家；不使用 Validation／Test 做 pilot |
| M3 完成後、M4 開始前 | 實測成本、剩餘人力、改善預算／截止日期、必要的技術配置調整 | 維持既定上限；需變更研究預算或範圍時一次確認，不自行延長 |
| M5 開始前 | 最終 Validation 矩陣、P95 門檻、相近／較簡單判準、統計算法與人工抽樣細則 | Agent 依 pilot／Dev 提出完整預設方案，使用者集中核對；不得看 Validation 後挑規則 |
| M6 解封前 | 選定系統、B0、適用消融、精確 source／設定／題庫／scorer 身分與執行清單 | 核對既定方法已落實，不再新增研究問題或依 Test 選有利分析 |

使用者協調自己／受邀者的人工出題，負責 Test 封存、必要條款與研究取捨、約定的人工核對及真正產品驗收；
agent 負責模板、非 Test 輔助工作、直接必要實作／驗證、紀錄與報告整理。
檔名、內部欄位、輸出排版等在既有契約內由 agent 提供一致預設，不逐項打斷使用者；
新下載、外部分享、破壞性清理、可見 UI／工具契約與實質預算擴張仍不是默認授權。

### 時程、風險與跨 context 接續

- 研究規格中的結果目標日與暫定改善截止日保留，但**尚無可行性證據，不是完成保證**。
  M1 要先完成整套題庫，受邀出題者及審查分工尚待確認；機器平行不能抵銷此人力依賴。
- M1 初批人工題完成後記錄實際出題／核對時間，估算剩餘工作；M2 盤點模型授權與接入缺口，
  M3 才有正式機器成本。據此在同一計畫排定可承諾的時程，不先替每個 milestone 填虛構日期。
- 若日期、完整題庫與可投入人力互相衝突，集中提出調日期／範圍的選項；不得縮題、改成 AI Test、
  降低驗證或自動增加人工負擔來假裝準時。未取得模型存取權也不能偷偷替代五模型。
- 每個 milestone 以具體交付與 gate 狀態回報；目前進度由上方 active 節擁有，
  文件更新不等於已通過題庫／runtime gate。施工只在已批准 scope 內持續，
  context compaction 或完成小切片不是停止或新授權的理由。
- 接手先讀上方 active、本節、研究規格、Git 與可辨識的執行狀態，再續作當前已授權項目；
  在 active 節更新進度、下一步與 blocker，不建立第二份工作日誌／控制平台。

下方是既有產品優先順序與候選背景，不覆蓋本輪授權至 Pilot 的範圍，也不授權本線施工其他候選。

## Historical order — Import UI → Assistant evaluator → cleanup/refactoring

以下為2026-09-16的順序與候選背景，不是目前狀態或派工入口；最新授權以上方Active為準。

使用者於 2026-09-16 指定以上順序；Preprocess panel 暫不作為下一個優先施工項目。
Import 白框修正已於 2026-09-16 完成 Windows 局部手測，使用者回覆「沒問題了可以準備合併」。
接受的產品 source 為 `b052fd75`，與修正 commit `d0a8b435` 的產品內容相同；接受範圍見
[Current](../current.md)。PR／CI／合併狀態以 GitHub 與 Git 為準，不重啟已完成的修理。
使用者批准的 Benchmark 第一輪已有離線 calibration 實作，能力與限制見下節；
其餘 UI 改版、Assistant runtime repair 與重構尚未開始。

本輪要讓匯入操作更清楚、Assistant 評測結果可信，再依具體問題繼續降低程式複雜度。
不以籠統的「架構已乾淨」、行數下降或總分提高作為完成證明。

### 1. Import UI：後續調整先確認範圍

- 已接受的白框修正不再是 active slice；原生 first-frame 與 transient-window 回歸留在測試。
  修理／失敗／逐幀證據與合併批准隨該修正 PR 保留，不把施工日誌留作後續 dispatch。
- **待確認**：使用者實際想調整的步驟、畫面、文案與互動；先看目前 UI／截圖並列出問題，
  不預先認定整個 wizard 都要重做。
- **邊界**：以已合併的匯入能力為基準，保留 reviewed labels、無標籤選擇、subject/run 選取、
  確認與取消、資料一致性保護。支援格式或 EEG 語意改變必須另作決策。
- **施工前**：將確認過的可見變更、預期行為、非目標、既有 owner、驗證與回退方式寫回本節。
  沿用共用 Windows 環境與 PowerShell log 先提供 PR 前局部預覽；不把 PR／CI 當作開啟本機
  預覽的前置條件，也不把預覽通過當作正式 CI 或合併批准。後續具體 UI 變更仍待確認。
- **完成條件**：已同意的 UI 問題有實際 diff 與正常／失敗／取消路徑證據，Import 既有能力
  無回歸；同版本適用 CI、跨來源資料及 Windows native 畫面／操作檢查通過，再集中一次手測。
  不要求使用者重測全部 134 個資料集，也不把既有自動匯入證據當作新 UI 的驗收。

### 2. Assistant evaluator：先確認評測器是否判得準

- **本輪 scope-complete**：三決策／三層離線 calibration、合成正反例及 focused regression
  已完成；契約、入口與 claim boundary 見
  [Benchmark calibration](../validation/assistant_benchmark_calibration.md)。這不是整體 Benchmark
  完成，也未執行真模型或證明產品成功率。舊 evaluator、81 cases 與 gates 不變；Git／CI／合併
  狀態仍從實際 repository 取得，不因本機驗證通過宣稱已合併或 handoff-ready。
- **下一個候選**：正常 ChatPanel → Host → Command 路徑的真實 observation 收集與 scorer
  對照，先確認少量場景、來源與資源預算，再補齊 active plan；不自動啟動模型／prompt／RAG 改動。
  人工 seeds、family 隔離、Validation／Sealed 管理與同軌跡獨立人工評分仍未實作。
  正式研究已確認依產品完成契約區分「開窗」與「完成操作」；詳見研究規格。
  舊合成 calibration 不因此成為真實 GUI outcome 證據。
- **診斷順序**：由少量可重現案例核對輸入、預期行為、raw output、解析／admission、confirmation、
  command 執行、verification 與評分結果，分開 evaluator 誤判、模型行為錯誤與產品執行錯誤。
- **修理邊界**：先固定預期行為與判分規則，再修理有證據的案例／scorer／runner 問題；
  重用既有 Command truth 與驗證入口，不讓 evaluator 建立另一套 readiness 或假成功。
  工具名稱、參數、確認及可見結果等產品契約變更仍須另外確認。
- **證據品質**：選取與已知誤判直接相關的正確、錯誤及必要邊界案例；明列分母、失敗、skip、
  runner／scorer 及模型版本。舊 frozen 結果保持原身分；若判分規則需改，先批准、版本化並說明差異，
  不暗改舊分數、不刪失敗案例充當進步。必要的真模型執行先固定案例與資源預算。
- **後續整階段完成條件**：可重現的誤判已修正，已知正／反例能被正確區分，有實際執行證據與獨立檢查，
  並清楚列出仍屬 Assistant 本體的問題。Evaluator 可靠不等於 Assistant 已達 Stable。
  若未發現 evaluator 缺陷，記錄判分依據與真正問題，不為了這個階段而強行修改。
  若只改測試／評分工具且沒有產品行為變更，不另要求 GUI 手測。

### 3. 清理與重構：按已確認的模組問題施工

- 完成前兩階段後，依實際 diff、reachable callers 與 reviewer findings 決定第一個模組，
  不現在先宣告整個核心都要重寫，也不重新執行已結束的全面匯入盤點。
- 每個模組明列責任、入口、測試保護與刪除／保留理由；優先刪除確認未使用的能力與專屬測試，
  合併重複政策與狀態。大型檔案依責任處理，不以搬檔或降低單檔行數冒充改善。
- Production、tests 與 scripts 一起看；mock-heavy 測試是否移除須有更可靠的替代證據。
  檢查不必要的資料複製、重複掃描及等待，但不先承諾大幅加速。
- **完成條件**：通過 reviewer 對本次責任邊界、回歸風險、測試有效性及複雜度的審查，
  已承諾項目與必要驗證齊全，才交付整合版本；不以做完一個切片當作整階段完成。
  無關發現列為後續候選，不無限擴張本輪。

### 節奏與跨輪延續

本文件是唯一 active plan；每階段開始前補齊具體 scope／假設／驗證／stop condition，施工中更新
next step 與 blocker。小 commit 用於回退，review 依模組與風險安排，不因每個小切片就要求手測／merge。
有產品可見變更時，在同意的完整範圍驗證完成後集中手測；真正需要新決策或授權時明確停在該邊界。
Context compaction 不是完成條件：接手先讀本節、Git 與執行狀態，再繼續已授權的下一步。
優先順序不是全部實作的預先授權；也不自動啟動下方獨立的 Assistant runtime repair 候選。

## Closed baseline

Quality-baseline closure was accepted and merged via
[PR #140](https://github.com/hxin-an/XBrainLab/pull/140). Its implementation/evidence history stays in
Git/PR, not active dispatch. Known Assistant limitations below remain deferred.

Retained import was manually accepted and merged through
[PR #141](https://github.com/hxin-an/XBrainLab/pull/141) on 2026-09-16. Accepted source, bounded
coverage and known limitations belong to [Current](../current.md); required data/failure evidence
remains on E. The former task worktrees were removed; do not restart their completed campaigns.

## Deferred candidate — Assistant runtime reliability (not evaluator scope)

Goal: reliable selection and parameter-collection continuity with no unexpected workflow side effects.
LOC, static pass, literal prompt assertions or one improved score are not completion criteria.

1. **Mechanism audit before choosing a fix.** Trace baseline/retained failures from full rendered input/
   RAG through raw output, parser, capability/provenance, typed receipt, GUI terminal and visible response.
   Separate intent errors, missing clarification fields, invalid/stale admission and evaluator assumptions.
   Reproduce a bounded set through normal ChatPanel with real execution, using no patient data.
   No Host intent guessing or new model experiments in this diagnostic phase.
2. **Approve a repair boundary.** Select one evidence-backed hypothesis and existing owner. Explicitly
   decide behavior for unspecified/multiple actions, missing/partial values, correction/cancel and
   unavailable tools. Tool/schema/confirmation/visible-flow or model/RAG changes require separate
   approval; current source/tests do not ratify target. A larger model is neither proven necessary nor
   authorized. No generic evaluator platform, control plane or parallel state owner.
3. **Separate development and acceptance.** Keep frozen 81/scorer unchanged as regression evidence.
   Before implementation, define supplementary development cases and disjoint reviewer-owned holdout
   by failure family. Never tune on the holdout or shrink its denominator; disclose prior exposure to
   frozen cases. Reuse existing runners, review any necessary bounded extension, and agree a candidate/
   resource budget before execution. Do not repeatedly add two more prompt attempts after failure.
4. **Implement/review one coherent repair.** Prefer deletion/reuse; test failing observable behavior
   through actual owners, then passing behavior. Mock external inference only in unit tests; real-model/
   native evidence cannot substitute fake generation or preapproved GUI terminals. Independent reviewer
   checks mechanism, meaningful tests, complexity and scope, not only summary.
5. **One integrated acceptance.** Require 36/36 positive, 10/10 explicit origin, 5/5 missing guards,
   5/5 direct clarification admission, 24/24 product no-action and 7/7 clarification. Holdout must show
   zero unexpected execution/confirmation/navigation/mutation and correct authorized continuations.
   Separate raw-model/Host/product outcomes. Then same-source normal ChatPanel→GUI→Command journey,
   relevant cancel/stale cleanup, applicable CI and one final Windows GUI/English Assistant acceptance.
   No Stable/generalized-safety claim from bounded cases alone. Unsupported mechanism or exhausted
   budget means a documented decision checkpoint, not weaker gates or automatic extra prompt edits.

This runtime repair proposal is separate from the evaluator phase above; its promotion criteria do not
automatically become evaluator-repair gates or authorize product/model changes.
New implementation begins only after diagnostic outcome, scope and budget are approved.

其他候選方向見 [Roadmap](roadmap.md)；不宣稱 Assistant Stable 或零缺陷。
