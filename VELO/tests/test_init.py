"""Tests unitaires pour la commande ``velo init``."""

from pathlib import Path

import pytest

from velo.commands.init import run_init
from velo.models import NetworkError, StationInfo, SystemInfo


def test_init_creates_config_folders_and_fetches_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """velo init crée la config, les dossiers et télécharge les données initiales."""
    cfg_path = tmp_path / "config" / "config.yaml"
    data_dir = tmp_path / "data"

    # Simule un appel réseau réussi sans contacter l'API réelle
    def fake_fetch_static(url: str, network_dir: Path):
        return (
            SystemInfo(system_id="vlille", name="V'Lille"),
            [StationInfo(station_id="42", name="Vauban", lat=50.63, lon=3.04)],
            [],
        )

    monkeypatch.setattr("velo.commands.init.fetch_static_feeds", fake_fetch_static)

    code = run_init(force=False, config_path=cfg_path, data_folder=data_dir)
    out = capsys.readouterr().out

    assert code == 0
    assert cfg_path.exists()
    assert (data_dir / "vlille" / "history").is_dir()
    assert "Connexion à V'Lille : OK (1 stations)" in out


def test_init_preserves_existing_config_unless_force(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sans --force, une configuration existante n'est pas écrasée."""
    cfg_path = tmp_path / "config.yaml"
    data_dir = tmp_path / "data"
    cfg_path.write_text(
        f"network:\n  name: CustomNet\n  gbfs_url: https://example.com/gbfs.json\n"
        f"data:\n  folder: {data_dir}\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "velo.commands.init.fetch_static_feeds",
        lambda url, d: (SystemInfo("c", "CustomNet"), [], []),
    )

    run_init(force=False, config_path=cfg_path, data_folder=data_dir)
    assert "CustomNet" in cfg_path.read_text(encoding="utf-8")

    run_init(force=True, config_path=cfg_path, data_folder=data_dir)
    assert "V'Lille" in cfg_path.read_text(encoding="utf-8")


def test_init_succeeds_with_warning_when_network_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """En cas d'échec réseau, config et dossiers sont quand même créés avec avertissement."""
    cfg_path = tmp_path / "config.yaml"
    data_dir = tmp_path / "data"

    def fake_fail(url: str, network_dir: Path):
        raise NetworkError("Hors ligne")

    monkeypatch.setattr("velo.commands.init.fetch_static_feeds", fake_fail)

    code = run_init(force=False, config_path=cfg_path, data_folder=data_dir)
    out = capsys.readouterr().out

    assert code == 0
    assert cfg_path.exists()
    assert (data_dir / "vlille").is_dir()
    assert "Avertissement" in out

