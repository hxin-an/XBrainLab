from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
LAUNCHER = REPO_ROOT / "scripts" / "launchers" / "xbrainlab_wsl_launcher.ps1"


def test_wsl_launcher_does_not_persist_untrusted_child_output() -> None:
    source = LAUNCHER.read_text(encoding="utf-8")

    assert "Write-LauncherLine $line" not in source
    assert "Windows repo: $RepoWindows" not in source
    assert "WSL repo: $Repo" not in source
    assert 'Write-LauncherLine "Process arguments:' not in source
    assert 'Write-LauncherConsoleLine "Process arguments:' in source
    assert "Write-LauncherConsoleLine $line" in source


def test_wsl_launcher_bounds_retained_log_files() -> None:
    source = LAUNCHER.read_text(encoding="utf-8")

    assert "Remove-ExpiredLauncherLogs" in source
    assert "$LauncherLogRetentionCount" in source
    assert "$LauncherLogMaxBytes" in source


def test_wsl_launcher_keeps_large_rebuildable_caches_on_repo_drive() -> None:
    source = LAUNCHER.read_text(encoding="utf-8")

    assert "$CacheRootWindows" in source
    assert "Split-Path -Qualifier $RepoWindows" in source
    assert '"XBrainLabCache"' in source
    assert "XBRAINLAB_CACHE_ROOT_WIN" in source
    assert "$LegacyModelCacheWindows" in source
    assert "$LegacyGraniteCacheWindows" in source
    assert "Test-Path $LegacyGraniteCacheWindows -PathType Container" in source
    assert "XBRAINLAB_MODEL_CACHE_DIR" in source
    assert "XBRAINLAB_RAG_CACHE_DIR" in source
    assert "export XBRAINLAB_MODEL_CACHE_DIR=" in source
    assert "export XBRAINLAB_RAG_CACHE_DIR=" in source


def test_wsl_launcher_creates_cache_boundaries_before_runtime_start() -> None:
    source = LAUNCHER.read_text(encoding="utf-8")

    cache_creation = "mkdir -p -- '$ModelCache' '$RagCache'"
    launch = "exec poetry run python run.py"

    assert cache_creation in source
    assert source.count("$CacheEnvironment") >= 3
    assert source.index(cache_creation) < source.index(launch)
