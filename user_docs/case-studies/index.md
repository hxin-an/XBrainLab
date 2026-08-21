# Dataset guides

These guides provide concrete import scopes and review checkpoints for selected public
datasets. They are examples, not compatibility claims for every file or every version
of a dataset.

## Choose a guide

| Dataset | Source | Scope in this guide |
| --- | --- | --- |
| [Graz / BCI Competition IV 2a](graz-2a.md) | GDF + MAT | `A01T`, `A02T`, `A03T` and matching labels |
| [OpenNeuro ds003061 P300](openneuro-ds003061.md) | BIDS · EEGLAB SET + TSV | `sub-001`, session `01`, runs `1`–`3` |
| [Ofner2017 Motor Imagery](moabb-ofner2017.md) | MOABB · GDF | Subject `1`, imagination runs `1`–`9` |
| [PhysionetMI](moabb-physionetmi.md) | MOABB · EDF+ | Subject `1`, runs `4` and `6` |
| [Lee2021Mobile ERP](moabb-lee2021mobile-erp.md) | MOABB · BrainVision | Subject `1`, session `01`, `task-ERP` |

**Unverified** means that the route is documented but this site does not publish an
identified XBrainLab run covering the stated checkpoints. Follow the instructions, but
do not cite the page as evidence that the workflow completed successfully.

## How to use a guide

1. Confirm the dataset source and version.
2. Select only the recordings listed in the guide.
3. Compare label and metadata choices with the dataset documentation.
4. Stop when the selected scope, mapping, or visible application state differs.
5. Record a new run identity when you change the source, settings, model, or seed.

Each case page keeps detailed provenance and evidence fields for maintainers. Those
fields are intentionally separate from the steps a user follows.

!!! note "A format is not a dataset result"
    Importing one GDF, EDF, or BrainVision dataset does not prove that arbitrary files
    with the same extension have correct event semantics.
