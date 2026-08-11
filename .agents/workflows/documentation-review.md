# Workflow: Documentation Review

Use `docs-curator` as primary and `validation-runner` for build/claim evidence.

1. Define the disputed topic and list every place that claims authority over it.
2. Verify current facts from Git, source, runtime evidence, and canonical docs.
3. Classify content as current, architecture, target, planning, decision, validation, or record.
4. Merge useful material into its one authority and delete superseded control surfaces.
5. Remove historical records from active/dispatch labels and repair links/navigation.
6. Run the guidance audit, `git diff --check`, and MkDocs strict build.
7. Add a concise implementation/worklog entry when the change is operationally important.

Done means no unnecessary new top-level document, no current/target/history mixing, no broken links,
and no reusable guidance containing mutable branch/gate truth.
