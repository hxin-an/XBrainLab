"""Canonical replay of pre-migration label-import recipes."""

from __future__ import annotations

import json
from pathlib import Path

from XBrainLab.backend.application import (
    ApplicationService,
    ApplyInterpretationCommand,
    ReloadInterpretationRecipeCommand,
    SaveInterpretationRecipeCommand,
    ValidateInterpretationCommand,
)

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "data"
GDF_PATH = (FIXTURE_DIR / "A01T.gdf").resolve()
MAT_PATH = (FIXTURE_DIR / "label" / "A01T.mat").resolve()
CLASS_MAP = {1: "left", 2: "right", 3: "feet", 4: "tongue"}
EVENT_ID = {name: code for code, name in CLASS_MAP.items()}


def test_historical_post_load_recipe_replays_without_legacy_commands(tmp_path):
    recipe_path = tmp_path / "historical-label-recipe.json"
    recipe_path.write_text(
        json.dumps(
            {
                "recipe_id": "historical-label-recipe",
                "interpretation_id": "historical-import",
                "source_path": str(GDF_PATH),
                "source_kind": "file",
                "selected_eeg_files": [str(GDF_PATH)],
                "label_sources": [str(MAT_PATH)],
                "label_carriers": [str(MAT_PATH)],
                "label_carrier": "external_files",
                "skip_labels": False,
                "class_map": {str(key): value for key, value in CLASS_MAP.items()},
                "label_imports": [
                    {
                        "mode": "sequence",
                        "label_carriers": [str(MAT_PATH)],
                        "label_configs": {str(MAT_PATH): {"label_field": "classlabel"}},
                        "target_files": [str(GDF_PATH)],
                        "file_mapping": {str(GDF_PATH): str(MAT_PATH)},
                        "selected_event_names": ["769", "770", "771", "772"],
                        "class_map": {
                            str(key): value for key, value in CLASS_MAP.items()
                        },
                        "success_count": 1,
                    }
                ],
                "recipe_trace": ["label_import:sequence:1"],
            }
        ),
        encoding="utf-8",
    )
    service = ApplicationService()
    try:
        assert service.execute(
            ReloadInterpretationRecipeCommand(recipe_path=str(recipe_path))
        ).ok
        assert service.execute(ValidateInterpretationCommand()).ok
        assert service.execute(ApplyInterpretationCommand(confirmed=True)).ok
        events, event_id = service.dataset.get_loaded_data_list()[0].get_event_list()
        assert event_id == EVENT_ID
        assert events.shape == (288, 3)
        assert service.execute(
            SaveInterpretationRecipeCommand(recipe_path=str(tmp_path / "replayed.json"))
        ).ok
    finally:
        service.close()
