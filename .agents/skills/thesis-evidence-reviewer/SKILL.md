---
name: thesis-evidence-reviewer
description: Use when reviewing XBrainLab thesis-related evidence, especially local LLM tool-call accuracy, benchmark case coverage, scorer validity, trajectory evaluation, artifact reproducibility, and claim boundaries versus EEG training accuracy.
---

# thesis-evidence-reviewer

## 用途

用於檢查論文 evidence 是否能支撐「agent tool-call accuracy」主張，而不是把 dashboard PASS、
EEG training accuracy 或 UI smoke 誤當論文結果。

## 設計來源

已消化參考：

- LangSmith agent evaluation：complex agent 要看 trajectory / tool-call path，不只 final answer。
- Berkeley Function Calling Leaderboard：function/tool calling eval 需要多類型 cases、參數、執行與
  failure taxonomy。
- OpenAI Structured Outputs：tool schema 應嚴格、可解析、可驗證；不能靠自由文字猜 tool call。

## 先讀

1. `.agents/context/thesis.md`
2. `docs/validation/thesis_protocol.md`
3. `docs/validation/README.md`
4. `docs/target/agent.md`
5. latest `artifacts/agent_evals/*`

## Review Gate

檢查：

- 主評分是否是 tool-call accuracy，而不是 EEG model accuracy。
- case schema 是否保存 user command、initial state、available tools、expected tool/no-call、
  expected args、verification decision、state delta、visible response、failure taxonomy。
- 評分是否包含 intent、tool selection、arguments、state awareness、verification、state delta、
  recovery、runtime safety、trajectory。
- cases 是否覆蓋中文/英文混合、ambiguous intent、no-tool question、多需求 prompt、blocked command、
  missing input、Data Interpretation、BIDS、label ambiguity、training/saliency readiness。
- deterministic runner 與 local LLM runner 是否分開解讀。
- primary / fallback 是否重跑足夠次數，並保存 repeat stability。
- tool-call dashboard 是否列 case family、metric breakdown、worst cases、artifact path、claim boundary。
- UI / launcher / product usability claim 是否沒有被 tool-call score 取代。

## 打回條件

- 只報 overall pass rate，沒有 failure taxonomy / case coverage。
- benchmark 太貼 normalizer 或 prompt hack，不能代表真使用者指令。
- local LLM 沒跑，只拿 deterministic scorer 宣稱能力。
- 把 training metrics 或 dashboard PASS 寫成 thesis 主 evidence。
- 缺少重跑 protocol、artifact path、模型版本、cache / runtime 條件。

## 輸出格式

```md
## Thesis Evidence Verdict

- verdict: thesis-candidate / engineering-only / insufficient

## Claim Supported

## Claim Not Supported

## Case Coverage Gaps

## Required Reruns
```
