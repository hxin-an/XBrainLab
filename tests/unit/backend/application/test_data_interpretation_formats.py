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


def test_format_constants_remain_shared_import_boundaries():
    assert ".gdf" in SUPPORTED_EEG_EXTENSIONS
    assert ".mat" in LABEL_CARRIER_EXTENSIONS
