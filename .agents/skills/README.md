# XBrainLab Agent Skills

最後更新：`2026-05-01`

這裡放 repo-local reusable skills。

skill 是「可重用能力」，不是長流程。長流程放 `.agents/workflows/`。

## 設計來源

第一版 skills 參考：

- OpenAI / Codex skill-creator 原則：短、單一職責、progressive disclosure。
- GitHub Copilot best practices：AI 擅長產生 tests / repetitive code，但輸出必須 review。
- Claude Code common workflows / best practices：明確指定檔案、測試場景、驗證方式。
- 社群 TDD 經驗：AI 容易跳過 failing test、過度 mock、寫假通過測試，所以需要 guard。

## Active Skills

| Skill | 用途 |
| --- | --- |
| `tdd-guard` | TDD / test-first 小變更流程。 |
| `test-quality-reviewer` | 檢查測試是否過度 mock、是否真能抓 side effect。 |
| `code-reviewer` | 以 bug / regression / missing tests 優先的 code review。 |
| `software-design-reviewer` | 評估設計是否有 source-of-truth、contract、testability。 |
| `docs-curator` | 整理文件、判斷 current / target / historical / records。 |
| `architecture-reviewer` | 對照 target 與 current architecture，產出架構 gap。 |
| `validation-runner` | 選擇驗證指令、判斷 evidence 能支撐什麼。 |
| `refactor-slicer` | 將後端 / agent 重構切成小 slice。 |
| `agent-toolcall-designer` | 設計 agent state / tool / verifier / scoring contract。 |

## 使用原則

- skill 只給 agent 操作方法，不取代 canonical docs。
- skill 不保存 current truth；current truth 回寫 `docs/current.md`、`docs/architecture/`、`docs/validation/README.md` 或 `docs/decisions/README.md`。
- skill 不應擴張成長篇規格；長流程應移到 workflow。
- 舊 `xbrainlab-*` skills 已刪除，不要恢復。
