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


def test_wsl_launcher_configures_bounded_ibus_before_qt_runtime() -> None:
    source = LAUNCHER.read_text(encoding="utf-8")

    readiness = "IBus readiness check: timed out; continuing with English input."
    launch = "exec poetry run python run.py"

    assert "export QT_IM_MODULE=ibus" in source
    assert "export GTK_IM_MODULE=ibus" in source
    assert "export XMODIFIERS=@im=ibus" in source
    assert "ibus-chewing" in source
    assert "grep -Fqi 'chewing'" in source
    assert "ibus-libpinyin" not in source
    assert "libpinyin" not in source
    assert "Standard Dachen" not in source
    assert "command -v ibus" in source
    assert "ibus list-engine" in source
    spawn = "timeout 3s ibus-daemon -d -x"
    readiness_poll = "for _ in 1 2 3 4 5 6 7 8 9 10; do"

    assert spawn in source
    assert readiness_poll in source
    assert source.index(spawn) < source.index(readiness_poll)
    assert readiness in source
    assert source.index("export QT_IM_MODULE=ibus") < source.index(launch)
    assert source.count("$InputMethodEnvironment") >= 3
    assert "$InputMethodEnvironment\nset -o pipefail\ncd '$Repo'" in source
    assert "sudo " not in source
    assert "ibus engine " not in source
    assert "ibus-daemon -r" not in source
    assert "ibus-daemon --replace" not in source
    assert "pkill" not in source
    assert "killall" not in source
    assert "kill " not in source
