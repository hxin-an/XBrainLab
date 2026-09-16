"""Relocation cannot overwrite a source or publish an incomplete dataset."""

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.dev.moabb_user_journeys.storage import copy_verified_tree, plan_tree_copy


def test_copy_publishes_identical_tree_without_removing_original(
    tmp_path: Path,
) -> None:
    source = tmp_path / "original"
    source.mkdir()
    (source / "data.eeg").write_bytes(b"original-data")
    (source / "nested").mkdir()
    (source / "nested" / "events.tsv").write_text("onset\tvalue\n1\tleft\n")
    root = tmp_path / "durable"
    root.mkdir()
    plan = plan_tree_copy(source, "datasets/source/example", root)

    result = copy_verified_tree(plan, root)

    assert result["status"] == "copied"
    assert (source / "data.eeg").read_bytes() == b"original-data"
    assert (root / "datasets/source/example/data.eeg").read_bytes() == b"original-data"
    assert copy_verified_tree(plan, root)["status"] == "already_verified"


def test_changed_source_is_rejected_before_destination_publication(
    tmp_path: Path,
) -> None:
    source = tmp_path / "original"
    source.mkdir()
    (source / "data.eeg").write_bytes(b"original")
    root = tmp_path / "durable"
    root.mkdir()
    plan = plan_tree_copy(source, "datasets/source/example", root)
    (source / "data.eeg").write_bytes(b"changed")

    with pytest.raises(ValueError, match=r"source.*changed"):
        copy_verified_tree(plan, root)
    assert not (root / "datasets/source/example").exists()


def test_existing_different_destination_is_never_overwritten(tmp_path: Path) -> None:
    source = tmp_path / "original"
    source.mkdir()
    (source / "data.eeg").write_bytes(b"original")
    root = tmp_path / "durable"
    target = root / "datasets/source/example"
    target.mkdir(parents=True)
    (target / "data.eeg").write_bytes(b"other-source")
    plan = plan_tree_copy(source, "datasets/source/example", root)

    with pytest.raises(ValueError, match="destination"):
        copy_verified_tree(plan, root)
    assert (target / "data.eeg").read_bytes() == b"other-source"


def test_source_added_after_plan_is_not_silently_omitted(tmp_path: Path) -> None:
    source = tmp_path / "original"
    source.mkdir()
    (source / "data.eeg").write_bytes(b"original")
    root = tmp_path / "durable"
    root.mkdir()
    plan = plan_tree_copy(source, "datasets/source/example", root)
    (source / "extra.vmrk").write_bytes(b"new")
    with pytest.raises(ValueError, match=r"source.*changed"):
        copy_verified_tree(plan, root)


def test_copy_rejects_destination_overlapping_source(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    with pytest.raises(ValueError, match="overlap"):
        plan_tree_copy(source, "source/child", tmp_path)


@pytest.mark.parametrize("through_parent", [False, True])
@pytest.mark.parametrize("operation", ["plan", "copy"])
def test_source_link_cannot_be_silently_resolved(
    tmp_path: Path, through_parent: bool, operation: str
) -> None:
    physical = tmp_path / "physical"
    source = physical / "recording" if through_parent else physical
    source.mkdir(parents=True)
    (source / "data.eeg").write_bytes(b"original-data")
    alias = tmp_path / "alias"
    if sys.platform == "win32":
        subprocess.run(  # noqa: S603 - exact test-owned junction paths.
            ["cmd", "/d", "/c", "mklink", "/J", str(alias), str(physical)],  # noqa: S607 - Windows built-in, controlled fixture.
            check=True,
            capture_output=True,
            timeout=10,
        )
    else:
        alias.symlink_to(physical, target_is_directory=True)
    linked = alias / "recording" if through_parent else alias
    root = tmp_path / "durable"
    root.mkdir()
    plan = plan_tree_copy(source, "datasets/source/example", root)
    plan["source"] = str(linked)

    with pytest.raises(ValueError, match="Linked"):
        if operation == "plan":
            plan_tree_copy(linked, "datasets/source/example", root)
        else:
            copy_verified_tree(plan, root)
    assert not (root / "datasets/source/example").exists()
    assert (source / "data.eeg").read_bytes() == b"original-data"
