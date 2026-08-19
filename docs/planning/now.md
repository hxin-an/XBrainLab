# XBrainLab Now

最後更新：`2026-08-20`

## 目前焦點

將使用者已在 `fix/assistant-direct-parameter-provenance-v1` 手測通過的 Local Assistant 初版封版為
`v0.7.0`，經同一 exact source 的 PR、CI 與 handoff evidence 合併到 `main`。封版期間不再改產品行為；
完成 release 後，才從乾淨 `main` 建立唯一的 cleanup branch，連續完成過時 Assistant／MCP surface
移除與驗證加速，直到下一個完整候選可交使用者手測才停。

目前 phase：`Active — v0.7.0 release closure`

## 問題與證據

- 目前 task branch 比 `main` 包含完整 Assistant integration 與後續真人手測修復，但最後一批 ChatPanel
  幾何變更尚未 commit；使用者已於 `2026-08-20` 明確表示此 exact working source 手測通過並同意合併。
- Remote PR #40 仍以舊 integration branch 為 base，且 remote head 尚未包含最後手測 source；不能直接把
  舊 checks 外推到目前 source。
- 版本與 current truth 仍停在 `0.6.0` Desktop GUI baseline，尚未記錄 bounded Local Assistant baseline。
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

### A. v0.7.0 release closure

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
