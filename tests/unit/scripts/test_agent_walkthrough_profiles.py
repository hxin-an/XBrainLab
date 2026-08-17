"""Stable-v2 model-free frontend walkthrough profile contracts."""

from pathlib import Path

from XBrainLab.debug.tool_debug_mode import ToolDebugMode
from XBrainLab.llm.action_contracts import AGENT_ACTION_CONTRACTS

PROFILE_ROOT = Path("scripts/dev/agent_tool_walkthrough")


def test_walkthrough_profiles_are_strict_and_cover_exact_target_surface() -> None:
    profiles = [
        ToolDebugMode(str(PROFILE_ROOT / "complete-workflow.json")),
        ToolDebugMode(str(PROFILE_ROOT / "lifecycle-routing.json")),
        ToolDebugMode(str(PROFILE_ROOT / "contract-failures.json")),
    ]

    covered = {call.tool for profile in profiles for call in profile.calls}
    assert covered == AGENT_ACTION_CONTRACTS.tool_names()
    assert {profile.profile_id for profile in profiles} == {
        "complete-workflow",
        "lifecycle-routing",
        "contract-failures",
    }


def test_walkthrough_profiles_never_bypass_product_confirmation() -> None:
    for path in PROFILE_ROOT.glob("*.json"):
        source = path.read_text(encoding="utf-8")
        assert '"confirmed"' not in source
        assert '"authorization_text"' not in source
