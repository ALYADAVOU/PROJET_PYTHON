"""Tests unitaires pour le chargement et la validation de config.yaml."""

from pathlib import Path

import pytest

from velo.config import (
    DEFAULT_INTERVAL_SECONDS,
    build_default_config,
    load_config,
    resolve_option,
    save_config,
    slugify_network_name,
)
from velo.models import ConfigError


def test_build_save_and_load_default_config(tmp_path: Path) -> None:
    """Vérifie qu'une configuration par défaut sauvegardée se recharge sans erreur."""
    cfg_path = tmp_path / "config.yaml"
    data_dir = tmp_path / "data"
    cfg = build_default_config(data_folder=data_dir)
    save_config(cfg, cfg_path)

    loaded = load_config(cfg_path)
    assert loaded.network.name == "V'Lille"
    assert loaded.network_slug == "vlille"
    assert loaded.data.folder == data_dir
    assert loaded.collect.interval_seconds == DEFAULT_INTERVAL_SECONDS
    assert loaded.alerts.low_bikes == 2


def test_load_missing_config_raises_config_error(tmp_path: Path) -> None:
    """Un fichier absent doit lever ConfigError avec invitation à lancer velo init."""
    with pytest.raises(ConfigError, match="velo init"):
        load_config(tmp_path / "absent.yaml")


@pytest.mark.parametrize(
    ("yaml_content", "expected_setting"),
    [
        ("collect:\n  interval_seconds: 30\n", "collect.interval_seconds"),
        ("dashboard:\n  refresh_seconds: 10\n", "dashboard.refresh_seconds"),
        ("alerts:\n  low_bikes: -1\n", "alerts.low_bikes"),
        ("alerts:\n  low_docks: true\n", "alerts.low_docks"),
        ("logging:\n  level: TRACE\n", "logging.level"),
        ("network:\n  gbfs_url: ftp://invalid\n", "network.gbfs_url"),
    ],
)
def test_invalid_settings_name_the_offending_key(
    tmp_path: Path,
    yaml_content: str,
    expected_setting: str,
) -> None:
    """Chaque valeur invalide doit nommer explicitement le réglage concerné."""
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml_content, encoding="utf-8")

    with pytest.raises(ConfigError, match=expected_setting):
        load_config(cfg_path)


def test_resolve_option_priority() -> None:
    """L'ordre de priorité est : option CLI > config.yaml > défaut du code."""
    assert resolve_option(300, 120, 60) == 300
    assert resolve_option(None, 120, 60) == 120
    assert resolve_option(None, None, 60) == 60  # type: ignore[arg-type]


def test_slugify_network_name() -> None:
    """V'Lille doit être converti en 'vlille' pour le nom du dossier de données."""
    assert slugify_network_name("V'Lille") == "vlille"
    assert slugify_network_name("Vélo'v Lyon") == "velov_lyon"


def test_cli_returns_nonzero_without_traceback_on_missing_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Le CLI affiche un message clair sur stderr et retourne 1 sans traceback."""
    from velo.cli import main

    monkeypatch.setenv("VELO_CONFIG", str(tmp_path / "missing.yaml"))
    code = main(["status"])
    captured = capsys.readouterr()

    assert code == 1
    assert "Erreur :" in captured.err
    assert "Traceback" not in captured.err

