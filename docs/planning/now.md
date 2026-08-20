# XBrainLab Now

最後更新：`2026-08-20`

## 目前焦點

將使用者已在 `fix/assistant-direct-parameter-provenance-v1` 手測通過的 Local Assistant 初版封版為
`v0.7.0`，經同一 exact source 的 PR、CI 與 handoff evidence 合併到 `main`。封版期間不再改產品行為；
完成 release 後，才從乾淨 `main` 建立唯一的 cleanup branch，連續完成過時 Assistant／MCP surface
移除與驗證加速，直到下一個完整候選可交使用者手測才停。

目前 phase：`Active — repository cleanup and validation acceleration`

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

## Observable outcome

1. 將已手測的產品 bytes 與 release metadata commit 成單一 exact branch head；沒有額外 UI／Assistant 行為
   變更。
2. `pyproject.toml`、runtime fallback、changelog、README、current／architecture truth 一致指向 `0.7.0`，
   並只宣稱 bounded local Assistant baseline。
3. PR #40 精確改以 `main` 為 base；同一 head 的 applicable non-skipped checks 全部
   `completed/success`，canonical handoff dossier 對同一 clean/explained source 通過。
4. 使用 merge commit 合入 `main`；main post-merge checks 通過後建立 annotated tag 與 GitHub Release
   `v0.7.0`。
5. 從 tagged `main` 建立唯一 cleanup branch。該 branch 以短 coherent commits 完成清理與加速，最終一次
   產生完整候選與手測指令；中途 checkpoint 不要求使用者反覆手測，也不合併到 `main`。

## Scope／non-goals

- Release slice 只包含已手測產品 source、版本與 current truth；不新增功能、不調整 UI、不改 model、tool
  surface、dataset、training 或 scientific behavior。
- `v0.7.0` 不宣稱 signed installer、安全零容忍、任意 dataset 支援、科學模型品質、完整 thesis evidence，
  或 MCP 產品能力。固定 Granite 2B 的語意限制仍是明示邊界。
- Cleanup branch 才處理已核准的完整 MCP retirement、無 caller 的舊 Assistant scripts/tests，以及 local
  handoff 重複工作。不得藉清理改變既有 GUI workflow 或建立第二套 owner／state／validation control plane。
- Remote CI 約十分鐘的跨平台基礎不因 local handoff 過慢而移除；Windows/macOS 與有意義的 real-data、
  lifecycle、安全 gates 保留。

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

## Focused validation 與 stop condition

- Release：version single-source test、已修改 ChatPanel／walkthrough suites、Ruff check／format check、
  MkDocs strict、canonical handoff dossier、PR與main exact-SHA checks。
- Cleanup deletion：`rg` caller inventory、registry／architecture guards、對應 focused tests與完整 regression；
  發現真實production caller即保留該surface並停止該刪除。
- Handoff acceleration：不得減少assertion、允許新的skip、放寬OutcomePolicy或沿用舊source evidence。
  Recorder source identity、dashboard evidence與capture manifest任一無法在final重新驗證即回退該slice。
- 目標以相同 warm environment 將local handoff由約74分鐘降低到不超過40分鐘；若未達標，保留已證明
  等價且有淨收益的slice，重新profile，不以刪安全gate湊數。
- cleanup product/UI source若意外改變、owner數增加、MCP retirement觸及active product caller，或需要
  新public contract決策，立即停止擴張並回報。最終source改動後，先前手測證據不外推。
