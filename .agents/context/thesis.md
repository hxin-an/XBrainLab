# XBrainLab Research Evidence Boundary

最後更新：`2026-10-06`

此context只在任務涉及論文證據／宣稱時載入，不把研究實驗重新接回產品開發流程。
產品與研究的保存位置及界線由[驗證契約](../../docs/validation/README.md#research-archive-boundary)擁有。

## 判讀原則

- 產品main維護Desktop EEG軟體與Assistant；論文受測source、題庫、設定、scorer、
  原始輸入輸出及實驗方法在外部封存。最新產品source不是歷史受測source。
- 研究衡量的是軟體狀態限制下的工具決策正確性與延遲，不是EEG分類正確率、
  臨床有效性、回答品質或整體產品可靠性。
- 模型原始決策、Host admission／確認、實際Command／GUI結果分開判讀；
  Host擋住錯誤不使模型答對，模型選對也不證明操作已完成。
- 核對exact source、題庫、模型／配置、scorer與逐題raw再評論結果；
  不用產品新parser重評舊答案，不用新的main覆蓋封存或改寫失敗。
- 重現性、題庫來源／隔離、選版時序與人工作業是不同證據；
  hash一致不能證明作者、人工審核或獨立盲測，重現成功也不能消除方法限制。

產品架構與後續目標仍由[目前架構](../../docs/architecture/agent.md)及
[Agent target](../../docs/target/agent.md)擁有；不在此另存模型排名、輪次、研究配額或排程。
