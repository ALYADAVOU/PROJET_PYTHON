# Guide d'installation et de vérification (`installation.md`)

Ce guide explique comment installer **uv**, installer l'outil **Vélo**, le lancer pour la première fois et exécuter les tests et vérifications qualité.

---

## 1. Prérequis

- **Python** `>= 3.13`
- **uv** (gestionnaire de paquets et d'environnements Python)

### Installer `uv`

Sous **Windows (PowerShell)** :
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Sous **Linux / macOS** :
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Vérifiez l'installation :
```bash
uv --version
```

---

## 2. Récupérer le projet et installer `velo`

```bash
git clone https://github.com/ALYADAVOU/PROJET_PYTHON.git
cd PROJET_PYTHON/VELO
```

### Installation pour l'utilisation en ligne de commande (`uv tool install`)

```bash
uv tool install .
```

La commande `velo` est alors disponible globalement dans votre terminal :
```bash
velo --help
velo init
velo status
```

### Installation en environnement de développement (`uv sync`)

```bash
uv sync
uv run velo --help
```

*(Sans `uv`, il est également possible d'utiliser un environnement `venv` standard avec `pip install -e .`.)*

---

## 3. Configuration (`config.yaml`)

Après `velo init`, éditez si besoin `~/.config/velo/config.yaml` :

```yaml
network:
  name: V'Lille
  gbfs_url: https://media.ilevia.fr/opendata/gbfs.json
data:
  folder: ~/.local/share/velo
refresh:
  max_age_days: 7
collect:
  interval_seconds: 120   # minimum 60
alerts:
  low_bikes: 2
  low_docks: 2
dashboard:
  refresh_seconds: 60     # minimum 60
logging:
  level: INFO
```

---

## 4. Tests et qualité du code

Exécuter toute la suite de tests unitaires (les appels API sont simulés) :
```bash
uv run pytest -v
```

Vérifier le style et les annotations avec Ruff :
```bash
uv run ruff check src tests
```

