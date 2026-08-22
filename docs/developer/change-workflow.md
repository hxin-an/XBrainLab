# 變更與驗證流程

## 1. 確認基線

開始編輯前：

```bash
git status --short --branch
git worktree list
```

確認 branch、base commit、dirty files，以及既有修改的 ownership。從 `main` 建立短期 task branch；
如果另一項任務仍在進行，或目前 checkout 有無關的本機設定，使用獨立 worktree。

## 2. 定義一個 observable outcome

先寫清楚：

- 使用者可見或 state-level outcome；
- 既有 owner 與 call path；
- scope 與 non-goals；
- 重要的 failure、cancellation 或 stale-result 行為；
- 能區分真正成功與 false pass 的 focused validation。

Product bug、feature 與 refactor 遵循 `AGENTS.md` 的 plan-first 規則。Plan 不會授權 adjacent
cleanup，也不會自動核准新的 public contract。

## 3. 完成最小 coherent change

重用既有 owner 與 command boundary。新增 abstraction 前，優先刪除重複 policy 或 compatibility
code。新的 abstraction 必須服務真實 production caller 或 unsafe／external boundary，並在同一
變更移除重複 policy。

所有可見 UI 變更都必須先取得使用者明確核准，包括文案、layout、interaction 與 state change。

## 4. 驗證行為

從[測試與驗證](testing.md)選擇能直接觀察所改 contract 的最小 command。該頁集中維護 focused
selector、domain runner、docs、tool-call 與 handoff 的執行方式，這裡不複製 command list。

Qt、PyTorch 與 MNE 檢查需要明確 timeout 並停用 core dump。只有 mock 的測試不能證明 native GUI
materialization、真實 dataset 路徑或本機模型決策。

Executable handoff gate registry 位於 `scripts/dev/handoff_gate_spec.py`。不要把它會變動的 command
list 複製到可重用 guidance。

## 5. 透過 pull request 提交

- 審閱 final diff，並解釋所有無關 dirty files。
- Push 驗證所使用的 exact branch head。
- 所有 applicable、non-skipped checks 都必須完成並成功。
- 只能透過 pull request merge。
- Product behavior 需要目前有效的使用者手動驗收；不改變產品行為的 docs-only、tests-only、CI
  或 guidance change 可依既有規則豁免。

Manual acceptance 後若 source 再次變更，該次批准就不再有效。
