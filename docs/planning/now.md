# XBrainLab Now

最後更新：`2026-08-20`

## 目前焦點

在已合併的 `v0.7.0` cleanup baseline 上，確認真實 EEG loader 仍在執行時取消 Import 是否會造成
native lifecycle 崩潰。此 slice 只處理一個 owner boundary：取消後不得提交部分資料、不得讓晚到
callback 重開已關閉視窗，且同一來源必須可重新 Import 成功；不在同一 branch 重構 Load Data 或調整
Import GUI。若真實 loader 證據已通過，就不為無法重現的 defect 增加 production code。

目前 phase：`Checkpoint — native-loader cancellation evidence complete`

## 問題與證據

- `v0.7.0` 已於 `2026-08-20` 從 `main` merge commit
  `e84ac035ba013e6db1165661aae46e60b17ccac2` 建立 annotated tag 與 GitHub Release；PR #40、40/40
  exact-source local handoff、main documentation 與 main CI attempt 2 均通過。第一次 main CI attempt 的
  `tests/unit/ui/components` 在 hosted runner 31% 後無 terminal，於每-shard 1,200 秒 timeout；同一 source
  的 PR run、本地 focused lifecycle tests與rerun均通過，因此記為待量測的 validation lifecycle finding，
  不作產品回歸或已修復宣稱。
- Repository 仍保留無 caller 的 legacy Assistant benchmark／capture／debug artifacts，以及已退出 active
  roadmap但仍有 package、CLI、capture、tests、guidance 與 schema projection 的 MCP compatibility surface。
- 最近 exact-source handoff 約 74 分鐘：逐 gate full-source rehash 約 14 分鐘、handoff dashboard 重跑約
  10 分鐘、Data Import wizard capture 約 8 分鐘，是先行可移除的重複成本；complete regression與各
  focused gate的不同 outcome／claim contract仍須保留。
- Root `settings.json` 是使用者本機 runtime 設定，已修改但不屬於 release tree；全程不得 stage、commit、
  revert、覆寫或隱藏。
- Cleanup PR #41 exact head `8bb8599b` 已於 `2026-08-20` 依使用者手測批准，以 merge commit
  `19d866f7796412f5cb23f0148449d61bd8fa9420` 合入 `main`；42/42 handoff gates 與所有 applicable
  remote checks 均成功。新修復從該 merge commit 建立 `fix/import-cancel-native-loader-v1`。
- 現有 offscreen BIDS Apply cancellation 證據能驗證 cancelled terminal、authoritative state 不變、同一
  review 重開與 retry 成功，但取消中的第一次 raw load 使用 in-memory Raw 替身，沒有覆蓋真實 MNE／
  BrainVision loader 正在 I/O 時的取消與晚到 Qt delivery。使用者已實際遇到 Import Cancel 崩潰，因此
  此缺口是本 slice 的 red-first reproduction target。
- Exact branch source 已以兩條低 mock Qt integration 路徑補上真實 loader 證據：BIDS Apply 取消後仍
  執行原始 MNE／BrainVision loader，單檔 review 取消後仍執行原始 MNE／EDF loader；兩者均得到 typed
  cancelled terminal、registry drainage、authoritative state 不變、無晚到 wizard，且同來源 retry 正式
  Apply 成功。兩項 focused tests 分別約 13 秒與 6 秒，沒有 native abort，故目前沒有 production red test。

## Observable outcome

1. 真實 loader 在 owned operation active 期間收到 Cancel，不會 native abort、閃退或留下無 owner worker。
2. Cancelled operation 只發布一次 typed cancelled terminal；raw data、interpretation review、publication 與
   pipeline state 保持取消前 truth，不產生部分 commit。
3. MainWindow 或 Import UI 關閉後，晚到 loader／review callback 不得重新顯示 dialog 或觸碰 quiescing
   widget。
4. 取消後重新開啟 Import，使用同一來源能重新得到 review 並完成一次正式 Apply。
5. 修復完成於單一 exact branch head；focused native-loader cancellation evidence、directly related lifecycle
   tests、source-diverse data gate、canonical handoff 與 remote CI 通過後，提供使用者一條
   Cancel→retry 手測流程。

## Scope／non-goals

- In scope：真實 public EEG 來源的一次 native loader cancellation、operation registry drainage、state
  rollback／non-commit、late-callback suppression 與 same-source retry。
- Non-goals：不改 file／folder／BIDS 分類、不改 label／event 語意、不改五步 wizard layout／copy、不做
  Load Data module refactor、不處理 Stop Training、不增加通用 cancellation framework。
- ApplicationService／OwnedWorkRegistry 與既有 Data Interpretation transaction 仍是唯一 authoritative
  owners；不新增 state、receipt、compatibility path 或第二套 error semantics。
- 此 slice 預期不需修改 `XBrainLab/ui/` 或可見 layout／文案。若根因要求可見 UI change，先停止並取得
  新的明確 UI 授權；既有對後續 source-classification UX 的授權不自動擴張到本 bug。

## 施工順序

### A. v0.7.0 release closure（completed）

1. 固定本頁與 release truth，確認產品 diff 只包含使用者已測內容。
2. 跑版本契約、ChatPanel focused regression、Ruff／format、MkDocs；commit 時明確排除 `settings.json`。
3. Push exact head，將 PR #40 retarget 到 `main`，記錄 `2026-08-20` manual acceptance、範圍與 exact SHA。
4. 在 clean/explained exact head 跑 canonical handoff workflow並驗證 dossier；同時等待 PR checks，任一
   missing／pending／stale／cancelled／failed 都 fail closed。
5. 以 merge commit 合併，確認 `main` post-merge checks，再建立／push `v0.7.0` tag與GitHub Release。

Checkpoint（`2026-08-20`）：exact `95949fc4` 的212項focused tests、Ruff、format與MkDocs已通過，
PR #40也已retarget到`main`；fresh CI隨後以三個直接相關的stale／platform oracle fail closed。Linux
unit UI仍要求已核准刪除的stage-specific首頁copy；Linux human-like capture的quality review也仍把同一
stage-specific copy matrix當必要契約，儘管chat geometry、runtime、signal、interaction等子項全PASS；
macOS則因QTextBrowser整數寬14px減浮點glyph寬11.625px為2.375，讓直接`<=2.0`的subpixel assertion
誤判。這三項只校正tests／validation script到已批准fixed onboarding與integer-pixel contract，不修改
`XBrainLab/ui/`或其他產品source。舊SHA canonical handoff在complete-regression中被主agent終止，因任何
修正都會使該dossier失效；新commit必須從頭重建。

Completion（`2026-08-20`）：PR #40以merge commit `e84ac035`合入`main`；main CI第一次只因Linux UI
components shard的hosted-runner timeout失敗，未改source的failed-job rerun與dependent Full Test Suite
均成功。Annotated tag與GitHub Release `v0.7.0`已發布；cleanup branch
`refactor/repo-cleanup-validation-speed-v1`從該tag建立。

### B. 單一 cleanup branch

1. 從 tagged `main` 建立一條短期 cleanup branch；先量測 current inventory與 baseline，不碰產品 UI。
2. 以 caller inventory 為刪除 gate，先移除無外部 caller 的 legacy benchmark、pipeline-chain capture、
   orphan debug JSON／lazy-import script與其專屬測試；每個 family 一個可回退 commit。
3. 完整退役 MCP adapter/package、CLI/config/capture、tests與repo-local skill；保留 ApplicationService command
   spine和必要 settings migration，只留不具執行面的歷史 tombstone。這是已取得使用者明確決策的 public
   surface removal，不恢復任何替代 compatibility path。
4. 加速 canonical handoff：先用一次 global immutable source barrier取代每 gate 前後全樹 rehash；再讓
   handoff dashboard消費前序 manifest evidence而不重跑相同測試；最後把Data Import capture按五個
   scenario family批次隔離。每步保留fail-closed identity／artifact contract並以實測前後時間驗證。
5. 只有前述穩定後才考慮固定 lane schedule；不建立通用 scheduler。Qt、GPU、RAG與public fixture的共享
   cache／process boundary按既有owner序列化。
6. 清理完成後跑同一 exact source 的完整 handoff、remote CI、artifact抽查與手測 walkthrough；停在
   `handoff-ready` 候選交使用者真人測試。使用者再次明確通過前不合併cleanup PR。

Checkpoint（`2026-08-20`，dead developer surfaces）：caller inventory確認legacy Assistant benchmark、
pipeline-chain capture、tool-eval dashboard、兩份orphan debug JSON與lazy-import script只有自身CLI／專屬
tests，沒有production consumer。已移除這些surface與`benchmark-llm` entry point，共淨刪11,441行、
`XBrainLab/` production 0行；刪除前後相同338項Assistant／walkthrough／runner／architecture tests、
architecture compliance及Ruff check／format均通過。

Checkpoint（`2026-08-20`，MCP retirement）：已移除MCP stdio／HTTP package、job/session transport、
`mcp_tool_specs`、`--mcp-tools`、client config/capture/launch scripts、runner gate、tests、architecture例外與
repo-local skill；ApplicationService automation command schemas／payload execution仍是唯一headless command
spine。Owner由2個transport/session owners降為0，`XBrainLab/` production淨刪1,036行、無新增owner。
Retained command／guidance／runner／architecture／diagnostics focused集合637項、3項retirement guards、
architecture compliance、guidance audit、Ruff check／format與MkDocs strict均通過。

Checkpoint（`2026-08-20`，source barrier）：canonical manifest現在只在開始與最終驗證各做一次完整
source-byte fingerprint；每個gate仍在命令前後重新檢查branch／HEAD／tree／dirty paths／upstream，任何
source mutation會立即使該gate失敗，最終dossier再以完整fingerprint fail closed。相同worktree量測完整
fingerprint為9.510秒、輕量guard中位數1.412秒；52項recorder／manifest tests（含命令修改source的反例）、
Ruff與basedpyright均通過。此切片不平行化gate、不減少gate或OutcomePolicy。

Checkpoint（`2026-08-20`，dashboard deduplication）：handoff dashboard已改為驗證並摘要同一dossier內
所有前序gate records，不再重跑Ruff／type／architecture／UI／IO／public-data commands；final recorder
仍逐record重驗command、environment、logs、artifacts與source。原dashboard獨有的真`run.py` startup與七張
approved-reference visual baseline已升為兩個正式GateSpec，實跑分別PASS；visual baseline最大mean diff
0.025、changed ratio 0.04%。fast／full日常dashboard不變，handoff report明記`executed_check_ids=[]`與
`source_of_truth=handoff gate records`。

Checkpoint（`2026-08-20`，Data Import capture batching）：十二張canonical wizard frames依choose/review
metadata、many-label、match-label、review/import四個family隔離，四張placement modes為第五個family；每個
family仍使用fresh Python／Qt／Xvfb，family內每個dialog仍close、`deleteLater`並flush deferred deletes。
完整16張capture由477.814秒降至215.94秒，獨立`--validate-only`與manifest／hash inventory通過；外層
冗餘`xvfb-run`已移除，staging／atomic publish／source identity契約不變。

Checkpoint（`2026-08-20`，complete regression fixed phases）：原本單一序列`run_tests.py all`已改為
固定兩階段執行canonical八個Linux CI groups；第一階段五個unit groups完成後，第二階段才執行三個
integration／regression groups，每階段最多兩個worker。各group使用獨立coverage file與證據路徑，pytest
暫存仍位於Linux原生`/dev/shm`以保留mtime、symlink、permission與logger語意；沒有建立通用scheduler或
改變group argv／OutcomePolicy。Exact commit `4aeca591`實跑11,290項，11,282 passed、8個既有允許skip、
0 failed／error／xfail／xpass／deselected，八份attestation、八份log與八份coverage均存在；總時間
1,327.47秒（22分07秒），相較舊complete-regression 1,527.20秒縮短約3分20秒。

Checkpoint（`2026-08-20`，first full cleanup handoff）：exact pushed commit `1ea8051a` 的42/42 gates與
final dossier verification全部PASS；完整regression為1,345.364秒，Data Import capture為217.527秒，
handoff dashboard僅8.070秒，新增startup與visual baseline分別25.530與38.316秒。從第一個gate開始到
dashboard完成約45分37秒，已較舊74分11秒縮短約28分34秒，但尚未達成不超過40分鐘的stop condition，
因此仍是checkpoint。固定、checked-in的post-regression lanes已實作：完整regression前仍序列fail-fast；
public fixture fetch／verify完成後，才讓單一offscreen Qt lane、單一Xvfb capture lane、單一GPU/model lane
與單一public-data lane並行，各lane內保持原gate順序與cache/process ownership；並行gate只產生經驗證的
deferred records，完成後才依registry order序列寫入dossier，再執行dashboard與final source/dossier驗證。
沒有建立通用scheduler、沒有讓多個gate競寫dossier，也未縮減gate／artifact／OutcomePolicy；任一lane
failure或source drift都使整體失敗，不能以其他lane成功補足。目前待同一clean／pushed exact source重跑
42-gate handoff，只有總時間不超過40分鐘且final dossier通過才可升為candidate。

Completion（`2026-08-20`）：exact `8bb8599b` 的 42/42 gates、11,294 項 complete regression 與 final
dossier 全部 PASS，總 wall time 2,226.162 秒（37 分 06 秒）；所有 applicable PR checks 成功。使用者手測
通過後，PR #41 以 merge commit `19d866f7` 合入 `main`。40 分鐘仍是 full handoff 硬門檻，30 分鐘只作
後續 test-quality cleanup 的 stretch goal；日常修復不重跑完整 manifest。

### C. Import Cancel native-loader evidence（checkpoint complete）

1. 從 main merge `19d866f7` 確認既有 file／folder／BIDS routing 與 offscreen cancellation baseline，
   不改產品。
2. 新增最小 red reproduction：真實 public EEG loader 已進入 I/O／materialization 後取消 owned operation，
   驗證 native process 存活、typed cancelled terminal、registry drainage、state 不變、no late dialog 與
   retry 成功。
3. 追蹤 cancel owner、loader checkpoint、transaction commit guard 及 Qt callback token；只修第一個被 red
   test 證明違反的 boundary，重用既有 owner，不建立通用抽象。
4. 用相同 red test 轉 green，再跑直接相鄰的 BIDS cancel/reopen、ApplicationService owned-work、dialog
   close 與 public source-diverse import evidence。
5. 完整 candidate 才跑 canonical handoff 與 remote CI，產生一條真實 Cancel→reopen→retry 手測指令；
   使用者明確通過前 PR 保持 draft 且不得 merge。

Checkpoint（`2026-08-20`）：既有 BIDS Apply cancel test 已移除 in-memory Raw 替身，取消後會完成原始
BrainVision loader，再驗證取消 operation、state non-commit、preserved review reopen 與 real retry；另新增
單檔 PhysioNet EDF 在 initial review loader active 時取消的完整路徑，驗證晚到真實 MNE read 不開 wizard、
registry 歸零、state 不變及同檔 retry 成功。兩項以 offscreen Qt、`prlimit --core=0` 和 timeout 實跑
2/2 PASS。因沒有可重現的 product failure，本 slice production `+0/-0/net 0 LOC`，不增加 cancellation
owner 或 compatibility path；若使用者 native 手測仍閃退，下一步需要該次 exact source、觸發階段與 native
terminal log，不能從 WSL X11 shutdown 推導產品修復。

## Focused validation 與 stop condition

- Red-first focused evidence 必須實際進入 native loader seam；只 patch 成 in-memory Raw 或只驗 button
  callback 不支持本修復 claim。
- 同一測試必須觀察 cancelled terminal、registry drainage、authoritative state 不變、late callback
  suppression 與 retry；若無法觀察其中一項，先改善 test seam 而非放寬 assertion。
- Native Qt／MNE 驗證使用 `prlimit --core=0` 與明確 timeout；只終止本 test 明確啟動的 PID。
- Focused green 後才依 `docs/validation/README.md` 選 directly related lifecycle 與 source-diverse evidence；
  完整 handoff 只在交使用者手測前執行，硬門檻 40 分鐘。
- 若 red test 顯示崩潰來自 WSL X server／使用者關閉 display，而產品 process／state 正常，停止產品修復並
  回報 environment boundary；不增加產品複雜度掩蓋環境問題。
- Scope-complete 需有 exact-source focused green；handoff-ready 另需 canonical dossier、remote CI 與手測
  指令。
