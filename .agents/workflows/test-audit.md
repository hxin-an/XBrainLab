# Workflow: Test Audit

Use `test-quality-reviewer` as primary and `validation-runner` for executable evidence.

1. Define the product/backend workflow and defects the suite should catch.
2. Inventory relevant tests and classify unit contract, integration, UI, real-data, and eval evidence.
3. Map assertions to observable outcomes; flag production bypasses and mock-only choreography.
4. Identify duplicated/obsolete tests and missing lower-mock workflow protection.
5. Use a mutation or bounded source change when practical to confirm strong tests fail correctly.
6. Propose the smallest stronger replacement before deleting weak tests.
7. Update validation docs only when the evidence contract changes.

Report strong, weak, obsolete, missing evidence, next test slice, and claim boundary. Test count is
inventory, not quality.
