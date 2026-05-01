#!/usr/bin/env python3
"""Download public EEG fixtures for broader source and format validation."""

from __future__ import annotations

import argparse
import ssl
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
PUBLIC_DIR = ROOT / "tests" / "data" / "public"

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
            },
            {
                "filename": "test_NO.eeg",
                "url": "https://raw.githubusercontent.com/mne-tools/mne-testing-data/master/Brainvision/test_NO.eeg",
            },
            {
                "filename": "test_NO.vmrk",
                "url": "https://raw.githubusercontent.com/mne-tools/mne-testing-data/master/Brainvision/test_NO.vmrk",
            },
        ],
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
        return 0

    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)

    for fixture_group in FIXTURE_GROUPS:
        print(
            f"Preparing {fixture_group['name']} "
            f"({fixture_group['source']}, entrypoint {fixture_group['entrypoint']})...",
        )
        for fixture_file in fixture_group["files"]:
            destination = PUBLIC_DIR / fixture_file["filename"]
            if destination.exists() and not args.force:
                print(f"  Using existing fixture: {destination}")
                continue

            print(f"  Downloading {fixture_file['filename']}...")
            download_file(fixture_file["url"], destination)
            print(f"  Saved {destination}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
