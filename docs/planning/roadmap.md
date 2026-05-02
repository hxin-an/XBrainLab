# XBrainLab Roadmap

最後更新：`2026-05-02`

## 目前主線

1. Product delivery engineering
2. Backend product core
3. UI / agent command surface unification
4. UI chat / agent panel stabilization
5. Agent tool system alignment
6. Local LLM runtime
7. Desktop launch / packaging
8. End-to-end product stabilization
9. Tool-call eval / thesis evidence
10. 優化迭代

目前位置：

- `後端 Application Service baseline 已落地；第一批 UI / Agent readiness 已共用 capability policy；local LLM primary/fallback 已通過 smoke；launcher 已有低風險 baseline。下一步推進成品級 UI / agent walkthrough。`

## 階段路線

| 階段 | 狀態 | 重點 |
| --- | --- | --- |
| GUI 重構 | done | 主畫面、panel、dialog 已有可驗證基礎。 |
| 建立新 Agent 架構 | active | 架構方向已記錄；現在要與 backend command surface 和 local runtime 對齊。 |
| 文件整理與現況盤點 | done | canonical 文件入口已建立；legacy / active 閱讀面已收掉。 |
| 使用者 review canonical 文件 | done | 使用者已大致看完 canonical / architecture，並決定先清 legacy。 |
| legacy 文件清理 | done | `docs/legacy/` 和 `.agents/legacy/` 已整合後刪除，不再保留 legacy 閱讀面。 |
| 文件架構重整 | done | 將 target、architecture、planning、decisions、validation、records 分開。 |
| Backend product core | active | `ApplicationService / Command API` baseline 已落地；持續補 command adapter、typed result、query command。 |
| UI / Agent command surface unification | active | UI readiness 與 agent guard 已開始共用 capability policy；下一步推進 action execution 和 typed result。 |
| UI chat / agent panel stabilization | active | 修穩對話視窗、tool-call feedback、local runtime unavailable、error 顯示與閃退問題。 |
| Local LLM runtime | baseline done | 非中國 primary / fallback model 已下載；preflight、cache limit、health check、fallback 和 UI 狀態已落地。 |
| Desktop launch / packaging | baseline done | 低風險 Windows launcher / shortcut 已產出；後續再評估 PyInstaller / executable packaging。 |
| End-to-end product stabilization | active | 驗收 backend -> UI -> agent -> local runtime -> launcher 的展示主線。 |
| Tool-call 驗證 | later | 產品主線穩定後，再建立可重跑 scoring system 和 thesis evidence。 |
| Agent runtime / tool surface 簡化 | active | Product runtime 已 local-only；remote backend modules 已移除，後續重點是 typed tool result、capability-aware tool surface 和真 local LLM UI walkthrough。 |
| 優化迭代 | later | 根據驗證結果改善 agent、資料流程和使用體驗。 |

## 現在先做

1. 把更多 UI action execution 改成 service-backed command adapter。
2. 將 agent real tools 推進到 `CommandResult` / typed result adapter。
3. 完成 launcher -> MainWindow -> chat panel -> agent blocked-command walkthrough。
4. 將 local runtime smoke 和 launcher smoke 收進更穩定的 product validation script。
5. 補真 local LLM 長時間 ChatPanel walkthrough，確認 local-only runtime 在產品 UI 中的長回覆 / timeout / fallback 體驗。
6. 產品主線穩定後，再開始 tool-call eval / thesis evidence。

## 先不做

- 不把 milestone 當工作上限；清單勾完但產品不可用不算完成。
- 不讓 UI / agent 各自維護第二套 backend workflow。
- 不在產品主線未穩定前提前做 tool-call eval。
- 不下載超過容量邊界的大模型；單模型原則 10GB 內，總 cache 原則 20GB 內。
- 不使用中國公司或中國來源模型；Qwen、DeepSeek、Yi、GLM、Baichuan、InternLM、MiniCPM 等模型不列入選型。
- 不直接下載 27B+ 模型，除非使用者明確同意。
- 不把 tool-call 驗證當成已完成。
- 不把 dashboard PASS 說成 thesis claim 已成立。
- 不新增更多 planning 文件。
