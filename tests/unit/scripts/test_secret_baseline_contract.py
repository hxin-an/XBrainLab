from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
import yaml
from detect_secrets.__version__ import VERSION as DETECT_SECRETS_VERSION
from detect_secrets.core import scan as detect_secrets_scan
from detect_secrets.filters.heuristic import is_non_text_file
from detect_secrets.pre_commit_hook import main as run_detect_secrets_hook
from detect_secrets.settings import Settings

ROOT = Path(__file__).resolve().parents[3]
BASELINE_PATH = ROOT / ".secrets.baseline"
PRE_COMMIT_CONFIG_PATH = ROOT / ".pre-commit-config.yaml"
EXPECTED_DETECT_SECRETS_VERSION = "1.5.0"
EXPECTED_EXCLUDE_PATTERN = (
    r"^(?:package-lock\.json|artifacts/user-journeys/moabb-datasets-v1\.json|"
    r"user_docs/assets/manifests/moabb-datasets-v1\.json|"
    r"user_docs/case-studies/manifests/moabb-"
    r"(?:lee2021mobile-erp|ofner2017|physionetmi)\.yml)$"
)
EXPECTED_EXCLUDED_TRACKED_PATHS = frozenset(
    {
        "artifacts/user-journeys/moabb-datasets-v1.json",
        "user_docs/assets/manifests/moabb-datasets-v1.json",
        "user_docs/case-studies/manifests/moabb-lee2021mobile-erp.yml",
        "user_docs/case-studies/manifests/moabb-ofner2017.yml",
        "user_docs/case-studies/manifests/moabb-physionetmi.yml",
    }
)
EXPECTED_UNREADABLE_TRACKED_PATHS = frozenset(
    {
        "XBrainLab/backend/visualization/3Dmodel/brain.ply",
        "XBrainLab/backend/visualization/3Dmodel/head.ply",
        "tests/fixtures/data/A01T.gdf",
        "tests/fixtures/data/A02T.gdf",
        "tests/fixtures/data/A03T.gdf",
        "tests/fixtures/data/label/A01T.mat",
        "tests/fixtures/data/label/A02T.mat",
        "tests/fixtures/data/label/A03T.mat",
        "tests/fixtures/data/multiformat/A01T-mini-real-epo.fif",
        "tests/fixtures/data/multiformat/A01T-mini-real.bdf",
        "tests/fixtures/data/multiformat/A01T-mini-real.edf",
        "tests/fixtures/data/multiformat/A01T-mini-real.eeg",
        "tests/fixtures/data/multiformat/A01T-mini-real.set",
        "tests/fixtures/data/multiformat/A01T-mini-real_raw.fif",
    }
)
EXPECTED_DEFAULT_FILTERS = frozenset(
    {
        "detect_secrets.filters.common.is_invalid_file",
        "detect_secrets.filters.heuristic.is_non_text_file",
    }
)
NON_TEXT_FILTER = "detect_secrets.filters.heuristic.is_non_text_file"
EXPECTED_PLUGIN_POLICY = (
    ("ArtifactoryDetector", ()),
    ("AWSKeyDetector", ()),
    ("AzureStorageKeyDetector", ()),
    ("Base64HighEntropyString", (("limit", 4.5),)),
    ("BasicAuthDetector", ()),
    ("CloudantDetector", ()),
    ("DiscordBotTokenDetector", ()),
    ("GitHubTokenDetector", ()),
    ("GitLabTokenDetector", ()),
    ("HexHighEntropyString", (("limit", 3.0),)),
    ("IbmCloudIamDetector", ()),
    ("IbmCosHmacDetector", ()),
    ("IPPublicDetector", ()),
    ("JwtTokenDetector", ()),
    ("KeywordDetector", (("keyword_exclude", ""),)),
    ("MailchimpDetector", ()),
    ("NpmDetector", ()),
    ("OpenAIDetector", ()),
    ("PrivateKeyDetector", ()),
    ("PypiTokenDetector", ()),
    ("SendGridDetector", ()),
    ("SlackDetector", ()),
    ("SoftlayerDetector", ()),
    ("SquareOAuthDetector", ()),
    ("StripeDetector", ()),
    ("TelegramBotTokenDetector", ()),
    ("TwilioKeyDetector", ()),
)
EXPECTED_FILTER_POLICY = (
    ("detect_secrets.filters.allowlist.is_line_allowlisted", ()),
    (
        "detect_secrets.filters.common.is_baseline_file",
        (("filename", ".secrets.baseline"),),
    ),
    (
        "detect_secrets.filters.common.is_ignored_due_to_verification_policies",
        (("min_level", 2),),
    ),
    ("detect_secrets.filters.heuristic.is_indirect_reference", ()),
    ("detect_secrets.filters.heuristic.is_likely_id_string", ()),
    ("detect_secrets.filters.heuristic.is_not_alphanumeric_string", ()),
    ("detect_secrets.filters.heuristic.is_potential_uuid", ()),
    ("detect_secrets.filters.heuristic.is_prefixed_with_dollar_sign", ()),
    ("detect_secrets.filters.heuristic.is_sequential_string", ()),
    ("detect_secrets.filters.heuristic.is_templated_secret", ()),
    (
        "detect_secrets.filters.regex.should_exclude_line",
        (
            (
                "pattern",
                (
                    r'^\s*"(?:sha256|image_sha256|source_fingerprint|fingerprint_at_start|fingerprint_at_completion|commit_sha|tree_sha|dirty_digest|head_tree_sha|source_content_digest|source_digest)"\s*:',
                    r'^content-hash = "[0-9a-f]{64}"$',
                ),
            ),
        ),
    ),
)


def _freeze_setting(value: object) -> object:
    if isinstance(value, list):
        return tuple(_freeze_setting(item) for item in value)
    if isinstance(value, dict):
        return tuple(
            sorted((str(key), _freeze_setting(item)) for key, item in value.items())
        )
    return value


def _normalized_policy(
    entries: object,
    *,
    identity_key: str,
) -> tuple[tuple[str, tuple[tuple[str, object], ...]], ...]:
    assert isinstance(entries, list)
    normalized = []
    for entry in entries:
        assert isinstance(entry, dict)
        identity = entry.get(identity_key)
        assert isinstance(identity, str)
        settings = tuple(
            sorted(
                (str(key), _freeze_setting(value))
                for key, value in entry.items()
                if key != identity_key
            )
        )
        normalized.append((identity, settings))
    return tuple(normalized)


def _assert_reviewed_baseline_policy(payload: dict[str, object]) -> None:
    assert payload.get("version") == EXPECTED_DETECT_SECRETS_VERSION
    detector_policy = _normalized_policy(
        payload.get("plugins_used"), identity_key="name"
    )
    filter_policy = _normalized_policy(payload.get("filters_used"), identity_key="path")

    assert detector_policy == EXPECTED_PLUGIN_POLICY, "Secret detector policy drifted."
    assert filter_policy == EXPECTED_FILTER_POLICY, "Secret filter policy drifted."


def _record_successful_read(
    filename: str,
    opened: set[str],
    reader: Callable[[str], Iterator[list[str]]],
) -> Iterator[list[str]]:
    batches = reader(filename)
    try:
        first_batch = next(batches)
    except StopIteration:
        return

    opened.add(Path(filename).resolve().relative_to(ROOT.resolve()).as_posix())
    yield first_batch
    yield from batches


def _detect_secrets_hook() -> dict[str, object]:
    payload = yaml.safe_load(PRE_COMMIT_CONFIG_PATH.read_text(encoding="utf-8"))
    matches = [
        hook
        for repository in payload["repos"]
        if repository["repo"] == "https://github.com/Yelp/detect-secrets"
        for hook in repository["hooks"]
        if hook["id"] == "detect-secrets"
    ]
    assert len(matches) == 1
    return matches[0]


def test_detect_secrets_configuration_is_version_locked() -> None:
    payload = yaml.safe_load(PRE_COMMIT_CONFIG_PATH.read_text(encoding="utf-8"))
    repository = next(
        item
        for item in payload["repos"]
        if item["repo"] == "https://github.com/Yelp/detect-secrets"
    )
    hook = _detect_secrets_hook()

    assert DETECT_SECRETS_VERSION == EXPECTED_DETECT_SECRETS_VERSION
    assert Settings.DEFAULT_FILTERS == EXPECTED_DEFAULT_FILTERS
    assert repository["rev"] == f"v{EXPECTED_DETECT_SECRETS_VERSION}"
    assert hook["args"] == ["--baseline", ".secrets.baseline"]
    assert hook["exclude"] == EXPECTED_EXCLUDE_PATTERN


def test_secret_baseline_uses_only_the_reviewed_detector_policy() -> None:
    payload = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))

    _assert_reviewed_baseline_policy(payload)


def test_secret_baseline_policy_rejects_an_empty_detector_set() -> None:
    payload = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    payload["plugins_used"] = []

    with pytest.raises(AssertionError, match="detector policy"):
        _assert_reviewed_baseline_policy(payload)


def test_secret_baseline_policy_rejects_an_unreviewed_filter() -> None:
    payload = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    filters = payload["filters_used"]
    assert isinstance(filters, list)
    filters.append({"path": "tests.always_allow"})

    with pytest.raises(AssertionError, match="filter policy"):
        _assert_reviewed_baseline_policy(payload)


def test_read_spy_attests_only_after_the_reader_yields() -> None:
    opened: set[str] = set()

    assert (
        list(_record_successful_read("missing.txt", opened, lambda _path: iter(())))
        == []
    )
    assert opened == set()
    assert list(
        _record_successful_read("empty.txt", opened, lambda _path: iter(([],)))
    ) == [[]]
    assert opened == {"empty.txt"}


def test_detect_secrets_scans_every_nonexcluded_tracked_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    git = shutil.which("git")
    assert git is not None
    tracked = (
        subprocess.run(  # noqa: S603 - exact resolved git with fixed arguments
            [git, "ls-files", "-z"],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
            timeout=30,
        )
        .stdout.decode("utf-8")
        .split("\0")
    )
    excluded = re.compile(EXPECTED_EXCLUDE_PATTERN)
    excluded_paths = {path for path in tracked if path and excluded.search(path)}
    assert excluded_paths == EXPECTED_EXCLUDED_TRACKED_PATHS
    assert excluded.search("tests/package-lock.json_credentials.py") is None
    scanned = [path for path in tracked if path and excluded.search(path) is None]
    candidate_text_paths = {
        path
        for path in scanned
        if path != ".secrets.baseline"
        and (ROOT / path).is_file()
        and not is_non_text_file(path)
    }
    assert candidate_text_paths >= EXPECTED_UNREADABLE_TRACKED_PATHS
    expected_opened = candidate_text_paths - EXPECTED_UNREADABLE_TRACKED_PATHS
    opened: set[str] = set()
    original_get_lines = detect_secrets_scan._get_lines_from_file

    def record_opened_file(filename: str) -> Iterator[list[str]]:
        yield from _record_successful_read(filename, opened, original_get_lines)

    baseline_before = BASELINE_PATH.read_bytes()
    monkeypatch.chdir(ROOT)
    monkeypatch.setattr(
        detect_secrets_scan,
        "_get_lines_from_file",
        record_opened_file,
    )

    return_code = run_detect_secrets_hook(["--baseline", ".secrets.baseline", *scanned])
    opened_by_general_scan = frozenset(opened)
    lockfile_return_code = run_detect_secrets_hook(
        [
            "--baseline",
            ".secrets.baseline",
            "--disable-filter",
            NON_TEXT_FILTER,
            "poetry.lock",
        ]
    )

    assert return_code == 0
    assert opened_by_general_scan == expected_opened
    assert lockfile_return_code == 0
    assert "poetry.lock" in opened
    assert BASELINE_PATH.read_bytes() == baseline_before
