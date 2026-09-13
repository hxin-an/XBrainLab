# Supported data and labels

Use this page before choosing data in **Import Data**. Common EEG files and EEG-BIDS
datasets are parallel entry points: ordinary files do not need conversion to BIDS,
and BIDS data do not need to come from MOABB.

!!! warning "Support scope is not universal certification"
    The formats below have import readers and reviewed workflows. This does not mean
    every format variant, BIDS structure, or MOABB dataset has passed end-to-end
    validation. In particular, all-MOABB compatibility is an agreed acceptance target,
    not a capability currently certified by the available examples.

## EEG files

| Format family | Select | Keep with the selected file |
| --- | --- | --- |
| EDF / EDF+ | `.edf` containing EEG signals | Any separate event/label files |
| BDF / BDF+ | `.bdf` | Any separate event/label files |
| BrainVision | `.vhdr` | Referenced `.eeg` and `.vmrk` files |
| EEGLAB | `.set` | Referenced `.fdt`, if data are stored separately |
| GDF | `.gdf` | Any separate event/label files |
| MNE FIF | `.fif` or `.fif.gz` containing raw recordings or epochs | Referenced split-file parts, if present |
| Neuroscan CNT (retained support) | `.cnt` | Any separate event/label files |

Select recordings, not their binary companion files. Keep dependencies available for
the duration of the workflow. EDF files containing only annotations are not EEG
waveforms. A `.cnt` suffix does not imply support for ANT Neuro or every vendor's CNT
variant. FIF analysis objects such as averaged responses are not raw/epoch inputs.

EEGLAB and FIF have raw/epoch reader paths. Reader availability alone does not certify
all epoched variants through the entire import wizard. The reader baseline is MNE
1.11.0 in the current dependency lock; newer upstream readers are not automatically
XBrainLab features.

## EEG-BIDS datasets

Select the dataset root, then review the subjects and recordings to import. Keep the
directory structure and applicable JSON/TSV metadata intact. The accepted target
covers EEG recordings and their subject/session/task/run/acquisition identity,
applicable inherited metadata, events, channels, and available electrode coordinates.

[EEG-BIDS](https://bids-specification.readthedocs.io/en/stable/modality-specific-files/electroencephalography.html)
uses EDF, BDF, BrainVision or EEGLAB recordings. FIF and GDF support as standalone
files does not make those formats conforming EEG-BIDS recordings. BIDS also permits
epoched and discontinuous recordings; complete end-to-end coverage of those cases
has not yet been established here. The conformance target is the EEG portion of BIDS
1.11.1, not every modality or every future specification version.

External event timestamp placement is blocked when inherited EEG metadata declares
an epoched or discontinuous recording: XBrainLab cannot safely treat it as one
continuous timeline. Existing continuous recordings keep their normal route. Changing
reviewed metadata, or adding sidecars after preview, requires a fresh source review.

XBrainLab is not a full BIDS validator. Missing optional metadata is different from
a missing required recording dependency. Unknown event meaning, conflicting metadata,
incomplete scans, or unresolved timing require review rather than guessed values.
Use a dedicated BIDS validator when checking standards compliance.

`events.tsv` is not unconditionally required for every recording. The BIDS
[common principles](https://bids-specification.readthedocs.io/en/stable/common-principles.html#compulsory-optional-and-additional-data-and-metadata)
permit omission when it is unavailable or inapplicable; do not create an empty file
merely to satisfy a filename check. When present, its `onset` and `duration` columns
are required, while `trial_type` is optional. An inherited events file may also cover
several recordings. This does not permit a conversion to discard known source events
or class meaning, and successful XBrainLab import is not BIDS-validator certification.

### Current multi-recording limits

One imported collection currently requires the same channel count, names, order and
types. Raw recordings may have different sampling rates, but must be explicitly
resampled to a compatible rate before the current epoch workflow. Already-epoched
inputs must share a sampling rate and compatible epoch shape; raw and epoched inputs
cannot be mixed in one collection.

Select a compatible subset and use a separate import for another configuration.
Do not silently discard channels or rewrite sampling rates merely to make import
pass. General heterogeneous-collection support remains a gap relative to the broad
dataset target, not evidence that a valid BIDS dataset is invalid.

## Labels: internal, external, combined, or absent

The five-step import workflow covers all four choices. Both ordinary files and
BIDS folders expose **Continue without labels**. For BIDS this works whether an
events.tsv is present or absent; the changed choice is revalidated before import.
Skipping labels does not remove the source event files or make supervised epoching ready.

For BIDS without `events.tsv`, existing events inside the EEG file can also supply labels.
Review all observed events, explicitly select the training events and name each class;
the wizard requests a fresh backend review before import. Missing or inconsistent mappings
remain blocked. When `events.tsv` is available, it remains the preferred label source.

| Label source | What to review |
| --- | --- |
| Internal | Annotations, event codes or stimulus-channel events; decide which describe actual classes rather than timing, artifacts or boundaries. |
| External | Supported CSV/TSV/TXT tables or sequences, selected MAT arrays, or BIDS `events.tsv`; identify the label field and associated recording. |
| Combined | Internal events can supply trial timing while external rows supply classes; explicitly select the target events and mapping. |
| None | Choose **Continue without labels** for inspection and preprocessing, for ordinary files or BIDS folders. Supervised epoching and training remain unavailable without reviewed labels. |

External labels require one of the supported reviewed placements:

- **Time or sample placement:** specify the time unit, recording-relative or absolute
  sample origin, zero/one-based indexing where applicable, and duration semantics.
- **Event/trial order:** identify the actual target events or epochs, then verify
  count and order. Equal row counts alone do not establish alignment.
- **Event-code mapping:** explicitly associate codes with their reviewed meaning.

For BIDS time/interval placement, the selected label field can be independent of `value`.
For example, a generic flash code may repeat while a separate reviewed trial-ID field supplies
classes. Do not treat every acquisition or context marker as a training class. Saved recipes keep
your choices and source checks; large regenerable event previews are summarized and rebuilt on reload.

CSV, TXT and MAT are containers, not guarantees that arbitrary columns or nested
arrays can be understood automatically. This support concerns labels, not generic
CSV/MAT waveform import. An unreadable or misaligned supplied label file must not be
silently treated as an intentional no-label import. Class choices must not silently
erase acquisition annotations or turn excluded events into training classes.

Without reviewed usable classes, stop before the current supervised epoch workflow.
Raw normalization requests are deferred until per-epoch application; allowing raw
preprocessing does not mean normalization immediately changes an unlabelled waveform.
At least two distinct usable classes and valid event placement are necessary, but
not sufficient for every split or model. To revise labels after preprocessing,
follow the existing reset/review/reimport prerequisites; seamless late label
replacement while retaining downstream results is not promised.

## MOABB: minimum compatibility target, not the only source

The agreed route is **source dataset → official MOABB loader → reproducible EEG-BIDS
conversion → normal XBrainLab import**. XBrainLab does not need to parse every original
device format or provide a built-in MOABB downloader. The conversion must retain
waveforms within declared export precision, units, EEG channel order/types, events and
class meaning, recording identity and provenance. A source stimulus channel may be
represented by BIDS `events.tsv` instead of remaining a signal channel, but the omitted
non-EEG channel and preserved event mapping must be disclosed and checked. Any other
material transformation must also be disclosed; filtering or event relabelling cannot
be hidden in conversion.

For MOABB 1.5.0 conversion, review `return_all_modalities` on the dataset object.
The default converter channel selection keeps EEG only; it can omit EOG or other
auxiliary signals even when the loader returned them. For dataset constructors that
expose the option, `return_all_modalities=True` retains non-STIM channels. This is a
conversion option, not an XBrainLab setting or a guarantee that every converter works.
Always compare the selected source run with its actual exported run, including
`channels.tsv`; BrainVision's header alone does not preserve every channel type.

Also distinguish acquisition triggers from MOABB's reviewed task annotations. Some
loaders define a task interval starting after the trigger, and BIDS `value` IDs may be
renumbered. Verify class meaning and sample placement against the documented mapping
and interval; do not compare numeric IDs alone or treat every annotation as a class.

The acceptance denominator must be a complete, pinned MOABB release inventory, not
only datasets that happened to pass. Each dataset needs an explicit source selection,
conversion identity and observed import result. Unavailable downloads, restricted
access, missing conversion evidence and untested datasets remain visible gaps.
Testing selected subjects/runs is not proof that every byte of a corpus was exercised.

The pinned MOABB 1.5.0 inventory now has an explicit outcome for all 147 static,
non-synthetic exports: 110 representative loader-to-BIDS routes passed and 37 have a
specific source, license, loader, conversion or product blocker. No row is unexamined,
but this is not a 147/147 support result. Several exports share recordings, and most
runtime checks intentionally cover only a representative subject/session/run. See
[Dataset examples](case-studies/index.md) for bounded routes, not an all-MOABB
support badge.

## Outside this scope

New vendor-specific readers, XDF/live LSL, arbitrary CSV/MAT waveforms, MRI/MEG/iEEG
workflows, BIDS derivatives, automatic repair of corrupt inputs, and an unlabelled
epoch/training mode are not part of this contract. Successful import does not certify
a benchmark protocol, suitable train/test partitions or scientific model quality.

Continue with [Run an EEG workflow](workflow.md), or use
[Troubleshooting](troubleshooting.md) when review or a later stage is blocked.
