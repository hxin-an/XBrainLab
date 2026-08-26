# XBrainLab Now

最後更新：`2026-08-26`

## 目前焦點

目前 active slice 是 Data Import 阻塞路徑的 deletion-first 收斂：在同一個 task branch／PR
中移除 Review／Apply 的重複 session copy、primary label compatibility transaction 與
`/mnt/d` 重複 path identity round-trip，同時保持安全、資料語意和 visible contract 不變。

### 問題與證據

- WSL `/mnt/d` OpenNeuro ds003061 `sub-001` 三個 run 約 190 MB；一次 warm-up 後三次
  fresh-service 的 blocking path（Catalog＋Review＋Apply）中位數約 `12.06s`，背景 BIDS
  montage idle 約 `1.52s`，完整 idle 約 `13.57s`。
- 同一 workload 在 WSL ext4 診斷副本的三次 warm measured median 約 `1.64s`；差距顯示
  `/mnt/d` filesystem metadata latency 被重複 resolve／stat／identity pass 放大。診斷副本已刪除。
- 真正 EEG loader 約 `0.73s`。主要 deletion candidates 是 discovery plan/prepared state 的
  重複 deepcopy、Apply 的整份 state deepcopy＋checkpoint/restore、以及 primary reviewed label
  apply 進入 post-load compatibility transaction 後重建 content identity。
- 目前 admitted-path experiment 將 blocking median 從約 `12.63s` 降至 `12.06s`；
  correctness、recipe trace 和 source/stored event digest 均一致，但仍未達 gate。

### Outcome

- blocking median `<= 10.0s`；非阻塞 BIDS montage background median `<= 2.0s`。
- Primary Review／Apply 各只持有一份 detached session snapshot，commit 用 one-shot ownership
  transfer 發布；rollback 不再 deepcopy interpretation records。
- Primary reviewed labels 重用當次已審查 file identities，在 commit 前仍完整 rehash 一次；
  真正 post-load compatibility import 仍 fresh-admit、checkpoint、rollback。
- Product commands、CommandResult、recipe、confirmation、UI／Assistant visible contract 不變；
  production owner 4→4，整個 branch 的 production LOC 相對 base 淨減。

### Scope 與 non-goals

- 保留目前 BIDS admitted `CanonicalPathIdentityScope` patch 與 opt-in performance profile。
- 重用現有 `AdmittedResourceReader`、BIDS index、parsed sidecar cache 和 staged session owner；
  不複製 raw data、不新增 global cache、receipt、state machine、owner、module 或 public class。
- 修改最多 8 個 production files，集中在 Data Interpretation metadata/scan、session state、
  discovery/apply preparation 與 command service。
- 不修改 `XBrainLab/ui/`、Loading presentation、Assistant/model、Import UX、背景 montage
  architecture、process-global BIDS registry 或同步 direct-handler test surface。
- root `settings.json` 必須原樣保留，不 stage、不 commit、不 restore。

### 施工步驟

1. 校正 profile contract：分開 blocking、background 與 stable idle；以 blocking median 套用
   10 秒 hard gate，保留一次 warm-up＋三次 fresh-service correctness/resource evidence。
2. 將 discovery/apply plan input 和 prepared output 改為同一 one-shot staged session container；
   plan 只保留 scalar session identity，detached state 只 deep-copy 一次，commit/rollback 採
   dictionary ownership swap。刪除 `InterpretationApplyCheckpoint` 與 apply deep-copy restore。
3. Primary detached Apply 使用 reviewed-label state path，不進 compatibility checkpoint；
   post-load content identity可重用 candidate 已審查 identities，final apply verify 仍對所有
   reviewed bytes 完整 rehash，再以 source boundary stat 守住短 commit。
4. 每個 coherent commit 都重跑同一 characterization 與相同 performance workload；最後才跑
   applicable handoff gates、exact-source WSLg 手測與 PR/CI。

### Focused validation

- Session ownership：detached prepare 不改 live state、one-shot 不能重複 consume、concurrent
  reset/revision 必須 stale、failed publish 能恢復完整 interpretation/pipeline truth。
- Apply safety：resource confirmation、content tamper before/during apply、metadata/label/dataset/
  trainer failure、cancel/retry、BaseException rollback。
- Semantics：三個 OpenNeuro runs、label apply、recipe `label_import` trace、source/stored event timing
  digest；compatibility label import 仍會 fresh-identify 新 label。
- Performance：同一 `/mnt/d` workload 一次 warm-up＋三次 fresh-service；blocking median
  `<=10.0s`、background median `<=2.0s`，CPU／IO／RSS 不得有無法解釋的 `>10%` 回歸。
- Handoff 時執行 canonical source-diverse Data Interpretation gate、focused tests、Ruff、
  diff checks；Qt／MNE 使用 `prlimit --core=0` 與明確 timeout。

### Stop condition 與 UI 確認

- 任一 commit 若破壞 correctness、rollback 或安全語意，回退該 commit並停在 checkpoint；
  不弱化 assertion 或安全檢查換速度。
- 三步完成後若 blocking median 仍高於 10 秒，保留可證明的 deletion/改善並停在 checkpoint；
  本 PR 不擴張到 raw staging、背景 montage redesign 或 security boundary 弱化。
- 本 slice 不修改 UI，因此沒有新的 UI 修改授權；但 Product 行為只能在 final exact commit
  的 WSLg 使用者手測通過並明確同意 merge 後，經 exact-head PR/CI 合併。

## 下一個 candidate

本輪合併後才回到共同打磨 Folder／File Import UX。同步 direct-handler tests、process-global
BIDS index registry 與其他非 critical-path cleanup 另開獨立 deletion slice，不併入本 PR。
