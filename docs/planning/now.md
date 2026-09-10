# XBrainLab Now

最後更新：`2026-09-11`

## Active

## Module-by-module quality baseline

User approved the complete modular cleanup plan and requested implementation on 2026-09-10.
Earlier PR #131 acceptance is historical; it does not approve this stage's source or merge.

### Outcome and scope

Establish a reliable, understandable baseline by deleting historical overdesign, duplicated work and
unnecessary waits. Audit all tracked production, tests, scripts, dependencies, development configuration
and docs. File/LOC/test counts are inventory, not proof of quality or completion.

Preserve visible UI behavior, Command/query/Assistant public contracts, EEG semantics, settings,
recipes and existing result reading. Behavior-preserving UI internals are explicitly authorized.
Unused Python convenience APIs may be removed after checking dynamic registration, configuration,
scripts and documentation. Preserve necessary safety, cancellation, publication and consistency.
No feature/UI redesign, architecture rewrite, model/prompt/RAG experiment, new control plane,
new environment, WSL compaction, backup deletion or unrelated local cleanup.

The user additionally confirmed large-file and code-quality assessment: inspect mixed responsibilities,
coupling, duplicated branches, typing diagnostics and test effectiveness, not only physical LOC. Record
before/after evidence for changes; splitting a file or improving a number alone is not closure.
Previously authorized withdrawal of WSL-compaction tooling and exact residual cleanup remains a
separate infrastructure task; do not restart compaction/shutdown or mix destructive cleanup into
product refactor commits. Revalidate exact targets and active use before that task executes.

### Stage integration exception

One integration branch/PR contains small independently reversible commits, reviewed by module.
The user explicitly approved accumulated stage-level diff and one final Windows manual acceptance;
this stage does not require a PR/manual merge per slice. Slice-level complexity review still applies:
record deletion candidates, owner delta, production +/-/net LOC and split any oversized coherent slice.
This exception does not weaken CI, data/native/Assistant evidence or exact-source merge approval.

Use the existing Windows environment and model/data caches. Preserve the original checkout's dirty
UI/test files and root settings. Worktree/branch/source facts come from Git, not historical paths.

### Module order and ownership

| Module | Includes | Status |
| --- | --- | --- |
| 1 Command/state spine | Admission, capabilities, confirmation, publication, owned work, shared domain ports | Responsibility review closed at 1247cf7c; native 178 passed; domain branches explicitly remain modules 2–6 |
| 2 Import/interpretation | Loaders, BIDS, labels/classes, channel/montage, metadata, recipes, related UI | Audited core reviewed; not closed: two confirmed visible defects await authorization; inventory reconciliation in progress |
| 3 Preprocess/epoch/split | Processing, copies, invalidation, preview/materialization, related UI/tools | 3A–3U reviewed; documented split-artifact decision and final inventory/closure review remain open |
| 4 Models/training | Catalog, resource preflight, settings, stop/rerun, history/checkpoints | Core/model/resource/record/UI audit substantially complete; final inventory, convenience retirement and two visible decisions remain open |
| 5 Evaluation/saliency/views | Read/publication, SmoothGrad/recompute, four views, stale work/render lifecycle | Core/attribution/3D/publication integration fully read; script/inventory reconciliation and two explicit retirement decisions remain open |
| 6 Assistant/chat | Tool adapters, turns/confirmation/execution, model/RAG lifecycle and shutdown | Core/runtime/RAG/controller/chat source and major tests deeply audited; adapters/helpers/inventory and explicit retirement decisions remain open |
| 7 Shared desktop/runtime | Shell/navigation, shared components, configuration, errors/logging/start/close | Shell/navigation/shared owners reviewed7A–7M; remaining shared UI tests/inventory and module closure review open |
| 8 Scripts/dev/CI | Launch/setup, Poe/hooks, runners, walkthroughs/evaluators/reports and artifacts | Launch/setup/CI/runners/reviewer-capture reviewed; remaining scripts/walkthrough/inventory open |
| 9 Cross-module tests/docs | Shared fixtures/guards, dependencies, canonical truth/navigation and coverage gaps | Fonts/RNG/VRAM/weight/refresh evidence strengthened9A–9G; docs/deps/remaining fixtures and full coverage evidence open |

Each module includes its callers, tests and related scripts. Domain UI belongs to its domain module;
shared UI belongs to module 7. Script infrastructure has a separate complete review in module 8.
Assign every tracked file to a module (or an explicit retained static/vendor asset group); count and
resolve uncovered files before final review. Generated files are not production inspection evidence.

### Per-module procedure and closure

1. Read owned implementation/tests; trace entry points, authoritative state, mutation/publication,
   async lifecycle and consumers. Record deletion/consolidation candidates and concrete retain reasons.
2. Obtain passing behavior characterization before refactors; reproduce bugs before fixing them.
   Measure only suspected redundant work/waits and their directly relevant paths.
3. Make small deletion/reuse-first changes. Do not replace wrappers with another owner or move code
   solely to reduce file size. Update this plan before each new coherent slice.
4. Improve behavior evidence before removing weak/obsolete tests. Important side effects need a
   lower-mock internal workflow; keep valid external/native isolation. Check selected high-risk tests
   with a bounded intentional behavior break. Preserve known regression cases.
5. An independent non-author reviewer examines actual source/diff/callers/evidence and audit coverage;
   the main agent inspects the resulting diff/evidence. Fix blocking in-scope findings and re-review.

Closure requires complete file responsibility/disposition, resolved confirmed in-scope redundancy,
credible normal/failure/cancel behavior protection and explicit independent review approval. Unknown
in-scope items are not done. Public-contract/visible-behavior decisions require user input; continue
independent authorized work. Later shared-boundary edits reopen only affected module evidence.

### Validation and final endpoint

Focused checks per slice; widen early for shared state/data/publication/lifecycle risk. Preserve the
existing 85% line coverage gate and branch evidence without shrinking the denominator. Select commands
from the existing validation contract/runner; do not create another test-selection or gate framework.

After all modules close, independently review cross-module integration and inventory completeness.
Freeze a final exact commit and require applicable same-head CI, source-diverse data, platform/UI and
affected real-model Assistant evidence. Reuse equivalent successful CI; fill only missing local evidence.
Keep the Assistant's accepted bounded limitations; this stage is not Stable promotion.

Required scenarios include failed import retaining prior data, old recipe/result reading, processing
and split semantics, training stop/rerun, saliency completion/cancel/SmoothGrad/recompute/selector changes,
stale work rejected, Assistant confirmation/failure recovery and runtime shutdown/resource release.
Scripts additionally need honest exit/output outcomes, rerun behavior and safe cleanup boundaries.

Only after all closure conditions pass, deliver one Windows native GUI with its PowerShell live log
(no separate Live Log window), exact source and restart command, consolidated manual checklist, measured
changes and limitations. Confirm responsiveness, then hand control to the user. A slice, commit,
compaction or pending CI is not a stopping condition. Genuine authority/resource blockers are reported.
Manual findings receive affected/adjacent revalidation and an updated delta checklist, not automatic
whole-suite human retesting. Merge only after explicit final-source acceptance and permission.

### Current slice / next step

Git recovery: product branch `cleanup/module-quality`, HEAD `f3554558`, 146 commits after baseline
`4770b049`. Original checkout UI/test/settings dirt remains protected. Recheck Git after reboot;
old session IDs and plan text do not prove a process is running. No manual candidate or merge request.

**Current work — shared UI callback/test cleanup and scripts; module2–6 closure gaps and explicit decisions remain open.**

**Bounded7J — retire test-only window bounds forwarder.** Full main geometry lifecycle373/placement439
and direct185/193/integration332 retain sole Qt restore/show/persist owner and pure multi-screen policy.
Only lifecycle.position_bounds has one test caller and no runtime/script/config/doc consumer; it repeats
the live pure usable_window_position_bounds adapter. Migrate that first-launch assertion to the actual
pure helper plus native frame_extents, preserving every geometry assertion; remove only the unused
method/import. Keep policy accessor used throughout geometry tests, actual bounded_position used by
MainWindow, saved settings and0/250ms recovery timers. No visible placement/timing change, new owner
or user settings write. Three suites before/after, Windows actual Qt platform where available; review
actual diff/callers and Ruff, commit independently; then continue module audit, not handoff.
Result:31geometry+6seed baseline37passed4.49s on Windows Qt windows; migrated first-launch1passed0.50s,
retained geometry31passed2.26s after. Production-27, testnet+8, zero case removal; exact policy/frame
assertions unchanged. Independent actualdiff review approved, Ruff/format passed.

**Bounded9B — strengthen actual RNG reproducibility evidence.** Utility audit full seed90/direct79
retains shared real Python/NumPy/Torch state ownership. Existing restore test captures and restores
without advancing generators, so an omitted restore can pass. Replace it with actual draws, advancing
all three streams and then verifying exact replay; strengthen set_seed with repeated real draws.
Preserve original state in finally, isolate only CUDA availability, keep actual CUDA configuration/
state seam cases and automatically generated seed assertion. Add rejected malformed-state/CUDA-unavailable
cases proving no partial CPU mutation. Production unchanged, no model/download/GPU allocation or
scientific reproducibility claim. Original six-case baseline, stronger focused suite, intentional omitted
restore fault must fail, main nonauthor review and Ruff before tests-only commit.
Result:9passed2.18s, original6 cases preserved/replaced plus3 new. Main review corrected CUDA
atomicity fixture to use requestedseed123 versus currentseed456; same-state input would miss premature
mutation. Three separate in-memory omitted Python/NumPy/Torch restore faults fail each exact stream,
and moved CPU mutation before unavailable-CUDA rejection fails fourth case. No faulty source written.
Ruff initially flags intentional experiment random.random as non-cryptographic; file-scoped S311
annotation documents exact test purpose, formatter/Ruff then pass. Only CUDA availability is isolated
for CPU cases; real CUDA allocation/reproducibility is not claimed.

**Bounded9C — replace mock-only VRAM warning tests with actual widget conditions.** Full main checker124/
direct147 finds one no-assertion negative case, two identical snapshot helper cases and policy tests
mocking both predicates. Preserve existing heuristic/copy/public behavior (not resource admission).
Use real QMainWindow/QStackedWidget/QTabWidget and immutable runtime snapshots, isolate only modal
show_alert. Cover initialized local+active3D warning, other tab/hidden/other workspace/no local,
explicit switching entrypoints, unavailable snapshot and lazy placeholder. Migrate assertions to
check()/on_viz_tab_changed results, retire exact duplicate/private-helper cases only after stronger
baseline. No production change or GPU/model invocation. Focused original and stronger suites,
intentional ignored-local or ignored-tab guard fault, main nonauthor review/Ruff; no handoff claim.
Result:13original0.09s ->23stronger0.15s ->10retained0.13s. All old behavior assertions migrated to
actual widget conditions, including non3D signal ignored and exact warning copy; one literal duplicate
and no-assertion path replaced. First stronger run22pass/1fail exposed fixture.show overriding stack
hiding; fixed fixture order, removed import-time QApplication, retained assertions. Omitted local and
tab guards each fail at unexpected show_alert. Production unchanged; tests+163/-124/net+39; Ruff pass.

**Security utility audit disposition.** Independent full filesystem_identity1115/direct121,
public_diagnostics1897/direct2256, structured projection531 and runtime collector71 retain live
descriptor/handle identity and single fail-closed privacy boundary. Tests exercise real hostile inputs,
budgets/cycles/idempotence and recovery-text preservation; no justified duplicate deletion. Runtime
collector intentionally returns internal filename/GDF details to dataset/preprocess state services.
Main traced state_builder->typed snapshot/query; model state-card assembler423–496 selects counts/
readiness, not raw diagnostics. ToolCommandResult.to_payload uses public_safe_result_projection and
final public_diagnostic_value for nested state/diagnostics. Raw internal snapshots are not public-safe
payload claims; no new leak or sanitizer rewrite justified by these internal fields alone.

**Bounded7K — retire orphan error decorator capability.** Full main utils/error_handler81/direct182
and actual exceptions141/application errors246 audit finds all three bespoke subclasses, handle_error
and its private message/storage helpers have only11 exclusive test callers. Git-wide source/config/
script/docs search and utils package exports show no registration/decorator use. Actual backend
XBrainLabError/subtypes, application map_exception and UI error presentation remain separate live
boundaries with retained real privacy/hostile-protocol tests; do not move these into the retired file.
Delete exactly orphan source/test file after original+live exceptions/results baseline, independent
caller/privacy review, then same retained cases. Production-81/test-182, live owner0delta, no public
Command/query/Assistant or visible semantics change; unknown external convenience imports are not
preserved per stage authorization. No replacement wrapper or new policy. Commit independently, then
continue shared UI/scripts audit; a failed permission decision stops only this deletion, not other work.
Result: original decorator11 plus live mapping/privacy25 and styles25 baseline61passed6.92s;
retained live exceptions/results25passed5.38s after deletion. Independent actualdiff/caller review
approved; public error/privacy owners unchanged. Only orphan source81/test182 lines removed, no data.

**Bounded7L — remove unused theme/registry surface.** Full independent and main icons52/direct65,
theme192/direct133 plus actual AgentManager474/settings button3128–3197 and AppConfig owner74 read.
Six icon entries reference absent assets and have no consumers; the only real SETTINGS.path forwards
literal settings.svg to AppConfig.get_icon_path. Use that existing owner directly in AgentManager and
the actual QIcon pixel test, then remove whole Icons module and its four exclusive registry mocks.
Retain actual settings.svg and standardIcon fallback unchanged; no visible UI/art change. Remove six
unused theme tokens and test-only get_style_sheet/three exclusive tests, not Stylesheets.MAIN_WINDOW
or live Matplotlib styling. Strengthen actual figure/axes/legend color assertions before retirement:
current not-white/legend-exists assertions can miss a styling no-op. Keep existing case shapes and
live color/style semantics. Baseline icons/theme/actual dock-titlebar test, stronger pre-delete then
retained after; exact path equality/pixel assertions, intentional no-style fault, Ruff and independent
actualdiff review. Three production files netnegative, ownerdelta0, no generic registry replacement.
Result:25original ->25stronger6.52s ->18retained6.49s. Seven exclusive registry/stylesheet cases
removed only after stronger live evidence; six actual Matplotlib cases remain. In-memory styling
no-op fails five exact color cases (one None case passes), proving detection. Production+2/-86/net-84;
tests net-8; independent actualdiff review approved and Ruff/format passed. No asset/layout change.

**Inventory corrections.** Current Windows setup launcher is87lines, not earlier187 typo. Installer
integrity tests belong to tests/unit/scripts/test_windows_source_bootstrap.py, not the UI local-bootstrap
suite. Main corrected the misattributed inventory row and then fully read the actual340line UI suite:
real dialog/runtime/settings behavior retained; its256MB-per-file fake weights need a bounded fixture
budget reduction (not model admission weakening). Reading that suite is not installer evidence.

**Bounded9D — shrink runtime-readiness fake weight fixtures.** Three fully audited suites (UI
local-bootstrap340, config761, runtime-inspection383) create seven256MB fake weights per full run;
they test settings/selection/readiness/classification, not production model size policy. First measure
actual fixture file counts/logical bytes on the existing Windows environment with pytest-owned
temporary cleanup, retaining all assertions. Then explicitly inject a test-local scaled minimum and
write tiny real weight files in the existing helpers; no global/autouse patch, mock cache-complete,
new shared fixture framework or production admission change. Preserve metadata/pinned revision and
real Qt inspection workers, wait through their terminal state before fixture teardown. Production
unchanged. Same three suites before/after, byte measurement, unchanged catalog tiny-weight rejection
and deliberate empty-weight fault must fail. Main/independent actualdiff review and Ruff; continue
catalog/lifecycle fixture audit separately, not final handoff. No real model/cache/env deletion.
Result: same72passed before7.72s/after6.34s; measured fake-weight logical bytes1792000000->7168
across7files. This is not physical disk reclamation or a stable speed claim. Production unchanged,
tests+52/-33/net+19, zero removed assertions/cases. Three empty-weight injected cases fail their
actual readiness/classification assertions; unpatched256MB minimum plus tiny-weight rejection passes.
Independent actualdiff/lifetime review and Ruff pass; all test artifacts use pytest temporary cleanup.

**Bounded9E — scale catalog/lifecycle fake weights without losing admission boundaries.** Full
independent catalog655/lifecycle659 and main affected helpers/callers show300MB complete/150MB shard
fixtures only cross the256MB minimum; no actual model loading/process download uses them. Baseline
both suites with temporary cleanup and measured logical artifact bytes. Replace giant weights with
real1KiB files and explicitly opt affected cases into a local threshold fixture (not global/autouse).
Keep default-size rejection outside that fixture, add below/equal/above scaled-limit assertions;
shard test must reject a missing shard even when its present shard alone meets total minimum.
Preserve actual pinned metadata, symlink/hardlink guards, partial quota accounting, Qt thread/terminal/
cleanup assertions and fake downloader external isolation. No production/runtime/download policy or
user files changed, no shared fixture platform. Same focused suites plus small boundary cases,
intentional missing-shard and strict-greater-than faults, independent actualdiff review and Ruff;
commit tests-only and continue remaining module audit, not manual handoff.
Result: original50passed3.59s, stronger54passed0.77s, weights20paths4800000308logicalbytes ->
24paths21812bytes (four added boundary/policy cases). First baseline attempt49pass/2errors was an
ephemeral measurement-hook conflict with mocked scandir; isolated measurement scan and repeated once,
no product/test assertion changed. Strict > instead of >= fails exact-limit case (other2pass);
omitted missing-shard check fails despite present weight meeting minimum. Production unchanged,
tests+61/-18/net+43, independent actualdiff approved, Ruff pass. No physical disk/speed certification.

**Bounded7M — retire MainWindow test-only global loader bypasses.** Independent source1–240 and
Git-wide dynamic/config/script/doc audit identifies seven None compatibility globals and three
globals().get early returns, with only five InfoPanelService test patch sites. Actual three lazy
loaders, module imports, panel import lock and GUI-only preparation flags remain sole owners. First
baseline main-window sync/launch/lazy-completion suites; try removing the five obsolete service mocks
so those cases compose the real lightweight InfoPanelService. Preserve controller-free typed-port
and real widget assertions; no new fake/adapter unless an actual external seam requires isolation.
After passing migrated tests, remove the unused globals/bypass branches. No visible UI, eager import,
timing/shutdown/publication change, ownerdelta0. Same focused suites plus independent actualdiff
review/Ruff; one independently reversible commit, then continue inventory/remaining tests/scripts.
Result:121before11.01s; six migrated real-service construction cases pass0.58s before removal;
same121after11.03s. Production-19/test-5, no cases/assertions removed. Independent actualdiff
review approves lazy/thread/startup invariants; Ruff passes after restoring one required import/class
blank line. Seven unused globals/three bypasses gone, real InfoPanelService used in all five patch sites.

**Bounded9F — consolidate all-page refresh behavior evidence.** Full independent MainWindow sync
3052lines (93definitions) retains real Qt/service/render/thread cases and distinct shutdown gates.
Five one-page positive refresh cases duplicate the same shape; existing stronger only-target case
covers training only. Parametrize that stronger case across all five pages and pass before retiring
the five weaker single-page cases. Assert selected refresh exactly once and all other panels untouched
through MainWindow.switch_page, not a mocked refresh policy. Keep nav checked-state, delegated refresh,
publication/status and all lifecycle assertions. Original7M121case baseline covers these six cases;
focused stronger10 then retained5 mapping cases, intentional wrong-page/all-pages refresh fault,
independent actualdiff review/Ruff. Production unchanged, one fewer case only with stronger evidence;
no new helper framework, native/manual model claim or module closure inferred.
Result: six old mapping cases covered in7M121baseline;10stronger0.62s ->5retained0.58s. Tests
+6/-34/net-28, production unchanged. Wrong-page in-memory fault fails4/5; all-pages refresh fails5/5
at exact selected/non-selected assertions. Independent actualdiff review and Ruff pass; unrelated
navigation/delegation/publication/shutdown cases unchanged.

**Bounded9G — retire misleading publication test duplicates only after preserving their nuances.**
Full main/independent primary publication suite570 uses real panels/Observable/Qt timers with narrow
render/query isolation. Dataset-only case's controller is never wired, so its notify proves nothing;
Preprocess-only case overlaps all-three-panel ledger evidence. Main identified two details not yet
subsumed: idle-before-any-event25ms negative window and repeated identical pending revision before
first render. Fold both into existing all-panel commit/coalescing cases, pass strengthened baseline,
then remove only those two superseded cases. Retain query failure/row preservation, queued filtering
readiness, transient training updates, retry/backoff/cleanup/stale and synchronous-command no-refresh.
Production unchanged; no reset of publication policy or mock readiness. Original/full stronger/retained
suite and an intentional premature-render fault, independent mapping/diff review/Ruff. The retained
bounded negative-observation window is test evidence, not an introduced UI wait or speed claim.
Result:32original8.68s ->32stronger8.81s ->30retained8.67s; productionunchanged, tests+5/-37/net-32.
Idle spontaneous-render fault fails all3 exact no-render assertions; same-pending immediate-render
fault fails all3 pre-queue assertions. Main corrected review's initially incomplete replacement map
before deleting anything; independent final diff approves, Ruff passes. No source fault persisted.

**Bounded9H — remove blind waits from navigation smoke when measured state evidence permits.**
Full main/independent integration smoke194 and shared test_app fixture retain real Study/MainWindow,
lazy panels and exact dock/stack assertions. _click always waits50ms, regardless of ready state;
measure count/helper duration and full-suite baseline first. Replace fixed delay with existing
_wait_for_panel at navigation assertions and explicit bounded dock-visibility waits; retain all
current state/type/ownership assertions and remove only unused EXPECTED_EVALUATION_TABS constant.
Evaluation intentionally supports bottom long-label and chart short-label layouts (source1974–2130),
so both labels remain accepted; this is not a copy defect or UI change. No production edits, model
activation/download or environment change. Same suite before/after, actual click/wait measurement,
Ruff/main+independent review. Report measured helper overhead only, not application speed or native
manual acceptance. Keep meaningful negative-observation waits in other tests; do not strip waits globally.
Execution resumed after9J settings isolation and85-case native validation below; no9H edits yet.

**Bounded9J — isolate actual Qt settings before more GUI tests.** Main found three live Python
QSettings consumers: main-window geometry, montage preferences and SmartParser settings. Test root
has no QSettings isolation; montage tests attempt NativeFormat.setPath, ineffective on Windows/macOS.
Read-only Windows probe confirms setDefaultFormat(IniFormat) does not alter the two-string org/app
constructor (stillNativeFormat), consistent with [Qt's constructor/setPath documentation](https://doc.qt.io/qt-6/qsettings.html).
Do not run further native-preference-consuming tests until isolated. Previous preference changes
cannot be excluded without before-state; do not claim no QSettings side effects or restore guessed
values. Root settings.json/model/data/env remain out of scope and untouched.
Scope: tests-only fail-closed isolation at the actual Qt constructor seam, preserving real per-test
INI serialization/roundtrip instead of Mock settings. First validate that scoped monkeypatching the
real QSettings.__init__ reaches existing imported aliases without eager UI imports. Audit actual
overloads and teardown order; avoid generic storage/control framework and extra temp allocation for
tests that never construct settings. Add red path/format assertion before any write, then isolation,
roundtrip and per-test reset tests; retire ineffective montage NativeFormat path/env redirects.
Keep production QSettings/native behavior and existing geometry-specific fakes unchanged. Focused
isolation/geometry/montage/SmartParser and9H baseline only after safe routing, independent safety/diff
review/Ruff. Necessary shared-fixture evidence may widen only to affected UI paths. Native registry
persistence is not claimed by INI-backed tests; required out-of-process gates retain separate review.
Result:4 red cases fail on NativeFormat before any write; isolated5 cases (including explicit INI
pass-through) pass0.30s. Affected85-case offscreen run83pass/2montage height failures; same assertions
on verified Qt windows platform85pass15.26s, with18 MNE/NumPy deprecation warnings. Keep offscreen
geometry limitation visible; no weakened assertions or claimed native registry persistence. Scoped
real constructor patch reaches imported aliases without eager UI imports; ineffective four NativeFormat
and six XDG redirects retired. Independent actual-diff/fixture-order review approves. Production unchanged.

**Reviewer-capture disposition.** Full independent script1629/direct767 plus actual handoff registry
and manifest consumers retain ui-reviewer-fixes as a required gate. It owns real A01T preview/time/PSD
curves, history/normalization/resampling/SmartParser/import-review states and unique multi-method/split
geometry evidence. App-polish/baseline overlap conceptually but no equivalent per-surface contract was
proved. No script/test/gate deletion; any future surface migration needs an explicit evidence-preserving
decision. Source inspection is not a newly executed capture or performance result.

**Module8 CI/Poe disposition.** Independent full ci925/docsworkflow83/pyproject314 plus routing109,
artifact verifier216/direct311 and reliability409/UI40/data58/integration-trigger24 retains distinct
Linux coverage shards/coverage-only aggregate, platform/native/data/visual/provenance gates. Repeated
setup occurs on isolated runners; aggregate already avoids full Poetry environment. No measured
redundant install or equivalent removable gate found. Existing developer CLI tasks remain live public
entrypoints, not orphan Python helpers. Docs workflow's direct bounded dependencies duplicate docs
group constraints without lock-exact install; record as a reproducibility decision candidate, not an
authorized environment migration or speed claim. This is full source audit, not same-head CI success.

**Module7 logging audit.** Independent full logger874/direct1304, run.py370,
Windows/WSL launcher sources and tests traced console output: StreamHandler binds native stdout;
CP950/strict cannot encode actual metrics `≈`, losing/noising that console record while UTF8 file
logging remains intact. Reproduce with a real strict encoded stream before any console-boundary fix;
do not change metrics copy, global/user encoding, redaction policy or introduce another log window.

7A is committed e6aa7d44: console fallback preserves already-redacted records, UTF8 file fidelity and
user stdout policy. Real strict CP950/ASCII/UTF8 streams test both sink orders; arbitrary third-party
stream partial-write atomicity is not claimed. Eight POSIX storage cases remain Linux CI obligations.

**Controller test audit completed (not module closure).** Independent full unit5429/integration582
reads retain typed receipt/confirmation generation, strict envelope, stale/duplicate terminal and
handoff contracts. High-mock units isolate real narrow seams; actual QObject/AgentWorker/QThread
integration covers nonblocking RAG/stop/setup rollback. No justified obsolete/duplicate case found;
neither suite alone claims real model/tool execution. Chat/AgentManager full test audit continues.

6Q retired unused snapshot serialization only; all typed fields/device/activation validation remain.
The six-state fault matrix catches five omitted-validation failures; string activation id is separately
rejected by coordinator correlation. Removing its two exclusive serializer cases is not reduced gate scope.

**Latest full UI reads (not closure).** Independent panel2349/controller483/history235+62 retains
sole backend transcript owner and bounded Qt reconciliation, stale deltas, reader-anchor/tail-follow
and typed confirmation/runtime controls. Zero-delay coalescing and capped8ms anchor retries are not
measured redundant waits. 6T removed the proven ignored-column/redundant-reflow and unused render paths after caller/geometry evidence. AgentManager direct3769 retains actual Qt/Study/
ApplicationService publication and real-controller debug blocked-command cases alongside isolated
manager correlation mocks. 6R replaced the zero-assert processing case with real widgets and removed only two exact duplicate
model-forwarding/dock-toggle cases after main nonauthor review.
Direct panel3041 now fully independently read: actual Qt runtime/confirmation, chunked rebuild/deltas,
prune/reader anchor/tail, resize/code/text geometry and clear lifecycle retain. Compatibility append
tests need caller migration evidence before retirement; no blanket deletion of rendering protection.

6R replaces the zero-assert processing check with actual ready -> Working/disabled -> Send/enabled
widgets; two exact duplicate cases retired.6S retains literal conversation append/prune/clear and
controller history field access; four exclusive convenience cases retired. Windows pre-import probes
can emit a Qt font-directory warning, but actual fault failures were state/order assertions.

**Additional chat widget audit.** Full independent action_card783/message_bubble776 retains exact
typed request capture/disable-before-emit and safe link/Markdown/streaming/geometry handling. Full
composer144/suggestion167/segmented98/styles753/package6 retains IME/bounded input, live model-setting
selection and shared design tokens. Direct action_card438/bubble824 tests fully read: exact request,
doubleclick, privacy/HTTPS confirmation, Markdown streaming/reuse and geometry evidence retained.
6T removed only proven unused conveniences and redundant row relocation; hidden icon/style remains.

6T places unchanged suggestion rows once; at400/620/900, five reflows each remove/add15+15 ->0+0,
with exact equal geometry/text/order. This is work elimination, not a wall-time speed claim. Deleted
panel._render_message, bubble.setText and ignored icon argument; typed rendering, script-used
append_message and hidden icon widget/style remain. Native Windows/DPI handoff remains required.

6U removed only _optional_str_list after full application_surface1687/direct264/authorized_paths303/
result_contract538 audit and caller/config/script/doc search. Formal contracts unchanged. Existing
ToolCommandResult.to_payload privacy/capability evidence also lives in controller5289, feedback82 and
execution coordinator92; absence in one direct file is not an overall coverage gap. Final byte-fit
behavior still needs bounded test/caller review.


**Publication/turn audit.** Full main presentation199/turn_state141/direct121+63 retains typed view-only
progress and exact admission/stop/terminal lease ownership. Independent coordinator251/direct149 and
actual AgentManager callers retain newest-revision retry/cadence and originating-turn training notice.
Stored training handoff_generation is unread after admission; retain admission validation pending a
bounded field-only cleanup decision. Manager/long-session evidence, not direct149 alone, protects
stale/missing run identity and exactly-once transcript delivery. Tool definitions/authorized paths and
remaining worker/runtime audit continue alongside inventory reconciliation.

**Tool/path audit correction.** Full independent definitions1+116+65+159/base65/registry62/tools-init288
and direct126+95 retain live schema providers and the18-tool projection. Full authorized_paths743/
direct303 initially misclassified the whole path capability as orphan; main challenged verifier968's
generic root branch and independent re-audit confirmed live scan/preview/recipe admission consumers.
Retain authorize_existing_path and POSIX/Windows identity checks. Only retained-handle open/grant
consumer absence is a retirement candidate; downstream backend IO protections were not examined in
this bounded audit, so no end-to-end TOCTOU defect is established. Do not delete the whole capability.

**Completed shared UI/runtime audit (not module closure).** Full capabilities1654/direct1610,
renderer428/direct377 and runner431/direct509 retain existing publication/Qt owners. Full main and
independent info_panel626/direct605 retain detached13row rendering, preprocessed precedence and actual
narrow/DPI/font/scrollbar geometry. Full service131/direct238 retained committed rows and weak listeners;
7D removed only unused Study retention. Full sizing60/direct24 and button policy78/direct97 retain
two-surface exact-pixel sizing and global post-style/safe Cancel policy. Full modal406/error319/common463/
BaseDialog209 and direct448/26/891/138/147 retain shared confirmation, geometry and diagnostic privacy.
Completed slices and evidence are in the table below; no unresolved item is closed by their test counts.

**Completed-slice qualifications.** 6V was explicitly approved by user
「同意移除未使用的整段能力與專屬測試」 after rejection before mutation; separate6E/6G remain untouched.
Its14stage/stale typed fixtures preserve133367bytes, SHA256
e5e84c01e0b44eac4ab4c8fe183969cc32adbeef90550c3b1d2eb22fb6f64872; not real-model/scientific evidence.
6Y reviewer initially confused LocalRuntimeProcessOwner alias with child core.engine.LLMEngine, then
checked actual constructor/callers and withdrew the injection-only blocker. Real QObject/load-thread
fixtures retain owned async initialization; no external monkeypatch compatibility claim.
7C intermediate test caught a removed QWidget import needed by a live chart; restored, final50pass.
7G initially39pass/3fail under Windows Python offscreen with missing fonts: message height30/minimum15,
unchanged after event drain. Same42pass on actual Windows Qt before/after and offscreen with installed
fonts. 9A defaults that existing directory in direct pytest, matching existing CI without product font/
assertion changes. Earlier Windows-interpreter offscreen counts are unit/component, not native-window
acceptance. Local MkDocs remains unavailable; final same-head CI docs validation is still required.
8H initial oversized-byte pytest ID caused Windows temp-path setup errors; explicit short IDs repaired
fixture only. Initial fault run with that error is invalid; corrected SHA-bypass gives1failed/2passed.
Public fixture SHA triggered detect-secrets; exact known test checksum annotated, hooks then passed.

**Module8 setup audit.** Full independent setup881/PS87/rootCMD20/direct436 retains
cmd->PS1->Python->existing model lifecycle ownership. Integrity evidence improved8H; orchestration
order/env failure-stop and wrapper argument forwarding remain bounded test-quality candidates.
Full WSL launcher CMD42/PS1276/direct89 retains console-only child output, bounded log retention,
exit propagation and safe optional IBus; source guards are not native launch/wait evidence.
Independent initially proposed integrating infraacf7c56d; main challenged absent product paths. Exact
Git has no compact/manual_environment tracked files and common ancestor4770b049, not a dependency.
Recommendation withdrawn: retain separate infra history, do not import absent tooling to withdraw it.

**Shared async handoff audit.** Full independent router260/host1004/interaction624 and direct265/939/
343/616 retain request-correlated session terminal-once, continuation leases, cancellation, stale
navigation and synchronous failure delivery. Host, interaction session and Assistant pending coordinator
have distinct live responsibilities, not duplicate state owners. Main traced actual MainWindow callbacks.

**Bounded7H — use actual lazy-navigation callback contract.** Sole production host is constructed by
AgentManager with real MainWindow.switch_page(index,on_ready,on_failed). Remove signature inspection,
optional failure callback and no-ready legacy path; keep generation/one-shot/reentrant failure/exception
cleanup and current UI messages. First migrate existing test doubles to explicit on_ready/on_failed
contracts and real immediate/deferred callback delivery, preserving all outcome/cancel/stale assertions.
Characterize full router/host/outcome/interaction suites and actual lazy MainWindow callback tests
before source changes; after identicalcases, fault dropped failure callback must fail. One production
file expectednegativeLOC/noowner/public/UI change, two direct test files at most; independent actual
lifecycle review/Ruff before reversible commit. Keep pending publication/admission owners untouched.
Result: migrated characterization94passed0.93s before, identical94passed0.85s after; production
+13/-42/net-29, tests net+13, no cases removed. In-memory omitted failure callback fails actual
MainWindow terminal-count assertion (1failed0.26s); faulty source never written. Independent actual
caller/lifecycle review approved; Ruff/format six7H/7I files passed. Integration callers use actual
MainWindow, not the retired compatibility route. Existing closing-window False/no-callback behavior
still relies on host/controller abandon; this slice does not claim to improve that boundary.

**Bounded7I — remove unused stateless presentation residue.** Full main language111/direct188,
status401/ownedpresenter132/direct320 and refresh50/direct78 plus caller sweep identify unused
COMMAND_LABELS alias/import and command_labels helper; _display_progress ignores completed/total;
refresh_panel only forwards to _call_noarg with literal update_panel. Remove unused labels and ignored
arguments; inline only private noarg helper into existing refresh_panel, preserving exact logging,
guard release, status timing/copy and every active caller. Three production files expectednegativeLOC,
no new owner or visible behavior. Baseline product-language/refresh/ownedpresenter suites, same tests
after, main actualdiff/lint; no case removal. Separate commit from7H, continue audit rather than handoff.
Result:40passed2.55s baseline,40passed2.52s after; production+2/-20/net-18, no test or owner changes.
Main actualdiff/caller review and changed-file Ruff/format pass. Earlier7H/7I terminal outputs lost
during context recovery were not counted; the recovered runs above provide the evidence.

**Module6 initial full owner audit (not closure).** Independent full controller2949/attempt898/
execution342/confirmation314/pending443 and respective direct confirmation154/pending560/execution151/
closure91 plus controller4625–4805 retain one host-turn/Qt orchestration, deterministic admission,
one pending correlation owner and authoritative ApplicationService expected-generation execution.
Real tiny-FIF product-flow528 proves a current direct-input receipt makes one resample without model/
RAG and stale receipt makes none; it does not prove confirmation-card approval through real mutation.
No controller split merely for LOC: lifecycle/presentation delegation already exists, with no proven
competing owner. Remaining helpers/direct suites/model/RAG/UI/scripts still require full audit.

**Pending explicit decision6E — retire unused stage prose and unreachable history suppression.** Full pipeline190/
direct298 and assembler835 audit, plus independent exact caller search, find STAGE_CONFIG's seven
system_prompt values unused by runtime: assembler and evaluator consume only tools. Preserve that
live stage/tool ledger, public membership and all actual generated prompt bytes. Before deletion,
compare full prompts for all seven fixed-publication stages with unique sentinel prose substituted;
also record exact before/after prompt digests. Remove only prose builder/values, unused fallback
prose/docs and exclusive prose tests; retain tool-stage and label assertions. Separately remove
receipt_question whose sole caller always passes None, retaining selected/sanitized bounded history.
No model/prompt experiment, new owner or compatibility shell; approximately-120productionLOC across
two files, owner delta0. Full stage/config/context baseline and retained after, exact output comparison,
Ruff and independent actualdiff review are required. No UI behavior change or confirmation-policy edit.
Stop this slice at verified output-preserving deletion, then continue module6 lifecycle/tool/UI audit.
Baseline92passed0.89s after imports; all seven fixed-publication prompt bytes remain exactly equal
when old prose is replaced with a stage-unique sentinel. Edit review rejected removal as potentially
external-contract-sensitive and correctly caught malformed generated source (nested closing lines
were not removed). Restored both uncommitted source files to5afdb10d with apply_patch; tests unchanged,
clean Git confirmed. Do not retry the rejected retirement without the separately requested approval.
No malformed source was committed or handed off. Corrected construction and full parse/output checks
would be required if approved. This item is not completed and does not block unrelated module work.

**Module6 async responsibility audit.** Independent full worker1065, RAG thread214/process466 and
their six direct suites2193 retain actual load/generation ownership, correlation/cancel fencing,
restart-required state and production child/queue/monitor lifecycle. Thread lifecycle remains the
intentional injected retriever seam; production process lifecycle has real spawned-process tests.
No measured redundant wait found; preserve close grace, deadlines and monitor polling. Candidate6F:
four diagnostic-only properties on each RAG lifecycle have no product caller; process has_active_process
is live in native shutdown and must remain.

**Pending explicit decision6G — retire bypassed legacy direct-tool forwarding.** Full real adapters/definitions/registry
audit plus main package288/coordinator path/guard review proves all18 contracts are9 Application
commands and9 UI requests; READ_ONLY projection is empty and pinned by actual surface tests. Mapped
commands always execute through application_surface; a missing mapped result fails closed before
legacy tool.execute. Remove seven unused Real command adapters (two modules), their now-orphan
execute_real_application_tool/context-binding chain and coordinator's unreachable wrapping branch.
Instantiate existing schema definitions in real registration (concrete execute intentionally raises
if incorrectly called), preserving names/order/descriptions/schemas/confirmation and switch-panel
live UI request adapter. No empty subclasses, replacement owner or execution route. External direct
Python Real adapters cease to be supported under the approved unused-convenience policy; model/UI/
formal Command contracts do not change. Remove only exclusive high-mock forwarding tests and the
guard/fixtures that enforce those retired adapters; retain actual command ownership/negative mapped
fallback, generic tool contracts, UI request and real application workflow evidence. Approximately
-240productionLOC across4files, owner delta0; guard retirement is not a general gate relaxation.
Before edits run surface/coordinator/controller/debug/registry/architecture +real product-flow focused
baseline and snapshot exact18 schema/confirmation payloads. After deletion compare exact payloads,
same retained tests plus6B real confirmation cases, Ruff and independent main nonauthor actualdiff
review. Stop slice only at verified complete dead-chain removal, then continue remaining module audit.
Baseline602passed42.55s, three MNE deprecations; exact18 schema/description/confirmation SHA256
ec17216b9683a2ae275511a83cbbce037c62b9729c0b753e9cfc02dd879e74db. Worker owns only declared adapter/
coordinator and exclusive guard/test files; main owns after verification, plan and actualdiff review.
Safety review rejected the whole write before any change, classifying the legacy adapter removal/
base registration as potentially public-tool behavior. Worker verified all seven scoped paths clean.
Concrete external direct-Python API removal approval requested separately; no split/indirect retry.
The baseline/digest and independent whole-chain audit remain evidence, not permission or completion.

6N92d6a091 retires only unused tolerant parser/strict-result convenience. Before removal, malformed
field fixtures were fixed to include workflow_stage so they actually reach type validation; bare
evaluate rejection moved into the retained malformed matrix. The first strengthened run404pass/1fail
uncovered6P's Windows capture newline defect; after6P the complete baseline452passed, then retained
403passed21.31s after exactlytwo diagnostic cases were removed. One MNE warning persists.57exact
parse-result payloads before/after share SHA2562634fe1b345c4c129ee13a3f370c5ad01d5f08c654a02f207f9bf054623e7428.
Omitting the parameter-type guard fails null/string cases; actual strict grammar/negative guards unchanged.

**Module6 completed reads and remaining candidates (not module closure).** Full core model download
lifecycle665/direct659 and downloader1086/direct1178 retain shared lifecycle composition, bounded
consumption/inactivity, conservative process ownership/reap/retry and terminal-after-reap. Confirmed
unused shutdown(wait_ms) argument and cleanup-result message alias are retired by6O above.

Full context_encoding712/direct683 retain exact-type admission, cycle/node/UTF8 limits, path/secret/
role sanitation and final assembler re-encoding; no serialization or model-obedience gap established.
Only unused CHARS constant alias (same BYTES value) is a candidate. Full intent935/training_request75/
prompt_policy215 retains RAG suppression classification, not host action routing. path_label_for_intent,
BlockedExplanationIntent.target_command/ambiguous and test-only prompt payload helpers are candidates;
do not alter classifier semantics, actual prompt bytes or recovery taxonomy without separate review.

Main full conversation76/direct51, runtime_snapshot120/direct43, coordinator289/direct290,
activity102/direct137, turn456, orchestrator362/direct211, confidence91/direct96,
decision55/direct115 and tool_feedback574/direct445 distinguish real typed/correlated state from
test-only convenience projections. Candidate runtime to_dict/from_payload/fallback aliases and
conversation get/index/equality/repr need full caller/test migration before retirement. Preserve all
typed snapshots, validation_error, publication/activation/turn/cancellation and actual history limits.
ToolRecoveryFeedback builder appears test-only; assembler recovery state must be fully traced before
retiring that chain. Actual summary/compact transcript payloads and public diagnostic bounds remain.

Source counts denote exact read versions, not current LOC or automatically approved closure. Main
reconciled50 existing core/RAG inventory rows; module6 direct controller/UI suites and other modules
still have uncovered ranges. Completed6B/P show concrete workflow/capture protection, not model or
manual acceptance. Preimported Windows probes exposed cp950 logger output failures; module7 owns
the unresolved logger/launcher defect. Both registered WSLs, sole Windows environment and real model/
dataset caches remain untouched; no repeated compaction. Continue independent authorized work.

Independent full runtime_lifecycle1531/dispatcher532/AgentManager2163 retain one UI composition owner,
one correlated runtime admission owner and one queued transport/QThread owner; controller owns its
worker thread. MainWindow cleanup-fence/retry and actual script diagnostics are live. Full direct
dispatcher529/delivery547/service1956/threading749 and integration lifecycle1303 retain distinct
admission, delivery timeout/stale, real command-thread affinity and real topology close/recreate
protection. No arbitrary AgentManager split or duplicate-test deletion justified. Only unread
RuntimeSetupOutcome.message and one-test is_queued property are future candidates; preserve important
expected_activation_id/turn_in_flight witnesses until equivalent behavior evidence exists.

Completed2AD–2AG and8C–8E are indexed below and fully traceable in Git. For source-bound Windows
capture tests only, use process-local GIT_DIR/GIT_WORK_TREE pointing to the actual Windows paths:
Windows Git cannot follow the WSL-absolute worktree pointer. Keep the existing identity guard;
do not edit .git pointers, shared environments or substitute a synthetic source digest.

**Module2 independent closure review.** Reviewer did not approve module closure: two confirmed
visible defects below remain unresolved, not merely documentation or LOC concerns. The audited
interior has one command spine, separate backend mutation/publication and UI draft/presentation;
large file size alone did not establish a competing owner. Three stale tracker pending rows were
actually inspected (montage capability80 +owner170, empty loader test package marker needed for
relative imports, DrawRegion148 +owner75–250). Reconcile these; DrawRegion belongs to module3.
Main fully read wizard runtime145 (real Scan/Preview/Validate +Qt draft handoff, intentionally invalid
FIF not actual EEG Apply). Main1–440 +independent441–1788 fully cover real-fixture wizard acceptance:
retain all five-step, exact fresh review, no-publication, cancellation/drain/retry and BIDS recovery
contracts. Optional fixtures were not run here; final required-source gate still applies.
Continue authorized module3 while awaiting visible decisions; do not markmodule2closed or handoff.

**Module3 progress and remaining boundaries.** Completed3A–3O/3Q are indexed below; full
chronology, baselines, correction details and reversible changes remain in their Git commits.
The actual prepared command spine now has real ordinary preprocessing, boundary ratio/multirecord,
RAM-before-deepcopy, BIDS receipt/reimport and display-alias materialization protection. Data/render
publication, immutable buffer copies, cancellation and SET_MONTAGE confirmation stay live; generic
callback-only epoch tests do not define a second public snapshot contract.

Module3 is not closed. Remaining obligations:

- Complete caller/test/script inventory reconciliation and independent closure review, including
  current dataset UI adapters and real-data/native lifecycle entries; zero pending rows is not
  a substitute for evidence or resolution of confirmed findings.
- Decide the documented split-artifact chain below; actual Generator/provenance/audit and receipt/
  rollback state remain intact. No restoration of retired picker-expanded indices.
- Shared-runtime module7 owns the native split-dialog center investigation: Windows QPA windows
  compact752/760 cases both pass (horizontal range0); offscreen30/22px overflow was a font/platform
  artifact. Native full layout26pass/1fail shows client center31px below screen center. Inspect actual
  frame/client geometry before requesting visible change; do not weaken assertions.
- Existing UI RAM presentation test spies Raw.copy, which is not the live preprocessing allocation
  seam. Actual no-allocation evidence is3H's deepcopy witness and omitted-guard fault, not that spy.
- 4E removed suppressed persistence from real-GDF training and successful OOM retry; actual safe
  checkpoint/EvalRecord reads now verify artifacts under pytest tmp paths. This is not GUI restart/reopen.

Evidence qualifications: 3G removed307 collected obsolete cases, not the earlier mistaken309
(actual108 trial-list entries times2, not109). 3E/F terminal output lost during context recovery was
rerun:291combined/25plotter passed. 3I's alleged third enum argument was a reviewer misread, retracted
without product edits. 3O fixture default class maps were corrected before the passing baseline.
3Q proves control synchronization/coalescing/real signal/shutdown, not precise restart latency.
No measured end-user speed gain, whole-module approval or final Windows manual acceptance is claimed.

**Module3 unresolved artifact decision.** Independent full validator123/direct45/schema134/split_audit1085
and thesis protocol285–375 audit found artifact writers have no product producer, but the documented
CLI/schema remain a public thesis evidence entry. Validator only checks reported audit and cross-split
overlap, not the full claimed schema/provenance. User asked asynchronously to retire the unused entry
or retain-and-align its contract. No deletion, acceptance-strengthening or scientific claim until choice.
Unused build_training_ready_state test helper is separately removable; actual saved split/receipt seam
helpers retain live integration callers. Continue independent cleanup; module3 not closed.

**Module4 bounded read-only audit (not closure or implementation permission).** Independent full
model_catalog892/braindecode_catalog408/catalog_contract20/model_holder117/input_contract201/
option909/training_service687/model_base.__init__7/training.__init__23 =3264source lines, plus
catalog662/model_holder114/option450direct tests. Subsequent full resource/runtime audits below
supersede the initial partial reads; whole training closure remains pending. Retain static
catalog browsing (no provider import), stable identity/provider admission, numeric/device/class-weight
validation, conditional model context and single configure/build/preflight/receipt owner. Actual
preflight differs intentionally from advisory preview. Catalog command-name helper/input aliases and
optimizer repr duplicate have no consumers; TestOnlyOption and its export are used only by exclusive
tests, while actual manager accepts base TrainingOption. Declare separate baseline slices before
removing these. Subsequent independent full TrainingManager2413/direct1122/training_runtime587 audit
retains real config/start-stop/wait/CAS/lease/rollback ownership; saliency724–2115 is module5's obligation.
Study110–360/shutdown180–245/pipeline tests1–230/integration1–250 remain partial, not full audits.
4B closes the real-manager startup restore evidence gap with a completed actual Trainer, retirement,
snapshot restore and an omitted-restore fault. Keep useful Thread/Event/identity tests.

**Module4 resource admission audit.** Independent full resource_guard2341/resource_preflight563/
resource_receipt322/training_resource_receipt517 and3371direct/integration test lines reviewed.
Retain advisory draft preview versus current authoritative start admission and distinct receipts;
exact scope/TTL/capacity/consume-before-start and actual Agent/Application/Qt paths remain protected.
OS/GPU/MNE isolation is justified, not a deletion target. 4C measured and removed the duplicate GPU
estimate (two model constructions/data reads become one), preserving the cancellation observation
between RAM and GPU queries. No draft-preview reuse or persistent cache was introduced.

**Documentation evidence limitation.** Consolidated plan passed audit_agent_guidance check (ok=true,
no errors). Strict MkDocs build could not start in the existing Windows interpreter: No module named
mkdocs. No environment/dependency installed. Final exact-source docs CI remains required; current
source-only consolidation is not a successful docs-site build or final handoff.

**Module4 main presentation audit (not closure).** Full MetricTab332/history497/modeldialog702/
optimizerdialog212/devicedialog94, metric tests155/history412 read. 4G retired test-only update_plot
and the history forwarder after protecting the actual set_series/reset/repopulate path.
Model dialog async provider, stable recovery identity and pretrained-weight handoff remain live;
Direct modelselection429, training setting1242/direct1321 and full panel/sidebar source/direct tests
are reviewed. 4H removed inert settings remnants, retaining actual saved-split recommendation evidence.
Model settings/identity and cross-module main-window obligations remain pending, not whole UI closure.

**Pending visible-state decision — zero validation metrics.** Actual offscreen TrainingHistoryTable
fed validationloss0.0/accuracy0.0 renders both cells N/A. Zero is a valid result, distinct from missing.
User asynchronously asked to authorize0.0000/0.00% with N/A only for absent metrics; no reply yet.
No product edit made. Continue internal cleanup; do not silently treat this visible issue as fixed.

**Pending visible-state decision — device recommendation adapter.** Independent recommendation owner604/
direct314 audit retained metadata-only formula/cache/provenance and all scope keys. Unused
cached_for_context is a separate deletion candidate. Real Sidebar device recommendation passes
prospective_device, while concrete _StudyApplicationUiRuntime/TrainingQueryPort omit it although
backend supports it. Real application_ui_runtime over Study reproduced the TypeError in Windows;
no signature mock or product file change. User asynchronously asked to authorize the visible device
workflow repair; no reply yet. ApplicationUiRuntime itself is the Protocol, not the concrete adapter.

Completed4I–4N and5A–5D/5G are indexed below; actual source, review and focused evidence
remain traceable in their small commits. Remaining decisions/audit gaps follow.




**Module5 entry audit / next declaration.** Independent full evaluator477/EvalRecord1344 and direct
evaluator173/eval352/metrics155/context532/integrity608/safe-store889 reviewed. Retain real torch
metrics/final evaluation/recompute and safe JSON+NPZ, identity/context/integrity/sealed publication;
real tampered artifact and MNE montage tests are necessary. Coupled renderer/visualizer/TrainingPlan
saliency paths were only sampled, so whole module5 remains open. Concrete candidates are unused
export_csv, standalone export_saliency and five saliency getter conveniences; each requires its
own plan/baseline and exact exclusive test disposition before deletion. Existing canonical EvalRecord
export/load and dynamic figures stay. No unknown-script compatibility or new artifact format.



**Module4 additional completed audits.** Independent full training_history417/direct159 retained as
sole detached JSON-safe projection. Full first-party model/requirements/holder plus direct tests
retain supported catalog/identity/minimum-input/real forward+optimizer boundaries. Full
training_contract9/reset30/submission65/synchronous_lifecycle365/publication_lifecycle582 and direct
reset60/contract32/synchronous574/publication597 retain exact reset ordering, typed host submission,
unlocked waits/locked final verification, retry/dedupe/supersession/close. Secure output paths518 and
safe-store889 were already fully reviewed; don't repeat reads as new coverage. Preview coordinator,
remaining training integration/script entries and final inventory still require completion.

**Module5 render owner audit (not closure).** Independent full evaluation_render1369/work139,
direct1267/205 and UI publication_refresh935 retain immutable DTO copies, exact selected identity
fences and shared owned-work claim/cancel/retry. Copies have a concrete isolation purpose; no new
cache or measured redundant allocation established. UI timer/worker tests use mock ports and do not
prove full native GUI acceptance. Two separate future candidates: unused _final_unavailable_error,
and legacy build_evaluation_model_summary string forward (migrate three test/helper calls to typed
result.text before deleting). Actual typed model-summary preparation/result stays. Full Evaluation/
Visualization UI audit is ongoing; sampled main-window/renderer paths remain incomplete.




**Pending explicit import-risk decision5E — provenance compatibility re-exports.** Independent full provenance925/
integrity872 plus exact-hash270/ownership138/integrity81/contextconsumer190 retain bounded exact
logical-C hashes, immutable sealing, schema/producer validation and surrounding cancellation fences.
No redundant SHA claim. Eight eval.py noqa-F401 aliases have no real caller; only architecture
compatibility tests and a guard requirement demand them. Remove those eight imports, exclusive
re-export identity test and the guard's must-re-export block only. Preserve actual three context/
producer class imports, domain owner's required definitions, forbidden record-local definitions and
mandatory direct-owner production imports. Rename misleading compatibility fixture/local constant
to record terminology and model minimal actual three imports in its fixture. Main reviewed exact
guard body; worker may own eval.py/tests architecture helper/directtest only after baseline.
Baseline ownership/exact-hash and actual record context before, same retained after with all negative
ownership tests intact, Ruff and independent actualdiff review. No runtime schema/cancellation/
publication behavior change; production-8, zero new owner/compatibility shell or new source guard.
Baseline39passed8.09s (ownership/exact-hash/current context). Edit safety review rejected both initial
attempt and one retry supplying the user's approved no-unknown-external-convenience policy; no files
changed. Gate requires a fresh explicit decision after disclosure that external imports from eval.py
would fail. User asked asynchronously; no reply yet. Preserve aliases and matching guard until then.
Do not bypass the gate with a different editing tool. Continue independent authorized module work.


**Pending explicit lifecycle-risk decision5F — dormant automatic saliency scheduler.** Main and independent caller audit
prove PostTrainingSaliencyAutomation is instantiated but never armed by production; its only active
arm calls are exclusive compatibility tests. Remove the220line class, exclusive imports/service
construction/callback/cancel/wait wiring and shutdown cancellation port; remove the dev native-stress
script's dormant idle probe, retaining actual job/terminal-delivery waits. Owner delta is one legacy
scheduler removed, zero new owner; no replacement shell. Preserve PostCommandSaliencyNotificationBoundary,
explicit SaliencyCommand, PostTrainingSaliencyTarget and scoped target context, runtime cancellation,
terminal publication/ack/retry/discard and timeout budgeting. Existing architecture already requires
explicit Compute Saliency as sole product admission; no UI/public command/schema change is intended.
First complete affected test reads and passing baseline. Remove only13 exclusive scheduler unit cases,
armed-only observer case, submission-only timeout case and automatic-thread-start failure integration
case. Migrate shared shutdown failure test to a live runtime cancellation failure and shared wait
assertions to remaining real runtime/delivery owners; preserve explicit-command startup/cancel/stale
and normal observer lifetime coverage. Approximate production-260, three production files plus one
script; main final diff/LOC and independent non-author lifecycle review before commit. Focused same
retained notification/observer/service/background/publication integration plus script evidence, Ruff
and source call-site sweep are required. No automatic closure of module5 or handoff claim.

5F original baseline448passed34.01s; migrated retained429passed33.60s against unchanged production.
The19 removed collected cases are15 scheduler-only parametrizations, one armed observer, one
submission-only wait and two automatic-thread failure cases. Live runtime cancellation failure now
proved close still discards delivery. Source deletion was rejected by edit safety review before
mutation: explicit approval is required after disclosing that external/manual service.post_training_saliency.arm
calls would fail. User asked asynchronously; no reply. Main restored all five worker-owned test/script
changes to HEAD so retained source keeps its protection. No source deletion or dummy replacement;
do not bypass the gate. Resume the tested migration only after approval. The now-exclusive runtime
submission-failure forwarding chain and manager helper are additional retirement dependencies for that
same decision, not grounds to silently delete the underlying live target/publication contracts.


**Completed bounded5H — no-op 3D scene internals.** Independent full base1548/head269/3Dview1749 and
direct baseasync896/cache391/time264/worker1273 audit plus main fullhead269 confirms definition-only
CHECKBOX_KWARGS/CHECKBOX_TEXT_KWARGS, empty _setup_scene/sole constructor call and unread self.save/
param[save]. Remove only those internals and the fixture's unused save key; sample_index routing,
actors/orientation/camera/control behavior stay. UI-internal behavior-preserving changes are explicitly
authorized; no visible change, owner addition or native lifecycle rewrite. Worker owns only head.py
and time-slider test after fullthree3D test baseline; main actualdiff/lint/after and independent
nonauthor review. Roughly-25productionLOC, oneUIfile; no screenshot equivalence/native3D acceptance
claim from controlled PyVista tests. Base/3D worker, cache, weakrefs and verified teardown are retained.
Same43passed6.74s before/6.50s after; main nonauthor actualdiff approved and Ruffpassed. Actual one
production file+1/-21/net-20; test+1/-1. No sample-index/control behavior or native ownership changed.

**Completed bounded5I — actual Saliency estimator-to-receipt evidence.** Full resource817/direct244 and
Analysis618/direct1409 audits found receipt tests patch preflight; integration confirmation402 covers
import/training only. Add one case to existing analysis test module: allocated tiny NumPy epoch data,
real torch Linear parameters and actual estimator produce a RAM warning (only OS telemetry isolated),
then exact challenge/confirmed consume/readback/replay. Reuse actual TrainingManager and
VisualizationStateService receiver, asserting no initial mutation, one confirmed notification and no
replay mutation. Prove each attempt rechecks current RAM before receipt authorization. The manager has
no trainer to avoid attribution: this is Analysis estimator/receipt/configuration wiring, not a whole
ApplicationService/GUI/training-compute journey. No production change or additional receipt owner.
Worker owns only test_analysis_service.py after existing analysis/resource baseline; fullsameafter,
bounded in-memory admission-bypass fault, Ruff and main nonauthor actualdiff review before commit.
Original41passed0.48s; new42passed2.70s. Admission-bypass in-memory fault fails at the initial challenge
(DIDNOTRAISE,1fail2.15s), no faulty source persisted. Main made the allocated fixture type explicit,
matched Linear input to32flattened features and asserted264real parameter bytes; final combined42+5J38
passed80in6.00s. Ruffpassed. Main nonauthor review approves real receiver/probe/readback evidence, not
a training job. Test-only+116/-3/net+113; existing receipt isolation tests remain useful and retained.

**Completed bounded5J — reuse owned normalized arrays in direct render query.** Main full SaliencyRenderPublisher1420/
work176 and direct733/317 found single-run normalize=True allocates normalized arrays, then copies
them again in DTO construction. An actual Windows publisher probe measured two extra copies/128bytes
for128bytes of output; raw also copies128bytes, which is required to detach source. Current GUI variant
preparation already uses the owned-array path, so this is direct query cleanup, not measured GUI speedup.
Reuse existing adopt_saliency_store only for newly normalized single-run arrays; raw source remains
copied, cancellation checkpoints/read-only flags/identity fences unchanged. No new cache/owner/buffer
type. Add normal/zero and raw/normalized source-isolation/dtype/value tests, establish passing baseline,
then one-line production reuse +stable copy regression/identical focused render/work/normalization
tests. Repeat probe, independent actualdiff review and Ruff before commit. DTO read-only arrays remain
trusted detached renderer data, distinct from immutable bytes-backed authoritative EvalRecord stores.
Do not claim measured RSS/latency gains or strengthen immutability through unnecessary extra copies.
Four new normal/zero/raw/normalized characterization cases and full render/work/normalization38passed
5.65s before reuse. Sole production+1 passes already-reviewed adopt flag only after fresh normalization;
independent actualdiff review approved. Same38after passed within80combined6.00s; repeated exact
probe shows normalized extra copies2/128bytes→0/0, output stays128bytes; raw remains2/128bytes.
Changed-file Ruffpassed. Production+1/testsnet+50, no owner or visible behavior change.

**Completed bounded5K — retire unused coverage forwarding shell.** Full main482source/294tests and independent
caller/guard audit find three compatibility functions plus _DEFAULT_PROJECTOR used only by one
direct test. Migrate that case to the actual SaliencyCoverageProjector methods, keeping all label/
method/complete assertions; passing baseline before deleting shell and its three exports. Keep
project_method/project_run/label projection and all coverage/context/integrity policy unchanged.
Architecture guard must require only the actual projector definition while still forbidding retired
names in UI imports/calls and state-service policy: retain COMPATIBILITY_NAMES and union it with
PUBLIC_NAMES for negative import detection. Do not weaken tests or the specialized visualization
guard. One production file roughly-40LOC, zero owner/public Command/query/EEG/visible UI change;
three scoped files only (coverage owner/directtest/architecture helper). Full direct coverage +actual
state architecture +negative architecture tests before/after, Ruff and main nonauthor review.
5E provenance aliases and5F scheduler remain unchanged pending explicit decisions.
Same258passed36.69s before/36.50s after, including full architecture negative tests and actual
state boundaries. Ruffpassed; main nonauthor actualdiff approved. Production-39, zero owner change;
all label/method/complete assertions retained. Retired-name negative UI import/call guards stay active.

**Module5 full source/test audit additions.** Backend visualizers2332source/direct2526 retain exact
class identity, scientific color/time/geometry semantics, actual STFT and cache single-flight/clear/
failure fanout/LRU; native mesh IO isolation is justified. All4602visualization redesign tests read
contiguously to EOF: typed receipt/terminal/request identity and state behavior remain valuable.
TrainingPlan prepared publication1–150/953–1348 +fullEvaluator477 +directtests1516–2399 retain atomic
multi-record replacement, captured identity/stale/cancel fences, selected-method batching and final CPU
release. Captum inner calls remain cooperatively cancellable only between protected boundaries;
no stronger interruption promise or measured end-user speed improvement. Direct tests of successful
temporary-model CPU cleanup need tracing before any cleanup-semantics change.

Independent full manager724–2413/directsaliencylifecycle1882 and actual-method accumulation275
retain explicit command target admission, terminal generation/notification/retry, unlocked callbacks,
stale/CAS fences, atomic recompute and actual safe reload. Full publication integration2773 (not the
earlier approximate2430) includes real MNE/EEGNet multi-fold commands, actual Qt close, render barriers,
live-model/mask/metadata mutation rejection and recovered publication. Narrow compute/thread/queue
fault seams are justified, not mock-only duplicates. Its one manually armed dormant scheduler case
remains protected pending5F; similarly named explicit-command scheduler/target tests must stay.
Seven compact read-side/UI/label/FIF tests1277 were fully source-reviewed, not executed native GUI
acceptance. Capture walkthrough/script test audit and final inventory review remain unfinished.

**Module4 preview coordinator full audit.** Main read439source/341directtests: retain single-flight
same-request sharing, latest queued draft replacement, exact generation/receipt refinement, shared
OwnedWork cancellation, non-daemon worker admission/failure/close/retry and nonblocking diagnostics.
Real threads/Events/registry assertions give direct evidence; model estimate callback is a justified
external seam. Retained cache has one bounded completed result, not a second policy owner. No measured
unnecessary waiting; waits are explicit ticket/lifecycle boundaries. The worker_thread property is
used by actual UI tests to check non-daemon identity and is retained. A possible dead None branch
requires control-flow disposition before closure; do not infer deletion from a text-only search.

Completed2X–2AC are indexed below; their full scope/evidence remains in Git history.
2AC found an existing shared-environment source hazard: Windows .pth adds the original checkout
to sys.path, making scripts.dev a two-checkout namespace. For subsequent native validation, remove
only that exact oldroot from the process search path before imports, then call unchanged
assert_active_checkout_import(Path.cwd()). Do not edit the environment/.pth or weaken the gate.
The first2AC run had two expected root failures plus this separate origin failure; isolated rerun
had only two expected failures, then allsix passed after the resolver fix. No real fixture ran.


- Main fully read load_labels_step462 and wizard preview4850; independent reviewer fully read
  label_placement_step2179 and coupled caller/test ranges. Independent workers fully read all7,359
  original direct preview test lines in two contiguous halves; real Qt controls/signals/serialized
  choices are useful UI evidence, not actual backend workflow evidence.
  ReviewImportStep1556 and InternalEventStep879 full independent audits are complete. No whole-family
  closure yet; confirmed remaining candidates and UI decision items still need disposition.
- Independent coordinator audit fully read recipe reload431/payload126/ActionCoordinator2400 and
  all4660 lines of direct async-flow tests across explicit non-overlapping ranges. Retain
  generation-bound apply, modal cleanup, live Cancel, exact
  warning-receipt retry, real QThread heartbeat/cleanup and shared operation presenter ownership.
- Independent integration audit completed external-label preview71, semantic render539/safety365,
  BIDS epoch duration414 and shared support55. Retain real file/recipe/atomicity evidence; render tests
  synthesize training records and do not prove actual training. Several standalone ApplicationService
  fixtures lack finally-close; no global autouse service close exists. This is an advisory hygiene
  candidate, not a demonstrated leak or permission to rewrite these fixtures during 2X.
- Remaining UI family source fullreads: subject chooser241/loading302/normalizer28, smart parser1035/
  channel chooser183/source chooser298, event editor644; direct tests237/63/407/109/125/431 retained.
  Actual BIDS editor157 integration proves real file -> Qt choices -> backend recheck -> confirmed Apply.
  Actions678/panel991/sidebar860 source read; import/review/recipe facets reviewed, other domain tests
  remain partial: panel450–620, sidebar1–75/514–644/945–963, minimal51. Preserve live public façade.
- Main fully read receipt authority153 (distinct from deleted label receipt), real receipt integration99,
  event-value workflow290, metadata111, optional BIDS montage130/public480/multisubject416/
  responsiveness165, Assistant exact-review cancellation130. Retain one-shot/semantic/atomic paths;
  Assistant cancellation seeds pending handoff directly and does not close actual model-attempt gap.
  External-label real Qt/GDF/MAT workflow934 is fully reviewed, including async remove/re-add andrecipe.
- Coverage routing found module2 consumers hidden by initial keyword mapping: Data Import capture/
  replay/report scripts and their tests and wizard harness617 still require body audits; module8
  infrastructure ownership does not make them out ofscope. Main fully read shared DataManager244/
  direct206: retain copy-on-preprocess, channel-undo deep backup, force-clean guards and invalidation;
  MagicMock dataset fixtures do not prove actual training transitions (module3/4 remain open).
- Independent full audits: wizard harness617 uses real Study/Qt/application runtime, visible modal
  controls and terminal fail/stop paths; retain. Format matrix2953/direct639/UI integration248
  retain real commands, fixed requirements, strict failure/artifact exit and honest generated-vs-public
  claim boundaries. Dataset matrix781/direct453 retains fixed denominator/diversity and lifecycle
  checks as a renderer, not a new command owner. Teacher1259/unit430/integration197 retains actual
  command/epoch/digest contracts, sidecar nonpromotion and explicit best-effort raw/service cleanup.
  Replay1329/direct572 retains live command/widget capture, geometry/artifact/identity guards and
  explicit noncanonical claim boundary. Its persistent-visible close timeout lacks a direct test;
  declare that focused evidence improvement separately before authoring. Script cleanup
  findings do not authorize shrinking existing evidence inventory or relaxing fail-closed outcomes.
- Confirmed backend candidates: two definition-only tabular multiplier aliases; CommandService
  pure pending-receipt/scope forwarders and raw-presence double-copy convenience. The preflight
  path-set method has two actual consumers and transforms/validates diagnostics; retain it rather
  than treating it as a one-call alias. Declare exact coherent scope/baseline before further edits.
  Actual memory multipliers/maps, preflight policy, receipts and candidate scope must remain.
- Coordinator payload wrappers and wizard source/state copies remain candidates, not approved changes.
  Trace dynamic bindings and real widget lifecycle before removal. Do not move large classes merely
  to improve file-size numbers or introduce another UI/backend owner.

**Pending visible-state decision — interval onset preview.** Placement source972/direct429 and
downstream candidate/event-code/interval tests were read. A real TSV with two labels, one nonnumeric
onset and two numeric durations currently overwrites time-field needs_review with ready; atomic apply
then rejects the nonnumeric onset without mutation. The matching-count interval and event-code
ready/repeated/conflict cases exist, but partial-onset preview evidence is missing. A visible-state
correction needs user approval, requested asynchronously; no reply yet. Do not silently change
readiness/UI behavior. Continue all independent authorized cleanup while awaiting that decision.

**Pending visible-UI decision — floating remap confirmation.** Main traced parentless confirmation_label
construction and its setVisible call. A read-only in-memory pytest profile of the actual recipe remap
widget test passed and observed parentWidget=None, isWindow=True, isVisible=True with replacement-file
confirmation text. This confirms an extra top-level Qt label, not Windows window-manager acceptance.
User approval requested asynchronously to contain the text in the wizard; no source/UI change yet.
Keep this separate from dead-helper removal and continue independent authorized cleanup.

**Recently closed source/test audits — retain reasons.**

- Candidate1348/choice-schema303, candidate tests2518/56 cases and event-value candidate342:
  retain source/scope/remap/identity/class choices and external reader isolation. 2P removed only
  the confirmed one-use missing-files forwarder; shared actual missing-path policy remains.
- Scan1493/direct1245/38 cases: retain explicit-vs-recursive discovery, admitted payload materialization,
  shared budget, identity/link guards and indexed BIDS traversal. No confirmed deletion.
- Main ApplyService1479/CommandService2309, apply preparation230/discovery142/public projection124
  and projection tests253; independent service tests2464/BIDS1375/event-value apply447/timestamp279:
  retain detached staging/rollback, one-shot command receipts, per-run EEG semantics, bounded/public
  projections and Windows freshness. DatasetState1877/direct1055 retains revision/generation,
  one-shot staging/checkpoints and legacy mutation invalidation; domain UI closure remains separate.
- EEGLAB preflight962/label estimator360/direct EEGLAB522 are fully read. Resource-guard tests were
  read only at190–275/480–535/570–815/840–890 of1632. Preserve pre-MNE bounded MAT parsing, compressed
  budgets, exact FDT shape/size/path checks and shared multi-file MAT budget. Real savemat/read-counter,
  parser-denial and pandas/tracemalloc tests are useful, not final source-diverse certification.
- Montage preparation1282/coordinator460/lifecycle355, their direct tests809/630 and fixture130:
  preserve geometry/resource admission, generation/manual precedence and publication as distinct
  responsibilities. 2Q adds failed-refresh retry protection at the coordinator level, not an extra
  service-level integrated claim.
- Module 8 full reads include run_tests961/direct1174, attestation195/direct185, required-wrapper260/
  direct409, Windows bootstrap881/direct436, run.py370 and startup test bodies, WSL launcher276/cmd42,
  setup ps1/cmd, ci_change_scope109 and artifact verifier216. Whole CI925, all Poe/dependency entries,
  other scripts and handoff/dashboard adapters remain open. Actual CI aggregation already installs
  only lock-derived coverage, not a duplicate product environment; retain non-equivalent gates.
  No measured unnecessary startup/CI wait was established.

**Recent evidence limitations.** 2T's unedited native baseline had two geometry assertion failures:
the intended150px minimum exceeded natural143px layout hint, legitimately adding footer surplus.
Tests now allow only that derived surplus plus existing rounding and explicitly require minimum150;
no product geometry change. 2U's first fixture migration failed two obsolete session.load diagnostic
assertions although generic forbidden-import checks already rejected the unsafe UI. Automated safety
review rejected deleting the specific gate, so all existing checks were retained and extended to
actual direct/symbol/module-alias factories; assertions were not removed. 2W's first sandboxed Windows
launch failed before collection; required escalated interop succeeded without restarting/installing.
Native Qt unit runs are offscreen, not Windows window-manager/DPI/manual acceptance.

After closing each scoped edit/review, continue the unfinished module audit immediately. Modules3–9
and same-source final integration gates remain required. A commit, context recovery or pending CI
is not an endpoint.

### Responsibility closure and retained boundaries

- Module 1: independent reviewer approved shared-spine responsibility closure at `1247cf7c`.
  Native same-source selection: 178 passed, covering runtime/cache, confirmation, publication/delivery,
  owned work, state/read models, observer batching and actual query/shutdown cases. Service domain
  branches and state/snapshot projections remain explicit module 2–6 obligations. Later changes to
  shared identity/publication/lifecycle reopen affected evidence.
- The state-service test audit read all 2,063 lines / 49 functions: retain distinct failure, detachment
  and retry contracts. Actual data_lists cases already protect nonwaiting lock rejection,
  stale-generation admission and committed-state reads; do not invent another concurrency owner.
- Results, automation, pipeline-transaction and workflow-projection test audit read 1,761 lines:
  retain privacy/public-JSON, real command/subprocess, mutation-port and fail-closed behavior.
- Module 2: content identity source (1,010 lines) and direct/hash-cancel tests (945 lines) retain
  streaming SHA, path scope, admitted digest reuse, bounded workers and owned-context cancellation.
  PathIdentity lexical/resolved matching and parser-window ResourceReader checks protect different
  boundaries from cross-review SHA; they are not redundant caches.
- Recipe source/direct tests retain save/replay, legacy class-map migration into unconfirmed
  suggestions and current label-audit reconstruction. Target provenance/schema additions are not
  current guarantees or authorized schema work.
- Loader orchestration/factory/registration and direct tests have been read. Native installed MNE
  source refuted the proposed Raw lazy-handle leak: relevant Raw readers reopen paths per read,
  while EpochsFIF legitimately retains its live descriptor. Do not add a disposal owner without
  evidence. No measured startup/performance improvement is claimed.
- Study convenience cleanup does not certify training/domain methods. EvalRecord.export_csv remains
  a module-5 caller/disposition question, not a claim of reachable product CSV export.
- Module 6 must close the actual Assistant attempt -> pending confirmation -> application workflow
  evidence gap; separately tested halves do not prove stale approval rejects with exactly one
  authorized mutation. Preserve accepted bounded Assistant limitations, not Stable promotion.
- Module 8 initial inventory: 106 scripts, 66,204 physical lines. This is not deep-review evidence.
  Current CI routing correction covers only helpers actually used by visual lanes; separate handoff
  producers are not grounds for extra unrelated CI waits.

### Completed slices — compact recovery index

Each entry was inspected by the main agent and independently reviewed unless a limitation is stated.
These focused counts are not additive whole-project evidence. Owners/public contracts did not increase.
Detailed scope declarations and chronological corrections remain in the associated Git history;
this table replaces their duplicated active-plan narrative, not any unresolved module obligation.

| Slice / commit | Change and production LOC | Focused evidence / limitation |
| --- | --- | --- |
| Stage / `5346a296` | One integrated phase plan, small-commit exception; no runtime change | Baseline main `4770b049`; source-only worktree, existing Windows environment |
| 1A / `0d67870f` | Snapshot uses existing pure training serializers; +16/-50/net -34 | 139 before/after; lazy imports and publication preserved |
| 1B / `f498e436` | Unused state exports/aliases/lazy forwards; handle_evaluate registry retained | 92 original -> 94 retained with real model-name/detachment cases; live-alias fault detected; fresh-cache native 84 later |
| 1C / `25aca4a8` | Delete four-line registry.start forwarding alias | 29 before/after; all seven migrated files 112; 20 calls changed, assertions unchanged |
| 1D / `1f0329fd` | Retired runtime serialization helpers; +2/-34/net -32 | 55 before/after; explicit public/internal serializers retained |
| 1E / `3a8143f0` | Publication-only Assistant stage, remove mock/Study derivation; +4/-107/net -103 | 138 -> 127; typed mapper and actual assembler; two wrong-stage probes detected; new typed cases were not run against old signature |
| 1F / `8044302c` | Derive lazy exports from existing mapping; +2/-116/net -114 | 4 original/strengthened cases; exact 114 names/order preserved; cold import/memoization retained |
| 1G / `b5d6dc4b` | Unused Assistant conveniences/type aliases; +2/-49/net -47 | Same 89 plus 4 selected before/after; no tool/policy/receipt changes |
| 1H / `f5c7fd77` | Unread snapshot/query dependencies; +1/-8/net -7 | Main selection 88; reviewer's 84 omitted four read-model cases, not failures |
| 1I / `264ef571` | Reuse detached prepare failure envelope in three callers; +6/-79/net -73 | Original 5, strengthened 6 before/after; concurrent winning publication/cancellation retained |
| 1J / `a5101683` | Lifecycle unread dependencies/fallback/forwarders; +5/-22/net -17 | 10 baseline, 26 extended reset/rollback/import cases; injected transaction remains owner |
| 1K / `e2f483dd` | Reuse six identical fence release blocks; +15/-36/net -21 | 17 + consumer -> 18; missing-release fault detected; locks/flags/finally order unchanged |
| 1L / `3a35efee` | Unread Qt callback member and empty test subclass; production -2 | 34 before/after, real Qt delivery/ack/teardown; visible behavior unchanged |
| 1M / `8d51502e` | Unused observer batch compatibility properties; production -17 | 33 original/characterized/after; public notify/deferred outcomes retained |
| 1N / `0b0a8e7b` | Unused Study and exclusive manager convenience chains; +2/-63/net -61 | Four-file 158 -> 146 (exactly 12 obsolete cases), 7 analysis/readback neighbors; real saliency/manager behavior retained |
| 1O / `6c0ee806` | Consolidate duplicate runtime identity test; no production change | 10 -> 9; both construction orders, concurrency/retry and explicit-close cache isolation retained |
| 2A / `d1dc62ff` | Fix raw cleanup retaining channel backup; +1/-0 | 3 red -> 59 green; two real FIF apply/session/reset cases; 8,000-byte weakref witness is retention evidence, not OS RSS promise |
| 2B / `930c2a6a` | Resource admission guard targets actual prepare, not dead handler; test-only | Unsafe actual path red -> 15 pass; no security rule weakening |
| 2C / `1c7ba6fc`, `d3ef1ac4` | Actual prepared-path characterization, then remove old direct apply/helpers; +2/-186/net -184 | 28 real command replacement cases; after 79 actual application and 134 retained cases; 21 legacy functions/35 cases removed; retained AST bodies unchanged; bypass-content-check fault detected |
| 2D / `7b4fc8a0` | Dead DatasetStateService import/port and raw prepare convenience; production -81 | Main 24 original/characterized -> 53 after; worker 10 before/after; stale no-import sentinels now watch actual loader |
| 2E / `722207cc` | Fix Windows recipe descriptor/path ctime mismatch; +16/-4/net +12 | 2 red/1 pass -> 3 pass; 18 selected, 107 full service/receipt cases resolve three native failures; complete within-channel checks and cross-channel dev/inode/size/mtime retained |
| 2F / `1247cf7c` | Duplicate current-session check and single-use verification wrappers; +9/-21/net -12 | 49 + 6 before, identical 55 after; SHA, contexts, cancellation unchanged |
| 2G / `aba4eea7` | Three unused interpretation mutation APIs; production -55 | Strengthened actual checkpoint/one-shot/recipe rollback protection; final historical-source 82 and current 82 pass; chronology qualification below |
| 2H / `7c89b532` | Six test-only Raw display conveniences; production -49 | 113 original, strengthened retained 116; 13 external-fixture skips; eight wipe cases before deletion and imported-event fault detection; 11 typed-summary + 3 rollback neighbors passed |
| 8A / `c0425f43` | Route three actual visual-CI helpers | 10 baseline, 1 red/10 pass, 11 corrected; five unrelated producer additions rejected before commit |
| 2I / `73002524` | Remove eight duplicate loader cases; no production change | 39 original/strengthened -> 31; exact SET codec/preload strengthened; actual FIF/epochs retained; plan history consolidated |
| 2J / `daaf1a59` | Retire unused flat sequence/force and catch-to-zero label chain; +9/-223/net -214 | 79 original/migrated -> 68 after (11 dead cases), 18 actual sequence/recipe neighbors; nine checked-batch cases retain explicit error phases/real Raw rollback; actual public state entry unchanged |
| 2K / `0e1c096c` | Remove identity alignment helper/index copies/unreachable warning; +5/-126/net -121 | 36 original -> 39 real Raw characterization -> 37 after two replaced mocks; 18 actual consumers; reversed-row fault detected |
| 2L / `d575fba4` | Unused BIDS admitted size-only property; production -7 | Identical native 28 before/after; property is not a dataclass field; content identity/budget unchanged |
| 2M / `e0df098d` | Three unused label-carrier convenience helpers; production -37 | 35 original/migrated -> same35 + six event-value consumers after; four full maps unchanged through actual derive_class_views |
| 8B / `323241a9` | Correct WSL launcher terminal-only output description; script +1/-1 | 5 original -> 1 red/4 pass -> 5 corrected; existing privacy source assertions; no launcher/app executed |
| 2N / `2a61245b` | Unused metadata readers/budget alias; production -30 | Native27 original/migrated/after; admitted cache/budget behavior retained |
| 2O / `f485c36f` | Reuse ordered path projection and target routing; +8/-23/net -15 | Same80 original/strengthened/after; duplicates/blanks/None recipe paths preserve exact output |
| 2P / `e78f9a78` | Remove missing-path forwarder and marker no-op branch; +1/-22/net -21 | 59 -> real FIF annotation/stim characterization61 before/after; upstream MNE warning |
| 2Q / `5155f913` | Coordinator failed-refresh -> pending -> retry -> no duplicate publication; tests only | Native18; missing-retention in-memory fault detected; not service-level dispatch evidence |
| 2R / `aaf64d41` | Actual duration evidence and mapped label owner replace test/single-call forwards; +8/-35/net -27 | Same101 original/migrated/after; per-run/time/atomic behavior intact |
| 2S / `5b97abfd` | Unread filename dependency across three constructors; production -8 | Native126 plus selected actual ApplicationService30 before/after; live snapshot filename retained |
| 2T baseline / `b67d24f8` | Correct two geometry bounds for intended minimum-height surplus; tests only | Original44 pass/2 fail -> strengthened46 pass; explicit150px floor, no layout edit |
| 2T / `92a7cc38` | Unused montage smart_match and three exclusive tests; +2/-50/net -48 | Retained native43; safe/reviewed mapping and all current lifecycle cases unchanged |
| 2U / `20c139b3` | Dead label admission/receipt/specs chain; production -258 | Native289 original ->290 migrated ->289 after one obsolete case; seven actual receipt/SHA neighbors; all safety gates retained |
| 2V / `1e28068c` | Discarded full label payload hash/state; +4/-119/net -115 | Real1MiB admission stream1,048,576 ->0 bytes; actual524,288 labels unchanged;64 safety cases before/65 after; identity probes/early descriptor/final SHA intact |
| 2W / `bb5a27e0` | Unused wizard legacy review fallbacks/target/clear_skip; production -172 | Native28 ->27; full target/empty metadata assertions preserved, main focused1; main nonauthor review; no separately strengthened pre-delete run |
| 2X / `bf1a14e6` | Wait for real cancelled-review terminal delivery; tests only | Same native5 before/after, Ruff; in-memory late delivery detected1!=0; finally releases on assertion failure |
| 2Y / `26b8c054` | Remove16 unused wizard-private helpers acrossfourfiles; production -224 | Native130 ->128, exactlytwoexclusivecases removed; real sidecar field retained; independentreview and Ruff |
| 2Z / `4e317328` | Removeignored tree-sizing inputs and equivalent row-count aliases; +4/-21/net-17 | Native10 geometry/rescan cases, Ruff; independent arithmetic/caller review; no visible geometry change |
| 2AA / `11125166` | Merge duplicate rescan case while preserving all assertions; tests net-34 | Strengthened3before ->retained2after, Ruff; main nonauthorreview |
| 2AB / `fca0ac35` | Deleteunused fuzzy montage chain/module; production -102 | Native59 ->52, nine new no-mock actualnormalizer cases; sevenexclusiveold removed; same18upstreamwarnings; independentreview/Ruff |
| 2AC / `36b2de7e` | TwoOpenNeuro integration roots reuse configured storage; tests only | Isolated red2fail/4pass ->6pass; runpyactualconsumer definitions, no downloads; independentreview/Ruff |
| 2AD / `27c525c6` | Remove four Coordinator payload forwarders; +20/-39/net-19 | Native80 before/after; migrated assertions6focused before deletion; independentreview/Ruff |
| 2AE / `20b05f75` | Remove unused loader lookup/commented rejection; production -17 | Strengthened23 before/after, no-publication fault detected; real Apply neighbors, independentreview/Ruff |
| 2AF / `4df0c36e` | Remove preflight forwards/list copy and unused multiplier aliases; +8/-40/net-32 | Same20 native before/after; receipt/scope/BIDS fallback review and Ruff; policies unchanged |
| 8C / `e8ed6d4b` | Retire duplicate placement capture entrypoint; script +1/-76/net-75 | Canonicalcapture32 before/after, mainnonauthorreview/Ruff; actual factories unchanged |
| 2AG / `528322e7` | Remove empty wizard footer instance and exclusion forward; +1/-9/net-8 | Same13 native rendering/removal/geometry before/after, independentreview/Ruff |
| 8D / `aeb53bf4` | Real Qt persistent-visible timeout evidence; tests+36 | Originalsuccess1 ->success/timeout2pass; in-memory wrong-success fault detected; mainnonauthorreview/Ruff |
| 8E / `b7ed74ab` | Remove unused review-state capture fixture; script-63 | Same32 native before/after, mainnonauthorreview/Ruff; canonical factories/inventory unchanged |
| 3B / `7fb9fcc9` | Retire unused MAT Export/module/export tests; production-57/tests-98 | Native78 ->73, exactlyfive obsoletecases; same17upstreamwarnings; independentreview/Ruff |
| 3A / `07881c8d` | Two unused DrawRegion APIs removed; production-23/testsnet-16 | Original22 ->stronger23 ->retained18; wrongoverlapfaultdetected; actualcanvas/strategycases and mainnonauthorreview/Ruff |
| 3C / `c628be38` | Remove unreachable ordinary preprocess handler branches/helpers; production-76/testsnet+37 | Real ordinary/admission characterization before deletion, retained42pass; cancellation/stale/rollback/epoch safety retained, independentreview/Ruff |
| 3D / `036cb1cc` | Remove unused split to_thread no-op; production-3/tests+87 | Native direct16 before/after; both omitted-guard faults detected; independentreview/Ruff; distinct offscreen font/native-center limitations remain tracked |
| 3E / `63f691b2` | Real epoch boundary workflow replaces two summary mocks; testsnet+43 | Exact1%, above1%, multirecord counts/atomicity; threshold fault detected; combined3E/3G291pass, independentreview/Ruff |
| 3F / `f234a5ea` | Synchronous plotter/fallback/alias cleanup; productionnet-29/testsnet-1 | Real curves/current+overlay/time+PSD; direct25pass and native8cycle stress; wrong-frequency fault, independentreview/Ruff |
| 3G / `d86efa15` | Retire unused Epochs picker chain; production-538 | 307 obsolete collected cases removed (corrected actual parametrization count), actual manual Generator retained; combined291pass, independentreview/Ruff |
| 3H / `3e556a98` | Actual RAM-before-deepcopy test replaces exclusive fake; testsnet-7 | Direct/adjacent37 retained; strengthened actual-copy node1pass and omitted-check fault caught; independentreview/Ruff |
| 3I / `db4670d7` | Normalize/validate split command once; productionnet-10/testsnet+30 | Real defaultNone vs explicitempty replacement; retained47pass; exact public message, independentreview/Ruff |
| 3J / `e77e389c` | Dialogs reuse inherited geometry owner; dead reference aliases removed; productionnet-22 | Same24 Windows QPA windows cases before/after, no visible change; main nonauthorreview/Ruff |
| 3K / `0b7d77ef` | Retire test-only dataset metadata conveniences; production-49/testsnet-11 | Missing mask assertion restored;113before112retained, exactlyone duplicate removed; independentreview/Ruff |
| 3L / `81e0dfb6` | Real BIDS receipt scope and same/changed-context reimport; testsnet+69 |45before40retained; four stale-acceptance faults caught; main nonauthorreview/Ruff |
| 3M / `a7b1ad2c` | Export supported lazy dialog targets only; productionnet-6/tests+13 | Missing-class red,12green; independentreview/Ruff |
| 3N / `96366558` | Remove ignored preprocess error-prefix plumbing; production-6/tests-2 | Same28before/after; main nonauthorreview/Ruff |
| 3O / `9ddb204c` | Actual alias-to-epoch labels/counts and unknown list/dict atomic rejection; testsnet+87 | Real3new plusneighbors40pass before handler retirement; main nonauthorreview/Ruff |
| 3Q / `e8cf3260` | Real Qt controls/signals replace timer-rewired mocks; testsnet-19 | Old2→combined4→retained2+15neighbors17; omitted-signal faults detected; independentreview/Ruff |
| 3P / `7e6007c1` | Retire synchronous epoch duplicate and callback chain; productionnet-122/testsnet-502 |17obsolete nodes retired after real migration; integrated3P/R89pass; main nonauthorreview/Ruff |
| 3R / `8ff29e95` | Six unused state-service apply conveniences/protocol entries removed; productionnet-93 | Same10direct before/migrated,89integrated after; independentreview/Ruff |
| 8F / `161b5a33` | Retire orphan synthetic epoch capture/test/optional scan path; script-726,totalnet-825 |7before6retained, oneexclusivecase removed; main nonauthorreview/Ruff |
| 3S / `731e28d5` | Three duplicate adapter tests and unused helpers retired; testsnet-123 |43before40retained; real metadata/row identity/receipt/wiring preserved; independentreview/Ruff |

| 4A / `31ca6ed1` | Unused TestOnlyOption/export retirement; production-195/tests-99 |162before140retained;22exclusive obsolete cases; main nonauthorreview/Ruff |
| 3U / `b1c0b902` | Direct shared preprocess query, no panel forward; productionnet-14/testsnet+10 |27before/migrated/recoveredafter; actual panel context/minimum rate retained; independentreview/Ruff |
| 4B / `210ea1f3` | Real completed Trainer retirement/startup restore; tests+58 |237combined; in-memory omitted restore fails; exact record identities/full snapshot; main nonauthorreview |
| 4C / `e19967d6` | Single estimate per preflight; productionnet-24/testsnet+93 |131baseline/133final; measured GPU models/data reads2→1; cancellation before GPU retained after fault; independentreview/Ruff |
| 4D / `12e389be` | Unused model metadata/optimizer conveniences; production-25 |Same125before/after; canonical schemas/dynamic catalog unchanged; independentreview/Ruff |
| 4E / `45aae45d` | Actual training persistence, shared safe-load assertion; testsnet-2 |5before/after; migrated A01T1pass; omitted-save fault fails; A01T100784bytes/retry100750bytes; no GUI restart claim |
| 4F / `893e4ad0` | Unused Trainer name lookup; production-22/tests-21 |Retained Trainer/real rollback/optimizer stop47pass;4obsolete cases; independentreview/Ruff |
| 4G / `eac27aad` | Live bulk metric/history rendering only; productionnet-26/testsnet-46 |35baseline→42final incl7retained presentation neighbors;2obsolete append cases retired after historical9pass; independentreview/Ruff |
| 4H / `05da6d88` | Inert settings fields/note/helper removed; productionnet-22/tests-1 |Same45before/after incl real saved-split recommendation; main nonauthorreview/Ruff; no visible change |
| 4I / `77fc31c2` | Orphan record wrappers/exclusive suite removed; production-82/tests-59 |70before65retained;5obsolete cases; negative architecture boundary retained; independentreview |
| 4J / `4e9deb3a` | Unused TrainRecord summary/append API; production-57/tests-72 |67migrated before;62retained+4K25=87after; actual update gapfill and omitted-gap fault retained |
| 4K / `e90be669` | Unused recommendation cache accessor; production-13 |Same25before/after within87; cache/invalidation/policy unchanged; independentreview |
| 4L / `2ab22913` | Unused ModelHolder description; production-18/tests-2 |Same232 real model/catalog construction+gradient cases; no test case removed; independentreview |
| 5A / `6558bd06` | Unused EvalRecord CSV export; production-21/tests-15 |35before34retained; current JSON/NPZ reading unchanged; independentreview |
| 5B / `5c33337d` | Unread standalone saliency export retired; production-83/tests-76 |101before93retained;8obsolete cases;8POSIX-only skips still CI obligations; main nonauthorreview |
| 4M / `bf24db3f` | Mock-only output uniqueness replaced by real frozen-clock records; testsnet-98 |32before31retained/4POSIXskips; duplicateUUID fails real exclusive output creation; independentreview |
| 5C / `cdeb3175` | Unused saliency getters removed; production-100/testsnet-67 |93migrated before88after;6actual-validator bypass faults fail; invalid/old/producer checks migratednotremoved |
| 5D / `ae7c8d62` | Dead render error/string forwards; production-19/testsnet-10 |Same50before/after incl real trainer typed summary; no cases removed; independentreview |
| 4N / `33a7ad8b` | Real persistence in synthetic training integration; testsnet-41 |Same27before/after;122files/723462bytes; omitted-save exactcase fails safe load; main nonauthorreview/Ruff |
| 5G / `0839dcc2` | Unused policy/holder/render conveniences + duplicate assertion; productionnet-61/testsnet-8 |235migrated before234after; strict invalid-method/default state/vectorized interpolation retained; independentreview/Ruff |
| 5H / `cef27766` | Inert 3D setup/state removed; productionnet-20 |Same43before/after; control/sample identity/lifecycle unchanged; main nonauthorreview/Ruff |
| 5I / `75bd4047` | Real Saliency estimator/receipt/receiver evidence; testsnet+113 |42after within80combined; admission-bypass fault fails; not an attribution journey |
| 5J / `848d3356` | Reuse newly normalized detached arrays; production+1 |Same38before/after; normalized extra copies128→0bytes, raw copy retained; independentreview/Ruff |
| 5K / `e3c57cd9` | Retire unused coverage forwards; production-39 |Same258before/after; all assertions and negative UI boundaries retained; main nonauthorreview/Ruff |

| 8G / `4f352cab` | Preserve caller-owned capture output root; script-3/test+61 | Red4 then76passed; real nested sentinel/rerun/exit evidence, not native rendering |
| 6A / `296af917` | Orphan command-to-panel route removed; production-80/test-18 |342before339retained; exactly3exclusive cases; actual navigation retained |
| 6C / `3d498c51` | Orphan backend class registry removed; production-101/testnet-36 |74before71retained; actual18-tool registration unchanged |
| 6D / `f4c060c5` | Unreachable empty-schema override; productionnet-15/test+23 |72before/after; exact schema assertions and empty-schema fault detected |
| 6B / `5afdb10d` | Real confirmation card → reset/replay/cancel/stale mutation; testnet+291 |21before24after; omitted-reset fault detected; real raw identity/256Hz/file bytes, model/runtime transport isolated |
| 6F / `65cd3519` | Eight test-only RAG probes removed; production-51/testnet+10 |12original/strengthened,271combinedafter; captured actual thread non-daemon fault detected; live shutdown query retained |
| 6H / `42cc98a4` | Shared settings-path owner and orphan cache alias; productionnet-90 |Same94before/after,21exact path combinations; no user settings written |
| 6I / `a2b21efc` | Real metrics tracker replaces synthetic capture fixture |Same17before/after; omitted-finish fault detected; no production/count change |
| 6J / `3831a483` | Dormant RAG initialize/publish/helper paths; productionnet-46/test-1 |89before/after,2POSIX-only skips; lease/closed fence/local-only/corpus policy retained |
| 6K / `965bc97e` | Sole-subclass backend shell/ignored-mode helper; productionnet-50/test-60 |116before110retained48.65s;6exclusive cases removed; first lost after ending not counted |
| 6L / `f44d3e0e` | Real RAG quota fixture10.1GB→101bytes; testsnet+9 |89after/2POSIXskips; omitted current-target guard fails; actual9.41GiB fake file removed, real caches untouched |
| 6M / `ef161994` | Four giant model quota fixtures →105/206/302/300bytes; tests only |77retained8.61s,4omitted-quota faults fail; baseline Windows expected-path mismatch corrected; defaults unchanged |
| 6P / `ec4eeeda` | Exact capture UTF8 writes on Windows; productionnet0/testnet+12 |3red/10pass→452combinedgreen23.50s; real LF/CRLF/Unicode bytes+SHA, strict validator retained |
| 6N / `92d6a091` | Unused tolerant parser chain; productionnet-136/testnet-9 |403retained21.31s;57exact-result digest; omittedtypeguard2fail; strict grammar unchanged |
| 6O / `b6d596d4` | Ignored downloader arg/cleanup message alias; productionnet-7 |Same23before6.89s/after6.78s; lifecycle/public-message protection retained |
| 7A / `e6aa7d44` | CP950/ASCII console encoding fallback; productionnet+22/test+63 |4red/2pass→58green8POSIXskips4.47s;6final1.30s; both sink orders/privacy/UTF8 intact |
| 6Q / `0181b233` | Unused snapshot serialization; productionnet-70/testnet-27 |39before37retained5.74s;5omitted-validation faults fail; typed/device/activation intact |
| 6R / `f3b850d7` | Real processing widget state +2duplicate tests retired; testnet+9 |150before22.79s/148after22.63s; noop forwarding fault fails; no production change |
| 6S / `f7632053` | Unused conversation convenience chain; production-33/testnet-23 |19before7.54s/15retained7.38s; wrong-end window2faults fail6.12s; exact list semantics |
| 6T / `f4d2884a` | Suggestion row churn +unused render helpers/arg; productionnet-33/testnet+27 |213before9.09s,3red1.01s,216after9.34s;3width geometry equal,15+15calls→0+0 |
| 6U / `5cf7a6df` | Unused private command list normalizer; production-7 |Same25before6.38s/after6.36s; no tests/contract changes |
| 6V / `337d94e7` | Approved dormant recovery-feedback chain; production-131/tests-102 |403before/400after,3exclusive cases retired;14prompt parity digest above; privacy review |
| 6W / `5132d43e` | Discarded footer input/list; production-4/tests-5 |35before/after, copy unchanged; independent review |
| 6X / `a6e3d7e9` | Stateless names/byte alias indirection; production-14 |104before/after; prompts/scoring/8192byte cap unchanged |
| 6Y / `6c66f2a0` | Owned runtime init only; production-13/tests+99 |110before/after;2failed-close faults fail; independent lifecycle review |
| 7B / `c089d7a8` | Unused UI query forwards; production-63 |52before/after; backend queries/variant lifecycle retained |
| 7C / `deb4a3cf` | Four orphan widgets/lazy exports/styles; production-660/tests-227 |70before/50retained,20exclusive cases retired; architecture/import/lint pass |
| 7D / `0aa9fa6c` | Aggregate renderer unused Study/marker; production-2 |42before/after; real rows/empty widget and weakref fault; architecture/review pass |
| 7E / `48b9f880` | Unused summary measurement/notifications; production-33/tests-2 |48before/after, no cases removed; all geometry/value assertions retained |
| 7F / `36a23137` | Orphan EventBus and unconnected worker/window signals; production-59/tests-75 |52before/43after,9exclusive cases retired; independent caller review |
| 7G / `e89291f9` | Unused modal facade/ignored error argument; production-14/tests-3 |42nativebefore/after; privacy review; INFORMATION severity retained |
| 8H / `f54e3c4f` | Real installer SHA/HTTPS/size/noexec evidence; tests+92 |20before/23after;SHA-bypass1fail/2pass; no network/install; independent review |
| 9A / `d7003752` | Direct Windows offscreen installed-font default; tests/config+87 |48after incl original42+4child cases; finalbootstrap+fixture29pass/Ruff; no production change |


### Evidence qualifications that remain relevant

- Use a fresh unique PYTHONPYCACHEPREFIX plus -B for Windows tests of WSL-edited source: -B alone
  prevents writes, not stale reads. The earlier ambiguous 1B run was superseded by fresh-cache 84.
  That earlier lookup was abandoned. During2X a worker mistakenly invoked Poetry and created a
  separate empty Windows environment. Main verified its exact newly-created path,7,235,691 bytes,
  no using process and sole internal file symlink, then removed only that accidental environment
  xbrainlab-urV89cf7-py3.12 from the Windows Poetry cache. Original Windows Python remains present;
  the invalid attempt supplied no test evidence. Further runs use the explicit existing interpreter.
- 2G had no original unedited chronological two-file baseline. Migrated tests before production
  deletion passed 81, but an environment-assignment warning invalidated its cache-isolation claim.
  Fresh-cache current runs passed 81; nested isolation was strengthened to mutate actual nested input.
  Final strengthened tests then passed 82 against exact historical `1247cf7c` state source loaded only
  in memory and 82 against current source. The first historical harness needed correct inspect
  linecache registration; that was a harness fix, not a product failure.
- 2G actual post-publication retirement failure now includes prior real apply/save and verifies
  interpretation identity, recipe ID/path/full content and pipeline/trainer/history restoration.
  It intentionally isolates internal transaction rollback with admission bypasses; normal policy
  blocks replacing data after training. A manually injected trainer fixture first caused stale
  Scan admission (combined 130 pass / 13 skip / 1 fail); publishing that injection through get_state
  fixed the fixture, and the corrected case plus full 82-case selection passed. Recipe carried into
  prepared state means recipe assertions alone do not prove rollback; restored interpretation ID does.
- 2H same retained Raw/loader/preprocess selection is 116 passed: one no-op case removed, four extra
  event-wipe parameter cases added. All passed within the combined run above. Thirteen skips are
  unconfigured external public fixtures, not checked-in GDF/multiformat cases; the final canonical
  source-diverse gate is still required. Replacing wipe with set_mne in memory caused all four
  imported-event cases to fail; no faulty source persisted. Existing MNE/NumPy warnings are not
  evidence of final whole-platform readiness.
- 2K's list/ndarray real Raw cases cover filtered interleaving, nonzero first sample, previous-value
  column, exact code/order and no source mutation before apply. Mismatch covers both directions.
  The isolated reversed-row probe failed both cases on timestamps/prior values; no faulty source
  persisted. The first argv probe had only a Windows quoting SyntaxError. One existing MNE warning
  in normal suites is expected all-epochs-dropped safety behavior, not a new failure.
- 2J's force_import field belonged to the explicitly internal LabelImportPlan recipe DTO; current
  construction/serialization never used it. Actual DatasetStateService.apply_labels_batch and
  checked atomic ownership remain. 2M's limit=20 belonged only to its discarded test-only convenience,
  not the current preview/public class-map policy. No formal contract changes are implied.
- Lower-mock internal paths retain external MNE/resource isolation where necessary. No reduced test
  count or path-only inventory establishes stronger workflow coverage by itself.

### Inventory and separate infrastructure recovery

The ignored static inventory is `build/dev-artifacts/module-quality-audit/tracked-files.md`,
initially 1,292 tracked files. Update disposition from actual source/caller/test reading; pending
remains unknown. Reconcile newly added/deleted files and domain-owned ranges before final closure.
Do not create a second planning platform or treat generated files as inspected production.

Authorized storage cleanup is complete locally: removed only abandoned backup
`E:\XBrainLabBackups\XBrainLab-WslCompaction-20260909-232646-9134c3e5810d4399b274695a2b546bce\Ubuntu-24.04-ext4.vhdx.bak`
and its empty parent, plus verified empty runs ending
`20260910-011228-93f0770cd28e49afb965485b587f3763` and
`20260910-014659-d5c3910b070c4a3ba2b6877f5734369d`.
E free bytes increased 712835555328 -> 927430828032 (214595272704 bytes, about 199.86 GiB).
Deletion is not recycle-bin recoverable. Both registered C WSL VHDXs, Windows Python, model/RAG caches
and central datasets remain. No C shrink, compaction, shutdown or deregistration ran.

Compaction-only source tooling withdrawal is separately committed `acf7c56d` on
`chore/manual-environment` in the infrastructure worktree; 84 retained native scripts tests passed.
An initial MAXPATH failure was resolved by the existing short cache temp path. Exact deployed
`D:\XBrainLabCache\tools\compact_wsl.ps1` matched retired source SHA-256
`6675b7debb8f02fc163ba1efed2eaff0d89afa632cd388329bff3935af73d0f5` and was removed.
Both manual launch tools remain. Source is recoverable from Git. No push/merge or manual-checkout
update is implied; inspect current Git/PR state before eventual integration.

### Recovery after context compaction

Read this whole active plan, Git status/diff/worktrees and current worker/session state first. Continue
the next unfinished authorized step immediately; a recovery summary is not an endpoint. Preserve the
module table, current slice, exact evidence and outstanding reviewer findings here before context loss.
Do not dispatch from older completed PRs, recreate environments, discard active work or stop because a
single slice has passed. Keep this file the sole active plan until the stage is actually complete.
