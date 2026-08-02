---
name: validation-runner
description: Use when choosing and interpreting XBrainLab validation commands, quality dashboard checks, pytest gates, mkdocs builds, real-data IO smoke tests, and claim boundaries.
---

# validation-runner

## 用途

用於選擇 XBrainLab 驗證指令，並判斷結果能支撐什麼 claim。

## 先讀

1. `docs/validation/README.md`
2. `docs/architecture/validation.md`
3. `docs/current.md`
4. `docs/agent_goals/product_quality_closure_goal.md`
5. `docs/records/product_quality_audit_2026-07-30.md`
6. `.agents/runbooks/setup.md`

## Command Authority

所有 current validation commands 只由 `docs/validation/README.md` 的 **Handoff Command
Manifest** 定義。這個 skill 負責選擇、執行和解讀 manifest slice，不複製命令、不省略
`required-ci` / `--verify-only` / wizard / multi-dataset steps，也不移除 native command 的
timeout 或 `prlimit --core=0`。

若 manifest command 與 repo path/CLI 不一致，先回報並修正 canonical manifest；不得自行改跑
較弱 command 後宣稱原 gate 通過。Focused work 可以只跑相關 slice，但 completion label 必須
保持 `checkpoint`，直到 active goal 要求的完整 exact-commit manifest 通過。

## 判斷規則

- dashboard PASS 是 engineering health，不是 thesis claim。
- mock-heavy unit tests 是 regression floor，不是 real workflow evidence。
- architecture / refresh / state-truth 類修復，必須有 same-class sweep 和 source guard clean
  evidence；只跑新增測試只能支撐 checkpoint，不能支撐 complete。
- 給使用者手測或宣稱 handoff-ready 前，必須完成 `.agents/workflows/handoff-candidate.md`：
  focused regression、same-class sweep、happy path、edge/regression、artifact review、branch
  hygiene 和 claim boundary。
- data/import/label/epoch/training/evaluation/visualization handoff 前，必須跑 required
  multi-dataset gate；跳過時只能稱為 checkpoint。
- 不同副檔名不等於不同資料集；同一 source family 的轉檔只能算 format coverage，不能算 dataset source diversity。
- public local-only fixture evidence 不能當作 clean clone always-on CI。
- optional `llm` group 未驗證前，不能宣稱 local LLM runtime ready。
- tool-call scoring system 尚未建立前，不能宣稱 agent tool-call accuracy。

## 輸出

每次驗證要寫：

- command
- result
- claim supported
- claim not supported
- completion label：`complete` / `checkpoint` / `blocked`
- follow-up
