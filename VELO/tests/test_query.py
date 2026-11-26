"""Tests unitaires et d'intégration CLI pour la commande ``velo query``."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from velo.cli import main
from velo.collection.storage import append_snapshot
from velo.config import build_default_config, save_config
from velo.models import NetworkSnapshot, StationStatus


def _prepare_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    cfg_path = tmp_path / "config.yaml"
    data_dir = tmp_path / "data"
    cfg = build_default_config(data_folder=data_dir)
    save_config(cfg, cfg_path)
    cfg.network_dir.mkdir(parents=True, exist_ok=True)
    (cfg.network_dir / "station_information.json").write_text(
        json.dumps(
            {
                "data": {
                    "stations": [
                        {"station_id": "61", "name": "Gambetta", "lat": 50.62, "lon": 3.05},
                        {
                            "station_id": "43",
                            "name": "Gare Lille Flandres",
                            "lat": 50.63,
                            "lon": 3.07,
                        },
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    tz = timezone(timedelta(hours=1))
    t1 = datetime(2026, 11, 18, 7, 15, tzinfo=tz)
    t2 = datetime(2026, 11, 19, 7, 15, tzinfo=tz)
    append_snapshot(
        cfg.history_dir,
        NetworkSnapshot(
            "V'Lille",
            t1,
            [
                StationStatus("61", 0, 20, True, True, True),
                StationStatus("43", 2, 18, True, True, True),
            ],
        ),
    )
    append_snapshot(
        cfg.history_dir,
        NetworkSnapshot(
            "V'Lille",
            t2,
            [
                StationStatus("61", 0, 20, True, True, True),
                StationStatus("43", 0, 20, True, True, True),
            ],
        ),
    )

    monkeypatch.setenv("VELO_CONFIG", str(cfg_path))
    return cfg_path


def test_cli_query_success_and_missing_data_exit_nonzero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Vérifie le fonctionnement complet de ``velo query`` via le CLI."""
    _prepare_env(tmp_path, monkeypatch)

    code = main(
        [
            "query",
            "--metric",
            "empty_rate",
            "avg_bikes",
            "--days",
            "weekdays",
            "--hours",
            "7-9",
            "--by",
            "station",
            "--top",
            "2",
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "61 Gambetta" in out
    assert "Avertissement" in out

    # Sélection vide : code de sortie non nul et affichage des périodes disponibles
    code_err = main(["query", "--metric", "avg_bikes", "--station", "999"])
    err = capsys.readouterr().err
    assert code_err == 1
    assert "Périodes disponibles" in err
