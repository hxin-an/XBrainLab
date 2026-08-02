#!/usr/bin/env python3
"""Report Data Interpretation format boundaries from the live command path."""

from __future__ import annotations

import argparse
import contextlib
import gc
import io
import json
import logging
import tempfile
import warnings
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import mne
import numpy as np
from scipy.io import savemat

if __package__:
    from scripts.dev.active_checkout import assert_active_checkout_import
else:
    from active_checkout import assert_active_checkout_import

ROOT = Path(__file__).resolve().parents[2]
assert_active_checkout_import(ROOT)

from XBrainLab.backend.application.commands import (
    ApplyInterpretationCommand,
    PreviewInterpretationCommand,
    ScanSourceCommand,
    ValidateInterpretationCommand,
)
from XBrainLab.backend.application.runtime import get_application_service
from XBrainLab.backend.application.service import ApplicationService
from XBrainLab.backend.study import Study
from XBrainLab.backend.utils.logger import logger as xbrainlab_logger

ARTIFACT_DIR = ROOT / "build" / "dev-artifacts" / "data-interpretation"
ARTIFACT_JSON = "format-capability-matrix.json"
ARTIFACT_MARKDOWN = "format-capability-matrix.md"
WORKFLOW_STAGES = ("scan", "preview", "validate", "apply")
REQUIRED_PUBLIC_SOURCE_FAMILIES = frozenset(
    {
        "BBCI",
        "MNE testing-data",
        "MNE-BIDS",
        "PhysioNet",
        "SCCN / EEGLAB",
    }
)
REQUIRED_PUBLIC_SOURCE_FAMILY_COUNT = len(REQUIRED_PUBLIC_SOURCE_FAMILIES)
REQUIRED_TIER_FORMATS = frozenset(
    {
        "BDF",
        "BIDS EEG / BrainVision",
        "BrainVision",
        "CNT",
        "CSV labels",
        "EDF",
        "EEGLAB SET",
        "Epoched FIF",
        "FIF",
        "FIF.GZ",
        "GDF",
        "GDF + MAT labels",
        "TSV labels",
        "TXT labels",
    }
)
REQUIRED_EXTERNAL_LABEL_CONTRACTS = frozenset(
    {
        "bids_interval",
        "csv_event_code",
        "csv_event_order",
        "csv_sample_time",
        "mat_event_order",
        "tsv_interval",
        "txt_event_order",
    }
)
INTERNAL_EVENT_CHOICE_PROFILES = frozenset(
    {
        "bbci_internal",
        "cnt_internal",
        "physionet_r04_internal",
        "sccn_internal",
    }
)
REQUIRED_INTERNAL_EVENT_PROFILES = INTERNAL_EVENT_CHOICE_PROFILES


@dataclass(frozen=True)
class FixtureFile:
    """A small synthetic file used only for scan/preview capability reporting."""

    relative_path: str
    kind: str = "binary"


@dataclass(frozen=True)
class ExpectedCapability:
    """Expected capability row for one detected file."""

    coverage_label: str
    filename: str
    format_name: str
    role: str
    status: str
    message_contains: str


@dataclass(frozen=True)
class FormatCase:
    """One scan/preview/validate source fixture."""

    case_id: str
    title: str
    source_entry: str
    source_hint: str
    expected_validation: str
    files: tuple[FixtureFile, ...]
    expected_capabilities: tuple[ExpectedCapability, ...]


@dataclass(frozen=True)
class RealWorkflowCase:
    """One real-file Data Interpretation lifecycle requirement."""

    case_id: str
    title: str
    evidence_scope: str
    dataset_source_id: str
    source_family: str
    format_name: str
    tier_category: str
    source_entry: str
    source_hint: str = "file"
    fixture_group: str = ""
    choice_profile: str = "raw_only"
    expected_label_apply_status: str = "not_applicable"
    expected_supervised_ready: bool = False
    expected_bids: bool = False
    label_contract: str = ""


@dataclass(frozen=True)
class ReviewedLabelCaseRequirement:
    """Fixed evidence requirement for one reviewed label/event case."""

    evidence_tier: str
    choice_profile: str


REQUIRED_REVIEWED_LABEL_CASE_REQUIREMENTS = {
    "checked_in_graz_gdf_mat": ReviewedLabelCaseRequirement(
        evidence_tier="supervised",
        choice_profile="a01t_external_labels",
    ),
    "public_physionet_motor_edf": ReviewedLabelCaseRequirement(
        evidence_tier="supervised",
        choice_profile="physionet_r04_internal",
    ),
    "public_bbci_gdf": ReviewedLabelCaseRequirement(
        evidence_tier="supervised",
        choice_profile="bbci_internal",
    ),
    "public_sccn_eeglab": ReviewedLabelCaseRequirement(
        evidence_tier="io_epoch_only",
        choice_profile="sccn_internal",
    ),
    "public_mne_cnt": ReviewedLabelCaseRequirement(
        evidence_tier="io_epoch_only",
        choice_profile="cnt_internal",
    ),
    "public_mne_bids_eeg": ReviewedLabelCaseRequirement(
        evidence_tier="label_apply_only",
        choice_profile="bids_events",
    ),
    "generated_csv_event_order": ReviewedLabelCaseRequirement(
        evidence_tier="generated_supervised_contract",
        choice_profile="generated_csv_event_order",
    ),
    "generated_csv_sample_time": ReviewedLabelCaseRequirement(
        evidence_tier="generated_supervised_contract",
        choice_profile="generated_csv_sample_time",
    ),
    "generated_tsv_interval": ReviewedLabelCaseRequirement(
        evidence_tier="generated_supervised_contract",
        choice_profile="generated_tsv_interval",
    ),
    "generated_csv_event_code": ReviewedLabelCaseRequirement(
        evidence_tier="generated_supervised_contract",
        choice_profile="generated_csv_event_code",
    ),
    "generated_txt_event_order": ReviewedLabelCaseRequirement(
        evidence_tier="generated_supervised_contract",
        choice_profile="generated_txt_event_order",
    ),
}
REQUIRED_REVIEWED_LABEL_CASE_IDS = frozenset(REQUIRED_REVIEWED_LABEL_CASE_REQUIREMENTS)


FORMAT_CASES: tuple[FormatCase, ...] = (
    FormatCase(
        case_id="gdf_with_mat_labels",
        title="GDF recording with external MAT labels",
        source_entry=".",
        source_hint="auto",
        expected_validation="needs_confirmation",
        files=(
            FixtureFile("sub-01_ses-01_task-mi_run-1.gdf"),
            FixtureFile("sub-01_ses-01_task-mi_run-1.mat", "mat_labels"),
        ),
        expected_capabilities=(
            ExpectedCapability(
                "GDF recording",
                "sub-01_ses-01_task-mi_run-1.gdf",
                "GDF",
                "eeg",
                "needs_review",
                "trial anchor",
            ),
            ExpectedCapability(
                "MAT labels",
                "sub-01_ses-01_task-mi_run-1.mat",
                "MAT labels",
                "external_labels",
                "needs_review",
                "variable selection",
            ),
        ),
    ),
    FormatCase(
        case_id="edf_recording",
        title="EDF recording with annotation review boundary",
        source_entry="sub-01_ses-01_task-rest_run-1.edf",
        source_hint="file",
        expected_validation="needs_confirmation",
        files=(FixtureFile("sub-01_ses-01_task-rest_run-1.edf"),),
        expected_capabilities=(
            ExpectedCapability(
                "EDF recording",
                "sub-01_ses-01_task-rest_run-1.edf",
                "EDF",
                "eeg",
                "needs_review",
                "annotations",
            ),
        ),
    ),
    FormatCase(
        case_id="bdf_recording",
        title="BDF recording with annotation review boundary",
        source_entry="sub-01_ses-01_task-rest_run-2.bdf",
        source_hint="file",
        expected_validation="needs_confirmation",
        files=(FixtureFile("sub-01_ses-01_task-rest_run-2.bdf"),),
        expected_capabilities=(
            ExpectedCapability(
                "BDF recording",
                "sub-01_ses-01_task-rest_run-2.bdf",
                "EDF",
                "eeg",
                "needs_review",
                "EDF / BDF",
            ),
        ),
    ),
    FormatCase(
        case_id="eeglab_set",
        title="EEGLAB SET with boundary-marker review",
        source_entry="sub-01_ses-01_task-mi_run-1.set",
        source_hint="file",
        expected_validation="needs_confirmation",
        files=(FixtureFile("sub-01_ses-01_task-mi_run-1.set", "eeglab_set"),),
        expected_capabilities=(
            ExpectedCapability(
                "EEGLAB SET",
                "sub-01_ses-01_task-mi_run-1.set",
                "EEGLAB",
                "eeg",
                "needs_review",
                "boundary",
            ),
        ),
    ),
    FormatCase(
        case_id="brainvision_recording",
        title="BrainVision header plus marker sidecar",
        source_entry=".",
        source_hint="folder",
        expected_validation="needs_confirmation",
        files=(
            FixtureFile("sub-01_ses-01_task-mi_run-1.vhdr", "brainvision_vhdr"),
            FixtureFile("sub-01_ses-01_task-mi_run-1.vmrk", "brainvision_vmrk"),
            FixtureFile("sub-01_ses-01_task-mi_run-1.eeg"),
        ),
        expected_capabilities=(
            ExpectedCapability(
                "BrainVision VHDR",
                "sub-01_ses-01_task-mi_run-1.vhdr",
                "BrainVision",
                "eeg",
                "needs_review",
                "marker sidecars",
            ),
            ExpectedCapability(
                "BrainVision VMRK",
                "sub-01_ses-01_task-mi_run-1.vmrk",
                "BrainVision markers",
                "sidecar",
                "context",
                "associated .vhdr",
            ),
        ),
    ),
    FormatCase(
        case_id="mne_fif_recording",
        title="MNE FIF recording with complete filename metadata",
        source_entry="sub-01_ses-01_task-rest_run-1_raw.fif",
        source_hint="file",
        expected_validation="safe",
        files=(FixtureFile("sub-01_ses-01_task-rest_run-1_raw.fif"),),
        expected_capabilities=(
            ExpectedCapability(
                "MNE FIF",
                "sub-01_ses-01_task-rest_run-1_raw.fif",
                "MNE FIF",
                "eeg",
                "supported",
                "loaded as an EEG recording",
            ),
        ),
    ),
    FormatCase(
        case_id="bids_events_root",
        title="BIDS EEG root with events.tsv",
        source_entry=".",
        source_hint="auto",
        expected_validation="blocked",
        files=(
            FixtureFile("dataset_description.json", "dataset_description"),
            FixtureFile("sub-01/ses-01/eeg/sub-01_ses-01_task-mi_run-1_raw.fif"),
            FixtureFile(
                "sub-01/ses-01/eeg/sub-01_ses-01_task-mi_run-1_events.tsv",
                "bids_events",
            ),
        ),
        expected_capabilities=(
            ExpectedCapability(
                "BIDS events.tsv",
                "sub-01_ses-01_task-mi_run-1_events.tsv",
                "BIDS events",
                "external_labels",
                "needs_review",
                "onset and duration",
            ),
        ),
    ),
    FormatCase(
        case_id="tabular_and_text_labels",
        title="Generic CSV, TSV, and TXT label carriers",
        source_entry=".",
        source_hint="folder",
        expected_validation="blocked",
        files=(
            FixtureFile("sub-01_ses-01_task-mi_run-1_raw.fif"),
            FixtureFile("labels.csv", "csv_labels"),
            FixtureFile("labels.tsv", "tsv_labels"),
            FixtureFile("labels.txt", "txt_labels"),
        ),
        expected_capabilities=(
            ExpectedCapability(
                "CSV labels",
                "labels.csv",
                "CSV / TSV labels",
                "external_labels",
                "needs_review",
                "label column",
            ),
            ExpectedCapability(
                "TSV labels",
                "labels.tsv",
                "CSV / TSV labels",
                "external_labels",
                "needs_review",
                "label column",
            ),
            ExpectedCapability(
                "TXT labels",
                "labels.txt",
                "TXT labels",
                "external_labels",
                "needs_review",
                "trial-order",
            ),
        ),
    ),
    FormatCase(
        case_id="xdf_lsl_device_export",
        title="XDF / LSL stream export blocked until stream selection exists",
        source_entry="session01_streams.xdf",
        source_hint="device_export",
        expected_validation="blocked",
        files=(FixtureFile("session01_streams.xdf"),),
        expected_capabilities=(
            ExpectedCapability(
                "XDF / LSL stream export",
                "session01_streams.xdf",
                "XDF / LSL",
                "device_export",
                "blocked",
                "stream selection",
            ),
        ),
    ),
)


REAL_WORKFLOW_CASES: tuple[RealWorkflowCase, ...] = (
    RealWorkflowCase(
        case_id="checked_in_graz_gdf_mat",
        title="Checked-in Graz GDF with external MAT labels",
        evidence_scope="checked_in_source",
        dataset_source_id="bci-competition-iv-2a",
        source_family="Graz / BCI Competition IV 2a",
        format_name="GDF + MAT labels",
        tier_category="GDF / BNCI / BCI Competition",
        source_entry="tests/fixtures/data/A01T.gdf",
        choice_profile="a01t_external_labels",
        expected_label_apply_status="applied",
        expected_supervised_ready=True,
        label_contract="mat_event_order",
    ),
    RealWorkflowCase(
        case_id="derived_fif_raw",
        title="A01T-derived raw FIF format lifecycle",
        evidence_scope="derived_format",
        dataset_source_id="bci-competition-iv-2a-derived",
        source_family="Graz A01T derived formats",
        format_name="FIF",
        tier_category="Generic EEG files with internal events / annotations",
        source_entry="tests/fixtures/data/multiformat/A01T-mini-real_raw.fif",
    ),
    RealWorkflowCase(
        case_id="derived_fif_gz_raw",
        title="A01T-derived compressed FIF format lifecycle",
        evidence_scope="derived_format",
        dataset_source_id="bci-competition-iv-2a-derived",
        source_family="Graz A01T derived formats",
        format_name="FIF.GZ",
        tier_category="Generic EEG files with internal events / annotations",
        source_entry="tests/fixtures/data/multiformat/A01T-mini-real_raw.fif.gz",
    ),
    RealWorkflowCase(
        case_id="derived_fif_epochs",
        title="A01T-derived epoched FIF format lifecycle",
        evidence_scope="derived_format",
        dataset_source_id="bci-competition-iv-2a-derived",
        source_family="Graz A01T derived formats",
        format_name="Epoched FIF",
        tier_category="Generic EEG files with internal events / annotations",
        source_entry="tests/fixtures/data/multiformat/A01T-mini-real-epo.fif",
    ),
    RealWorkflowCase(
        case_id="derived_edf",
        title="A01T-derived EDF format lifecycle",
        evidence_scope="derived_format",
        dataset_source_id="bci-competition-iv-2a-derived",
        source_family="Graz A01T derived formats",
        format_name="EDF",
        tier_category="Generic EEG files with internal events / annotations",
        source_entry="tests/fixtures/data/multiformat/A01T-mini-real.edf",
    ),
    RealWorkflowCase(
        case_id="derived_bdf",
        title="A01T-derived BDF format lifecycle",
        evidence_scope="derived_format",
        dataset_source_id="bci-competition-iv-2a-derived",
        source_family="Graz A01T derived formats",
        format_name="BDF",
        tier_category="Generic EEG files with internal events / annotations",
        source_entry="tests/fixtures/data/multiformat/A01T-mini-real.bdf",
    ),
    RealWorkflowCase(
        case_id="derived_brainvision",
        title="A01T-derived BrainVision format lifecycle",
        evidence_scope="derived_format",
        dataset_source_id="bci-competition-iv-2a-derived",
        source_family="Graz A01T derived formats",
        format_name="BrainVision",
        tier_category="Generic EEG files with internal events / annotations",
        source_entry="tests/fixtures/data/multiformat/A01T-mini-real.vhdr",
    ),
    RealWorkflowCase(
        case_id="derived_eeglab",
        title="A01T-derived EEGLAB SET format lifecycle",
        evidence_scope="derived_format",
        dataset_source_id="bci-competition-iv-2a-derived",
        source_family="Graz A01T derived formats",
        format_name="EEGLAB SET",
        tier_category="Generic EEG files with internal events / annotations",
        source_entry="tests/fixtures/data/multiformat/A01T-mini-real.set",
    ),
    RealWorkflowCase(
        case_id="public_physionet_rest_edf",
        title="PhysioNet EEGMMI rest EDF import lifecycle",
        evidence_scope="public_source",
        dataset_source_id="physionet-eegmmidb",
        source_family="PhysioNet",
        format_name="EDF",
        tier_category="Generic EEG files with internal events / annotations",
        source_entry=("tests/fixtures/data/public/physionet-eegmmidb-S008R01.edf"),
        fixture_group="physionet-edf-rest",
    ),
    RealWorkflowCase(
        case_id="public_physionet_motor_edf",
        title="PhysioNet EEGMMI motor EDF reviewed-event lifecycle",
        evidence_scope="public_source",
        dataset_source_id="physionet-eegmmidb",
        source_family="PhysioNet",
        format_name="EDF",
        tier_category="Generic EEG files with internal events / annotations",
        source_entry=("tests/fixtures/data/public/physionet-eegmmidb-S008R04.edf"),
        fixture_group="physionet-edf-motor",
        choice_profile="physionet_r04_internal",
        expected_supervised_ready=True,
    ),
    RealWorkflowCase(
        case_id="public_bbci_gdf",
        title="BBCI Competition III GDF reviewed-event lifecycle",
        evidence_scope="public_source",
        dataset_source_id="bbci-competition-iii-iii-b",
        source_family="BBCI",
        format_name="GDF",
        tier_category="GDF / BNCI / BCI Competition",
        source_entry="tests/fixtures/data/public/bbci-competition-iii-O3VR.gdf",
        fixture_group="bbci-gdf",
        choice_profile="bbci_internal",
        expected_supervised_ready=True,
    ),
    RealWorkflowCase(
        case_id="public_sccn_eeglab",
        title="SCCN EEGLAB IO/epoch-only reviewed-event lifecycle",
        evidence_scope="public_source",
        dataset_source_id="sccn-eeglab-tutorial",
        source_family="SCCN / EEGLAB",
        format_name="EEGLAB SET",
        tier_category="Generic EEG files with internal events / annotations",
        source_entry="tests/fixtures/data/public/sccn-eeglab_data.set",
        fixture_group="sccn-eeglab",
        choice_profile="sccn_internal",
        expected_supervised_ready=False,
    ),
    RealWorkflowCase(
        case_id="public_mne_cnt",
        title="MNE testing-data CNT reviewed-event lifecycle",
        evidence_scope="public_source",
        dataset_source_id="mne-testing-data",
        source_family="MNE testing-data",
        format_name="CNT",
        tier_category="Generic EEG files with internal events / annotations",
        source_entry="tests/fixtures/data/public/scan41_short.cnt",
        fixture_group="mne-testing-cnt",
        choice_profile="cnt_internal",
    ),
    RealWorkflowCase(
        case_id="public_mne_brainvision",
        title="MNE testing-data BrainVision import lifecycle",
        evidence_scope="public_source",
        dataset_source_id="mne-testing-data",
        source_family="MNE testing-data",
        format_name="BrainVision",
        tier_category="Generic EEG files with internal events / annotations",
        source_entry="tests/fixtures/data/public/test_NO.vhdr",
        fixture_group="mne-testing-brainvision",
    ),
    RealWorkflowCase(
        case_id="public_mne_bids_eeg",
        title="MNE-BIDS tiny EEG events lifecycle",
        evidence_scope="public_source",
        dataset_source_id="mne-bids-tiny-eeg",
        source_family="MNE-BIDS",
        format_name="BIDS EEG / BrainVision",
        tier_category="BIDS EEG folder",
        source_entry="tests/fixtures/data/public/mne-bids-tiny-eeg",
        source_hint="bids",
        fixture_group="mne-bids-tiny-eeg",
        choice_profile="bids_events",
        expected_label_apply_status="applied",
        expected_bids=True,
        label_contract="bids_interval",
    ),
)


GENERATED_CONTRACT_CASES: tuple[RealWorkflowCase, ...] = (
    RealWorkflowCase(
        case_id="generated_csv_event_order",
        title="Generated CSV label sequence aligned to EEG event order",
        evidence_scope="generated_contract",
        dataset_source_id="generated-external-label-contracts",
        source_family="Generated contract fixture",
        format_name="CSV labels",
        tier_category="External label carriers",
        source_entry="generated_csv_event_order",
        source_hint="folder",
        choice_profile="generated_csv_event_order",
        expected_label_apply_status="applied",
        expected_supervised_ready=True,
        label_contract="csv_event_order",
    ),
    RealWorkflowCase(
        case_id="generated_csv_sample_time",
        title="Generated CSV sample-index label placement",
        evidence_scope="generated_contract",
        dataset_source_id="generated-external-label-contracts",
        source_family="Generated contract fixture",
        format_name="CSV labels",
        tier_category="External label carriers",
        source_entry="generated_csv_sample_time",
        source_hint="folder",
        choice_profile="generated_csv_sample_time",
        expected_label_apply_status="applied",
        expected_supervised_ready=True,
        label_contract="csv_sample_time",
    ),
    RealWorkflowCase(
        case_id="generated_tsv_interval",
        title="Generated TSV onset-duration interval placement",
        evidence_scope="generated_contract",
        dataset_source_id="generated-external-label-contracts",
        source_family="Generated contract fixture",
        format_name="TSV labels",
        tier_category="External label carriers",
        source_entry="generated_tsv_interval",
        source_hint="folder",
        choice_profile="generated_tsv_interval",
        expected_label_apply_status="applied",
        expected_supervised_ready=True,
        label_contract="tsv_interval",
    ),
    RealWorkflowCase(
        case_id="generated_csv_event_code",
        title="Generated CSV event-code label mapping",
        evidence_scope="generated_contract",
        dataset_source_id="generated-external-label-contracts",
        source_family="Generated contract fixture",
        format_name="CSV labels",
        tier_category="External label carriers",
        source_entry="generated_csv_event_code",
        source_hint="folder",
        choice_profile="generated_csv_event_code",
        expected_label_apply_status="applied",
        expected_supervised_ready=True,
        label_contract="csv_event_code",
    ),
    RealWorkflowCase(
        case_id="generated_txt_event_order",
        title="Generated TXT integer label sequence aligned to EEG event order",
        evidence_scope="generated_contract",
        dataset_source_id="generated-external-label-contracts",
        source_family="Generated contract fixture",
        format_name="TXT labels",
        tier_category="External label carriers",
        source_entry="generated_txt_event_order",
        source_hint="folder",
        choice_profile="generated_txt_event_order",
        expected_label_apply_status="applied",
        expected_supervised_ready=True,
        label_contract="txt_event_order",
    ),
)

REQUIRED_REAL_WORKFLOW_CASE_IDS = frozenset(
    {
        "checked_in_graz_gdf_mat",
        "derived_bdf",
        "derived_brainvision",
        "derived_edf",
        "derived_eeglab",
        "derived_fif_epochs",
        "derived_fif_gz_raw",
        "derived_fif_raw",
        "generated_csv_event_code",
        "generated_csv_event_order",
        "generated_csv_sample_time",
        "generated_tsv_interval",
        "generated_txt_event_order",
        "public_bbci_gdf",
        "public_mne_bids_eeg",
        "public_mne_brainvision",
        "public_mne_cnt",
        "public_physionet_motor_edf",
        "public_physionet_rest_edf",
        "public_sccn_eeglab",
    }
)
REQUIRED_CHECKED_IN_AND_DERIVED_CASE_IDS = frozenset(
    {
        "checked_in_graz_gdf_mat",
        "derived_bdf",
        "derived_brainvision",
        "derived_edf",
        "derived_eeglab",
        "derived_fif_epochs",
        "derived_fif_gz_raw",
        "derived_fif_raw",
    }
)
REQUIRED_PUBLIC_SOURCE_WORKFLOW_CASE_IDS = frozenset(
    {
        "public_bbci_gdf",
        "public_mne_bids_eeg",
        "public_mne_brainvision",
        "public_mne_cnt",
        "public_physionet_motor_edf",
        "public_physionet_rest_edf",
        "public_sccn_eeglab",
    }
)
REQUIRED_GENERATED_CONTRACT_CASE_IDS = frozenset(
    {
        "generated_csv_event_code",
        "generated_csv_event_order",
        "generated_csv_sample_time",
        "generated_tsv_interval",
        "generated_txt_event_order",
    }
)
REQUIRED_CASE_EVIDENCE_SCOPES = {
    "checked_in_graz_gdf_mat": "checked_in_source",
    "derived_bdf": "derived_format",
    "derived_brainvision": "derived_format",
    "derived_edf": "derived_format",
    "derived_eeglab": "derived_format",
    "derived_fif_epochs": "derived_format",
    "derived_fif_gz_raw": "derived_format",
    "derived_fif_raw": "derived_format",
    "generated_csv_event_code": "generated_contract",
    "generated_csv_event_order": "generated_contract",
    "generated_csv_sample_time": "generated_contract",
    "generated_tsv_interval": "generated_contract",
    "generated_txt_event_order": "generated_contract",
    "public_bbci_gdf": "public_source",
    "public_mne_bids_eeg": "public_source",
    "public_mne_brainvision": "public_source",
    "public_mne_cnt": "public_source",
    "public_physionet_motor_edf": "public_source",
    "public_physionet_rest_edf": "public_source",
    "public_sccn_eeglab": "public_source",
}

PUBLIC_FIXTURE_FACT_CONTRACTS: dict[str, dict[str, Any]] = {
    "public_physionet_rest_edf": {
        "source_entry": "tests/fixtures/data/public/physionet-eegmmidb-S008R01.edf",
        "sampling_frequency_hz": 160.0,
        "channel_count": 64,
        "channel_type_counts": {"eeg": 64},
        "channel_unit_counts": {"V": 64},
        "source_unit_counts": {"uV": 64},
        "sample_count": 9760,
        "embedded_event_count": 1,
        "embedded_event_labels": ["T0"],
        "interpretation_event_count": 1,
        "import_warnings": [],
    },
    "public_physionet_motor_edf": {
        "source_entry": "tests/fixtures/data/public/physionet-eegmmidb-S008R04.edf",
        "sampling_frequency_hz": 160.0,
        "channel_count": 64,
        "channel_type_counts": {"eeg": 64},
        "channel_unit_counts": {"V": 64},
        "source_unit_counts": {"uV": 64},
        "sample_count": 19680,
        "embedded_event_count": 30,
        "embedded_event_labels": ["T0", "T1", "T2"],
        "interpretation_event_count": 30,
        "import_warnings": [],
    },
    "public_bbci_gdf": {
        "source_entry": "tests/fixtures/data/public/bbci-competition-iii-O3VR.gdf",
        "sampling_frequency_hz": 125.0,
        "channel_count": 2,
        "channel_type_counts": {"eeg": 2},
        "channel_unit_counts": {"V": 2},
        "source_unit_counts": {"unknown": 2},
        "sample_count": 729558,
        "embedded_event_count": 2560,
        "embedded_event_labels": ["768", "769", "770", "781", "783", "785"],
        "interpretation_event_count": 2560,
        "import_warnings": [
            {
                "category": "RuntimeWarning",
                "message": (
                    "Limited 1 annotation(s) that were expanding outside the data "
                    "range."
                ),
                "count": 1,
            }
        ],
    },
    "public_sccn_eeglab": {
        "source_entry": "tests/fixtures/data/public/sccn-eeglab_data.set",
        "sampling_frequency_hz": 128.0,
        "channel_count": 32,
        "channel_type_counts": {"eeg": 32},
        "channel_unit_counts": {"V": 32},
        "source_unit_counts": {"unknown": 32},
        "sample_count": 30504,
        "embedded_event_count": 154,
        "embedded_event_labels": ["rt", "square"],
        "interpretation_event_count": 154,
        "import_warnings": [],
    },
    "public_mne_cnt": {
        "source_entry": "tests/fixtures/data/public/scan41_short.cnt",
        "sampling_frequency_hz": 400.0,
        "channel_count": 128,
        "channel_type_counts": {"eeg": 128},
        "channel_unit_counts": {"V": 128},
        "source_unit_counts": {"unknown": 128},
        "sample_count": 3070,
        "embedded_event_count": 6,
        "embedded_event_labels": ["0", "109", "7"],
        "interpretation_event_count": 6,
        "import_warnings": [
            {
                "category": "RuntimeWarning",
                "message": "Could not parse meas date from the header. Setting to None.",
                "count": 1,
            },
            {
                "category": "RuntimeWarning",
                "message": (
                    "Could not define the number of bytes automatically. "
                    "Defaulting to 2."
                ),
                "count": 1,
            },
        ],
    },
    "public_mne_brainvision": {
        "source_entry": "tests/fixtures/data/public/test_NO.vhdr",
        "sampling_frequency_hz": 5000.0,
        "channel_count": 65,
        "channel_type_counts": {"eeg": 65},
        "channel_unit_counts": {"V": 65},
        "source_unit_counts": {"uV": 65},
        "sample_count": 2238,
        "embedded_event_count": 0,
        "embedded_event_labels": [],
        "interpretation_event_count": 0,
        "import_warnings": [],
    },
    "public_mne_bids_eeg": {
        "source_entry": (
            "tests/fixtures/data/public/mne-bids-tiny-eeg/sub-01/ses-eeg/eeg/"
            "sub-01_ses-eeg_task-rest_eeg.vhdr"
        ),
        "sampling_frequency_hz": 5000.0,
        "channel_count": 69,
        "channel_type_counts": {"eeg": 67, "misc": 2},
        "channel_unit_counts": {"V": 67, "degC": 1, "none": 1},
        "source_unit_counts": {"C": 1, "S": 1, "uV": 67},
        "sample_count": 10000,
        "embedded_event_count": 1,
        "embedded_event_labels": [
            "Comment/ControlBox is not connected via USB",
        ],
        "interpretation_event_count": 2,
        "import_warnings": [],
    },
}
REQUIRED_PUBLIC_FIXTURE_FACT_CASE_IDS = frozenset(PUBLIC_FIXTURE_FACT_CONTRACTS)

EXPECTED_INTERNAL_CHOICE_SIGNATURES = {
    "public_physionet_motor_edf": {
        "label_event_codes": ["T1", "T2"],
        "not_label_event_codes": ["T0"],
        "class_map": {"T1": "left fist", "T2": "right fist"},
        "run_event_mappings": {
            "physionet-eegmmidb-S008R04.edf": {
                "T1": "left fist",
                "T2": "right fist",
            }
        },
    },
    "public_bbci_gdf": {
        "label_event_codes": ["769", "770"],
        "not_label_event_codes": ["768", "781", "783", "785"],
        "class_map": {"769": "769", "770": "770"},
        "run_event_mappings": {},
    },
    "public_sccn_eeglab": {
        "label_event_codes": [],
        "not_label_event_codes": ["rt", "square"],
        "class_map": {},
        "run_event_mappings": {},
    },
    "public_mne_cnt": {
        "label_event_codes": ["7"],
        "not_label_event_codes": ["0", "109"],
        "class_map": {"7": "7"},
        "run_event_mappings": {},
    },
}

EXPECTED_EXTERNAL_CHOICE_SIGNATURES = {
    "checked_in_graz_gdf_mat": {
        "selected_label_field": "classlabel",
        "selected_anchor": "768",
        "selected_target_event_codes": ["768"],
        "selected_duration_field": "",
        "placement_method": "eeg_event",
        "time_model": "trial_order",
        "sample_index_base": "",
        "sample_index_origin": "",
        "class_map": {"1": "1", "2": "2", "3": "3", "4": "4"},
    },
    "public_mne_bids_eeg": {
        "selected_label_field": "trial_type",
        "selected_anchor": "onset",
        "selected_target_event_codes": [],
        "selected_duration_field": "duration",
        "placement_method": "interval",
        "time_model": "seconds",
        "sample_index_base": "",
        "sample_index_origin": "",
        "class_map": {"show_stimulus": "show stimulus"},
        "value_decisions": {
            "show_stimulus": {
                "role": "stimulus",
                "keep_event": True,
                "use_as_class": True,
                "class_name": "show stimulus",
            },
            "start_experiment": {
                "role": "system",
                "keep_event": False,
                "use_as_class": False,
                "class_name": None,
            },
        },
    },
    "generated_csv_event_order": {
        "selected_label_field": "label",
        "selected_anchor": "768",
        "selected_target_event_codes": ["768"],
        "selected_duration_field": "",
        "placement_method": "eeg_event",
        "time_model": "trial_order",
        "sample_index_base": "",
        "sample_index_origin": "",
        "class_map": {"1": "Left", "2": "Right"},
    },
    "generated_csv_sample_time": {
        "selected_label_field": "label",
        "selected_anchor": "sample",
        "selected_target_event_codes": [],
        "selected_duration_field": "",
        "placement_method": "time_field",
        "time_model": "sample_index",
        "sample_index_base": "zero_based",
        "sample_index_origin": "recording_relative",
        "class_map": {"left": "Left", "right": "Right"},
    },
    "generated_tsv_interval": {
        "selected_label_field": "label",
        "selected_anchor": "onset",
        "selected_target_event_codes": [],
        "selected_duration_field": "duration",
        "placement_method": "interval",
        "time_model": "seconds",
        "sample_index_base": "",
        "sample_index_origin": "",
        "class_map": {"left": "Left", "right": "Right"},
    },
    "generated_csv_event_code": {
        "selected_label_field": "label",
        "selected_anchor": "event_code",
        "selected_target_event_codes": [],
        "selected_duration_field": "",
        "placement_method": "event_code",
        "time_model": "seconds",
        "sample_index_base": "",
        "sample_index_origin": "",
        "class_map": {"left": "Left", "right": "Right"},
    },
    "generated_txt_event_order": {
        "selected_label_field": "line label sequence",
        "selected_anchor": "768",
        "selected_target_event_codes": ["768"],
        "selected_duration_field": "",
        "placement_method": "eeg_event",
        "time_model": "trial_order",
        "sample_index_base": "",
        "sample_index_origin": "",
        "class_map": {"1": "Left", "2": "Right"},
    },
}

GENERATED_LABEL_FILENAMES = {
    "generated_csv_event_order": "sub-01_task-mi_run-1_labels.csv",
    "generated_csv_sample_time": "sub-01_task-mi_run-1_labels.csv",
    "generated_tsv_interval": "sub-01_task-mi_run-1_labels.tsv",
    "generated_csv_event_code": "sub-01_task-mi_run-1_event_codes.csv",
    "generated_txt_event_order": "sub-01_task-mi_run-1_labels.txt",
}
GENERATED_EEG_FILENAME = "sub-01_task-mi_run-1_raw.fif"


def capture_public_fixture_facts(
    case_id: str,
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    """Load one pinned public fixture and verify its physical source facts."""
    contract = PUBLIC_FIXTURE_FACT_CONTRACTS.get(case_id)
    if contract is None:
        return {
            "status": "not_applicable",
            "case_id": case_id,
            "mismatches": [],
        }
    source_path = (repo_root / str(contract["source_entry"])).resolve()
    result: dict[str, Any] = {
        "status": "failed",
        "case_id": case_id,
        "source_entry": str(contract["source_entry"]),
        "source_path": str(source_path),
        "mismatches": [],
    }
    if not source_path.is_file():
        result["mismatches"] = [f"fixture fact source is missing: {source_path}"]
        return result

    from XBrainLab.backend.load_data.raw_data_loader import load_raw_data

    try:
        with (
            warnings.catch_warnings(record=True) as caught_warnings,
            mne.use_log_level("WARNING"),
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            warnings.simplefilter("always")
            raw = load_raw_data(str(source_path))
            mne_data = raw.get_mne()
            event_summary = raw.get_event_summary(allow_scan=True)
    except Exception as exc:
        result["mismatches"] = [
            f"fixture fact load failed: {type(exc).__name__}: {exc}"
        ]
        return result

    warning_counts = Counter(
        (warning.category.__name__, str(warning.message).strip())
        for warning in caught_warnings
    )
    channel_types = Counter(str(item) for item in mne_data.get_channel_types())
    channel_units = Counter(
        _canonical_channel_unit(channel.get("unit")) for channel in mne_data.info["chs"]
    )
    source_units = _source_unit_counts(mne_data, len(mne_data.ch_names))
    result.update(
        {
            "sampling_frequency_hz": float(mne_data.info["sfreq"]),
            "channel_count": len(mne_data.ch_names),
            "channel_type_counts": dict(sorted(channel_types.items())),
            "channel_unit_counts": dict(sorted(channel_units.items())),
            "source_unit_counts": source_units,
            "sample_count": len(mne_data.times),
            "embedded_event_count": int(event_summary.get("count") or 0),
            "embedded_event_labels": sorted(
                str(item) for item in event_summary.get("labels", [])
            ),
            "import_warnings": [
                {
                    "category": category,
                    "message": message,
                    "count": count,
                }
                for (category, message), count in warning_counts.items()
            ],
        }
    )
    compared_fields = (
        "sampling_frequency_hz",
        "channel_count",
        "channel_type_counts",
        "channel_unit_counts",
        "source_unit_counts",
        "sample_count",
        "embedded_event_count",
        "embedded_event_labels",
        "import_warnings",
    )
    mismatches = [
        f"{field}: expected {contract[field]!r}, observed {result[field]!r}"
        for field in compared_fields
        if result[field] != contract[field]
    ]
    result["mismatches"] = mismatches
    result["status"] = "passed" if not mismatches else "failed"
    return result


def _canonical_channel_unit(value: object) -> str:
    try:
        unit_code = int(cast(Any, value))
    except (TypeError, ValueError):
        return "unknown"
    return {
        -1: "none",
        107: "V",
        114: "degC",
    }.get(unit_code, f"FIFF:{unit_code}")


def _source_unit_counts(mne_data: Any, channel_count: int) -> dict[str, int]:
    raw_units = getattr(mne_data, "_orig_units", {})
    units = (
        [str(item) for item in raw_units.values()]
        if isinstance(raw_units, Mapping)
        else []
    )
    counts = Counter(_normalize_source_unit(item) for item in units)
    unknown_count = max(0, channel_count - len(units))
    if unknown_count:
        counts["unknown"] += unknown_count
    return dict(sorted(counts.items()))


def _normalize_source_unit(value: str) -> str:
    return value.replace("\N{MICRO SIGN}", "u").replace(
        "\N{GREEK SMALL LETTER MU}", "u"
    )


def build_format_capability_snapshot() -> dict[str, Any]:
    """Build a matrix from actual ApplicationService scan/preview/validate calls."""
    with (
        _suppress_application_info_logs(),
        mne.use_log_level("ERROR"),
        tempfile.TemporaryDirectory(prefix="xbrainlab-di-format-") as temp_dir,
    ):
        fixture_root = Path(temp_dir)
        rows: list[dict[str, Any]] = []
        case_summaries: list[dict[str, Any]] = []
        for case in FORMAT_CASES:
            case_dir = fixture_root / case.case_id
            _write_case_fixture(case_dir, case)
            case_result = _run_case(case_dir, case)
            case_summaries.append(case_result["case_summary"])
            rows.extend(case_result["rows"])

    coverage_labels = [str(row["coverage_label"]) for row in rows]
    expected_row_count = sum(len(case.expected_capabilities) for case in FORMAT_CASES)
    has_required_rows = expected_row_count > 0 and len(rows) == expected_row_count
    all_observed = has_required_rows and all(bool(row["observed"]) for row in rows)
    all_matched = all_observed and all(bool(row["matches_expected"]) for row in rows)
    return {
        "generator": "scripts/dev/report_data_interpretation_format_matrix.py",
        "command_path": [
            "ApplicationService.execute(ScanSourceCommand)",
            "ApplicationService.execute(PreviewInterpretationCommand)",
            "ApplicationService.execute(ValidateInterpretationCommand)",
        ],
        "summary": {
            "case_count": len(FORMAT_CASES),
            "row_count": len(rows),
            "expected_row_count": expected_row_count,
            "coverage_labels": coverage_labels,
            "statuses": sorted({str(row["status"]) for row in rows}),
            "validation_decisions": sorted(
                {str(row["validation_decision"]) for row in rows}
            ),
            "all_expected_capabilities_observed": all_observed,
            "all_expected_capabilities_match": all_matched,
        },
        "cases": case_summaries,
        "rows": rows,
        "claim_boundary": {
            "supports": (
                "Data Interpretation scan, preview, and validation expose "
                "user-facing format capability boundaries for representative "
                "EEG recordings, label carriers, BIDS events, and blocked XDF / "
                "LSL stream exports."
            ),
            "does_not_support": (
                "This matrix does not implement an XDF / LSL stream parser, "
                "raw-event-anchor-specific GDF / MAT alignment, or a full manual "
                "compatibility certification across real public datasets."
            ),
        },
    }


def run_real_workflow_case(
    case: RealWorkflowCase,
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    """Run one real file through scan, preview, validate, and apply."""
    source_path = (repo_root / case.source_entry).resolve()
    stages = {stage: {"ok": False, "message": "Not run."} for stage in WORKFLOW_STAGES}
    result: dict[str, Any] = {
        "case_id": case.case_id,
        "title": case.title,
        "evidence_level": (
            "generated_contract_workflow"
            if case.evidence_scope == "generated_contract"
            else "real_application_workflow"
        ),
        "evidence_scope": case.evidence_scope,
        "dataset_source_id": case.dataset_source_id,
        "source_family": case.source_family,
        "format": case.format_name,
        "tier_category": case.tier_category,
        "source_entry": case.source_entry,
        "source_hint": case.source_hint,
        "fixture_group": case.fixture_group,
        "protocol_choice_profile": case.choice_profile,
        "label_contract": case.label_contract,
        "status": "failed",
        "failed_stage": "fixture",
        "stages": stages,
        "observations": {},
        "expectations": {
            "label_apply_status": case.expected_label_apply_status,
            "supervised_ready": case.expected_supervised_ready,
            "bids": case.expected_bids,
            "label_contract": case.label_contract,
        },
    }
    fixture_evidence = _fixture_manifest_evidence(case, repo_root)
    result["fixture_evidence"] = fixture_evidence
    if not source_path.exists() or not (source_path.is_file() or source_path.is_dir()):
        result["status"] = "missing"
        result["reason"] = f"Required source is missing: {source_path}"
        return result
    if fixture_evidence["status"] == "invalid":
        result["reason"] = str(fixture_evidence["message"])
        return result
    fixture_facts = capture_public_fixture_facts(case.case_id, repo_root)
    result["fixture_facts"] = fixture_facts
    if fixture_facts["status"] == "failed":
        result["failed_stage"] = "fixture_facts"
        result["reason"] = "; ".join(fixture_facts["mismatches"])
        return result

    service: ApplicationService | None = None
    with _suppress_application_info_logs(), mne.use_log_level("ERROR"):
        try:
            service = get_application_service(Study())
            scan = service.execute(
                ScanSourceCommand(
                    source_path=str(source_path),
                    source_hint=case.source_hint,
                )
            )
            stages["scan"] = _stage_evidence(scan)
            if not scan.ok:
                return _failed_workflow_result(result, "scan", scan.message)

            choices = _workflow_choices(case, repo_root)
            preview = service.execute(PreviewInterpretationCommand(choices=choices))
            stages["preview"] = _stage_evidence(preview)
            if not preview.ok:
                return _failed_workflow_result(result, "preview", preview.message)

            validation = service.execute(ValidateInterpretationCommand())
            stages["validate"] = _stage_evidence(validation)
            if not validation.ok:
                return _failed_workflow_result(
                    result,
                    "validate",
                    validation.message,
                )
            validation_payload = validation.diagnostics.get(
                "validation_decision",
                {},
            )
            if validation_payload.get("decision") == "blocked":
                return _failed_workflow_result(
                    result,
                    "validate",
                    "Validation blocked apply: "
                    + "; ".join(validation_payload.get("blocked_reasons", [])),
                )

            apply_result = service.execute(
                ApplyInterpretationCommand(confirmed=True),
            )
            stages["apply"] = _stage_evidence(apply_result)
            if not apply_result.ok:
                return _failed_workflow_result(
                    result,
                    "apply",
                    apply_result.message,
                )

            scan_payload = scan.diagnostics.get("scan_result", {})
            preview_payload = preview.diagnostics.get("preview", {})
            candidate_payload = preview.diagnostics.get("candidate", {})
            label_apply = apply_result.diagnostics.get("label_apply", {})
            applied_payload = apply_result.diagnostics.get(
                "applied_interpretation",
                {},
            )
            handoff = apply_result.state.interpretation.epoch_handoff
            internal_event_count = int(
                candidate_payload.get("internal_event_preview", {}).get(
                    "event_count",
                    0,
                )
                or 0
            )
            source_event_count = _source_event_count(
                case,
                candidate_payload,
                internal_event_count,
            )
            choice_evidence = _reviewed_choice_evidence(
                case.case_id,
                applied_payload,
            )
            observations = {
                "eeg_file_count": len(scan_payload.get("eeg_files", [])),
                "label_carrier_count": len(
                    scan_payload.get("label_carriers", []),
                ),
                "preview_summary": str(preview_payload.get("summary", "")),
                "validation_decision": str(
                    validation_payload.get("decision", ""),
                ),
                "required_confirmation_count": len(
                    validation_payload.get("required_confirmations", []),
                ),
                "blocked_reasons": list(
                    validation_payload.get("blocked_reasons", []),
                ),
                "scan_warnings": list(scan_payload.get("warnings", [])),
                "interpretation_warnings": list(
                    candidate_payload.get("warnings", []),
                ),
                "internal_event_count": internal_event_count,
                "source_event_count": source_event_count,
                "selected_internal_events": list(
                    candidate_payload.get("internal_event_selection", {}).get(
                        "label_event_codes",
                        [],
                    )
                ),
                "run_event_mapping_count": len(
                    handoff.get("run_event_mappings", {}),
                ),
                "label_apply_status": str(label_apply.get("status", "")),
                "raw_file_count": apply_result.state.raw.count,
                "applied_interpretation": (
                    apply_result.state.interpretation.has_applied_interpretation
                ),
                "bids": bool(
                    apply_result.state.interpretation.bids.get("is_bids", False),
                ),
                "epoch_handoff_ready": bool(handoff.get("ready", False)),
                "supervised_ready": bool(
                    handoff.get("supervised_ready", False),
                ),
                "label_source": str(handoff.get("label_source", "")),
                "default_epoch_events": list(
                    handoff.get("default_epoch_events", []),
                ),
                "reviewed_choice_signature": choice_evidence["observed"],
                "reviewed_choice_expected": choice_evidence["expected"],
                "reviewed_choice_preserved": choice_evidence["preserved"],
                "fixture_facts_verified": fixture_facts["status"]
                in {
                    "not_applicable",
                    "passed",
                },
            }
            observations["reviewed_evidence_tier"] = _reviewed_evidence_tier(
                case.case_id,
                observations,
            )
            result["reviewed_evidence_tier"] = observations["reviewed_evidence_tier"]
            result["reviewed_choice_preserved"] = observations[
                "reviewed_choice_preserved"
            ]
            result["observations"] = observations
            mismatches = _workflow_expectation_mismatches(case, observations)
            if mismatches:
                result["failed_stage"] = "evidence_assertion"
                result["reason"] = "; ".join(mismatches)
                return result
            result.update(
                {
                    "status": "passed",
                    "failed_stage": "",
                    "reason": "Real ApplicationService lifecycle passed.",
                }
            )
        except Exception as exc:
            failed_stage = next(
                (stage for stage in WORKFLOW_STAGES if not bool(stages[stage]["ok"])),
                "evidence_assertion",
            )
            return _failed_workflow_result(
                result,
                failed_stage,
                f"{type(exc).__name__}: {exc}",
            )
        else:
            return result
        finally:
            service = None
            gc.collect()


def build_real_workflow_snapshot(
    repo_root: Path = ROOT,
    cases: tuple[RealWorkflowCase, ...] | None = None,
) -> dict[str, Any]:
    """Build auditable real-file lifecycle evidence for strict validation."""
    selected_cases = REAL_WORKFLOW_CASES if cases is None else cases
    results = [run_real_workflow_case(case, repo_root) for case in selected_cases]
    if cases is None:
        with tempfile.TemporaryDirectory(
            prefix="xbrainlab-di-label-contract-",
        ) as temp_dir:
            generated_root = Path(temp_dir)
            _write_generated_contract_fixtures(generated_root)
            results.extend(
                run_real_workflow_case(case, generated_root)
                for case in GENERATED_CONTRACT_CASES
            )
    summary = summarize_real_workflow_results(results)
    return {
        "evidence_level": "layered_application_workflow_evidence",
        "command_path": [
            "ApplicationService.execute(ScanSourceCommand)",
            "ApplicationService.execute(PreviewInterpretationCommand)",
            "ApplicationService.execute(ValidateInterpretationCommand)",
            "ApplicationService.execute(ApplyInterpretationCommand)",
        ],
        "summary": summary,
        "cases": results,
        "claim_boundary": {
            "supports": (
                "Seven hash-pinned public fixture workflows across five source "
                "families, eight checked-in or derived-format fixtures, and five "
                "generated parser/placement contracts completed the scan, preview, "
                "validate, and apply command lifecycle in separate evidence layers. "
                "Public fixtures also matched pinned sampling, channel/type/unit, "
                "sample/event, and import-warning facts. The fixed 11-case "
                "reviewed-choice set preserved its explicit choices and required "
                "evidence tiers."
            ),
            "does_not_support": (
                "A passing lifecycle does not prove arbitrary files, scientific "
                "class semantics, full BIDS compliance, or source diversity for "
                "A01T-derived format conversions. Generated CSV, TSV, and TXT "
                "fixtures prove only the declared parser and placement contracts; "
                "they do not add public dataset-source diversity or certify arbitrary "
                "carrier schemas. SCCN rt/square and CNT marker evidence is IO/epoch "
                "only, not protocol-grounded supervised-class or training evidence."
            ),
        },
    }


def summarize_real_workflow_results(
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Summarize against fixed strict denominators, never observed-list length."""
    case_id_counts = Counter(
        str(result.get("case_id")) for result in results if result.get("case_id")
    )
    duplicate_case_ids = sorted(
        case_id for case_id, count in case_id_counts.items() if count > 1
    )
    results_by_id = {
        str(result.get("case_id")): result
        for result in results
        if result.get("case_id")
    }
    evidence_scope_mismatch_case_ids = sorted(
        case_id
        for case_id, expected_scope in REQUIRED_CASE_EVIDENCE_SCOPES.items()
        if case_id in results_by_id
        and results_by_id[case_id].get("evidence_scope") != expected_scope
    )
    missing_required_case_ids = sorted(
        REQUIRED_REAL_WORKFLOW_CASE_IDS.difference(results_by_id)
    )
    passed_required_case_ids = sorted(
        case_id
        for case_id in REQUIRED_REAL_WORKFLOW_CASE_IDS
        if results_by_id.get(case_id, {}).get("status") == "passed"
        and case_id not in evidence_scope_mismatch_case_ids
    )
    public_results = [
        results_by_id[case_id]
        for case_id in sorted(REQUIRED_PUBLIC_SOURCE_WORKFLOW_CASE_IDS)
        if case_id in results_by_id and case_id not in evidence_scope_mismatch_case_ids
    ]
    public_families = sorted(
        {
            str(result.get("source_family"))
            for result in public_results
            if result.get("status") == "passed"
        }
    )
    missing_public_families = sorted(
        REQUIRED_PUBLIC_SOURCE_FAMILIES.difference(public_families)
    )
    format_results: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        format_name = str(result.get("format") or "")
        if format_name:
            format_results.setdefault(format_name, []).append(result)
    passed_formats = sorted(
        format_name
        for format_name, grouped_results in format_results.items()
        if all(result.get("status") == "passed" for result in grouped_results)
    )
    passed_required_formats = sorted(REQUIRED_TIER_FORMATS.intersection(passed_formats))
    missing_required_formats = sorted(
        REQUIRED_TIER_FORMATS.difference(passed_required_formats)
    )
    observed_passed_external_label_contracts = {
        str(result.get("label_contract"))
        for result in results
        if result.get("status") == "passed" and result.get("label_contract")
    }
    passed_external_label_contracts = sorted(
        REQUIRED_EXTERNAL_LABEL_CONTRACTS.intersection(
            observed_passed_external_label_contracts
        )
    )
    unexpected_passed_external_label_contracts = sorted(
        {
            contract
            for contract in observed_passed_external_label_contracts
            if contract not in REQUIRED_EXTERNAL_LABEL_CONTRACTS
        }
    )
    missing_external_label_contracts = sorted(
        REQUIRED_EXTERNAL_LABEL_CONTRACTS.difference(passed_external_label_contracts)
    )
    passed_internal_event_profiles = sorted(
        {
            str(result.get("protocol_choice_profile"))
            for result in results
            if result.get("status") == "passed"
            and result.get("protocol_choice_profile")
            in REQUIRED_INTERNAL_EVENT_PROFILES
        }
    )
    missing_internal_event_profiles = sorted(
        REQUIRED_INTERNAL_EVENT_PROFILES.difference(passed_internal_event_profiles)
    )
    missing_reviewed_case_ids = sorted(
        REQUIRED_REVIEWED_LABEL_CASE_IDS.difference(results_by_id)
    )
    downgraded_reviewed_case_ids = sorted(
        case_id
        for case_id, requirement in REQUIRED_REVIEWED_LABEL_CASE_REQUIREMENTS.items()
        if case_id in results_by_id
        and results_by_id[case_id].get("reviewed_evidence_tier")
        != requirement.evidence_tier
    )
    choice_failure_case_ids = sorted(
        case_id
        for case_id in REQUIRED_REVIEWED_LABEL_CASE_IDS
        if case_id in results_by_id
        and not bool(results_by_id[case_id].get("reviewed_choice_preserved"))
    )
    passed_reviewed_case_ids = sorted(
        case_id
        for case_id, requirement in REQUIRED_REVIEWED_LABEL_CASE_REQUIREMENTS.items()
        if results_by_id.get(case_id, {}).get("status") == "passed"
        and results_by_id[case_id].get("reviewed_evidence_tier")
        == requirement.evidence_tier
        and bool(results_by_id[case_id].get("reviewed_choice_preserved"))
    )
    missing_public_fact_case_ids = sorted(
        REQUIRED_PUBLIC_FIXTURE_FACT_CASE_IDS.difference(results_by_id)
    )
    failed_public_fact_case_ids = sorted(
        case_id
        for case_id in REQUIRED_PUBLIC_FIXTURE_FACT_CASE_IDS
        if case_id in results_by_id
        and results_by_id[case_id].get("fixture_facts", {}).get("status") != "passed"
    )
    passed_public_fact_case_ids = sorted(
        case_id
        for case_id in REQUIRED_PUBLIC_FIXTURE_FACT_CASE_IDS
        if results_by_id.get(case_id, {}).get("fixture_facts", {}).get("status")
        == "passed"
    )
    evidence_layers = {
        "checked_in_and_derived_formats": _summarize_evidence_layer(
            results_by_id,
            REQUIRED_CHECKED_IN_AND_DERIVED_CASE_IDS,
            counts_toward_public_source_diversity=False,
        ),
        "generated_contracts": _summarize_evidence_layer(
            results_by_id,
            REQUIRED_GENERATED_CONTRACT_CASE_IDS,
            counts_toward_public_source_diversity=False,
        ),
        "public_source_workflows": _summarize_evidence_layer(
            results_by_id,
            REQUIRED_PUBLIC_SOURCE_WORKFLOW_CASE_IDS,
            counts_toward_public_source_diversity=True,
        ),
    }

    strict_failures = [
        f"{case_id}: {result.get('reason', result.get('status', 'missing'))}"
        for case_id, result in sorted(results_by_id.items())
        if case_id in REQUIRED_REAL_WORKFLOW_CASE_IDS
        and result.get("status") != "passed"
    ]
    _append_missing_failure(
        strict_failures,
        "Duplicate workflow evidence is not allowed",
        duplicate_case_ids,
    )
    _append_missing_failure(
        strict_failures,
        "Evidence scope does not match the fixed case contract",
        evidence_scope_mismatch_case_ids,
    )
    _append_missing_failure(
        strict_failures,
        "Required real-workflow cases are missing",
        missing_required_case_ids,
    )
    _append_missing_failure(
        strict_failures,
        "Public source diversity is incomplete",
        missing_public_families,
    )
    _append_missing_failure(
        strict_failures,
        "Tier format lifecycle coverage is incomplete",
        missing_required_formats,
    )
    _append_missing_failure(
        strict_failures,
        "External label placement coverage is incomplete",
        missing_external_label_contracts,
    )
    _append_missing_failure(
        strict_failures,
        "Reviewed internal-event coverage is incomplete",
        missing_internal_event_profiles,
    )
    _append_missing_failure(
        strict_failures,
        "Required reviewed-label cases are missing",
        missing_reviewed_case_ids,
    )
    _append_missing_failure(
        strict_failures,
        "Required reviewed-label evidence was downgraded",
        downgraded_reviewed_case_ids,
    )
    _append_missing_failure(
        strict_failures,
        "Reviewed choices were not preserved",
        choice_failure_case_ids,
    )
    _append_missing_failure(
        strict_failures,
        "Required public fixture fact cases are missing",
        missing_public_fact_case_ids,
    )
    _append_missing_failure(
        strict_failures,
        "Pinned public fixture facts failed",
        failed_public_fact_case_ids,
    )

    missing_status_count = sum(
        result.get("status") == "missing"
        for case_id, result in results_by_id.items()
        if case_id in REQUIRED_REAL_WORKFLOW_CASE_IDS
    )
    failed_status_count = sum(
        result.get("status") == "failed"
        for case_id, result in results_by_id.items()
        if case_id in REQUIRED_REAL_WORKFLOW_CASE_IDS
    )
    return {
        "workflow_stages": list(WORKFLOW_STAGES),
        "required_case_count": len(REQUIRED_REAL_WORKFLOW_CASE_IDS),
        "required_case_ids": sorted(REQUIRED_REAL_WORKFLOW_CASE_IDS),
        "passed_required_case_count": len(passed_required_case_ids),
        "passed_required_case_ids": passed_required_case_ids,
        "missing_required_case_ids": missing_required_case_ids,
        "duplicate_case_ids": duplicate_case_ids,
        "evidence_scope_mismatch_case_ids": evidence_scope_mismatch_case_ids,
        "missing_case_count": missing_status_count + len(missing_required_case_ids),
        "failed_case_count": failed_status_count,
        "public_case_count": len(REQUIRED_PUBLIC_SOURCE_WORKFLOW_CASE_IDS),
        "passed_public_case_count": sum(
            result.get("status") == "passed" for result in public_results
        ),
        "public_source_family_count": len(public_families),
        "public_source_families": public_families,
        "missing_public_source_families": missing_public_families,
        "observed_format_count": len(format_results),
        "passed_formats": passed_formats,
        "required_format_count": len(REQUIRED_TIER_FORMATS),
        "passed_required_format_count": len(passed_required_formats),
        "passed_required_formats": passed_required_formats,
        "missing_required_formats": missing_required_formats,
        "required_external_label_contract_count": len(
            REQUIRED_EXTERNAL_LABEL_CONTRACTS
        ),
        "passed_external_label_contract_count": len(passed_external_label_contracts),
        "passed_external_label_contracts": passed_external_label_contracts,
        "unexpected_passed_external_label_contracts": (
            unexpected_passed_external_label_contracts
        ),
        "missing_external_label_contracts": missing_external_label_contracts,
        "required_internal_event_profile_count": len(REQUIRED_INTERNAL_EVENT_PROFILES),
        "passed_internal_event_profile_count": len(passed_internal_event_profiles),
        "passed_internal_event_profiles": passed_internal_event_profiles,
        "missing_internal_event_profiles": missing_internal_event_profiles,
        "required_reviewed_label_case_count": len(REQUIRED_REVIEWED_LABEL_CASE_IDS),
        "required_reviewed_label_case_ids": sorted(REQUIRED_REVIEWED_LABEL_CASE_IDS),
        "passed_required_reviewed_label_case_count": len(passed_reviewed_case_ids),
        "passed_required_reviewed_label_case_ids": passed_reviewed_case_ids,
        "missing_required_reviewed_label_case_ids": missing_reviewed_case_ids,
        "downgraded_required_reviewed_label_case_ids": (downgraded_reviewed_case_ids),
        "choice_preservation_failure_case_ids": choice_failure_case_ids,
        "reviewed_label_case_count": len(REQUIRED_REVIEWED_LABEL_CASE_IDS),
        "passed_reviewed_label_case_count": len(passed_reviewed_case_ids),
        "required_public_fixture_fact_count": len(
            REQUIRED_PUBLIC_FIXTURE_FACT_CASE_IDS
        ),
        "passed_public_fixture_fact_count": len(passed_public_fact_case_ids),
        "passed_public_fixture_fact_case_ids": passed_public_fact_case_ids,
        "missing_public_fixture_fact_case_ids": missing_public_fact_case_ids,
        "failed_public_fixture_fact_case_ids": failed_public_fact_case_ids,
        "evidence_layers": evidence_layers,
        "strict_failures": strict_failures,
        "all_required_passed": not strict_failures,
    }


def _summarize_evidence_layer(
    results_by_id: dict[str, dict[str, Any]],
    required_case_ids: frozenset[str],
    *,
    counts_toward_public_source_diversity: bool,
) -> dict[str, Any]:
    missing_case_ids = sorted(required_case_ids.difference(results_by_id))
    failed_case_ids = sorted(
        case_id
        for case_id in required_case_ids
        if case_id in results_by_id
        and (
            results_by_id[case_id].get("status") != "passed"
            or results_by_id[case_id].get("evidence_scope")
            != REQUIRED_CASE_EVIDENCE_SCOPES[case_id]
        )
    )
    passed_case_ids = sorted(
        case_id
        for case_id in required_case_ids
        if results_by_id.get(case_id, {}).get("status") == "passed"
        and results_by_id[case_id].get("evidence_scope")
        == REQUIRED_CASE_EVIDENCE_SCOPES[case_id]
    )
    return {
        "required_case_count": len(required_case_ids),
        "passed_required_case_count": len(passed_case_ids),
        "missing_required_case_ids": missing_case_ids,
        "failed_required_case_ids": failed_case_ids,
        "evidence_scopes": sorted(
            {REQUIRED_CASE_EVIDENCE_SCOPES[case_id] for case_id in required_case_ids}
        ),
        "counts_toward_public_source_diversity": (
            counts_toward_public_source_diversity
        ),
    }


def _append_missing_failure(
    failures: list[str],
    label: str,
    values: list[str],
) -> None:
    if values:
        failures.append(f"{label}: {', '.join(values)}.")


def _write_generated_contract_fixtures(root: Path) -> None:
    """Create valid, tiny EEG and label files for external-carrier contracts."""
    for case in GENERATED_CONTRACT_CASES:
        case_dir = root / case.source_entry
        case_dir.mkdir(parents=True, exist_ok=True)
        eeg_path = case_dir / GENERATED_EEG_FILENAME
        label_path = case_dir / GENERATED_LABEL_FILENAMES[case.choice_profile]

        if case.choice_profile in {
            "generated_csv_event_order",
            "generated_txt_event_order",
        }:
            data = np.zeros((2, 500), dtype=np.float64)
            data[1, [50, 150, 250, 350]] = 768
            info = mne.create_info(
                ["Cz", "STI 014"],
                sfreq=100.0,
                ch_types=cast(Any, ["eeg", "stim"]),
            )
        elif case.choice_profile == "generated_csv_event_code":
            data = np.zeros((2, 500), dtype=np.float64)
            data[1, [50, 250]] = 11
            data[1, 150] = 12
            info = mne.create_info(
                ["Cz", "STI 014"],
                sfreq=100.0,
                ch_types=cast(Any, ["eeg", "stim"]),
            )
        else:
            data = np.zeros((1, 500), dtype=np.float64)
            info = mne.create_info(["Cz"], sfreq=100.0, ch_types="eeg")
        raw = mne.io.RawArray(data, info, verbose="ERROR")
        raw.save(eeg_path, overwrite=True, verbose="ERROR")

        contents = {
            "generated_csv_event_order": "label\n1\n2\n1\n2\n",
            "generated_csv_sample_time": "sample,label\n50,left\n150,right\n",
            "generated_tsv_interval": (
                "onset\tduration\tlabel\n0.5\t0.2\tleft\n1.5\t0.3\tright\n"
            ),
            "generated_csv_event_code": ("event_code,label\n11,left\n12,right\n"),
            "generated_txt_event_order": "1\n2\n1\n2\n",
        }
        label_path.write_text(contents[case.choice_profile], encoding="utf-8")


def build_data_interpretation_validation_snapshot(
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    """Combine synthetic capability boundaries with real workflow evidence."""
    snapshot = build_format_capability_snapshot()
    real_workflows = build_real_workflow_snapshot(repo_root)
    snapshot["real_workflows"] = real_workflows
    snapshot["strict_validation"] = {
        "ok": bool(
            snapshot["summary"]["all_expected_capabilities_observed"]
            and snapshot["summary"]["all_expected_capabilities_match"]
            and real_workflows["summary"]["all_required_passed"]
        ),
        "synthetic_capabilities_match": bool(
            snapshot["summary"]["all_expected_capabilities_match"],
        ),
        "real_workflows_pass": bool(
            real_workflows["summary"]["all_required_passed"],
        ),
    }
    return snapshot


def _stage_evidence(command_result: Any) -> dict[str, Any]:
    return {
        "ok": bool(command_result.ok),
        "message": str(command_result.message),
    }


def _failed_workflow_result(
    result: dict[str, Any],
    stage: str,
    reason: str,
) -> dict[str, Any]:
    result["status"] = "failed"
    result["failed_stage"] = stage
    result["reason"] = reason
    return result


def _fixture_manifest_evidence(
    case: RealWorkflowCase,
    repo_root: Path,
) -> dict[str, Any]:
    if not case.fixture_group:
        if case.evidence_scope == "generated_contract":
            return {
                "status": "generated",
                "manifest_verified": False,
                "message": (
                    "Generated valid EEG and label files exercise a parser/placement "
                    "contract; they are not public-source evidence."
                ),
            }
        return {
            "status": "not_applicable",
            "manifest_verified": False,
            "message": "Checked-in or test-local fixture; no public manifest required.",
        }
    from scripts.dev.fetch_public_eeg_fixtures import (
        FIXTURE_GROUPS,
        fixture_file_is_valid,
    )

    fixture_group = next(
        (group for group in FIXTURE_GROUPS if group["name"] == case.fixture_group),
        None,
    )
    if fixture_group is None:
        return {
            "status": "invalid",
            "manifest_verified": False,
            "message": f"Fixture manifest group is undefined: {case.fixture_group}",
        }
    public_dir = repo_root / "tests" / "fixtures" / "data" / "public"
    invalid_files = [
        fixture_file["filename"]
        for fixture_file in fixture_group["files"]
        if not fixture_file_is_valid(
            public_dir / fixture_file["filename"],
            fixture_file["sha256"],
            fixture_file["size_bytes"],
        )
    ]
    if invalid_files:
        return {
            "status": "invalid",
            "manifest_verified": False,
            "message": "Missing or hash/size-invalid public fixture files: "
            + ", ".join(invalid_files),
        }
    return {
        "status": "verified",
        "manifest_verified": True,
        "message": (
            f"Pinned public fixture group {case.fixture_group} passed size and hash "
            "verification."
        ),
    }


def _workflow_choices(
    case: RealWorkflowCase,
    repo_root: Path,
) -> dict[str, Any]:
    source_path = (repo_root / case.source_entry).resolve()
    if case.choice_profile == "a01t_external_labels":
        label_path = (repo_root / "tests/fixtures/data/label/A01T.mat").resolve()
        return {
            "label_carrier_choices": {
                str(label_path): {
                    "label_field": "classlabel",
                    "placement_method": "eeg_event",
                    "target_event_codes": ["768"],
                }
            }
        }
    if case.choice_profile == "physionet_r04_internal":
        return {
            "label_carrier": "embedded_events",
            "internal_event_selection": {
                "label_event_codes": ["T1", "T2"],
                "not_label_event_codes": ["T0"],
                "class_map": {"T1": "left fist", "T2": "right fist"},
            },
            "run_event_mappings": {
                source_path.name: {"T1": "left fist", "T2": "right fist"}
            },
        }
    internal_profiles = {
        "bbci_internal": {
            "label_event_codes": ["769", "770"],
            "not_label_event_codes": ["768", "781", "785", "783"],
        },
        "cnt_internal": {
            "label_event_codes": ["7"],
            "not_label_event_codes": ["0", "109"],
        },
    }
    if case.choice_profile == "sccn_internal":
        return {
            "label_carrier": "embedded_events",
            "internal_event_selection": {
                "label_event_codes": [],
                "not_label_event_codes": ["rt", "square"],
                "class_map": {},
            },
        }
    if case.choice_profile in internal_profiles:
        selection: dict[str, Any] = dict(internal_profiles[case.choice_profile])
        selection["class_map"] = {code: code for code in selection["label_event_codes"]}
        return {
            "label_carrier": "embedded_events",
            "internal_event_selection": selection,
        }
    if case.choice_profile == "bids_events":
        eeg_path = source_path / (
            "sub-01/ses-eeg/eeg/sub-01_ses-eeg_task-rest_eeg.vhdr"
        )
        events_path = source_path / (
            "sub-01/ses-eeg/eeg/sub-01_ses-eeg_task-rest_events.tsv"
        )
        return {
            "selected_eeg_files": [str(eeg_path)],
            "label_carrier_choices": {
                str(events_path): {
                    "label_field": "trial_type",
                    "anchor": "onset",
                    "duration_field": "duration",
                    "time_model": "seconds",
                    "placement_method": "interval",
                    "value_decisions": {
                        "start_experiment": {
                            "role": "system",
                            "keep_event": False,
                            "use_as_class": False,
                        },
                        "show_stimulus": {
                            "role": "stimulus",
                            "keep_event": True,
                            "use_as_class": True,
                            "class_name": "show stimulus",
                        },
                    },
                }
            },
        }
    if case.choice_profile in GENERATED_LABEL_FILENAMES:
        eeg_path = source_path / GENERATED_EEG_FILENAME
        label_path = source_path / GENERATED_LABEL_FILENAMES[case.choice_profile]
        choice: dict[str, Any]
        class_map: dict[str, str]
        if case.choice_profile == "generated_csv_event_order":
            choice = {
                "label_field": "label",
                "target_event_codes": ["768"],
                "placement_method": "eeg_event",
                "time_model": "trial_order",
                "granularity": "trial",
            }
            class_map = {"1": "Left", "2": "Right"}
        elif case.choice_profile == "generated_csv_sample_time":
            choice = {
                "label_field": "label",
                "anchor": "sample",
                "placement_method": "time_field",
                "time_model": "sample_index",
                "sample_index_base": "zero_based",
                "sample_index_origin": "recording_relative",
                "granularity": "trial",
            }
            class_map = {"left": "Left", "right": "Right"}
        elif case.choice_profile == "generated_tsv_interval":
            choice = {
                "label_field": "label",
                "anchor": "onset",
                "duration_field": "duration",
                "placement_method": "interval",
                "time_model": "seconds",
                "granularity": "trial",
            }
            class_map = {"left": "Left", "right": "Right"}
        elif case.choice_profile == "generated_csv_event_code":
            choice = {
                "label_field": "label",
                "anchor": "event_code",
                "placement_method": "event_code",
                "time_model": "seconds",
                "granularity": "trial",
            }
            class_map = {"left": "Left", "right": "Right"}
        else:
            choice = {
                "label_field": "line label sequence",
                "target_event_codes": ["768"],
                "placement_method": "eeg_event",
                "time_model": "trial_order",
                "granularity": "trial",
            }
            class_map = {"1": "Left", "2": "Right"}
        choice["value_decisions"] = _class_value_decisions(class_map)
        choice["target_file"] = eeg_path.name
        return {
            "label_carrier_choices": {str(label_path): choice},
            "class_map": class_map,
        }
    return {}


def _class_value_decisions(class_map: dict[str, str]) -> dict[str, dict[str, Any]]:
    """Return the explicit Match Labels choices used by contract fixtures."""
    return {
        raw_value: {
            "role": "stimulus",
            "keep_event": True,
            "use_as_class": True,
            "class_name": class_name,
        }
        for raw_value, class_name in sorted(class_map.items())
    }


def _source_event_count(
    case: RealWorkflowCase,
    candidate_payload: dict[str, Any],
    internal_event_count: int,
) -> int:
    if not case.expected_bids:
        return internal_event_count
    runs = candidate_payload.get("bids", {}).get("event_validation", {}).get("runs", [])
    return sum(
        int(run.get("event_count", 0) or 0) for run in runs if isinstance(run, Mapping)
    )


def _reviewed_choice_evidence(
    case_id: str,
    applied_payload: dict[str, Any],
) -> dict[str, Any]:
    if case_id in EXPECTED_INTERNAL_CHOICE_SIGNATURES:
        expected = EXPECTED_INTERNAL_CHOICE_SIGNATURES[case_id]
        selection = applied_payload.get("internal_event_selection", {})
        raw_run_mappings = applied_payload.get("run_event_mappings", {})
        run_mappings = {
            Path(str(path)).name: {
                str(code): str(label) for code, label in sorted(mapping.items())
            }
            for path, mapping in sorted(raw_run_mappings.items())
            if isinstance(mapping, Mapping)
        }
        observed = {
            "label_event_codes": sorted(
                str(item) for item in selection.get("label_event_codes", [])
            ),
            "not_label_event_codes": sorted(
                str(item) for item in selection.get("not_label_event_codes", [])
            ),
            "class_map": {
                str(code): str(label)
                for code, label in sorted(
                    applied_payload.get("class_map", {}).items(),
                )
            },
            "run_event_mappings": run_mappings,
        }
        return {
            "expected": expected,
            "observed": observed,
            "preserved": observed == expected,
        }
    if case_id in EXPECTED_EXTERNAL_CHOICE_SIGNATURES:
        expected = EXPECTED_EXTERNAL_CHOICE_SIGNATURES[case_id]
        plans = applied_payload.get("label_carrier_plan", [])
        plan = plans[0] if isinstance(plans, list) and plans else {}
        observed = {
            "selected_label_field": str(plan.get("selected_label_field", "")),
            "selected_anchor": str(plan.get("selected_anchor", "")),
            "selected_target_event_codes": sorted(
                str(item) for item in plan.get("selected_target_event_codes", [])
            ),
            "selected_duration_field": str(
                plan.get("selected_duration_field", ""),
            ),
            "placement_method": str(plan.get("placement_method", "")),
            "time_model": str(plan.get("time_model", "")),
            "sample_index_base": str(plan.get("sample_index_base", "")),
            "sample_index_origin": str(plan.get("sample_index_origin", "")),
            "class_map": {
                str(code): str(label)
                for code, label in sorted(
                    applied_payload.get("class_map", {}).items(),
                )
            },
        }
        if "value_decisions" in expected:
            raw_decisions = plan.get("value_decisions", {})
            observed["value_decisions"] = {
                str(value): {
                    "role": decision.get("role"),
                    "keep_event": decision.get("keep_event"),
                    "use_as_class": decision.get("use_as_class"),
                    "class_name": decision.get("class_name"),
                }
                for value, decision in sorted(raw_decisions.items())
                if isinstance(decision, Mapping)
            }
        return {
            "expected": expected,
            "observed": observed,
            "preserved": observed == expected,
        }
    return {"expected": {}, "observed": {}, "preserved": True}


def _reviewed_evidence_tier(
    case_id: str,
    observations: dict[str, Any],
) -> str:
    if case_id not in REQUIRED_REVIEWED_LABEL_CASE_IDS:
        return "not_required"
    if bool(observations["supervised_ready"]):
        if case_id in REQUIRED_GENERATED_CONTRACT_CASE_IDS:
            return "generated_supervised_contract"
        return "supervised"
    if observations["label_apply_status"] == "applied":
        return "label_apply_only"
    if bool(observations["reviewed_choice_preserved"]):
        return "io_epoch_only"
    return "none"


def _workflow_expectation_mismatches(
    case: RealWorkflowCase,
    observations: dict[str, Any],
) -> list[str]:
    mismatches: list[str] = []
    if observations["eeg_file_count"] != 1:
        mismatches.append(
            f"expected one selected EEG file, got {observations['eeg_file_count']}"
        )
    if observations["raw_file_count"] != 1:
        mismatches.append(
            f"expected one applied raw file, got {observations['raw_file_count']}"
        )
    if not observations["applied_interpretation"]:
        mismatches.append("applied interpretation state was not published")
    if observations["label_apply_status"] != case.expected_label_apply_status:
        mismatches.append(
            "label apply status mismatch: expected "
            f"{case.expected_label_apply_status}, got "
            f"{observations['label_apply_status']}"
        )
    if observations["supervised_ready"] is not case.expected_supervised_ready:
        mismatches.append(
            "supervised readiness mismatch: expected "
            f"{case.expected_supervised_ready}, got "
            f"{observations['supervised_ready']}"
        )
    if observations["bids"] is not case.expected_bids:
        mismatches.append(
            f"BIDS state mismatch: expected {case.expected_bids}, got "
            f"{observations['bids']}"
        )
    if case.label_contract and observations["label_carrier_count"] != 1:
        mismatches.append(
            "expected one discovered label carrier, got "
            f"{observations['label_carrier_count']}"
        )
    if (
        case.choice_profile == "physionet_r04_internal"
        and observations["run_event_mapping_count"] < 1
    ):
        mismatches.append("PhysioNet run-dependent event mapping was not preserved")
    requirement = REQUIRED_REVIEWED_LABEL_CASE_REQUIREMENTS.get(case.case_id)
    if requirement is not None:
        if case.choice_profile != requirement.choice_profile:
            mismatches.append(
                "reviewed choice profile mismatch: expected "
                f"{requirement.choice_profile}, got {case.choice_profile}"
            )
        if observations["reviewed_evidence_tier"] != requirement.evidence_tier:
            mismatches.append(
                "reviewed evidence tier mismatch: expected "
                f"{requirement.evidence_tier}, got "
                f"{observations['reviewed_evidence_tier']}"
            )
        if not observations["reviewed_choice_preserved"]:
            mismatches.append("reviewed choices were not preserved into applied state")
    fact_contract = PUBLIC_FIXTURE_FACT_CONTRACTS.get(case.case_id)
    if fact_contract is not None:
        expected_event_count = int(fact_contract["interpretation_event_count"])
        if observations["source_event_count"] != expected_event_count:
            mismatches.append(
                "interpretation event count mismatch: expected "
                f"{expected_event_count}, got {observations['source_event_count']}"
            )
        if not observations["fixture_facts_verified"]:
            mismatches.append("pinned public fixture facts were not verified")
    return mismatches


def write_artifacts(
    snapshot: dict[str, Any],
    output_dir: Path = ARTIFACT_DIR,
) -> tuple[Path, Path]:
    """Write JSON and Markdown artifacts for the current matrix."""
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / ARTIFACT_JSON
    markdown_path = output_dir / ARTIFACT_MARKDOWN
    json_path.write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    markdown_path.write_text(render_markdown(snapshot) + "\n", encoding="utf-8")
    return json_path, markdown_path


def render_markdown(snapshot: dict[str, Any]) -> str:
    """Render the format matrix in Markdown."""
    lines = [
        "# Data Interpretation Format Capability Matrix",
        "",
        "Generated from the live ApplicationService command path:",
        "",
        "- `ScanSourceCommand`",
        "- `PreviewInterpretationCommand`",
        "- `ValidateInterpretationCommand`",
        "",
        "| Coverage | Source fixture | Detected format | Role | Status | Validation | Boundary |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in snapshot["rows"]:
        lines.append(
            "| {coverage_label} | {source_fixture} | {format} | {role} | "
            "{status} | {validation_decision} | {message} |".format(
                coverage_label=_escape_markdown(row["coverage_label"]),
                source_fixture=_escape_markdown(row["source_fixture"]),
                format=_escape_markdown(row["format"]),
                role=_escape_markdown(row["role"]),
                status=_escape_markdown(row["status"]),
                validation_decision=_escape_markdown(row["validation_decision"]),
                message=_escape_markdown(row["message"]),
            )
        )

    lines.extend(
        [
            "",
            "## Summary",
            "",
            f"- Cases: `{snapshot['summary']['case_count']}`",
            f"- Matrix rows: `{snapshot['summary']['row_count']}`",
            "- Statuses: "
            + ", ".join(f"`{item}`" for item in snapshot["summary"]["statuses"]),
            "- Validation decisions: "
            + ", ".join(
                f"`{item}`" for item in snapshot["summary"]["validation_decisions"]
            ),
            "- All expected capabilities observed: "
            f"`{snapshot['summary']['all_expected_capabilities_observed']}`",
            "- All expected capabilities match: "
            f"`{snapshot['summary']['all_expected_capabilities_match']}`",
            "",
            "## Claim Boundary",
            "",
            f"- Supports: {snapshot['claim_boundary']['supports']}",
            f"- Does not support: {snapshot['claim_boundary']['does_not_support']}",
        ]
    )
    real_workflows = snapshot.get("real_workflows")
    if isinstance(real_workflows, dict):
        real_summary = real_workflows["summary"]
        lines.extend(
            [
                "",
                "## Real Data Interpretation Workflows",
                "",
                "Every row passes only after "
                "`scan -> preview -> validate -> apply`. Public fixture workflows, "
                "checked-in/derived formats, and generated parser contracts are "
                "reported in separate evidence layers.",
            ]
        )
        layer_sections = (
            (
                "Public dataset-source evidence",
                {"public_source"},
                "Hash-pinned public fixtures. These rows alone count toward public "
                "dataset-source diversity.",
            ),
            (
                "Checked-in and derived-format evidence",
                {"checked_in_source", "derived_format"},
                "Checked-in source data and compact format derivatives. Derived "
                "formats add format coverage, not independent source diversity.",
            ),
            (
                "Generated contract evidence",
                {"generated_contract"},
                "Generated valid EEG/label fixtures exercise declared parser and "
                "placement contracts only. They are not public dataset, protocol, "
                "or training evidence.",
            ),
        )
        for heading, evidence_scopes, explanation in layer_sections:
            lines.extend(
                [
                    "",
                    f"### {heading}",
                    "",
                    explanation,
                    "",
                    "| Scope | Source family | Format | Evidence tier | Validation | Label apply | Epoch handoff | Status |",
                    "| --- | --- | --- | --- | --- | --- | --- | --- |",
                ]
            )
            for case in real_workflows["cases"]:
                if case["evidence_scope"] not in evidence_scopes:
                    continue
                observations = case["observations"]
                evidence_tier = observations.get(
                    "reviewed_evidence_tier",
                    "unreviewed_io",
                )
                if evidence_tier == "supervised":
                    handoff = "supervised ready"
                elif evidence_tier == "generated_supervised_contract":
                    handoff = "generated contract only"
                elif evidence_tier == "io_epoch_only":
                    handoff = (
                        "epoch ready"
                        if observations.get("epoch_handoff_ready")
                        else "epoch smoke separate"
                    )
                elif observations.get("epoch_handoff_ready"):
                    handoff = "epoch handoff"
                else:
                    handoff = "raw/import only"
                lines.append(
                    "| {scope} | {source} | {format_name} | {evidence_tier} | "
                    "{validation} | {label_apply} | {handoff} | {status} |".format(
                        scope=_escape_markdown(case["evidence_scope"]),
                        source=_escape_markdown(case["source_family"]),
                        format_name=_escape_markdown(case["format"]),
                        evidence_tier=_escape_markdown(evidence_tier),
                        validation=_escape_markdown(
                            observations.get("validation_decision", "not run"),
                        ),
                        label_apply=_escape_markdown(
                            observations.get("label_apply_status", "not run"),
                        ),
                        handoff=_escape_markdown(handoff),
                        status=_escape_markdown(case["status"]),
                    )
                )
        lines.extend(
            [
                "",
                "### Real workflow summary",
                "",
                "- Public fixture workflow layer: "
                f"`{real_summary['evidence_layers']['public_source_workflows']['passed_required_case_count']} / "
                f"{real_summary['evidence_layers']['public_source_workflows']['required_case_count']}`",
                "- Checked-in and derived-format layer: "
                f"`{real_summary['evidence_layers']['checked_in_and_derived_formats']['passed_required_case_count']} / "
                f"{real_summary['evidence_layers']['checked_in_and_derived_formats']['required_case_count']}`",
                "- Generated contract layer: "
                f"`{real_summary['evidence_layers']['generated_contracts']['passed_required_case_count']} / "
                f"{real_summary['evidence_layers']['generated_contracts']['required_case_count']}` "
                "(excluded from public source diversity)",
                "- Required cases: "
                f"`{real_summary['passed_required_case_count']} / "
                f"{real_summary['required_case_count']}` passed",
                "- Public source families completing the lifecycle: "
                f"`{real_summary['public_source_family_count']}` "
                + ", ".join(real_summary["public_source_families"]),
                "- Required formats completing the lifecycle: "
                f"`{real_summary['passed_required_format_count']} / "
                f"{real_summary['required_format_count']}`",
                "- Cross-layer external label placement contracts: "
                f"`{real_summary['passed_external_label_contract_count']} / "
                f"{real_summary['required_external_label_contract_count']}`",
                "- Reviewed public internal-event profiles: "
                f"`{real_summary['passed_internal_event_profile_count']} / "
                f"{real_summary['required_internal_event_profile_count']}`",
                "- Fixed cross-layer reviewed-label/event workflows: "
                f"`{real_summary['passed_required_reviewed_label_case_count']} / "
                f"{real_summary['required_reviewed_label_case_count']}`",
                "- Pinned public fixture fact contracts: "
                f"`{real_summary['passed_public_fixture_fact_count']} / "
                f"{real_summary['required_public_fixture_fact_count']}`",
                "- Strict real-workflow result: "
                f"`{real_summary['all_required_passed']}`",
            ]
        )
        public_fact_cases = [
            case
            for case in real_workflows["cases"]
            if case.get("fixture_facts", {}).get("status") != "not_applicable"
        ]
        if public_fact_cases:
            lines.extend(
                [
                    "",
                    "### Pinned public fixture facts",
                    "",
                    "| Case ID | Hz | Channels / types | Canonical / source units | Samples | Embedded events | Import warnings | Status |",
                    "| --- | --- | --- | --- | --- | --- | --- | --- |",
                ]
            )
            for case in public_fact_cases:
                facts = case["fixture_facts"]
                warning_count = sum(
                    int(item["count"]) for item in facts.get("import_warnings", [])
                )
                lines.append(
                    "| {case_id} | {sfreq} | {channels} / {types} | {units} / "
                    "{source_units} | {samples} | {events} | {warnings} | "
                    "{status} |".format(
                        case_id=_escape_markdown(case["case_id"]),
                        sfreq=_escape_markdown(
                            facts.get("sampling_frequency_hz", "not loaded")
                        ),
                        channels=_escape_markdown(
                            facts.get("channel_count", "not loaded")
                        ),
                        types=_escape_markdown(
                            json.dumps(
                                facts.get("channel_type_counts", {}),
                                sort_keys=True,
                            )
                        ),
                        units=_escape_markdown(
                            json.dumps(
                                facts.get("channel_unit_counts", {}),
                                sort_keys=True,
                            )
                        ),
                        source_units=_escape_markdown(
                            json.dumps(
                                facts.get("source_unit_counts", {}),
                                sort_keys=True,
                            )
                        ),
                        samples=_escape_markdown(
                            facts.get("sample_count", "not loaded")
                        ),
                        events=_escape_markdown(
                            facts.get("embedded_event_count", "not loaded")
                        ),
                        warnings=warning_count,
                        status=_escape_markdown(facts["status"]),
                    )
                )
        lines.extend(
            [
                "",
                "### Real workflow claim boundary",
                "",
                f"- Supports: {real_workflows['claim_boundary']['supports']}",
                f"- Does not support: {real_workflows['claim_boundary']['does_not_support']}",
            ]
        )
    return "\n".join(lines)


def _run_case(case_dir: Path, case: FormatCase) -> dict[str, Any]:
    source_path = case_dir / case.source_entry
    service = get_application_service(Study())

    scan = service.execute(
        ScanSourceCommand(
            source_path=str(source_path),
            source_hint=case.source_hint,
        )
    )
    preview = service.execute(PreviewInterpretationCommand())
    validation = service.execute(ValidateInterpretationCommand())

    scan_result = scan.diagnostics["scan_result"]
    preview_payload = preview.diagnostics["preview"]
    validation_payload = validation.diagnostics["validation_decision"]
    capabilities = {
        str(item.get("name")): item
        for item in scan_result.get("format_capabilities", [])
    }

    rows = [
        _row_for_expected_capability(
            case=case,
            expected=expected,
            actual=capabilities.get(expected.filename),
            preview_payload=preview_payload,
            validation_payload=validation_payload,
        )
        for expected in case.expected_capabilities
    ]
    return {
        "case_summary": {
            "case_id": case.case_id,
            "title": case.title,
            "source_hint": case.source_hint,
            "source_entry": case.source_entry,
            "source_files": [item.relative_path for item in case.files],
            "source_kind": scan_result["source_kind"],
            "eeg_files": _names(scan_result.get("eeg_files", [])),
            "label_carriers": _names(scan_result.get("label_carriers", [])),
            "warning_count": len(scan_result.get("warnings", [])),
            "blocked_reasons": list(scan_result.get("blocked_reasons", [])),
            "preview_summary": preview_payload["summary"],
            "validation_decision": validation_payload["decision"],
        },
        "rows": rows,
    }


def _row_for_expected_capability(
    *,
    case: FormatCase,
    expected: ExpectedCapability,
    actual: dict[str, Any] | None,
    preview_payload: dict[str, Any],
    validation_payload: dict[str, Any],
) -> dict[str, Any]:
    observed = actual is not None
    actual = actual or {}
    message = str(actual.get("message", ""))
    matches_expected = (
        observed
        and actual.get("format") == expected.format_name
        and actual.get("role") == expected.role
        and actual.get("status") == expected.status
        and expected.message_contains in message
        and validation_payload.get("decision") == case.expected_validation
    )
    return {
        "case_id": case.case_id,
        "coverage_label": expected.coverage_label,
        "source_fixture": expected.filename,
        "source_hint": case.source_hint,
        "source_kind_validation": case.expected_validation,
        "format": str(actual.get("format", "")),
        "role": str(actual.get("role", "")),
        "status": str(actual.get("status", "")),
        "message": message,
        "validation_decision": str(validation_payload.get("decision", "")),
        "required_confirmations": list(
            validation_payload.get("required_confirmations", [])
        ),
        "blocked_reasons": list(validation_payload.get("blocked_reasons", [])),
        "preview_summary": str(preview_payload.get("summary", "")),
        "preview_blocked_reasons": list(preview_payload.get("blocked_reasons", [])),
        "preview_confirmation_items": list(
            preview_payload.get("confirmation_items", [])
        ),
        "observed": observed,
        "matches_expected": matches_expected,
    }


def _write_case_fixture(case_dir: Path, case: FormatCase) -> None:
    for fixture in case.files:
        path = case_dir / fixture.relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_fixture_file(path, fixture.kind)


def _write_fixture_file(path: Path, kind: str) -> None:
    if path.suffix.lower() == ".fif":
        info = mne.create_info(["Cz"], sfreq=100.0, ch_types="eeg")
        raw = mne.io.RawArray(np.zeros((1, 500)), info, verbose="ERROR")
        raw.save(path, overwrite=True, verbose="ERROR")
    elif kind == "dataset_description":
        path.write_text(
            json.dumps(
                {
                    "Name": "XBrainLab format capability fixture",
                    "BIDSVersion": "1.9.0",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    elif kind == "mat_labels":
        savemat(
            str(path),
            {
                "classlabel": [[1, 2, 1, 2]],
                "cue_onset": [[0, 250, 500, 750]],
            },
        )
    elif kind == "eeglab_set":
        savemat(
            str(path),
            {
                "data": np.zeros((1, 500), dtype=np.float32),
                "nbchan": 1,
                "pnts": 500,
                "trials": 1,
                "srate": 100.0,
            },
            do_compression=False,
        )
    elif kind == "bids_events":
        path.write_text(
            "onset\tduration\ttrial_type\n0.0\t1.0\tleft\n2.0\t1.0\tright\n",
            encoding="utf-8",
        )
    elif kind == "csv_labels":
        path.write_text("sample,label\n0,left\n250,right\n", encoding="utf-8")
    elif kind == "tsv_labels":
        path.write_text("trial\tclass\n1,left\n2,right\n", encoding="utf-8")
    elif kind == "txt_labels":
        path.write_text("left\nright\n", encoding="utf-8")
    elif kind == "brainvision_vhdr":
        path.write_text(
            "Brain Vision Data Exchange Header File Version 1.0\n"
            "[Common Infos]\n"
            "DataFile=sub-01_ses-01_task-mi_run-1.eeg\n"
            "MarkerFile=sub-01_ses-01_task-mi_run-1.vmrk\n",
            encoding="utf-8",
        )
    elif kind == "brainvision_vmrk":
        path.write_text(
            "Brain Vision Data Exchange Marker File, Version 1.0\n"
            "[Marker Infos]\n"
            "Mk1=Stimulus,S  1,1,1,0\n",
            encoding="utf-8",
        )
    else:
        path.write_bytes(b"scan-only placeholder\n")


def _names(paths: Any) -> list[str]:
    return [Path(str(item)).name for item in paths or []]


def _escape_markdown(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


@contextlib.contextmanager
def _suppress_application_info_logs():
    """Keep report stdout machine-readable; failures remain structured evidence."""
    logger_level = xbrainlab_logger.level
    handler_levels = [handler.level for handler in xbrainlab_logger.handlers]
    silent_level = logging.CRITICAL + 1
    xbrainlab_logger.setLevel(silent_level)
    for handler in xbrainlab_logger.handlers:
        handler.setLevel(silent_level)
    try:
        yield
    finally:
        xbrainlab_logger.setLevel(logger_level)
        for handler, level in zip(
            xbrainlab_logger.handlers,
            handler_levels,
            strict=False,
        ):
            handler.setLevel(level)


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="markdown",
        help="Output format",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Fail unless synthetic capability boundaries and all required real "
            "scan/preview/validate/apply workflows pass."
        ),
    )
    parser.add_argument(
        "--write-artifacts",
        action="store_true",
        help="Write the JSON and Markdown matrix artifacts.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ARTIFACT_DIR,
        help="Artifact output directory when --write-artifacts is set.",
    )
    args = parser.parse_args()

    snapshot = build_data_interpretation_validation_snapshot()
    if args.write_artifacts:
        json_path, markdown_path = write_artifacts(snapshot, args.output_dir)
        print(f"Wrote {json_path}")
        print(f"Wrote {markdown_path}")
        return 0 if not args.strict or snapshot["strict_validation"]["ok"] else 1
    if args.format == "json":
        print(json.dumps(snapshot, indent=2, ensure_ascii=False, sort_keys=True))
    else:
        print(render_markdown(snapshot))
    return 0 if not args.strict or snapshot["strict_validation"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
