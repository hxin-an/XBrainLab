# XBrainLab Now

最後更新：`2026-08-19`

## 目前焦點

Assistant 真實 Granite 行為仍是 integration candidate 的最後 blocker。18-action surface、no-model
walkthrough、confirmation、navigation、Compute Saliency 與 presentation 以 PR #39 merge commit
`70274bed4c41331965e7d4795d0d16520cb0aada` 為唯一產品基線；本輪 evaluator 實驗未改產品 runtime、
ApplicationService、UI 或 `settings.json`。

目前 phase：`Checkpoint；two-pass candidates rejected，無真人手測候選`

## Exact-model evidence

固定 `ibm-granite/granite-3.3-2b-instruct` revision
`707f574c62054322f6b5b04b6d075f0a8f05e0f0`、greedy generation、同一 GPU process與同一50-case
development suite；所有實驗只產生／評分 envelope，未執行產品工具：

- A 現行一段式：36/50；positive 36/36，challenge 0/14，warm P95約1.5秒。
- B gate-first：最佳31/50；positive 31/36，challenge 0/14，warm P95約3.2秒。
- C gate-first＋safe-decision RAG：最佳32/50；positive 30/36，challenge 2/14，warm P95約3.0秒。
- D proposal-first／critic-second 初始格式衝突輪：proposal 36/36，但 critic 只2/50可解析；此輪只用來
  找 evaluator contract defect，不作架構比較。
- D 修正通用 critic／response strict envelope後：proposal仍36/36；critic後positive 17/36；14個
  challenge只擋8個，6個仍被approve；安全response 0/14；總分17/50；warm P95約3.9秒。

D 最終報告位於 ignored local artifact
`build/dev-artifacts/stable-assistant-proposal-critic-development-v2.json`；positive cases SHA256
`a4311b63165c2f4fb1c68d88c1ed8c81ecb9ae3beb1760bf1c2e52cda57f31bc`，challenge SHA256
`df300230c11b0ca014b1320e20ec80f2529766d2cbb2d50cd38adbe78ba2405b`。Model load、runner identity、
逐case proposal／critic／branch／timing皆在該report。沒有執行heldout，因development promotion已失敗。

## Stop decision

- B/C/D 均未過預註冊門檻，不得接入正常產品 turn，不得稱為較安全或較準確，也不得交使用者手測。
- 不降低門檻、不以個別challenge句子調prompt、不把expected答案或錯誤raw calls放入RAG。
- 未採用的 gate-first、decision-RAG與proposal-critic evaluator程式／tests／corpus已從worktree移除；只保留
  本頁證據與 ignored report，避免失敗架構累積為產品複雜度。
- 現行一段式仍是工具選擇最佳baseline，但14/14 challenge都提出不應執行的action，不能因此宣稱
  Assistant-ready。Backend schema、stage capability與confirmation仍提供deterministic防線，但無法辨識
  ambiguous／multi-action意圖，不能把它們當作模型語意正確的替代品。

## 下一個決策邊界

目前沒有已核准且有證據支持的兩段式。下一步必須先重新選擇產品方向，不能由施工agent自行擴張：

1. 保留一段式與既有 deterministic backend guards，接受模型層 ambiguous／multi-action限制，直接建立
   明確限制的真人可用性評估；或
2. 核准另一個 bounded evaluator 實驗，但必須提出與 B/C/D 不同、可由2B模型負擔且不建立 Host intent
   router的假設，先過development與heldout才可改產品；或
3. 收窄 Assistant 可直接 mutation 的工具，只讓模型導航／開GUI，高風險與語意模糊動作交回使用者。

無論選哪一條，都不改18-action membership、UI、ApplicationService、模型revision或confirmation policy，
除非使用者另行明確核准。下一個產品candidate仍須在同一exact source完成正常ChatPanel真Granite、
GUI handoff、direct command、取消／stale／late event與安全拒絕，再交使用者手測；source改變即重測。

## Merge boundary

Assistant product行為先以短branch進`integration/assistant-stable-v2`。只有同一source的applicable CI全數
completed/success、真人手測通過並由使用者明確同意，才可另走PR合入`main`。本checkpoint沒有產品diff、
沒有手測批准，也不是handoff-ready。
