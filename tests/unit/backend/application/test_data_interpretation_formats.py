from pathlib import Path

from XBrainLab.backend.application.data_interpretation_formats import (
    LABEL_CARRIER_EXTENSIONS,
    SUPPORTED_EEG_EXTENSIONS,
    format_capabilities,
)


def test_format_capabilities_report_review_and_block_boundaries(tmp_path: Path):
    gdf = tmp_path / "subject.gdf"
    events = tmp_path / "events.tsv"
    xdf = tmp_path / "stream.xdf"
    gdf.write_text("", encoding="utf-8")
    events.write_text("onset\ttrial_type\n", encoding="utf-8")
    xdf.write_text("", encoding="utf-8")

    by_name = {item["name"]: item for item in format_capabilities([xdf, gdf, events])}

    assert by_name["subject.gdf"]["status"] == "needs_review"
    assert "external label alignment" in by_name["subject.gdf"]["message"]
    assert by_name["events.tsv"]["format"] == "BIDS events"
    assert by_name["events.tsv"]["role"] == "external_labels"
    assert by_name["stream.xdf"]["status"] == "blocked"


def test_format_capabilities_report_unsupported_sidecars(tmp_path: Path):
    pickle_file = tmp_path / "labels.pkl"
    log_file = tmp_path / "proprietary.log"
    unknown_file = tmp_path / "session.sidecar"
    pickle_file.write_bytes(b"pickle")
    log_file.write_text("proprietary export", encoding="utf-8")
    unknown_file.write_text("unknown", encoding="utf-8")

    by_name = {
        item["name"]: item
        for item in format_capabilities([pickle_file, log_file, unknown_file])
    }

    assert by_name["labels.pkl"]["status"] == "blocked"
    assert by_name["proprietary.log"]["status"] == "limited"
    assert by_name["session.sidecar"]["status"] == "limited"


def test_format_constants_remain_shared_import_boundaries():
    assert ".gdf" in SUPPORTED_EEG_EXTENSIONS
    assert ".mat" in LABEL_CARRIER_EXTENSIONS
