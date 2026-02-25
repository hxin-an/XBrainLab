---
description: 自動化提交流程 (包含 Pre-commit, Changelog 更新與 Git Commit)
---

# 提交工作流 (Commit Workflow)

這個流程會協助開發者將目前的變更自動進行代碼格式檢查、更新版本紀錄，並完成提交。請嚴格按照以下步驟執行：

## 步驟 1：檢查 Git 狀態與變更
// turbo
1. 執行 `git status` 確認目前有哪些檔案被修改、新增或刪除。
2. 執行 `git diff` (若有 staged files 則執行 `git diff --cached`) 查看具體的程式碼變更內容。
3. 根據變更內容，**在心裡**總結出剛才做了哪些主要修改（例如：修復了某個 Controller 的 Bug、新增了某個功能等）。

## 步驟 2：執行 Pre-commit 檢查
// turbo-all
1. 執行 `git add .` 將所有變更加入暫存區 (Staged)。
2. 執行 `pre-commit run --all-files`。
3. 如果 Pre-commit 檢查失敗（例如 ruff 或 black 自動修改了檔案）：
   - 讀取終端機輸出的錯誤訊息。
   - 執行 `git add .` 將自動修正的檔案再次加入暫存區。
   - 再次執行 `pre-commit run --all-files`，不斷重複此循環，直到顯示「全部通過 (Passed)」或是 Exit code 為 0 為止。
   - *注意：若出現需要手動修復的靜態型別錯誤 (mypy 等)，請暫停並詢問使用者如何處理。*

## 步驟 3：更新 CHANGELOG.md
1. 讀取 `documentation/CHANGELOG.md` 檔案目前的內容。
2. 根據「步驟 1」中你總結的變更，按照 CHANGELOG 的格式（例如放在 `[Unreleased]` 或是當天的日期區塊下），新增本次的變更紀錄。
   - 請將變更分類到 `### Added`, `### Fixed`, `### Changed`, 或 `### Refactored` 底下。
3. 將修改後的內容寫回 `CHANGELOG.md` 檔案中。
// turbo
4. 執行 `git add documentation/CHANGELOG.md` 將更新後的 Changelog 加入暫存區。

## 步驟 4：產生描述性 Git Commit
1. 根據變更內容，決定一個符合 [Conventional Commits](https://www.conventionalcommits.org/) 規範的 Commit 標題 (例如 `fix(core): ...`, `feat(ui): ...`)。
2. 產生的 Commit Message 必須包含適當的描述。
3. 詢問使用者：「我打算使用以下訊息進行 Commit，請問是否同意？\n\n\`\`\`\n<你的 Commit Message>\n\`\`\`」。
4. 得到同意後，執行 `git commit -m "<你的 Commit Message>"`。

## 步驟 5：完成
1. 總結本次提交流程，告知使用者已成功完成 Commit。
