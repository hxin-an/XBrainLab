# XBrainLab Now

最後更新：`2026-08-17`

## 目前焦點

**建立 Assistant Stable v2 的 durable target authority，之後在暫時 integration branch 以小 PR
完成 replacement、atomic cutover、deletion 與 exact-SHA candidate；在完整候選前不要求使用者手測，
未取得同一 source 的手測通過不得合併 main。**

目前 phase：`CI bootstrap`

目前 branch：`ci/assistant-stable-v2-integration-trigger`

下一步：將 CI bootstrap PR 推向 main，要求同一 exact SHA 的所有 applicable GitHub checks
`completed/success`；合入後才從 exact main 建立 integration branch。

已完成 checkpoint：target authority 已由 PR #34 以 exact merge commit
`7518c7a60ab7e5355b2e5e1fbc6412ba8edeab2b` 合入 main；該 PR 只有 docs/guidance，沒有產品行為。

## 問題與證據

- Current product仍發布21個model-facing actions；該集合是PR #30從runtime inventory投影出的current
  implementation，不是使用者逐項核准的target。
- 舊target文件仍同時描述Host intent narrowing、bounded continuation、大型state snapshot與多分支
  response contract，和已核准的一回合一動作／thin Host設計衝突。
- Current `PipelineStage.DATASET_READY`只以generated datasets推導，尚未表達split、model、training
  settings三者都完成的target語意。
- Current debug path仍要求local runtime READY，且在terminal前consume下一個call；因此不能作為
  無模型、逐步可見的frontend walkthrough。
- Current UI handoff已有Import、Epoch、Split、Training、Montage與panel correlation；Channel Selection
  仍缺typed terminal。這些是bounded seam，不需要新增dialog或workflow owner。

## Observable outcome

- [Agent target intent ledger](../target/agent.md#target-intent-ledger)是唯一approved target surface，
  current／target不再混用。
- Backend既有stage、publication與capability policy是唯一readiness truth；Host不再自行縮限intent、
  substitute command或自動continuation。
- Granite只輸出strict三欄envelope；一個turn最多一個tool或一個response。
- 七個GUI completion tools只開啟既有surface；五個preprocess tools直接走ApplicationService；四個
  lifecycle tools沿用既有confirmation；navigation只由`switch_panel`負責。
- Normal UI layout與dialogs維持穩定；只加入已核准的debug-only banner、progress與Enter gating。
- 最終authoritative owner、workflow state machine與receipt數量不增加，production LOC淨減少。
- 只有完整17-tool、三份no-model profile、真Granite、source-diverse gate與CI在同一SHA閉合後，才
  交付一次完整手測。

## Scope、ordered repair 與 checkpoint

1. **已完成 — Target authority PR → main**：收斂target、decisions、current/target wording與staged
   validation；PR #34 已合入 exact main。
2. **PR candidate — CI bootstrap PR → main**：讓base=`integration/assistant-stable-v2`的product/docs
   PR執行既有GitHub Actions；只改兩個既有 workflow 的 exact PR base filter 與直接 regression，
   不建立較弱的替代CI或新 workflow。Local focused regression、guidance audit與MkDocs strict已通過，
   等待同一SHA的remote checks。
3. 從exact main建立`integration/assistant-stable-v2`；該branch不是產品基線或release source。
4. Characterize current UI／handoff／debug／PhysioNet path，建立no-generation diagnostic transport。
5. 校正backend stage與action metadata，先讓prompt、RAG、verifier、eval、showcase從單一projection
   取得catalog。
6. 收斂strict envelope、repair budget、minimal state card與one-message context。
7. 建立target adapters與GUI routes，但在cutover前不發布第二個model catalog。
8. Atomic cutover到approved target projection，同時停止Host narrowing／continuation call sites。
9. 按analysis、dataset protocol／recipe、training wrappers與Host policy分片物理刪除obsolete code。
10. 執行三份no-model profiles與frozen Granite suite；未達gate時只調prompt／schema／approved
    examples，不增加Host heuristic或silent fallback。
11. 同步最新main、完成handoff dossier並凍結exact candidate SHA；只在此時交付使用者手測。
12. 手測通過且source未變後，以integration→main merge commit合併；之後刪branch並移除暫時CI
    trigger。

每個implementation slice從integration開短branch並PR回integration；CI全綠後squash為一個coherent
commit。Final rollup可以聚合這些已分片審查的commits，但不得加入新的未審實作。

## Scope ceiling 與 UI confirmation

已取得的UI實作確認只涵蓋：

- 既有Assistant經approved GUI tools開啟既有dialog／panel。
- Debug launch的slim banner、step progress、composer提示與pending期間Enter disabled。
- `switch_panel`顯示具體destination，並等待materialized terminal。

不包含normal product layout、theme、dialog redesign、新generic result card或其他workflow copy變更。
若implementation需要超出以上範圍，停止並重新取得使用者明確確認。

Non-goals：不修改或stage root `settings.json`；不重建ApplicationService；不新增authoritative owner、
state machine、receipt、runtime fallback或第二套compatibility path；不在candidate前啟動thesis-grade
benchmark。

## Focused validation

- Target ledger完整鎖定tool、stage、schema、execution kind、owner、confirmation、terminal與retired
  disposition；其他canonical docs只引用，不複製清單。
- Current architecture在runtime切換前仍誠實稱為current21 projection；不得提前宣稱Stable v2完成。
- Docs link/source audit、guidance audit及MkDocs strict通過。
- 每個code slice加入直接對應的unit／integration evidence；UI handoff驗accepted→completed／cancelled／
  blocked／failed與stale／duplicate。
- Candidate使用同一clean/explained exact SHA完成no-model、Granite、data、UI artifact、static quality與
  GitHub checks；manual acceptance不由automation取代。

## Stop conditions

- Target、current、active plan或source對tool membership／stage／owner互相衝突。
- Prompt、RAG、eval、showcase或walkthrough另存第二份可漂移catalog。
- GUI tool在surface opened時過早回success，或debug在terminal前前進。
- Slice新增owner／state machine／receipt、pure refactor淨增超過100 production LOC，或final
  production LOC非淨減少而未取得complexity exception。
- Granite未達candidate safety／accuracy gate、必要CI有missing／pending／skipped／failed，或
  source在manual acceptance後改變。
