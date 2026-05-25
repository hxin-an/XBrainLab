#!/usr/bin/env python3
"""Download public EEG fixtures for broader source and format validation."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import ssl
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
PUBLIC_DIR = ROOT / "tests" / "fixtures" / "data" / "public"

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
]

TINY_BIDS_NAME = "tiny-bids-eeg"
TINY_BIDS_ENTRYPOINT = (
    "tiny-bids-eeg/sub-01/ses-01/eeg/sub-01_ses-01_task-mi_run-1_eeg.vhdr"
)
TINY_BIDS_STEM = "sub-01_ses-01_task-mi_run-1_eeg"

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


def create_tiny_bids_eeg_fixture(
    *,
    force: bool = False,
    public_dir: Path = PUBLIC_DIR,
    repo_root: Path = ROOT,
) -> None:
    """Create a compact BIDS-like EEG root from checked-in BrainVision fixtures."""
    source_dir = repo_root / "tests" / "fixtures" / "data" / "multiformat"
    source_vhdr = source_dir / "A01T-mini-real.vhdr"
    source_eeg = source_dir / "A01T-mini-real.eeg"
    source_vmrk = source_dir / "A01T-mini-real.vmrk"
    missing = [
        path.name
        for path in (source_vhdr, source_eeg, source_vmrk)
        if not path.exists()
    ]
    if missing:
        raise FileNotFoundError(
            "Cannot create tiny BIDS EEG fixture; missing checked-in "
            f"BrainVision source file(s): {', '.join(missing)}"
        )

    bids_root = public_dir / TINY_BIDS_NAME
    eeg_dir = bids_root / "sub-01" / "ses-01" / "eeg"
    target_vhdr = eeg_dir / f"{TINY_BIDS_STEM}.vhdr"
    target_eeg = eeg_dir / f"{TINY_BIDS_STEM}.eeg"
    target_vmrk = eeg_dir / f"{TINY_BIDS_STEM}.vmrk"

    if (
        target_vhdr.exists()
        and target_eeg.exists()
        and target_vmrk.exists()
        and not force
    ):
        print(f"  Using existing fixture: {bids_root}")
        return

    if bids_root.exists():
        shutil.rmtree(bids_root)
    eeg_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_eeg, target_eeg)
    target_vhdr.write_text(
        source_vhdr.read_text(encoding="utf-8")
        .replace("DataFile=A01T-mini-real.eeg", f"DataFile={target_eeg.name}")
        .replace("MarkerFile=A01T-mini-real.vmrk", f"MarkerFile={target_vmrk.name}"),
        encoding="utf-8",
    )
    target_vmrk.write_text(
        source_vmrk.read_text(encoding="utf-8").replace(
            "DataFile=A01T-mini-real.eeg",
            f"DataFile={target_eeg.name}",
        ),
        encoding="utf-8",
    )

    (bids_root / "dataset_description.json").write_text(
        "{\n"
        '  "Name": "XBrainLab tiny local BIDS EEG fixture",\n'
        '  "BIDSVersion": "1.9.0",\n'
        '  "DatasetType": "raw"\n'
        "}\n",
        encoding="utf-8",
    )
    (bids_root / "participants.tsv").write_text(
        "participant_id\tsex\tage\nsub-01\tn/a\tn/a\n",
        encoding="utf-8",
    )
    (eeg_dir / f"{TINY_BIDS_STEM[:-4]}_channels.tsv").write_text(
        "name\ttype\tunits\tstatus\n"
        "EEG-Fz\tEEG\tuV\tgood\n"
        "EEG-0\tEEG\tuV\tgood\n"
        "EEG-1\tEEG\tuV\tgood\n"
        "EEG-2\tEEG\tuV\tgood\n"
        "EEG-3\tEEG\tuV\tgood\n"
        "EEG-4\tEEG\tuV\tgood\n"
        "EEG-5\tEEG\tuV\tgood\n"
        "EEG-C3\tEEG\tuV\tgood\n",
        encoding="utf-8",
    )
    (eeg_dir / f"{TINY_BIDS_STEM[:-4]}_events.tsv").write_text(
        "onset\tduration\ttrial_type\tvalue\n"
        "1.0\t1.0\tleft_hand\t769\n"
        "3.0\t1.0\tright_hand\t770\n"
        "5.0\t1.0\tfeet\t771\n",
        encoding="utf-8",
    )
    (eeg_dir / f"{TINY_BIDS_STEM[:-4]}_events.json").write_text(
        "{\n"
        '  "trial_type": {\n'
        '    "Description": "Motor imagery class label",\n'
        '    "Levels": {\n'
        '      "left_hand": "Left hand motor imagery",\n'
        '      "right_hand": "Right hand motor imagery",\n'
        '      "feet": "Feet motor imagery"\n'
        "    }\n"
        "  },\n"
        '  "value": {\n'
        '    "Description": "Original event code"\n'
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    print(f"  Saved {bids_root}")


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
        print(
            "tiny-bids-eeg: Compact BIDS-like EEG root generated from checked-in "
            "BrainVision mini fixture. [XBrainLab derived fixture]"
        )
        print(f"  entrypoint: {TINY_BIDS_ENTRYPOINT}")
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

    print("Preparing tiny-bids-eeg (XBrainLab derived fixture)...")
    create_tiny_bids_eeg_fixture(force=args.force)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
