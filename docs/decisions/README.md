# XBrainLab Decisions

最後更新：`2026-08-17`

## 這份文件的用途

這份文件是目前有效決策的濃縮入口。

舊 ADR 的核心內容已整合到這裡，原 legacy ADR 文件已刪除。這份文件會標記：

- 目前有效決策
- 歷史決策
- 需要重新驗證的決策
- 被新方向取代的早期想法

## 目前有效決策

| 決策 | 狀態 | 說明 |
| --- | --- | --- |
| 穩定化優先 | active | 先讓既有 app 可跑、可測、可理解，再做 agent redesign。 |
| app 內 assistant 是 workflow operator | active | 它不是外部 coding assistant，也不是普通聊天視窗。 |
| assistant runtime local-only | active | 為了簡化開發、部署、隱私和驗證，assistant product runtime 已 local-only；remote backend modules 已從 product package 移除，`openai` / `google-genai` 只留 optional `legacy-remote-llm` dependency group。 |
| Assistant tool surface 由 approved intent 決定 | active | Tool 不由 runtime inventory 或既有測試反推。名稱、membership、side effect、confirmation 與 visible result 必須先在 `docs/target/agent.md` 的 intent ledger 取得使用者核准；current model-facing projection 只描述現況。 |
| Assistant Stable v2 target surface | active | Target intent ledger 已鎖定17個產品tools、backend-owned stage、strict三欄envelope、一回合一動作、thin Host與GUI completion terminal。Implementation只能投影該ledger；不得用Host heuristic、silent substitution、auto continuation或runtime fallback補模型決策。 |
| Assistant Stable v2 staged merge | active | Product重建先在暫時integration branch以小PR完成；該branch不是產品基線。只有完整candidate在同一exact SHA通過工程證據、使用者手測並取得明確merge同意後，才以merge commit進main；source改變即使批准失效。 |
| validation 是 thesis-critical | active | 測試和 evidence 是論文主張的一部分。 |
| 文件要少數 canonical 化 | active | 短期 AI / agent 文件整合後刪除，只保留少數 canonical 文件。 |
| Agent guidance 採 lean single-authority contract | active | Root 保存授權、safety、scope ceiling、complexity trigger 與 handoff 不變量；skills 只保存 routing/方法，workflows 保存多步程序。Static audit 只限制上限與 authority integrity，不再要求最低篇幅或大量外部 A/B。 |
| Declared scope 是 delivery ceiling | active | 使用者要求、明定 acceptance 與直接必要依賴是本 slice 上限。Independent findings 預設只回報，不自動實作或阻擋 scope-complete；完整 closure 只由明確 handoff claim 啟動。 |
| Product repair 採 plan-first | active | Product bug、feature 與 refactor 在實作前先收斂到 `docs/planning/now.md` 的唯一 active plan，包含證據、邊界、修理步驟、驗證與 stop condition；不以聊天上下文或分散 planning files 承擔 durable truth。 |
| UI 修改需使用者事前確認 | active | 任何 `XBrainLab/ui/` 修改，或會改變可見 layout、文案、互動、狀態或流程的修改，即使是 bug fix，實作前也必須先取得使用者明確確認。唯讀診斷與無可見行為變化的 backend 修正除外。 |
| product delivery milestone 是最低門檻 | superseded 2026-08-14 | 這個語意會讓 finding 無限重新定義 scope，已由 declared scope ceiling 與獨立 handoff-ready gate 取代。 |
| tool-call eval 等產品主線穩定後再做 | active | Eval / thesis evidence 應測穩定產品主線，不應太早測半成品 bug。 |
| local LLM 下載需受容量邊界控制 | active | 可下載模型，但單模型原則 10GB 內、總 cache 原則 20GB 內；27B+ 需使用者明確同意。 |
| local LLM 不使用中國模型 | active | 不使用中國公司或中國來源模型；Qwen、DeepSeek、Yi、GLM、Baichuan、InternLM、MiniCPM 等不列入 primary / fallback 選型。 |
| 資料匯入目標是 Data Interpretation System | active | 使用者提供資料位置後，系統應建立可預覽、可驗證、可重跑的資料解讀；不以單純 load file / attach label 心智模型作為終局設計。 |
| MCP 從 active roadmap 移除 | active | MCP 不再是 MVP、release candidate、handoff gate 或 thesis evidence 前置；既有 MCP code/tests/artifacts 只保留為歷史探索或相容性證據。只有使用者明確要求時才 opt in；未來若要恢復，需另開決策重新定義 scope、security、session ownership、client matrix 和 validation cost。 |
| Roadmap 五階段定型 | active | 產品主線固定為 Rebaseline -> Desktop MVP -> Product Polish / Release Candidate -> Assistant MVP -> Thesis Evidence。阻礙使用或理解的 UI/UX 屬於 Desktop MVP blocker；美感、一致性和低風險 polish 屬於 Product Polish / Release Candidate。 |
| Product-Quality Closure Delivery Flow | superseded 2026-08-04 | `stabilize/product-quality-closure` 已依使用者決定收斂到 `main` 作 development checkpoint。這不代表 release 或 product completion；後續以短 task branch 回到 `main`，並由 current Now / Validation 定義下一個 candidate gate。 |
| Desktop MVP Delivery Flow | superseded | `stabilize/desktop-mvp` 是較早 delivery flow，保留作決策歷史，不再是 current branch、task base、merge destination 或 validation authority。 |
| User bug report triggers broad audit | superseded 2026-08-14 | 舊 product-quality closure 模式會把單一回報擴張為跨產品盤點。現在只掃描改動 owner 與直接耦合 call sites；獨立問題只作 advisory follow-up。 |

## 目前工作方向

| 方向 | 狀態 | 說明 |
| --- | --- | --- |
| UI / Assistant / Scripts 共用 Application Service | confirmed | `BackendFacade` 已物理移除，也不是 wrapper 或 compatibility target。UI、assistant tools、scripts 應共用 `ApplicationService / Command API`，不得建立等價第二入口。 |
| UI / Agent command surface unification | active | UI 和 agent 對同一 backend workflow 應共用 state、capability policy、blocked reason 和 typed command result，不各自維護第二套判斷。 |

## 舊 ADR 處理

- `ADR-011` 的主線已濃縮為：穩定化優先、validation thesis-critical。
- `ADR-012` 的主線已濃縮為：文件少數 canonical 化、legacy 整合後刪除。
- `ADR-013` 的主線已濃縮為：app 內 assistant 是 workflow operator。
- `ADR-001` 到 `ADR-010` 視為早期探索，已不再保留為 current decision source。

未來若需要新增重大決策，直接補到本文件，不再新增大量碎片化 ADR。
