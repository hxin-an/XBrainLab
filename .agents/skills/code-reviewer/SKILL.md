# code-reviewer

## 用途

用於 review XBrainLab 程式碼變更。採用 code-review stance：先找 bug、regression、missing tests，再談風格。

## 先讀

1. `docs/current.md`
2. 相關 `docs/architecture/*.md`
3. `docs/validation/README.md`

## Review Priority

1. 行為 regression。
2. state lifecycle / side effect 錯誤。
3. thread / UI refresh / long-running task 風險。
4. data pipeline correctness。
5. test coverage gap。
6. API / Gemini path 是否被誤當產品目標。
7. style / naming。

## XBrainLab 特別注意

- UI 和 backend state 不應分裂。
- agent tool availability 要由 backend capability policy 控制。
- 一次只有一個 active dataset pipeline。
- epoch / dataset 後，一般 `load_data` / 開新 dataset 應被擋下。
- `blocked_commands` 不完整塞進 LLM prompt。
- `target/` 是目標，不是 current implementation。

## 輸出格式

Findings first：

```md
## Findings

- [severity] file:line - issue

## Open Questions

## Test Gaps
```

若沒有問題，明確說沒有發現 blocking issue，並列 remaining risk。
