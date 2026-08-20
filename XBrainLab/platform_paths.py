"""Cross-platform writable paths for installed XBrainLab applications."""

from __future__ import annotations

import os
import platform
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

CONFIG_DIR_ENV = "XBRAINLAB_CONFIG_DIR"
DATA_DIR_ENV = "XBRAINLAB_DATA_DIR"
CACHE_DIR_ENV = "XBRAINLAB_CACHE_DIR"
LOG_DIR_ENV = "XBRAINLAB_LOG_DIR"
MODEL_CACHE_DIR_ENV = "XBRAINLAB_MODEL_CACHE_DIR"
SETTINGS_FILENAME = "settings.json"


@dataclass(frozen=True)
class DatasetStorageLayout:
    """Canonical durable locations for local EEG dataset payloads."""

    data_root: Path
    datasets_root: Path
    source_root: Path
    bids_root: Path
    public_fixtures_root: Path
    manifests_root: Path
    quarantine_root: Path


def _user_home(home: str | Path | None) -> Path:
    return Path.home() if home is None else Path(home).expanduser()


def _explicit_path(
    env: Mapping[str, str],
    variable: str,
    user_home: Path,
) -> Path | None:
    raw_path = str(env.get(variable, "")).strip()
    if not raw_path:
        return None
    path = Path(raw_path).expanduser()
    return path if path.is_absolute() else user_home / path


def _absolute_environment_path(
    env: Mapping[str, str],
    variable: str,
    fallback: Path,
) -> Path:
    raw_path = str(env.get(variable, "")).strip()
    path = Path(raw_path).expanduser()
    return path if raw_path and path.is_absolute() else fallback


def user_config_dir(
    *,
    environ: Mapping[str, str] | None = None,
    system_name: str | None = None,
    home: str | Path | None = None,
) -> Path:
    """Return the per-user directory for mutable application settings."""
    env = os.environ if environ is None else environ
    user_home = _user_home(home)
    explicit = _explicit_path(env, CONFIG_DIR_ENV, user_home)
    if explicit is not None:
        return explicit

    current_system = system_name or platform.system()
    if current_system == "Windows":
        roaming = _absolute_environment_path(
            env,
            "APPDATA",
            user_home / "AppData" / "Roaming",
        )
        return roaming / "XBrainLab"
    if current_system == "Darwin":
        return user_home / "Library" / "Application Support" / "XBrainLab"

    xdg_config = _absolute_environment_path(
        env,
        "XDG_CONFIG_HOME",
        user_home / ".config",
    )
    return xdg_config / "xbrainlab"


def user_data_dir(
    *,
    environ: Mapping[str, str] | None = None,
    system_name: str | None = None,
    home: str | Path | None = None,
) -> Path:
    """Return the per-user directory for durable application data."""
    env = os.environ if environ is None else environ
    user_home = _user_home(home)
    explicit = _explicit_path(env, DATA_DIR_ENV, user_home)
    if explicit is not None:
        return explicit

    current_system = system_name or platform.system()
    if current_system == "Windows":
        local = _absolute_environment_path(
            env,
            "LOCALAPPDATA",
            user_home / "AppData" / "Local",
        )
        return local / "XBrainLab"
    if current_system == "Darwin":
        return user_home / "Library" / "Application Support" / "XBrainLab"

    xdg_data = _absolute_environment_path(
        env,
        "XDG_DATA_HOME",
        user_home / ".local" / "share",
    )
    return xdg_data / "xbrainlab"


def dataset_storage_layout(
    *,
    environ: Mapping[str, str] | None = None,
    system_name: str | None = None,
    home: str | Path | None = None,
) -> DatasetStorageLayout:
    """Return the single hierarchy for durable local EEG datasets.

    ``XBRAINLAB_DATA_DIR`` remains the application data root. Dataset payloads
    are kept below its ``datasets`` child so they cannot be confused with
    models, logs, generated outputs, or other application state.
    """
    data_root = user_data_dir(
        environ=environ,
        system_name=system_name,
        home=home,
    )
    datasets_root = data_root / "datasets"
    return DatasetStorageLayout(
        data_root=data_root,
        datasets_root=datasets_root,
        source_root=datasets_root / "source",
        bids_root=datasets_root / "bids",
        public_fixtures_root=datasets_root / "public-fixtures",
        manifests_root=datasets_root / "manifests",
        quarantine_root=datasets_root / "quarantine",
    )


def user_cache_dir(
    *,
    environ: Mapping[str, str] | None = None,
    system_name: str | None = None,
    home: str | Path | None = None,
) -> Path:
    """Return the per-user directory for rebuildable application caches."""
    env = os.environ if environ is None else environ
    user_home = _user_home(home)
    explicit = _explicit_path(env, CACHE_DIR_ENV, user_home)
    if explicit is not None:
        return explicit

    current_system = system_name or platform.system()
    if current_system == "Windows":
        return (
            user_data_dir(environ=env, system_name=current_system, home=user_home)
            / "cache"
        )
    if current_system == "Darwin":
        return user_home / "Library" / "Caches" / "XBrainLab"

    xdg_cache = _absolute_environment_path(
        env,
        "XDG_CACHE_HOME",
        user_home / ".cache",
    )
    return xdg_cache / "xbrainlab"


def user_log_dir(
    *,
    environ: Mapping[str, str] | None = None,
    system_name: str | None = None,
    home: str | Path | None = None,
) -> Path:
    """Return the per-user directory for rotating application logs."""
    env = os.environ if environ is None else environ
    user_home = _user_home(home)
    explicit = _explicit_path(env, LOG_DIR_ENV, user_home)
    if explicit is not None:
        return explicit

    current_system = system_name or platform.system()
    if current_system == "Windows":
        return (
            user_data_dir(environ=env, system_name=current_system, home=user_home)
            / "logs"
        )
    if current_system == "Darwin":
        return user_home / "Library" / "Logs" / "XBrainLab"

    xdg_state = _absolute_environment_path(
        env,
        "XDG_STATE_HOME",
        user_home / ".local" / "state",
    )
    return xdg_state / "xbrainlab" / "logs"


def user_model_cache_dir(
    *,
    environ: Mapping[str, str] | None = None,
    system_name: str | None = None,
    home: str | Path | None = None,
) -> Path:
    """Return the per-user cache boundary for downloaded local LLM models."""
    env = os.environ if environ is None else environ
    user_home = _user_home(home)
    explicit = _explicit_path(env, MODEL_CACHE_DIR_ENV, user_home)
    if explicit is not None:
        return explicit
    return (
        user_data_dir(
            environ=env,
            system_name=system_name,
            home=user_home,
        )
        / "models"
    )


def user_settings_path(
    *,
    environ: Mapping[str, str] | None = None,
    system_name: str | None = None,
    home: str | Path | None = None,
) -> Path:
    """Return the mutable local-assistant settings file for one OS user."""
    return (
        user_config_dir(
            environ=environ,
            system_name=system_name,
            home=home,
        )
        / SETTINGS_FILENAME
    )
