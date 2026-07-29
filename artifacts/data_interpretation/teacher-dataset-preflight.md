# Teacher Dataset Preflight

- Required cases passed: `3 / 3`
- Strict result: `PASS`

| Dataset | Format | Evidence | Status | Result |
| --- | --- | --- | --- | --- |
| OpenNeuro ds003061 P300 | BIDS EEG / EEGLAB SET + events.tsv | supervised_import | passed | Three BIDS runs, three run-specific event carriers, and 2,245 reviewed class events imported with exact source sample/label agreement and a successful epoch handoff. |
| CHB-MIT chb01 | EDF | raw_import_only | passed | The selected EDF recording imported as raw EEG; its companion annotation/report file remained an explicit unsupported sidecar. |
| Sleep-EDF Expanded ST7011 | EDF | raw_import_only | passed | The PSG recording imported as raw EEG. Its 231 reviewed hypnogram intervals remained a detected, unsupported sidecar and were not promoted to labels. |

## Claim Boundary

- Supports: A larger teacher preflight across a real three-run OpenNeuro BIDS auditory dataset and independent CHB-MIT and Sleep-EDF raw recordings. The OpenNeuro case proves a reviewed three-condition auditory stimulus class-label import, exact source-to-runtime sample/label agreement, and a bounded epoch handoff; the two clinical/sleep cases prove raw import and that unsupported sidecars are not promoted to EEG or label carriers.
- Does not support: This does not claim automatic supervised use of CHB-MIT seizure sidecars or Sleep-EDF hypnograms. Those companion annotations remain explicit sidecar boundaries. It is not a full BIDS validator or exhaustive certification of every EEG dataset.
