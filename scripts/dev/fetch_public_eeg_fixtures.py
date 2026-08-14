#!/usr/bin/env python3
"""Download public EEG fixtures for broader source and format validation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import ssl
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from typing import TypedDict
from urllib.parse import quote, urlparse

from XBrainLab.platform_paths import DATA_DIR_ENV, dataset_storage_layout

ROOT = Path(__file__).resolve().parents[2]
PUBLIC_DIR = ROOT / "tests" / "fixtures" / "data" / "public"
CI_REQUIRED_MAX_BYTES = 220 * 1024 * 1024
TEACHER_PREFLIGHT_MAX_BYTES = 320 * 1024 * 1024
DEFAULT_FIXTURE_PROFILE = "required-ci"
MNE_BIDS_TINY_NAME = "mne-bids-tiny-eeg"
MNE_BIDS_TINY_REVISION = (
    "9dc7b5b8bdfb8bbdb72983900e2df7be484f2b0c"  # pragma: allowlist secret
)
MNE_BIDS_TINY_SOURCE_ROOT = "mne_bids/tests/data/tiny_bids"
MNE_BIDS_TINY_RAW_BASE_URL = (
    "https://raw.githubusercontent.com/mne-tools/mne-bids/"
    f"{MNE_BIDS_TINY_REVISION}/{MNE_BIDS_TINY_SOURCE_ROOT}"
)
MNE_BIDS_TINY_ENTRYPOINT = (
    "mne-bids-tiny-eeg/sub-01/ses-eeg/eeg/sub-01_ses-eeg_task-rest_eeg.vhdr"
)
MNE_TESTING_DATA_REVISION = (
    "f9dc9fc10d35e817e45136d9a3932f2ee0d7053c"  # pragma: allowlist secret
)
OPENNEURO_P300_NAME = "openneuro-ds003061-p300"
OPENNEURO_P300_MULTISUBJECT_NAME = "openneuro-ds003061-p300-multisubject-extension"
OPENNEURO_P300_VERSION = "1.1.2"
OPENNEURO_P300_BASE_URL = "https://s3.amazonaws.com/openneuro.org/ds003061"
P300_MULTISUBJECT_MAX_BYTES = 700 * 1024 * 1024


class FixtureFile(TypedDict):
    """One pinned public fixture file."""

    filename: str
    url: str
    sha256: str
    size_bytes: int


class FixtureGroup(TypedDict):
    """One source-level public fixture group."""

    name: str
    description: str
    source: str
    entrypoint: str
    files: list[FixtureFile]


def resolve_public_fixture_dir(
    *,
    explicit: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> Path:
    """Resolve the public fixture cache without making CI machine-dependent."""
    if explicit is not None:
        return explicit.expanduser().absolute()
    env = os.environ if environ is None else environ
    if str(env.get(DATA_DIR_ENV, "")).strip():
        return dataset_storage_layout(environ=env).public_fixtures_root
    return PUBLIC_DIR


def _sha256(*segments: str) -> str:
    return "".join(segments)


MNE_BIDS_TINY_FILES: tuple[tuple[str, str, int], ...] = (
    (
        "README",
        _sha256(
            "2424885a2575d03a",  # pragma: allowlist secret
            "8a4733db5a8c9800",  # pragma: allowlist secret
            "b3ab2aa956d41cd5",  # pragma: allowlist secret
            "78a84ad79599b586",  # pragma: allowlist secret
        ),
        693,
    ),
    (
        "dataset_description.json",
        _sha256(
            "39ebf1b7a89a6e19",  # pragma: allowlist secret
            "280dfdd7767207df",  # pragma: allowlist secret
            "a5c962c709efe578",  # pragma: allowlist secret
            "ba7c5d9ce3e8b041",  # pragma: allowlist secret
        ),
        190,
    ),
    (
        "participants.json",
        _sha256(
            "85d31cc698fd8f6c",  # pragma: allowlist secret
            "d98522746c71fbbd",  # pragma: allowlist secret
            "7e36ca42393607bf",  # pragma: allowlist secret
            "cafcaff7f4edc2fd",  # pragma: allowlist secret
        ),
        771,
    ),
    (
        "participants.tsv",
        _sha256(
            "854ecc7216ba7648",  # pragma: allowlist secret
            "348bd5f0d8ae51a6",  # pragma: allowlist secret
            "df16ccbb8167d233",  # pragma: allowlist secret
            "33def6abb2d88fda",  # pragma: allowlist secret
        ),
        67,
    ),
    (
        "sub-01/ses-eeg/eeg/sub-01_ses-eeg_coordsystem.json",
        _sha256(
            "e0e01df82e280710",  # pragma: allowlist secret
            "3fd547af9ccae636",  # pragma: allowlist secret
            "5b79f9f91e533b4c",  # pragma: allowlist secret
            "7f5c9490b848b0c8",  # pragma: allowlist secret
        ),
        1040,
    ),
    (
        "sub-01/ses-eeg/eeg/sub-01_ses-eeg_electrodes.tsv",
        _sha256(
            "50f00c3adb3b9d04",  # pragma: allowlist secret
            "10ceddff84d51ed4",  # pragma: allowlist secret
            "0fe90aa89f1204bf",  # pragma: allowlist secret
            "0e41415d78083d3e",  # pragma: allowlist secret
        ),
        4443,
    ),
    (
        "sub-01/ses-eeg/eeg/sub-01_ses-eeg_space-CapTrak_coordsystem.json",
        _sha256(
            "e0e01df82e280710",  # pragma: allowlist secret
            "3fd547af9ccae636",  # pragma: allowlist secret
            "5b79f9f91e533b4c",  # pragma: allowlist secret
            "7f5c9490b848b0c8",  # pragma: allowlist secret
        ),
        1040,
    ),
    (
        "sub-01/ses-eeg/eeg/sub-01_ses-eeg_space-CapTrak_electrodes.tsv",
        _sha256(
            "0172199f9543eb2e",  # pragma: allowlist secret
            "7f3951518943d94b",  # pragma: allowlist secret
            "15d85c3b842b0677",  # pragma: allowlist secret
            "2a6b4e7130d71949",  # pragma: allowlist secret
        ),
        4553,
    ),
    (
        "sub-01/ses-eeg/eeg/sub-01_ses-eeg_task-rest_channels.tsv",
        _sha256(
            "df8883c71cb70865",  # pragma: allowlist secret
            "73c90d2e0945c761",  # pragma: allowlist secret
            "a3fd09b3b24f11d3",  # pragma: allowlist secret
            "cef62f84df6e89c5",  # pragma: allowlist secret
        ),
        5447,
    ),
    (
        "sub-01/ses-eeg/eeg/sub-01_ses-eeg_task-rest_eeg.eeg",
        _sha256(
            "7dd6d01424bcd836",  # pragma: allowlist secret
            "7a0c48b13253389f",  # pragma: allowlist secret
            "3b5fb508755c56b3",  # pragma: allowlist secret
            "214c90f3fe1e8212",  # pragma: allowlist secret
        ),
        1380000,
    ),
    (
        "sub-01/ses-eeg/eeg/sub-01_ses-eeg_task-rest_eeg.json",
        _sha256(
            "afe7def2643befa1",  # pragma: allowlist secret
            "49800d927e18a6e6",  # pragma: allowlist secret
            "7ff824f448fd44bf",  # pragma: allowlist secret
            "42c84b582c124cd5",  # pragma: allowlist secret
        ),
        503,
    ),
    (
        "sub-01/ses-eeg/eeg/sub-01_ses-eeg_task-rest_eeg.vhdr",
        _sha256(
            "3ff0577005cd9e49",  # pragma: allowlist secret
            "e672d48a256d365b",  # pragma: allowlist secret
            "4f7cbe1e96fea2a2",  # pragma: allowlist secret
            "6334645ef9b468af",  # pragma: allowlist secret
        ),
        11078,
    ),
    (
        "sub-01/ses-eeg/eeg/sub-01_ses-eeg_task-rest_eeg.vmrk",
        _sha256(
            "df211bf40a9578b2",  # pragma: allowlist secret
            "4951869f2610cd79",  # pragma: allowlist secret
            "79d68bbb9fa2594a",  # pragma: allowlist secret
            "d10b94f60048287e",  # pragma: allowlist secret
        ),
        529,
    ),
    (
        "sub-01/ses-eeg/eeg/sub-01_ses-eeg_task-rest_events.json",
        _sha256(
            "8bf8e6cdeb9eaa40",  # pragma: allowlist secret
            "b57bba4066fa8bc2",  # pragma: allowlist secret
            "30da76217cdeda0c",  # pragma: allowlist secret
            "19efc31de11b9cb0",  # pragma: allowlist secret
        ),
        476,
    ),
    (
        "sub-01/ses-eeg/eeg/sub-01_ses-eeg_task-rest_events.tsv",
        _sha256(
            "7f20d56032752bef",  # pragma: allowlist secret
            "41d8efcf3506f105",  # pragma: allowlist secret
            "d747bc34556f3d8b",  # pragma: allowlist secret
            "325df80b2aaba7c5",  # pragma: allowlist secret
        ),
        100,
    ),
    (
        "sub-01/ses-eeg/sub-01_ses-eeg_scans.tsv",
        _sha256(
            "1ec0eb51f143b243",  # pragma: allowlist secret
            "afdecd1980060415",  # pragma: allowlist secret
            "fb3fd4b34cfaef50",  # pragma: allowlist secret
            "f843bd813c6c8728",  # pragma: allowlist secret
        ),
        87,
    ),
    (
        "sub-01/sub-01_sessions.json",
        _sha256(
            "92b0f5178442768d",  # pragma: allowlist secret
            "cb5b67e4eb14c64d",  # pragma: allowlist secret
            "627e534cec534ce6",  # pragma: allowlist secret
            "a4157ae46e100e04",  # pragma: allowlist secret
        ),
        261,
    ),
    (
        "sub-01/sub-01_sessions.tsv",
        _sha256(
            "ca47aa9a0a90bf95",  # pragma: allowlist secret
            "05a6d380c76968d7",  # pragma: allowlist secret
            "7503c1baed42df61",  # pragma: allowlist secret
            "944f754b62c8afd1",  # pragma: allowlist secret
        ),
        86,
    ),
)


def _mne_bids_tiny_downloads() -> list[FixtureFile]:
    return [
        {
            "filename": f"{MNE_BIDS_TINY_NAME}/{relative_path}",
            "url": f"{MNE_BIDS_TINY_RAW_BASE_URL}/{quote(relative_path, safe='/')}",
            "sha256": sha256,
            "size_bytes": size_bytes,
        }
        for relative_path, sha256, size_bytes in MNE_BIDS_TINY_FILES
    ]


OPENNEURO_P300_FILES: tuple[tuple[str, str, int], ...] = (
    (
        "README",
        "38453943c3d1564fb4b45ed9e59276684a25d38139f60e30242534960994c1b0",  # pragma: allowlist secret
        1742,
    ),
    (
        "dataset_description.json",
        "e4a6f4095f4dc7c4b84b7d2930eeb618262d231e473e503013273f780d64c753",  # pragma: allowlist secret
        501,
    ),
    (
        "participants.json",
        "afa01f868867780199fe6c3b03666febc94206a526329ee04763653856868f58",  # pragma: allowlist secret
        768,
    ),
    (
        "participants.tsv",
        "aa1262f77a7e9fc9c5ec66629507e3ff49efc4fb32a9833615325bb53074a8c1",  # pragma: allowlist secret
        377,
    ),
    (
        "task-P300_events.json",
        "ddfe630b881248dfcd66a90794e39bd8ee6b1391bb9f12755c78b1a46293f92e",  # pragma: allowlist secret
        2983,
    ),
    (
        "sub-001/eeg/sub-001_task-P300_run-1_channels.tsv",
        "2ff571acb0e9f9fe82027fb00bcf3927ff9f6794eeaa978ff4b9580a3b7907be",  # pragma: allowlist secret
        1152,
    ),
    (
        "sub-001/eeg/sub-001_task-P300_run-1_coordsystem.json",
        "38cbd743cd80f8243716dcfe326138c49c124855551fbed50f935724a5ee71d3",  # pragma: allowlist secret
        97,
    ),
    (
        "sub-001/eeg/sub-001_task-P300_run-1_eeg.json",
        "e8f1e276ae3c50a5cf2f11251eb11c5166197ca456f5bed56ff72fc4a268ddaa",  # pragma: allowlist secret
        1377,
    ),
    (
        "sub-001/eeg/sub-001_task-P300_run-1_eeg.set",
        "e07138cd7f7509fe40655691f61df29324f89d40141dae701407fc6cbca8646c",  # pragma: allowlist secret
        63516912,
    ),
    (
        "sub-001/eeg/sub-001_task-P300_run-1_electrodes.tsv",
        "7159f6f8f95410bfa3653d42985a10cf176400486a4ec8732b42bde7eebe30c0",  # pragma: allowlist secret
        1717,
    ),
    (
        "sub-001/eeg/sub-001_task-P300_run-1_events.json",
        "1c1447887fded4c86acf66cc6a35326a5b56152c14a47163c111c48fced966c5",  # pragma: allowlist secret
        1893,
    ),
    (
        "sub-001/eeg/sub-001_task-P300_run-1_events.tsv",
        "1851175f4a5f11c604708510ec2843ed57e9d70cdf2147fda5451878fc9b3131",  # pragma: allowlist secret
        45335,
    ),
    (
        "sub-001/eeg/sub-001_task-P300_run-2_channels.tsv",
        "2ff571acb0e9f9fe82027fb00bcf3927ff9f6794eeaa978ff4b9580a3b7907be",  # pragma: allowlist secret
        1152,
    ),
    (
        "sub-001/eeg/sub-001_task-P300_run-2_coordsystem.json",
        "38cbd743cd80f8243716dcfe326138c49c124855551fbed50f935724a5ee71d3",  # pragma: allowlist secret
        97,
    ),
    (
        "sub-001/eeg/sub-001_task-P300_run-2_eeg.json",
        "6d7dae55f96d3f5f643f1a9df944f51fbb9011d0966794136b69bf0025cf6fdf",  # pragma: allowlist secret
        1377,
    ),
    (
        "sub-001/eeg/sub-001_task-P300_run-2_eeg.set",
        "4a4fd78720ebf0a00b91eba6465162da7d4cfe74c485cef0e838a7a86c963602",  # pragma: allowlist secret
        63433336,
    ),
    (
        "sub-001/eeg/sub-001_task-P300_run-2_electrodes.tsv",
        "7159f6f8f95410bfa3653d42985a10cf176400486a4ec8732b42bde7eebe30c0",  # pragma: allowlist secret
        1717,
    ),
    (
        "sub-001/eeg/sub-001_task-P300_run-2_events.json",
        "1c1447887fded4c86acf66cc6a35326a5b56152c14a47163c111c48fced966c5",  # pragma: allowlist secret
        1893,
    ),
    (
        "sub-001/eeg/sub-001_task-P300_run-2_events.tsv",
        "58afc85d5fe1e85a19ca8f0115dcc825b35a007668cc3a15518526c583b0631a",  # pragma: allowlist secret
        45307,
    ),
    (
        "sub-001/eeg/sub-001_task-P300_run-3_channels.tsv",
        "2ff571acb0e9f9fe82027fb00bcf3927ff9f6794eeaa978ff4b9580a3b7907be",  # pragma: allowlist secret
        1152,
    ),
    (
        "sub-001/eeg/sub-001_task-P300_run-3_coordsystem.json",
        "38cbd743cd80f8243716dcfe326138c49c124855551fbed50f935724a5ee71d3",  # pragma: allowlist secret
        97,
    ),
    (
        "sub-001/eeg/sub-001_task-P300_run-3_eeg.json",
        "6644b91106926737f5eb63f4b5ce6640c73175ffe686222d3947dba950749aae",  # pragma: allowlist secret
        1377,
    ),
    (
        "sub-001/eeg/sub-001_task-P300_run-3_eeg.set",
        "0ea43ace2bd0010dadb99c3e50161a981b5ff834a69c895727008a2088915ecb",  # pragma: allowlist secret
        63349072,
    ),
    (
        "sub-001/eeg/sub-001_task-P300_run-3_electrodes.tsv",
        "7159f6f8f95410bfa3653d42985a10cf176400486a4ec8732b42bde7eebe30c0",  # pragma: allowlist secret
        1717,
    ),
    (
        "sub-001/eeg/sub-001_task-P300_run-3_events.json",
        "1c1447887fded4c86acf66cc6a35326a5b56152c14a47163c111c48fced966c5",  # pragma: allowlist secret
        1893,
    ),
    (
        "sub-001/eeg/sub-001_task-P300_run-3_events.tsv",
        "0bc2d6c2e7334add8d95c472a34e4fab72ea101f81d1580940736a08d1d547ae",  # pragma: allowlist secret
        45156,
    ),
)


def _openneuro_p300_downloads() -> list[FixtureFile]:
    return [
        {
            "filename": f"{OPENNEURO_P300_NAME}/{relative_path}",
            "url": f"{OPENNEURO_P300_BASE_URL}/{quote(relative_path, safe='/')}",
            "sha256": sha256,
            "size_bytes": size_bytes,
        }
        for relative_path, sha256, size_bytes in OPENNEURO_P300_FILES
    ]


_P300_SHARED_SIDECARS: tuple[tuple[str, str, int], ...] = (
    (
        "channels.tsv",
        "2ff571acb0e9f9fe82027fb00bcf3927ff9f6794eeaa978ff4b9580a3b7907be",  # pragma: allowlist secret
        1152,
    ),
    (
        "coordsystem.json",
        "38cbd743cd80f8243716dcfe326138c49c124855551fbed50f935724a5ee71d3",  # pragma: allowlist secret
        97,
    ),
    (
        "electrodes.tsv",
        "7159f6f8f95410bfa3653d42985a10cf176400486a4ec8732b42bde7eebe30c0",  # pragma: allowlist secret
        1717,
    ),
    (
        "events.json",
        "1c1447887fded4c86acf66cc6a35326a5b56152c14a47163c111c48fced966c5",  # pragma: allowlist secret
        1893,
    ),
)

# subject, run, eeg.set hash/size, eeg.json hash/size, events.tsv hash/size
OPENNEURO_P300_MULTISUBJECT_RUNS: tuple[
    tuple[str, int, str, int, str, int, str, int], ...
] = (
    (
        "002",
        1,
        "78640f17bbe0069ce421dc754a4be7f9594bfa61f1b96ec13ebae2682498f322",  # pragma: allowlist secret
        63068800,
        "b3a287656ffe3ae053d54660f89f7e466fcb1db1db798530c16be1d1cc37bcfd",  # pragma: allowlist secret
        1392,
        "6859df45d6729e8cb5e3ddb39bbcb58ea7ba5cd11ad13df9345cc430cfabc724",  # pragma: allowlist secret
        42059,
    ),
    (
        "002",
        2,
        "14837ab4f65114bd2cc725b42958659089d1ef364f605c53c18914141ba79447",  # pragma: allowlist secret
        62982648,
        "1ec2ee7a2ecfe2b4b8b84a9275e9bb5cba6d87a999dfb226cfc4bc45b25fac2b",  # pragma: allowlist secret
        1419,
        "ab2ad846dbeb1c6ef2e99f3e0c2d37e3bddc37fcd7a5cbd6c98b816ae3e096f0",  # pragma: allowlist secret
        41717,
    ),
    (
        "002",
        3,
        "3e9c88e465485952f1b452e347a8afa46fc5b86d6f209d1f87a284415fa82500",  # pragma: allowlist secret
        62977424,
        "1ee05bd171585199334ee637286f37cc760c094e9df48912814c28e8246b9034",  # pragma: allowlist secret
        1444,
        "389a280e3b8681cf3860db4e62dfa9dfcff7aaf9c25c677be94343231c180d6b",  # pragma: allowlist secret
        41231,
    ),
    (
        "003",
        1,
        "c56852d7507875362867161dd51bba1b53352e74305ee3f99f70e6c23c8fec5e",  # pragma: allowlist secret
        63100664,
        "8fe2465a9e9e6bb564f1310b4af80f693c2b768e698d99e32c1a5271b870aba9",  # pragma: allowlist secret
        1377,
        "bf07a2aa96ddb511f92766b31f8fd1a61733fe87426cfcfbae1d2812e3f6b186",  # pragma: allowlist secret
        45216,
    ),
    (
        "003",
        2,
        "298b29e41b6574286557f5fb4207c8467e18d294a84d1fc4036c450d6857635f",  # pragma: allowlist secret
        63099800,
        "8fe2465a9e9e6bb564f1310b4af80f693c2b768e698d99e32c1a5271b870aba9",  # pragma: allowlist secret
        1377,
        "86732188c5f6339a8ddc4e118848282cbfe95d3f49faae2a9cce71069761b3d9",  # pragma: allowlist secret
        44968,
    ),
    (
        "003",
        3,
        "53f5fa0584140e55025863437042972245d2842e9c2fe5a0e79b7f50454dc8f6",  # pragma: allowlist secret
        63183600,
        "becb08e89527b1595cf9a195b034466c481d674a31acec6000f925a4274d5fed",  # pragma: allowlist secret
        1377,
        "e1621a50fe6825e3eb3910eb0f51c0e8fabe15d42d596e4b718cdb1255c7e256",  # pragma: allowlist secret
        45202,
    ),
)


def _openneuro_p300_multisubject_downloads() -> list[FixtureFile]:
    """Return two extra complete subjects for manual BIDS selector testing."""
    downloads: list[FixtureFile] = []
    for (
        subject,
        run,
        eeg_set_sha256,
        eeg_set_size,
        eeg_json_sha256,
        eeg_json_size,
        events_tsv_sha256,
        events_tsv_size,
    ) in OPENNEURO_P300_MULTISUBJECT_RUNS:
        prefix = f"sub-{subject}/eeg/sub-{subject}_task-P300_run-{run}"
        files = (
            ("eeg.set", eeg_set_sha256, eeg_set_size),
            ("eeg.json", eeg_json_sha256, eeg_json_size),
            ("events.tsv", events_tsv_sha256, events_tsv_size),
            *_P300_SHARED_SIDECARS,
        )
        downloads.extend(
            {
                "filename": f"{OPENNEURO_P300_NAME}/{prefix}_{suffix}",
                "url": (
                    f"{OPENNEURO_P300_BASE_URL}/{quote(f'{prefix}_{suffix}', safe='/')}"
                ),
                "sha256": sha256,
                "size_bytes": size_bytes,
            }
            for suffix, sha256, size_bytes in files
        )
    return downloads


FIXTURE_GROUPS: list[FixtureGroup] = [
    {
        "name": "physionet-edf-rest",
        "description": "PhysioNet EEG Motor Movement/Imagery dataset, EDF, baseline/rest run kept for import-only EDF coverage.",
        "source": "PhysioNet EEG Motor Movement/Imagery Dataset",
        "entrypoint": "physionet-eegmmidb-S008R01.edf",
        "files": [
            {
                "filename": "physionet-eegmmidb-S008R01.edf",
                "url": "https://physionet.org/files/eegmmidb/1.0.0/S008/S008R01.edf?download=",
                "sha256": "678e47541d9903c300ba7811554ad1f8bfbe2bff086407cb4ff489d2d0e507bc",  # pragma: allowlist secret
                "size_bytes": 1275936,
            },
        ],
    },
    {
        "name": "physionet-edf-motor",
        "description": "PhysioNet EEG Motor Movement/Imagery dataset, EDF, event-rich motor imagery run for one-epoch smoke.",
        "source": "PhysioNet EEG Motor Movement/Imagery Dataset",
        "entrypoint": "physionet-eegmmidb-S008R04.edf",
        "files": [
            {
                "filename": "physionet-eegmmidb-S008R04.edf",
                "url": "https://physionet.org/files/eegmmidb/1.0.0/S008/S008R04.edf?download=",
                "sha256": "034a26131e1425e6374a459e5887b1f831f7bfdb101a3658d2cd07620cf2c06b",  # pragma: allowlist secret
                "size_bytes": 2555616,
            },
        ],
    },
    {
        "name": "bbci-gdf",
        "description": "BCI Competition III dataset IIIb, GDF, motor imagery with non-stationarity.",
        "source": "BBCI / BCI Competition III dataset IIIb",
        "entrypoint": "bbci-competition-iii-O3VR.gdf",
        "files": [
            {
                "filename": "bbci-competition-iii-O3VR.gdf",
                "url": "https://www.bbci.de/competition/download/competition_iii/graz/O3VR.gdf",
                "sha256": "947636fada6b7ab8d6d9d6e047fb900c0f3fe00d62abe6250ad76d9c5940043e",  # pragma: allowlist secret
                "size_bytes": 2949728,
            },
        ],
    },
    {
        "name": "sccn-eeglab",
        "description": "Official EEGLAB tutorial dataset, EEGLAB .set format.",
        "source": "SCCN / EEGLAB tutorial dataset",
        "entrypoint": "sccn-eeglab_data.set",
        "files": [
            {
                "filename": "sccn-eeglab_data.set",
                "url": "https://sccn.ucsd.edu/eeglab/download/eeglab_data.set",
                "sha256": "b4bf70cd5db2d0636ea773d8542a56179acf2927b1079a20a8c0d500fd40debc",  # pragma: allowlist secret
                "size_bytes": 3986216,
            },
        ],
    },
    {
        "name": "mne-testing-cnt",
        "description": "MNE testing-data Neuroscan CNT sample.",
        "source": "MNE testing-data",
        "entrypoint": "scan41_short.cnt",
        "files": [
            {
                "filename": "scan41_short.cnt",
                "url": (
                    "https://raw.githubusercontent.com/mne-tools/mne-testing-data/"
                    f"{MNE_TESTING_DATA_REVISION}/CNT/scan41_short.cnt"
                ),
                "sha256": "f58b7182f6be670159a79090fb666d3f1ed6645f5b488d0016940fd2b8b7e5b6",  # pragma: allowlist secret
                "size_bytes": 2033263,
            },
        ],
    },
    {
        "name": "mne-testing-brainvision",
        "description": "MNE testing-data BrainVision sample with .vhdr entrypoint and .eeg/.vmrk sidecars.",
        "source": "MNE testing-data",
        "entrypoint": "test_NO.vhdr",
        "files": [
            {
                "filename": "test_NO.vhdr",
                "url": (
                    "https://raw.githubusercontent.com/mne-tools/mne-testing-data/"
                    f"{MNE_TESTING_DATA_REVISION}/Brainvision/test_NO.vhdr"
                ),
                "sha256": "aa3f2d42a1ad3897e702c27d09abdd261f01ccdeb0dae2e674af25fe7be72261",  # pragma: allowlist secret
                "size_bytes": 1451,
            },
            {
                "filename": "test_NO.eeg",
                "url": (
                    "https://raw.githubusercontent.com/mne-tools/mne-testing-data/"
                    f"{MNE_TESTING_DATA_REVISION}/Brainvision/test_NO.eeg"
                ),
                "sha256": "894099d7ea0db262bd2dd84918ff96e5c81e39f7677f0405746faaed1623604b",  # pragma: allowlist secret
                "size_bytes": 581880,
            },
            {
                "filename": "test_NO.vmrk",
                "url": (
                    "https://raw.githubusercontent.com/mne-tools/mne-testing-data/"
                    f"{MNE_TESTING_DATA_REVISION}/Brainvision/test_NO.vmrk"
                ),
                "sha256": "fc02236e72a90124ea04f171a065ae94784ec707bbd96632a86a44499bf7cf27",  # pragma: allowlist secret
                "size_bytes": 267,
            },
        ],
    },
    {
        "name": MNE_BIDS_TINY_NAME,
        "description": "Pinned MNE-BIDS tiny_bids EEG root, downloaded as a real external BIDS fixture.",
        "source": "MNE-BIDS tiny_bids test data",
        "entrypoint": MNE_BIDS_TINY_ENTRYPOINT,
        "files": _mne_bids_tiny_downloads(),
    },
    {
        "name": OPENNEURO_P300_NAME,
        "description": (
            "OpenNeuro ds003061 auditory P300 BIDS dataset: one subject, three "
            "EEGLAB runs, and per-run events.tsv label carriers."
        ),
        "source": (
            f"OpenNeuro ds003061 snapshot {OPENNEURO_P300_VERSION}, mirrored "
            "from the public S3 object paths. The local cache is exact-byte "
            "pinned by size and SHA-256; a changed upstream object fails "
            "verification instead of being accepted silently"
        ),
        "entrypoint": OPENNEURO_P300_NAME,
        "files": _openneuro_p300_downloads(),
    },
    {
        "name": OPENNEURO_P300_MULTISUBJECT_NAME,
        "description": (
            "Two additional complete ds003061 P300 subjects for exercising "
            "BIDS subject selection with three subjects and nine runs total."
        ),
        "source": (
            f"OpenNeuro ds003061 snapshot {OPENNEURO_P300_VERSION}; exact-byte "
            "pinned subject-selection extension for local product testing"
        ),
        "entrypoint": OPENNEURO_P300_NAME,
        "files": _openneuro_p300_multisubject_downloads(),
    },
    {
        "name": "chbmit-chb01",
        "description": (
            "CHB-MIT scalp EEG seizure recording with the source summary and "
            "seizure sidecar retained for boundary testing."
        ),
        "source": "PhysioNet CHB-MIT Scalp EEG Database 1.0.0",
        "entrypoint": "chbmit-chb01/chb01_03.edf",
        "files": [
            {
                "filename": "chbmit-chb01/chb01_03.edf",
                "url": "https://physionet.org/files/chbmit/1.0.0/chb01/chb01_03.edf",
                "sha256": "4c4a95a9b4331aeaadadd538763eb2e735950d9aa615b85ee6246c784be8ae90",  # pragma: allowlist secret
                "size_bytes": 42399744,
            },
            {
                "filename": "chbmit-chb01/chb01_03.edf.seizures",
                "url": (
                    "https://physionet.org/files/chbmit/1.0.0/chb01/"
                    "chb01_03.edf.seizures"
                ),
                "sha256": "eb521b5e1a521f70fb8224e4205f0826c5ade093f29765d057b5db4d6b6594ab",  # pragma: allowlist secret
                "size_bytes": 54,
            },
            {
                "filename": "chbmit-chb01/chb01-summary.txt",
                "url": (
                    "https://physionet.org/files/chbmit/1.0.0/chb01/chb01-summary.txt"
                ),
                "sha256": "77e86183845192d147c88a9bb4263c2b4a32e936c6236029770f86ca2ea023db",  # pragma: allowlist secret
                "size_bytes": 5355,
            },
        ],
    },
    {
        "name": "sleep-edfx-st7011",
        "description": (
            "Sleep-EDF telemetry PSG recording with its independent EDF+ "
            "hypnogram annotation file."
        ),
        "source": "PhysioNet Sleep-EDF Expanded 1.0.0",
        "entrypoint": "sleep-edfx-st7011/ST7011J0-PSG.edf",
        "files": [
            {
                "filename": "sleep-edfx-st7011/ST7011J0-PSG.edf",
                "url": (
                    "https://physionet.org/files/sleep-edfx/1.0.0/"
                    "sleep-telemetry/ST7011J0-PSG.edf"
                ),
                "sha256": "6f14ca2c42184c5114e2d220d91c4f0d7bc627fb53f6760c4c9997272cf4319b",  # pragma: allowlist secret
                "size_bytes": 29439536,
            },
            {
                "filename": "sleep-edfx-st7011/ST7011JP-Hypnogram.edf",
                "url": (
                    "https://physionet.org/files/sleep-edfx/1.0.0/"
                    "sleep-telemetry/ST7011JP-Hypnogram.edf"
                ),
                "sha256": "e4c8dcc87611e3daa559f633b43d51b47e0ba6ad1f246fc9af3327e4e4e885a8",  # pragma: allowlist secret
                "size_bytes": 6356,
            },
        ],
    },
]

CI_REQUIRED_GROUP_NAMES = frozenset(
    {
        "physionet-edf-rest",
        "physionet-edf-motor",
        "bbci-gdf",
        "sccn-eeglab",
        "mne-testing-cnt",
        "mne-testing-brainvision",
        MNE_BIDS_TINY_NAME,
        OPENNEURO_P300_NAME,
    }
)
CI_REQUIRED_MANIFEST_SHA256 = "f7bb9c3938cdaad72cc6843ee6ba1c22d403ff5ec6c5432fc51459de0d44983e"  # pragma: allowlist secret
TEACHER_PREFLIGHT_GROUP_NAMES = frozenset(
    {
        *CI_REQUIRED_GROUP_NAMES,
        OPENNEURO_P300_NAME,
        "chbmit-chb01",
        "sleep-edfx-st7011",
    }
)
P300_MULTISUBJECT_GROUP_NAMES = frozenset(
    {OPENNEURO_P300_NAME, OPENNEURO_P300_MULTISUBJECT_NAME}
)

_ALLOWED_DOWNLOAD_HOSTS = {
    "physionet.org",
    "s3.amazonaws.com",
    "www.bbci.de",
    "sccn.ucsd.edu",
    "raw.githubusercontent.com",
}


def _validate_download_url(url: str) -> None:
    """Reject unexpected schemes or hosts before issuing a network request."""
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError(f"Unsupported download URL scheme: {parsed.scheme}")
    if parsed.netloc not in _ALLOWED_DOWNLOAD_HOSTS:
        raise ValueError(f"Unexpected download host: {parsed.netloc}")


def fixture_manifest_sha256(groups: list[FixtureGroup]) -> str:
    """Return a canonical digest of evidence-critical fixture metadata."""
    manifest = [
        {
            "name": group["name"],
            "entrypoint": group["entrypoint"],
            "files": sorted(
                (
                    {
                        "filename": fixture_file["filename"],
                        "url": fixture_file["url"],
                        "sha256": fixture_file["sha256"],
                        "size_bytes": fixture_file["size_bytes"],
                    }
                    for fixture_file in group["files"]
                ),
                key=lambda fixture_file: fixture_file["filename"],
            ),
        }
        for group in sorted(groups, key=lambda group: group["name"])
    ]
    encoded = json.dumps(
        manifest,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def validate_fixture_profile_manifest(
    profile: str,
    groups: list[FixtureGroup],
) -> None:
    """Reject a required profile whose fixed manifest denominator drifted."""
    if profile != "required-ci":
        return
    actual_digest = fixture_manifest_sha256(groups)
    if actual_digest != CI_REQUIRED_MANIFEST_SHA256:
        raise RuntimeError(
            "Required CI fixture manifest is stale or incomplete: "
            f"expected {CI_REQUIRED_MANIFEST_SHA256}, got {actual_digest}"
        )


def fixture_groups_for_profile(profile: str) -> list[FixtureGroup]:
    """Return the pinned groups selected by a download profile."""
    if profile == "all":
        return list(FIXTURE_GROUPS)
    if profile == "required-ci":
        selected = [
            group
            for group in FIXTURE_GROUPS
            if group["name"] in CI_REQUIRED_GROUP_NAMES
        ]
        selected_names = {group["name"] for group in selected}
        missing_groups = CI_REQUIRED_GROUP_NAMES - selected_names
        if missing_groups:
            raise RuntimeError(
                "Required CI fixture groups are not defined: "
                + ", ".join(sorted(missing_groups))
            )
        validate_fixture_profile_manifest(profile, selected)
        return selected
    if profile == "teacher-preflight":
        selected = [
            group
            for group in FIXTURE_GROUPS
            if group["name"] in TEACHER_PREFLIGHT_GROUP_NAMES
        ]
        selected_names = {group["name"] for group in selected}
        missing_groups = TEACHER_PREFLIGHT_GROUP_NAMES - selected_names
        if missing_groups:
            raise RuntimeError(
                "Teacher preflight fixture groups are not defined: "
                + ", ".join(sorted(missing_groups))
            )
        return selected
    if profile == "p300-multisubject":
        selected = [
            group
            for group in FIXTURE_GROUPS
            if group["name"] in P300_MULTISUBJECT_GROUP_NAMES
        ]
        selected_names = {group["name"] for group in selected}
        missing_groups = P300_MULTISUBJECT_GROUP_NAMES - selected_names
        if missing_groups:
            raise RuntimeError(
                "P300 multi-subject fixture groups are not defined: "
                + ", ".join(sorted(missing_groups))
            )
        return selected
    raise ValueError(f"Unknown fixture profile: {profile}")


def fixture_profile_size_bytes(groups: list[FixtureGroup]) -> int:
    """Return the exact manifest size for a fixture profile."""
    return sum(
        fixture_file["size_bytes"]
        for group in groups
        for fixture_file in group["files"]
    )


def download_file(url: str, destination: Path, *, max_bytes: int) -> None:
    """Download one fixture without allowing its pinned size boundary to grow."""
    _validate_download_url(url)
    request = urllib.request.Request(  # noqa: S310 - validated by _validate_download_url
        url,
        headers={"User-Agent": "XBrainLab Codex"},
    )
    context = ssl.create_default_context()
    with (
        urllib.request.urlopen(  # noqa: S310 - validated by _validate_download_url
            request,
            context=context,
            timeout=120,
        ) as response,
        destination.open("wb") as handle,
    ):
        downloaded_bytes = 0
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            downloaded_bytes += len(chunk)
            if downloaded_bytes > max_bytes:
                raise ValueError(
                    f"Fixture download exceeds pinned size boundary ({max_bytes} bytes)"
                )
            handle.write(chunk)


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest for ``path``."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def fixture_file_is_valid(
    path: Path,
    expected_sha256: str,
    expected_size_bytes: int | None = None,
) -> bool:
    """Return whether a downloaded fixture exists, is non-empty, and matches hash."""
    if not path.exists() or path.stat().st_size <= 0:
        return False
    if expected_size_bytes is not None and path.stat().st_size != expected_size_bytes:
        return False
    return sha256_file(path) == expected_sha256


def validate_fixture_file(
    path: Path,
    expected_sha256: str,
    expected_size_bytes: int | None = None,
) -> None:
    """Raise if a downloaded fixture is missing, empty, or hash-mismatched."""
    if not path.exists():
        raise FileNotFoundError(f"Downloaded fixture is missing: {path}")
    if path.stat().st_size <= 0:
        raise ValueError(f"Downloaded fixture is empty: {path}")
    if expected_size_bytes is not None and path.stat().st_size != expected_size_bytes:
        raise ValueError(
            f"Downloaded fixture size mismatch for {path.name}: "
            f"expected {expected_size_bytes}, got {path.stat().st_size}"
        )
    actual = sha256_file(path)
    if actual != expected_sha256:
        raise ValueError(
            f"Downloaded fixture hash mismatch for {path.name}: "
            f"expected {expected_sha256}, got {actual}"
        )


def download_fixture_file(fixture_file: FixtureFile, destination: Path) -> None:
    """Download, validate, then atomically install one fixture file."""
    temporary_path = destination.with_name(f"{destination.name}.part")
    temporary_path.unlink(missing_ok=True)
    try:
        download_file(
            fixture_file["url"],
            temporary_path,
            max_bytes=fixture_file["size_bytes"],
        )
        validate_fixture_file(
            temporary_path,
            fixture_file["sha256"],
            fixture_file["size_bytes"],
        )
        temporary_path.replace(destination)
    finally:
        temporary_path.unlink(missing_ok=True)


def validate_fixture_set(public_dir: Path, groups: list[FixtureGroup]) -> None:
    """Validate every file in a selected profile against its pinned manifest."""
    for group in groups:
        for fixture_file in group["files"]:
            validate_fixture_file(
                public_dir / fixture_file["filename"],
                fixture_file["sha256"],
                fixture_file["size_bytes"],
            )


def main() -> int:
    """Download or verify a controlled public-fixture profile."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download files even if they already exist.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List fixture metadata without downloading.",
    )
    parser.add_argument(
        "--profile",
        choices=("all", "required-ci", "teacher-preflight", "p300-multisubject"),
        default=DEFAULT_FIXTURE_PROFILE,
        help=(
            "Select all fixtures, the compact required CI profile, or the "
            "larger local teacher-preflight profile, or the three-subject "
            "P300 BIDS profile."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help=(
            "Fixture destination. Defaults to XBRAINLAB_DATA_DIR/datasets/"
            "public-fixtures when configured, otherwise the repo CI cache."
        ),
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Validate the selected fixture profile without downloading.",
    )
    args = parser.parse_args()
    public_dir = resolve_public_fixture_dir(explicit=args.output_dir)
    groups = fixture_groups_for_profile(args.profile)
    profile_size_bytes = fixture_profile_size_bytes(groups)
    if args.profile == "required-ci" and profile_size_bytes > CI_REQUIRED_MAX_BYTES:
        raise ValueError(
            "Required CI fixture profile exceeds its download boundary: "
            f"{profile_size_bytes} > {CI_REQUIRED_MAX_BYTES} bytes"
        )
    if (
        args.profile == "teacher-preflight"
        and profile_size_bytes > TEACHER_PREFLIGHT_MAX_BYTES
    ):
        raise ValueError(
            "Teacher preflight fixture profile exceeds its download boundary: "
            f"{profile_size_bytes} > {TEACHER_PREFLIGHT_MAX_BYTES} bytes"
        )
    if (
        args.profile == "p300-multisubject"
        and profile_size_bytes > P300_MULTISUBJECT_MAX_BYTES
    ):
        raise ValueError(
            "P300 multi-subject fixture profile exceeds its download boundary: "
            f"{profile_size_bytes} > {P300_MULTISUBJECT_MAX_BYTES} bytes"
        )

    if args.list:
        for fixture_group in groups:
            print(
                f"{fixture_group['name']}: {fixture_group['description']}"
                f" [{fixture_group['source']}]",
            )
            print(f"  entrypoint: {fixture_group['entrypoint']}")
            for fixture_file in fixture_group["files"]:
                print(f"  - {fixture_file['filename']}")
                print(f"    {fixture_file['url']}")
                print(f"    sha256: {fixture_file['sha256']}")
                print(f"    size: {fixture_file['size_bytes']} bytes")
        print(f"Profile total: {profile_size_bytes} bytes")
        return 0

    public_dir.mkdir(parents=True, exist_ok=True)
    if args.verify_only:
        validate_fixture_set(public_dir, groups)
        print(
            f"Verified {args.profile} public EEG fixture profile "
            f"({profile_size_bytes} bytes)."
        )
        return 0

    for fixture_group in groups:
        print(
            f"Preparing {fixture_group['name']} "
            f"({fixture_group['source']}, entrypoint {fixture_group['entrypoint']})...",
        )
        for fixture_file in fixture_group["files"]:
            destination = public_dir / fixture_file["filename"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            if (
                destination.exists()
                and not args.force
                and fixture_file_is_valid(
                    destination,
                    fixture_file["sha256"],
                    fixture_file["size_bytes"],
                )
            ):
                print(f"  Using existing fixture: {destination}")
                continue
            if destination.exists() and not args.force:
                print(
                    f"  Existing fixture failed validation; re-downloading {destination.name}..."
                )

            print(f"  Downloading {fixture_file['filename']}...")
            download_fixture_file(fixture_file, destination)
            print(f"  Saved {destination}")

    validate_fixture_set(public_dir, groups)
    print(
        f"Verified {args.profile} public EEG fixture profile "
        f"({profile_size_bytes} bytes)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
