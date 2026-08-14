from __future__ import annotations

from pathlib import Path

from XBrainLab.platform_paths import (
    dataset_storage_layout,
    user_cache_dir,
    user_log_dir,
    user_model_cache_dir,
)


def test_dataset_storage_layout_keeps_all_eeg_payloads_under_one_data_root() -> None:
    data_root = Path("/mnt/d/xbrainlab-data")

    layout = dataset_storage_layout(
        environ={"XBRAINLAB_DATA_DIR": str(data_root)},
        system_name="Linux",
        home="/home/tester",
    )

    assert layout.data_root == data_root
    assert layout.datasets_root == data_root / "datasets"
    assert layout.source_root == data_root / "datasets" / "source"
    assert layout.bids_root == data_root / "datasets" / "bids"
    assert layout.public_fixtures_root == data_root / "datasets" / "public-fixtures"
    assert layout.manifests_root == data_root / "datasets" / "manifests"
    assert layout.quarantine_root == data_root / "datasets" / "quarantine"
    assert all(
        path.is_relative_to(layout.datasets_root)
        for path in (
            layout.source_root,
            layout.bids_root,
            layout.public_fixtures_root,
            layout.manifests_root,
            layout.quarantine_root,
        )
    )


def test_dataset_hierarchy_does_not_absorb_models_caches_or_logs() -> None:
    environ = {"XBRAINLAB_DATA_DIR": "/mnt/d/xbrainlab-data"}
    layout = dataset_storage_layout(
        environ=environ,
        system_name="Linux",
        home="/home/tester",
    )

    assert not user_model_cache_dir(
        environ=environ,
        system_name="Linux",
        home="/home/tester",
    ).is_relative_to(layout.datasets_root)
    assert not user_cache_dir(
        environ=environ,
        system_name="Linux",
        home="/home/tester",
    ).is_relative_to(layout.datasets_root)
    assert not user_log_dir(
        environ=environ,
        system_name="Linux",
        home="/home/tester",
    ).is_relative_to(layout.datasets_root)
