# XBrainLab Agent Skills

最後更新：`2026-05-05`

這裡放 repo-local reusable skills。

skill 是「可重用能力」，不是長流程。長流程放 `.agents/workflows/`。

## 設計來源

第一版 skills 參考：

- OpenAI / Codex skill-creator 原則：短、單一職責、progressive disclosure。
- GitHub Copilot best practices：AI 擅長產生 tests / repetitive code，但輸出必須 review。
- Claude Code common workflows / best practices：明確指定檔案、測試場景、驗證方式。
- 社群 TDD 經驗：AI 容易跳過 failing test、過度 mock、寫假通過測試，所以需要 guard。
- Google Engineering Practices：code review 目標是讓整體 code health 持續改善。
- Refactoring code smells：Large Class、Long Method、Shotgun Surgery、Feature Envy 等是重構信號。
- Readability / maintainability practice：可讀性、清楚策略、一致性和責任邊界是維護成本的一部分。
- Nielsen Norman usability heuristics、Microsoft Windows design guidance：UI 要能呈現狀態、
  使用者控制、錯誤預防、清楚命令面與一致內容層級。
- BIDS / MNE-BIDS：EEG/BCI import 要把 folder-level metadata、events、channels、inheritance
  和 mismatch handling 視為資料語意的一部分。
- MCP specification：stdio、Streamable HTTP、tools/list、tools/call、authorization 有不同
  transport / security / session 邊界。
- PyTorch CUDA、Qt thread/QObject、PyInstaller / Qt deployment、GitHub Actions、Apple
  notarization、OWASP LLM/MCP：用於 resource、release、security 和 thesis evidence skills。

## Active Skills

| Skill | 用途 |
| --- | --- |
| `tdd-guard` | TDD / test-first 小變更流程。 |
| `test-quality-reviewer` | 檢查測試是否過度 mock、是否真能抓 side effect。 |
| `code-reviewer` | 以 bug / regression / missing tests 優先的 code review。 |
| `clean-code-reviewer` | 檢查 maintainability、god object、legacy/fallback creep、重複 workflow truth。 |
| `ui-product-reviewer` | 檢查桌面 UI 是否像使用者產品，而不是 debug panel。 |
| `data-interpretation-reviewer` | 檢查 EEG/BCI import、label/event、BIDS、recipe 語意是否可信。 |
| `mcp-adapter-reviewer` | 檢查 MCP stdio/HTTP、session、tools/list、tools/call 是否只是 adapter。 |
| `release-packaging-reviewer` | 檢查 launcher、packaging、平台驗證、logs、first-run 和 release evidence。 |
| `performance-resource-reviewer` | 檢查 GPU/VRAM/disk、UI responsiveness、long-running job 和 native optimization。 |
| `security-privacy-reviewer` | 檢查 local-first、MCP/agent 權限、prompt injection、logs 和資料隱私。 |
| `thesis-evidence-reviewer` | 檢查 tool-call benchmark、trajectory scoring、claim boundary 和論文 evidence。 |
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
