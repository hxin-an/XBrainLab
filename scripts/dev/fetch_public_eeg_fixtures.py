#!/usr/bin/env python3
"""Download a few small public EEG fixtures for cross-dataset validation."""

from __future__ import annotations

import argparse
import ssl
import sys
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PUBLIC_DIR = ROOT / "tests" / "data" / "public"

FIXTURES = [
    {
        "filename": "physionet-eegmmidb-S008R01.edf",
        "url": "https://physionet.org/files/eegmmidb/1.0.0/S008/S008R01.edf?download=",
        "description": "PhysioNet EEG Motor Movement/Imagery dataset, EDF, 64-channel motor imagery run.",
    },
    {
        "filename": "bbci-competition-iii-O3VR.gdf",
        "url": "https://www.bbci.de/competition/download/competition_iii/graz/O3VR.gdf",
        "description": "BCI Competition III dataset IIIb, GDF, motor imagery with non-stationarity.",
    },
    {
        "filename": "sccn-eeglab_data.set",
        "url": "https://sccn.ucsd.edu/eeglab/download/eeglab_data.set",
        "description": "Official EEGLAB tutorial dataset, EEGLAB .set format.",
    },
]


def download_file(url: str, destination: Path) -> None:
    """Download one fixture into ``destination``."""
    request = urllib.request.Request(url, headers={"User-Agent": "XBrainLab Codex"})
    context = ssl.create_default_context()
    with (
        urllib.request.urlopen(request, context=context, timeout=120) as response,
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
        for fixture in FIXTURES:
            print(f"{fixture['filename']}: {fixture['description']}")
            print(f"  {fixture['url']}")
        return 0

    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)

    for fixture in FIXTURES:
        destination = PUBLIC_DIR / fixture["filename"]
        if destination.exists() and not args.force:
            print(f"Using existing fixture: {destination}")
            continue

        print(f"Downloading {fixture['filename']}...")
        download_file(fixture["url"], destination)
        print(f"Saved {destination}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
