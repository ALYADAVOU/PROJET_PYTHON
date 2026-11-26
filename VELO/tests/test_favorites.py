"""Tests unitaires pour la commande ``velo favorites``."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from velo.commands.favorites import run_favorites_add, run_favorites_list, run_favorites_remove
from velo.config import MAX_FAVORITES, build_default_config
from velo.models import DataError, NetworkSnapshot, StationStatus


def _seed_stations(network_dir: Path, count: int = 12) -> None:
    network_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "data": {
            "stations": [
                {"station_id": str(i), "name": f"Station {i}", "lat": 50.6, "lon": 3.0}
                for i in range(1, count + 1)
            ]
        }
    }
    (network_dir / "station_information.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )


def test_favorites_empty_message(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Sans favoris, velo favorites explique comment en ajouter."""
    config = build_default_config(data_folder=tmp_path)
    assert run_favorites_list(config) == 0
    out = capsys.readouterr().out
    assert "velo favorites add" in out


def test_favorites_add_list_remove_and_limits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Vérifie ajout, doublon, limite à 10, affichage et suppression."""
    config = build_default_config(data_folder=tmp_path)
    _seed_stations(config.network_dir, count=12)

    # Identifiant inconnu
    with pytest.raises(DataError, match="inconnu"):
        run_favorites_add(config, "999")

    # Ajout jusqu'à la limite de 10
    for idx in range(1, MAX_FAVORITES + 1):
        assert run_favorites_add(config, str(idx)) == 0

    # Doublon refusé
    with pytest.raises(DataError, match="déjà"):
        run_favorites_add(config, "1")

    # 11e station refusée (limite atteinte)
    with pytest.raises(DataError, match="10"):
        run_favorites_add(config, "11")

    # Affichage temps réel des favoris
    snapshot = NetworkSnapshot(
        network_name="V'Lille",
        last_updated=datetime(2026, 11, 16, 12, 5, tzinfo=UTC),
        statuses=[
            StationStatus("1", 0, 20, True, True, True)
        ],
    )
    monkeypatch.setattr("velo.commands.favorites.fetch_live_status", lambda url, name: snapshot)
    assert run_favorites_list(config) == 0
    out = capsys.readouterr().out
    assert "Station 1" in out
    assert "vide" in out

    # Retrait valide puis erreur sur retrait inexistant
    assert run_favorites_remove(config, "1") == 0
    with pytest.raises(DataError, match="n'est pas dans vos favoris"):
        run_favorites_remove(config, "1")
