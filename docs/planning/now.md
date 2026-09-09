# XBrainLab Now

最後更新：`2026-09-09`

## Active — reusable manual environment and in-place WSL compaction

The user approved implementation of a fixed Windows manual environment plus one shared WSL
development/test environment, accepted-test checkpoint cleanup, and an offline Windows script
for **in-place** WSL compaction. Moving/reinstalling/unregistering WSL is explicitly out of scope.
No product UI, model, Assistant contract or EEG behavior change is authorized/needed.

Measured baseline: C: free about 48.5 GiB; D: free about 261.7 GiB. Ubuntu-24.04 VHDX is about
200 GiB while Linux reports about 77 GiB used. Two old Windows PR environments are about 4.1 GiB
each; two large WSL environments total about 12.8 GiB, with the old one still owning Git hooks.
These are inventory observations, not promised reclaim amounts or permission to remove unrelated data.

### Implementation

1. Reuse current Windows .venv and WSL IiX9BmR2; verify dependencies/import provenance and migrate
   Git hooks before retiring duplicate environments. Keep required Granite and embedding snapshots.
2. Provide one source/SHA-checked native manual entrypoint, isolated settings/output, one console log,
   no implicit installation/download, and no switch/cleanup while in use. Reuse existing Git/source,
   configuration, test-temp and process owners; no general inventory service/control plane.
3. Default cleanup to preview and named owned run roots. Successful automated generated weights are
   disposable; manual outputs require acceptance and stopped processes. Preserve unknown/research
   results, protected root settings, original data, failed reproductions and explicitly retained output.
4. Build standalone Windows PowerShell preview/apply for the registered Ubuntu-24.04 VHDX only:
   stopped/unused checks, capacity/backup/hash validation, DiskPart compaction, exact before/after
   measurements and startup verification. Keep backup >=7 days; never overwrite or auto-restore it.
   No WSL shutdown/terminate/move/unregister, no Linux-resident Python dependency.
5. Update existing development/handoff rules and document exact commands; one infrastructure PR.

### Verification and stop condition

Test-first safety contracts with real temporary filesystem/process evidence and Windows-native
PowerShell execution; isolate only privileged WSL/DiskPart seams. Cover wrong source, stale/missing
environment, active process, missing cache, path escapes, preserved outputs, backup/compaction failure.
Use focused tests and changed-file checks, then applicable exact-head CI. Verify native GUI/Assistant,
short training/Saliency, shared hooks and two source preparations without another environment.

The endpoint is the verified stable manual entrypoint, safe cleanup with measured results, and a
Windows-accessible offline script. Actual VHDX compaction waits for the user to save/stop WSL and
run that script as administrator; this agent is inside WSL and must not shut down itself/other work.
After offline execution, resume to verify the existing user/Git/SSH/environment/data/model access.
Do not claim C: VHDX recovery before actual measurements. UI approval: no UI source changes planned.

Implemented: shared-env/source-checked Windows launcher, accepted output-only cleanup, successful
attested pytest temp cleanup, and standalone offline backup/compaction script. Focused Linux tests
and Windows-native launcher/PowerShell harness pass; actual registry preview resolves only the
intended main VHDX. Independent safety findings were repaired. No real VHDX operation has run.

Online cleanup: the obsolete xaLO7TCQ WSL environment and two PR113 Windows .venvs were removed
after usage checks and successful hook migration; D free space increased about 8.1 GiB and WSL used
space fell about 6.5 GiB. Required environments, models and all user/manual outputs were retained.
Moving the old manual source was denied by Windows, so a new source-only stable worktree was made;
the old source is preserved rather than force-closing user consoles. No duplicate env was created.

Next: exact-head infrastructure CI, deployed Windows entrypoints and native startup evidence.
Local docs build lacks MkDocs in the retained environment; use same-head docs CI instead of creating
another environment. Offline compaction and post-restart data verification remain user-assisted.
