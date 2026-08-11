# Dataset Run Guides

<p class="page-kicker">Choose by source, paradigm, and review checkpoint</p>

<p class="portal-lede">Each page provides a route you can follow and a condition that
tells you when to stop. Evidence status is separate: a route is not treated as
completed until its dataset revision, app revision, run ID, and evidence files are
published together.</p>

<nav class="page-jumps" aria-label="Dataset guide sections" markdown>
[Evidence states](#evidence-states) · [Available routes](#available-routes) ·
[Evidence requirements](#how-a-route-becomes-evidence)
</nav>

## Evidence states

<div class="evidence-legend" markdown>
  <div><span class="evidence-badge evidence-badge--observed">Observed</span><p>An identified manual run is published with the dataset revision, app revision, run ID, and evidence files.</p></div>
  <div><span class="evidence-badge evidence-badge--bounded">Bounded</span><p>An identified automated or partial run supports only the named stage and scope.</p></div>
  <div><span class="evidence-badge evidence-badge--unverified">Unverified</span><p>The execution route is described, but its required checkpoints and evidence identity are not published.</p></div>
</div>

!!! info "Current status"
    All five dataset pages are **Unverified**. Graz and OpenNeuro provide scoped manual
    import routes. The three MOABB pages are pending execution guides generated from an
    exact source contract. None claims a complete run through saliency.

## Available routes

<div class="grid cards case-catalog route-cards" markdown>

-   <span class="case-format">GDF + MAT</span>

    **Graz / BCI Competition IV 2a**

    Page scope: `A01T`, `A02T`, `A03T` training recordings with matching MAT label files.

    **Followable checkpoint:** three EEG files, three paired label files, reviewed cue
    placement.

    **Published evidence:** Unverified.

    [Run the Graz route](graz-2a.md)

-   <span class="case-format">BIDS · EEGLAB SET + TSV</span>

    **OpenNeuro ds003061 P300**

    Page scope: `sub-001`, session `01`, task `P300`, runs `1`, `2`, and `3`.

    **Followable checkpoint:** one selected subject, three EEG files, three run-matched
    event carriers.

    **Published evidence:** Unverified.

    [Run the OpenNeuro route](openneuro-ds003061.md)

-   <span class="case-format">MOABB · GDF</span>

    **Ofner2017 motor imagery**

    Page scope: subject `1`, `imagination` session, runs `1`–`9`, with the seven
    specified embedded event labels.

    **Execution state:** Pending. **Published evidence:** Unverified.

    [Open the Ofner2017 guide](moabb-ofner2017.md)

-   <span class="case-format">MOABB · EDF+</span>

    **PhysionetMI run semantics**

    Page scope: subject `1`, session `0`, runs `4` and `6`; each run keeps its own
    meaning for `T1` and `T2`.

    **Execution state:** Pending. **Published evidence:** Unverified.

    [Open the PhysionetMI guide](moabb-physionetmi.md)

-   <span class="case-format">MOABB · BrainVision</span>

    **Lee2021Mobile ERP**

    Page scope: subject `1`, session `01`, standing `task-ERP` recording, with
    `Target` and `NonTarget` read from native BrainVision markers.

    **Execution state:** Pending. **Published evidence:** Unverified.

    [Open the Lee2021Mobile ERP guide](moabb-lee2021mobile-erp.md)

</div>

## How a route becomes evidence

A dataset route is promoted from **Unverified** only when one evidence record provides:

1. a stable manifest ID;
2. the dataset revision or file hashes;
3. the exact XBrainLab app revision;
4. a unique run ID;
5. evidence files for every promoted stage;
6. stage status and limits that agree with the case page.

The three MOABB guides are generated from the linked
[compact journey contract](../assets/manifests/moabb-datasets-v1.json). Their source
identity, selected scope, file hashes, choices, and limitations stay tied to that
contract. A page cannot promote a stage unless its matching evidence record adds a
complete run identity and immutable evidence files.

!!! info "A format is not a dataset claim"
    Converting one source into another file extension can check a parser, but it does
    not add an independent dataset or prove that arbitrary files of that format have
    correct event semantics.
