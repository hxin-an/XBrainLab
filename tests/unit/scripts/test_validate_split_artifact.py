from __future__ import annotations

from scripts.dev.validate_split_artifact import validate_artifact


def _artifact():
    return {
        "schema_version": 1,
        "protocol": "trial-wise",
        "seed": 7,
        "repeat": 1,
        "audit": {"ok": True, "dataset_count": 1, "issues": []},
        "environment": {"python": "3.12", "platform": "test"},
        "config": {},
        "datasets": [
            {
                "name": "fold_0",
                "selected": True,
                "indices": {
                    "train": [0, 1],
                    "validation": [2],
                    "test": [3],
                },
                "counts": {"train": 2, "validation": 1, "test": 1},
                "groups": {},
            }
        ],
    }


def test_validate_split_artifact_accepts_clean_payload():
    assert validate_artifact(_artifact()) == []


def test_validate_split_artifact_rejects_leakage_and_failed_audit():
    payload = _artifact()
    payload["audit"]["ok"] = False
    payload["audit"]["issues"] = [{"severity": "error"}]
    payload["datasets"][0]["indices"]["test"] = [1, 3]
    payload["datasets"][0]["counts"]["test"] = 2

    errors = validate_artifact(payload)

    assert any("audit.ok" in error for error in errors)
    assert any("overlap" in error for error in errors)
