# Workflow: Agent Tool-Call Scoring

## 目的

設計 thesis 用的 agent tool-call scoring system。

## 使用 Skills

- `agent-toolcall-designer`
- `validation-runner`

## 前置條件

- local-only runtime 方向已確認。
- State Snapshot / Tool Call / Verification Result / Scoring contract 外框已存在。
- 後端 command surface 至少有第一個可測切片。

## 步驟

1. 定義 benchmark case schema。
2. 定義 expected tool call / expected state delta。
3. 定義 scorer output：intent、tool、parameters、verification、state transition、error recovery。
4. 區分 single-turn、multi-turn、wrong-stage、invalid parameter、self-correction cases。
5. 產生 machine-readable report 和 human-readable summary。
6. 將結果映射到 thesis claim。

## 禁止

- 不把舊 Gemini/API benchmark 當新的 thesis evidence。
- 不只評自然語言回答。
- 不在沒有 backend command evidence 時宣稱 workflow success。
