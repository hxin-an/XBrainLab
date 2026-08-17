# Assistant frontend walkthroughs

These debug-only profiles exercise the real ChatPanel, confirmation cards,
ApplicationService commands, UI handoffs, and panel materialization without loading or
prompting the local language model.

Run the short navigation profile first:

```bash
poetry run python run.py --tool-debug scripts/dev/agent_tool_walkthrough/panel-navigation.json
```

Then run the complete action profile:

```bash
poetry run python run.py --tool-debug scripts/dev/agent_tool_walkthrough/assistant-21-actions.json
```

Press Enter or **Next** once per step. When a confirmation card or product settings
surface opens, resolve it in the existing UI and wait for the step to become terminal
before pressing Enter again. The complete profile creates a small FIF and recipe in a
session temporary directory, trains EEGNet for one CPU epoch, and removes that temporary
directory when the XBrainLab process exits.

This is a human walkthrough, not a pass receipt. The compact status states the expected
observable behavior but does not score it automatically. Use the headless Agent showcase
for deterministic command-policy evidence.
