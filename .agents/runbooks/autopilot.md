# XBrainLab Autopilot

最後更新：`2026-05-02`

這份文件描述 agent 長時間工作時的 product-delivery 循環。舊的 `Prep Gate` / `Repair Loop` autopilot 已退役。

## 核心規則

持續推進，並以文件保存狀態。milestone 是最低交付門檻，不是工作上限。

目前階段是：

```text
product-delivery engineering
```

所以 autopilot 的工作重點是：

1. 維持 legacy 整合後刪除的閱讀面。
2. 推進 backend core、UI / agent command surface、UI chat、agent tools、local LLM、desktop launcher。
3. 每個 milestone 自己驗證；測試失敗先修。
4. 把重要結果寫回少數 canonical docs。
5. 產品主線穩定後，才開始 tool-call eval / thesis evidence。
6. 開始較大工作前，先讀 `AGENTS.md`、`docs/planning/now.md` 和相關 `.agents/workflows/`。

## 當前 queue

以 `.agents/runbooks/active-queue.md` 的短 queue 為準。

## 工作循環

每輪工作：

1. 讀 `AGENTS.md` 和 `docs/current.md`。
2. 確認 `docs/planning/now.md`、`docs/planning/roadmap.md` 沒有混在一起。
3. 對要改的程式或文件做 code / runtime / artifact 對照。
4. 實作能讓產品更可用的最小完整工程成果。
5. 跑對應驗證。
6. 把結果寫進 `docs/records/worklog.md`。
7. 若結果會改變 current truth，再同步 `docs/current.md`、`docs/validation/README.md`、`docs/decisions/README.md` 或 `docs/planning/now.md`。

## 可做

- 清理 `.agents/` 舊引用。
- 清理 canonical 文件的舊路徑與過期說法。
- 把短期舊文件的有效內容整合到 canonical 文件，然後刪除原舊文件。
- 對 dashboard、pipeline smoke、docs build 做驗證。
- 對架構文件做 source-code 對照。
- 使用新的 repo-local skills / workflows 推進 product delivery、驗證或文件校準。
- 推進 backend command adapter、UI chat、agent tool alignment、local LLM runtime、desktop launcher。

## 邊界

- 不恢復舊 `xbrainlab-*` repo-local skills。
- 不新增新多角色 automation。
- 不把 UI / agent 各自接成第二套 backend workflow。
- 不在產品主線未穩定前提前做 tool-call eval。
- 不下載超過容量邊界的大模型。

## 完成定義

一輪 autopilot 工作完成時，至少要有：

- 清楚的修改範圍。
- 一個可檢查的驗證結果，或明確寫出沒跑的原因。
- `docs/records/worklog.md` 裡的流水帳紀錄。
- 沒有把 legacy 文件重新升格成 current truth。
- 若改變產品能力或架構，已更新 implementation log 和相關 architecture / validation / planning 文件。
