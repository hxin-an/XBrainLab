# XBrainLab Now

最後更新：`2026-08-25`

## 目前焦點：Assistant runtime lifecycle 測試隔離

### 問題與證據

- PR #54 的 Linux Python 3.11 `components` shard 連續兩次在 1200 秒 watchdog
  timeout；兩次都進入既有 `test_agent_runtime_lifecycle.py`，但分別停在約第 6 與
  第 15 個 lifecycle case。
- 同一檔案目前位於 UI unit components domain，實際保留真 `AgentManager` →
  `LLMController` → `AgentWorker` Qt/thread topology，屬於 integration lifecycle evidence。
- main baseline 的 components domain 曾為 `477 passed`；目前本機完整 components、完整
  `linux-unit-ui`、疑點案例 bounded repeat 都通過，沒有單一產品 assertion failure。
- 現有 16 個案例各自保護 loading、turn admission、timeout、stop、error、handoff、model switch
  或 shutdown transition；沒有足夠證據刪除任何案例。

### Outcome

將真 Assistant runtime lifecycle evidence 移到獨立 integration domain；Linux 每個 lifecycle
case 在獨立 forked process 中執行，避免 Qt／QThread 狀態跨案例累積，同時維持 authoritative
suite 的完整分母與既有 assertions。

### Scope／non-goals

- Scope：測試分類、Linux process boundary、canonical test registry、直接 registry tests。
- Owners before／after：`scripts/dev/run_tests.py` 仍是 executable test registry owner；產品
  runtime、controller、worker 與 UI ownership 完全不變。
- Deletion candidates：移除錯誤的 unit/components placement 與含糊分類文案；不刪除測試案例。
- Production LOC：`+0/-0/net 0`；不新增 production module、owner、public API 或 compatibility path。
- Non-goals：Assistant runtime 修理、thread timeout 放寬、skip／xfail／retry、GitHub Actions
  matrix 擴張、面板 UI 修改。

### 修理步驟

1. 以現有 16/16 lifecycle passing baseline 與兩次 exact CI timeout 作 characterization；不製造
   人工 red test。
2. 將 lifecycle 檔案移至獨立 `tests/integration/assistant_runtime/` domain，保留全部 assertions。
3. Linux 對該 domain 套用 per-case `pytest-forked`；Windows／macOS 保留獨立 domain process，
   不使用 Unix fork。
4. 讓 generic integration runner 與 `linux-integration-rest` 各自把新 domain 當單一 shard；
   `linux-unit-ui` 不再收錄它，總 authoritative partition 仍精確一次。
5. 加強 registry tests，證明分類、process boundary 與完整分母。

### Focused validation

- Moved lifecycle domain：16/16，另含 Linux forked coverage＋JUnit。
- `tests/unit/scripts/test_run_tests.py` registry／partition contracts。
- Authoritative `linux-unit-ui` 與 `linux-integration-rest`。
- Ruff check／format check、`git diff --check`、exact-head PR CI。

### Stop condition

- 若 forked domain 仍 timeout，不提高 watchdog、不重跑到綠；定位單一 case 後另開需要使用者
  授權的產品 runtime diagnosis slice。
- tests-only exact head 全部 non-skipped checks `completed/success` 才可合併 main；純 tests／CI
  結構變更不要求產品 manual acceptance。
- 合併後才將最新 main 帶回 PR #54，重新建立 exact-source UI evidence 並交付 WSLg 真人手測。

### 目前狀態

- 16 個 lifecycle cases 已完整搬移；Linux 使用 per-case fork，沒有刪除或弱化 assertion。
- Registry contracts `39/39`、`linux-unit-ui` `2709/2709`、`linux-integration-rest`
  `305 passed / 35 optional skipped`，Ruff check／format check 與 `git diff --check` 均通過。
- 第一次 integration 本機執行被共用 editable environment 混入另一 checkout，active-checkout
  guard 如預期 fail closed；移除該環境污染後，同一 gate 未修改程式即通過。
- Next：freeze tests-only exact commit、建立 PR，等待所有 non-skipped CI checks 成功後合併 main。
