#!/usr/bin/env python3
"""Download public EEG fixtures for broader source and format validation."""

from __future__ import annotations

import argparse
import hashlib
import ssl
import urllib.request
from pathlib import Path
from urllib.parse import quote, urlparse

ROOT = Path(__file__).resolve().parents[2]
PUBLIC_DIR = ROOT / "tests" / "fixtures" / "data" / "public"
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


def _sha256(*segments: str) -> str:
    return "".join(segments)


MNE_BIDS_TINY_FILES = (
    (
        "README",
        _sha256(
            "2424885a2575d03a",  # pragma: allowlist secret
            "8a4733db5a8c9800",  # pragma: allowlist secret
            "b3ab2aa956d41cd5",  # pragma: allowlist secret
            "78a84ad79599b586",  # pragma: allowlist secret
        ),
    ),
    (
        "dataset_description.json",
        _sha256(
            "39ebf1b7a89a6e19",  # pragma: allowlist secret
            "280dfdd7767207df",  # pragma: allowlist secret
            "a5c962c709efe578",  # pragma: allowlist secret
            "ba7c5d9ce3e8b041",  # pragma: allowlist secret
        ),
    ),
    (
        "participants.json",
        _sha256(
            "85d31cc698fd8f6c",  # pragma: allowlist secret
            "d98522746c71fbbd",  # pragma: allowlist secret
            "7e36ca42393607bf",  # pragma: allowlist secret
            "cafcaff7f4edc2fd",  # pragma: allowlist secret
        ),
    ),
    (
        "participants.tsv",
        _sha256(
            "854ecc7216ba7648",  # pragma: allowlist secret
            "348bd5f0d8ae51a6",  # pragma: allowlist secret
            "df16ccbb8167d233",  # pragma: allowlist secret
            "33def6abb2d88fda",  # pragma: allowlist secret
        ),
    ),
    (
        "sub-01/ses-eeg/eeg/sub-01_ses-eeg_coordsystem.json",
        _sha256(
            "e0e01df82e280710",  # pragma: allowlist secret
            "3fd547af9ccae636",  # pragma: allowlist secret
            "5b79f9f91e533b4c",  # pragma: allowlist secret
            "7f5c9490b848b0c8",  # pragma: allowlist secret
        ),
    ),
    (
        "sub-01/ses-eeg/eeg/sub-01_ses-eeg_electrodes.tsv",
        _sha256(
            "50f00c3adb3b9d04",  # pragma: allowlist secret
            "10ceddff84d51ed4",  # pragma: allowlist secret
            "0fe90aa89f1204bf",  # pragma: allowlist secret
            "0e41415d78083d3e",  # pragma: allowlist secret
        ),
    ),
    (
        "sub-01/ses-eeg/eeg/sub-01_ses-eeg_space-CapTrak_coordsystem.json",
        _sha256(
            "e0e01df82e280710",  # pragma: allowlist secret
            "3fd547af9ccae636",  # pragma: allowlist secret
            "5b79f9f91e533b4c",  # pragma: allowlist secret
            "7f5c9490b848b0c8",  # pragma: allowlist secret
        ),
    ),
    (
        "sub-01/ses-eeg/eeg/sub-01_ses-eeg_space-CapTrak_electrodes.tsv",
        _sha256(
            "0172199f9543eb2e",  # pragma: allowlist secret
            "7f3951518943d94b",  # pragma: allowlist secret
            "15d85c3b842b0677",  # pragma: allowlist secret
            "2a6b4e7130d71949",  # pragma: allowlist secret
        ),
    ),
    (
        "sub-01/ses-eeg/eeg/sub-01_ses-eeg_task-rest_channels.tsv",
        _sha256(
            "df8883c71cb70865",  # pragma: allowlist secret
            "73c90d2e0945c761",  # pragma: allowlist secret
            "a3fd09b3b24f11d3",  # pragma: allowlist secret
            "cef62f84df6e89c5",  # pragma: allowlist secret
        ),
    ),
    (
        "sub-01/ses-eeg/eeg/sub-01_ses-eeg_task-rest_eeg.eeg",
        _sha256(
            "7dd6d01424bcd836",  # pragma: allowlist secret
            "7a0c48b13253389f",  # pragma: allowlist secret
            "3b5fb508755c56b3",  # pragma: allowlist secret
            "214c90f3fe1e8212",  # pragma: allowlist secret
        ),
    ),
    (
        "sub-01/ses-eeg/eeg/sub-01_ses-eeg_task-rest_eeg.json",
        _sha256(
            "afe7def2643befa1",  # pragma: allowlist secret
            "49800d927e18a6e6",  # pragma: allowlist secret
            "7ff824f448fd44bf",  # pragma: allowlist secret
            "42c84b582c124cd5",  # pragma: allowlist secret
        ),
    ),
    (
        "sub-01/ses-eeg/eeg/sub-01_ses-eeg_task-rest_eeg.vhdr",
        _sha256(
            "3ff0577005cd9e49",  # pragma: allowlist secret
            "e672d48a256d365b",  # pragma: allowlist secret
            "4f7cbe1e96fea2a2",  # pragma: allowlist secret
            "6334645ef9b468af",  # pragma: allowlist secret
        ),
    ),
    (
        "sub-01/ses-eeg/eeg/sub-01_ses-eeg_task-rest_eeg.vmrk",
        _sha256(
            "df211bf40a9578b2",  # pragma: allowlist secret
            "4951869f2610cd79",  # pragma: allowlist secret
            "79d68bbb9fa2594a",  # pragma: allowlist secret
            "d10b94f60048287e",  # pragma: allowlist secret
        ),
    ),
    (
        "sub-01/ses-eeg/eeg/sub-01_ses-eeg_task-rest_events.json",
        _sha256(
            "8bf8e6cdeb9eaa40",  # pragma: allowlist secret
            "b57bba4066fa8bc2",  # pragma: allowlist secret
            "30da76217cdeda0c",  # pragma: allowlist secret
            "19efc31de11b9cb0",  # pragma: allowlist secret
        ),
    ),
    (
        "sub-01/ses-eeg/eeg/sub-01_ses-eeg_task-rest_events.tsv",
        _sha256(
            "7f20d56032752bef",  # pragma: allowlist secret
            "41d8efcf3506f105",  # pragma: allowlist secret
            "d747bc34556f3d8b",  # pragma: allowlist secret
            "325df80b2aaba7c5",  # pragma: allowlist secret
        ),
    ),
    (
        "sub-01/ses-eeg/sub-01_ses-eeg_scans.tsv",
        _sha256(
            "1ec0eb51f143b243",  # pragma: allowlist secret
            "afdecd1980060415",  # pragma: allowlist secret
            "fb3fd4b34cfaef50",  # pragma: allowlist secret
            "f843bd813c6c8728",  # pragma: allowlist secret
        ),
    ),
    (
        "sub-01/sub-01_sessions.json",
        _sha256(
            "92b0f5178442768d",  # pragma: allowlist secret
            "cb5b67e4eb14c64d",  # pragma: allowlist secret
            "627e534cec534ce6",  # pragma: allowlist secret
            "a4157ae46e100e04",  # pragma: allowlist secret
        ),
    ),
    (
        "sub-01/sub-01_sessions.tsv",
        _sha256(
            "ca47aa9a0a90bf95",  # pragma: allowlist secret
            "05a6d380c76968d7",  # pragma: allowlist secret
            "7503c1baed42df61",  # pragma: allowlist secret
            "944f754b62c8afd1",  # pragma: allowlist secret
        ),
    ),
)


def _mne_bids_tiny_downloads() -> list[dict[str, str]]:
    return [
        {
            "filename": f"{MNE_BIDS_TINY_NAME}/{relative_path}",
            "url": f"{MNE_BIDS_TINY_RAW_BASE_URL}/{quote(relative_path, safe='/')}",
            "sha256": sha256,
        }
        for relative_path, sha256 in MNE_BIDS_TINY_FILES
    ]


FIXTURE_GROUPS = [
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
                "url": "https://raw.githubusercontent.com/mne-tools/mne-testing-data/master/CNT/scan41_short.cnt",
                "sha256": "f58b7182f6be670159a79090fb666d3f1ed6645f5b488d0016940fd2b8b7e5b6",  # pragma: allowlist secret
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
                "url": "https://raw.githubusercontent.com/mne-tools/mne-testing-data/master/Brainvision/test_NO.vhdr",
                "sha256": "aa3f2d42a1ad3897e702c27d09abdd261f01ccdeb0dae2e674af25fe7be72261",  # pragma: allowlist secret
            },
            {
                "filename": "test_NO.eeg",
                "url": "https://raw.githubusercontent.com/mne-tools/mne-testing-data/master/Brainvision/test_NO.eeg",
                "sha256": "894099d7ea0db262bd2dd84918ff96e5c81e39f7677f0405746faaed1623604b",  # pragma: allowlist secret
            },
            {
                "filename": "test_NO.vmrk",
                "url": "https://raw.githubusercontent.com/mne-tools/mne-testing-data/master/Brainvision/test_NO.vmrk",
                "sha256": "fc02236e72a90124ea04f171a065ae94784ec707bbd96632a86a44499bf7cf27",  # pragma: allowlist secret
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
]

_ALLOWED_DOWNLOAD_HOSTS = {
    "physionet.org",
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


def download_file(url: str, destination: Path) -> None:
    """Download one fixture into ``destination``."""
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
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
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


def fixture_file_is_valid(path: Path, expected_sha256: str) -> bool:
    """Return whether a downloaded fixture exists, is non-empty, and matches hash."""
    if not path.exists() or path.stat().st_size <= 0:
        return False
    return sha256_file(path) == expected_sha256


def validate_fixture_file(path: Path, expected_sha256: str) -> None:
    """Raise if a downloaded fixture is missing, empty, or hash-mismatched."""
    if not path.exists():
        raise FileNotFoundError(f"Downloaded fixture is missing: {path}")
    if path.stat().st_size <= 0:
        raise ValueError(f"Downloaded fixture is empty: {path}")
    actual = sha256_file(path)
    if actual != expected_sha256:
        raise ValueError(
            f"Downloaded fixture hash mismatch for {path.name}: "
            f"expected {expected_sha256}, got {actual}"
        )


def main() -> int:
    """Download all configured fixtures unless they already exist."""
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
    args = parser.parse_args()

    if args.list:
        for fixture_group in FIXTURE_GROUPS:
            print(
                f"{fixture_group['name']}: {fixture_group['description']}"
                f" [{fixture_group['source']}]",
            )
            print(f"  entrypoint: {fixture_group['entrypoint']}")
            for fixture_file in fixture_group["files"]:
                print(f"  - {fixture_file['filename']}")
                print(f"    {fixture_file['url']}")
                print(f"    sha256: {fixture_file['sha256']}")
        return 0

    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)

    for fixture_group in FIXTURE_GROUPS:
        print(
            f"Preparing {fixture_group['name']} "
            f"({fixture_group['source']}, entrypoint {fixture_group['entrypoint']})...",
        )
        for fixture_file in fixture_group["files"]:
            destination = PUBLIC_DIR / fixture_file["filename"]
            expected_sha256 = str(fixture_file["sha256"])
            destination.parent.mkdir(parents=True, exist_ok=True)
            if (
                destination.exists()
                and not args.force
                and fixture_file_is_valid(destination, expected_sha256)
            ):
                print(f"  Using existing fixture: {destination}")
                continue
            if destination.exists() and not args.force:
                print(
                    f"  Existing fixture failed validation; re-downloading {destination.name}..."
                )

            print(f"  Downloading {fixture_file['filename']}...")
            download_file(fixture_file["url"], destination)
            validate_fixture_file(destination, expected_sha256)
            print(f"  Saved {destination}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
